"""Freeze source-defined western operator diagnostics without observations.

Only the first two interface rows may differ from the preferred baseline.
Physical flowgate definitions without complete circuit/terminal lineage are
recorded as unexecutable, never mapped by guessing or zero filling.
"""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re

import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/"output/nygrid_2025_western_counterfactuals/mapping"
STATES=["refined_2025_pre_may_case","refined_2025_may21_case","refined_2025_may30_case","refined_2025_case"]
IDS=[1,2,3,4,5,8,10]
NAMES=["DYSINGER EAST","WEST CENTRAL","TOTAL EAST","MOSES SOUTH","CENTRAL EAST - VC","UPNY CONED","SPR/DUN-SOUTH"]
DEPS={};CHECKS=[];LOADED=[]
LITERAL=[[-32,34,37,47],[-28,-29,33,50]]
DOCS=[
 ("2019_Dysinger","tmp/nygrid_2019_diagnostics/references/NYISO_Summer2019_Operating_Study_Appendices","https://www.nyiso.com/documents/20142/3691300/Summer2019-Operating-Study-Appendices-OC-Approved.pdf/7923fe3b-579b-a48d-bda8-8063b309dc08",44),
 ("2014_WestCentral","tmp/nygrid_2019_diagnostics/references/NYISO_DE_WC_Stability_2014","https://www.nyiso.com/documents/20142/1394656/DE_WC_Stability_Limit_Report_final-3.pdf/b461b192-f51d-7bf7-340e-d424b60c84fa",6),
 ("undated_planning","tmp/nygrid_2019_diagnostics/references/NYISO_CRPP_Appendix5_1_Interface_Definitions","https://www.nyiso.com/documents/20142/1410707/CRPP_Appendix_5.1_Interface_Definitions.pdf/6bd50d60-bfd2-4572-31bf-634fbb6c8ddf",2),
]


def sha(p):
    with Path(p).open("rb")as f:return hashlib.file_digest(f,"sha256").hexdigest()


def use(p):
    p=Path(p);p=p if p.is_absolute()else ROOT/p;DEPS[p.relative_to(ROOT).as_posix()]=sha(p);return p


def mat(p,names):
    LOADED.append(dict(path=Path(p).as_posix(),variables=names))
    return loadmat(use(p),simplify_cells=True,variable_names=names)


def check(name,value,error=0):
    CHECKS.append(dict(check=name,passed=bool(value),maximum_absolute_error=float(error)))
    if not value:raise AssertionError(name+" "+str(error))


def close(name,a,b,tol=1e-7):
    a,b=np.asarray(a),np.asarray(b);same=a.shape==b.shape and np.isfinite(a).all()and np.isfinite(b).all()
    e=float(np.max(abs(a-b),initial=0))if same else np.inf;check(name,same and e<=tol,e);return e


def save(name,rows):pd.DataFrame(rows).to_csv(OUT/name,index=False,lineterminator="\n")


def op_from_map(case):
    mapping=np.asarray(case["if"]["map"]);op=np.zeros((7,len(case["branch"])))
    for j,iid in enumerate(IDS):
        rows=mapping[mapping[:,0]==iid,1].astype(int)
        check("unique_interface_members_"+str(iid),len(rows)==len(set(abs(rows))))
        op[j,abs(rows)-1]=np.sign(rows)
    return op


def cuts(case,zones,selected):
    # Net outward AC/DC export, plus its explicitly external part. Subtracting
    # the external part isolates export to the other represented NY zones.
    ac=np.zeros(len(case["branch"]));external=np.zeros_like(ac)
    dc=np.zeros(6);dc_external=np.zeros(6)
    def coefficient(f,t):return int(zones[f]in selected)-int(zones[t]in selected)
    def outside_is_external(f,t):
        outside=t if zones[f]in selected else f
        return zones[outside]=="NA"
    for i,row in enumerate(case["branch"]):
        f,t=map(int,row[:2]);a=coefficient(f,t)*row[10];ac[i]=a
        if a and outside_is_external(f,t):external[i]=a
    links=np.vstack([np.asarray(case["dcline"])[:,:3],[[100,48,1],[100,48,1]]])
    for i,(f,t,status)in enumerate(links):
        f,t=int(f),int(t);a=coefficient(f,t)*status;dc[i]=a
        if a and outside_is_external(f,t):dc_external[i]=a
    return ac,external,dc,dc_external


