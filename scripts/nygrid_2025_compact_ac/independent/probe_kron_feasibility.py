"""Independent complex-Y elimination audit; no compact implementation imports.

No PF or OPF is run. Existing detailed PF points check voltage/current recovery;
random retained phasors check the linear network identity off the solved points.
"""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess
import numpy as np
import pandas as pd
from scipy.io import loadmat
from scipy.linalg import solve

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'output/nygrid_2025_compact_ac/independent'
SOURCE=ROOT/'output/nygrid_2025_acpf_profile_audit/acpf'


def rec(p):
    with p.open('rb') as f:h=hashlib.file_digest(f,'sha256').hexdigest()
    return dict(path=p.relative_to(ROOT).as_posix(),sha256=h)


def require(ok,msg):
    if not ok:raise AssertionError(msg)


def network(m):
    bus=np.asarray(m['bus'],float);branch=np.asarray(m['branch'],float)
    n=len(bus);nl=len(branch);base=float(m['baseMVA'])
    lookup={int(b):i for i,b in enumerate(bus[:,0])}
    f=np.array([lookup[int(b)] for b in branch[:,0]]);t=np.array([lookup[int(b)] for b in branch[:,1]])
    on=branch[:,10]>0;z=branch[:,2]+1j*branch[:,3]
    require((abs(z[on])>0).all(),'Active branch has zero series impedance')
    y=np.zeros(nl,complex);y[on]=1/z[on]
    charge=np.where(on,1j*branch[:,4]/2,0j)
    tau=np.where(branch[:,8]==0,1.,branch[:,8])*np.exp(1j*np.deg2rad(branch[:,9]))
    require((abs(tau)>0).all(),'Invalid tap ratio')
    yff=(y+charge)/(tau*np.conj(tau));yft=-y/np.conj(tau);ytf=-y/tau;ytt=y+charge
    yf=np.zeros((nl,n),complex);yt=np.zeros((nl,n),complex);series=np.zeros((nl,n),complex)
    j=np.arange(nl);yf[j,f]+=yff;yf[j,t]+=yft;yt[j,f]+=ytf;yt[j,t]+=ytt
    series[j,f]+=y/tau;series[j,t]-=y
    Y=np.diag((bus[:,4]+1j*bus[:,5])/base).astype(complex)
    for k in range(nl):
        Y[f[k],f[k]]+=yff[k];Y[f[k],t[k]]+=yft[k]
        Y[t[k],f[k]]+=ytf[k];Y[t[k],t[k]]+=ytt[k]
    return Y,yf,yt,series,f,t,on


def component_audit(n,f,t,on,eliminated):
    adjacency=[set() for _ in range(n)]
    for a,b in zip(f[on],t[on]):adjacency[a].add(int(b));adjacency[b].add(int(a))
    es=set(map(int,eliminated));remaining=set(es);components=[]
    while remaining:
        start=remaining.pop();todo=[start];component={start};anchors=set()
        while todo:
            a=todo.pop()
            for b in adjacency[a]:
                if b not in es:anchors.add(b)
                elif b in remaining:remaining.remove(b);component.add(b);todo.append(b)
        require(bool(anchors),'Eliminated component has no retained connection')
        components.append(dict(eliminated_size=len(component),retained_connections=len(anchors)))
    return components


