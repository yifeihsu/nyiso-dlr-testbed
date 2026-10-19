"""Independent full192/148 Dover phase-affine network validation.

No production reducer/solver or observed-flow data are imported. Two parallel
bank phase columns are derived directly from the branch equations and block
elimination, including differential circulation and terminal response tests.
"""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json
import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/"output/nygrid_2025_dover_parameters"
DEST=OUT/"local_audit"
PARENT=ROOT/"output/nygrid_2025_line_parameters/overlays/engineering_nominal"


def require(ok,text):
    if not bool(ok):raise ValueError(text)


def sha(path):
    with Path(path).open("rb") as stream:return hashlib.file_digest(stream,"sha256").hexdigest()


def maxabs(x):return float(np.max(np.abs(x),initial=0.))


def system(case,remove_old211=False):
    branch=np.array(case["branch"],copy=True);bus=np.asarray(case["bus"]);ids=bus[:,0].astype(int);lookup={b:j for j,b in enumerate(ids)}
    if remove_old211:
        require(np.array_equal(branch[210,:2],[48,100]),"Old controlled aggregate identity changed")
        branch[210,10]=0
    C=np.zeros((len(branch),len(bus)))
    for j,row in enumerate(branch):C[j,lookup[int(row[0])]]+=1;C[j,lookup[int(row[1])]]-=1
    k=float(case["baseMVA"])*branch[:,10]/(branch[:,3]*np.where(branch[:,8]==0,1,branch[:,8]))
    F=k[:,None]*C;h=-k*np.deg2rad(branch[:,9])
    return dict(C=C,k=k,F=F,h=h,B=C.T@F,p=C.T@h,ids=ids,lookup=lookup,branch=branch)


