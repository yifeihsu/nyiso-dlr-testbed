"""Independently audit emitted sectioned AC fixtures against frozen inputs.

No import of the builder. This proves construction and mapping invariants,
not OPF success or historical/installed equipment claims.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import math
import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT=Path(__file__).resolve().parents[3]
BASE=ROOT/'output/nygrid_2025_ac_system'
B=BASE/'branches'
RAW=B/'revision_02_complete_mapping'


def require(ok,msg):
    if not ok:raise AssertionError(msg)


def close(a,b,msg,tol=1e-10):
    aa,bb=np.asarray(a,float),np.asarray(b,float)
    require(aa.shape==bb.shape,msg+' shape')
    if aa.size:
        require(np.allclose(aa,bb,atol=tol,rtol=0,equal_nan=True),msg)


def sha(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def rows(value):
    if isinstance(value,dict):return [value]
    if isinstance(value,list):return value
    return list(np.asarray(value,dtype=object).reshape(-1))


def exact(z,y):
    g=np.sqrt(z*y);s=np.sinh(g)/g
    return np.array([[np.cosh(g),z*s],[y*s,np.cosh(g)]],complex)


def main():
    fixture=B/'sectioned_design_fixtures.mat'
    built=loadmat(fixture,simplify_cells=True)
    plan=pd.read_csv(B/'section_and_reactor_plan.csv').set_index('original_branch_row')
    source_pre=loadmat(ROOT/'output/nygrid_2025_line_parameters/overlays/engineering_nominal/full191_network_cases.mat',simplify_cells=True)
    source_post=loadmat(ROOT/'output/nygrid_2025_dover_parameters/network/x_nominal.mat',simplify_cells=True)
    sources=dict(pre_may=source_pre['refined_2025_pre_may_case'],may21=source_pre['refined_2025_may21_case'],
                 may30=source_pre['refined_2025_may30_case'],post_dover=source_post['full_case'])
    raw=loadmat(RAW/'engineering_overlay.mat',simplify_cells=True)
    assignments=pd.read_csv(RAW/'branch_assignments.csv').set_index('branch_row')
    oh=pd.read_csv(RAW/'thermal_segments.csv');cables=pd.read_csv(RAW/'cable_segments.csv')
    rawkeys=np.asarray(raw['branch_keys']).astype(str)
    original_limits=raw['terminal_current_limit_A'].copy()
    classfile=BASE/'engineering/voltage_changing_classification_review.csv'
    classes=pd.read_csv(classfile).set_index('branch_row')
    composites=classes.loc[classes.revised_evidence_class.eq('unresolved_composite_voltage_changing_equivalent')]
    require(len(composites)==65,'Complete composite evidence classification')
    for row,c in composites.iterrows():
        original_limits[row-1]=[c.recommended_composite_from_A,c.recommended_composite_to_A]
    checkstates=[];max_abcd=0.;max_v_error=0.
    for state,source in sources.items():
        case=built['cases'][state];info=built['runtime'][state]
        sourcebus=source['bus'];sourcebranch=source['branch'].copy()
        nb0=len(sourcebus);nl0=len(sourcebranch)
        sourcebranch[:,2:8]=raw['branch_reference'][:nl0,2:8];sourcebranch[210,10]=0
        for row,c in composites.iterrows():
            if row<=nl0:sourcebranch[row-1,5:8]=c.recommended_composite_nominal_mva_proxy
        bus=case['bus'];branch=case['branch'];keys=np.asarray(info['branch_keys']).astype(str)
        limits=info['terminal_current_limit_A']
        mapping=pd.DataFrame(rows(info['branch_map'])).sort_values('runtime_branch_row')
        require(len(mapping)==len(branch) and np.array_equal(mapping.runtime_branch_row,np.arange(1,len(branch)+1)),state+' complete runtime axis')
        require(len(set(keys))==len(keys) and len(set(bus[:,0]))==len(bus),state+' unique keys and buses')
        close(case['gen'],source['gen'],state+' original generator template')
        close(case['dcline'],source['dcline'],state+' original six transfers')
        columns=[0,1,2,3,4,6,7,8,9,10,11,12]
        close(bus[:nb0,columns],sourcebus[:,columns],state+' original bus identity/load/voltage inputs')
        require((bus[nb0:,2:6]==0).all() and (bus[nb0:,1]==1).all(),state+' new zero-injection PQ nodes')
        expected_bs=np.zeros(nb0);source_lookup={int(b):j for j,b in enumerate(sourcebus[:,0])}
        needed_added=[];active_oh=[];active_cables=[];reactor_total=0.
        for row in range(1,nl0+1):
            p=plan.loc[row];original=sourcebranch[row-1];g=mapping.loc[mapping.original_branch_row==row].sort_values('section_index')
            enabled=original[10]>0;n=int(p.section_count) if enabled else 1
            require(len(g)==n,state+f' active section count row {row}')
            rr=g.runtime_branch_row.to_numpy(int)-1
            close(branch[rr,2:5].sum(axis=0),original[2:5],state+f' physical R/X/B totals row {row}')
            require((branch[rr,10]==original[10]).all(),state+f' section status row {row}')
            require(int(g.iloc[0].from_bus)==int(original[0]) and int(g.iloc[-1].to_bus)==int(original[1]),state+' original corridor endpoints')
            for j in range(n):
                require(keys[rr[j]]==g.iloc[j].runtime_branch_key,state+' runtime key axis')
                require(str(g.iloc[j].original_corridor_key)==rawkeys[row-1],state+' original corridor key binding')
                if j<n-1:
                    require(g.iloc[j].to_bus==g.iloc[j+1].from_bus,state+' connected section path')
                    needed_added.append(int(g.iloc[j].to_bus))
                expected_from=original_limits[row-1,0] if j==0 else np.nan
                expected_to=original_limits[row-1,1] if j==n-1 else np.nan
                close(limits[rr[j]],np.array([expected_from,expected_to]),state+' hardware only at original terminals')
            if n>1:
                require((branch[rr,5:8]==0).all(),state+' no MVA apparatus at artificial nodes')
                close(branch[rr,8:10],np.tile(original[8:10],(n,1)),state+' phase controls unchanged')
            else:
                close(branch[rr[0]],original,state+' unsplit branch unchanged')
            if row in composites.index:
                require(not bool(p.is_OH) and not bool(p.is_cable) and n==1,state+' unresolved composite excluded from line thermal realization')
                close(branch[rr[0],2:5],raw['branch_reference'][row-1,2:5],state+' composite original R/X/B preserved')
            if enabled and bool(p.is_OH):
                active_oh.extend((rr+1).tolist())
                if n>1:require(len(oh.loc[oh.branch_row==row])==1,'No repeated mixing of heterogeneous long sections')
            if enabled and bool(p.is_cable):active_cables.extend((rr+1).tolist())
            expected_selection=(bool(p.is_OH) and p.corridor_length_m>120*1609.344) or (bool(p.is_cable) and original[4]*100>=10)
            require(bool(p.reactor_selected)==expected_selection,state+' predeclared reactor selection')
            if enabled and expected_selection:
                q=.75*100*original[4];reactor_total+=q
                expected_bs[source_lookup[int(original[0])]]-=q/2
                expected_bs[source_lookup[int(original[1])]]-=q/2
            if bool(p.is_OH) or bool(p.is_cable):
                z=complex(original[2],original[3]);y=complex(0,original[4]);target=exact(z,y)
                count=int(p.section_count);zs=z/count;ys=y/count
                block=np.array([[1+zs*ys/2,zs],[ys*(1+zs*ys/4),1+zs*ys/2]],complex)
                cascade=np.linalg.matrix_power(block,count)
                error=float(np.abs((cascade-target)/target).max())
                verr=abs(abs(1/cascade[0,0])-abs(1/target[0,0]))
                max_abcd=max(max_abcd,error);max_v_error=max(max_v_error,verr)
                require(error<.005 and verr<.005,state+' declared line accuracy screen')
        require(set(needed_added)==set(bus[nb0:,0].astype(int)),state+' no orphan/internal extra nodes')
        require(len(needed_added)==len(bus)-nb0,state+' all new nodes uniquely associated with active corridors')
        close(bus[:nb0,5]-sourcebus[:,5],expected_bs,state+' exact negative reactor BS increments',tol=1e-9)
        for name,original_segments,active_rows in [('thermal_segments',oh,active_oh),('cable_segments',cables,active_cables)]:
            emitted=pd.DataFrame(rows(info[name]))
            require(set(emitted.branch_row)==set(active_rows),state+' complete '+name+' runtime coverage')
            for s in emitted.to_dict('records'):
                row=int(s['original_branch_row']);runtime_row=int(s['branch_row']);n=int(s['section_count'])
                source_options=original_segments.loc[original_segments.branch_row==row]
                if name=='thermal_segments':source_options=source_options.loc[source_options.segment_id==s['segment_id']]
                require(len(source_options)==1,state+' source segment identity')
                original_s=source_options.iloc[0]
                close(np.array([s['segment_length_m'],s['reference_r_pu'],s['reference_x_pu'],s['reference_b_pu']]),
                      original_s[['segment_length_m','reference_r_pu','reference_x_pu','reference_b_pu']].to_numpy(float)/n,state+' divided segment dimensions')
                require(s['catalog_id']==original_s.catalog_id and s['circuits']==original_s.circuits and s['bundle_count']==original_s.bundle_count,state+' unchanged conductor or cable geometry')
                require(s['branch_key']==keys[runtime_row-1] and branch[runtime_row-1,10]>0,state+' active segment key binding')
            for runtime_row,g in emitted.groupby('branch_row'):
                close(g[['reference_r_pu','reference_x_pu','reference_b_pu']].sum().to_numpy(float),branch[int(runtime_row)-1,2:5],state+' segment/branch R/X/B composition')
        reactors=pd.DataFrame(rows(info['reactor_ledger']))
        for r in reactors.to_dict('records'):
            row=int(r['original_branch_row']);enabled=sourcebranch[row-1,10]>0
            require(bool(r['associated_line_active'])==enabled,state+' reactor follows original dated line status')
            require(r['from_bus_BS_delta_mvar']<=0 and r['to_bus_BS_delta_mvar']<=0,state+' reactor sign')
            require(not bool(r['asbuilt_equipment_claim']),state+' synthetic compensation claim')
        close(np.array(reactors.applied_total_reactor_mvar_at1pu.sum()),np.array(reactor_total),state+' reactor ledger sum',tol=1e-9)
        checkstates.append(dict(state=state,original_buses=nb0,buses=len(bus),original_branch_records=nl0,branch_records=len(branch),
            added_zero_injection_buses=len(bus)-nb0,OH_runtime_branches=len(active_oh),cable_runtime_sections=len(active_cables),
            total_reactor_mvar_at1pu=reactor_total,all_original_load_generators_transfers_preserved=True,no_orphan_new_buses=True,
            hardware_amperes_only_original_endpoints=True,reactors_follow_corridor_status=True))
    construction=json.loads((B/'sectioned_design_receipt.json').read_text())
    for item in construction['dependencies']+construction['outputs']:
        require(sha(ROOT/item['path'])==item['sha256'],'Construction freshness '+item['path'])
    inputs=[fixture,B/'sectioned_design_plan.mat',B/'section_and_reactor_plan.csv',B/'sectioned_design_receipt.json',
            RAW/'engineering_overlay.mat',RAW/'thermal_segments.csv',RAW/'cable_segments.csv',classfile,Path(__file__)]
    report=dict(passed=True,created_utc=datetime.now(timezone.utc).isoformat(),
        scope='Independent emitted four-state construction, mapping, compensation and distributed-line electrical accuracy review; no OPF or coupled thermal feasibility claim',
        all_original_injections_controls_and_full_system_nodes_preserved=True,no_gamma_current_or_impedance_transform=True,
        maximum_ABCD_relative_error=max_abcd,maximum_open_end_voltage_magnitude_error_pu=max_v_error,
        declared_relative_ABCD_tolerance=.005,declared_voltage_tolerance_pu=.005,states=checkstates,
        composite_voltage_changing_equivalents=65,station_transformer_compatible_equivalents=38,
        composite_limits_checked_against_independent_voltage_class_prior=True,
        total_X_not_used_to_size_composite_terminal_limits=True,
        limitations=['Reactor sizing is a synthetic 75-percent charging rule; cable use is an explicit planning extension.',
            'This verifies Python-generated reference fixtures. MATLAB runtime implementation equivalence requires separate fresh evidence.',
            'Section terminal electrical accuracy does not certify exact continuous local thermal maxima.',
            'Undecomposed line interiors inside 65 voltage-changing composite equivalents have no physical-conductor DLR certification.',
            'Station-transformer-compatible capacity choices and buried-cable thermal ratings remain synthetic and unverified as installed assets.'],
        checked_files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for p in inputs])
    runtime_proof=B/'sectioned_matlab_runtime_validation.json'
    report['MATLAB_runtime_cross_language_confirmed']=False
    if runtime_proof.exists():
        runtime=json.loads(runtime_proof.read_text())
        require(runtime['passed'] and runtime['cross_language_topology_states']==4 and runtime['wrapper_guards']==4,'MATLAB runtime parity completeness')
        for field in ['maximum_bus_matrix_error','maximum_branch_matrix_error','maximum_OH_segment_error','maximum_cable_segment_error']:
            require(runtime[field]<1e-12,'MATLAB runtime parity '+field)
        require(runtime['inactive_split_corridor_row']==185 and runtime['inactive_split_internal_nodes_omitted']==5,'MATLAB inactive-corridor case')
        require(abs(runtime['inactive_split_reactor_mvar_omitted']-607.2794681638039)<1e-9,'MATLAB inactive-reactor case')
        for item in runtime['dependencies']:
            require(sha(Path(item['path']))==item['sha256'],'MATLAB runtime evidence freshness '+item['path'])
        report['MATLAB_runtime_cross_language_confirmed']=True
        report['MATLAB_runtime_status_guards']=4
        report['inactive_split_corridor_nodes_and_reactor_removed_verified']=True
        report['scope']='Independent four-state construction, MATLAB/Python parity, mapping, status-linked compensation and distributed-line electrical accuracy review; no OPF or coupled thermal feasibility claim'
        report['limitations'].remove('This verifies Python-generated reference fixtures. MATLAB runtime implementation equivalence requires separate fresh evidence.')
        for path in [runtime_proof,B/'sectioned_matlab_parity_checks.csv',B/'sectioned_matlab_guard_checks.csv',
                     ROOT/'scripts/nygrid_2025_ac_system/branches/nygrid_ac_apply_sections.m',
                     ROOT/'scripts/nygrid_2025_ac_system/branches/validate_sectioned_runtime.m']:
            report['checked_files'].append(dict(path=path.relative_to(ROOT).as_posix(),sha256=sha(path)))
    target=BASE/'engineering/sectioned_design_independent_review.json'
    target.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='checked_files'},indent=2))


if __name__=='__main__':main()
