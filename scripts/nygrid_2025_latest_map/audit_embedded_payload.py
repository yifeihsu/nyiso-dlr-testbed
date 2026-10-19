"""Bind a frozen offline HTML map to exact canonical data, metadata and UI."""
from pathlib import Path
from html.parser import HTMLParser
from datetime import datetime, timezone
import argparse
import hashlib
import json

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output/nygrid_2025_latest_map"
SRC = Path(__file__).parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value):
    # Unlike Python equality alone, this also distinguishes booleans from
    # numeric 0/1 and preserves integer-versus-float JSON representations.
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


class Embedded(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.active = None
        self.blocks = []
        self.external_stylesheets = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag in {"script", "style"}:
            self.active = {"tag": tag, "attributes": attributes, "parts": []}
        if tag == "link" and attributes.get("rel", "").lower() == "stylesheet":
            self.external_stylesheets.append(attributes.get("href"))

    def handle_data(self, text):
        if self.active is not None:
            self.active["parts"].append(text)

    def handle_endtag(self, tag):
        if self.active is not None and tag == self.active["tag"]:
            self.blocks.append(self.active)
            self.active = None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-html-sha256", required=True)
    args = parser.parse_args()
    html_path = OUT / "network_map.html"
    assert sha(html_path) == args.expected_html_sha256, "The requested final HTML changed"
    parsed = Embedded(); parsed.feed(html_path.read_text(encoding="utf-8"))
    scripts = [b for b in parsed.blocks if b["tag"] == "script"]
    payloads = [b for b in scripts if b["attributes"].get("id") == "network-data"]
    program = [b for b in scripts if b not in payloads]
    styles = [b for b in parsed.blocks if b["tag"] == "style"]
    assert len(payloads) == len(program) == len(styles) == 1 and len(scripts) == 2
    assert not any("src" in b["attributes"] for b in scripts) and not parsed.external_stylesheets
    actual = json.loads("".join(payloads[0]["parts"]))
    components = {"geography": "geography_data.json", "annual": "annual_data.json", "interfaces": "interface_definitions.json"}
    checks = []
    expected = {}
    for key, filename in components.items():
        path = OUT / filename; reference = json.loads(path.read_text(encoding="utf-8"))
        text = canonical(reference); embedded = canonical(actual[key])
        assert text == embedded, key + " differs, including metadata or JSON scalar types"
        expected[key] = reference
        checks.append({"component": key, "path": path.relative_to(ROOT).as_posix(),
            "file_sha256": sha(path), "canonical_JSON_sha256": hashlib.sha256(text.encode()).hexdigest(),
            "exact_complete_component_and_metadata_match": True, "no_fields_dropped_or_changed": True})
    composed = {"schemaVersion": 1, "sourceModelCommit": expected["geography"]["mapSourceCommit"], **expected}
    assert canonical(actual) == canonical(composed)
    map_data = OUT / "map_data.json"
    assert canonical(actual) == canonical(json.loads(map_data.read_text(encoding="utf-8")))
    assert "".join(program[0]["parts"]).strip() == (SRC / "map.js").read_text(encoding="utf-8").strip()
    assert "".join(styles[0]["parts"]).strip() == (SRC / "map.css").read_text(encoding="utf-8").strip()
    math_path = OUT / "independent_ui_flow_math_review.json"
    math_review = json.loads(math_path.read_text(encoding="utf-8"))
    assert math_review["passed"] and math_review["test_count"] == 11
    js_record = next(r for r in math_review["sources"] if r["path"].endswith("/map.js"))
    assert js_record["sha256"] == sha(SRC / "map.js"), "UI math review is stale"
    build_path = OUT / "build_receipt.json"; build = json.loads(build_path.read_text(encoding="utf-8"))
    mismatches = [r["path"] for r in build["sources"] + build["outputs"] if sha(ROOT / r["path"]) != r["sha256"]]
    assert not mismatches, mismatches
    receipt = {"passed": True, "created_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "Final HTML exact embedded canonical datasets and metadata, matching inline UI/CSS, and current source-bound math proof",
        "HTML_sha256": sha(html_path), "HTML_bytes": html_path.stat().st_size,
        "map_data_sha256": sha(map_data), "component_checks": checks,
        "complete_top_level_payload_exact": True, "map_data_JSON_exact": True,
        "inline_JS_exact_source_match": True, "inline_CSS_exact_source_match": True,
        "JS_sha256": sha(SRC / "map.js"), "CSS_sha256": sha(SRC / "map.css"),
        "script_blocks": len(scripts), "external_script_sources": [], "external_stylesheets": [],
        "UI_math_checks_passed": math_review["test_count"], "UI_math_review_sha256": sha(math_path),
        "build_receipt_sha256": sha(build_path), "build_source_and_output_hash_mismatches": mismatches,
        "real_browser_visual_review_is_separate": True, "new_simulation_run": False,
        "canonical_data_or_UI_sources_modified": False,
        "audit_script": {"path": Path(__file__).relative_to(ROOT).as_posix(), "sha256": sha(Path(__file__))}}
    target = OUT / "independent_embedded_payload_review.json"
    target.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": True, "HTML_sha256": receipt["HTML_sha256"], "JS_sha256": receipt["JS_sha256"],
        "complete_component_metadata_matches": len(checks), "UI_math_checks": 11, "receipt_sha256": sha(target)}))


if __name__ == "__main__": main()
