"""Fail-closed candidate lookup for primary flowgate terms in historical models.

The candidate search below is deliberately not a physical crosswalk. Even an
exact station/voltage string match cannot prove a utility circuit identity,
2025 topology/resection, or meter terminal. No coefficients are promoted to a
physical gate, and no observations are read. Current legacy AC operators are
also inventoried by provenance so they cannot be silently relabelled.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.io import loadmat

from audit_source_crosswalk import ROOT, OUT, PINS, VARIANTS, require, sha, maxabs, branch_law


# Explicit search hints only. Every result remains unverified. These strings
# never authorize an alias, electrical equivalence, meter, or physical mapping.
SEARCH_HINTS = {
    "PANNELL RD": ["PANNELL"], "PANNELL ROAD": ["PANNELL"],
    "QUAKER": ["QUAKER #121"], "ST. 162": ["PERRY #162"], "S. PERRY": ["SOUTH PERRY"],
    "WOOD ST.": ["WOOD STREET"], "WOOD ST": ["WOOD STREET"],
    "EAST FISHKILL": ["E. FISHKILL"], "E. FISHKILL": ["E. FISHKILL"],
    "BUCHANAN SOUTH": ["BUCHANAN"], "BUCHANAN NORTH": ["BUCHANAN"],
    "E. 179TH STREET": ["EAST 179TH STREET"], "EAST 179TH ST.": ["EAST 179TH STREET"],
    "WEST 49TH ST.": ["WEST 49TH STREET"], "W. 49TH STREET": ["WEST 49TH STREET"],
    "SLEIGHT RD": ["SLEIGHT RD"], "SLEIGHT ROAD": ["SLEIGHT RD"],
    "ALCOA": ["ALCOA MASSENA OPERATIONS - WEST PLANT"],
    "ADIRONDACK": ["ADIRONDACK"], "N. OGDENSBURG": ["NORTH OGDENSBURG"],
    "S. MAHWAH": ["SOUTH MAHWAH"], "SAND BAR": ["SAND BAR"],
    "FARRAGUT": ["FARRAGUT"], "LEEDS": ["LEEDS"],
}


def norm(value):
    return re.sub(r"[^A-Z0-9]", "", str(value).upper())


def search_station(station, buses):
    if not str(station).strip():
        return set(), "absent_source_station_label"
    # Remove an explicitly written terminal voltage suffix, preserving that
    # voltage in the separate term filter. This is not a station-name alias.
    station_label=re.sub(r"\s+\d+(?:\.\d+)?\s*kV\s*$","",str(station),flags=re.I).strip()
    exact=set(buses.loc[buses.source_bus_name.map(norm)==norm(station_label),"source_bus"].astype(int))
    hints=SEARCH_HINTS.get(station_label.upper(),[])
    hinted=set(buses.loc[buses.source_bus_name.map(norm).isin([norm(s) for s in hints]),"source_bus"].astype(int))
    return exact|hinted, ("literal_normalized_label_candidate_only" if exact else "explicit_search_hint_unverified_alias" if hinted else "no_textual_station_candidate")


def special_blockers(term):
    circuit=str(term["circuit_id"]).upper()
    name=str(term["source_name"]).upper()
    reasons=[]
    if circuit in ["DH1","DH2"]:
        reasons.append("2025_Dysinger_Henrietta_circuit_not_original_Dysinger_Rochester80_station_pair")
    if circuit=="Y88":
        reasons.append("2025_Lovett_terminal_resection_not_a_Ladentown_name_alias")
    if circuit in ["351","352"] and "EDIC" in name:
        reasons.append("2025_Edic_Princetown_project_path_not_2019_Edic_source_identity")
    if circuit in ["HA1","HA2"]:
        reasons.append("winter_Haverstock_Adirondack_345_replaces_summer_Moses_Adirondack_230_with_changed_meter")
    if circuit=="C3403":
        reasons.append("2025_Marion_Farragut_resection_not_historical_Hudson_Farragut_name_alias")
    if circuit=="X28":
        reasons.append("official_Sprain_Tremont_345_cannot_use_historical_Tremont_138_rows")
    if "BUCHANAN" in name:
        reasons.append("historical_BUCHANAN_node_does_not_resolve_official_North_South_terminal_split")
    if "FARM" in name or "HOOK" in name or "CLYDE" in name:
        reasons.append("compound_path_or_transformer_winding_identity_requires_detailed_source")
    return reasons


def build(definition_paths, output):
    output=Path(output)
    require(not (output/"model_term_candidate_receipt.json").exists(),"Choose a fresh output directory")
    before={p:sha(ROOT/p) for p in PINS}
    require(before==PINS,"Pinned model/source changed")
    helper="scripts/nygrid_2025_flowgate_definitions/audit_source_crosswalk.py"
    source_receipt=json.loads((OUT/"source_crosswalk_receipt.json").read_text())
    require(source_receipt["passed"] and sha(ROOT/helper)==source_receipt["script_sha256"],"Historical audit helper changed since verified source receipt")
    before[helper]=sha(ROOT/helper)
    before[str((OUT/"source_crosswalk_receipt.json").relative_to(ROOT)).replace("\\","/")]=sha(OUT/"source_crosswalk_receipt.json")
    definitions=[]
    for path in definition_paths:
        path=Path(path).resolve()
        df=pd.read_csv(path,keep_default_na=False)
        required={"interface","definition_id","term_id","source_name","from_station","to_station","circuit_id","voltage_kv","metered_end","source_pdf","pdf_page"}
        require(required.issubset(df.columns),"Physical definition schema missing columns: "+str(required-set(df.columns)))
        df["definition_file"]=str(path.relative_to(ROOT)).replace("\\","/")
        definitions.append(df)
        before[str(path.relative_to(ROOT)).replace("\\","/")]=sha(path)
    terms=pd.concat(definitions,ignore_index=True)
    terms["term_key"]=terms.definition_id.astype(str)+"::"+terms.term_id.astype(str)
    require(terms.term_key.is_unique,"Duplicate physical definition/term identity")
    for source in terms.source_pdf.unique():
        before[source]=sha(ROOT/source)
    sourceledger=pd.read_csv(OUT/"PERFORM_source_to_model.csv",keep_default_na=False)
    before[str((OUT/"PERFORM_source_to_model.csv").relative_to(ROOT)).replace("\\","/")]=sha(OUT/"PERFORM_source_to_model.csv")
    buses=pd.read_csv(ROOT/"output/ny_only_package_a/source_inventory/perform_ny_bus_inventory.csv",keep_default_na=False)
    slim=loadmat(ROOT/"output/nygrid_2025_slim/network/network_cases.mat",simplify_cells=True)
    full=loadmat(ROOT/"output/nygrid_2025_downstate/network/network_cases.mat",simplify_cells=True)
    fullreg=pd.read_csv(ROOT/"output/nygrid_2025_downstate/network/branch_register.csv",keep_default_na=False)
    fullbus=pd.read_csv(ROOT/"output/nygrid_2025_downstate/network/bus_register.csv",keep_default_na=False).set_index("model_bus")
    terminalmap=pd.read_csv(ROOT/"output/nygrid_2025_downstate/network/source_bus_map.csv",keep_default_na=False)
    records=[]; candidate_rows=[]; station_records=[]
    for term in terms.to_dict("records"):
        aa,basis_a=search_station(term["from_station"],buses)
        bb,basis_b=search_station(term["to_station"],buses)
        volts=set(float(x) for x in re.findall(r"\d+(?:\.\d+)?",str(term["voltage_kv"])))
        is_xf="transformer" in str(term.get("element_kind","")).lower() or len(volts)>1
        if is_xf and not term["to_station"]:
            bb=aa.copy();basis_b="same_station_other_winding_candidate_only"
        for side,ids,basis in [("from",aa,basis_a),("to",bb,basis_b)]:
            for bid in sorted(ids):
                bus=buses[buses.source_bus==bid].iloc[0]
                station_records.append(dict(term_key=term["term_key"],definition_id=term["definition_id"],term_id=term["term_id"],terminal_side=side,official_station=term[side+"_station"],
                                            historical_source_bus=bid,historical_source_name=bus.source_bus_name,historical_kv=bus.base_kv,
                                            search_basis=basis,alias_verified=False))
        pairs=sourceledger[((sourceledger.source_from_bus.isin(aa))&(sourceledger.source_to_bus.isin(bb)))|
                           ((sourceledger.source_from_bus.isin(bb))&(sourceledger.source_to_bus.isin(aa)))]
        if volts:
            candidates=pairs[pairs.source_from_kv.isin(volts)&pairs.source_to_kv.isin(volts)]
            if is_xf:
                candidates=candidates[candidates.source_from_kv!=candidates.source_to_kv]
            elif len(volts)==1:
                candidates=candidates[candidates.source_from_kv==candidates.source_to_kv]
        else:
            candidates=pairs.iloc[0:0]
        embedded=candidates[candidates.full191_branch_row>0]
        blockers=special_blockers(term)
        if not aa or not bb:
            status="unresolved_station_or_new_terminal"
        elif len(pairs)>0 and len(candidates)==0:
            status="historical_endpoint_candidate_voltage_mismatch"
        elif len(candidates)==0:
            status="no_direct_historical_circuit_candidate_requires_path_or_new_topology"
        elif len(embedded)==0:
            status="historical_candidate_not_embedded_in_current_model"
        else:
            status="embedded_historical_candidate_physical_2025_identity_unverified"
        if term["metered_end"] in ["", "unspecified", "unknown"]:
            blockers.append("official_meter_terminal_not_resolved")
        blockers.extend(["no_verified_2025_circuit_terminal_to_model_crosswalk", "no_source_backed_whole_gate_identifiability_constraint"])
        records.append(dict(**term,model_crosswalk_status=status,
                            historical_from_station_candidates=";".join(map(str,sorted(aa))),historical_to_station_candidates=";".join(map(str,sorted(bb))),
                            historical_endpoint_candidates_before_voltage_filter=";".join(map(str,pairs.source_branch_row)),
                            historical_voltage_compatible_candidate_rows=";".join(map(str,candidates.source_branch_row)),
                            embedded_candidate_full191_rows=";".join(map(str,embedded.full191_branch_row)),
                            direct_candidate_slim148_rows=";".join(map(str,embedded.loc[embedded.slim148_direct_branch_row>0,"slim148_direct_branch_row"])),
                            parent_aggregate_substitute_used=False,physical_2025_crosswalk_verified=False,physical_operator_emitted=False,
                            complete_gate_score_allowed=False,unknown_terms_filled_zero=False,
                            blockers=";".join(blockers),candidate_basis="label_voltage_search_only_never_identity_proof"))
        for row in candidates.to_dict("records"):
            sid=int(row["source_branch_row"]);a=int(row["source_from_bus"]);b=int(row["source_to_bus"])
            orientation=1 if a in aa and b in bb else -1
            # This sign follows candidate station ordering only, not a verified
            # physical P32 orientation or actual AC meter-terminal convention.
            candidate_rows.append(dict(term_key=term["term_key"],definition_id=term["definition_id"],term_id=term["term_id"],interface=term["interface"],source_branch_row=sid,
                                       source_from_bus=a,source_to_bus=b,source_from_name=row["source_from_name"],source_to_name=row["source_to_name"],
                                       from_kv=row["source_from_kv"],to_kv=row["source_to_kv"],raw_circuit_id=row["raw_circuit_id"],
                                       official_circuit_id=term["circuit_id"],literal_circuit_code_match=str(row["raw_circuit_id"])==str(term["circuit_id"]),
                                       full191_branch_row=int(row["full191_branch_row"]),slim148_direct_branch_row=int(row["slim148_direct_branch_row"]),
                                       candidate_station_order_sign=orientation,sign_is_verified_physical_P32_sign=False,
                                       raw_individual_identity_resolved=row["individual_RAW_identity_resolved"],physical_2025_mapping_verified=False))
    output.mkdir(parents=True,exist_ok=True)
    frame=pd.DataFrame(records)
    frame.to_csv(output/"physical_term_model_identifiability.csv",index=False)
    pd.DataFrame(candidate_rows).to_csv(output/"historical_circuit_candidates.csv",index=False)
    pd.DataFrame(station_records).to_csv(output/"unverified_station_search_candidates.csv",index=False)
    legacy=[]; legacy_terms=[]; numerical=[]
    for variant in VARIANTS:
        recovery=slim["recovery"][variant]
        F,phase,_=branch_law(full[variant+"_case"])
        L,d=recovery["angle_lift"],recovery["angle_offset"]
        for iid,name,c in zip(slim["interface_ids"],slim["interface_names"],recovery["full_interface_branch_matrix"]):
            used=np.flatnonzero(c)
            picked=fullreg.iloc[used]
            H=c@F@L;h=c@(F@d+phase)
            ix=list(slim["interface_ids"]).index(iid)
            err=maxabs(H-recovery["interface_angle_matrix"][ix]);offseterr=abs(float(h)-float(recovery["interface_flow_offset"][ix]))
            require(err<1e-8 and offseterr<1e-8,"Legacy operator provenance mismatch")
            legacy.append(dict(variant=variant,legacy_interface_id=int(iid),legacy_interface_name=name,active_AC_member_count=len(used),
                               full191_rows=";".join(map(str,used+1)),signed_full191_rows=";".join(str(int(np.sign(c[j]))*(j+1)) for j in used),
                               historical_PERFORM_rows=";".join(map(str,picked.loc[picked.source_branch_row>0,"source_branch_row"].astype(int))),
                               aggregate_parent_rows=";".join(map(str,picked.loc[picked.parent_branch_row>0,"parent_branch_row"].astype(int))),
                               source_historical_rows=int((picked.source_branch_row>0).sum()),aggregate_parent_count=int((picked.parent_branch_row>0).sum()),
                               verified_2025_physical_gate=False,source_of_membership="accounting_zone_crossing_not_official_physical_terms",
                               scope="AC_member_operator_only_original_fixed_DC_terms_not_enumerated_here",
                               independent_operator_error_MW_per_rad=err,independent_offset_error_model_MW=offseterr))
            for j in used:
                record=fullreg.iloc[j]
                a,b=int(record.from_bus),int(record.to_bus)
                legacy_terms.append(dict(variant=variant,legacy_interface_id=int(iid),legacy_interface_name=name,
                                         full191_branch_row=j+1,coefficient=float(c[j]),from_model_bus=a,to_model_bus=b,
                                         from_model_name=fullbus.loc[a,"model_name"],to_model_name=fullbus.loc[b,"model_name"],
                                         from_model_kv=float(fullbus.loc[a,"base_kv"]),to_model_kv=float(fullbus.loc[b,"base_kv"]),
                                         from_accounting_zone=fullbus.loc[a,"accounting_zone"],to_accounting_zone=fullbus.loc[b,"accounting_zone"],
                                         electrical_role=record.electrical_role,source_PERFORM_row=int(record.source_branch_row),
                                         ancestor_parent_row=int(record.parent_branch_row),original_parent_record=record.electrical_role=="retained_parent",
                                         verified_2025_physical_member=False))
        for row in candidate_rows:
            modelrow=int(row["full191_branch_row"])
            if modelrow==0:
                continue
            j=modelrow-1;sgn=row["candidate_station_order_sign"]
            H=sgn*(F[j]@L);h=sgn*float(F[j]@d+phase[j])
            err=maxabs(H-sgn*recovery["branch_angle_matrix"][j]);offseterr=abs(h-sgn*float(recovery["branch_flow_offset"][j]))
            require(err<1e-8 and offseterr<1e-8,"Historical candidate recovery mismatch")
            numerical.append(dict(variant=variant,term_key=row["term_key"],definition_id=row["definition_id"],term_id=row["term_id"],source_branch_row=row["source_branch_row"],full191_branch_row=modelrow,
                                  historical_operator_error_MW_per_rad=err,historical_offset_error_model_MW=offseterr,
                                  numerical_recovery_passed=True,physical_2025_mapping_passed=False,physical_operator_emitted=False))
    pd.DataFrame(legacy).to_csv(output/"legacy_AC_operator_provenance.csv",index=False)
    pd.DataFrame(legacy_terms).to_csv(output/"legacy_AC_operator_terms.csv",index=False)
    terminalmap[terminalmap.source_physical_zone!=terminalmap.parent_accounting_zone].to_csv(output/"embedded_source_vs_accounting_zone_differences.csv",index=False)
    pd.DataFrame(numerical).to_csv(output/"historical_candidate_numeric_checks.csv",index=False)
    summary=frame.groupby(["definition_id","interface"],dropna=False).agg(physical_term_count=("term_id","size"),verified_physical_model_terms=("physical_2025_crosswalk_verified","sum"),
                        terms_with_embedded_historical_candidates=("embedded_candidate_full191_rows",lambda s:int((s!="").sum()))).reset_index()
    summary["complete_physical_operator_available"]=False
    summary.to_csv(output/"gate_model_coverage.csv",index=False)
    after={p:sha(ROOT/p) for p in before}
    require(before==after,"Input changed during candidate audit")
    report=dict(passed=True,created_utc=datetime.now(timezone.utc).isoformat(),scope="candidate_search_and_identifiability_audit_not_physical_operator_calibration",
                physical_terms=len(frame),definition_families=terms.definition_id.nunique(),verified_physical_model_terms=0,
                complete_physical_operators=0,internal_interface_observations_used=False,score_calibration_used=False,
                current_model_numeric_gate_promotion=False,legacy_AC_operator_state_checks=len(legacy),historical_candidate_state_checks=len(numerical),
                source_hashes_unchanged=True,dependencies=before,script_sha256=sha(__file__),coverage=summary.to_dict("records"),
                limitations=["Candidate name/voltage or generic RAW ID equality is never a source-backed utility circuit crosswalk.",
                             "Original 225 parent rows contain no independently verified physical source lineage.",
                             "No source-backed physical-to-aggregate matrix or hidden-injection constraint exists here to establish whole-gate identifiability.",
                             "Current detailed circuits use a 2019 source with 2025 project assumptions; seasonal definition availability does not establish every-hour annual validity.",
                             "The current lossless DC model cannot reconstruct actual AC meter-end losses."])
    report["outputs"]={p.name:sha(p) for p in output.iterdir() if p.is_file()}
    (output/"model_term_candidate_receipt.json").write_text(json.dumps(report,indent=2)+"\n")
    print(summary.to_string(index=False))
    print(json.dumps({k:report[k] for k in ["passed","physical_terms","verified_physical_model_terms","legacy_AC_operator_state_checks","historical_candidate_state_checks"]}))


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--definitions",type=Path,nargs="+",required=True)
    parser.add_argument("--output",type=Path,default=ROOT/"output/nygrid_2025_flowgate_definitions/model_identifiability")
    args=parser.parse_args()
    build(args.definitions,args.output)
