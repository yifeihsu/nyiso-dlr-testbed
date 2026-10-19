"""Independent saved-array audit of the representative DC-to-AC bridge."""
from pathlib import Path
from datetime import datetime,timezone
import json,hashlib
import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT=Path(__file__).resolve().parents[3]
BASE=ROOT/'output/nygrid_2025_centraleast_diagnosis'
IDS=[1,2,3,4,5,8,10]


def record(p):
    with p.open('rb') as f:h=hashlib.file_digest(f,'sha256').hexdigest()
    return dict(path=p.relative_to(ROOT).as_posix(),sha256=h)


def mx(a):return float(np.max(abs(a),initial=0))


def flows(r,parent,original):
    branch=np.asarray(r['branch']);mapping=np.asarray(original['if']['map']);result=np.zeros((7,4))
    for j,ident in enumerate(IDS):
        selected=mapping[mapping[:,0]==ident,1].astype(int);assert len(selected)
        for s in selected:
            p=abs(s);sign=np.sign(s);a,b=original['branch'][p-1,:2].astype(int)
            chain=np.flatnonzero(parent==p);first=chain[branch[chain,0]==a];last=chain[branch[chain,1]==b]
            assert len(first)==len(last)==1 and np.all(branch[chain,10]>0)
            F=branch[first[0],13];T=branch[last[0],15]
            result[j,0]+=sign*F;result[j,1]+=F if sign>0 else T;result[j,2]+=-T if sign>0 else -F
            result[j,3]+=np.sum(branch[chain,13]+branch[chain,15])
    assert mx(result[:,1]-result[:,2]-result[:,3])<1e-6
    return result


def check_network(m,r,ac):
    bus=np.asarray(m['bus']);branch=np.asarray(m['branch']);rb=np.asarray(r['bus']);br=np.asarray(r['branch'])
    gen=np.asarray(r['gen']);dc=np.asarray(r['dcline']);base=float(m['baseMVA']);lookup={int(x):i for i,x in enumerate(bus[:,0])}
    f=np.asarray([lookup[int(x)] for x in branch[:,0]]);t=np.asarray([lookup[int(x)] for x in branch[:,1]])
    assert np.array_equal(rb[:,0],bus[:,0]) and np.array_equal(branch[:,:13],br[:,:13])
    assert np.array_equal(rb[:,2:4],bus[:,2:4]) and bool(r['success'])
    ref=int(bus[bus[:,1]==3,0][0]);slack=np.flatnonzero((m['gen'][:,0]==ref)&(m['gen'][:,7]>0))[0]
    others=np.arange(len(gen))!=slack;dp=gen[:,1]-m['gen'][:,1]
    assert mx(dp[others])<1e-7 and mx(dc[:,3:5]-m['dcline'][:,3:5])<1e-7
    angle=np.deg2rad(rb[:,8]);tap=np.where(branch[:,8]==0,1.,branch[:,8]);on=branch[:,10]>0
    net=np.zeros(len(bus),complex)
    for g in gen:
        if g[7]>0:net[lookup[int(g[0])]]+=g[1]+(1j*g[2] if ac else 0j)
    for d in dc:
        if d[2]>0:
            net[lookup[int(d[0])]]+=-d[3]+(1j*d[5] if ac else 0j)
            net[lookup[int(d[1])]]+=d[4]+(1j*d[6] if ac else 0j)
    net-=bus[:,2]+(1j*bus[:,3] if ac else 0j)
    if ac:
        V=rb[:,7]*np.exp(1j*angle);tau=tap*np.exp(1j*np.deg2rad(branch[:,9]))
        y=np.zeros(len(branch),complex);y[on]=1/(branch[on,2]+1j*branch[on,3]);bc=np.where(on,1j*branch[:,4]/2,0j)
        Is=y*(V[f]/tau-V[t]);If=Is/np.conj(tau)+bc*V[f]/abs(tau)**2;It=-Is+bc*V[t]
        F=base*V[f]*np.conj(If);T=base*V[t]*np.conj(It)
        error=max(mx(F-(br[:,13]+1j*br[:,14])),mx(T-(br[:,15]+1j*br[:,16])))
        loss_error=mx((F+T).real-base*branch[:,2]*abs(Is)**2)
        net-=abs(V)**2*(bus[:,4]-1j*bus[:,5])
    else:
        F=np.zeros(len(branch));F[on]=base*(angle[f[on]]-angle[t[on]]-np.deg2rad(branch[on,9]))/(branch[on,3]*tap[on]);T=-F
        error=max(mx(F-br[:,13]),mx(T-br[:,15]));loss_error=mx(br[:,13]+br[:,15]);net-=bus[:,4]
    for j in range(len(branch)):net[f[j]]-=F[j];net[t[j]]-=T[j]
    assert error<1e-6 and loss_error<1e-6 and mx(net)<1e-5
    return dict(branch_law_error_MVA=error,nodal_balance_error_MVA=mx(net),loss_identity_error_MW=loss_error,
                total_real_loss_MW=float(np.sum((F+T).real)),slack_increment_MW=float(dp[slack]),non_slack_P_change_MW=mx(dp[others]))


