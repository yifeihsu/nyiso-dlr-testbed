"""Read-only role/operator/network audit; writes only crosswalk* artifacts.

Uses no target values and solves no operating point. Branch keys come from
the frozen compact branch map; NYgrid operators come from its independently
audited released if.map. Source-zone labels are equivalent allocation roles,
not proof of geographic location. Requires numpy, pandas and scipy.
"""
from pathlib import Path
import hashlib
import json
import platform
import re
import numpy as np
import pandas as pd
import scipy
from scipy.io import loadmat

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
COMPACT = ROOT / 'output/compact_npcc_ny/compact_npcc_ny_reference.mat'
SOURCE = ROOT / 'output/nygrid_2019/unmodified_smoke_mirror_legacy.mat'
UP = ROOT / 'tmp/nygrid_2019_reproduction/upstream'
NAMES = ['Dysinger East', 'West Central', 'Total East', 'Moses South',
         'Central East', 'UpNY-Coned', 'Dun/SPR-South']
PAIRS = [[('A','B')],[('B','C')],[('E','F'),('E','G')],[('D','E')],
         [('E','F')],[('G','H')],[('I','J')]]
EXTENSION = {774:'G',858:'G',9001:'G',9002:'G',9003:'K'}


def write(data, suffix):
    if not isinstance(data, pd.DataFrame):
        data = pd.DataFrame(data)
    data.to_csv(OUT / ('crosswalk_' + suffix + '.csv'), index=False,
                lineterminator='\n', float_format='%.15g')


def edge_key(branch):
    return tuple(sorted(map(int, branch[:2])))


