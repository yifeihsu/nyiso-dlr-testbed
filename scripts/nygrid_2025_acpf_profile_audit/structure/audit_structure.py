"""Read-only cable-evidence and bus-lineage audit of committed AC baseline.

The audit can pass as an investigation while reporting physical-classification
conflicts. It does not promote the synthetic conductor model to an asset model.
"""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,re,subprocess
import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'output/nygrid_2025_acpf_profile_audit/structure'
AC=ROOT/'output/nygrid_2025_ac_system'
DOWN=ROOT/'output/nygrid_2025_downstate'
SLIM=ROOT/'output/nygrid_2025_slim/network'
PERFORM=ROOT/'PERFORM/On Peak 2019 v23_Perform_NY/On Peak 2019 v23/nyiso_On_Peak_v23_shunts_as_z_load.m'
INVENTORY=OUT/'sources/perform_ny_branch_inventory.csv'
EXPECTED_HEAD='330be1d90e6faab8d6c32c3d6c174aa364a30c73'


def require(ok,msg):
    if not ok:raise AssertionError(msg)


def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def rec(p):return dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p))


def dump(path,data):
    path.write_text(json.dumps(data,indent=2,allow_nan=False)+'\n',encoding='utf-8')


def csv(name,frame):
    path=OUT/name;frame.to_csv(path,index=False,lineterminator='\n');return path


def rows(v):
    if isinstance(v,dict):return [v]
    if isinstance(v,list):return v
    return list(np.asarray(v,dtype=object).reshape(-1))


