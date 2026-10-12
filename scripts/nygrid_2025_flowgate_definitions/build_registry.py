"""Compile literal seasonal NYISO definitions, never empirical flow coefficients.

The registry preserves every printed entry and every unresolved terminal. It
does not substitute station-name matches for a verified physical circuit map.
"""
from pathlib import Path
import csv
import hashlib
import json
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'output/nygrid_2025_flowgate_definitions'
DEFS = OUT / 'definitions'
INPUTS = ['western_2025.csv', 'western_winter2025_26.csv',
          'western_winter2024_25.csv', 'central_north_2025.csv',
          'central_north_winter2024_25.csv', 'downstate_2025.csv']
GATES = {'DYSINGER EAST': 'dysinger_east', 'WEST CENTRAL': 'west_central',
         'TOTAL EAST': 'total_east', 'MOSES SOUTH': 'moses_south',
         'CENTRAL EAST': 'central_east', 'UPNY-CONED': 'upny_coned',
         'SPRAIN BROOK-DUNWOODIE SOUTH': 'sprain_dunwoodie_south'}
EXPECTED = dict(zip(GATES.values(), [10, 14, 29, 7, 8, 10, 11]))
SOURCES = {
    'winter2024_25': ('sources/central_north/NYISO_Winter2024_2025_Appendices_APPROVED.pdf',
                      '546402b7e85f51441e64a6b68adac53579f83828f6bc8c1195ccc480e082dc0b'),
    'summer2025': ('sources/western/NYISO_Summer2025_Appendices_CE_Changes_APPROVED.pdf',
                   '32e4fb86cc8397ab458fdf790ab52decfcaa9e9686de7aa9bec7527eaf04b901'),
    'winter2025_26': ('sources/central_north/NYISO_Winter2025_2026_Appendices.pdf',
                     'bcf26e7ac908f43a29f34230067b5b1afc6e587845b26246d7ca39a41ef9f072')}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path, obj):
    Path(path).write_text(json.dumps(obj, indent=2, ensure_ascii=False)+'\n', encoding='utf-8', newline='\n')


def truth(value):
    return str(value).lower() == 'true'


