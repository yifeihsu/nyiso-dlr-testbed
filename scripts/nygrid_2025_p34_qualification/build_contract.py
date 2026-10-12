"""Bind the public-source P34 audit to the existing, unchanged DC reconstruction."""
import csv
import json
from qualification import ROOT, OUT, CONTRACT, sha, require


def main():
    source = OUT / 'sources/primary_evidence_conclusion.json'
    require(source.is_file(), 'Complete the primary source audit first')
    primary = json.loads(source.read_text())
    require(primary['passed'] and primary['audit_complete']
            and not primary['physical_unit_confirmed']
            and not primary['product_kind']['independent_metered_actual_confirmed']
            and primary['sign']['Ontario_StLawrence']['applies_to_2025']
            and not primary['sign']['Dover']['specific_2025_effective_date_confirmed'],
            'Primary qualification changed; review the evidence before rebuilding')
    # Preserve each evidence file rather than copying or rewriting old receipts.
    deps = [source, OUT / 'sources/primary_evidence_register.csv',
            OUT / 'sources/NYISO_PARdiagram_version1_0.pdf',
            OUT / 'sources/NYISO_OASIS_ParFlows_20251219.csv',
            ROOT / 'output/nygrid_2025_par_controls/controls/input_receipt.json',
            ROOT / 'output/nygrid_2025_dover_parameters/local_audit/Dover_P34_input_receipt.json',
            ROOT / 'output/nygrid_2025_dover_parameters/replay/replay_receipt.json',
            ROOT / 'output/nygrid_2025_dover_parameters/replay/operating_states.mat',
            ROOT / 'System Matpower Format/npcc_nygrid_2025_dover_dc.m']
    ontario = json.loads(deps[4].read_text())
    dover = json.loads(deps[5].read_text())
    replay = json.loads(deps[6].read_text())
    require(ontario['P34_direction_effective_date'] == '2024-12-03', 'Ontario sign evidence changed')
    require(dover['direction']['historical_2025_sign_effective_date_verified'] is False,
            'Dover historical qualification changed; review the new evidence')
    require(replay['fixed_annual_cohort'] == 8651 and replay['post_cutover_source_hours'] == 287,
            'Runtime cohort changed')
    channels = []
    for ptid, name, family, positive_from, positive_to in [
        (25118, 'PS33 / L33P', 'Ontario', 'St Lawrence / IESO', 'Moses / NYISO'),
        (25119, 'PS34 / L34P', 'Ontario', 'St Lawrence / IESO', 'Moses / NYISO'),
        (625149, 'T398-A', 'Dover', 'Long Mountain / ISONE', 'Cricket Valley / NYISO'),
        (625150, 'T398-B', 'Dover', 'Long Mountain / ISONE', 'Cricket Valley / NYISO')]:
        historical = family == 'Ontario'
        channels.append(dict(ptid=ptid, name=name, family=family,
            documented_positive_from=positive_from, documented_positive_to=positive_to,
            raw_to_NY_import_multiplier=1, raw_to_NY_export_multiplier=-1,
            documentary_direction_verified=True, historical_2025_sign_verified=historical,
            explicit_effective_date='2024-12-03' if historical else None,
            oldest_diagram_publication_retrieved_in_this_audit='2026-01-09',
            historical_basis='explicit_Moses_page_note' if historical else 'near_period_corroboration_only',
            adopted_model_policy='NY_import_positive;reorient_explicitly_once_for_model_branch',
            native_unit_status='unresolved;posted_numeric_as_MW_assumed',
            measurement_origin='operator_published_P34;SCADA_vs_RTD_calculation_unverified',
            schedule_product='P53A_not_covered_by_P34_sign_or_unit_qualification'))
    contract = dict(schema_version=1,
        audit_status='complete_available_public_evidence_audit_with_unresolved_semantics',
        audited_model_commit='797049c152073c0cdb800147ee2d11267d556cd6',
        model_loader='System Matpower Format/npcc_nygrid_2025_dover_dc.m',
        native_numeric_MW_unit_verified=False, actual_measurement_origin_verified=False,
        native_timestamp_support_verified=False,
        no_new_numeric_case_or_replay=True, no_internal_interface_fit=True,
        channels=channels,
        raw_numeric_policy=dict(literal_source_column='Flow (MWH)',
            interval_energy_multiplier=1, conversion_is_assumption=True,
            policy='retain_posted_numbers_as_conditional_MW_equivalent;no_factor12_conversion',
            time_aggregation='forward_hold_max600s;complete3600s;retain_UTC_DST;no_missing_zero_fill',
            native_timestamp_support='begin_end_instantaneous_or_average_unresolved;forward_hold_is_model_policy',
            gamma=ontario['gamma'], gamma_applied_once=True,
            ratings_plausibility_is_not_unit_proof=True,
            independent_regional_aggregate_does_not_identify_single_PAR=True),
        runtime_scope=dict(full_year_qualified_hours=8651, Dover_applied_hours=287,
            Dover_cutover_utc='2025-12-20T04:00:00Z',
            Dover_ambiguous_zero_hours=18, Dover_phase_bound_active_hours_nominal=49,
            missing_channels_are_not_zero=True, zero_channels_do_not_prove_bypass_or_zero_intertie=True,
            old_observed_field_names_do_not_certify_measured_origin=True),
        remaining_evidence_requests=[
            'NYISO P34 native-field specification: physical unit, interval duration and timestamp reference.',
            'NYISO P34 product provenance: measured/estimated/calculated flow and revision policy.',
            'A Dover sign convention effective-date record covering December2025, tied to PTIDs625149/625150.',
            'Hourly switching/tap/cooling state and actual current/voltage/Q if claiming physical thermal validation.'],
        dependencies={p.relative_to(ROOT).as_posix(): sha(p) for p in deps})
    CONTRACT.write_text(json.dumps(contract, indent=2) + '\n', encoding='utf-8')
    with (OUT / 'P34_channel_qualifications.csv').open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(channels[0]))
        writer.writeheader(); writer.writerows(channels)
    print(json.dumps(dict(passed=True, channels=len(channels),
                         native_MW_verified=False, measured_origin_verified=False,
                         historical_sign_verified_channels=2, numeric_case_changed=False), indent=2))


if __name__ == '__main__':
    main()