def main():
    folder=BASE/'experiments/representative_bridge';proof_path=folder/'bridge_receipt.json';proof=json.loads(proof_path.read_text())
    assert proof['completed'] and proof['passed'];paths=[Path(__file__),proof_path]
    original_npz=ROOT/'output/nygrid_2025_dover_parameters/replay/bounded_x_nominal.npz';paths.append(original_npz)
    with np.load(original_npz,allow_pickle=False) as d:
        gamma=float(d['gamma']);archive=d['interface_pf'].copy();angles=d['bus_va'].copy()
    rows=[];maximum_archived=0.;maximum_identity=0.;maximum_report=0.
    for h in proof['hours']:
        h=int(h);path=folder/f'bridge_h{h:04d}.mat';paths.append(path);d=loadmat(path,simplify_cells=True)
        p,full,m=d['prior'],d['full'],d['detailed'];assert gamma==float(d['a']['gamma'])
        assert np.array_equal(p['gen'][:,[0,1,7,8,9]],m['gen'][:,[0,1,7,8,9]])
        assert np.array_equal(p['gen'],full['gen']) and np.array_equal(p['dcline'],full['dcline']) and np.array_equal(p['dcline'],m['dcline'])
        parent=np.asarray(m['userdata']['ac_system']['branch_parent_row'],int)
        slim=check_network(p,d['slim_dc'],False);f=check_network(full,d['full_dc'],False)
        dc=check_network(m,d['detailed_dc'],False);ac=check_network(m,d['detailed_ac'],True)
        fullflow=flows(d['full_dc'],np.arange(1,len(full['branch'])+1),full)
        dcflow=flows(d['detailed_dc'],parent,full);acflow=flows(d['detailed_ac'],parent,full)
        mismatch=mx(fullflow[:,0]-archive[h-1]);maximum_archived=max(maximum_archived,mismatch);assert mismatch<1e-7
        assert mx(d['slim_dc']['bus'][:,8]-angles[h-1])<1e-7
        for name,value in [('full_if',fullflow),('detailed_dc_if',dcflow),('detailed_ac_if',acflow)]:assert mx(value-d[name])<1e-6
        expected={'CE_archived_DC_public_MW':archive[h-1,4]/gamma,'CE_restored_parent_DC_public_MW':fullflow[4,0]/gamma,
                  'CE_detailed_DC_public_MW':dcflow[4,0]/gamma,'CE_detailed_AC_public_MW':acflow[4,0]/gamma,
                  'CE_construction_delta_public_MW':(dcflow[4,0]-archive[h-1,4])/gamma,
                  'CE_same_network_AC_minus_DC_public_MW':(acflow[4,0]-dcflow[4,0])/gamma,
                  'CE_total_AC_minus_archived_DC_public_MW':(acflow[4,0]-archive[h-1,4])/gamma,
                  'detailed_AC_losses_model_MW':ac['total_real_loss_MW'],'detailed_AC_slack_increment_model_MW':ac['slack_increment_MW']}
        for key,value in expected.items():maximum_report=max(maximum_report,abs(value-d['a'][key]));assert abs(value-d['a'][key])<1e-6
        identity=expected['CE_construction_delta_public_MW']+expected['CE_same_network_AC_minus_DC_public_MW']-expected['CE_total_AC_minus_archived_DC_public_MW']
        maximum_identity=max(maximum_identity,abs(identity));assert abs(identity)<1e-8
        rows.append(dict(hour_index=h,original_eight_hour_cohort=bool(d['a']['original_eight_hour_cohort']),
                         additional_posthoc_diagnostic_extreme=bool(d['a']['posthoc_diagnostic_extreme']),
                         independently_audited_AC_KCL_MVA=ac['nodal_balance_error_MVA'],
                         independent_AC_branch_law_error_MVA=ac['branch_law_error_MVA'],
                         all_stage_flow_and_input_audits_passed=True,**expected))
    output=BASE/'model_delta/representative_bridge_independent_checks.csv';pd.DataFrame(rows).to_csv(output,index=False)
    src=ROOT/'scripts/nygrid_2025_centraleast_diagnosis/experiments'
    paths.extend(src/n for n in ['restore_full_DC_parent.m','physical_interface_flows.m','audit_diagnostic_DCPF.m','run_representative_bridge.m'])
    report=dict(passed=True,created_utc=datetime.now(timezone.utc).isoformat(),
        scope='Independent saved-array audit of the corrected representative five-stage bridge, no new solve',
        primary_hours=list(map(int,proof['primary_hours'])),additional_posthoc_diagnostic_hours=list(map(int,proof['additional_diagnostic_extremes'])),
        hour_count=len(rows),all_seven_authoritative_interface_IDs_checked=IDS,
        original_load_PQ_generator_locations_P_profiles_and_six_transfers_verified=True,
        all_DC_branch_laws_KCL_lossless_terminal_identities_checked=True,AC_branch_laws_KCL_and_series_loss_identity_checked=True,
        maximum_full_parent_vs_archived_interface_error_model_MW=maximum_archived,
        maximum_additive_bridge_identity_error_public_MW=maximum_identity,
        maximum_reported_value_recomputation_error=maximum_report,
        all_qualified_operating_outputs_remain_diagnostic=True,
        explicit_limitations=['The same-network AC-minus-DC term combines voltage-angle nonlinearity, resistance/losses, Q/voltage support and slack balancing; it is not a pure loss contribution.',
            'These11 selected hours do not establish annual WAPE effects.',
            'The three additional extreme hours were selected after examining diagnostics and remain separate from the original eight-hour cohort.',
            'The first failed helper revision omitted interface IDs8/10; current corrected seven-ID artifacts passed this fresh independent review.'],
        dependencies=[record(p) for p in paths],outputs=[record(output)])
    (BASE/'model_delta/bridge_independent_review.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ['dependencies','outputs']},indent=2))


if __name__=='__main__':main()
