"""Seal the additive map and disclose the bounds of its UI verification."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib,json

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/nygrid_2025_cable_review_map'
SRC=Path(__file__).parent


def rec(path):
    with path.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
    return dict(path=path.relative_to(ROOT).as_posix(),sha256=digest,bytes=path.stat().st_size)


def main():
    validation=json.loads((OUT/'validation.json').read_text())
    assert validation['passed'] and validation['interactionChecks']==41
    assert validation['html_sha256']==rec(OUT/'network_map.html')['sha256']
    ui=json.loads((OUT/'interaction_validation.json').read_text())
    assert ui['passed'] and ui['html_sha256']==validation['html_sha256']
    preview=json.loads((OUT/'static_preview_receipt.json').read_text())
    assert preview['passed'] and preview['html_sha256']==validation['html_sha256']
    files=[OUT/name for name in ['network_map.html','README.md','cable_review.csv','cable_review.json',
        'cable_audit_recommendations.json','cable_audit_recommendations.md','build_receipt.json',
        'interaction_validation.json','static_preview_receipt.json','validation.json']]
    files.extend(sorted((OUT/'qa').glob('*.png')))
    source_files=sorted(p for p in SRC.iterdir() if p.is_file())
    manifest=dict(passed=True,created_utc=datetime.now(timezone.utc).isoformat(),
        kind='Additive cable-review visualization of current Moses-repair AC model',
        entry='network_map.html',selfContainedOffline=True,
        currentModelPointerAndPriorArtifactsPreserved=True,modelParametersChanged=False,
        annualPowerFlowRerun=False,highPriorityModelParents=19,totalReviewModelParents=44,
        nativeBrowserVerification=False,nativeBrowserLimitation=validation['nativeBrowserReason'],
        validationScope='41 actual inline-code DOM-event checks and static vector preview; full HTML layout/native pointer hit testing not certified.',
        files=[rec(p) for p in files],source_files=[rec(p) for p in source_files])
    (OUT/'DELIVERY_MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(passed=True,files=len(files),source_files=len(source_files),html_sha256=validation['html_sha256'])))


if __name__=='__main__':main()