def source_receipts():
    new=[
      ('CONED_2018_PSC','Consolidated Edison / NYPSC','2018','coned_2018_psc_annual.pdf',
       'https://documents.dps.ny.gov/public/Common/ViewDoc.aspx?DocRefId=%7BD1ECD891-F860-466A-83DC-46A22D8789BA%7D&DocTitle=2018+PSC+Annual+Filing+Electric',
       '145;147','422;422a','Transmission inventory construction types and corridor endpoints; historical evidence, not a 2025 asset census.'),
      ('NYPA_Y49_2022','New York Power Authority','2022','nypa_y49_2022_notice.pdf',
       'https://documents.dps.ny.gov/public/Common/ViewDoc.aspx?DocRefId=%7BB7F218CA-117C-46D3-A42F-58242A93BC9D%7D',
       '1','1','Y49 expressly underground/submarine between Sprain Brook and East Garden City; already constructed and operating.'),
      ('PSC_Y49_2025','New York Public Service Commission','2025-12-22','psc_y49_2025_order.pdf',
       'https://documents.dps.ny.gov/public/Common/ViewDoc.aspx?DocRefId=%7B7064479B-0000-CC18-A475-5EE82A2ACA0B%7D',
       '1','1','Official order corroborates the Y49 345kV underground/submarine facility and named terminals.'),
      ('LIPA_2018_DISCLOSURE','Long Island Power Authority','2018','lipa_2018_annual_disclosure.pdf',
       'https://documents.dps.ny.gov/public/Common/ViewDoc.aspx?DocRefId=%7BF279431C-3926-4680-B7AC-9DCF11AB9146%7D&DocTitle=Attachment+to+Comments+-LIPA-Annual-Disclosure-Report-FY-2018',
       '27','24','Y50 and Y49 cable terminal pairs; separate Neptune/CSC/1385 transmission technologies.'),
      ('CONED_LTP_2023','Consolidated Edison','2023','coned_local_transmission_plan_2023.pdf',
       'https://www.coned.com/-/media/files/coned/documents/business-partners/transmission-planning/local-transmission-plan-2023.pdf',
       '12','12','Identifies M51 and M52 as the two Sprain Brook-West49th345kV feeders; no source-row-to-owner-ID mapping.'),
    ]
    result=[]
    for sid,publisher,date,name,url,pdfpage,printed,claim in new:
        path=OUT/'sources'/name
        require(path.read_bytes().startswith(b'%PDF-'),'Primary PDF bytes readable '+sid)
        result.append(dict(source_id=sid,publisher=publisher,source_date=date,source_url=url,
            local_path=path.relative_to(ROOT).as_posix(),sha256=sha(path),pdf_pages=pdfpage,printed_pages=printed,
            relevant_pages_visually_reviewed=True,evidence_scope=claim,source_is_current_asset_inventory=False))
    faq=OUT/'sources/coned_rcc_owner_faq.html'
    require('underground transmission feeder connecting our Rainey and Corona substations' in faq.read_text(encoding='utf-8'),'Explicit owner underground statement')
    result.append(dict(source_id='RCC_OWNER_FAQ',publisher='Consolidated Edison',source_date='undated_owner_page_read_2026-10-12',
        source_url='https://www.coned.com/en/our-energy-future/our-energy-vision/where-we-are-going/reliable-clean-city-project/faq',
        local_path=faq.relative_to(ROOT).as_posix(),sha256=sha(faq),pdf_pages='',printed_pages='',
        relevant_pages_visually_reviewed=False,evidence_scope='Owner explicitly calls the installed Rainey-Corona transmission feeder underground; complements dated completion/operator identity evidence.',
        source_is_current_asset_inventory=False))
    prior=pd.read_csv(DOWN/'sources/source_receipts.csv').set_index('source_id')
    for sid in ['RCC_QUEENS_OWNER','RCC_MAY_OWNER','NYISO_WINTER2023','NYISO_MAY2025_OPS','NEPTUNE_OWNER_CABLE']:
        r=prior.loc[sid];p=ROOT/r.local_path
        require(sha(p)==r.sha256,'Preserved primary source bytes '+sid)
        result.append(dict(source_id=sid,publisher=r.publisher,source_date=r.publication_date,source_url=r.source_url,
            local_path=r.local_path,sha256=r.sha256,pdf_pages='existing_downstate_receipt',printed_pages='',
            relevant_pages_visually_reviewed=False,evidence_scope=r.evidence_role,source_is_current_asset_inventory=False))
    return pd.DataFrame(result)


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    require(head==EXPECTED_HEAD,'Audit baseline HEAD changed')
    inputs=[AC/'branches/branch_assignments.csv',AC/'branches/cable_segments.csv',AC/'branches/thermal_segments.csv',
      AC/'branches/sectioned_design_fixtures.mat',AC/'branches/section_and_reactor_plan.csv',
      DOWN/'network/bus_register.csv',DOWN/'network/branch_register.csv',
      DOWN/'sources/source_receipts.csv',DOWN/'sources/upgrade_register.csv',
      DOWN/'sources/merchant_boundary_landing_crosswalk.csv',
      SLIM/'bus_register.csv',SLIM/'eliminated_bus_register.csv',SLIM/'retained_station_rationale.csv',SLIM/'network_cases.mat',
      ROOT/'output/nygrid_2025_line_parameters/overlays/engineering_nominal/full191_network_cases.mat',
      ROOT/'output/nygrid_2025_dover_parameters/network/x_nominal.mat',PERFORM,INVENTORY]
    before={str(p):sha(p) for p in inputs}
    a=pd.read_csv(inputs[0]);c=pd.read_csv(inputs[1]);thermal=pd.read_csv(inputs[2])
    inventory=pd.read_csv(INVENTORY,keep_default_na=False).set_index('source_branch_row')
    canonical_text=PERFORM.read_text(encoding='utf-8')
    match=re.search(r'mpc\.branch\s*=\s*\[(.*?)\];',canonical_text,re.S)
    canonical=np.array([list(map(float,line.split('%')[0].strip().rstrip(';').split()))
        for line in match[1].splitlines() if line.split('%')[0].strip()])
    selected=a.loc[a.branch_row.isin(c.branch_row)].copy()
    require(len(selected)==40,'Complete cable-like model row set')
    raw_counts=selected.classification.value_counts().to_dict()
    require(raw_counts=={'cable_compatible_source_equivalent':22,'urban_non_OH_network_equivalent':12,
        'synthetic_cable_network_equivalent':3,'documented_underground_cable':3},'Current cable classification counts')
    # Strict corridor matches require station names and voltage, never B alone.
    direct={288:(145,'422 row22','West49th-East13th345kV'),289:(145,'422 row22','West49th-East13th345kV'),
      319:(145,'422 row21','SprainBrook-West49th345kV;M51/M52 pair'),320:(145,'422 row21','SprainBrook-West49th345kV;M51/M52 pair'),
      369:(145,'422 row17','Farragut-Gowanus345kV'),370:(145,'422 row17','Farragut-Gowanus345kV'),
      371:(145,'422 row15','Rainey-Farragut345kV'),372:(145,'422 row15','Rainey-Farragut345kV'),
      339:(147,'422a row13','Corona-Jamaica138kV'),340:(147,'422a row13','Corona-Jamaica138kV'),341:(147,'422a row13','Corona-Jamaica138kV')}
    related={336:('422a row8','Dunwoodie South-East179th138kV;model does not resolve North/South terminal'),
      337:('422a row8','Dunwoodie South-East179th138kV;model does not resolve North/South terminal'),
      338:('422a row8','Dunwoodie South-East179th138kV;model does not resolve North/South terminal'),
      342:('422a row12','Astoria-Corona138kV;Astoria versus EastAstoria alias not certified'),
      343:('422a row12','Astoria-Corona138kV;Astoria versus EastAstoria alias not certified'),
      344:('422a row12','Astoria-Corona138kV;Astoria versus EastAstoria alias not certified'),
      345:('422a row12','Astoria-Corona138kV;Astoria versus EastAstoria alias not certified')}
    project={408:('RCC_Rainey_Corona:FEEDER','36188','RCC_OWNER_FAQ;RCC_QUEENS_OWNER;NYISO_WINTER2023'),
      409:('RCC_Gowanus_Greenwood:FEEDER','42233','RCC_MAY_OWNER;NYISO_MAY2025_OPS'),
      410:('RCC_Goethals_FoxHills:FEEDER','39291','RCC_MAY_OWNER;NYISO_MAY2025_OPS')}
    upgrades=pd.read_csv(DOWN/'sources/upgrade_register.csv').set_index('asset_key')
    out=[]
    for b in selected.itertuples():
        row=dict(branch_row=b.branch_row,branch_key=b.branch_key,from_bus=b.from_bus,to_bus=b.to_bus,
            from_name=b.from_name,to_name=b.to_name,base_kv=b.base_kv,current_classification=b.classification,
            current_classification_basis=b.classification_basis,source_branch_row=int(b.source_branch_row),
            model_parameter_representation='synthetic_Cu_XLPE_equivalent;not_installed_cable_specification',
            current_bare_overhead_thermal_eligible=False,installed_electrical_parameters_or_burial_rating_verified=False,
            owner_circuit_ID_bound_to_this_model_row=False,source_record_identity_is_not_physical_type_certificate=True,
            physical_corridor_type_supported=False,source_ids='',source_locator='',owner_feeder_ids='',
            source_claim_scope='No direct physical installation-type evidence found in the inspected primary sources for this exact endpoint pair.')
        if b.source_branch_row>0:
            s=inventory.loc[b.source_branch_row]
            require(np.allclose(canonical[int(b.source_branch_row)-1,2:5],[b.original_r_pu,b.original_x_pu,b.original_b_pu],rtol=0,atol=1e-12),'PERFORM parameter lineage')
            row.update(source_mat_path=PERFORM.relative_to(ROOT).as_posix(),raw_device_key=s.device_key,
                raw_circuit_id=str(s.raw_circuit_id),raw_record_match_unique=bool(int(s.individual_circuit_identity_resolved)),
                raw_identity_confidence=s.identity_confidence,raw_source_device_role=s.source_device_role)
        if b.branch_row in project:
            key,feeder,sids=project[b.branch_row];u=upgrades.loc[key]
            require(str(u.circuit_id)==feeder,'RCC feeder source binding')
            row.update(evidence_tier='A_documented_project_underground_identity',physical_corridor_type_supported=True,
                owner_circuit_ID_bound_to_this_model_row=True,owner_feeder_ids=feeder,source_ids=sids,
                source_locator='upgrade_register:'+key,source_claim_scope='Primary owner/operator evidence supports project feeder, terminals, nominal voltage and chronology; R/X/B and thermal rating remain assumptions.')
        elif b.branch_row in direct:
            page,locator,label=direct[b.branch_row]
            row.update(evidence_tier='B_historical_matching_underground_corridor',physical_corridor_type_supported=True,
                source_ids='CONED_2018_PSC'+(';CONED_LTP_2023' if b.branch_row in [319,320] else ''),
                source_locator=f'PDFp{page};{locator}',source_claim_scope=label+';historical corridor construction supported, exact model-row/physical-circuit assignment and circuit multiplicity not certified.',
                owner_feeder_ids='M51;M52_unordered_pair' if b.branch_row in [319,320] else '')
        elif b.branch_row in related:
            locator,label=related[b.branch_row]
            row.update(evidence_tier='C_related_corridor_terminal_alias_unresolved',source_ids='CONED_2018_PSC',
                source_locator='PDFp147;'+locator,source_claim_scope=label+';supporting context only, not exact physical-row certification.')
        elif b.classification=='synthetic_cable_network_equivalent':
            row.update(evidence_tier='E_explicit_synthetic_network_proxy',source_claim_scope='Builder explicitly labels omitted-network or project-route proxy, not a unique installed circuit.')
            if b.branch_row==400:
                row.update(physical_corridor_type_supported=True,source_ids='CONED_2018_PSC',source_locator='PDFp147;422a row23',
                    source_claim_scope='Greenwood-FoxHills138kV is historically documented underground, but this model row remains an explicitly synthetic receiving-network proxy.')
            if b.branch_row==401:
                row.update(source_ids='CONED_LTP_2023',source_locator='PDFp12',owner_feeder_ids='Q35M_corridor_reference_only',
                    source_claim_scope='Owner confirms East13th-AstoriaAnnex345kV feeder Q35M; this aggregate proxy is not an individual Q35 cable or installed parameter model.')
        else:
            row['evidence_tier']='D_electrical_or_urban_assumption_only'
        out.append(row)
    evidence=pd.DataFrame(out);outputs=[csv('cable_evidence_tiers.csv',evidence)]
    conflicts=[]
    conflict_sources={300:('Y50','LIPA_2018_DISCLOSURE;CONED_2018_PSC','LIPAp27/printed24;ConEdp145/printed422 row23',
        'Owner identifies ShoreRoad-Dunwoodie as Y50 cable; ConEd lists its county-line section as underground.'),
      309:('Y49','NYPA_Y49_2022;PSC_Y49_2025;LIPA_2018_DISCLOSURE','NYPAp1;PSCp1;LIPAp27/printed24',
        'NYPA/PSC identify EastGardenCity-SprainBrook345kV as underground/submarine Y49; two identical source rows do not prove two physical Y49 circuits.'),
      310:('Y49','NYPA_Y49_2022;PSC_Y49_2025;LIPA_2018_DISCLOSURE','NYPAp1;PSCp1;LIPAp27/printed24',
        'NYPA/PSC identify EastGardenCity-SprainBrook345kV as underground/submarine Y49; two identical source rows do not prove two physical Y49 circuits.'),
      386:('Goethals-Gowanus','CONED_2018_PSC','PDFp145;printed422 row18',
        'Named physical corridor is underground; model record itself is a synthetic aggregate attachment, not a proven physical circuit.')}
    for index,(label,sids,locator,claim) in conflict_sources.items():
        b=a.loc[a.branch_row==index].iloc[0];t=thermal.loc[thermal.branch_row==index]
        require(b.thermal_overhead_eligible and len(t)==1,'Current overhead classification conflict location')
        s=inventory.loc[int(b.source_branch_row)] if b.source_branch_row>0 else None
        conflicts.append(dict(branch_row=index,branch_key=b.branch_key,from_name=b.from_name,to_name=b.to_name,
            current_classification=b.classification,current_OH_thermal_eligible=True,documented_corridor=label,
            physical_overhead_thermal_qualification_supported=False,model_source_row=int(b.source_branch_row),
            raw_record_key=s.device_key if s is not None else '',
            raw_record_assignment_unique=bool(int(s.individual_circuit_identity_resolved)) if s is not None else False,
            raw_record_identity_is_not_owner_circuit_identity=True,source_ids=sids,source_locator=locator,
            finding=claim,current_catalog_id=t.iloc[0].catalog_id,current_circuits=int(t.iloc[0].circuits),
            current_bundle_count=int(t.iloc[0].bundle_count),current_length_m=float(t.iloc[0].segment_length_m),
            required_followup='Versioned physical-class review and cable/aggregate treatment before asserting real-route OH DLR; no current-model mutation in this audit.'))
    conflicts=pd.DataFrame(conflicts);outputs.append(csv('overhead_cable_classification_conflicts.csv',conflicts))
    # Exact bus-axis reconciliation, using saved matrices rather than counts alone.
    fullreg=pd.read_csv(DOWN/'network/bus_register.csv');slimreg=pd.read_csv(SLIM/'bus_register.csv')
    eliminated=pd.read_csv(SLIM/'eliminated_bus_register.csv');rationale=pd.read_csv(SLIM/'retained_station_rationale.csv')
    full=loadmat(ROOT/'output/nygrid_2025_line_parameters/overlays/engineering_nominal/full191_network_cases.mat',simplify_cells=True)
    slim=loadmat(SLIM/'network_cases.mat',simplify_cells=True)
    dover=loadmat(ROOT/'output/nygrid_2025_dover_parameters/network/x_nominal.mat',simplify_cells=True)['full_case']
    fixtures=loadmat(AC/'branches/sectioned_design_fixtures.mat',simplify_cells=True)
    fids=set(fullreg.model_bus);sids=set(slimreg.model_bus);parent=set(range(1,141))
    retained=sids-parent;restored=fids-sids
    require(len(fids)==191 and len(sids)==148 and parent<=sids,'Full/reduced node axes')
    require(retained==set(rationale.model_bus) and len(retained)==8,'Eight retained added nodes')
    require(restored==set(eliminated.model_bus) and len(restored)==43,'Exact restored 43 nodes')
    require(set(slim['refined_2025_pre_may_case']['bus'][:,0])==sids,'Reduced MAT axis')
    require(set(full['refined_2025_pre_may_case']['bus'][:,0])==fids,'Full MAT axis')
    for key in ['refined_2025_pre_may_case','refined_2025_may21_case','refined_2025_may30_case']:
        model=full[key];new_nodes=~np.isin(model['bus'][:,0],list(parent))
        require(np.all(model['bus'][new_nodes,2:4]==0),'Restored/added station nodes carry no duplicated P/Q loads')
        require(not np.isin(model['gen'][:,0],list(fids-parent)).any(),'Restoration does not add or relocate generation')
    require(set(dover['bus'][:,0])-fids=={21001},'Only Dover regulated port adds the 192nd reference node')
    pre=fixtures['cases']['pre_may'];post=fixtures['cases']['post_dover']
    numeric=set(post['bus'][:,0])-set(dover['bus'][:,0])
    require(len(numeric)==75 and set(pre['bus'][:,0])-fids==numeric,'Same 75 AC numerical nodes pre/post')
    require(len(pre['bus'])==266 and len(post['bus'])==267,'AC final node counts')
    branchreg=pd.read_csv(DOWN/'network/branch_register.csv')
    lineage=[]
    for b in fullreg.itertuples():
        kind=('original_parent_model_bus' if b.model_bus<=140 else 'device_terminal_auxiliary' if b.model_bus in [20009,20010,20014] else
            'historical_source_tap_or_unknown_bus' if str(b.model_name).startswith(('UNKNOWN','TAP')) else
            'historical_named_source_station_terminal' if b.source_bus>0 else 'public_project_station_terminal_with_equivalent_connections')
        adjacent=branchreg.loc[(branchreg.from_bus==b.model_bus)|(branchreg.to_bus==b.model_bus),'branch_key']
        lineage.append(dict(model_bus=int(b.model_bus),model_name=b.model_name,base_kv=float(b.base_kv),
            lineage_kind=kind,original_identity_role=b.identity_role,source_bus=int(b.source_bus),
            source_key=f'PERFORM2019:BUS:{int(b.source_bus)}' if b.source_bus>0 else f'NPCC:BUS:{b.model_bus}' if b.model_bus<=140 else f'PROJECT_MODEL_BUS:{b.model_bus}',
            retained_in_reduced148=b.model_bus in sids,one_of_8_retained_additions=b.model_bus in retained,
            one_of_43_restored_nodes=b.model_bus in restored,present_full191=True,present_full192=True,
            present_AC266=True,present_AC267=True,adjacent_source_branch_keys=';'.join(adjacent),
            is_new_physical_substation_claim=False,numerical_only_AC_section_node=False,
            source_reference=DOWN.joinpath('network/bus_register.csv').relative_to(ROOT).as_posix()))
    d=dover['bus'][dover['bus'][:,0]==21001][0]
    require(np.all(d[2:6]==0),'Dover port has zero injection/shunt')
    lineage.append(dict(model_bus=21001,model_name='DOVER REGULATED PORT345',base_kv=345.,
        lineage_kind='Dover_PAR_regulated_terminal_auxiliary',source_bus=0,source_key='DOVER:REGULATED_PORT:21001',
        retained_in_reduced148=False,one_of_8_retained_additions=False,one_of_43_restored_nodes=False,
        present_full191=False,present_full192=True,present_AC266=False,present_AC267=True,
        adjacent_source_branch_keys='DOVER:PAR:T398_A;DOVER:PAR:T398_B;DOVER:RESOLVED_398',
        is_new_physical_substation_claim=False,numerical_only_AC_section_node=False,
        source_reference='output/nygrid_2025_dover_parameters/network/x_nominal.mat'))
    added=pd.DataFrame(rows(fixtures['runtime']['post_dover']['added_bus_map']))
    require(set(added.bus_id)==numeric,'Numerical bus map covers exact new axis')
    numeric_oh=0;numeric_cable=0
    for b in added.itertuples():
        x=post['bus'][post['bus'][:,0]==b.bus_id][0];p=a.loc[a.branch_row==b.original_branch_row].iloc[0]
        require(np.all(x[2:6]==0),'Numerical bus has zero P/Q/GS/BS')
        oh=bool(p.thermal_overhead_eligible);numeric_oh+=int(oh);numeric_cable+=int(not oh)
        lineage.append(dict(model_bus=int(b.bus_id),model_name=str(post['bus_name'][np.flatnonzero(post['bus'][:,0]==b.bus_id)[0]]),base_kv=float(x[9]),
            lineage_kind='OH_pi_section_numerical_node' if oh else 'cable_pi_section_numerical_node',source_bus=0,
            source_key=str(b.original_branch_key)+f':INTERIOR_FRACTION:{b.stationing_fraction}',
            retained_in_reduced148=False,one_of_8_retained_additions=False,one_of_43_restored_nodes=False,
            present_full191=False,present_full192=False,present_AC266=True,present_AC267=True,
            adjacent_source_branch_keys=str(b.original_branch_key),original_corridor_row=int(b.original_branch_row),
            stationing_fraction=float(b.stationing_fraction),is_new_physical_substation_claim=False,
            numerical_only_AC_section_node=True,zero_P_Q_GS_BS_checked=True,
            source_reference='output/nygrid_2025_ac_system/branches/sectioned_design_fixtures.mat'))
    require(numeric_oh==73 and numeric_cable==2,'73 OH + 2 cable numerical nodes')
    busdf=pd.DataFrame(lineage).sort_values('model_bus')
    require(len(busdf)==267 and set(busdf.model_bus)==set(post['bus'][:,0]),'Complete 267-node lineage')
    outputs.extend([csv('bus_lineage_all267.csv',busdf),csv('retained_8_added_buses.csv',busdf.loc[busdf.one_of_8_retained_additions]),
        csv('restored_43_buses.csv',busdf.loc[busdf.one_of_43_restored_nodes]),csv('numerical_75_buses.csv',busdf.loc[busdf.numerical_only_AC_section_node])])
    boundary=pd.read_csv(DOWN/'sources/merchant_boundary_landing_crosswalk.csv')
    boundary['part_of_40_AC_cable_equivalent_rows']=False
    boundary['bare_overhead_DLR_on_controlled_transfer']=False
    outputs.append(csv('controlled_transfer_cable_scope.csv',boundary))
    receipts=source_receipts();outputs.append(csv('source_receipts.csv',receipts))
    require(before=={str(p):sha(p) for p in inputs},'Old source/model bytes changed during read-only audit')
    summary=dict(passed=True,audit_complete=True,created_utc=datetime.now(timezone.utc).isoformat(),baseline_HEAD=head,
        current_model_changed=False,old_inputs_byte_preserved=True,physical_cable_inventory_certified=False,
        current_cable_equivalent_rows=40,current_model_classification_counts=raw_counts,
        reviewed_cable_evidence_tier_counts=evidence.evidence_tier.value_counts().to_dict(),
        project_feeder_underground_identities_supported=3,historical_strict_corridor_matches=11,
        historical_related_alias_unresolved_rows=7,electrical_or_urban_assumption_only_rows=16,explicit_synthetic_proxy_rows=3,
        all_40_as_actual_underground_cables_claim_supported=False,
        known_cable_corridor_conflicts_in_current_OH_rows=[300,309,310,386],
        current_OH_classification_is_complete_physical_line_inventory=False,
        bus_reconciliation=dict(original_parent=140,full_reference_added=51,full_reference=191,
            reduced_retained_added=8,reduced=148,restored_from_reduced=43,Dover_regulated_auxiliary=1,
            numerical_AC_nodes=75,numerical_OH_nodes=73,numerical_cable_nodes=2,AC_pre_Dover=266,AC_post_Dover=267,
            original_nodes_removed=0,extra_buses_are_not_extra_generation_or_load=True,
            retained_added_ids=sorted(retained),restored_ids=sorted(restored),
            added51_kind_counts=busdf.loc[busdf.present_full191&(busdf.model_bus>140),'lineage_kind'].value_counts().to_dict()),
        limitations=['Corridor evidence does not certify assignment to a particular model row, number of physical circuits, cable construction parameters or burial ampacity.',
            'The 2018 utility inventories are historical; selected project sources supplement them, not a complete 2025 asset audit.',
            'Y49 is documented as a cable corridor. Two identical PERFORM rows do not establish two physical Y49 circuits.',
            'The current OH thermal equations on four cable-correlated rows cannot serve as physical thermal certification for those routes.',
            'Original parent and added historical nodes are model terminals or aggregates; 267 electrical nodes are not 267 physical substations.',
            'Controlled-transfer cables, including Neptune and the Norwalk-Northport link, lie outside the 40 AC cable-equivalent-row count.'],
        sources=[rec(p) for p in inputs]+[rec(Path(__file__))],outputs=[rec(p) for p in outputs])
    dump(OUT/'structure_audit.json',summary)
    print(json.dumps({k:v for k,v in summary.items() if k not in ['sources','outputs']},indent=2))


if __name__=='__main__':main()
