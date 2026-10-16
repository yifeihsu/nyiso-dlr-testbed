"""Normalize a narrow primary-manufacturer conductor catalog for added lines.

The primary F84 match is Mallard 795 ACSS, based on project documentary identity,
not closeness to a proxy R. Other 795-ACSS constructions remain candidates only
where a project source names size/family without its code word/stranding.
Existing Hawk/Drake/Cardinal ACSR entries are comparison surrogates, not installs.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
DEFAULT = ROOT / "output/nygrid_2025_line_parameters/conductors"
ACSR_SELECTION = {"Hawk", "Drake", "Cardinal", "Mallard"}
ACSS_SELECTION = {"Macaw", "Turbit", "Tern", "Puffin", "Cuckoo", "Condor", "Drake", "Mallard", "Bluebird"}
INCH_M = .0254
FOOT_M = .3048
KFT_M = 304.8
SQ_INCH_MM2 = 645.16
LB_KG = .45359237
KCMIL_MM2 = math.pi / 4 * (.0254 ** 2) * 1000


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def parse_family(path, family, selection):
    text_path = path.with_suffix(".txt")
    subprocess.run(["pdftotext", "-layout", str(path), str(text_path)], check=True)
    tables = {}
    for page, text in enumerate(text_path.read_text(encoding="utf-8").split("\f"), 1):
        table_type = "electrical" if "(ELECTRICAL PROPERTIES)" in text else "mechanical" if "(MECHANICAL PROPERTIES)" in text else None
        if table_type is None:
            continue
        for line in text.splitlines():
            tokens = line.split()
            if not tokens:
                continue
            name = tokens[0].removesuffix("/ACSS")
            if name not in selection:
                continue
            require(re.fullmatch(r"\d+x[\d.]+", tokens[2]) is not None and re.fullmatch(r"\d+x[\d.]+", tokens[3]) is not None,
                    "Stranding columns moved: " + line)
            tables[(name, table_type)] = dict(page=page, tokens=tokens, line=line.strip())
    rows = []
    for name in sorted(selection):
        require((name, "electrical") in tables and (name, "mechanical") in tables, "Selected catalog record missing")
        e, m = tables[(name, "electrical")], tables[(name, "mechanical")]
        values, mechanical = e["tokens"], m["tokens"]
        require(len(values) == (18 if family == "ACSS" else 15), "Unexpected electrical table schema: " + e["line"])
        require(values[:7] == mechanical[:7], "Electrical/mechanical geometry mismatch")
        n_al, d_al = values[2].split("x"); n_st, d_st = values[3].split("x")
        gmr_index = 15 if family == "ACSS" else 12
        rows.append(dict(catalog_id=f"PRYSMIAN_{family}_{name.upper()}_{values[1].replace('.', '_')}_{n_al}_{n_st}",
            family=family, code_word=name, aluminum_kcmil=float(values[1]), aluminum_strands=int(n_al), steel_strands=int(n_st),
            aluminum_wire_diameter_in=float(d_al), steel_wire_diameter_in=float(d_st),
            total_area_in2=float(values[4]), aluminum_area_in2=float(values[5]), outside_diameter_in=float(values[6]),
            r_dc20_ohm_per_kft=float(values[7]), r_ac25_ohm_per_kft=float(values[8]), r_ac75_ohm_per_kft=float(values[9]),
            r_ac200_ohm_per_kft=float(values[10]) if family == "ACSS" else np.nan,
            gmr_ft=float(values[gmr_index]), one_foot_inductive_reference_ohm_per_kft=float(values[gmr_index + 1]),
            one_foot_capacitive_reference_Mohm_kft=float(values[gmr_index + 2]),
            total_mass_lb_per_kft=float(mechanical[7]), aluminum_mass_lb_per_kft=float(mechanical[8]), steel_mass_lb_per_kft=float(mechanical[9]),
            source_id=path.stem, source_pdf_page_electrical=e["page"], source_pdf_page_mechanical=m["page"],
            source_electrical_row=e["line"], source_mechanical_row=m["line"]))
    return rows


def ac_resistance_at_temperature(row, temperature_c):
    temperatures, resistances = [25., 75.], [row["r_ac25_ohm_per_m"], row["r_ac75_ohm_per_m"]]
    if np.isfinite(row["r_ac200_ohm_per_m"]):
        temperatures.append(200.); resistances.append(row["r_ac200_ohm_per_m"])
    require(temperatures[0] <= temperature_c <= temperatures[-1], "No silent resistance extrapolation beyond catalog temperatures")
    return float(np.interp(temperature_c, temperatures, resistances))


def build(folder=DEFAULT):
    folder = Path(folder).resolve()
    receipts = json.loads((folder / "source_receipts.json").read_text())
    sources = {row["source_id"]: row for row in receipts}
    for row in receipts:
        require(sha(ROOT / row["path"]) == row["sha256"], "Source bytes changed: " + row["source_id"])
    raw = pd.DataFrame(parse_family(folder / "sources/prysmian_acsr_us.pdf", "ACSR", ACSR_SELECTION)
                       + parse_family(folder / "sources/prysmian_acss_us.pdf", "ACSS", ACSS_SELECTION))
    normalized = []
    checks = []
    for row in raw.to_dict("records"):
        source = sources[row["source_id"]]
        item = dict(catalog_id=row["catalog_id"], manufacturer_catalog="Prysmian / General Cable TransPowr",
            family=row["family"], code_word=row["code_word"], aluminum_kcmil=row["aluminum_kcmil"],
            aluminum_strands=row["aluminum_strands"], steel_strands=row["steel_strands"],
            construction_modifier="MA2_regular_strength_ZnAl_mischmetal_steel" if row["family"] == "ACSS" else "GA2_regular_strength_galvanized_steel",
            aluminum_temper="1350-O" if row["family"] == "ACSS" else "1350-H19",
            diameter_m=row["outside_diameter_in"] * INCH_M, gmr_m=row["gmr_ft"] * FOOT_M,
            aluminum_area_mm2=row["aluminum_area_in2"] * SQ_INCH_MM2,
            total_metal_area_mm2=row["total_area_in2"] * SQ_INCH_MM2,
            steel_area_mm2=(row["total_area_in2"] - row["aluminum_area_in2"]) * SQ_INCH_MM2,
            nominal_aluminum_area_mm2=row["aluminum_kcmil"] * KCMIL_MM2,
            aluminum_wire_diameter_m=row["aluminum_wire_diameter_in"] * INCH_M,
            steel_wire_diameter_m=row["steel_wire_diameter_in"] * INCH_M,
            aluminum_mass_kg_per_m=row["aluminum_mass_lb_per_kft"] * LB_KG / KFT_M,
            steel_mass_kg_per_m=row["steel_mass_lb_per_kft"] * LB_KG / KFT_M,
            r_dc20_ohm_per_m=row["r_dc20_ohm_per_kft"] / KFT_M,
            r_ac25_ohm_per_m=row["r_ac25_ohm_per_kft"] / KFT_M,
            r_ac75_ohm_per_m=row["r_ac75_ohm_per_kft"] / KFT_M,
            r_ac200_ohm_per_m=row["r_ac200_ohm_per_kft"] / KFT_M,
            ac_frequency_hz=60, frequency_basis="60Hz_North_American_catalog_context;frequency_not_repeated_in_each_resistance_header",
            resistance_temperature_points_c="25;75;200" if row["family"] == "ACSS" else "25;75",
            resistance_policy="manufacturer_AC_points;piecewise_linear_interpolation_only;no_DC_alpha_substitution",
            source_id=row["source_id"], source_url=source["url"], source_sha256=source["sha256"],
            source_pdf_page_electrical=row["source_pdf_page_electrical"], source_pdf_page_mechanical=row["source_pdf_page_mechanical"],
            source_document_date="not_stated_in_retrieved_sheet", manufacturer_installed_on_project_verified=False,
            project_match_scope="F84_codeword_size_family_match;manufacturer_core_grade_and_asbuilt_testing_unverified"
              if row["family"] == "ACSS" and row["code_word"] == "Mallard" else
              "CT_398_2156_ACSS_size_family_compatible;codeword_manufacturer_core_grade_not_verified" if row["family"] == "ACSS" and row["code_word"] == "Bluebird" else
              "Dover_795_ACSS_family_size_candidate_only_codeword_unresolved" if row["family"] == "ACSS" else "comparison_only_not_current_added_overhead_target",
            catalog_one_foot_X_is_full_line_X=False, catalog_ampacity_used_as_project_rating=False)
        require(0 < item["gmr_m"] < item["diameter_m"] / 2, "GMR/radius units inconsistent")
        require(item["r_dc20_ohm_per_m"] < item["r_ac25_ohm_per_m"] < item["r_ac75_ohm_per_m"], "Resistance points inconsistent")
        reconstructed_area = row["aluminum_strands"] * math.pi / 4 * (row["aluminum_wire_diameter_in"] ** 2)
        area_error = abs(reconstructed_area / row["aluminum_area_in2"] - 1)
        require(area_error < .001, "Conductor strand area differs from catalog area")
        require(abs(item["nominal_aluminum_area_mm2"] / item["aluminum_area_mm2"] - 1) < .0015, "Nominal kcmil conversion differs")
        # The tabulated one-foot reactance is a reference term; this validates
        # frequency/length/GMR units without misusing it as a circuit X.
        x_reference = 2 * math.pi * 60 * 2e-7 * math.log(FOOT_M / item["gmr_m"]) * KFT_M
        x_error = abs(x_reference - row["one_foot_inductive_reference_ohm_per_kft"])
        require(x_error < .00025, "One-foot reference/GMR unit consistency failed")
        checks.append(dict(catalog_id=row["catalog_id"], passed=True,
                           strand_area_relative_error=area_error, one_foot_X_rounding_error_ohm_per_kft=x_error))
        normalized.append(item)
    catalog = pd.DataFrame(normalized)
    require(len(catalog) == 13 and catalog.catalog_id.is_unique, "Narrow catalog inventory changed")
    target = catalog.loc[catalog.family.eq("ACSS") & catalog.code_word.eq("Mallard")].iloc[0].to_dict()
    r95 = ac_resistance_at_temperature(target, 95)
    r180 = ac_resistance_at_temperature(target, 180)
    basis = dict(project="Cricket_Valley_F84_new_14.6_mile_line", catalog_id=target["catalog_id"],
        code_word="Mallard", family="ACSS", aluminum_kcmil=795, stranding="30/19", bundle_count=2,
        diameter_m=target["diameter_m"], gmr_m=target["gmr_m"], aluminum_area_mm2=target["aluminum_area_mm2"],
        total_metal_area_mm2=target["total_metal_area_mm2"], source_ac_temperatures_c=[25, 75, 200],
        source_ac_ohm_per_kft=[.0212, .0253, .0359], r_ac95_ohm_per_m=r95, r_ac180_ohm_per_m=r180,
        interpolation_policy="linear between75C and200C catalog AC values;not a measured95C or180C product test",
        length_m=14.6 * 1609.344, phase_R95_ohm=r95 * 14.6 * 1609.344 / 2,
        r95_pu_at_100MVA_345kV=r95 * 14.6 * 1609.344 / 2 / (345**2 / 100),
        existing_proxy_r_pu=.00092, project_design_source_url="https://documents.dps.ny.gov/public/Common/ViewDoc.aspx?DocRefId=%7BD6338C27-6589-4A30-84A5-B185CF6E6EC8%7D",
        project_design_pdf_page=12, project_design_printed_page=9,
        identity_is_project_design_evidence_not_installed_manufacturer_certificate=True,
        x_and_b_require_phase_coordinates_bundle_spacing_and_line_section_geometry=True,
        cable_and_transformer_use_allowed=False, bundle_current_is_total_phase_current=True,
        source_catalog_sha256=target["source_sha256"])
    raw.to_csv(folder / "conductor_raw_values.csv", index=False, lineterminator="\n")
    catalog.to_csv(folder / "conductor_catalog.csv", index=False, lineterminator="\n")
    pd.DataFrame(checks).to_csv(folder / "catalog_checks.csv", index=False, lineterminator="\n")
    (folder / "F84_Mallard_engineering_basis.json").write_text(json.dumps(basis, indent=2) + "\n", encoding="utf-8")
    bluebird = catalog.loc[catalog.family.eq("ACSS") & catalog.code_word.eq("Bluebird")].iloc[0].to_dict()
    ct_basis = dict(project="CT_398_NY_border_to_Long_Mountain", catalog_id=bluebird["catalog_id"],
        code_word="Bluebird", code_word_status="manufacturer_2156_ACSS_family_size_compatible_not_installed_vendor_confirmation",
        family="ACSS", aluminum_kcmil=2156, stranding="84/19", bundle_count=1,
        bundle_count_basis="project_CSC_interrogatory_confirms_single_conductor_per_phase;see_project_source_register",
        diameter_m=bluebird["diameter_m"], gmr_m=bluebird["gmr_m"], aluminum_area_mm2=bluebird["aluminum_area_mm2"],
        source_ac_temperatures_c=[25,75,200], source_ac_ohm_per_kft=[.00882,.0103,.0141],
        r_ac95_ohm_per_m=ac_resistance_at_temperature(bluebird,95),
        r_ac180_ohm_per_m=ac_resistance_at_temperature(bluebird,180),
        temperature_95C_is_analysis_scenario_not_CT_line_rating_claim=True,
        route_length_m=5.3*1609.344,
        source_catalog_sha256=bluebird["source_sha256"],
        project_design_source_url="https://portal.ct.gov/lib/csc/pending_petitions/2_petitions_1201through1300/pe1216_filing_eversource.pdf",
        project_design_pdf_page=5, project_design_printed_page=3,
        limitation="CT section differs from NY twin795Mallard section;do not assign one uniform conductor to the composite Dover-LongMountain path")
    (folder / "CT398_Bluebird_compatible_basis.json").write_text(json.dumps(ct_basis,indent=2)+"\n",encoding="utf-8")
    legacy_path=ROOT/"output/compact_ny_2025/thermal/conductor_library.csv"
    legacy=pd.read_csv(legacy_path)
    old_rows=[]
    for row in legacy.itertuples(index=False):
        name=row.conductor_code.split("_")[0]
        current=catalog.loc[catalog.family.eq("ACSR") & catalog.code_word.str.upper().eq(name)].iloc[0]
        old_rows.append(dict(legacy_code=row.conductor_code,legacy_diameter_m=row.diameter_m,
            primary_comparison_diameter_m=current.diameter_m,legacy_r_ac75_ohm_per_m=row.r_ref_ohm_m,
            prysmian_r_ac75_ohm_per_m=current.r_ac75_ohm_per_m,
            legacy_resistance_difference_percent=100*(row.r_ref_ohm_m/current.r_ac75_ohm_per_m-1),
            legacy_installed_conductor_verified=bool(row.physical_NY_conductor_verified),
            interpretation="different_catalog_nominal_and_rounding_values;legacy_template_is_explicit_surrogate_not_installed_asset_match"))
    pd.DataFrame(old_rows).to_csv(folder/"existing_surrogate_catalog_audit.csv",index=False,lineterminator="\n")
    validation = dict(passed=True, catalog_rows=len(catalog), primary_target_rows=1, documented_family_size_candidates=8,
        CT2156_ACSS_compatible_rows=1, comparison_ACSR_rows=4, manufacturer_geometry_electrical_unit_checks=len(checks),
        excluded_from_catalog_scope=["underground_RCC_cables", "transformers_and_PAR_equivalents", "DC_Schur_equivalent_edges"],
        existing_model_parameters_changed=False, R_matching_alone_can_certify_conductor=False,
        files=[dict(path=p.relative_to(ROOT).as_posix(), sha256=sha(p)) for p in
               [folder / "conductor_catalog.csv", folder / "conductor_raw_values.csv", folder / "F84_Mallard_engineering_basis.json",
                folder / "CT398_Bluebird_compatible_basis.json",folder/"existing_surrogate_catalog_audit.csv",legacy_path,
                folder / "source_receipts.json", Path(__file__)]])
    (folder / "catalog_validation.json").write_text(json.dumps(validation, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in validation.items() if key != "files"}, indent=2))
    return validation


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--output", type=Path, default=DEFAULT)
    build(parser.parse_args().output)