def validate():
    path=OUT/"network/network_receipt.json";proof=json.loads(path.read_text())
    require(proof["passed"] and not proof["internal_interface_observations_read"],"Network source isolation failed")
    before={item["path"]:item["sha256"] for item in proof["dependencies"]}
    for p,h in before.items():require(sha(ROOT/p)==h,"Network dependency changed: "+p)
    before[str(path.relative_to(ROOT)).replace("\\","/")]=sha(path)
    parent=loadmat(PARENT/"full191_network_cases.mat",simplify_cells=True)["refined_2025_case"]
    parent_slim=loadmat(PARENT/"network_cases.mat",simplify_cells=True)
    reg=pd.read_csv(ROOT/"output/nygrid_2025_downstate/network/branch_register.csv",keep_default_na=False)
    sreg=pd.read_csv(ROOT/"output/nygrid_2025_slim/network/branch_register.csv",keep_default_na=False)
    source_ix=np.flatnonzero(reg.source_branch_row.to_numpy(int)>0)
    direct=sreg.iloc[:244].full191_branch_row.to_numpy(int)-1
    keep=np.asarray(parent_slim["kept_bus_ids"],int)
    records=[];responses=[]
    for item in proof["scenarios"]:
        p=ROOT/item["path"];require(sha(p)==item["sha256"],"Network scenario changed")
        before[item["path"]]=item["sha256"]
        d=loadmat(p,simplify_cells=True);full,slim,rec=d["full_case"],d["slim_case"],d["recovery"]
        require(full["bus"].shape==(192,13) and full["branch"].shape==(413,13),"Dover detail axes changed")
        require(slim["bus"].shape==(148,13) and slim["branch"].shape==(274,13),"Retained axes changed")
        require(np.array_equal(full["bus"][:191],parent["bus"]) and np.array_equal(d["kept_bus_ids"],keep),"Old bus axes/values changed")
        require(np.array_equal(full["gen"],parent["gen"]) and np.array_equal(full["dcline"],parent["dcline"]),"Original generator/fourDC data changed")
        require(np.array_equal(full["branch"][source_ix],parent["branch"][source_ix]),"Original97circuits changed")
        immutable=[j for j in range(410) if j not in [392,393]]
        require(np.array_equal(full["branch"][immutable],parent["branch"][immutable]),"Unrelated old branch changed")
        require(np.array_equal(full["branch"][410:412,:2],[[20003,21001],[20003,21001]]) and full["branch"][393,10]==0,"Parallel-bank/retired-route topology incorrect")
        require(np.array_equal(full["branch"][412,:2],[21001,20002]) and np.array_equal(full["branch"][392,:2],[20001,20003]),"Line section ports incorrect")
        require(np.array_equal(slim["branch"][:244],full["branch"][direct]),"Direct244record identity changed")
        require(np.array_equal(slim["branch"][:,[0,1,10]],parent_slim["refined_2025_case"]["branch"][:,[0,1,10]]),"Condensed graph/support changed")
        require(str(rec["phase_units"])=="radians;MATPOWER_SHIFT_sign","Ambiguous phase units/sign")
        require(np.array_equal(rec["input_bank_rows_1based"],[411,412]),"Phase-column device order changed")
        for controlled in [False,True]:
            net=system(full,controlled);small=system(slim,controlled)
            ri=np.array([net["lookup"][b] for b in keep]);ii=np.array([j for j,b in enumerate(net["ids"]) if b not in set(keep)])
            require(len(ii)==44 and np.all(full["bus"][ii,2:6]==0),"Eliminated-bus zero-injection contract failed")
            require(not np.isin(full["gen"][:,0],net["ids"][ii]).any() and not np.isin(full["dcline"][:,:2],net["ids"][ii]).any(),"Eliminated bus has external injection/control terminal")
            Bii=net["B"][np.ix_(ii,ii)];Bir=net["B"][np.ix_(ii,ri)];Bri=net["B"][np.ix_(ri,ii)]
            L=np.zeros((192,148));L[ri]=np.eye(148);L[ii]=-np.linalg.solve(Bii,Bir)
            offset=np.zeros(192);offset[ii]=-np.linalg.solve(Bii,net["p"][ii])
            K=np.zeros((413,2));K[410,0]=-net["k"][410];K[411,1]=-net["k"][411]
            nodal=net["C"].T@K
            D=np.zeros((192,2));D[ii]=-np.linalg.solve(Bii,nodal[ii])
            S=nodal[ri]+Bri@D[ii];W=net["F"]@D+K
            H=net["F"]@L;h=net["F"]@offset+net["h"]
            reduced=net["B"][np.ix_(ri,ri)]+Bri@L[ii]
            zones=dict(zip(net["ids"],np.asarray(d["full_bus_zones"]).astype(str)))
            zonepairs=[("A","B"),("B","C"),("ABCDE","FGHIJK"),("D","E"),("E","F"),("ABCDEFG","HIJK"),("I","J")]
            interface=np.zeros((7,413))
            for q,(left,right) in enumerate(zonepairs):
                for j,row in enumerate(net["branch"]):
                    a,b=zones[int(row[0])],zones[int(row[1])]
                    interface[q,j]=row[10]*(int(a in set(left) and b in set(right))-int(b in set(left) and a in set(right)))
            errors=dict(angle_lift_error=maxabs(L-rec["angle_lift"]),angle_phase_basis_error=maxabs(D-rec["angle_phase_basis"]),
                branch_phase_basis_error_MW_per_rad=maxabs(W-rec["branch_flow_phase_basis"]),
                projected_phase_basis_error_MW_per_rad=maxabs(S-rec["reduced_phase_bus_basis"]),
                inherited_interface_branch_membership_error=maxabs(interface-rec["full_interface_branch_matrix"]),
                inherited_interface_angle_operator_error_MW_per_rad=maxabs(interface@H-rec["interface_angle_matrix"]),
                inherited_interface_phase_operator_error_MW_per_rad=maxabs(interface@W-rec["interface_phase_basis"]),
                inherited_interface_offset_error_model_MW=maxabs(interface@h-rec["interface_flow_offset"]),
                Schur_realization_error_MW_per_rad=maxabs(reduced-small["B"]))
            # Removing original211 affects only its retained-angle coefficient;
            # both Dover phase-affine columns remain unchanged.
            require(max(errors.values())<1e-8,"Independent phase-affine matrix mismatch")
            phi=np.array([.07,-.03]);theta=np.sin(np.arange(148))*.01
            theta_full=L@theta+offset+D@phi
            flow=net["F"]@theta_full+net["h"]+K@phi
            slim_shift=np.deg2rad(slim["branch"][:,9])+rec["slim_shift_phase_basis"]@phi
            slim_flow=small["F"]@theta-small["k"]*slim_shift
            interior_error=maxabs((net["C"].T@flow)[ii])
            retained_error=maxabs((net["C"].T@flow)[ri]-small["C"].T@slim_flow)
            direct_error=maxabs(flow[direct]-slim_flow[:244])
            require(max(interior_error,retained_error,direct_error)<1e-8,"Unequal-bank affine realization failed")
            # Anti-symmetric bank phases create equal/opposite circulation and
            # zero change at retained ports for equalX/tap parallel banks.
            differential=np.array([.05,-.05]);retained_phase=maxabs(S@differential)
            circulation=W@differential
            require(retained_phase<1e-8 and maxabs(circulation[:410])<1e-8 and abs(circulation[410]+circulation[411])<1e-8,"Differential bank circulation leaked into external transfer")
            weights=net["k"][[410,411]];expected_shift=-weights/weights.sum()
            eq=np.flatnonzero((slim["branch"][:,0]==35)&(slim["branch"][:,1]==20001));require(len(eq)==1,"Dover retained series-path pair changed")
            shift_error=maxabs(rec["slim_shift_phase_basis"][eq[0]]-expected_shift)
            require(shift_error<1e-12,"Series path phase aggregation/sign mismatch")
            # Directly derive the two-bank response to applied SHIFT after
            # fixing one retained-angle gauge; no observed targets are used.
            nonref=np.arange(1,148);Theta=np.zeros((148,2));Theta[nonref]=-np.linalg.solve(reduced[np.ix_(nonref,nonref)],S[nonref])
            response=(H@Theta+W)[[410,411]]
            require(np.linalg.matrix_rank(response)==2,"Two individual bank flows are not jointly controllable in this scenario")
            response_condition=float(np.linalg.cond(response))
            responses.append(dict(scenario=item["scenario"],old211_disabled=controlled,response_condition_number=response_condition,
                response11_MW_per_rad=response[0,0],response12_MW_per_rad=response[0,1],response21_MW_per_rad=response[1,0],response22_MW_per_rad=response[1,1],
                target_fit_or_observation_used=False))
            records.append(dict(scenario=item["scenario"],old211_disabled=controlled,**errors,
                arbitrary_angle_unequal_phase_interior_KCL_error=interior_error,retained_KCL_error=retained_error,direct_branch_error=direct_error,
                differential_bank_phase_retained_response=retained_phase,weighted_reversed_equivalent_shift_error=shift_error,
                original97source_rows_and_operating_templates_unchanged=True))
    before[str(Path(__file__).relative_to(ROOT)).replace("\\","/")]=sha(__file__)
    require({p:sha(ROOT/p) for p in before}==before,"Source changed during independent network audit")
    pd.DataFrame(records).to_csv(DEST/"Dover_phase_affine_checks.csv",index=False)
    pd.DataFrame(responses).to_csv(DEST/"Dover_independent_two_bank_response.csv",index=False)
    report=dict(passed=True,created_utc=datetime.now(timezone.utc).isoformat(),scenario_control_state_checks=len(records),
        full192_to_same148_affine_identity_validated=True,parallel_bank_differential_circulation_validated=True,
        nontrivial_unequal_phase_fixture_radians=[.07,-.03],differential_phase_fixture_radians=[.05,-.05],
        original97source_circuits_and_input_templates_preserved=True,retained244direct_and30derived_support_preserved=True,
        physical_hardware_or_factory_impedance_certified=False,observed_flows_read=False,phase_targets_fit=False,
        source_dependencies=before,source_hashes_unchanged=True,checks=records,
        outputs={name:sha(DEST/name) for name in ["Dover_phase_affine_checks.csv","Dover_independent_two_bank_response.csv"]})
    (DEST/"Dover_network_independent_validation.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(dict(passed=True,checks=len(records),maximum_matrix_error=max(row[k] for row in records for k in row if "error" in k),
                         maximum_two_bank_response_condition=max(r["response_condition_number"] for r in responses)),indent=2))


if __name__=="__main__":validate()
