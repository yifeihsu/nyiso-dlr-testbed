"""Seal reviewed map evidence; do not promote the previous current entry point."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json

ROOT=Path(__file__).resolve().parents[4]
OUT=ROOT/'output/nygrid_2025_moses_repair/delivery/map'


def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def main():
    page=OUT/'network_map.html';observations=OUT/'qa/native_browser_observations.json'
    actual=json.loads(observations.read_text());assert actual['passed'] and actual['reviewed_html_sha256']==sha(page)
    shot=OUT/'qa'/actual['screenshot'];assert shot.is_file()
    evidence=[]
    for name in ['build_receipt.json','scientific_data_receipt.json','independent_annual_data_review.json',
                 'geography_independent_review.json','independent_ui_flow_math_review.json',
                 'independent_embedded_payload_review.json','interaction_validation.json']:
        p=OUT/name;proof=json.loads(p.read_text());assert proof['passed'],name
        evidence.append(dict(path=name,sha256=sha(p)))
    review=dict(passed=True,created_utc=datetime.now(timezone.utc).isoformat(),
                HTML_sha256=sha(page),method=actual['method'],native_browser_observations=actual['observations'],
                screenshot=dict(path='qa/'+shot.name,sha256=sha(shot)),
                observations_sha256=sha(observations),actual_mobile_device_test_claimed=False)
    (OUT/'browser_visual_review.json').write_text(json.dumps(review,indent=2)+'\n',encoding='utf-8')
    annual=json.loads((OUT/'annual_data.json').read_text());meta=annual['metadata'];counts=meta['counts']
    readme=f'''# Current 2025 NYgrid interactive map

Open `network_map.html` in a browser. It is self-contained and requires no network connection.

This version displays the St. Lawrence monthly-energy allocation and the northern PV20 boundary correction. It includes all 8,760 clock positions, {counts['qualified']:,} equation/loss-qualified annual states, and {counts['sourceExcluded']} source-excluded positions. Full-network operating qualification remains {counts['operatingQualified']}; equation success does not certify operating limits.

Choose an hour, toggle Model MW or Public scale MW, and select a zone, bus or interface. Public power is aggregate model power divided by gamma. Current is never rescaled. Unavailable model flows remain blank.

The North Country panel shows St. Lawrence generation, HQ import and the signed PV20 proxy input. The PV20 map label opens Plattsburgh in Zone D. Positive means import into New York; negative means export. This component is removed from the remaining New England input pool, preserving total regional interchange.

St. Lawrence hourly output is reconstructed under monthly EIA energy constraints and declared capability/availability assumptions. PV20 uses observed Sand Bar metering at the Plattsburgh aggregate boundary. South Hero net load, intervening losses and historical sign applicability remain qualified. Source documents verify the physical northern pocket and seven Moses South members; exact physical P32 meter equivalence is not certified.

Candidate: `{meta['mosesRepairCandidateSha256']}`. Compiled model: `{meta['compiledModelSha256']}`. Annual replay: `{meta['annualRun']}`.

The complete model package supplies runtime, source policies, boundary evidence, annual validation and reproduction instructions. Map geography shows model points and schematic accounting areas, not surveyed line routes or official NYISO zone polygons.
'''
    (OUT/'README.md').write_text(readme,encoding='utf-8')
    manifest=dict(schema_version=1,passed=True,created_utc=datetime.now(timezone.utc).isoformat(),
                  package_kind='Moses_source_repair_current_interactive_map',
                  candidate_sha256=meta['mosesRepairCandidateSha256'],compiled_model_sha256=meta['compiledModelSha256'],
                  annual_run=meta['annualRun'],counts=counts,offline_self_contained=True,
                  physical_meter_equivalence_certified=False,
                  files=[dict(path=name,sha256=sha(OUT/name),bytes=(OUT/name).stat().st_size) for name in ['network_map.html','README.md']],
                  numerical_and_interaction_evidence=evidence,
                  browser_visual_review_sha256=sha(OUT/'browser_visual_review.json'))
    (OUT/'DELIVERY_MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(passed=True,html_sha256=sha(page),qualified=counts['qualified'])))


if __name__=='__main__':main()
