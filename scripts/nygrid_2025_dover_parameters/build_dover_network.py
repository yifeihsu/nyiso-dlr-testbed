"""Apply Dover line sections and explicit parallel PARs after full cutover.

The post-cutover reference has192 buses. The additional regulated station port
is eliminated back to the same148 retained buses. Two independent branch phase
inputs are carried through exact DC affine reduction. No generator, load or DC
terminal is introduced at an eliminated bus, and no observed flow enters here.
"""
from pathlib import Path
import copy
import hashlib
import importlib.util
import json
import numpy as np
import pandas as pd
from scipy.io import loadmat,savemat

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/nygrid_2025_dover_parameters'
PARENT=ROOT/'output/nygrid_2025_line_parameters/overlays/engineering_nominal'
SCRIPTS=Path(__file__).parent
REGULATED_BUS=21001
PAR_ROWS=np.array([410,411]) # zero based; new physical bank records411/412
LINE_ROW=412               # new regulated-port-to-LongMountain line413
PINS={
 'output/nygrid_2025_line_parameters/overlays/engineering_nominal/full191_network_cases.mat':'24eac4d6a410f6b2b0bb5b3789e1c74517f8de5695aebadb831ff90f1a75813b',
 'output/nygrid_2025_line_parameters/overlays/engineering_nominal/network_cases.mat':'5fb84104d527b2e26d22f3a772ebd4e56ff981325ea7490d349fa53758646320',
 'output/nygrid_2025_line_parameters/estimates/Dover_line_only_estimates_not_applied.csv':'f2b64d1fd3734daa3a2a078f1cdef97bf4e16281a6203661fa61de352e484dee',
 'scripts/nygrid_2025_slim/build_slim_network.py':'574d8d6eaac69fe2002fba8fa88e24ed0f179c8b78f66ebcdfffffdeea70d9bc'}


def require(ok,msg):
    if not ok:raise ValueError(msg)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def record(p):return dict(path=Path(p).relative_to(ROOT).as_posix(),sha256=sha(p))
def dump(p,d):Path(p).write_text(json.dumps(d,indent=2)+'\n',encoding='utf-8',newline='\n')
def maxabs(x):return float(np.max(np.abs(x),initial=0.))


