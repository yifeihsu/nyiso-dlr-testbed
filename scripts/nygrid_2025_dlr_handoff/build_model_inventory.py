"""Read-only model/provenance inventory for a colleague DLR handoff.

Writes only the new handoff namespace. Reads saved evidence; runs no PF/OPF.
"""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess
import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/nygrid_2025_dlr_handoff'
BASE='8188cbec1172219a0414881121ad042b405a4044'


def record(path):
    with path.open('rb') as f:h=hashlib.file_digest(f,'sha256').hexdigest()
    return dict(path=path.relative_to(ROOT).as_posix(),sha256=h,bytes=path.stat().st_size)


def main():
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()==BASE
    branch=subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip()
    assert branch=='codex/s13-phase1b-upny-coned'
    OUT.mkdir(parents=True,exist_ok=True);sources={};source_overrides=[]
    def evidence(path,needle=None,span=2):
        p=ROOT/path;original=path;extra={}
        if path=='NYGRID_2025_WESTERN_SOURCE_AUDIT.md':
            committed=subprocess.check_output(['git','show',BASE+':'+path],cwd=ROOT)
            snapshot=OUT/'sources'/'NYGRID_2025_WESTERN_SOURCE_AUDIT_committed_8188cbec.md'
            snapshot.parent.mkdir(exist_ok=True)
            if snapshot.exists():assert snapshot.read_bytes()==committed
            else:snapshot.write_bytes(committed)
            if not source_overrides:
                source_overrides.append(dict(original_repository_path=path,committed_snapshot_commit=BASE,
                    snapshot=record(snapshot),working_copy_sha256_preserved=record(p)['sha256'],
                    reason='An unrelated working-copy annotation is preserved. The handoff binds the committed report, matching the packaged root report.'))
            p=snapshot;path=snapshot.relative_to(ROOT).as_posix();extra=dict(original_repository_path=original,source_snapshot_commit=BASE)
        lines=p.read_text(encoding='utf-8-sig').splitlines();sources[path]=record(p)
        i=0 if needle is None else next(i for i,s in enumerate(lines) if needle in s)
        return dict(path=path,line_start=i+1,line_end=min(len(lines),i+span),excerpt='\n'.join(lines[i:i+span]),**extra)
    def load(path,**kw):
        p=ROOT/path;sources[path]=record(p);return loadmat(p,simplify_cells=True,**kw)
    def read(path):
        p=ROOT/path;sources[path]=record(p);return json.loads(p.read_text(encoding='utf-8-sig'))
    def stage(id,title,counts,change,status,report,needle=None,**extra):
        return dict(id=id,title=title,counts=counts,major_change=change,scientific_status=status,evidence=[evidence(report,needle,4)],**extra)
    familyA=[
        stage('s7_structural','Separate NPCC/S7 structural provenance',dict(buses=143,branches=246,generators=62,baseMVA=100),
              'Original local233-branch NPCC plus S4 delivery/capability assumptions and direct PERFORM corridor parameters.',
              'Structural/historical baseline; not a certified operating case. Do not substitute its bus/zone roles or fitted priors into the Cornell NYgrid branch.',
              'PROJECT_HANDOFF.md','The S7 structural provenance case',lineage='local_ENLITEN_NPCC_to_S7'),
        stage('s13_checkpoints','Preserved S13-FULL construction checkpoints',dict(phase1a_buses=147,phase1a_branches=253,phase1b_buses=149,phase1b_branches=262,generators=62),
              'Source-backed physical corridor overlays with provenance/overlap registers; cumulative construction preserves full-NPCC identities.',
              'Historical construction/validation parent; no DLR promotion follows from structural or local identity checks.',
              'PROJECT_HANDOFF.md','The current cumulative Phase 1B checkpoint'),
        stage('s11_s12_s14','S11 diagnostic, S12 oracle and unpromoted S14 roles',dict(S11_buses=49,S12_buses=317,S12_branches=3531,S12_generators=615,S14_external_reduction_diagnostic_buses=86),
              'Reduced diagnostics and a PERFORM comparison oracle. The named S14-NYISO promoted operating model remains pending; an86-bus S14-labelled diagnostic is a different artifact.',
              'Do not use S12 dense equivalent branches as physical construction inputs or treat an S14-named diagnostic as a promoted DLR model.',
              'PROJECT_HANDOFF.md','### 1.1 Governing model hierarchy'),
        stage('historical_ny_only','Separate51/66/71-bus NY-only research families',dict(compact2019_buses=51,calibrated2025_buses=66,source_generation2025_buses=66,partial_SPC2025_buses=71,partial_SPC_branch_records=135,partial_SPC_active_branches=117,partial_SPC_generators=37),
              'Historical NY-only boundary-equivalent studies, an interface-fitted66-bus baseline, source-generation alternative, and71-bus year-end partial-SPC synthetic DLR study.',
              'Preserved historical experiments. Their snapshots, gamma, optimization policy and thermal proofs do not transfer to the current148-bus NYgrid replay.',
              'PROJECT_HANDOFF.md','Preferred preliminary model',legacy_latest_csv_is_not_current_nygrid_selector=True),
        stage('phase1c_external_diagnostic','Historical Phase 1C and external reduction',dict(phase1c_buses=170,phase1c_branches=315,inherited_generators=62,reduced_buses=86,reduced_branches=182,eliminated_external_buses=84),
              'Adds source terminals and electrical elements, then tests a separate external reduction and bounded reconstruction workflow.',
              '130 implementation checks passed, but all six bounded reconstruction attempts failed. Same-state reduction identity is not operating qualification or DLR readiness.',
              'ELECTRICAL_MODEL_IMPLEMENTATION.md','The verified run passes'),
        stage('package_a_reference','Package A historical NY-only foundation',dict(immutable_source_buses=1576,immutable_source_branches=2371,immutable_source_generator_records=615,fixed_boundary_PQ_proxies=20),
              'Qualifies one assumed 2019 PERFORM reference using fixed NY-side boundary injections, bounded prior-based reconstruction and independent PF; retains a declared Marcy Q-only support assumption.',
              'One historical electrical reference, not contemporary coverage, physical thermal qualification or a promoted S14 case.',
              'output/ny_only_package_a/NY_ONLY_FOUNDATION_RESULTS.md','Electrical qualification'),
        stage('package_b_reference','Package B historical regional replacement',dict(buses=878,branches=1375,generator_records=595,source_D_to_K_buses=855,retained_NPCC_A_to_C_buses=23),
              'Replaces regional network and device functions with explicitly mapped PERFORM source records while preserving zone demand and fixed boundary schedules.',
              'One bounded historical AC candidate with fresh PF replay; optional reference, not the preferred compact testbed or current NYgrid model.',
              'NY_ONLY_PACKAGE_B_IMPLEMENTATION.md','Package B replaces')]
    stages=[
        stage('paper_reproduction','Pinned Cornell NYgrid2019 reproduction',dict(raw_buses=140,raw_branches=227,raw_generators=48,released_modified_branches=226,paper_reduced_buses=57,paper_reduced_branches=94,generators=271,DC_records=4,hour_labels=8760),
              'Pinned author commit47698b6c7823ae7b1bc6935e5601d5b64b8f918e; release removes3remote ties, adds38-77 and43-38 E-G aggregates, then substitutes one AC row with4controlled DC records. Five of seven plotting expressions had wrong branch indices; measurement repair leaves the solved network unchanged.',
              'Retrospective DC reproduction. Original227-versus-paper/local233-branch discrepancy remains.2019hour labels use author preparation, not the later2025physical UTC/DST axis.',
              'NYGRID_2019_INTERFACE_VERIFICATION.md','The released'),
        stage('full_2019','Unreduced full2019 DC counterpart and first thermal exposure',dict(buses=140,AC_branch_records=225,generators=271,DC_records=4,prepared_hours=8760,structural_DLR_candidates=39),
              'Restores the unreduced author-derived network, registers raw/modified/reduced branch lineage, and creates first explicitly synthetic fixed-dispatch thermal screens.',
              'DC and declared exposure-method use; not bounded AC, installed ampacity, observed weather or economic DLR-benefit validation.',
              'NYGRID_2019_DLR_REBUILD.md','**Verified'),
        stage('historical_comparison','Separate compact2019 comparison and western diagnostic studies',dict(historical_compact_buses=51,branch_records=94,active_branches=89,NY_only_reference_buses=46),
              'Tests source-role/operator crosswalk and NY-side boundary accounting on the older compact family; diagnoses shared Dysinger/WestCentral errors and verifies raw2019load preparation.',
              'Historical cross-family diagnostic, not an ancestor that replaces the present full-NPCC NYgrid case; selected snapshots are retrospective, not holdouts.',
              'NYGRID_COMPACT_2019_COMPARISON.md','**The matched-2019 experiment'),
        stage('inputs_2025','2025source and clock reconstruction',dict(original_buses=140,physical_hour_positions=8760,NY_zones=11,combined_operating_source_qualified_hours=8673),
              'Builds P58load, generation priors and external schedules on a UTC physical-hour axis with source-quality masks. Scales aggregate public powers once by gamma=0.30012075175285535.',
              'Input struct only; not yet a balanced MATPOWER case. Missingness, assumptions and imputed/source-quality status remain explicit.',
              'NYGRID_2025_OPERATING_INPUTS.md','## Scale and accounting'),
        stage('bounded_dispatch','2025fleet mapping and bounded DC dispatch',dict(buses=140,AC_branch_records=225,DC_records=4,fleet_inventory_identities=2245,native_generator_rows=1436,external_plus_HQ_rows=28,total_generator_rows=1464,qualified_hours=8663,gap_hours=97),
              'Maps unique EIA identities and source-derived priors to retained proxies, then projects hourly PG into finite active-power bounds to close lossless DC balance without load shedding/free generation.',
              'Hourly average reconstruction; not observed unit dispatch, commitment, ramps, reserves, hydro/storage energy or AC/thermal feasibility.',
              'NYGRID_2025_BOUNDED_DISPATCH.md','The requested operating-model stage'),
        stage('downstate_191','Detailed Downstate construction on all140original buses',dict(buses=191,added_station_terminals=51,branch_records=410,historical_PERFORM_circuits=97,year_end_core_active_AC_branches=336,generators=1464,DC_records=4),
              'Adds38historical-source and13project/plant/proxy terminals; registers replacements for9old aggregates; includes dated RCC/Dover states and separate NYES/asset-placement diagnostics.',
              'DC construction with many explicit attachments/project assumptions.97historical circuits are source detail, not97newly constructed lines. Default retains original injection landings.',
              'NYGRID_2025_DOWNSTATE_REFINEMENT.md','## What was constructed'),
        stage('slim_148_dc','148-bus DC alternative',dict(buses=148,original_buses=140,retained_additions=8,NY_buses=54,external_buses=94,eliminated_added_buses=43,branch_records=274,derived_DC_equivalent_edges=30,year_end_active_branch_records_before_PAR_substitution=265),
              'Keeps the eight named345kV transmission ports and eliminates only43zero-injection added nodes using DC Schur/affine recovery. Retains all225original branch records in provenance.',
              'Exact tested DC response; equivalent R/B/rating zeros are placeholders. It is not a physical conductor network or a usable AC model merely because MATPOWER accepts it.',
              'NYGRID_2025_SLIM_DOWNSTATE.md','**Completed'),
        stage('moses_repair','Moses hydro-zone correction',dict(corrected_plants=26,admitted_rows_relocated=46,qualified_hours=8663),
              'Moves explicitly documented hydro sites from incorrect county-based ZoneD to ZoneE, preserving their PG and bounds.',
              'Source-backed placement repair; substantial residual remains. Initial Ontario-sign/control alternatives remained diagnostics until separate documentary confirmation.',
              'NYGRID_2025_MOSES_SOUTH_DIAGNOSIS.md','The versioned correction'),
        stage('ontario_PAR','Direction-qualified PS33/PS34 controls',dict(retained_buses=148,fixed_transfer_records=6,physical_HVDC_containers_original=4,additional_PAR_transfer_equivalents=2,nominal_MVA_per_replacement_PAR=300),
              'Replaces aggregate branch211 electrically with two separate lossless controlled transfers from Ontario to Moses; keeps211inactive as provenance. Positive reportedflow direction applies from2024-12-03.',
              'External P34conditioned DC reconstruction, not physical tap telemetry or fullP/Q/thermal limits. Two extra dcline records are PAR equivalents, not two newHVDC assets.',
              'NYGRID_2025_VERIFIED_PAR_CONTROLS.md','The official NYISO diagram'),
        stage('western_inputs','Confirmed western placement repairs and actual regional exchanges',dict(inventory_rows_corrected=40,admitted_rows_changed=36,western_admitted_bus_moves=35,combined_generator_landings_different_from_raw_template=81,source_qualified_hours=8651,source_excluded_hours=109),
              'Adds eight site-zone corrections and Lewiston project-voltage landing; adopts NYIS EIA930 bilateral actuals consistently for ISONE/Ontario/PJM/HQ and reprojects the same bounded native priors. Earlier Moses corrections remain.',
              'Source-conditioned reconstruction. Individual unit output and within-region AC/DC partition are not observed. Counterparty reporting differences, storage accounting and western physical gates remain unresolved.',
              'NYGRID_2025_WESTERN_SOURCE_AUDIT.md','## Confirmed mapping corrections'),
        stage('western_tests','Controlled Niagara/load/operator counterfactuals',dict(fixed_cohort_hours=8651,PF_scenarios=16,scenario_hours=138416),
              'Separates Niagara monthly-energy/legacy-rule tests, within-zone load reshaping, and independent zone-cut operators with held-fixed controls.',
              'Diagnostic only; no alternative was promoted by a better interface score and the western residual is not uniquely assigned to mapping error.',
              'NYGRID_2025_WESTERN_CONTROLLED_TESTS.md','The controlled tests'),
        stage('physical_gates','Physical flowgate and P34 semantics audits',dict(seasonal_gate_definitions=21,printed_entries=269,interfaces=7,complete_physical_model_gate_mappings_verified=0),
              'Archives three seasonal editions, metered-end/source identities and model gaps. Separately qualifies P34direction, headerunits, nativecadence and signal origin without changing numerical conventions.',
              'Official definitions do not identify a complete2025model operator. Flow(MWH)→numeric-as-MW and forward-hold time semantics remain conditional; never introduce a factor12fromcadence alone.',
              'NYGRID_2025_PHYSICAL_FLOWGATE_DEFINITIONS.md','The source definitions'),
        stage('line_estimates','Applied F84 and Staten route-based parameter corrections',dict(retained_buses=148,retained_branch_records=274,detailed_buses=191,detailed_branch_records=410,changed_detailed_rows=[391,410],annual_scenarios=5,scenario_hours=43255),
              'Replaces F84aggregate-budget R/X/B with a conductor/geometry estimate and Staten cable9.2mi prior with9.4mi source route; preserves otherprojectpaths and97historical circuits. RecomputesDCreduction/recovery.',
              'Engineering estimates, not as-builtAC/thermal certification. F84energization wasJuly28,2019; missing-from-frozen2019doesnotmeanbuilt-after2019.',
              'NYGRID_2025_LINE_PARAMETER_ESTIMATION.md','This work traced'),
        stage('dover_controls','Dover two-bank device and phase-state model',dict(retained_buses=148,retained_branch_records=274,post_full_buses=192,post_full_branch_records=413,additional_regulated_port=1,parallel_PAR_banks=2,fixed_transfers_preserved=6,qualified_annual_hours=8651,qualified_post_cutover_hours=287,ambiguous_zero_hours=18,bounded_hours=49),
              'SeparatesY17, parallelT398-A/B banks and heterogeneous398line sections. Uses conditional leakage estimateX=.01873877796pu per750MVA bank on100MVA base; tracks externalP34targets with gamma*40degree modelbounds.',
              'Bank impedance/taps/bypass are not observed. Exacttracking is diagnostic. Two bank phase controls are inAC branches and do not add moredcline records.',
              'NYGRID_2025_DOVER_PARAMETERS_APPLIED.md','The post-cutover detailed reference'),
        stage('engineering_AC','Whole-system engineering AC and current-constrained DLR snapshots',dict(reference_parent_branches=413,active_in_any_source_state=339,inactive_reference_records=74,OH_corridors=186,OH_conductor_segments_before_numerical_split=187,cable_equivalent_rows=40,transformer_compatible_rows=38,mixed_voltage_composite_equivalents=65,OH_exact_RX=128,OH_RX_replacements=58,thermal_catalog_entries=14,numerical_added_buses=75),
              'Builds finiteR/X/B, conductor/cable/equipment metadata, current limits, Q/S capability proxies, numericalpi sections and declared75%reactors. Keeps the existing power scale and interprets ACcurrent directly.',
              'Fourofseven bounded electrical snapshots and fourofeight weather-constrained OPF/PFreplays qualified. Uniform syntheticweather and fixedreferenceR do not establish annual electrothermal operation or installed ratings.',
              'NYGRID_2025_AC_SYSTEM.md','The numerical qualification'),
        stage('profile_AC_audit','Unchanged-profile detailed ACPF and asset audit',dict(source_hours=8651,equation_profile_qualified_hours=8494,failed_NR_hours=157,physical_assumption_qualified_hours=0,additional_NR_recovery_attempts=314,recovered_failures=0,cable_like_parent_rows=40,OH_cable_conflict_rows=[300,309,310,386]),
              'Runs the frozen lossless operating profiles through detailedACPF; the first original reference generator supplies losses. Inventories cable evidence and every bus lineage.',
              'Numeric currents available for8494hours but zero jointV/Q/generator/converter qualification. FourOH/cableconflicts and65mixed-device interiors prevent physicalwhole-NYISO DLR claims.',
              'NYGRID_2025_ACPF_PROFILE_AUDIT.md','## Underground cables'),
        stage('compact_AC','Exact148-retained-bus complex-admittance AC solver',dict(retained_buses=148,pre_eliminated_nodes=118,post_eliminated_nodes=119,annual_attempts=8651,qualified_paired_hours=8494,new_successes=0,lost_successes=0,physical_assumption_qualified_hours=0),
              'Forms generalcomplexYred and exact voltage/current lift includingR,B,shunts,taps,phase. Retains all specified injections/controlports; automaticallypromotesnewports; fingerprints reject stale/edited operators.',
              'Exact validatedmatrix reduction, not physicalreduced edges; dedicatedPFonly. Numeric equivalence doesnotrepair calibration or operatingbounds;148isrequestedinterface not globallyminimal proof.',
              'NYGRID_2025_COMPACT_AC.md','The delivered model'),
        stage('CE_diagnosis','CentralEast model-change and loss diagnostics',dict(fixed_matched_hours=8494,annual_DCPF_variant_solves=33976,annual_loss_allocation_DCPF_solves=25482),
              'Separates DCnetwork-construction shift fromsame-networkAC effects; identifies224bypassX fallback as dominantDCrerouting and reconstructs effects of already-solved losses.',
              'After-the-fact diagnostics, not uniquephysicalcause or additiveWAPE attribution; no baseline tuning or production modification.',
              'NYGRID_2025_CENTRAL_EAST_DIAGNOSIS.md','The increase is'),
        stage('loss_revision','Latest source-equivalent and boundary-consistent148-bus ACPF',dict(source_eligible_hours=8651,qualified_hours=8170,paired_hours=8170,new_hours=0,old_successes_lost=324,rejected_source_hours=481,source_excluded_hours=109,solver_exceptions=0,physical_assumption_qualified_hours=0,representative_factorial_cases=56,common_factorial_hours=11),
              'Restores224completeR/X/B(.02,.0147,0) as explicitunvalidatednetworkequivalent and removesitsconductor/DLRclaims. SolvesACvoltageswithloss-dependentP/Q: NYgross=served+allocatedloss, externalfinitegenerators supplyregional/borderlosses, nativePG/HQ/6transfersfixed.',
              'CurrentPF-only syntheticaccountingresearchbaseline. No physical224impedance validation, no fulloperatingqualification, no integrated revisedDLROPFor temperaturecoupling. Extremezonal allocatedlossfractions remain.',
              'NYGRID_2025_AC_LOSS_REVISION.md','The versioned148' if False else 'The versioned 148-bus')]
    familyA[0]['evidence'].append(evidence('PROJECT_HANDOFF.md','The S7 structural provenance case',9))
    familyA[1]['evidence'] += [evidence('LATEST_MODEL_CONFIGURATION.csv','s13_phase1a,case_size',1),evidence('LATEST_MODEL_CONFIGURATION.csv','s13_phase1b,case_size',1)]
    familyA[2]['evidence'].append(evidence('LATEST_MODEL_CONFIGURATION.csv','reference_s12,case_size',1))
    familyA[3]['evidence'] += [evidence('COMPACT_NPCC_NY_TESTBED.md','The active direction',2),evidence('COMPACT_NY_2025_DLR_METHODOLOGY.md','The new preliminary model',2),evidence('COMPACT_NY_PARTIAL_SPC_BASELINE.md','This separate variant',2)]
    familyA[4]['evidence'].append(evidence('LATEST_MODEL_CONFIGURATION.csv','s13_phase1c,case_size',1))
    stages[0]['evidence'].append(evidence('NYGRID_2019_DLR_REBUILD.md','| Downloaded',8))
    stages[4]['evidence'].append(evidence('NYGRID_2025_BOUNDED_DISPATCH.md','The final case contains',6))
    stages[5]['evidence'].append(evidence('NYGRID_2025_DOWNSTATE_REFINEMENT.md','The expansion adds',9))
    stages[6]['evidence'].append(evidence('NYGRID_2025_SLIM_DOWNSTATE.md','## Eight retained additions',18))
    stages[14]['evidence'].append(evidence('NYGRID_2025_AC_SYSTEM.md','| Reference-model class',14))
    snapshots=[]
    for hour in [1,3360,3576,8472,8508]:
        c=load(f'output/nygrid_2025_compact_ac/models/compact_ac_h{hour:04d}.mat')['model'];m=c['detailed_mpc']
        proof=load(f'output/nygrid_2025_ac_loss_revision/impedance/actual_case_checks/prepared_h{hour:04d}_numeric.mat')
        assert np.array_equal(proof['before_bus'],proof['after_bus']) and np.array_equal(proof['before_gen'],proof['after_gen'])
        snapshots.append(dict(hour_index=hour,full_buses=len(m['bus']),full_branch_records=len(m['branch']),active_branch_records=int(np.sum(m['branch'][:,10]>0)),
            real_generator_rows=len(m['gen']),controlled_transfer_records=len(m['dcline']),retained_buses=len(c['retained_bus_ids']),eliminated_buses=len(c['eliminated_full_rows']),
            prior_OH_segment_metadata_rows=len(proof['section_rows_before']),remaining_segment_metadata_rows_after224_exclusion=len(proof['section_rows_after']),
            remaining_unique_OH_electrical_rows_after224_exclusion=len(np.unique(proof['section_rows_after'])),
            remaining_metadata_is_not_physical_DLR_qualification=True))
    api_notes={
        'npcc_nygrid_2019_full_dc':'Historical unreduced2019DC; author-prepared local-hour labels.',
        'npcc_nygrid_2025_operating_inputs':'Input struct only; not a runnable case.',
        'npcc_nygrid_2025_full_dc':'Bounded2025DC on140-bus/225-branch parent.',
        'npcc_nygrid_2025_downstate_dc':'191-bus detailedDC; defaults upgrades_dated, retains source injection landings.',
        'npcc_nygrid_2025_slim_dc':'148-bus DC equivalent; defaults topology_dated.',
        'npcc_nygrid_2025_moses_corrected_dc':'Confirmed hydro-zone correction only.',
        'npcc_nygrid_2025_par_controlled_dc':'Adds two Ontario PAR transfer equivalents, total6dcline records.',
        'npcc_nygrid_2025_western_corrected_dc':'Corrected landing and all-boundary actuals; defaults combined.',
        'npcc_nygrid_2025_line_estimated_dc':'Adds source-informedF84/Staten engineering parameters; DC-only.',
        'npcc_nygrid_2025_dover_dc':'Final source-conditionedDC comparator; defaults bounded,x_nominal.',
        'npcc_nygrid_2025_slim_interfaces':'For a successfulDCresult only; evaluates the sealed affineinterfacefunctional.',
        'npcc_nygrid_2025_ac':'Earlier fullsyntheticengineeringAC constructor; does notapply thelatest224/lossrevision.',
        'run_nygrid_2025_ac_dlr':'Earlier full-network steady-ampacity ACOPF/PFreplay; syntheticweather/referenceR; differentcaseandoperatingpolicyfromlatestreplay.',
        'npcc_nygrid_2025_compact_ac':'Builds complexmatrixequivalent ofolderengineeringAC; do notpassmodelto genericrunpf.',
        'run_nygrid_2025_compact_acpf':'Earlier exact148-busPF; preservesPD/non-slackPG, originalreference supplieslosses.',
        'run_nygrid_2025_loss_consistent_acpf':'LatestPF-only148-bus sourceequivalent/loss-accounting replay; defaultreleased_equivalent,boundary_consistent,simultaneousNewton.'}
    apis=[]
    for name,note in api_notes.items():
        p=f'System Matpower Format/{name}.m';ref=evidence(p,None,18)
        apis.append(dict(name=name,signature=ref['excerpt'].splitlines()[0],role=note,evidence=[ref]))
    current=read('output/nygrid_2025_ac_loss_revision/summary/revision_summary.json')
    latest_ind=read('output/nygrid_2025_ac_loss_revision/impedance/released_equivalent_boundary_consistent_annual_arrays_independent_review.json')
    independent=read('output/nygrid_2025_ac_loss_revision/comparison/independent/final_scoring_independent_review.json')
    assert current['counts']['revised_qualified']==8170 and latest_ind['completed'] and independent['passed']
    manifests=[]
    for folder in sorted((ROOT/'output').glob('nygrid*')):
        if not folder.is_dir() or folder.name=='nygrid_2025_dlr_handoff':continue
        candidates=[p for p in folder.iterdir() if p.is_file() and p.name.lower() in ['delivery_manifest.json','upstream_manifest.json']]
        for p in candidates:
            d=json.loads(p.read_text(encoding='utf-8-sig'));rel=p.relative_to(ROOT).as_posix();sources[rel]=record(p)
            entries=d.get('files');count=len(entries) if isinstance(entries,(dict,list)) else entries if isinstance(entries,int) else None
            manifests.append(dict(path=rel,scope=d.get('scope',d.get('status')),declared_file_entries=count,sha256=sources[rel]['sha256']))
    cautions=[
        'Never select the current NYgrid model via the older genericLATEST_MODEL_CONFIGURATION.csv: its preferred71-bus entry belongs to another family.',
        '2019author-preparedlocal labels and2025UTC physicalhours are different time contracts despite both having8760positions.',
        'Usegamma0.30012075175285535 only for2025aggregatepublic/modelMW comparison; do not rescale per-unitR/X or divide ACcurrent by gamma. Historicalcompact2019usesadifferentgamma.',
        'Use exactbranch keys/parent rows/presence/status, not positionalpadding or arbitraryreducededges, for recoveredcurrent andinterface comparisons.',
        'Use series current forI-squared-R; terminalcurrent includes charging. Divide conductorphasecurrent by explicitparallelcircuit andbundlecounts. Voltage-changing/composite rows arenotdirectOHthermalconductors.',
        'P34 Flow(MWH), timing andsignal provenance remainconditional. No cadence-basedfactor12conversion, silentretiming, zero-fill or physicaltapclaim.',
        'Currentparent224isareleasedE-Gnetworkequivalent, notaninstalledGilboa-Buchanancircuit. R=.02isnotphysicallyvalidated; noIEEE738/R(T)/ampacityclaim for224.',
        'Rows300,309,310,386 haveOH/cableclassificationconflicts. Forty cable-likeequivalents and65mixed-voltagecomposites do notconstituteacompletephysicalcircuitinventory.',
        'Exactreductionrequirespassivezero-injectioninteriors. Retainnewload/generator/converter/voltage-controlports; rebuild afterR(T),B,shunts,status,tap,phaseorcontrol changes.',
        'PFconvergence, equation/recoveryclosure, profile/loss-accountingclosure, V/Q/generatorlimits andthermal/securityqualification areseparate gates.',
        'Neveraveragefailedlastiterates or silentlydropchangedcoverage. Old8494 andnew8170scores mustuseanexplicitpairedcohort; the324losthoursremainvisible.',
        'Currentlossallocationisdeclaredaccounting, notobservedzonal loss. ExtremeF/Efractions95.45%/94.52%andzerojointoperatingqualificationprecludephysicaldeploymentclaims.',
        'CurrentlatestPFAPIrejectsalreadyrevised/thermallypreparedinputs andremovesOPFcallbacks. Do notattacholdDLR/OPFconstraints and assume thecombinationwasvalidated.',
        'TheolderACDLRresultsused boundednativeOPFredispatch anduniformweather. Theirfourqualifyingpointsdonotcertify thelatestfixed-native-PGannualreplay.',
        'Noannualweather-driven/transienttemperature study, installedampacitycertificate, N-1securityproof, economicDLRsavings, unitcommitment/ramp/reservoirenergyqualification is established.'
    ]
    critical_evidence=[
        evidence('scripts/nygrid_2025_ac_loss_revision/core/ac_loss_prepare_case.m','if strcmp(mode',12),
        evidence('scripts/nygrid_2025_ac_loss_revision/core/ac_loss_prepare_case.m','terminal_current_constraints_applied=false',10),
        evidence('scripts/nygrid_2025_ac_loss_revision/core/ac_loss_finalize.m','policy_gate=',8),
        evidence('scripts/nygrid_2025_ac_loss_revision/core/ac_loss_finalize.m','VQ_and_generator_assumption_gate=',5),
        evidence('scripts/nygrid_2025_ac_system/thermal/ac_dlr_prepare_case.m','terminal_current_constraints_applied',4),
        evidence('scripts/nygrid_2025_ac_system/thermal/ac_dlr_apply_resistance.m','rows=unique',12),
        evidence('scripts/nygrid_2025_compact_ac/README.md','The model is a matrix network',4),
        evidence('NYGRID_2025_ACPF_PROFILE_AUDIT.md','four currently overhead-classified',4),
        evidence('NYGRID_2025_P34_QUALIFICATION_AND_DLR_READINESS.md','## Which DLR research claims are ready',10)]
    for p in [Path(__file__),Path(__file__).with_name('technical_outline_template.md')]:sources[p.relative_to(ROOT).as_posix()]=record(p)
    report=dict(passed=True,created_utc=datetime.now(timezone.utc).isoformat(),baseline_HEAD=BASE,branch=branch,
        scope='Read-only model-history, modification, publicAPI and DLR scientific-scope inventory; no new solver runs or priorfile edits',
        observed_evidence_status='Freshly inspected saved artifacts at the pinned handoffHEAD; numerical outcomes are preserved historical runs, not rerun in this inventory.',
        historical_S7_S13_S14_family=familyA,current_NYgrid_evolution=stages,exact_saved_dated_case_counts=snapshots,
        public_APIs=apis,latest_result_summary=current['counts'],latest_paired_annual_interfaces=current['paired_annual_interfaces'],
        latest_loss_fraction_warning=dict(maximum_fraction=latest_ind['maximum_qualified_NY_zonal_loss_fraction'],minimum_served_fraction=latest_ind['minimum_qualified_NY_zonal_served_fraction'],
            parent224_loss_ranges=latest_ind['equivalent224_qualified_loss_ranges'],physical_impedance_validated=False),
        current_DLR_decision=dict(latest_loss_consistent_148_case='Usable for conditionalPF/current-recovery/accounting experiments only; PF-onlyAPI andzerooperatingqualifiedannualhours.',
            older_full_engineering_DLR='ReproduciblesyntheticsteadyampacityOPFmethoddemonstrationatitsfourqualifiedweatherpoints, subjecttolaterassetclassificationcaveats; notthelatestlossrevision.',
            integrated_latest_DLR='Notdelivered:requires versionedeligible-branch/thermaladapterintegration, refreshedR(T)/admittancelift/currentconstraints andadequateoperatingstates.',
            physical_NYISO_wide_DLR='Notvalidated:incompleteassetidentity/gates, mixed-equivalentinteriors, cableconflicts andunobservedthermalconditions.'),
        next_research_gates=['Selectandfreezeelectricalmodel+powerbase+lossaccountingrolebeforecomparingDLRscenarios.',
            'QualifyOH/cable/transformer/equivalentidentities;exclude224andresolvefourOH/cableconflictsbeforephysicalweather-basedDLR.',
            'Choosefeasibleboundedoperatingstates anddocumentfailedhours;repairV/Qandcapabilityassumptions withoutusinginternalinterfaceerrorasatuningtarget.',
            'Bindroute-segmentweather withtime/height/direction/solaruncertainty;declarefixedR,steadytemperatureortransientthermalstate.',
            'RebuildcomplexACreductionwhentemperaturechangesR;checkphysicalseries/end/hardwarecurrents onrecoveredbranchaxes.',
            'Addafullyspecifiedredispatch/controlpolicyandcomparablestaticbaselinebeforeclaimingDLRbenefits;economics/securityrequiretheirownvalidation.'],
        pitfalls=cautions,critical_implementation_evidence=critical_evidence,delivery_manifest_index=manifests,
        committed_source_overrides=source_overrides,
        sources=list(sources.values()))
    (OUT/'model_and_modification_inventory.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    template=Path(__file__).with_name('technical_outline_template.md')
    outline=template.read_text(encoding='utf-8').replace('{{BASE_HEAD}}',BASE).replace('{{BRANCH}}',branch)
    (OUT/'proposed_technical_outline.md').write_text(outline,encoding='utf-8')
    print(json.dumps(dict(passed=True,model_stages=len(stages),separate_historical_roles=len(familyA),public_APIs=len(apis),dated_snapshots=len(snapshots),manifests=len(manifests),source_files=len(sources))))


if __name__=='__main__':main()
