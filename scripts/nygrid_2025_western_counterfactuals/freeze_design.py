"""Freeze source-defined experimental scope before the counterfactual scores."""
from datetime import datetime,timezone
from pathlib import Path
import subprocess
from common import OUT,PARENT,ROOT,atomic_json,load_baseline,read,record,require,sha

def freeze():
    target=OUT/'design/experiment_plan.json'
    require(not target.exists(),'Experimental plan already exists; do not silently revise it after seeing scores')
    b=load_baseline()
    files=[ROOT/e['path'] for e in read(PARENT/'delivery_manifest.json')['entries'] if e['path']!='.gitattributes']
    files.append(PARENT/'delivery_manifest.json')
    differences=[]
    for row in read(PARENT/'delivery_manifest.json')['entries']:
        if sha(ROOT/row['path'])!=row['sha256']:differences.append(row['path'])
    require(differences==['NYGRID_2025_WESTERN_SOURCE_AUDIT.md'],
            'Unexpected change in parent delivery beyond the observed user report annotation')
    snapshot=dict(created_utc=datetime.now(timezone.utc).isoformat(),
        preserved_parent_files=[record(p) for p in files],
        preexisting_parent_manifest_difference=differences,
        preexisting_report_note='User annotation CENTRAL EAST ? - VC is preserved; prior report is not regenerated.',
        gitattributes_may_receive_only_new_scope_rules=True)
    atomic_json(OUT/'design/preservation_snapshot.json',snapshot)
    plan=dict(created_utc=datetime.now(timezone.utc).isoformat(),
        branch=subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip(),
        head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        purpose='Matched 2025 source-defined diagnostic counterfactuals for Niagara generation, within-zone load allocation and interface operators.',
        fixed_hours=8651,fixed_hour_mask=record(PARENT/'replay/paired_common_mask.npy'),
        topology='dated commissioning states; exactly the baseline 148-bus model',
        fixed_boundaries='All28 external generator equivalents, original4DC schedules and2 observed P34 transfers stay exactly fixed.',
        primary_scoring='All primary scenarios use the exact8651mask; no observation-based exclusion. Infeasible literal hypotheses cannot be called full-cohort results.',
        Niagara=dict(targets=['legacy80percent_of_P63_hydro_minus_fixed_StLawrence',
                             'EIA_RMN_monthly_mean_times_baseline_hourly_shape',
                             'same_monthly_mean_with_hourly_capacity_feasible_shape'],
            fixed=['all_loads','StLawrence2694','all_pumped_storage_and_Lewiston2692','all_nonhydro_generation','all_boundaries'],
            primary_compensation='Other conventionalHY outside zonesA/B excludingStLawrence; preserve hourly statewideHY total and original unit bounds.',
            compensation_sensitivity='All other conventionalHY excludingStLawrence; distinguish this from the outsideA/B pool.',
            bounded_legacy='Explicit nearest-feasible projection of the requested hypothesis target; report all changes without modifying source data.',
            monthly_scope='Source EIA monthly energy divided by actual local-calendar physical hours defines a mean. Matching that mean on the fixed qualified cohort is conditional and does not claim full-month energy reconciliation.',
            feasibility='Report raw requested-target infeasibility, and month-level feasibility before scoring; no capacity relaxation.'),
        load=dict(candidates=['original_A','original_B','original_AB'],
            scope='Original npcc.csv versus released npcc_new.csv nonnegative bus load shares; preserve every zonalPD/QDtotal and all generation.',
            negative_and_null_controls='A shares are identical; A-only should be a no-op and AB should equal B-only.',
            extremal_test='A priori simplex bounds across retainedA/Bbuses demonstrate maximum operator response without fitting demand to observations.'),
        mapping=dict(candidates=['baseline_corrected_full191_operator','independent_zone_cuts','literal_released_plot_negative_control'],
            physical_alternative='Only evaluate an as-built physical gate if every member/sign/terminal maps independently. Incomplete coverage is a documented identifiability gap, never a zero-filled operator.',
            fixed='Identical flows/angles/injections for operator-only comparisons; no network parameter changes.'),
        analysis=dict(families='One factor at a time; fully crossed Niagara plus load cases only as algebraic interaction checks when load-cut invariance holds.',
            internal_observations='Read only in separate posthoc score command after all candidate definitions and input hashes are sealed.',
            outputs='All7interfaces, annual/monthly MW metrics/WAPE, matchedbaseline metrics per diagnostic mask, component deltas, feasibility and independent validation.',
            attribution='Changes measure sensitivity to declared hypotheses, not shares of true error. Residual after tests is not automatically assigned to interface mapping.'),
        constraints=dict(no_internal_flow_fitting=True,no_default_model_promotion=True,no_original_artifact_changes=True),
        dependencies=[record(p) for p in b['paths']]+[record(Path(__file__))])
    atomic_json(target,plan)
    print(target)

if __name__=='__main__':freeze()
