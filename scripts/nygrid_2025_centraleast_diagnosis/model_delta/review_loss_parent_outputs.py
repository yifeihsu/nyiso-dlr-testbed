"""Independent audit of loss loading, zero-R and original-parent AC trials."""
from pathlib import Path
from datetime import datetime,timezone
import json
import numpy as np
import pandas as pd
from scipy.io import loadmat
from review_bridge_outputs import ROOT,BASE,IDS,record,mx,flows,check_network


def loaded_terminal_flows(r,parent,original):
    # Artificial loss demand at section interiors makes source-target power
    # differ even in lossless DCPF. Explicitly include that declared demand.
    branch=r['branch'];bus=r['bus'];lookup={int(x):i for i,x in enumerate(bus[:,0])}
    result=np.zeros((7,4));mapping=original['if']['map']
    for j,ident in enumerate(IDS):
        for signed in mapping[mapping[:,0]==ident,1].astype(int):
            p=abs(signed);f,t=original['branch'][p-1,:2].astype(int);chain=np.flatnonzero(parent==p)
            first=chain[branch[chain,0]==f];last=chain[branch[chain,1]==t];assert len(first)==len(last)==1
            F=branch[first[0],13];T=branch[last[0],15];sgn=np.sign(signed)
            result[j,0]+=sgn*F;result[j,1]+=F if sgn>0 else T;result[j,2]+=-T if sgn>0 else -F
            internal=set(branch[chain,:2].astype(int).flatten())-{f,t};ii=[lookup[x] for x in internal]
            assert not np.isin(r['gen'][:,0],list(internal)).any() and not np.isin(r['dcline'][:,:2],list(internal)).any()
            expected=np.sum(branch[chain,13]+branch[chain,15])+np.sum(bus[ii,2]+bus[ii,4])
            assert abs(F+T-expected)<1e-6
            result[j,3]+=F+T
    assert mx(result[:,1]-result[:,2]-result[:,3])<1e-6
    return result


