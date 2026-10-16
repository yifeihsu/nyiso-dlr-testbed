"""Bind source-backed North NYCA scope and a conditional PV20 repair contract.

No circuit mapping is invented, no P32 value is used, and no AC case is changed.
The certificate distinguishes documentary topology from meter equivalence.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'output/nygrid_2025_moses_repair/boundary'
SOURCES=OUT/'sources'
DEPS={}


def sha(path):
    with Path(path).open('rb')as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def read(path):
    path=Path(path);DEPS[path.relative_to(ROOT).as_posix()]=sha(path);return path


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    definitions=pd.read_csv(read(ROOT/'output/nygrid_2025_flowgate_definitions/definitions/all_seasonal_members.csv'))
    moses=definitions.loc[definitions.gate_id.eq('moses_south')].copy()
    pvdefs=definitions.loc[definitions.circuit_id.astype(str).eq('PV20')].copy()
    assert len(moses)==21 and len(pvdefs)==6 and pvdefs.source_zone_direction.eq('D -> N').all()
    assert moses.groupby('edition').size().eq(7).all()
    moses.to_csv(OUT/'physical_Moses_seasonal_terms.csv',index=False,lineterminator='\n')
    pvdefs.to_csv(OUT/'PV20_official_2025_boundary_memberships.csv',index=False,lineterminator='\n')
    for rel,h in pd.concat([moses,pvdefs])[['source_pdf','source_pdf_sha256']].drop_duplicates().itertuples(index=False,name=None):
        assert sha(read(ROOT/rel))==h

    pvarray=pd.read_csv(read(OUT/'PV20_hourly_source.csv'))
    pvreview=json.loads(read(OUT/'PV20_source_receipt.json').read_text())
    eia=pd.read_csv(read(ROOT/'output/nygrid_2025_western_audit/boundary_actuals/hourly_regional_actuals.csv'))
    assert np.array_equal(pvarray.timestamp_utc,eia.timestamp_utc) and len(pvarray)==8760
    q=pvarray.current_and_PV20_qualified.to_numpy(bool)
    assert q.sum()==8651 and np.array_equal(q,pvarray.qualified.to_numpy(bool))
    disagg=pvarray[['hour_index','timestamp_utc','current_and_PV20_qualified']].copy()
    disagg['ISO_NE_total_actual_import_MW']=eia.ISONE_actual_import_mw
    disagg['PV20_SandBar_import_proxy_MW']=pvarray.PV20_SandBar_import_to_NY_proxy_MW
    disagg['ISO_NE_non_PV20_import_target_MW']=disagg.ISO_NE_total_actual_import_MW-disagg.PV20_SandBar_import_proxy_MW
    disagg['conservation_error_MW']=disagg.ISO_NE_total_actual_import_MW-disagg.PV20_SandBar_import_proxy_MW-disagg.ISO_NE_non_PV20_import_target_MW
    assert np.max(abs(disagg.conservation_error_MW[q]))<1e-10
    disagg.to_csv(OUT/'ISO_NE_PV20_disaggregation_contract.csv',index=False,lineterminator='\n')

    model=loadmat(read(ROOT/'output/nygrid_2025_physical_repair/model/latest_model.mat'),simplify_cells=True)['model']
    model_states=[]
    for si,(template,static)in enumerate(zip(model['templates'],model['loss_static']),1):
        parent=np.asarray(static['parent'],int)
        crossing=np.flatnonzero((np.asarray(static['parent_from'])==4)^(np.asarray(static['parent_to'])==4))+1
        active=sorted(map(int,set(parent[template['branch'][:,10]>0])&set(crossing)))
        assert active==[46,51,52]
        bg=dict(zip(template['bus'][:,0].astype(int),np.asarray(static['bus_group'],int)))
        d_buses=sorted(int(k) for k,v in bg.items()if v==4)
        assert d_buses==[48,49]
        assert bg[49]==4 and int(static['HQ'])==1464 and template['gen'][1463,0]==48
        transfer=template['dcline'];cross=[i+1 for i,r in enumerate(transfer)if r[2]>0 and((bg[int(r[0])]==4)^(bg[int(r[1])]==4))]
        assert cross==[5,6]
        model_states.append(dict(state_index=si,D_model_bus_ids=d_buses,active_D_AC_cut_parents=active,
            prescribed_D_transfer_rows=cross,PV20_external_path_present_in_baseline=False,
            Plattsburgh_model_bus49_kV=float(template['bus'][template['bus'][:,0]==49,9].item())))

    source_specs=[
      ('MS24','output/nygrid_2025_flowgate_definitions/sources/central_north/NYISO_MS24_20240718.pdf','https://www.nyiso.com/documents/20142/1411640/MS-24-StabReport-OC-07-18-2024-Approved.pdf/1c512118-6ef0-2092-5653-2f2807d3e380',[7,10,12]),
      ('Summer25','output/nygrid_2025_flowgate_definitions/sources/central_north/NYISO_Summer2025_OperatingStudy_APPROVED.pdf','https://www.nyiso.com/documents/20142/3691300/Summer2025-OperatingStudy-APPROVED.pdf/3aaa5eb6-9fa4-53b5-181a-189e3ac52fcb',[16,19]),
      ('PAR27','output/nygrid_2025_par_controls/sources/direction/NYISO_ParFlowDiagrams27.pdf','https://www.nyiso.com/documents/20142/2268519/ParFlowDiagrams27.pdf/7bd78df8-311c-0b29-fa3f-ba0c8a51d123',[7,8,26]),
      ('EIA930','output/nygrid_2025_western_audit/boundary_actuals/raw/EIA930_instructions.pdf','https://www.eia.gov/survey/form/eia_930/instructions.pdf',[3,5,7]),
    ]
    source_registry=[]
    for sid,rel,url,pages in source_specs:
        path=read(ROOT/rel);source_registry.append(dict(source_id=sid,path=rel,sha256=sha(path),url=url,pages_1based=pages))
    for file in ['NYPA_HA1_in_service_20260330.pdf','NYPA_HA2_in_service_20251014.pdf','NYPA_MH1_in_service_20260416.pdf',
                 'NYISO_transfer_limitations_20251022.pdf','VELCO_OC_minutes_SandBar_failure_20210318.pdf',
                 'ISONE_OP17A_boundaries_current.pdf','ISONE_weekly_20251116.pdf','VEC2025_IRP_section4_SouthHero.pdf',
                 'DPS_21_T_0340_public_documents.json','NYPA_Smart_Path_Connect_current.html']:
        path=read(SOURCES/file);receipt=json.loads(read(path.with_suffix(path.suffix+'.receipt.json')).read_text())
        assert receipt['sha256']==sha(path)
        source_registry.append(dict(source_id=file.rsplit('.',1)[0],path=path.relative_to(ROOT).as_posix(),sha256=sha(path),url=receipt['url']))
    for sid,path in [
        ('2025seasonaldefinitionCSV',ROOT/'output/nygrid_2025_flowgate_definitions/definitions/all_seasonal_members.csv'),
        ('baseline_model',ROOT/'output/nygrid_2025_physical_repair/model/latest_model.mat'),
        ('previousboundarysourceaudit',ROOT/'output/nygrid_2025_moses_source_diagnosis/boundary/boundary_audit_receipt.json'),
        ('PV20_source_receipt.json',OUT/'PV20_source_receipt.json'),
        ('ISO_NE_PV20_disaggregation_contract.csv',OUT/'ISO_NE_PV20_disaggregation_contract.csv')]:
        source_registry.append(dict(source_id=sid,path=read(path).relative_to(ROOT).as_posix(),sha256=sha(path)))
    source_registry.append(dict(source_id='NYISO_NX19_2020_indexed_table5A',
        url='https://www.nyiso.com/documents/20142/7321461/Northern-Export-and-Cedars-Import-Stability-Limit-Report-Final-OC-Approved.pdf/12e2c04a-1243-d6e3-5e88-018d083de111',
        reviewed_utc_date='2026-10-15',source_section='Printed page 9, interface summary and Table 5A',
        retrieval_status='Primary document search-index text inspected; direct PDF access showed a JavaScript/robot challenge. No bypass attempted.',
        local_PDF_available=False,source_bytes_sha256=None))

    bindings=[]
    def bind(key,status,statement,source,limitation=''):
        assert status in ['verified','assumed','unresolved']
        bindings.append(dict(binding_id=key,status=status,statement=statement,source_ids=source,limitation=limitation))
    bind('physical_Moses_definition', 'verified', 'Official 2025 seasonal tables identify seven Moses South circuit entries, North Zone D to Mohawk Valley Zone E, with starred meter ends.', '2025seasonaldefinitionCSV;MS24p7', 'Operational P32 expressions and change hours are not supplied by these tables.')
    bind('PV20_additional_D_boundary', 'verified', 'PV20 Plattsburgh-Sand Bar 115 kV is an additional North Zone D to ISO-NE Zone N path. It belongs to Central East and Total East, but not to the seven-term Moses South list.', '2025seasonaldefinitionCSV;MS24p12', 'Physical boundary existence is established; exact Plattsburgh hourly meter data are not.')
    bind('North_NYCA_pocket_components', 'verified', 'NYISO MS24 Figure 2 shows North NYCA connections to HQ 7040, Cedars, Ontario PAR33/34, PV20 ISO-NE, and the seven Moses South paths to Main NYCA.', 'MS24p12', 'The schematic is not a bus-by-bus source/load census or operational switching history.')
    bind('MMS_internal_scope', 'verified', 'MS24 Table 3 identifies MMS1/MMS2 as Massena-Moses connections. Both stations are northern source ends in the 2025 D-to-E definition, making these links internal to the illustrated North NYCA pocket.', 'MS24p10;2025seasonaldefinitionCSV', 'This inference uses documented endpoints and pocket topology. No model circuit identity or MMS flow is invented.')
    bind('NX2020_distinct_boundary', 'verified', 'The 2020 Northern Export definition adds MMS1, MMS2, L33P, L34P and PV20, and subtracts MSU1, relative to Moses South. It studies a distinct boundary with local North Country generation and zero external imports.', 'NYISO_NX19_2020_indexed_table5A', 'Primary search-index text only; direct PDF retrieval encountered a JavaScript/robot challenge. The 2020 formula is not promoted to 2025 P32 weights or net Zone D accounting.')
    bind('HQ_full_physical_aggregate', 'verified', 'The HQ input is NYIS-HQT EIA930 net physical interchange counted once, import positive. The 2025 study identifies 7040 Chateauguay-Massena and Dennison/Cedars paths.', 'EIA930;Summer25p19', 'The EIA aggregate does not separately measure Cedars and 7040. Merchant schedules must not be added again.')
    bind('HQ_inside_northern_pocket', 'assumed', 'Treat all 2025 NYIS-HQT physical interchange as entering the North NYCA pocket, consistent with the 2025 named links and MS24 Figure 2. Retain its net aggregate for pocket balance.', 'MS24p12;Summer25p19', 'Collapse at bus 48 is an engineering representation. The bus-level split and meter-end losses remain unverified.')
    bind('HQ_wheeling_no_subtraction', 'verified', 'Summer25 distinguishes 7040 NYCA delivery of 1310 MW from 1800 MW total including wheeling. EIA records physical flow; wheeling must not be subtracted from HQT physical imports merely because its final destination is another BA.', 'EIA930;Summer25p19', 'Limits provide context, not hourly telemetry or a numerical wheeling correction.')
    bind('Ontario_PAR_current_inputs', 'verified', 'P34 inputs 25118/25119 have official positive Ontario-to-NY direction effective 2024-12-03 and reproducible 2025 hourly actuals. Preserve these values.', 'PAR27p7,p26;previousboundarysourceaudit', 'An active-flow series does not resolve PAR reactive power, taps or losses.')
    bind('PV20_P34_identity', 'verified', 'Native 2025 P34 archives contain PTID325270, labeled Sand Bar PAR PS01 on PV20 in the official diagram. The 105998 records provide 8673 fully covered hours, including all 8651 current qualified hours.', 'PAR27p8;PV20_source_receipt.json', 'This is a Sand Bar meter, not the Plattsburgh physical gate meter.')
    bind('PV20_current_sign', 'verified', 'The official PAR27 page 8 cyan plus arrow points from Sand Bar ISO-NE toward South Hero and Plattsburgh NYISO. The current raw sign is import positive to NY.', 'PAR27p8,p26', 'No P32 fitting or residual-based sign choice is used.')
    bind('PV20_2025_sign_continuity', 'assumed', 'Use the current official Sand Bar sign for 2025.', 'PAR27p8', 'Page 8 has no dated 2025 effective note. A historical operator-sign record is needed to certify all 2025 sign semantics.')
    bind('PV20_meter_end_gap', 'verified', 'The physical PV20 gate is metered at Plattsburgh. The P34 diagram places the Sand Bar PAR beyond South Hero. ISO-NE OP17 Appendix A identifies PV20-2 Plattsburgh-South Hero as the Vermont boundary.', '2025seasonaldefinitionCSV;PAR27p8;ISONE_OP17A_boundaries_current', 'Sand Bar PAR flow cannot silently be equated to Plattsburgh flow.')
    bind('SouthHero_load_exists', 'verified', 'VELCO 2021 OC minutes describe VEC load at South Hero. VEC 2025 IRP page 71 gives a 6.66 MVA 2025 planning peak for feeder South Hero 29-1A.', 'VELCO_OC_minutes_SandBar_failure_20210318;VEC2025_IRP_section4_SouthHero', 'This single-feeder planning value is not an hourly net-load series or a complete bound on meter error.')
    bind('PV20_proxy_approximation', 'assumed', 'At existing aggregate Plattsburgh bus 49, use fixed P equal to the Sand Bar import proxy and Q=0. No Sand Bar bus or AC line is invented. South Hero net injection, segment losses and bypass contributions are omitted in this engineering approximation.', 'PV20_source_receipt.json;baseline_model', 'The omission does not claim those physical terms are zero or establish reactive, thermal or physical meter equivalence.')
    bind('ISO_NE_no_double_count', 'verified', 'Each hour must satisfy ISO_NE_total_import = PV20_proxy_import + ISO_NE_nonPV20_import_target. Pair the new Zone D proxy with the opposite redistribution of the ISO-NE pool/target, preserving the reported BA aggregate.', 'EIA930;ISO_NE_PV20_disaggregation_contract.csv', 'Existing NNC/CSC disaggregation still applies to the remaining pool. Do not add or subtract PV20 twice.')
    bind('HA2_energization', 'verified', 'NYPA formal PSC filing dated 2025-10-14 states HA2 was energized on 2025-10-13.', 'NYPA_HA2_in_service_20251014', 'No energization hour or P32 meter-switch timestamp is provided.')
    bind('HA1_energization', 'verified', 'NYPA formal PSC filing dated 2026-03-30 states HA1 was energized on 2026-03-27.', 'NYPA_HA1_in_service_20260330', 'The winter 2025-26 planning definition does not establish HA1 operation in 2025.')
    bind('2025_gate_switching_history', 'unresolved', 'Exact 2025 P32 weights, the MA2-to-HA2 meter-change hour and intermediate bypass topology are not supplied by seasonal tables or energization dates.', 'NYPA_HA2_in_service_20251014;NYPA_HA1_in_service_20260330;2025seasonaldefinitionCSV', 'Do not switch both lines at a seasonal publication date. Distinguish documentary dates from measurement-effective intervals.')
    bind('physical_D_injection_census', 'unresolved', 'A complete dated crosswalk does not yet certify every load, generator and allocated model loss inside the exact physical North NYCA meter boundary.', 'baseline_model;MS24p12', 'The aggregate component diagram supports candidate scope, not complete injection equivalence.')
    bind('physical_to_model_loss_operator', 'unresolved', 'Physical Moses meters combine northern from ends with the Colton target end. Their exact correspondence to model parents 46/51/52 and the signed terminal correction remains unverified.', '2025seasonaldefinitionCSV;baseline_model', 'Do not assign a physical circuit ID to an aggregate parent solely by name or voltage.')
    bind('whole_physical_meter_certificate', 'unresolved', 'PV20 repairs a source-supported missing external component. Exact 2025 public Moses South meter equivalence remains unverified.', 'allbindings', 'Missing evidence: dated P32 weights/switching history, Plattsburgh PV20 flow or South Hero net-load/loss/bypass data, and a complete pocket load/generator/loss mapping.')
    pd.DataFrame(bindings).to_csv(OUT/'source_binding_ledger.csv',index=False,lineterminator='\n')

    chronology=pd.DataFrame([
      dict(element='HA2',event='energized',local_calendar_date='2025-10-13',notification_date='2025-10-14',hour_verified=False,P32_effective_hour_verified=False,source='NYPA_HA2_in_service_20251014.pdf'),
      dict(element='HA1',event='energized',local_calendar_date='2026-03-27',notification_date='2026-03-30',hour_verified=False,P32_effective_hour_verified=False,source='NYPA_HA1_in_service_20260330.pdf'),
      dict(element='MH1',event='energized',local_calendar_date='2026-04-13',notification_date='2026-04-16',hour_verified=False,P32_effective_hour_verified=False,source='NYPA_MH1_in_service_20260416.pdf')])
    chronology.to_csv(OUT/'actual_energization_chronology.csv',index=False,lineterminator='\n')
    certificate=dict(status='source_supported_PV20_missing_component_and_conditional_aggregate_repair_contract',
        created_utc=datetime.now(timezone.utc).isoformat(),source_bindings=bindings,source_registry=source_registry,
        documentary_North_NYCA_component_scope_verified=True,specific_missing_external_component='PV20 Plattsburgh-Sand Bar',
        whole_2025_physical_Moses_meter_equivalence_verified=False,source_sign_or_meter_end_fitted_to_P32=False,
        current_PV20_direction_verified=True,historical_2025_PV20_sign_continuity_assumed=True,
        baseline_model_state_checks=model_states,current_qualified_hours=8651,PV20_additional_exclusions=0,
        conditional_physical_balance='Moses_DtoE_meter = G_D - served_D_load - internal_D_real_losses + HQ_import + Ontario_PAR_import + PV20_Platt_import + meter_end_loss_adjustment',
        SandBar_to_Platt_identity='PV20_Platt_import = P34_SandBar_toward_Platt - SouthHero_net_load - intervening_real_losses + unmetered_bypass_or_parallel_transfer',
        model_candidate='Fixed active boundary injection at aggregate Plattsburgh bus 49; Q=0 assumed; matching ISO-NE pool/target adjustment. No invented AC impedance, conductor, tap angle, physical ISO-NE bus or physical circuit identity.',
        region_disaggregation_max_abs_error_MW=float(np.max(abs(disagg.conservation_error_MW[q]))),
        full_PV20_meter_error_numeric_bound_MW=None,
        partial_uncertainty_context=dict(SouthHero29_1A_2025_planning_peak_MVA=6.66,
            is_total_substation_hourly_netload_or_full_meter_error_bound=False,
            source='VEC2025IRPSection4page71',source_recorded_P34_native_range_MW=[-167.9,11.1]),
        physical_staggered_upgrade_dates_verified=True,P32_switch_timestamps_verified=False,
        source_quality_policy='Keep all 8760 physical UTC rows; require full native coverage; carry existing 8651-hour qualification; no imputation or promotion of additional hours.',
        operator_change_permitted_by_this_certificate='Add an explicit PV20 aggregate boundary proxy with documented assumptions; do not rename it a verified physical P32 operator.',
        default_model_changed=False,new_AC_power_flows=0,
        sources_preserved=all(sha(ROOT/p)==h for p,h in DEPS.items()),
        input_manifest=[dict(path=p,sha256=h)for p,h in DEPS.items()],script_sha256=sha(Path(__file__)))
    assert certificate['sources_preserved']
    (OUT/'boundary_verification_receipt.json').write_text(json.dumps(certificate,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:certificate[k]for k in ['status','documentary_North_NYCA_component_scope_verified','whole_2025_physical_Moses_meter_equivalence_verified','specific_missing_external_component','region_disaggregation_max_abs_error_MW','current_qualified_hours']},indent=2))


if __name__=='__main__':main()