def write_csv(path, records):
    with Path(path).open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(records[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(records)


def build():
    dependencies = {str(Path(__file__).relative_to(ROOT)).replace('\\', '/'): sha(__file__)}
    source_editions = {}
    for edition, (rel, digest) in SOURCES.items():
        path = OUT / rel
        if sha(path) != digest:
            raise ValueError('Official PDF differs from reviewed edition: '+rel)
        relative = path.relative_to(ROOT).as_posix()
        dependencies[relative] = digest
        source_editions[relative] = edition
    records = []
    original = {}
    for name in INPUTS:
        path = DEFS / name
        dependencies[path.relative_to(ROOT).as_posix()] = sha(path)
        for row in csv.DictReader(path.open(encoding='utf-8-sig', newline='')):
            gate = GATES[row['interface'].upper()]
            edition = source_editions[row['source_pdf']]
            key = row['definition_id'] + '::' + row['term_id']
            if key in original:
                raise ValueError('Duplicate source row key: '+key)
            original[key] = row
            meter = row['metered_end'].lower()
            if meter not in ('from', 'to', 'unspecified'):
                raise ValueError('Unknown meter token: '+meter)
            blockers = []
            if meter == 'unspecified':
                blockers.append('metered_terminal_unresolved')
            if not row['from_station'] or not row['to_station']:
                blockers.append('physical_terminal_pair_unresolved')
            if truth(row.get('compound_term')):
                blockers.append('compound_path_requires_port_definition')
            if truth(row.get('voltage_name_column_conflict')):
                blockers.append('source_voltage_conflict')
            if row.get('possible_duplicate_group'):
                blockers.append('possible_duplicate_source_entry')
            expr = '' if blockers else ('+PF' if meter == 'from' else '-PT')
            records.append(dict(gate_id=gate, edition=edition, definition_id=row['definition_id'],
                term_id=row['term_id'], term_key=key, source_name=row['source_name'],
                from_station=row['from_station'], to_station=row['to_station'],
                circuit_id=row['circuit_id'], voltage_kv=row['voltage_kv'], metered_end=meter,
                source_table_port_expression=expr,
                source_zone_direction=row.get('source_zone_direction') or row.get('source_from_zone','')+' -> '+row.get('source_to_zone',''),
                source_pdf=row['source_pdf'], source_pdf_sha256=dependencies[row['source_pdf']],
                pdf_page=int(row['pdf_page']), printed_page=int(row['printed_page']),
                posted_date=row['posted_date'], source_scope=row['scope_period'],
                literal_term=row.get('verbatimterm') or row['source_quote_or_verbatim_term'],
                documentary_blockers=';'.join(blockers),
                source_issue=row.get('source_issue',''),
                notes=row.get('notes') or row.get('meter_note',''),
                source_entry_unique_physical_identity_certified=False,
                model_identity_certified=False, P32_expression_certified=False,
                operational_effective_start='', operational_effective_end=''))
    grouped = defaultdict(list)
    for row in records:
        grouped[(row['edition'], row['gate_id'])].append(row)
    if len(grouped) != 21 or len(records) != 269:
        raise ValueError('Incomplete all-seven, three-edition register')
    definitions = []
    for (edition, gate), members in sorted(grouped.items()):
        expected = 16 if edition == 'winter2024_25' and gate == 'west_central' else EXPECTED[gate]
        if len(members) != expected or len({x['definition_id'] for x in members}) != 1:
            raise ValueError('Definition row count/identity mismatch: '+edition+' '+gate)
        definitions.append(dict(gate_id=gate, edition=edition,
            definition_id=members[0]['definition_id'], printed_entries=len(members),
            documentary_port_resolved_entries=sum(bool(x['source_table_port_expression']) for x in members),
            documentary_unresolved_entries=sum(bool(x['documentary_blockers']) for x in members),
            members=[x['term_key'] for x in members],
            numeric_model_operator=None, physical_model_mapping='unestablished',
            P32_expression_binding='unestablished', operational_interval='unestablished',
            current_model_promotion_allowed=False))
    records.sort(key=lambda x:(x['edition'], x['gate_id'], x['term_key']))
    write_csv(DEFS/'all_seasonal_members.csv', records)
    summary = [{k:v for k,v in d.items() if k not in ('members','numeric_model_operator')} for d in definitions]
    write_csv(DEFS/'definition_summary.csv', summary)
    registry = dict(schema_version=1, status='source_definitions_reconstructed_model_calibration_unresolved',
        count=dict(interfaces=7, editions=3, definitions=21, printed_entries=len(records)),
        semantics=dict(PF='MW entering the asset at the literal from terminal',
                       PT='MW entering the asset at the literal to terminal',
                       source_table_port_expression='Local convention: positive flow from the first named terminal to the second, measured at the starred end. This is not a certified P32 gate coefficient or expression.',
                       AC_losses='A receiving-end -PT differs from sending-end PF by active losses; never replace one with the other in an AC comparison.',
                       DC_only='PF = -PT only in a verified lossless representation. That identity does not establish circuit membership.',
                       source_dates='Publication/study edition only. No automatic timestamp-based operational selection.'),
        internal_interface_observations_used=False, fitted_parameters=False,
        dependencies=dependencies, definitions=definitions, terms=records)
    dump(DEFS/'physical_flowgate_registry.json', registry)
    templates = [dict(term_key=x['term_key'], gate_id=x['gate_id'], edition=x['edition'],
        physical_asset_id='', model_branch_or_aggregate_id='', model_orientation_to_source='',
        metered_model_port='', mapping_evidence_path='', mapping_evidence_sha256='',
        mapping_status='unresolved') for x in records]
    write_csv(DEFS/'model_binding_template.csv', templates)
    outputs = ['all_seasonal_members.csv','definition_summary.csv', 'physical_flowgate_registry.json','model_binding_template.csv']
    dump(DEFS/'registry_receipt.json', dict(passed=True,
        status='passed_documentary_registry_only_no_physical_model_promotion',
        counts=registry['count'], dependencies=dependencies,
        outputs={name:sha(DEFS/name) for name in outputs},
        numerical_model_operators_emitted=0, internal_observations_used=False))
    print(json.dumps(registry['count']))


if __name__ == '__main__':
    build()