def main():
    data = loadmat(COMPACT, simplify_cells=True)
    source_data = loadmat(SOURCE, simplify_cells=True)
    model = data['mpc']
    source = source_data['cases'][0]['input']
    bus = model['bus']; br = model['branch']
    ids = bus[:,0].astype(int)
    assert len(ids)==51 and set(range(37,83)) <= set(ids)
    assert len(br)==92 and sum(br[:,10]>0)==87
    key_file = ROOT/'output/compact_npcc_ny/compact_branch_map.csv'
    branch_map = pd.read_csv(key_file)
    keys = branch_map.branch_key.tolist()
    assert len(keys)==len(br) and len(set(keys))==len(keys)
    audit_branches = pd.read_csv(ROOT/'output/compact_npcc_ny/compact_NY_replay_branch.csv')
    assert np.array_equal(audit_branches[['from_bus','to_bus']].to_numpy(),br[:,:2])
    assert np.array_equal(audit_branches.online.to_numpy(),br[:,10])
    paper = pd.read_csv(UP/'Data/npcc.csv',keep_default_na=False).set_index('idx')
    load_roles = pd.read_csv(UP/'Data/npcc_new.csv',keep_default_na=False).set_index('idx')
    original = loadmat(UP/'Data/npcc.mat',simplify_cells=True)['mpc']
    compact_zones = dict(zip(ids, map(str,model['userdata']['nyiso_physical_zone'])))
    paper_zones = {i:str(paper.loc[i,'zone']) if i in paper.index else EXTENSION[i] for i in ids}
    source_gen_buses = set(source['gen'][:,0].astype(int)) & set(range(37,83))
    compact_gen_buses = set(model['gen'][:,0].astype(int))
    special = {
        38:'Equivalent role E in paper vs F in compact changes37-38 from CentralEast member to intrazone;38-69 reverses from E-internal to C-F crossing.',
        46:'Paper E; compact D. Paper MosesSouth includes46-49, compact northern partition includes45-46 instead.',
        47:'Paper E; compact D. Paper MosesSouth includes47-48; compact treats it as D-internal.',
        62:'Paper B; compact A. Moves54-62/58-62 across Dysinger in paper and62-63 across WestCentral.',
        69:'Paper E; compact C.38-69 remains an original physical/equivalent network edge in both; it is not a substitute to delete when adding paper Marcy.',
        74:'Paper IndianPoint2/3 and reference generation land here; compact has the bus but no generator record. Preserve74 for literal bus-injection transfer.',
        77:'Paper G; compact H.74-77 is a paper UPNY member; candidate physical IndianPoint relocation to77 is a separate spatial-policy experiment.',
        79:'Paper K allocation role despite RAV A-3 name; compact J. Paper Dunwoodie excludes78-79, current compact I-J includes it.'}
    roles=[]
    for i,b in enumerate(bus):
        bid=int(b[0]); pg=bid in paper.index
        roles.append({'bus_id':bid,'compact_bus_name':str(model['bus_name'][i]),
            'base_kv':b[9], 'original_NPCC_NY_bus':37<=bid<=82,
            'nygrid_equivalent_zone':paper_zones[bid], 'compact_declared_physical_zone':compact_zones[bid],
            'zone_role_differs':paper_zones[bid]!=compact_zones[bid],
            'nygrid_zone_basis':'released_npcc.csv_and_npcc_new.csv' if pg else 'explicit_added_transit_role_assumption',
            'nygrid_raw_load_weight':load_roles.loc[bid,'sumLoadP0'] if pg else 0,
            'nygrid_generator_role_present':bid in source_gen_buses,
            'compact_generator_record_present':bid in compact_gen_buses,
            'source_generation_role_missing_in_compact':bid in source_gen_buses and bid not in compact_gen_buses,
            'recommended_literal_injection_bus':bid,
            'claim_boundary':'role_identity_not_geographic_validation',
            'note':special.get(bid,'Same original ID retained; transfer original bus-level P exactly. Added terminals remain zero-injection unless separately justified.' if pg else 'Zero-injection extension retained with explicitly assigned comparison-zone role.')})
    write(roles,'bus_roles')
    assert sum(x['zone_role_differs'] for x in roles)==7
    # Verify the semantic definition against the already audited if.map terms.
    term_file=ROOT/'output/nygrid_2019/operator_audit_terms.csv'
    terms=pd.read_csv(term_file)
    ref=terms[(terms.smoke_case==1)&(terms.operator_variant=='released_if_map')].copy()
    assert len(ref)==24
    operator_rows=[]; coverage=[]
    for name,pairs in zip(NAMES,PAIRS):
        expected=ref[ref.interface==name]
        for row in expected.itertuples():
            matches=[j for j,b in enumerate(br) if edge_key(b)==tuple(sorted([row.from_bus,row.to_bus])) and b[10]>0]
            coverage.append({'interface_name':name,'nygrid_branch_row':row.branch_row,
                'source_from_bus':row.from_bus,'source_to_bus':row.to_bus,'source_PF_coefficient':row.PF_coefficient,
                'matching_active_compact_count':len(matches),
                'matching_active_compact_keys':';'.join(keys[j] for j in matches),
                'identity_status':'missing_direct_edge' if not matches else ('same_endpoint_identity' if len(matches)==1 else 'multiple_parallel_records_all_must_be_accounted'),
                'exact_electrical_response_identity':False})
        for j,b in enumerate(br):
            if b[10]<=0:continue
            f,t=map(int,b[:2]);zf,zt=paper_zones[f],paper_zones[t]
            sign=sum(1 if (zf,zt)==p else -1 if (zt,zf)==p else 0 for p in pairs)
            if sign:
                operator_rows.append({'operator_variant':'nygrid_role_corridor_v1','interface_name':name,
                    'compact_branch_row':j+1,'branch_key':keys[j],'from_bus':f,'to_bus':t,
                    'from_role':zf,'to_role':zt,'PF_coefficient':sign,'PT_coefficient':0,
                    'source_upstream_bus':f if sign>0 else t,
                    'uniform_upstream_AC_PF_coefficient':1 if sign>0 else 0,
                    'uniform_upstream_AC_PT_coefficient':1 if sign<0 else 0,
                    'exact_official_public_operator':False,
                    'metering_scope':'signed_from_terminal_P_for_literal_DC;upstream_AC_columns_are_separate_loss_convention'})
    # Reproduce the frozen current source-informed partition semantics without targets.
    for name in NAMES:
        if name=='Dysinger East':up={i for i,z in compact_zones.items() if z=='A'};down=set(ids)-up
        elif name=='West Central':up={i for i,z in compact_zones.items() if z in ['A','B']};down=set(ids)-up
        elif name=='Total East':up={i for i,z in compact_zones.items() if z in list('ABCDE')};down=set(ids)-up
        elif name=='Moses South':up={i for i,z in compact_zones.items() if z=='D'};down=set(ids)-up
        elif name=='Central East':up={i for i,z in compact_zones.items() if z=='E'};down={i for i,z in compact_zones.items() if z=='F'}
        elif name=='UpNY-Coned':up={i for i,z in compact_zones.items() if z in list('ABCDEFG') and i not in [858,9002]};down=set(ids)-up
        else:up={i for i,z in compact_zones.items() if z=='I'};down={i for i,z in compact_zones.items() if z=='J'}
        for j,b in enumerate(br):
            if b[10]<=0:continue
            f,t=map(int,b[:2]);sign=int(f in up and t in down)-int(t in up and f in down)
            if sign:
                operator_rows.append({'operator_variant':'frozen_current_partition_v1','interface_name':name,
                    'compact_branch_row':j+1,'branch_key':keys[j],'from_bus':f,'to_bus':t,
                    'from_role':compact_zones[f],'to_role':compact_zones[t],'PF_coefficient':sign,'PT_coefficient':0,
                    'source_upstream_bus':f if sign>0 else t,
                    'uniform_upstream_AC_PF_coefficient':1 if sign>0 else 0,
                    'uniform_upstream_AC_PT_coefficient':1 if sign<0 else 0,
                    'exact_official_public_operator':False,
                    'metering_scope':'signed_from_terminal_P_DC;frozen_AC_operator_uses_the_separate_upstream_columns'})
    operators=pd.DataFrame(operator_rows)
    assert not operators.duplicated(['operator_variant','interface_name','branch_key']).any()
    write(operators,'operator_members');write(coverage,'source_operator_member_coverage')
    summary=[]
    for name in NAMES:
        a=operators[(operators.interface_name==name)&(operators.operator_variant=='nygrid_role_corridor_v1')]
        b=operators[(operators.interface_name==name)&(operators.operator_variant=='frozen_current_partition_v1')]
        av=dict(zip(a.branch_key,a.PF_coefficient));bv=dict(zip(b.branch_key,b.PF_coefficient))
        summary.append({'interface_name':name,'nygrid_role_member_count':len(a),'current_partition_member_count':len(b),
            'same_compact_operator':av==bv,
            'only_nygrid_role_keys':';'.join(sorted(set(av)-set(bv))),
            'only_current_partition_keys':';'.join(sorted(set(bv)-set(av))),
            'coefficient_changed_keys':';'.join(k for k in sorted(set(av)&set(bv)) if av[k]!=bv[k]),
            'correction_type':'measurement_harmonization_same_electrical_state','targets_used':False})
    write(summary,'operator_summary')
    # Original/reduced source and compact parallel-path accounting. DC only:
    # charging does not enter; taps/phase shifts remain separately reported.
    srcbr=source['branch']
    srcbr=srcbr[np.isin(srcbr[:,0],range(37,83))&np.isin(srcbr[:,1],range(37,83))&(srcbr[:,10]>0)]
    active=br[br[:,10]>0]
    pair_rows=[]
    for pair in sorted(set(map(edge_key,srcbr))|set(map(edge_key,active))):
        s=srcbr[np.array([edge_key(b)==pair for b in srcbr])]
        c=active[np.array([edge_key(b)==pair for b in active])]
        si=[j for j,b in enumerate(source['branch']) if edge_key(b)==pair and b[10]>0]
        ci=[j for j,b in enumerate(br) if edge_key(b)==pair and b[10]>0]
        def susceptance(x):return float(sum(1/(b[3]*(b[8] if b[8] else 1)) for b in x))
        bs,bc=susceptance(s),susceptance(c)
        pair_rows.append({'bus_a':pair[0],'bus_b':pair[1],'source_active_count':len(s),'compact_active_count':len(c),
            'source_branch_rows':';'.join(str(j+1) for j in si),'compact_keys':';'.join(keys[j] for j in ci),
            'source_sum_reciprocal_tap_x_pu':bs,'compact_sum_reciprocal_tap_x_pu':bc,
            'same_pair_DC_susceptance':abs(bs-bc)<1e-10,
            'source_x_values':';'.join(str(b[3]) for b in s),'compact_x_values':';'.join(str(b[3]) for b in c),
            'source_any_phase_shift':bool(np.any(s[:,9])),'compact_any_phase_shift':bool(np.any(c[:,9])),
            'scope':'parallel_pair_only_not_whole_network_transfer_identity'})
    write(pair_rows,'network_pairs')
    additions=[]
    for j,b in enumerate(br):
        if not keys[j].startswith('NPCC_S7:BRANCH_ROW:') or int(keys[j].split(':')[-1])<234:continue
        f,t=map(int,b[:2]);pair=edge_key(b)
        direct=[k+1 for k,x in enumerate(srcbr) if edge_key(x)==pair]
        cuts=operators[(operators.branch_key==keys[j])&(operators.operator_variant=='nygrid_role_corridor_v1')].interface_name.tolist()
        classification=('retired_record_not_active_overlap' if b[10]<=0 else
                        'additional_parallel_path_at_existing_source_endpoints' if direct else
                        'new_compact_path_with_no_identical_source_edge')
        additions.append({'branch_key':keys[j],'compact_branch_row':j+1,'from_bus':f,'to_bus':t,
            'status':int(b[10]),'r_pu':b[2],'x_pu':b[3],'b_pu':b[4],
            'classification':classification,'paper_role_cuts_crossed':';'.join(cuts),
            'same_endpoint_as_paper_Marcy_addition':pair in [(38,43),(38,77)],
            'recommendation':'retain_primary;remove_only_in_separate_registered_hypothesis_with_zero_transit_components_handled',
            'physical_functional_overlap_proven':False})
    write(additions,'s4_additions')
    marcy=[]
    for f,t,x in [(43,38,.0427),(38,77,.0147)]:
        match=[j for j,b in enumerate(br) if edge_key(b)==tuple(sorted([f,t])) and b[10]>0]
        marcy.append({'source_from_bus':f,'source_to_bus':t,'source_r_pu':.02,'source_x_pu':x,
            'source_rate_a':0,'source_base_mva':100,'existing_active_same_endpoint_count':len(match),
            'existing_keys':';'.join(keys[j] for j in match),
            'diagnostic_action':'append_separate_paper_specific_DC_hypothesis;retain38-69_and_all_primary_compact_paths',
            'exact_physical_overlap_proven':False,'AC_or_DLR_parameter_qualified':False,
            'note':'Distinct source topology addition, not a replacement for38-69 which source retains. Existing38-39 path is different endpoints; equivalent regional overlap remains unproven.'})
    write(marcy,'marcy_hypothesis')
    validation=[{'gate':'all_original_46_bus_IDs_retained','passed':True,'evidence':'Original37:82 are a subset of compact51.'},
                {'gate':'seven_role_differences_verified','passed':True,'evidence':'38;46;47;62;69;77;79.'},
                {'gate':'operators_use_unique_active_stable_keys','passed':True,'evidence':'No duplicate interface/key pairs; active status checked before membership.'},
                {'gate':'Marcy_direct_endpoint_pairs_absent','passed':not any(x['existing_active_same_endpoint_count'] for x in marcy),
                 'evidence':'43-38 and38-77 each have zero active compact records; functional equivalence beyond identical endpoints not established.'}]
    actual_compact=OUT/'compact/current_operator_members.csv'
    actual_source=OUT/'reference/corrected_interface_coefficients.csv'
    extra_deps=[]
    if actual_compact.exists():
        current=pd.read_csv(actual_compact)
        name_map={'Dysinger_East':'Dysinger East','West_Central':'West Central','Moses_South':'Moses South',
                  'Central_East':'Central East','Total_East_proxy':'Total East','UPNY_ConEd':'UpNY-Coned','Dunwoodie_South':'Dun/SPR-South'}
        current.interface_name=current.interface_name.map(name_map)
        expected={(x.interface_name,x.branch_key,x.meter_column):x.sign for x in current.itertuples()}
        actual={}
        for x in operators[operators.operator_variant=='frozen_current_partition_v1'].itertuples():
            actual[(x.interface_name,x.branch_key,'PF' if x.PF_coefficient>0 else 'PT')]=1
        assert expected==actual,'Independent MATLAB compact operator differs from this crosswalk.'
        validation.append({'gate':'current_operator_matches_independent_MATLAB_export','passed':True,
                           'evidence':'Every interface/key/PF-or-PT/sign matches current_operator_members.csv.'})
        extra_deps.append(actual_compact)
    if actual_source.exists():
        actual=pd.read_csv(actual_source)
        a={(x.interface,int(x.source_branch_row),int(x.from_bus),int(x.to_bus),float(x.coefficient)) for x in actual.itertuples()}
        b={(x.interface,int(x.branch_row),int(x.from_bus),int(x.to_bus),float(x.PF_coefficient)) for x in ref.itertuples()}
        assert a==b,'Fresh annual reference operators differ from pinned semantic audit.'
        validation.append({'gate':'reference_operator_matches_fresh_annual_export','passed':True,
                           'evidence':'All24 corrected source terms match fresh reference export by row/endpoints/sign.'})
        extra_deps.append(actual_source)
    write(validation,'validation')
    deps=[Path(__file__),COMPACT,SOURCE,key_file,UP/'Data/npcc.csv',UP/'Data/npcc_new.csv',
          UP/'Data/npcc.mat',UP/'modifyMPC.m',UP/'updateOpCond.m',UP/'Utility/allocateLoad.m',
          term_file,ROOT/'System Matpower Format/NY_Lite/compact_nyiso_interface_operator_variant.m',
          ROOT/'System Matpower Format/NY_Lite/nyiso_bus_zone_map.m']+extra_deps
    write([{'path':p.relative_to(ROOT).as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
            'lf_normalized_sha256':hashlib.sha256(p.read_bytes().replace(b'\r\n',b'\n')).hexdigest() if p.suffix in ['.m','.py','.csv'] else ''} for p in deps], 'sources')
    result={'read_only_audit':True,'observed_interfaces_used':False,'network_or_dispatch_modified':False,
        'all_original_46_NY_buses_preserved':True,'role_mismatches':[x['bus_id'] for x in roles if x['zone_role_differs']],
        'source_generator_role_missing_buses':[x['bus_id'] for x in roles if x['source_generation_role_missing_in_compact']],
        'source_internal_branches':len(srcbr),'compact_active_branches':len(active),
        'source_original_branch_records':len(original['branch']),'compact_S7_parent_branch_records':len(data['build']['parent']['branch']),
        'compact_inherited_NPCC_branch_records_before_13_S4_additions':233,
        'source_Marcy_existing_same_endpoint_count':sum(x['existing_active_same_endpoint_count'] for x in marcy),
        'runtime':{'python':platform.python_version(),'numpy':np.__version__,'pandas':pd.__version__,'scipy':scipy.__version__}}
    (OUT/'crosswalk_summary.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2));print(pd.DataFrame(summary).to_string(index=False))


if __name__=='__main__':main()
