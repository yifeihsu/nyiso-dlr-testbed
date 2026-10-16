"""Inspect an explicit study edition; refuse unsupported numeric promotion.

No automatic year/month selection is provided because study posting dates are
not operational effective dates. The current registry has no certified model
operators. A failed --require-model-operator is an expected scientific gate.
"""
from pathlib import Path
import argparse
import json
from build_registry import ROOT, DEFS, GATES, SOURCES, INPUTS, sha


def load_registry(directory=DEFS):
    directory = Path(directory)
    receipt = json.loads((directory/'registry_receipt.json').read_text(encoding='utf-8'))
    if receipt.get('passed') is not True:
        raise ValueError('Registry build has not passed')
    required_outputs = {'physical_flowgate_registry.json', 'all_seasonal_members.csv',
                        'definition_summary.csv', 'model_binding_template.csv'}
    if set(receipt['outputs']) != required_outputs:
        raise ValueError('Incomplete registry output manifest')
    for path, digest in receipt['outputs'].items():
        if sha(directory/path) != digest:
            raise ValueError('Changed registry output: '+path)
    dependencies = receipt['dependencies']
    expected_sources = {(ROOT/'output/nygrid_2025_flowgate_definitions'/p).relative_to(ROOT).as_posix(): s
                        for p,s in SOURCES.values()}
    if any(dependencies.get(p) != s for p,s in expected_sources.items()):
        raise ValueError('Official source edition manifest mismatch')
    required_inputs = {(DEFS/p).relative_to(ROOT).as_posix() for p in INPUTS}
    if not required_inputs.issubset(dependencies):
        raise ValueError('Incomplete source transcription manifest')
    for path, digest in dependencies.items():
        if sha(ROOT/path) != digest:
            raise ValueError('Changed dependency: '+path)
    data = json.loads((directory/'physical_flowgate_registry.json').read_text(encoding='utf-8'))
    if data['dependencies'] != dependencies:
        raise ValueError('Registry/receipt dependency disagreement')
    if len(data['terms']) != 269 or len(data['definitions']) != 21:
        raise ValueError('Incomplete registry')
    if len({x['term_key'] for x in data['terms']}) != len(data['terms']):
        raise ValueError('Duplicate source-entry keys')
    if data['internal_interface_observations_used'] or data['fitted_parameters']:
        raise ValueError('Source-only registry contract violated')
    return data


def select_definition(data, gate, edition, require_model_operator=False):
    if gate not in GATES.values() or edition not in SOURCES:
        raise ValueError('Use an explicit known gate and study edition; dates cannot select an operational definition')
    matches = [d for d in data['definitions'] if d['gate_id']==gate and d['edition']==edition]
    if len(matches) != 1:
        raise ValueError('Missing or ambiguous definition')
    definition = matches[0]
    terms = [x for x in data['terms'] if x['definition_id']==definition['definition_id']]
    if (len(definition['members']) != len(set(definition['members']))
            or len(definition['members']) != definition['printed_entries']
            or {x['term_key'] for x in terms} != set(definition['members'])
            or len(terms)!=definition['printed_entries']
            or any(x['gate_id'] != gate or x['edition'] != edition for x in terms)):
        raise ValueError('Incomplete definition membership')
    if require_model_operator:
        # Deliberately no escape hatch that converts candidates or unresolved
        # entries to coefficients. Promotion requires new reviewed evidence.
        raise ValueError('No certified physical model operator for '+gate+' / '+edition+
                         '; resolve circuit/aggregate lineage, metered ports, P32 expression and operational interval first')
    return dict(definition=definition, terms=terms, model_operator_usable=False)


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gate', required=True, choices=list(GATES.values()))
    parser.add_argument('--edition', required=True, choices=list(SOURCES))
    parser.add_argument('--require-model-operator', action='store_true')
    args = parser.parse_args()
    try:
        print(json.dumps(select_definition(load_registry(), args.gate, args.edition,
                                          args.require_model_operator), indent=2, ensure_ascii=False))
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(2, str(exc)+'\n')