def physical_coverage(info,full_zones):
    # Literal source member entries. Asterisks in the original tables identify
    # metered terminals. Several West Central entries are compound/transformer
    # entries, so their count is not asserted to be an individual-circuit count.
    dys=[("Somerset","Rochester Station80","SR1-39","345","from"),
         ("Niagara","Rochester Station80","NR2","345","to"),
         ("Lockport","N. Akron","108","115","from"),
         ("Lockport","Oakfield","112","115","from"),
         ("Lockport","Sweden1","111","115","from"),
         ("Lockport","Shelby","113","115","from"),
         ("Lockport","Telegraph","107","115","from"),
         ("Lockport","Telegraph","114","115","from"),
         ("Stolle Road","High Sheldon","67","230","from"),
         ("Andover","Palmiter","157-932","115","from")]
    wc=[("Pannell Road","Clay","PC1","345","to"),("Pannell Road","Clay","PC2","345","to"),
        ("Quaker","Macedon","930","115","from"),("Mortimer","Hook Road/Elbridge","1/7","115","from"),
        ("Mortimer","Elbridge","2","115","from"),("Pannell","Farmington","4","115","from"),
        ("Quaker","Sleight Road","13","115","from"),("Station162","South Perry","906","115","from"),
        ("Hook Road RGE","Hook Road NGRID","TB3","34.5/115","not_explicit_in_table"),
        ("Clyde","Clyde","TR1","34.5/115","not_explicit_in_table"),
        ("Farmington","Farmington","7","34.5/115","not_explicit_in_table"),
        ("Farmington","Farmington","4","34.5/115 and12/115","not_explicit_in_table"),
        ("Stolle Road","High Sheldon","67","230","from"),("Andover","Palmiter","932","115","from")]
    rows=[]
    for source,interface,members in [(DOCS[0],NAMES[0],dys),(DOCS[1],NAMES[1],wc)]:
        for f,t,circuit,kv,meter in members:
            reason="No certified individual-circuit/terminal-to-full191 lineage; coarse aggregate branch identities are insufficient."
            if f=="Stolle Road":reason+=" Retainedbus62 STOLLE_RD230 is accountingZoneB, not a certified physicalZoneA Stolle terminal."
            if f in ["Pannell Road","Pannell"]:reason+=" Pannell physical station is not a separately retained western node."
            if f=="Lockport":reason+=" Lockport115 and its individual outgoing circuits are not separately retained."
            rows.append(dict(interface=interface,source_period=source[0],source_pdf=source[1]+".pdf",source_pdf_page=source[3],source_url=source[2],from_station=f,to_station=t,line_id=circuit,voltage_kv=kv,metered_end=meter,
                exact_full191_branch_row=None,coverage_status="unresolved_exact_circuit_crosswalk",executable_term_created=False,unmatched_term_assumed_zero=False,reason=reason))
    check("physical_source_member_entry_counts",len(dys)==10 and len(wc)==14)
    check("no_added_western_nodes_can_supply_missing_terminals",not any(b>140 and z in {"A","B","C"}for b,z in full_zones.items()))
    save("physical_member_coverage.csv",rows)
    return dict(official2019_Dysinger_member_entries=10,dated2014_WestCentral_member_entries=14,
        certified_complete_full191_physical_alternatives=0,exactly_crosswalked_physical_member_entries=0,
        unexecutable_physical_scenarios=[dict(name="physical2019_Dysinger",reason="No complete circuit/terminal lineage into aggregate full191 network"),dict(name="physical2014_WestCentral",reason="Historical fourteen source entries include compound low-voltage terms with missing retained circuits and some unspecified meter terminals"),dict(name="physical2025_western_gates",reason="Complete2025 as-built member/terminal definitions and exact lineage are not established")],
        missing_evidence=["Circuit/PTID plus meter-terminal orientation mapped to each retained or recovered branch","Treatment of compound/low-voltage physical members and shared A-C paths","Complete2025 membership including any post2019 station/PAR reconfiguration"],
        no_guessed_alias_or_zero_filled_operator=True,scope="No executable physical alternative is emitted; zero certified coverage means unknown mapping, not zero physical flow.")