def load_reducer():
    spec=importlib.util.spec_from_file_location('frozen_Dover_reducer',ROOT/'scripts/nygrid_2025_slim/build_slim_network.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def realize(slim_parent,full,reduction,sreg,reducer):
    """Preserve the existing direct/equivalent branch axis, updating DC values."""
    direct=sreg.iloc[:244].full191_branch_row.to_numpy(int)-1
    pairs=[tuple(map(int,x)) for x in sreg.iloc[244:][['from_bus','to_bus']].to_numpy()]
    require(sorted(reduction['edges'])==pairs,'Dover changed the retained equivalent graph')
    require(np.array_equal(reduction['direct_rows'][reduction['direct_rows']<225],np.arange(225)),
            'An original parent branch record was lost')
    case=copy.deepcopy(slim_parent);branches=full['branch'][direct,:13].copy();eq=[]
    case['userdata']['slim_DC_equivalence']['eliminated_added_zero_injection_buses']=44
    case['userdata']['slim_DC_equivalence']['full_reference_bus_count']=192
    for a,b in pairs:
        item=reduction['edges'][(a,b)]
        eq.append([a,b,0.,item['x_pu'],0.,0.,0.,0.,1.,item['shift_degree'],1.,-360.,360.])
    case['branch']=np.r_[branches,np.asarray(eq)]
    net=reducer.dc(case)
    require(maxabs(net['B']-reduction['Schur_B'])<1e-8,'Dover Schur matrix realization failed')
    require(maxabs(net['phase_bus']-reduction['Schur_phase'])<1e-8,'Dover phase realization failed')
    return case


def build():
    for p,h in PINS.items():require(sha(ROOT/p)==h,'Frozen parent changed: '+p)
    evidence=json.loads((OUT/'sources/dover_source_evidence_receipt.json').read_text())
    require(evidence['passed'] and evidence['parallel_topology_established'],'Parallel bank topology lacks evidence')
    for row in evidence['reviewed_project_files']:require(sha(ROOT/row['path'])==row['sha256'],'Changed project PDF')
    require(sha(OUT/'sources/dover_source_register.csv')==evidence['register_sha256'],'Changed source register')
    basis=json.loads((OUT/'engineering/conditional_impedance_basis.json').read_text())
    require(not basis['source_nameplate']['actual_factory_R_X_and_tap_curve_publicly_established']
        and basis['source_nameplate']['normal_parallel_banks']==2,'Engineering qualification changed')
    scenarios=pd.read_csv(OUT/'engineering/PST_parameter_scenarios.csv',float_precision='round_trip')
    lines=pd.read_csv(ROOT/'output/nygrid_2025_line_parameters/estimates/Dover_line_only_estimates_not_applied.csv',float_precision='round_trip')
    lines=lines[(lines.temperature_c==95)&(lines.adjacent_phase_spacing_ft==25.6)].set_index('section')
    require(len(lines)==4,'Ambiguous line-section engineering choice')
    parent=loadmat(PARENT/'full191_network_cases.mat',simplify_cells=True)
    old=parent['refined_2025_case']
    slimdata=loadmat(PARENT/'network_cases.mat',simplify_cells=True)
    keep=np.asarray(slimdata['kept_bus_ids'],int);oldslim=slimdata['refined_2025_case']
    reg=pd.read_csv(ROOT/'output/nygrid_2025_downstate/network/branch_register.csv',keep_default_na=False)
    sreg=pd.read_csv(ROOT/'output/nygrid_2025_slim/network/branch_register.csv',keep_default_na=False)
    busreg=pd.read_csv(ROOT/'output/nygrid_2025_downstate/network/bus_register.csv',keep_default_na=False)
    zones=dict(zip(busreg.model_bus,busreg.accounting_zone));zones[REGULATED_BUS]='G'
    require(REGULATED_BUS not in old['bus'][:,0] and old['branch'].shape[0]==410,'Parent branch/bus axes changed')
    require(tuple(old['branch'][392,:2])==(20001,20003) and tuple(old['branch'][393,:2])==(20003,20002),
            'Expected existing Dover Y17 and398 assumed paths')
    reducer=load_reducer();folder=OUT/'network';folder.mkdir(parents=True,exist_ok=True)
    dependencies=[ROOT/p for p in PINS]+[OUT/'sources/dover_source_register.csv',OUT/'sources/dover_source_evidence_receipt.json',
        OUT/'engineering/conditional_impedance_basis.json',OUT/'engineering/PST_parameter_scenarios.csv',Path(__file__),
        ROOT/'output/nygrid_2025_downstate/network/branch_register.csv',ROOT/'output/nygrid_2025_slim/network/branch_register.csv',
        ROOT/'output/nygrid_2025_downstate/network/bus_register.csv']
    records=[];branch_rows=[]
    for scenario in scenarios.to_dict('records'):
        name=scenario['scenario'];full=copy.deepcopy(old)
        newbus=old['bus'][old['bus'][:,0]==20003][0].copy();newbus[0]=REGULATED_BUS
        require(np.all(newbus[2:6]==0),'New regulated port has an injection')
        full['bus']=np.vstack([full['bus'],newbus])
        full['bus_name']=np.r_[np.asarray(full['bus_name'],object),['DOVER REGULATED PORT345']]
        # Preserve the old398 proxy as inactive provenance; add the newly
        # resolved line between the correct regulated port and Long Mountain.
        full['branch'][393,10]=0
        for col,field in [(2,'r_pu'),(3,'x_pu'),(4,'b_pu')]:
            full['branch'][392,col]=float(lines.loc['Y17_NY_line_only',field])
        full['branch'][392,5:8]=0 # full-path/facility rating remains unresolved
        bank=np.zeros(13);bank[:2]=[20003,REGULATED_BUS]
        bank[2]=scenario['per_bank_model_r_pu'];bank[3]=scenario['per_bank_x_pu_100MVA']
        bank[5]=scenario['per_bank_selected_nameplate_mva'];bank[8]=1.;bank[10]=1.;bank[11:13]=[-360,360]
        route=old['branch'][393].copy();route[:2]=[REGULATED_BUS,20002]
        for col,field in [(2,'r_pu'),(3,'x_pu'),(4,'b_pu')]:
            route[col]=float(lines.loc['Dover_LongMountain_composite_line_only',field])
        route[5:8]=0;route[10]=1
        full['branch']=np.vstack([full['branch'],bank,bank.copy(),route])
        require(full['bus'].shape[0]==192 and full['branch'].shape[0]==413,'Dover detail shape failed')
        source_rows=np.flatnonzero(reg.source_branch_row.to_numpy(int)>0)
        require(np.array_equal(full['branch'][source_rows],old['branch'][source_rows]),'Historical circuit changed')
        immutable=np.array([j for j in range(410) if j not in [392,393]])
        require(np.array_equal(full['branch'][immutable],old['branch'][immutable]),'Unrelated branch changed')
        require(np.array_equal(full['gen'],old['gen']) and np.array_equal(full['dcline'],old['dcline'])
            and np.array_equal(full['bus'][:191],old['bus']),'Parent operating templates changed')
        r=reducer.reduce_added_components(full,keep)
        slim=realize(oldslim,full,r,sreg,reducer)
        interface=reducer.zone_operators(full,zones)
        H=interface@r['branch_angle_matrix'];h=interface@r['branch_flow_offset']
        angle_basis=[];branch_basis=[];interface_basis=[];shift_basis=[];reduced_phase_basis=[]
        # Unit-radian perturbations are algebraic basis columns, not commanded
        # physical operating points or a relaxation of any phase limit.
        for row in PAR_ROWS:
            perturbed=copy.deepcopy(full);perturbed['branch'][row,9]=np.rad2deg(1.)
            rp=reducer.reduce_added_components(perturbed,keep)
            sp=realize(oldslim,perturbed,rp,sreg,reducer)
            require(maxabs(rp['angle_lift']-r['angle_lift'])==0,'Phase input changed the passive reduction')
            angle_basis.append(rp['angle_offset']-r['angle_offset'])
            branch_basis.append(rp['branch_flow_offset']-r['branch_flow_offset'])
            interface_basis.append(interface@(rp['branch_flow_offset']-r['branch_flow_offset']))
            shift_basis.append(np.deg2rad(sp['branch'][:,9]-slim['branch'][:,9]))
            reduced_phase_basis.append(rp['Schur_phase']-r['Schur_phase'])
        rec=dict(angle_lift=r['angle_lift'],angle_offset=r['angle_offset'],
            branch_angle_matrix=r['branch_angle_matrix'],branch_flow_offset=r['branch_flow_offset'],
            interface_angle_matrix=H,interface_flow_offset=h,
            full_interface_branch_matrix=interface,
            angle_phase_basis=np.asarray(angle_basis).T,
            branch_flow_phase_basis=np.asarray(branch_basis).T,
            interface_phase_basis=np.asarray(interface_basis).T,
            slim_shift_phase_basis=np.asarray(shift_basis).T,
            reduced_phase_bus_basis=np.asarray(reduced_phase_basis).T,
            retained_full_indices_1based=r['retained_indices']+1,
            eliminated_full_indices_1based=r['eliminated_indices']+1,
            phase_units='radians;MATPOWER_SHIFT_sign',angle_units='radians',
            input_bank_rows_1based=PAR_ROWS+1)
        # Test a nontrivial unequal bank phase vector through both reductions.
        psi=np.deg2rad(np.array([7.,-3.]));test=copy.deepcopy(full);test['branch'][PAR_ROWS,9]=np.rad2deg(psi)
        rt=reducer.reduce_added_components(test,keep);st=realize(oldslim,test,rt,sreg,reducer)
        err=max(maxabs(rt['angle_offset']-(rec['angle_offset']+rec['angle_phase_basis']@psi)),
            maxabs(rt['branch_flow_offset']-(rec['branch_flow_offset']+rec['branch_flow_phase_basis']@psi)),
            maxabs(np.deg2rad(st['branch'][:,9])-np.deg2rad(slim['branch'][:,9])-rec['slim_shift_phase_basis']@psi))
        require(err<1e-8,'Independent phase-affine reproduction failed')
        payload=dict(full_case=full,slim_case=slim,recovery=rec,kept_bus_ids=keep,
            full_bus_zones=np.asarray([zones[int(i)] for i in full['bus'][:,0]],object),
            full_branch_keys=np.r_[reg.branch_key.to_numpy(object),['DOVER:PAR:T398_A','DOVER:PAR:T398_B','DOVER:RESOLVED_398']],
            slim_branch_keys=sreg.branch_key.to_numpy(object),
            metadata=dict(scenario=name,model_base_mva=100.,regulator_port_bus=REGULATED_BUS,
                physical_bank_ptids=np.array([625149,625150]),bypass_normally_open_assumption=True,
                spare_in_service=False,parameters_are_conditional_engineering_estimates=True,
                valid_from_utc='2025-12-20T04:00:00Z',
                valid_from_basis='documented_full_service_HB23_cutover_not_first_partial_energization',
                physical_taps_observed=False,physical_winding_resistance_known=False,
                before_full_cutover_reuse_parent191_and148_models=True,retained_original_buses=140,
                direct_source_circuits_preserved=97))
        path=folder/(name+'.mat');savemat(path,payload,do_compression=True,long_field_names=True)
        records.append(dict(scenario=name,path=path.relative_to(ROOT).as_posix(),sha256=sha(path),
            per_bank_x_pu_100MVA=float(bank[3]),full_buses=192,full_branches=413,slim_buses=148,slim_branches=274,
            phase_basis_error=err,original_97_circuits_and_inputs_preserved=True))
        for row,key in [(392,'DOVER:Y17_LINE'),(393,'DOVER:OLD_398_INACTIVE'),(410,'DOVER:PAR:T398_A'),(411,'DOVER:PAR:T398_B'),(412,'DOVER:RESOLVED_398')]:
            z=full['branch'][row]
            branch_rows.append(dict(scenario=name,key=key,full_branch_row=row+1,from_bus=int(z[0]),to_bus=int(z[1]),
                r_pu=z[2],x_pu=z[3],b_pu=z[4],rate_a_mva=z[5],tap=z[8],status=int(z[10]),base_mva=100.,
                physical_factory_impedance_certified=False))
    pd.DataFrame(branch_rows).to_csv(folder/'Dover_applied_branch_register.csv',index=False,lineterminator='\n')
    dump(folder/'network_receipt.json',dict(passed=True,internal_interface_observations_read=False,
        conditional_PAR_impedance_applied=True,new_line_parameters_applied=True,
        original_six_transfer_runtime_contract_preserved=True,physical_full_AC_or_hardware_certification=False,
        scenarios=records,dependencies=[record(p) for p in dict.fromkeys(dependencies)],
        applied_register=record(folder/'Dover_applied_branch_register.csv')))
    print(json.dumps(dict(passed=True,scenarios=records),indent=2))


if __name__=='__main__':build()
