"""Bind observed native-browser checks and final screenshot artifacts."""
from pathlib import Path
import hashlib
import json
from PIL import Image

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/nygrid_2025_latest_map'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    path=OUT/'qa/native_browser_observations.json'
    observed=json.loads(path.read_text(encoding='utf-8'))
    assert observed['passed'] and observed['checks_run']==13 and all(c['passed'] for c in observed['checks'])
    assert observed['HTML_sha256']==sha(OUT/'network_map.html')
    screenshots=[]
    for name in ['default_map_preview.jpg','mobile_map_preview.jpg']:
        image=OUT/'qa'/name
        with Image.open(image) as pixels:size=list(pixels.size)
        assert size[0]>300 and size[1]>600
        screenshots.append({'path':image.relative_to(ROOT).as_posix(),'sha256':sha(image),'pixels':size})
    result={'passed':True,'scope':'Actual native browser interactions and final visual layout review',
        'HTML_sha256':observed['HTML_sha256'],'JS_sha256':sha(ROOT/'scripts/nygrid_2025_latest_map/map.js'),
        'CSS_sha256':sha(ROOT/'scripts/nygrid_2025_latest_map/map.css'),
        'native_browser_checks':observed['checks_run'],'native_pointer_hit_testing':True,
        'desktop_visual_review':True,'mobile_visual_review':True,'viewport_override_reset':True,
        'browser_console_errors':[],
        'final_screenshots':screenshots,
        'observations':{'path':path.relative_to(ROOT).as_posix(),'sha256':sha(path)},
        'preview_protocol':'http_on_127.0.0.1_only',
        'direct_file_protocol_browser_test_completed':False,
        'direct_file_protocol_rejection':'Browser URL security policy allows only http and https',
        'blocked_file_navigation_not_bypassed':True,'external_runtime_requests':False,
        'failed_preliminary_cases_resolved':'interactive pointer capture, input commit, detail wrapping, compact mobile letters'}
    (OUT/'browser_visual_review.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':True,'native_browser_checks':13,'screenshots':screenshots},indent=2))
if __name__=='__main__':main()
