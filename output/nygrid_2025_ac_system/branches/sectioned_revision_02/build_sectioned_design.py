"""Compile a separate cascaded-pi and fixed-reactor synthetic AC design.

The frozen raw branch engineering stage is not edited. Splitting and reactor
selection use only conductor lengths, electrical charging and a declared
accuracy/design rule; operating dispatch and OPF residuals are never inputs.
"""
from pathlib import Path
from datetime import datetime,timezone
import copy,hashlib,json,math
import numpy as np
import pandas as pd
from scipy.io import loadmat,savemat

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'output/nygrid_2025_ac_system/branches'
RAW=OUT/'revision_02_complete_mapping'
ENGINEERING=ROOT/'output/nygrid_2025_ac_system/engineering'
SOURCE_PRE=ROOT/'output/nygrid_2025_line_parameters/overlays/engineering_nominal/full191_network_cases.mat'
SOURCE_POST=ROOT/'output/nygrid_2025_dover_parameters/network/x_nominal.mat'
OH_MAX_SECTION_M=100000.
LONG_OH_M=120*1609.344
ABCD_TOL=.005
REACTOR_FRACTION=.75


def require(ok,message):
    if not ok:raise ValueError(message)


def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def record(path):
    p=Path(path);return dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p))


def clean(value):
    if isinstance(value,dict):return {str(k):clean(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [clean(v) for v in value]
    if isinstance(value,np.generic):return clean(value.item())
    if isinstance(value,float) and not math.isfinite(value):return None
    return value


def dump(path,data):
    Path(path).write_text(json.dumps(clean(data),indent=2,allow_nan=False)+'\n',encoding='utf-8')


def abcd_error(r,x,b,n):
    z=complex(r,x);y=complex(0,b)
    if abs(y)<1e-15:return 0.,0.
    gamma=np.sqrt(z*y);zc=np.sqrt(z/y)
    exact=np.array([[np.cosh(gamma),zc*np.sinh(gamma)], [np.sinh(gamma)/zc,np.cosh(gamma)]])
    zs=z/n;ys=y/n
    one=np.array([[1+zs*ys/2,zs],[ys*(1+zs*ys/4),1+zs*ys/2]])
    approximate=np.linalg.matrix_power(one,n)
    relative=float(np.max(abs(approximate-exact)/np.maximum(abs(exact),1e-9)))
    voltage=abs(abs(1/approximate[0,0])-abs(1/exact[0,0]))
    return relative,float(voltage)


def build_plan(assignments,oh,cables):
    rows=[]
    for a in assignments.to_dict('records'):
        i=int(a['branch_row']);thermal=bool(a['thermal_overhead_eligible'])
        is_cable=i in set(cables.branch_row)
        length=float(oh.loc[oh.branch_row==i,'segment_length_m'].sum()) if thermal else float(cables.loc[cables.branch_row==i,'segment_length_m'].sum()) if is_cable else 0.
        n=max(1,int(math.ceil(length/OH_MAX_SECTION_M))) if thermal else 1
        original_error,_=abcd_error(a['applied_r_pu'],a['applied_x_pu'],a['applied_b_pu'],1)
        if is_cable:
            while abcd_error(a['applied_r_pu'],a['applied_x_pu'],a['applied_b_pu'],n)[0]>ABCD_TOL:
                n+=1;require(n<=20,'Cable segmentation did not meet declared accuracy criterion')
        nominal_charge=100*float(a['applied_b_pu'])
        selected=bool((thermal and length>LONG_OH_M) or (is_cable and nominal_charge>=10))
        policy='long_OH75pct_generic_source_supported_synthetic_design' if thermal and selected else 'cable75pct_declared_extension_not_installed_equipment_claim' if is_cable and selected else 'none'
        final_error,voltage_error=abcd_error(a['applied_r_pu'],a['applied_x_pu'],a['applied_b_pu'],n)
        if thermal or is_cable:require(final_error<=ABCD_TOL+1e-12 and voltage_error<=.005,'Planned line segmentation fails accuracy screen')
        rows.append(dict(original_branch_row=i,original_branch_key=a['branch_key'],classification=a['classification'],
            from_bus=int(a['from_bus']),to_bus=int(a['to_bus']),base_kv=float(a['base_kv']),
            active_in_any_selected2025_state=bool(a['active_in_any_selected2025_state']),
            is_OH=thermal,is_cable=is_cable,corridor_length_m=length,section_count=n,
            internal_bus_ids=';'.join(str(60000+i*100+j) for j in range(1,n)),
            raw_r_pu=float(a['applied_r_pu']),raw_x_pu=float(a['applied_x_pu']),raw_b_pu=float(a['applied_b_pu']),
            nominal_charging_mvar=nominal_charge,reactor_selected=selected,
            reactor_fraction=REACTOR_FRACTION if selected else 0.,reactor_total_nominal_mvar=REACTOR_FRACTION*nominal_charge if selected else 0.,
            reactor_policy=policy,original_ABCD_relative_error=original_error,
            sectioned_ABCD_relative_error=final_error,sectioned_no_load_voltage_error_pu=voltage_error))
    return pd.DataFrame(rows)


def compile_case(case,keys,plan,raw_limits,oh,cables):
    result=copy.deepcopy(case)
    source_bus=np.asarray(case['bus'],float).copy();source_branch=np.asarray(case['branch'],float).copy()
    n0=len(source_branch);nb0=len(source_bus)
    bus=[x.copy() for x in source_bus];branch=[x.copy() for x in source_branch]
    names=list(np.asarray(case['bus_name'],dtype=object).reshape(-1));runtime_keys=list(keys[:n0])
    lookup={int(x[0]):i for i,x in enumerate(source_bus)}
    limits=[x.copy() for x in raw_limits[:n0]]
    static_cable_limits=[np.array([np.nan,np.nan]) for _ in range(n0)]
    branch_map=[];newbus_map=[];thermal=[];runtime_cables=[];reactors=[]
    for i in range(n0):
        p=plan.iloc[i];z=source_branch[i];active=bool(z[10]);count=int(p.section_count) if active else 1
        f=int(z[0]);t=int(z[1]);section_rows=[i+1]
        if count>1:
            if bool(p.is_OH):require(int((oh.branch_row==i+1).sum())==1,'Long heterogeneous OH needs explicit ordered section construction')
            require(z[8] in [0,1] and z[9]==0,'Only zero-phase line circuits may be sectioned')
            require(source_bus[lookup[f],9]==source_bus[lookup[t],9],'Sectioned circuit changes voltage base')
            interior=[60000+(i+1)*100+k for k in range(1,count)]
            require(not set(interior)&set(lookup),'Internal-bus ID collision')
            for k,bid in enumerate(interior,1):
                a=source_bus[lookup[f]];b=source_bus[lookup[t]];u=k/count
                v=np.zeros(13);v[0]=bid;v[1]=1;v[6]=a[6]
                v[7]=(1-u)*a[7]+u*b[7];v[8]=(1-u)*a[8]+u*b[8];v[9]=a[9];v[10]=a[10]
                v[11]=min(a[11],b[11]);v[12]=max(a[12],b[12])
                require(v[11]>v[12]>0,'Invalid internal-bus voltage range')
                bus.append(v);names.append(f'SYNTHETIC LINE {i+1} INTERNAL {k}');lookup[bid]=len(bus)-1
                newbus_map.append(dict(bus_id=bid,original_branch_row=i+1,original_branch_key=str(p.original_branch_key),
                    stationing_fraction=u,computational_line_section_bus=True,physical_station_claim=False,
                    added_PD_MW=0.,added_QD_Mvar=0.,added_GS_MW=0.,added_BS_Mvar=0.))
            nodes=[f]+interior+[t]
            limits[i][1]=np.nan
            for k in range(count):
                part=z.copy();part[:2]=nodes[k:k+2];part[2:5]/=count
                # No physical apparatus is introduced at artificial taps.
                part[5:8]=0.
                key=f'{p.original_branch_key}:SECTION:{k+1}_OF_{count}'
                if k==0:branch[i]=part;runtime_keys[i]=key
                else:
                    branch.append(part);runtime_keys.append(key);section_rows.append(len(branch))
                    limits.append(np.array([np.nan,raw_limits[i,1] if k==count-1 else np.nan]))
                    static_cable_limits.append(np.array([np.nan,np.nan]))
        for k,br_row in enumerate(section_rows,1):
            current=branch[br_row-1]
            branch_map.append(dict(runtime_branch_row=br_row,runtime_branch_key=runtime_keys[br_row-1],
                original_branch_row=i+1,original_corridor_key=str(p.original_branch_key),section_index=k,section_count=count,
                from_bus=int(current[0]),to_bus=int(current[1]),active=active,classification=str(p.classification),
                section_length_fraction=1/count,physical_terminal_from=bool(k==1),physical_terminal_to=bool(k==count)))
            if active:
                if bool(p.is_cable):static_cable_limits[br_row-1]=raw_limits[i].copy()
                for frame,container in [(oh,thermal),(cables,runtime_cables)]:
                    for s in frame.loc[frame.branch_row==i+1].to_dict('records'):
                        s['original_branch_row']=i+1;s['original_corridor_key']=str(p.original_branch_key)
                        s['branch_row']=br_row;s['branch_key']=runtime_keys[br_row-1]
                        s['section_index']=k;s['section_count']=count;s['corridor_segment_length_m']=s['segment_length_m']
                        s['segment_length_m']/=count
                        for field in ['reference_r_pu','reference_x_pu','reference_b_pu']:s[field]/=count
                        container.append(s)
        q=float(p.reactor_total_nominal_mvar) if active else 0.
        if bool(p.reactor_selected):
            if active:
                bus[lookup[f]][5]-=q/2;bus[lookup[t]][5]-=q/2
            reactors.append(dict(original_branch_row=i+1,original_corridor_key=str(p.original_branch_key),
                from_bus=f,to_bus=t,associated_line_active=active,nominal_line_charging_mvar=float(p.nominal_charging_mvar),
                fraction=float(p.reactor_fraction),applied_total_reactor_mvar_at1pu=q,
                from_bus_BS_delta_mvar=-q/2,to_bus_BS_delta_mvar=-q/2,policy=str(p.reactor_policy),
                actual_absorption_follows_voltage_squared=True,asbuilt_equipment_claim=False))
    result['bus']=np.asarray(bus);result['branch']=np.asarray(branch);result['bus_name']=np.asarray(names,dtype=object)
    info=dict(branch_keys=np.asarray(runtime_keys,dtype=object),terminal_current_limit_A=np.asarray(limits),
        static_cable_current_limit_A=np.asarray(static_cable_limits),
        branch_map=sorted(branch_map,key=lambda x:x['runtime_branch_row']),added_bus_map=newbus_map,
        thermal_segments=thermal,cable_segments=runtime_cables,reactor_ledger=reactors,
        original_bus_count=nb0,original_branch_count=n0,added_bus_count=len(bus)-nb0,added_branch_count=len(branch)-n0,
        original_bus_BS=source_bus[:,5].copy(),reactor_BS_delta=result['bus'][:nb0,5]-source_bus[:,5])
    require(len(set(runtime_keys))==len(runtime_keys),'Runtime branch keys are duplicated')
    require(np.array_equal(result['bus'][:nb0,[0,1,2,3,4,6,7,8,9,10,11,12]],source_bus[:,[0,1,2,3,4,6,7,8,9,10,11,12]]),'Original bus inputs changed beyond declared reactors')
    require(np.all(result['bus'][nb0:,2:6]==0),'Added line node carries undeclared injections or shunts')
    for name in ['gen','dcline']:
        require(np.array_equal(result[name],case[name]),'Frozen generator/transfer template changed')
    for i in range(n0):
        indices=[r['runtime_branch_row']-1 for r in branch_map if r['original_branch_row']==i+1]
        require(np.allclose(result['branch'][indices,2:5].sum(axis=0),source_branch[i,2:5],rtol=0,atol=1e-12),'Section R/X/B coefficient sums changed')
        if len(indices)>1:
            require(np.isfinite(info['terminal_current_limit_A'][indices,0]).sum()==int(np.isfinite(raw_limits[i,0]))
                    and np.isfinite(info['terminal_current_limit_A'][indices,1]).sum()==int(np.isfinite(raw_limits[i,1])),
                    'Artificial taps acquired duplicated hardware current limits')
    return result,info


def matlab_struct_rows(rows):
    return np.asarray(rows,dtype=object)


def main():
    assignment_path=RAW/'branch_assignments.csv';oh_path=RAW/'thermal_segments.csv';cable_path=RAW/'cable_segments.csv';overlay_path=RAW/'engineering_overlay.mat'
    paths=[assignment_path,oh_path,cable_path,overlay_path,SOURCE_PRE,SOURCE_POST,
           ENGINEERING/'final_branch_mapping_review.json',ENGINEERING/'line_segmentation_accuracy.json',
           ENGINEERING/'shunt_reactor_source_review.json',ENGINEERING/'sources/SEL_Oncor_2013_shunt_reactors.pdf',Path(__file__),
           Path(__file__).with_name('nygrid_ac_apply_sections.m')]
    before={str(p):sha(p) for p in paths}
    a=pd.read_csv(assignment_path);oh=pd.read_csv(oh_path);cables=pd.read_csv(cable_path)
    raw=loadmat(overlay_path,simplify_cells=True);require(len(a)==413,'Wrong frozen branch design')
    plan=build_plan(a,oh,cables)
    require(int((plan.section_count-1).sum())==75,'Unexpected declared section design; review the plan')
    require(plan.loc[plan.is_OH,'section_count'].sum()-plan.is_OH.sum()==73,'OH design changed')
    require(set(plan.loc[plan.is_cable&(plan.section_count>1),'original_branch_row'])=={319,320},'Cable accuracy-triggered split set changed')
    require(int((plan.reactor_selected&plan.is_OH).sum())==16 and int((plan.reactor_selected&plan.is_cable).sum())==19,
            'Charging/length-based reactor selection changed')
    plan_path=OUT/'section_and_reactor_plan.csv';plan.to_csv(plan_path,index=False,lineterminator='\n')
    payload=dict(base_branch_reference=raw['branch_reference'],base_branch_keys=raw['branch_keys'],
        base_terminal_current_limit_A=raw['terminal_current_limit_A'],section_count=plan.section_count.to_numpy(int),
        reactor_total_nominal_mvar=plan.reactor_total_nominal_mvar.to_numpy(float),
        reactor_policy=plan.reactor_policy.to_numpy(object),base_thermal_segments=matlab_struct_rows(oh.to_dict('records')),
        base_cable_segments=matlab_struct_rows(cables.to_dict('records')),baseMVA=100.,
        metadata=dict(status='complete_synthetic_sectioned_network_design;independent_runtime_validation_separate',
            raw_design_revision='revision_02_complete_mapping',maximum_OH_section_length_m=100000.,
            reactor_long_OH_threshold_m=LONG_OH_M,reactor_cable_charging_threshold_mvar=10.,reactor_fraction=.75,
            branch_compensation_or_dispatch_fitting=False,physical_assets_or_weather_certified=False,
            power_scale='existing_gamma_scaled_synthetic_AC;no_current_or_impedance_gamma_transform',
            terminal_hardware_only_at_original_endpoints=True,interior_bus_id_policy='60000+100*original_branch_row+interior_index'))
    planmat=OUT/'sectioned_design_plan.mat';savemat(planmat,payload,do_compression=True,long_field_names=True)
    pre=loadmat(SOURCE_PRE,simplify_cells=True);post=loadmat(SOURCE_POST,simplify_cells=True)
    templates={};runtime={};checks=[];outputs=[plan_path,planmat]
    sources=[('pre_may',pre['refined_2025_pre_may_case']),('may21',pre['refined_2025_may21_case']),
             ('may30',pre['refined_2025_may30_case']),('post_dover',post['full_case'])]
    for name,original in sources:
        base=copy.deepcopy(original);nb=len(base['branch']);base['branch'][:,2:8]=raw['branch_reference'][:nb,2:8]
        base['branch'][210,10]=0
        case,info=compile_case(base,raw['branch_keys'],plan,raw['terminal_current_limit_A'],oh,cables)
        templates[name]=case
        runtime[name]={k:matlab_struct_rows(v) if isinstance(v,list) else v for k,v in info.items()}
        for label in ['branch_map','added_bus_map','thermal_segments','cable_segments','reactor_ledger']:
            path=OUT/f'{name}_{label}.csv';pd.DataFrame(info[label]).to_csv(path,index=False,lineterminator='\n');outputs.append(path)
        checks.append(dict(state=name,original_buses=len(base['bus']),buses=len(case['bus']),
            original_branch_records=nb,branch_records=len(case['branch']),added_zero_injection_buses=info['added_bus_count'],
            active_runtime_OH_thermal_segments=len(info['thermal_segments']),active_runtime_cable_sections=len(info['cable_segments']),
            applied_reactor_corridors=sum(x['associated_line_active'] for x in info['reactor_ledger']),
            total_fixed_reactor_mvar_at1pu=sum(x['applied_total_reactor_mvar_at1pu'] for x in info['reactor_ledger']),
            original_generators_transfers_PD_QD_GS_preserved=True,coefficient_sums_preserved=True,
            no_new_PQ_GS_BS_on_section_buses=True,terminal_A_not_duplicated_at_artificial_taps=True))
    fixtures=OUT/'sectioned_design_fixtures.mat';savemat(fixtures,dict(cases=templates,runtime=runtime),do_compression=True,long_field_names=True);outputs.append(fixtures)
    checks_path=OUT/'sectioned_design_checks.csv';pd.DataFrame(checks).to_csv(checks_path,index=False,lineterminator='\n');outputs.append(checks_path)
    require(before=={str(p):sha(p) for p in paths},'Frozen design source changed during compilation')
    report=dict(passed=True,design_construction_checked=True,created_utc=datetime.now(timezone.utc).isoformat(),
        operating_AC_or_thermal_solver_run=False,original_case_artifacts_modified=False,
        source_raw_stage='frozen_revision_02_complete_mapping',raw_source_status_is_historical_stage_not_runtime_gate=True,
        criteria=dict(OH_max_section_m=OH_MAX_SECTION_M,cable_ABCD_error_trigger=ABCD_TOL,
            long_OH_reactor_threshold_m=LONG_OH_M,cable_reactor_min_charging_mvar=10.,reactor_fraction=.75,
            reactor_fraction_scope='generic_OH_source_supported_midpoint;cable_application_explicit_synthetic_extension'),
        designed_extra_buses=75,OH_split_corridors=int(((plan.section_count>1)&plan.is_OH).sum()),
        cable_split_corridors=[319,320],OH_reactor_corridors=16,cable_reactor_corridors=19,
        source_style='preserve_full_R_X_B_totals;cascade_pi_sections;separate_fixed_negative_bus_BS_reactors',
        no_OPF_outcome_or_observed_interface_input=True,asbuilt_or_actual_site_thermal_claim=False,
        states=checks,dependencies=[record(p) for p in paths],outputs=[record(p) for p in outputs],
        plan_file=record(planmat))
    dump(OUT/'sectioned_design_receipt.json',report)
    print(json.dumps(clean({k:v for k,v in report.items() if k not in ['dependencies','outputs']}),indent=2))


if __name__=='__main__':main()
