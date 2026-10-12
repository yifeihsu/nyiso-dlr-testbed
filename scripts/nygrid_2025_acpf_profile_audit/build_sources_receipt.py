"""Prepare bounded, reviewed evidence for the native Sources disclosure."""
from pathlib import Path
import json
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'output/nygrid_2025_acpf_profile_audit'


def main():
    s = json.loads((OUT / 'audit_summary.json').read_text())
    a = json.loads((OUT / 'alignment/profile_alignment_summary.json').read_text())
    m = pd.read_csv(OUT / 'comparison/interface_metrics.csv')
    m = m[(m.period == 'annual') & (m.convention == 'legacy_signed_literal_from')]
    items = []

    def add(key, title, files, definition, caveats, columns, rows, method=None):
        query = dict(id=key + '-evidence', source=dict(label='2025 AC model verification',
                     files=[dict(label=p) for p in files],
                     metricDefinitions=[dict(label=title, definition=definition)], caveats=caveats),
                     reportingPeriod='2025 hourly profiles; verification performed October 12, 2026',
                     columns=columns, rows=rows)
        if method:
            query['methods'] = [dict(language='calculation', code=method)]
        items.append(dict(id=key, title=title, queries=[query]))

    add('acpf', 'Does profile-driven ACPF provide qualified operating points?',
        ['annual_profile_PF_receipt.json', 'annual_hour_quality.csv', 'Q_limit_sensitivity_receipt.json'],
        'Numerical convergence, profile preservation, and operating-capability qualification are checked separately.',
        ['No OPF was used. The baseline annual run uses ordinary Q-unlimited PV control.',
         'The 157 failed annual hours also remained unresolved after 314 flat/previous-voltage retries; this is not an infeasibility proof.',
         'Generator capability bounds are assumptions. Thermal overloads are excluded from the convergence gate.',
         'The single slack generator supplies losses; non-slack real-power profiles and loads are preserved.'],
        ['check', 'hours'], [dict(check='Source-qualified attempts', hours=s['source_qualified_hours']),
                             dict(check='Default NR converged', hours=s['default_NR_converged_hours']),
                             dict(check='Equation/profile qualified', hours=s['AC_equation_and_profile_qualified_hours']),
                             dict(check='All V/Q/generator/converter gates', hours=s['VQ_generator_gate_counts']['VQ_and_generator_assumption_gate']),
                             dict(check='Separate Q-limit sensitivity converged, out of 7', hours=s['Q_limit_sensitivity_converged_hours'])])
    add('load', 'How closely do loads match NYISO?',
        ['profile_alignment_summary.json', 'load_zone_allocation_audit.csv', 'load_source_semantics.json'],
        'The 11 zonal totals are preserved after the declared synthetic power scaling; within-zone bus shares remain fixed.',
        ['Zonal agreement is a construction identity. Substation-level allocation is not observed for 2025.',
         'NYISO grid load is net of behind-the-meter solar and demand response.',
         'External regional loads follow the NY load shape; generator profiles are source-informed reconstructions.'],
        ['measure', 'value'], [dict(measure='Hour-zone values checked', value=96360),
                               dict(measure='Largest zonal reaggregation difference, public MW', value=a['NY_load']['maximum_public_scale_zone_reaggregation_error_MW']),
                               dict(measure='Original NY bus records', value=46), dict(measure='Positive load weights', value=31)],
        'For each hour and zone: sum(model bus PD) / gamma - public zonal load. gamma = 0.30012075175285535.')
    add('interfaces', 'How closely do the interface diagnostics match?',
        ['interface_metrics.csv', 'scoring_receipt.json', 'interface_operator_contract.json'],
        f"Seven inherited zone cuts compared on {s['AC_equation_and_profile_qualified_hours']} equation/profile-qualified hours.",
        ['Exact physical P-32 membership, meter terminals, and the inherited numeric-as-MW convention remain unestablished.',
         'These are diagnostic errors, not certified physical flow accuracy. The case is synthetic.',
         'The AC/DC comparison also changes engineering parameters and charging/reactors; it does not isolate AC-loss effects.'],
        ['interface', 'MAE_public_MW', 'WAPE_percent'],
        [dict(interface=r.interface, MAE_public_MW=round(r.mae_public_MW, 3), WAPE_percent=round(r.wape_percent, 3)) for r in m.itertuples()],
        'MAE = mean(abs(predicted - observed)). WAPE = 100 * sum(abs(predicted - observed)) / sum(abs(observed)). Only aggregate model MW is divided by gamma.')
    add('cables', 'Which cable classifications are established?',
        ['cable_evidence_tiers.csv', 'overhead_cable_classification_conflicts.csv', 'source_receipts.csv'],
        'The current 40 cable-like AC rows have different evidence levels; four overhead-classified rows conflict with cable-corridor evidence.',
        ['The 40 rows are network equivalents, not a certified count of physical cables.',
         'Historical utility and project evidence does not establish every circuit identity or burial ampacity.',
         'Y49-associated rows 309 and 310 do not prove two physical Y49 circuits.'],
        ['evidence_tier', 'rows'], [dict(evidence_tier=k, rows=v) for k, v in
          [('Documented project underground identity', 3), ('Historical matching underground corridor', 11),
           ('Related corridor; terminal aliases unresolved', 7), ('Electrical or urban assumption', 16), ('Synthetic proxy', 3)]])
    add('buses', 'Why is the AC bus count larger?',
        ['bus_lineage_all267.csv', 'restored_43_buses.csv', 'numerical_75_buses.csv'],
        'The full AC model restores reduced-out terminals and adds numerical line sections, without adding demand or generation.',
        ['Electrical node count is not physical substation count.', 'The Dover device node is present only after its dated change.'],
        ['stage', 'buses'], [dict(stage=k, buses=v) for k, v in
          [('Previous reduced case', 148), ('Restored full reference', 191), ('Full reference after Dover', 192),
           ('AC before Dover', 266), ('AC after Dover', 267)]],
        '148 + 43 restored nodes + 1 dated Dover node + 75 numerical nodes = 267; the 75 comprise 73 overhead-section nodes and 2 cable-section nodes.')
    path = OUT / 'sources_receipt_input.json'
    path.write_text(json.dumps(dict(schemaVersion=1, items=items), indent=2) + '\n', encoding='utf-8')
    print(str(path))


if __name__ == '__main__':
    main()