def main():
    folder=BASE/'experiments/loss_and_parent_diagnostics';bp=BASE/'experiments/representative_bridge'
    proof_path=folder/'diagnostic_receipt.json';proof=json.loads(proof_path.read_text());assert proof['completed']
    paths=[Path(__file__),Path(__file__).with_name('review_bridge_outputs.py'),proof_path];rows=[]
    maximum_loss_loading_error=0.;maximum_report_error=0.;r0good=[];r0failed=[]
    oldsrc_path=ROOT/'output/nygrid_2025_line_parameters/overlays/engineering_nominal/full191_network_cases.mat'
    postsrc_path=ROOT/'output/nygrid_2025_dover_parameters/network/x_nominal.mat';paths.extend([oldsrc_path,postsrc_path])
    oldsrc=loadmat(oldsrc_path,simplify_cells=True);postsrc=loadmat(postsrc_path,simplify_cells=True)
    for h in proof['hours']:
        h=int(h);path=folder/f'h{h:04d}.mat';bpath=bp/f'bridge_h{h:04d}.mat';paths.extend([path,bpath])
        d=loadmat(path,simplify_cells=True);b=loadmat(bpath,simplify_cells=True);m=b['detailed'];a=d['a'];gamma=float(b['a']['gamma'])
        parents=np.asarray(m['userdata']['ac_system']['branch_parent_row'],int);loaded=d['loaded'];zero=d['zeroR'];parent=d['parent_AC']
        for name in ['bus','gen','dcline','gencost']:assert np.array_equal(zero[name],m[name])
        keep=np.arange(m['branch'].shape[1])!=2
        assert np.array_equal(zero['branch'][:,keep],m['branch'][:,keep]) and np.all(zero['branch'][:,2]==0)
        losses=b['detailed_ac']['branch'][:,13]+b['detailed_ac']['branch'][:,15]
        assert np.array_equal(losses,d['loss_by_branch']) and losses.min()>-1e-6
        lookup={int(x):i for i,x in enumerate(m['bus'][:,0])};lossPD=np.zeros(len(m['bus']))
        for line,value in zip(m['branch'],losses):lossPD[lookup[int(line[0])]]+=value/2;lossPD[lookup[int(line[1])]]+=value/2
        maximum_loss_loading_error=max(maximum_loss_loading_error,mx(lossPD-d['loss_PD']));assert mx(lossPD-d['loss_PD'])<1e-10
        assert mx(loaded['bus'][:,2]-m['bus'][:,2]-lossPD)<1e-10
        keepbus=np.arange(m['bus'].shape[1])!=2
        assert np.array_equal(loaded['bus'][:,keepbus],m['bus'][:,keepbus])
        for name in ['branch','gen','dcline','gencost']:assert np.array_equal(loaded[name],m[name])
        loss_audit=check_network(loaded,d['result_loss_DCF'],False)
        lossflow=loaded_terminal_flows(d['result_loss_DCF'],parents,b['full']);assert mx(lossflow-d['if_loss_DCF'])<1e-6
        assert abs(loss_audit['slack_increment_MW']-lossPD.sum())<1e-6
        assert np.array_equal(parent['branch'],b['full']['branch']) and np.array_equal(parent['gen'],m['gen']) and np.array_equal(parent['dcline'],m['dcline'])
        keepfull=np.asarray([lookup[int(x)] for x in parent['bus'][:,0]])
        assert np.array_equal(parent['bus'][:,[1,7,8]],m['bus'][keepfull][:,[1,7,8]])
        assert np.array_equal(parent['bus'][:,2:6],b['full']['bus'][:,2:6])
        source=postsrc['full_case'] if h>=8472 else oldsrc[b['prior']['userdata']['slim']['network_state']]
        assert np.array_equal(parent['bus'][:,4:6],source['bus'][:,4:6])
        assert np.array_equal(parent['branch'][:,2:5],source['branch'][:,2:5])
        parent_audit=check_network(parent,d['result_parent_AC'],True)
        parentflow=flows(d['result_parent_AC'],np.arange(1,len(parent['branch'])+1),b['full'])
        assert mx(parentflow-d['if_parent_AC'])<1e-6 and bool(a['parent_AC_equation_profile_qualified'])
        expected={'half_loss_PD_total_model_MW':lossPD.sum(),'loss_loaded_DCF_slack_increment_model_MW':loss_audit['slack_increment_MW'],
            'loss_loaded_DCF_CE_public_MW':lossflow[4,0]/gamma,
            'CE_loss_allocation_delta_public_MW':(lossflow[4,0]-b['detailed_dc_if'][4,0])/gamma,
            'CE_remaining_AC_minus_loss_loaded_DCF_public_MW':(b['detailed_ac_if'][4,0]-lossflow[4,0])/gamma,
            'parent_AC_CE_public_MW':parentflow[4,0]/gamma,'parent_AC_CE_minus_archived_DC_public_MW':(parentflow[4,0]-b['archived_if'][4])/gamma,
            'parent_AC_losses_model_MW':parent_audit['total_real_loss_MW']}
        r0qual=bool(a['R0_AC_equation_profile_qualified']);assert r0qual==bool(d['audit_R0']['equation_and_profile_qualified'])
        if r0qual:
            r0good.append(h);audit=check_network(zero,d['result_R0'],True);value=flows(d['result_R0'],parents,b['full'])
            assert mx(value-d['if_R0'])<1e-6
            expected.update(R0_CE_public_MW=value[4,0]/gamma,
                            R0_CE_delta_from_baseline_AC_public_MW=(value[4,0]-b['detailed_ac_if'][4,0])/gamma,
                            R0_AC_losses_model_MW=audit['total_real_loss_MW'])
        else:
            r0failed.append(h);assert not bool(d['result_R0']['success'])
        for key,value in expected.items():
            err=abs(value-a[key]);maximum_report_error=max(maximum_report_error,err);assert err<1e-6
        rows.append(dict(hour_index=h,original_eight_hour_cohort=bool(b['a']['original_eight_hour_cohort']),
            R0_qualified=r0qual,R0_failed_iterate_excluded_from_valid_comparisons=not r0qual,
            loss_DCF_and_original_parent_AC_independent_checks_passed=True,**expected))
    assert len(rows)==proof['loss_loaded_DCF_qualified']==proof['parent_AC_qualified']==11
    assert len(r0good)==proof['R0_qualified']==5 and len(r0failed)==6
    table=pd.DataFrame(rows);out=BASE/'model_delta/loss_parent_independent_checks.csv';table.to_csv(out,index=False)
    primary=table[table.original_eight_hour_cohort]
    paths.extend(ROOT/'scripts/nygrid_2025_centraleast_diagnosis/experiments'/n for n in ['run_loss_and_parent_diagnostics.m','audit_bridge_AC_solution.m','audit_diagnostic_DCPF.m','physical_interface_flows.m'])
    report=dict(passed=True,created_utc=datetime.now(timezone.utc).isoformat(),
        scope='Independent saved-array audit of eleven representative loss-loading and coherent-parent AC diagnostics',
        loss_loaded_DC_checked=11,coherent_original_parent_AC_checked=11,R0_qualified_hours=r0good,R0_unqualified_failed_hours=r0failed,
        failed_R0_points_excluded_from_valid_recomputed_values=True,
        original_R_X_B_GS_BS_and_same_generator_converter_controls_verified_for_parent_AC=True,
        half_end_loss_demand_exactly_reconstructed=True,loss_loaded_DC_preserves_R_X_B_shunts_gen_and_transfer_inputs=True,
        source_target_difference_in_loaded_DC_includes_artificial_section_interior_demand=True,
        maximum_nodal_loss_loading_reconstruction_error_MW=maximum_loss_loading_error,
        maximum_report_value_reconstruction_error=maximum_report_error,
        primary_eight_hour_mean_loss_allocation_shift_public_MW=float(primary.CE_loss_allocation_delta_public_MW.mean()),
        primary_eight_hour_mean_remaining_AC_minus_loss_loaded_DC_public_MW=float(primary.CE_remaining_AC_minus_loss_loaded_DCF_public_MW.mean()),
        primary_eight_hour_mean_original_parent_AC_minus_archived_DC_public_MW=float(primary.parent_AC_CE_minus_archived_DC_public_MW.mean()),
        limitations=['Half of each baseline AC line loss is assigned to each terminal as an explicitly chosen DC load perturbation; it is a diagnostic decomposition rather than unique causal attribution.',
            'ZeroingR changes voltage and angle behavior as well as real losses, and6of11 zeroR cases failedNR; their raw saved iterates are not valid predictions.',
            'The coherent original-parent AC cases use original electrical parameters and the same controlled-VG assumptions, but numerical convergence does not establish physical asset or operating feasibility.',
            'Representative eleven-hour results must not be generalized to annual metrics.'],
        dependencies=[record(p) for p in dict.fromkeys(paths)],outputs=[record(out)])
    (BASE/'model_delta/loss_parent_independent_review.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ['dependencies','outputs']},indent=2))


if __name__=='__main__':main()
