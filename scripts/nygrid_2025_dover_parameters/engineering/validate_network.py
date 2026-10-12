"""Independent Dover branch placement and two-input affine DC reduction audit.

Uses the independent full-matrix Schur implementation, never the builder's
component reducer. All phase probes are algebraic checks, not operating cases.
No network power-flow or interface-observation fitting is performed here.
"""
from pathlib import Path
import copy
import importlib.util
import json

import numpy as np
import pandas as pd
from scipy.io import loadmat

import pst_model as pst

ROOT=pst.ROOT
OUT=ROOT/'output/nygrid_2025_dover_parameters'
PARENT=ROOT/'output/nygrid_2025_line_parameters/overlays/engineering_nominal'


def require(value,message):
    if not value:raise ValueError(message)


def difference(a,b):
    a,b=np.asarray(a),np.asarray(b)
    require(a.shape==b.shape,'Independent comparison axes differ')
    require(np.isfinite(a).all() and np.isfinite(b).all(),'Nonfinite independent comparison')
    return float(np.max(np.abs(a-b),initial=0))


def audit():
    helper_path=ROOT/'scripts/nygrid_2025_slim/validate_slim.py'
    spec=importlib.util.spec_from_file_location('independent_Dover_schur',helper_path)
    independent=importlib.util.module_from_spec(spec);spec.loader.exec_module(independent)
    reference=loadmat(PARENT/'full191_network_cases.mat',simplify_cells=True)['refined_2025_case']
    old_slim=loadmat(PARENT/'network_cases.mat',simplify_cells=True)
    keep=np.asarray(old_slim['kept_bus_ids'],int)
    cases=json.loads((OUT/'network/network_receipt.json').read_text())
    parameters=json.loads((OUT/'engineering/PAR_estimates.json').read_text())
    require(cases['passed'] and cases['internal_interface_observations_read'] is False,'Construction scope changed')
    for item in cases['dependencies']:
        require(pst.sha(ROOT/item['path'])==item['sha256'],'Changed source dependency '+item['path'])
    lines_path=ROOT/'output/nygrid_2025_line_parameters/estimates/Dover_line_only_estimates_not_applied.csv'
    lines=pd.read_csv(lines_path,float_precision='round_trip')
    lines=lines.loc[(lines.temperature_c==95)&(lines.adjacent_phase_spacing_ft==25.6)].set_index('section')
    direct_register=pd.read_csv(ROOT/'output/nygrid_2025_downstate/network/branch_register.csv',keep_default_na=False)
    historical=np.flatnonzero(direct_register.source_branch_row.to_numpy(int)>0)
    require(len(historical)==97,'Historical source circuit count changed')
    results=[];files=[]
    for item in cases['scenarios']:
        name=item['scenario'];path=ROOT/item['path']
        require(pst.sha(path)==item['sha256'],'Changed network artifact '+name)
        files.append(path)
        payload=loadmat(path,simplify_cells=True);full=payload['full_case'];slim=payload['slim_case'];rec=payload['recovery']
        family=parameters['families'][name]
        require(full['bus'].shape==(192,13) and full['branch'].shape==(413,13),'Full Dover device shape differs')
        require(slim['bus'].shape==(148,13) and slim['branch'].shape==(274,13),'Slim representation expanded unexpectedly')
        require(np.array_equal(payload['kept_bus_ids'],keep) and np.array_equal(keep[:140],np.arange(1,141)),'Original bus identities changed')
        require(difference(full['bus'][:191],reference['bus'])==0 and int(full['bus'][-1,0])==21001
                and np.all(full['bus'][-1,2:6]==0),'Regulated zero-injection port altered the original system')
        for key in ['gen','dcline']:
            require(difference(full[key],reference[key])==0 and difference(slim[key],reference[key])==0,'Generator/DC template altered')
        immutable=np.setdiff1d(np.arange(410),[392,393])
        require(difference(full['branch'][immutable],reference['branch'][immutable])==0,'Unrelated branch altered')
        require(difference(full['branch'][historical],reference['branch'][historical])==0,'Exact historical circuit altered')
        old398=reference['branch'][393].copy();old398[10]=0
        require(difference(full['branch'][393],old398)==0,'Old398 branch was not retired once as provenance')
        expected_pairs=np.array([[20001,20003],[20003,21001],[20003,21001],[21001,20002]])
        require(np.array_equal(full['branch'][[392,410,411,412],:2],expected_pairs),'Banks not parallel between correct line ports')
        for row,section in [(392,'Y17_NY_line_only'),(412,'Dover_LongMountain_composite_line_only')]:
            require(difference(full['branch'][row,2:5],lines.loc[section,['r_pu','x_pu','b_pu']].to_numpy(float))==0,
                    'Applied mixed-section line parameters differ from declared source estimate')
            require(np.all(full['branch'][row,5:8]==0),'Unverified full-path line rating invented')
        for row in [410,411]:
            branch=full['branch'][row]
            require(branch[2]==0 and branch[3]==family['bank_x_pu100'] and branch[5]==750 and branch[4]==0
                    and branch[8]==1 and branch[9]==0 and branch[10]==1,'Bank parameter family/rating/scope changed')
        meta=payload['metadata']
        require(np.array_equal(meta['physical_bank_ptids'],[625149,625150]) and not meta['spare_in_service']
                and not meta['physical_taps_observed'] and not meta['physical_winding_resistance_known'], 'Bank identity or evidence qualification changed')
        require(meta['valid_from_utc']=='2025-12-20T04:00:00Z' and meta['before_full_cutover_reuse_parent191_and148_models'],
                'Full-service applicability changed')
        proof=independent.eliminated_response(full,keep)
        net=proof['network'];small=independent.matrices(slim)
        require(len(proof['internal'])==44,'Wrong eliminated bus count')
        independent.zero_interior_injection_contract(full,keep)
        b_error=difference(proof['B'],small['B']);p_error=difference(proof['nodal_phase'],small['nodal_phase'])
        require(max(b_error,p_error)<1e-8,'Independent Schur matrix/phase mismatch')
        for key,expected in [('angle_lift',proof['angle_lift']),('angle_offset',proof['angle_offset']),
                             ('branch_angle_matrix',proof['source_flow_angle_map']),('branch_flow_offset',proof['source_flow_offset'])]:
            require(difference(rec[key],expected)<1e-8,'Base recovery map differs: '+key)
        # Exact analytic derivative per bank phase in RADIANS.
        direct_phase=np.zeros((413,2));direct_phase[[410,411],[0,1]]=-net['b'][[410,411]]
        nodal_source=net['C'].T@direct_phase
        ri,ni=proof['retained'],proof['internal']
        angle_basis=np.zeros((192,2))
        angle_basis[ni]=-np.linalg.solve(net['B'][np.ix_(ni,ni)],nodal_source[ni])
        branch_basis=net['b'][:,None]*(net['C']@angle_basis)+direct_phase
        reduced_source=nodal_source[ri]+net['B'][np.ix_(ri,ni)]@angle_basis[ni]
        source_operator=independent.source_interface_matrix(full)
        errors=[difference(rec['angle_phase_basis'],angle_basis),difference(rec['branch_flow_phase_basis'],branch_basis),
                difference(rec['reduced_phase_bus_basis'],reduced_source),
                difference(rec['interface_phase_basis'],source_operator@branch_basis)]
        slim_phase_source=small['C'].T@(-small['b'][:,None]*rec['slim_shift_phase_basis'])
        errors.append(difference(slim_phase_source,reduced_source))
        require(max(errors)<1e-8,'Two-bank phase-affine derivative differs')
        require(rec['phase_units']=='radians;MATPOWER_SHIFT_sign' and np.array_equal(rec['input_bank_rows_1based'],[411,412]),
                'Phase basis units or bank order differs')
        require(difference(rec['full_interface_branch_matrix'],source_operator)==0,'Seven source functionals changed')
        theta=np.sin(np.arange(148))/100
        probe_errors=[]
        for psi_degree in [[0.,0.],[.3,-.2],[7.,-3.]]:
            psi=np.deg2rad(psi_degree)
            full_angles=proof['angle_lift']@theta+proof['angle_offset']+angle_basis@psi
            flow=net['b']*(net['C']@full_angles)+net['branch_phase']+direct_phase@psi
            saved_flow=rec['branch_angle_matrix']@theta+rec['branch_flow_offset']+rec['branch_flow_phase_basis']@psi
            saved_interfaces=rec['interface_angle_matrix']@theta+rec['interface_flow_offset']+rec['interface_phase_basis']@psi
            probe_errors.extend([difference(flow,saved_flow),difference(source_operator@flow,saved_interfaces)])
        require(max(probe_errors)<1e-7,'Unequal phase recovery probe failed')
        # Differential phase creates bank circulation but no retained nodal source.
        require(difference(reduced_source[:,0],reduced_source[:,1])<1e-8,'Equal parallel banks have inconsistent nodal phase impact')
        circulation=branch_basis@np.array([.01,-.01])
        require(abs(circulation[410]+circulation[411])<1e-9 and abs(circulation[410])>1,
                'Independent bank circulation was lost by reduction')
        # The runtime substitutes original branch211 with two fixed transfer
        # containers. It is removed for the controller's response matrix.
        runtime=copy.deepcopy(slim);runtime['branch'][210,10]=0
        control=independent.matrices(runtime)
        ref=int(np.flatnonzero(keep==50)[0]);nonref=np.delete(np.arange(148),ref)
        response=np.zeros((148,2))
        response[nonref]=-np.linalg.solve(control['B'][np.ix_(nonref,nonref)],reduced_source[nonref])
        jacobian=proof['source_flow_angle_map'][[410,411]]@response+branch_basis[[410,411]]
        require(np.linalg.matrix_rank(jacobian)==2,'Two bank-flow targets are not independently controllable')
        result=dict(scenario=name,passed=True,original_buses_retained=140,slim_buses=148,full_buses=192,eliminated_added_buses=44,
            historical_circuits_unchanged=97,parallel_banks=2,model_bank_X_pu100=family['bank_x_pu100'],
            parallel_pair_X_pu100=family['bank_x_pu100']/2,maximum_Schur_B_error=b_error,maximum_Schur_phase_error=p_error,
            maximum_analytic_phase_basis_error=max(errors),maximum_unequal_phase_recovery_error=max(probe_errors),
            controller_response_rank=2,controller_response_condition=float(np.linalg.cond(jacobian)),
            differential_bank_circulation_preserved=True,original_six_transfer_substitution_respected_in_control_derivative=True)
        results.append(result)
    files += [OUT/'network/network_receipt.json',OUT/'network/Dover_applied_branch_register.csv',
              OUT/'engineering/PAR_estimates.json',PARENT/'full191_network_cases.mat',PARENT/'network_cases.mat',lines_path,
              helper_path,Path(__file__)]
    report=dict(passed=True,scenarios=len(results),network_PF_run=False,
        source_observations_used_for_impedance_or_phase_math=False,physical_factory_impedance_or_measured_taps_claimed=False,
        results=results,files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=pst.sha(p)) for p in files])
    output=OUT/'validation';output.mkdir(parents=True,exist_ok=True)
    (output/'independent_network_validation.json').write_text(json.dumps(report,indent=2)+'\n')
    pd.DataFrame(results).to_csv(output/'independent_network_checks.csv',index=False,lineterminator='\n')
    print(json.dumps({key:value for key,value in report.items() if key!='files'},indent=2))
    return report


if __name__=='__main__':audit()