def inspect(label,m,kept_ids,solution=None):
    bus=np.asarray(m['bus']);ids=bus[:,0].astype(int);index={bid:k for k,bid in enumerate(ids)}
    require(set(kept_ids)<=set(ids),'Retained 148 IDs absent from full case')
    keep=np.array([index[int(x)] for x in kept_ids]);elim=np.array([i for i,x in enumerate(ids) if x not in set(kept_ids)])
    require(len(keep)==148,'Retained interface size')
    require(np.max(abs(bus[elim,2:4]),initial=0)==0,'Eliminated constant-P/Q injection is nonzero')
    require(np.all(bus[elim,1]==1),'Eliminated bus has REF/PV/inactive control type')
    require(not np.isin(np.asarray(m['gen'])[:,0],ids[elim]).any(),'Generator bus eliminated, including offline devices')
    if 'dcline' in m and np.asarray(m['dcline']).size:
        require(not np.isin(np.asarray(m['dcline'])[:,:2],ids[elim]).any(),'Controlled-transfer endpoint eliminated')
    Y,yf,yt,ys,f,t,on=network(m)
    components=component_audit(len(bus),f,t,on,elim)
    Yee=Y[np.ix_(elim,elim)];Yek=Y[np.ix_(elim,keep)];Yke=Y[np.ix_(keep,elim)];Ykk=Y[np.ix_(keep,keep)]
    singular=np.linalg.svd(Yee,compute_uv=False)
    condition=float(singular[0]/singular[-1]);require(np.isfinite(condition) and singular[-1]>0,'Singular eliminated block')
    K=-solve(Yee,Yek,assume_a='gen')
    T=np.zeros((len(bus),148),complex);T[keep]=np.eye(148);T[elim]=K
    reduced=Ykk+Yke@K
    rng=np.random.default_rng(4407);v=(.95+.1*rng.random((148,5)))*np.exp(1j*.1*rng.standard_normal((148,5)))
    full=T@v;Ifull=Y@full
    interior_error=float(np.max(abs(Ifull[elim])))
    retained_error=float(np.max(abs(Ifull[keep]-reduced@v)))
    require(max(interior_error,retained_error)<1e-8,'Linear Schur/Kron identity failed')
    monitor_f=yf@T;monitor_t=yt@T;monitor_s=ys@T
    monitor_error=max(float(np.max(abs(monitor_f@v-yf@full))),float(np.max(abs(monitor_t@v-yt@full))),float(np.max(abs(monitor_s@v-ys@full))))
    require(monitor_error<1e-8,'Recovered current operator failed')
    shunt_rows=elim[np.any(bus[elim,4:6]!=0,axis=1)]
    out=dict(label=label,full_buses=len(bus),retained_buses=148,eliminated_buses=len(elim),
        eliminated_ids=ids[elim].tolist(),eliminated_generator_or_DC_or_PV_or_REF_buses=0,
        eliminated_bus_P_Q_zero=True,fixed_shunt_buses_eliminated=ids[shunt_rows].tolist(),
        eliminated_block_condition_2=condition,eliminated_block_min_singular_value_pu=float(singular[-1]),
        eliminated_components=components,all_eliminated_components_retain_electrical_connection=True,
        maximum_random_phasor_eliminated_current_pu=interior_error,
        maximum_random_phasor_retained_current_error_pu=retained_error,
        maximum_random_phasor_branch_current_operator_error_pu=monitor_error,
        full_Y_complex_transpose_asymmetry=float(np.max(abs(Y-Y.T))),
        reduced_Y_complex_transpose_asymmetry=float(np.max(abs(reduced-reduced.T))),
        active_nonzero_phase_shift_branches=int(np.count_nonzero(on&(abs(np.asarray(m['branch'])[:,9])>1e-12))),
        phase_taps_and_shunts_included_in_complex_Y=True)
    if solution is not None:
        r=solution;V=np.asarray(r['bus'])[:,7]*np.exp(1j*np.deg2rad(np.asarray(r['bus'])[:,8]))
        recovered=T@V[keep]
        original_if=yf@V;original_it=yt@V
        If=monitor_f@V[keep];It=monitor_t@V[keep];Is=monitor_s@V[keep]
        saved_from=np.asarray(r['branch'])[:,13]+1j*np.asarray(r['branch'])[:,14]
        saved_to=np.asarray(r['branch'])[:,15]+1j*np.asarray(r['branch'])[:,16]
        power_error=float(max(np.max(abs(float(m['baseMVA'])*V[f]*np.conj(original_if)-saved_from)),
                              np.max(abs(float(m['baseMVA'])*V[t]*np.conj(original_it)-saved_to))))
        recovered_power_error=float(max(np.max(abs(float(m['baseMVA'])*recovered[f]*np.conj(If)-saved_from)),
                                        np.max(abs(float(m['baseMVA'])*recovered[t]*np.conj(It)-saved_to))))
        amp_f=float(m['baseMVA'])*1000/(np.sqrt(3)*bus[f,9]);amp_t=float(m['baseMVA'])*1000/(np.sqrt(3)*bus[t,9])
        amp_error=float(max(np.max(abs(If-original_if)*amp_f),np.max(abs(It-original_it)*amp_t)))
        verr=float(np.max(abs(recovered-V)))
        out.update(saved_PF_converged=bool(r['success']),maximum_saved_point_voltage_recovery_error_pu=verr,
            maximum_independent_original_branch_power_error_MVA=power_error,
            maximum_recovered_branch_power_error_MVA=recovered_power_error,
            maximum_recovered_terminal_current_error_A=amp_error,
            maximum_saved_point_eliminated_current_pu=float(np.max(abs(Y[elim]@V))),
            exact_recovery_does_not_certify_operating_bound_feasibility=True)
        require(verr<1e-7 and power_error<1e-6 and recovered_power_error<1e-5 and amp_error<1e-4,'Saved-point recovery tolerance')
    return out


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    kept_file=ROOT/'output/nygrid_2025_slim/network/bus_register.csv'
    kept=pd.read_csv(kept_file).model_bus.to_numpy(int)
    fixture=ROOT/'output/nygrid_2025_ac_system/branches/sectioned_design_fixtures.mat'
    d=loadmat(fixture,simplify_cells=True);result=[];paths=[kept_file,fixture]
    for state in ['pre_may','may21','may30','post_dover']:
        result.append(inspect('topology_'+state,d['cases'][state],kept))
    for h in [523,2630,4000,4194,8471,8472,8508]:
        path=SOURCE/f'representative_h{h:04d}.mat';m=loadmat(path,simplify_cells=True);paths.append(path)
        result.append(inspect(f'saved_profile_h{h}',m['m'],kept,m['r']))
    paths.append(Path(__file__))
    report=dict(passed=True,created_utc=datetime.now(timezone.utc).isoformat(),baseline_HEAD=head,
        scope='Independent mathematical feasibility/eligibility and saved-point recovery audit, not a new PF/OPF or compact solver validation',
        requested_retained_interface_buses=148,extra_nodes_required_for_current_fixed_control_model=0,
        retained148_is_user_chosen_interface_not_proved_globally_minimal=True,
        all43_station_nodes_and75_numerical_nodes_eliminable_in_current_passive_model=True,
        dated_Dover_regulated_auxiliary_eliminable_with_fixed_taps=True,
        original_detailed_model_operating_and_cable_classification_limits_preserved_not_repaired=True,
        results=result,
        required_implementation_guards=[
            'Reproduce full MATPOWER converter-generator/PV-control setup; Y equivalence alone does not establish control equivalence.',
            'Retain every specified injection, generator/control, REF/PV or converter endpoint, unless separately modeled by an exact nonlinear reduced formulation.',
            'Include fixed GS/BS and line charging in Y before elimination; fixed shunts do not themselves require retained voltage unknowns.',
            'Use general complex blocks and solves. Phase taps can make Y nonsymmetric; do not substitute transpose/conjugate blocks or force branch-only R/X equivalents.',
            'Reject singular or unanchored eliminated components; do not silently use a pseudoinverse or discard energized islands.',
            'Rebuild or invalidate cache on branch status, R/X/B, tap/phase, shunt or retained-set changes. Temperature-dependent R changes the recovery operator.',
            'Keep original branch identities and recover original voltages plus Yf*T, Yt*T and series currents for line/DLR audits.',
            'Check eliminated-bus voltage bounds and original branch limits using recovered states; compact PF success does not enforce those bounds.',
            'No OPF support or physical-parameter certification follows from this PF reduction audit.'
        ],dependencies=[rec(p) for p in paths])
    path=OUT/'kron_feasibility_review.json';dump=json.dumps(report,indent=2);path.write_text(dump+'\n',encoding='utf-8')
    print(json.dumps(dict(passed=True,matrices_checked=len(result),extra_required_nodes=0,
        eliminated_bus_counts=sorted({r['eliminated_buses'] for r in result}),
        maximum_condition_2=max(r['eliminated_block_condition_2'] for r in result),
        maximum_voltage_recovery_error_pu=max(r.get('maximum_saved_point_voltage_recovery_error_pu',0) for r in result),
        maximum_terminal_current_recovery_error_A=max(r.get('maximum_recovered_terminal_current_error_A',0) for r in result)),indent=2))


if __name__=='__main__':main()