def build():
    OUT.mkdir(parents=True,exist_ok=True)
    check("fresh_operator_outputs",not(OUT/"operators.npz").exists()and not(OUT/"mapping_receipt.json").exists())
    design=json.loads(use("output/nygrid_2025_western_counterfactuals/design/experiment_plan.json").read_text())
    check("matched_design8651",design["fixed_hours"]==8651 and design["constraints"]["no_internal_flow_fitting"])
    for r in design["dependencies"]:check("design_dependency_"+r["path"],sha(use(r["path"]))==r["sha256"])
    old=mat("output/nygrid_2019_full_stage1/full_year.mat",["base_case","reduced_final_case"])
    full=mat("output/nygrid_2025_downstate/network/network_cases.mat",STATES+["bus_ids","bus_zones","branch_keys"])
    slim=mat("output/nygrid_2025_slim/network/network_cases.mat",["recovery","kept_bus_ids","gamma"])
    info=pd.read_csv(use("tmp/nygrid_2019_reproduction/upstream/Data/npcc_new.csv"),keep_default_na=False).set_index("idx")
    zones=dict(zip(np.asarray(full["bus_ids"],int),np.asarray(full["bus_zones"]).astype(str)))
    check("accounting_zone_labels",set(zones.values()).issubset(set("ABCDEFGHIJK")|{"NA"}))
    source=use("tmp/nygrid_2019_reproduction/upstream/Utility/flow4Plot.m").read_text()
    expected_lines=["A2BResult = -resultBranch(32,PF)+resultBranch(34,PF)+resultBranch(37,PF)+resultBranch(47,PF);","B2CResult = -resultBranch(28,PF)-resultBranch(29,PF)+resultBranch(33,PF)+resultBranch(50,PF);"]
    check("literal_formula_source_exact",all(line in source for line in expected_lines))
    sources=[]
    for name,path,url,page in DOCS:
        pdf=use(path+".pdf");txt=use(path+".txt")
        sources.append(dict(name=name,pdf_path=pdf.relative_to(ROOT).as_posix(),pdf_sha256=sha(pdf),text_path=txt.relative_to(ROOT).as_posix(),source_url=url,examined_page=page))
    check("2019_primary_membership_text",all(s in(ROOT/(DOCS[0][1]+".txt")).read_text(encoding="utf-8")for s in ["SR1-39","NR2","Stolle Road-High Sheldon","157-932"]))
    coverage=physical_coverage(info,zones)
    legacy=op_from_map(old["base_case"]);reduced=old["reduced_final_case"];baseline=[];cuts_all=[];dc_all=[];raw_ac=[];external_ac=[];raw_dc=[];external_dc=[]
    lineage=[];cutrows=[]
    negative=np.zeros((7,410))
    for j,terms in enumerate(LITERAL):
        for signed in terms:
            r=reduced["branch"][abs(signed)-1]
            # The released reduction clears BR_B charging on several retained
            # physical branches. It does not enter lossless DC branch laws.
            # Every other branch field, including unique original endpoints,
            # R/X, tap, phase, status and limits, must match exactly.
            identity_columns=[i for i in range(13)if i!=4]
            candidate=np.flatnonzero(np.all(np.isclose(old["base_case"]["branch"][:,identity_columns],r[None,identity_columns],atol=1e-12,rtol=0),axis=1))
            check("literal_to_full_unique_DC_identity_"+str(abs(signed)),len(candidate)==1)
            idx=int(candidate[0]);negative[j,idx]+=np.sign(signed)
            canonical=old["base_case"]["branch"][idx]
            f,t=map(int,r[:2]);lineage.append(dict(interface=NAMES[j],released57_signed_row=signed,full191_signed_row=int(np.sign(signed)*(idx+1)),from_bus=f,to_bus=t,from_name=info.loc[f,"name"],to_name=info.loc[t,"name"],from_zone=zones[f],to_zone=zones[t],from_kv=info.loc[f,"Vn"],to_kv=info.loc[t,"Vn"],unique_full_DC_row_match=True,reduced_BR_B=float(r[4]),source_full_BR_B=float(canonical[4]),charging_scope="BR_B is omitted from DC laws; released reduction clears charging on some retained branches",classification="known_wrong_plot_operator_not_candidate_fix"))
            for state in STATES:close(state+"_literal_row_preserved_"+str(idx+1),full[state]["branch"][idx],canonical,0)
    old_west=np.pad(legacy[:2],((0,0),(0,410-legacy.shape[1])))
    for state in STATES:
        case=full[state];check(state+"_full191_410",case["branch"].shape==(410,13)and len(case["bus"])==191)
        rec=slim["recovery"][state.removesuffix("_case")]
        base=np.asarray(rec["full_interface_branch_matrix"],float);check(state+"_operator_dimensions",base.shape==(7,410))
        close(state+"_west_equals_published_corrected2019",base[:2],old_west,0)
        whole=base.copy();direct=np.zeros((7,6));ra=[];ea=[];rd=[];ed=[]
        for j,selected in enumerate([{"A"},{"A","B"}]):
            ac,ext,dc,dext=cuts(case,zones,selected);whole[j]=ac-ext;direct[j]=dc-dext
            ra.append(ac);ea.append(ext);rd.append(dc);ed.append(dext)
            for i in np.flatnonzero(ac):
                f,t=map(int,case["branch"][i,:2]);cutrows.append(dict(state=state,region="A"if j==0 else"A+B",branch_row=i+1,outward_coefficient=ac[i],external_outward_coefficient=ext[i],interface_coefficient=whole[j,i],from_bus=f,to_bus=t,from_zone=zones[f],to_zone=zones[t]))
        close(state+"_independent_cut_equals_baseline",whole,base,0)
        close(state+"_accounting_west_has_no_DC_crossing",direct,np.zeros((7,6)),0)
        baseline.append(base);cuts_all.append(whole);dc_all.append(direct);raw_ac.append(ra);external_ac.append(ea);raw_dc.append(rd);external_dc.append(ed)
    baseline=np.asarray(baseline);cutop=np.asarray(cuts_all);dcop=np.asarray(dc_all)
    for label,array in [("baseline",baseline),("cut",cutop),("DC",dcop),("rawAC",np.array(raw_ac)),("externalAC",np.array(external_ac))]:
        close(label+"_state_invariant",array,np.broadcast_to(array[0],array.shape),0)
    negative[2:]=baseline[0,2:]
    check("negative_control_changes_only_Western",np.array_equal(negative[2:],baseline[0,2:])and not np.array_equal(negative[:2],baseline[0,:2]))
    save("literal_operator_exact_lineage.csv",lineage);save("accounting_cut_members.csv",cutrows)
    scenarios=[dict(name="baseline_corrected_full191_operator",key="baseline_corrected_full191_operator",dc_key="baseline_corrected_full191_operator_dc",label="Preferred baseline operator reconstructed on full191",is_diagnostic_only=False,source_basis="Current recovery operator; Western rows exactly preserve corrected released2019 interface maps"),
        dict(name="independent_zone_cuts",key="independent_zone_cuts",dc_key="independent_zone_cuts_dc",label="Independent accounting-zone A/A+B cuts with external-border removal",is_diagnostic_only=True,source_basis="Bus-zone membership plus complete active AC and6DC boundary enumeration; exact conservation null control"),
        dict(name="literal_released_plot_negative_control",key="literal_released_plot_negative_control",dc_key="literal_released_plot_negative_control_dc",label="Known-bug released Western plotting formulas; negative control",is_diagnostic_only=True,source_basis="Original57-bus flow4Plot Western formulas remapped by unique exact electrical-row lineage; not a correction candidate")]
    plan=dict(frozen_utc=datetime.now(timezone.utc).isoformat(),dataset_type="operator",qualified_hours=8651,source_only=True,internal_observation_files_read=False,operator_fit_to_internal_observations=False,
        scenarios=scenarios,only_first_two_rows_changed=True,retained_other_five_rows="Current baseline, including refined downstate definitions; not stale2019downstate formulas",
        branch_axis="full191 current410branchorder",DC_axis="original4DC_then_P34_25118_25119",operator_shape=[7,410],DC_operator_shape=[7,6],topology_states=STATES,operators_state_invariant=True,
        cut_formula="interface = raw native-zone outward AC/DC cut minus explicitly external outward AC/DC part; all6DCterms carried even whenzero",
        physical_mapping=coverage,primary_sources=sources,forbidden=["No observed interface inputs","No tuning signs/scales/memberweights","No guessed alias or zero-filled missing physical member","No physical-topology or PG changes"],
        selected_mat_variables=LOADED,dependencies=[dict(path=p,sha256=h)for p,h in DEPS.items()])
    planpath=OUT/"mapping_plan.json";check("mapping_plan_is_new",not planpath.exists());planpath.write_text(json.dumps(plan,indent=2)+"\n",encoding="utf-8")
    # Only after definitions are sealed, inspect saved baseline predictions for
    # algebraic reproducibility. No target observation or metric is loaded.
    replay=mat("output/nygrid_2025_western_audit/replay/dated_combined.mat",["timestamp_utc","network_state_ids","bus_va","interface_pf","common_scoring_mask","gamma"])
    q=np.load(use("output/nygrid_2025_western_audit/replay/paired_common_mask.npy"),allow_pickle=False)
    check("fixed8651_mask",q.dtype==bool and q.shape==(8760,)and q.sum()==8651 and np.array_equal(q,replay["common_scoring_mask"]))
    checks=[]
    for j,state in enumerate(STATES):
        mask=q&(np.asarray(replay["network_state_ids"]).astype(str)==state)
        rec=slim["recovery"][state.removesuffix("_case")]
        theta=np.deg2rad(replay["bus_va"][mask])@rec["angle_lift"].T+rec["angle_offset"]
        b=full[state]["branch"].copy();b[210,10]=0;idx={int(v):i for i,v in enumerate(full["bus_ids"])}
        tap=np.where(b[:,8]==0,1.,b[:,8]);k=b[:,10]*float(full[state]["baseMVA"])/(b[:,3]*tap)
        flow=k*(theta[:,[idx[int(v)]for v in b[:,0]]]-theta[:,[idx[int(v)]for v in b[:,1]]]-np.deg2rad(b[:,9]))
        predicted=flow@baseline[j].T
        e=close(state+"_baseline148_to_full191_operator_invariance",predicted,replay["interface_pf"][mask])
        checks.append(dict(state=state,hours=int(mask.sum()),maximum_baseline_recovery_error_model_mw=e))
    use(planpath);use(Path(__file__))
    links=np.vstack([full[STATES[0]]["dcline"][:,:2],[[100,48],[100,48]]]).astype(int)
    np.savez_compressed(OUT/"operators.npz",baseline_corrected_full191_operator=baseline[0],baseline_corrected_full191_operator_dc=np.zeros((7,6)),
        independent_zone_cuts=cutop[0],independent_zone_cuts_dc=dcop[0],literal_released_plot_negative_control=negative,literal_released_plot_negative_control_dc=np.zeros((7,6)),
        raw_native_cut_branch=np.array(raw_ac)[0],external_cut_branch=np.array(external_ac)[0],raw_native_cut_dc=np.array(raw_dc)[0],external_cut_dc=np.array(external_dc)[0],
        interface_names=np.array(NAMES),state_names=np.array(STATES),full_bus_ids=np.asarray(full["bus_ids"],int),full_branch_endpoints=full[STATES[0]]["branch"][:,:2].astype(int),DC_endpoints=links,
        qualified=q,timestamp_utc=np.asarray(replay["timestamp_utc"]).astype(str),gamma=float(replay["gamma"]))
    save("baseline_recovery_checks.csv",checks);save("checks.csv",CHECKS)
    check("all_inputs_unchanged",all(sha(ROOT/p)==h for p,h in DEPS.items()))
    receipt=dict(passed=True,dataset_type="operator",created_utc=datetime.now(timezone.utc).isoformat(),status="source_definitions_frozen_and_baseline_invariance_verified",qualified_hours=8651,
        operators_path=(OUT/"operators.npz").relative_to(ROOT).as_posix(),operators_sha256=sha(OUT/"operators.npz"),mapping_plan_path=planpath.relative_to(ROOT).as_posix(),mapping_plan_sha256=sha(planpath),
        scenario_definitions=scenarios,operator_shape=[7,410],DC_operator_shape=[7,6],state_invariant=True,full191_branch_count=410,full191_bus_count=191,slim_bus_count=148,states=STATES,
        no_internal_observation_files_read=True,no_parameter_or_operator_fit=True,no_PF_or_PG_write=True,no_network_solve=True,negative_control_is_known_wrong=True,complete_source_backed_physical_alternatives=0,
        physical_coverage=coverage,exact_Western_baseline_members=[[-58,61,69,212],[-54,-55,59,72]],exact_literal_Western_negative_members=[[-57,59,60,68],[-53,-54,58,216]],
        invariance_scope="Within-zone changes preserving net injections and external boundary components cannot alter these complete represented western cuts. Physical flowgate mismatch is not identified by this equality.",
        checks=CHECKS,failed_checks=0,all_input_hashes_unchanged=True,selected_mat_variables=LOADED,
        dependencies=[dict(path=p,sha256=h)for p,h in DEPS.items()],outputs=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p))for p in sorted(OUT.iterdir())if p.is_file()])
    (OUT/"mapping_receipt.json").write_text(json.dumps(receipt,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:receipt[k]for k in ["passed","dataset_type","qualified_hours","complete_source_backed_physical_alternatives","failed_checks"]},indent=2))


if __name__=="__main__":build()
