"""Read-only western operator, raw P32 and plant-zone evidence audit.

All frozen artifacts remain immutable. Writes only the new mapping audit folder.
No interface observations enter a correction, regression, or parameter fit.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import io
import json
import math
from pathlib import Path
import subprocess
import zipfile

import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output/nygrid_2025_western_audit/mapping"
DEPENDENCIES = {}
CHECKS = []
CHANNELS = {"DYSINGER EAST": (1, 23326), "WEST CENTRAL": (2, 23312)}


def sha(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def use(path):
    p = ROOT / path
    DEPENDENCIES[path] = sha(p)
    return p


def csv(path, **kwargs):
    return pd.read_csv(use(path), **kwargs)


def mat(path, names=None):
    return loadmat(use(path), simplify_cells=True, variable_names=names)


def check(name, passed, error=0., detail=""):
    CHECKS.append(dict(check=name, passed=bool(passed), maximum_absolute_error=float(error), detail=detail))
    if not passed:
        raise AssertionError(name + " " + detail)


def close(name, a, b, tolerance=1e-7):
    a, b = np.asarray(a), np.asarray(b)
    same = a.shape == b.shape and np.array_equal(np.isfinite(a), np.isfinite(b))
    error = np.max(abs(a[np.isfinite(a)] - b[np.isfinite(b)]), initial=0) if same else np.inf
    check(name, same and error < tolerance, error)


def save(name, frame):
    frame.to_csv(OUT / name, index=False, lineterminator="\n")


def operator(case, interface_id):
    mapping = np.atleast_2d(case["if"]["map"])
    signed = mapping[mapping[:, 0] == interface_id, 1].astype(int)
    check(f"unique_members_{len(case['branch'])}_{interface_id}", len(signed) == len(set(abs(signed))))
    out = np.zeros(len(case["branch"]))
    out[abs(signed)-1] = np.sign(signed)
    return out


def cut(case, zones, left, right):
    return np.array([r[10] * (int(zones[int(r[0])] in left and zones[int(r[1])] in right)
                     - int(zones[int(r[1])] in left and zones[int(r[0])] in right))
                     for r in case["branch"]], float)


def utc(raw):
    t = pd.DatetimeIndex(pd.to_datetime(raw, format="mixed"))
    amb = t.tz_localize("America/New_York", ambiguous="NaT", nonexistent="raise").isna()
    summer = np.zeros(len(t), bool)
    if amb.any():
        rewind = [i for i in range(1, len(t)) if amb[i] and amb[i-1] and (t[i-1]-t[i]).total_seconds() > 1800]
        check("unique_fall_clock_rewind", len(rewind) == 1)
        summer[:rewind[0]] = True
    return t.tz_localize("America/New_York", ambiguous=summer, nonexistent="raise").tz_convert("UTC")


def raw_channels():
    receipts = csv("output/nygrid_2025_inputs/load_source/source_receipts.csv")
    channels = {name: [] for name in CHANNELS}
    identity = []
    for receipt in receipts.loc[receipts.family == "ExternalLimitsFlows"].to_dict("records"):
        path = use(receipt["archive"])
        check("raw_archive_hash_" + receipt["month"], sha(path) == receipt["sha256"])
        with zipfile.ZipFile(path) as z:
            for member in sorted(z.namelist()):
                if receipt["month"] == "2026-01" and member != "20260101ExternalLimitsFlows.csv":
                    continue
                raw = pd.read_csv(io.BytesIO(z.read(member)))
                check("P32_header_" + member, list(raw) == ["Timestamp", "Interface Name", "Point ID", "Flow (MWH)", "Positive Limit (MWH)", "Negative Limit (MWH)"])
                for name, (_, ptid) in CHANNELS.items():
                    f = raw.loc[raw["Interface Name"] == name].copy()
                    check(f"P32_identity_{name}_{member}", len(f) > 0 and set(f["Point ID"]) == {ptid})
                    f["utc"] = utc(f.Timestamp)
                    channels[name].append(f[["utc", "Flow (MWH)"]])
                    identity.append(dict(source_member=member, interface=name, ptid=ptid, rows=len(f), source_url=receipt["source_url"]))
    save("raw_channel_identity.csv", pd.DataFrame(identity))
    return {k: pd.concat(v, ignore_index=True) for k, v in channels.items()}


def means(raw, hours):
    s = raw.groupby("utc")["Flow (MWH)"].mean().sort_index()
    t, y = s.index.asi8 / 1e9, s.to_numpy(float)
    result, cover = np.full(len(hours), np.nan), np.zeros(len(hours))
    for h, start in enumerate(hours.asi8 / 1e9):
        first = max(0, int(np.searchsorted(t, start, side="right"))-1)
        last = min(len(t)-1, int(np.searchsorted(t, start+3600, side="left")))
        ix = np.arange(first, last)
        span = np.maximum(0, np.minimum(t[ix+1], start+3600) - np.maximum(t[ix], start))
        good = (t[ix+1]-t[ix] <= 600) & np.isfinite(y[ix])
        cover[h] = span[good].sum()
        if abs(cover[h]-3600) < 1e-7:
            result[h] = np.dot(span[good], y[ix[good]])/3600
    return result, cover


def site_audit(dispatch, gen):
    fleet = csv("output/nygrid_2025_moses_audit/corrected/fleet/fleet_register.csv", keep_default_na=False)
    plants = pd.read_excel(use("tmp/nonfossil_sources/eia860_2025/2___Plant_Y2025_Early_Release.xlsx"), sheet_name="Plant", header=2)
    pdf = use("output/nygrid_2025_dispatch/fleet/source_scope/2025_Gold_Book.pdf")
    check("frozen_GoldBook_hash", sha(pdf) == "cc43665b9344a04b4c9355edd1dc7e31d42a6bb759ffe027ad867221556aea8e")
    pages = use("output/nygrid_2025_moses_audit/generation/goldbook2025_layout.txt").read_text(encoding="utf-8").split("\f")
    parent = csv("output/nygrid_2025_dispatch/fleet/source_parent/npcc.csv", keep_default_na=False)
    # Site identity is based on names plus owner, town, capacity and EIA plant data.
    # It does not constitute a Gold Book to EIA generator-unit/market-membership join.
    sites = [
        (2568, "Glenwood", "B", 24046, 86, "Glenwood Hydro name, Erie Boulevard owner, Medina town and three0.5MW units match. Do not confuse with LongIsland GlenwoodGT in zoneK."),
        (2623, "Waterport", "B", 24046, 87, "Waterport name, Erie Boulevard owner, Waterport town and two units match. EIA4.0MW versus GoldBook4.8MW nameplate difference is retained; no capacity adjustment."),
        (61012, "Mill Seat", "B", 323607, 87, "Name, WM Renewable Energy owner, 6.4 MW match; EIA mailing town Bergen/Genesee differs from Gold Book Riga/Monroe, so county is not used as the zone authority."),
        (56987, "Hyland LFGE", "B", 323620, 87, "Distinctive Hyland name and Angelica location; 3 active 1.6 MW units match 4.8 MW Gold Book. Fourth 1.6 MW EIA unit remains excluded by existing admission policy."),
        (50203, "United States Gypsum", "B", 23774, 100, "US Gypsum name, Niagara Mohawk connection and 5.8 MW nameplate match; Gold Book nonmarket table. Preserve excluded native-dispatch status."),
        (54593, "Batavia", "B", 24024, 86, "Batavia town, Seneca Power Partners owner and 67.3 MW total match exactly; GEN1/2 already B, only 1.1 MW GEN3 has erroneous A metadata while already on B bus62."),
        (50568, "High Acres", "C", 23767, 87, "Distinctive High Acres name, WM Renewable Energy owner, Fairport town and 9.6 MW total match; EIA Monroe versus Gold Book Wayne county does not override explicit C electrical zone."),
        (58399, "Synergy Biogas", "B", 323694, 87, "Exact distinctive name and Wyoming town match; EIA nameplate1.4 versus Gold Book2.0 MW is recorded, not overwritten. Existing excluded dispatch remains excluded."),
    ]
    proposals, unit_rows, plant_rows = [], [], []
    for pid, station, zone, ptid, page, evidence in sites:
        p = plants.loc[plants["Plant Code"] == pid]
        check(f"unique_EIA_site_{pid}", len(p) == 1)
        f = fleet.loc[fleet.plant_id == pid]
        check(f"fleet_site_exists_{pid}", len(f) > 0)
        matches = [line.strip() for line in pages[page-1].splitlines() if station in line and str(ptid) in line]
        expected_matches = {2568:3, 2623:2}.get(pid,1)
        check(f"unique_GoldBook_site_{pid}", len(matches) == expected_matches and all(f" {zone} " in line for line in matches))
        source_line = " | ".join(matches)
        ids = gen.loc[gen.plant_id == pid].index.to_numpy(int)
        native_ids = gen.loc[(gen.plant_id == pid) & (gen.role == "native")].index.to_numpy(int)
        pg = np.asarray(dispatch["gen_pg"])
        power = pg[:, native_ids].sum(axis=1) / float(dispatch["gamma"])
        proposals.append(dict(plant_id=pid, station=station, new_zone=zone, source_ptid=ptid,
            old_zones=";".join(sorted(set(f.zone))), units=len(f), nameplate_mw=float(f.nameplate_capacity_mw.astype(float).sum()),
            dispatch_eligible_units=int(f.dispatch_eligible_default.astype(int).sum()), generator_register_rows=len(ids),
            current_public_mean_mw=float(power[np.asarray(dispatch["dispatch_qualified"],bool)].mean()),
            current_public_peak_mw=float(np.max(power[np.asarray(dispatch["dispatch_qualified"],bool)])), pdf_page=page, printed_page=page-4,
            source_line=source_line, identity_evidence=evidence,
            policy="explicit_GoldBook2025_site_zone_only_preserve_capacity_admission_and_dispatch",
            terminal_policy="same_zone_proxy_to_be_selected_by_existing_landing_policy; not_physical_terminal_confirmation"))
        for r in f.to_dict("records"):
            # Preserve known existing landing in the correct accounting zone.
            # Otherwise repeat the established same-zone geographical proxy.
            old_bus = parent.loc[parent.idx == int(r["bus_id"])].iloc[0]
            if old_bus.zone == zone:
                bid, km, bus_name = int(r["bus_id"]), r["mapping_distance_km"], old_bus["name"]
                landing_reason = "existing_landing_already_in_confirmed_zone_preserved"
            else:
                check("bus_move_is_only_unanchored_county_fallback_"+str(r["fleet_id"]),
                    r["mapping_method"] == "same_zone_nearest_parent_bus_geographic_proxy"
                    and r["zone_mapping_policy"] == "approximate_county_zone_not_verified_electrical_delivery"
                    and not r["legacy_source_gen_rows"] and not r["legacy_candidate_bus_ids"]
                    and int(r["legacy_mapping_ambiguous"]) == 0)
                ranked=[]
                lat, lon = float(r["latitude"]), float(r["longitude"])
                for b in parent.loc[parent.zone == zone].to_dict("records"):
                    p1,p2=math.radians(lat),math.radians(float(b["ycoord"]))
                    value=math.sin((p2-p1)/2)**2+math.cos(p1)*math.cos(p2)*math.sin(math.radians(float(b["xcoord"])-lon)/2)**2
                    km=6371.0088*2*math.asin(min(1.,math.sqrt(value)))
                    ranked.append((km,int(b["idx"]),b["name"]))
                km,bid,bus_name=min(ranked)
                landing_reason="existing_same_zone_nearest_parent_bus_geographic_proxy"
            unit_rows.append({k:r[k] for k in ["fleet_id","plant_id","device_key","plant_name","eia_generator_id","zone","zone_mapping_policy","bus_id","parent_bus_zone","mapping_method","legacy_source_gen_rows","legacy_candidate_bus_ids","legacy_mapping_ambiguous","nameplate_capacity_mw","summer_capacity_mw","dispatch_eligible_default"]} | {"proposed_zone":zone,"zone_changes":r["zone"] != zone,"proposed_bus_id":bid,"proposed_parent_bus_name":bus_name,"proposed_mapping_distance_km":km,"landing_reason":landing_reason,"physical_terminal_verified":False,"source_ptid":ptid,"source_pdf_page":page})
        plant_rows.extend(p.to_dict("records"))
    save("source_confirmed_site_zone_proposals.csv", pd.DataFrame(proposals))
    save("source_confirmed_unit_zone_proposals.csv", pd.DataFrame(unit_rows))
    save("EIA_site_identity.csv", pd.DataFrame(plant_rows))
    return proposals


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat()
    info = csv("tmp/nygrid_2019_reproduction/upstream/Data/npcc_new.csv", keep_default_na=False).set_index("idx")
    zones = info.zone.to_dict()
    d19 = mat("output/nygrid_2019_full_stage1/full_year.mat", ["base_case", "reduced_final_case", "branch_pf", "interface_mw"])
    data = mat("output/nygrid_2025_dispatch/dispatch/dispatch.mat", ["base_case","bus_pd","gen_pg","gamma","timestamp_utc","dispatch_qualified"])
    slim = mat("output/nygrid_2025_slim/network/network_cases.mat")
    full = mat("output/nygrid_2025_downstate/network/network_cases.mat")
    replay = mat("output/nygrid_2025_par_controls/replay/dated_verified_PAR_flows.mat")
    gen = csv("output/nygrid_2025_moses_audit/corrected/model_generator_register.csv")
    check("generator_register_order_aligns_PG",np.array_equal(gen.gen_row.to_numpy(int),np.arange(1,np.asarray(data["gen_pg"]).shape[1]+1)))
    q = np.asarray(replay["qualified"], bool)
    check("common_cohort8663", int(q.sum()) == 8663)
    check("same_frozen_cohort", np.array_equal(q, np.asarray(data["dispatch_qualified"], bool)))
    check("same_UTC_axis", np.array_equal(np.asarray(replay["timestamp_utc"]).astype(str), np.asarray(data["timestamp_utc"]).astype(str)))
    all_zones = dict(zip(np.asarray(full["bus_ids"],int), np.asarray(full["bus_zones"]).astype(str)))
    ledger = []
    for j, (name, (iid, _)) in enumerate(CHANNELS.items()):
        op19, op25 = operator(d19["base_case"],iid), operator(data["base_case"],iid)
        left, right = ({"A"},{"B"}) if j == 0 else ({"B"},{"C"})
        close(name+"_full2019_vs2025_operator", op19,op25)
        close(name+"_semantic_zone_cut", op25,cut(data["base_case"],zones,left,right))
        close(name+"_full2019_PF_sum", np.asarray(d19["branch_pf"])@op19,np.asarray(d19["interface_mw"])[:,j])
        for label,case in [("2019_full140",d19["base_case"]),("2019_corrected_reduced",d19["reduced_final_case"]),("2025_original140",data["base_case"])]:
            op = operator(case,iid)
            for i in np.flatnonzero(op):
                row=case["branch"][i]; a,b=int(row[0]),int(row[1])
                ledger.append(dict(case=label,interface=name,branch_row_1based=int(i+1),coefficient=float(op[i]),from_bus=a,to_bus=b,from_name=info.loc[a,"name"],to_name=info.loc[b,"name"],from_zone=zones[a],to_zone=zones[b],from_kv=float(info.loc[a,"Vn"]),to_kv=float(info.loc[b,"Vn"]),status=float(row[10])))
        for state in sorted(set(np.asarray(replay["network_state_ids"]).astype(str))):
            keep=q & (replay["network_state_ids"] == state)
            rec=slim["recovery"][state.removesuffix("_case")]
            op=cut(full[state],all_zones,left,right)
            close(name+state+"_original_members",op[:225],op25)
            check(name+state+"_no_added_members",np.all(op[225:]==0))
            close(name+state+"_full_recovery_operator",rec["full_interface_branch_matrix"][j],op)
            recovered=np.deg2rad(replay["bus_va"][keep])@rec["interface_angle_matrix"][j]+rec["interface_flow_offset"][j]
            close(name+state+"_saved_recovery",recovered,replay["interface_pf"][keep,j])
            direct=replay["branch_pf"][keep]@rec["local_interface_branch_matrix"][j]
            close(name+state+"_retained_branch_sum",direct,recovered)
    save("model_operator_terms.csv",pd.DataFrame(ledger))
    base=data["base_case"]
    busB=np.array([zones[int(b)]=="B" for b in base["bus"][:,0]])
    genB=np.array([zones[int(b)]=="B" for b in gen.bus_id])
    PB=np.asarray(data["gen_pg"])[:,genB].sum(axis=1)-np.asarray(data["bus_pd"])[:,busB].sum(axis=1)
    difference=replay["interface_pf"][:,1]-replay["interface_pf"][:,0]
    close("WC_minus_Dys_equals_bus_derived_B_injection",difference[q],PB[q])
    save("zone_B_identity.csv",pd.DataFrame(dict(timestamp_utc=replay["timestamp_utc"],qualified=q,WC_minus_Dys_model_mw=difference,bus_derived_B_net_injection_model_mw=PB)))
    catalog=csv("output/nygrid_2025_inputs/load_source/hour_catalog.csv")
    wide=csv("output/nygrid_2025_inputs/load_source/interface_wide.csv")
    long=csv("output/nygrid_2025_inputs/load_source/interface_hourly.csv")
    hours=pd.DatetimeIndex(pd.to_datetime(catalog.timestamp_utc,utc=True))
    check("8760_physical_hours",len(hours)==8760 and np.all(np.diff(hours.asi8)==3600e9))
    check("observation_UTC_matches_dispatch",np.array_equal(wide.timestamp_utc.astype(str),np.asarray(data["timestamp_utc"]).astype(str)))
    raw=raw_channels()
    hourly, scores=[],[]
    saved=csv("output/nygrid_2025_par_controls/comparison/interface_summary.csv")
    for j,(name,(_,ptid)) in enumerate(CHANNELS.items()):
        observed,covered=means(raw[name],hours)
        close(name+"_raw_Flow_rebuild",observed,wide[name].to_numpy(float))
        rows=long.loc[long.channel==name].sort_values("hour_index")
        close(name+"_coverage",covered,rows.coverage_seconds.to_numpy())
        check(name+"_qualified_observation_complete",np.isfinite(observed[q]).all())
        check(name+"_saved_PTID",set(rows.point_id)=={ptid})
        predicted=np.asarray(replay["interface_pf"])[:,j]/float(data["gamma"])
        errors=predicted[q]-observed[q]
        score=dict(interface=name,hours=int(q.sum()),wape_percent=float(100*abs(errors).sum()/abs(observed[q]).sum()),mae_public_mw=float(abs(errors).mean()),bias_public_mw=float(errors.mean()),observation_mean_absolute_mw=float(abs(observed[q]).mean()))
        matching=saved.loc[(saved.interface==name)&(saved.variant=="dated_verified_PAR_flows")]
        if len(matching)==1:
            close(name+"_saved_WAPE",[score['wape_percent']],[matching.iloc[0].wape_percent])
        else:
            check(name+"_saved_variant_present",False,detail=str(saved.variant.unique()))
        scores.append(score)
        hourly.append(pd.DataFrame(dict(timestamp_utc=catalog.timestamp_utc,interface=name,qualified=q,observed_rebuilt_public_mw=observed,covered_seconds=covered,predicted_public_mw=predicted)))
    save("observations_rebuilt.csv",pd.concat(hourly,ignore_index=True))
    save("scores_rebuilt.csv",pd.DataFrame(scores))
    proposals=site_audit(data,gen)
    branch_workbook=use("PERFORM/Auxilliary_Perform_NY/Branch_changes_2019_to_2030.xlsx")
    planning_rows=[]
    for sheet,header in [("New in 2030",0),("2019 On Peak",1),("2030 On Peak",1)]:
        table=pd.read_excel(branch_workbook,sheet_name=sheet,header=header)
        keep=table["From Name"].astype(str).str.contains("DYSINGER",case=False)|table["To Name"].astype(str).str.contains("DYSINGER",case=False)
        subset=table.loc[keep].copy()
        subset.insert(0,"source_sheet",sheet)
        subset.insert(1,"source_excel_row",np.flatnonzero(keep)+header+2)
        planning_rows.append(subset)
    planning=pd.concat(planning_rows,ignore_index=True)
    save("PERFORM_Dysinger_planning_branches.csv",planning)
    new_line=planning.loc[(planning.source_sheet=="New in 2030")&(planning.ID=="1299_1248_1")]
    check("PERFORM_new_Dysinger_Stolle345_identity",len(new_line)==1 and int(new_line.iloc[0]["From Nom kV"])==345 and int(new_line.iloc[0]["To Nom kV"])==345)
    pb=csv("output/ny_only_package_a/source_inventory/perform_ny_bus_inventory.csv",keep_default_na=False)
    # Retain source inventory verbatim only for western station name matches.
    pmask=pb.astype(str).apply(lambda c:c.str.contains("STOLLE|DYSINGER|NIAGARA|HUNTLEY",case=False,regex=True)).any(axis=1)
    save("PERFORM_western_station_buses.csv",pb.loc[pmask])
    evidence=json.loads(use("output/nygrid_2019_diagnostics/western_source_evidence.json").read_text())
    refs=[]
    for receipt in evidence["source_receipts"]:
        if receipt["filename"] not in {"NYISO_Summer2019_Operating_Study_Appendices.pdf","NYISO_DE_WC_Stability_2014.pdf","NYISO_CRPP_Appendix5_1_Interface_Definitions.pdf"}:continue
        check("primary_reference_hash_"+receipt["filename"],sha(use(receipt["path"]))==receipt["sha256"])
        check("primary_text_hash_"+receipt["filename"],sha(use(receipt["text_path"]))==receipt["text_sha256"])
        refs.append(receipt)
    source_note=dict(primary_cached_references=refs,physical2025_membership_verified=False,
        historical_scope="2019 Dysinger has ten physical circuits, including eight A-B and two A-C paths. Dated2014 WestCentral member table shares two A-C paths; undated CRPP lists19 signed terminal measurements. Neither is a certified2025 P32 definition.",
        semantic_warning="NPCC bus62 STOLLE_RD230 is an accounting-B aggregate holding Allegany/Batavia plants. Physical PERFORM StolleRoad230 is A. Relabeling bus62 wholesale would move valid B generation and is unsupported.",
        new2025_source=dict(title="NYISO Summer2025 Operating Study",url="https://www.nyiso.com/documents/20142/3691300/Summer2025-OperatingStudy-APPROVED.pdf/3aaa5eb6-9fa4-53b5-181a-189e3ac52fcb",access="official-domain indexed text retrieved during2026-10-11 audit",printed_page=9,finding="Study includes Dysinger-EastStolleRoad PAR scheduled400MW and Niagara generation50/50 across230/115kV at2100MW total. These are study assumptions, not measured hourly schedules."),
        winter_source=dict(title="NYISO Winter2024-25 Operating Study",url="https://www.nyiso.com/documents/20142/3691300/Winter2024-25%20Operating-Study-Report-APPROVED.pdf/43473858-276f-dcf9-ee2e-5ff519a76639",printed_page=22,finding="Dysinger-EastStolle PAR controller schedule directly affects DysingerEast transfer limit."),
        planning_parameters=dict(path=str(branch_workbook.relative_to(ROOT).as_posix()),sha256=sha(branch_workbook),row_id="1299_1248_1",sheet="New in 2030",from_bus1299="DYSINGER345",to_bus1248="STOLLE_ROAD345",r_pu=0.00101,x_pu=0.012,b_pu=0.18,tap=1.,phase_degree=0.,rated_MVA_A=1216.,rated_MVA_B=2454.,rated_MVA_C=1804.,scope="2030 planning line row, not proof of2025 PAR impedance/rating/tap limits. The workbook2019 sheet already contains Dysinger bus1299 with fivecircuits but omits this new line.",missing_before_model_promotion=["2025 in-service circuit/node crosswalk to retained NPCC western equivalents","separate PAR physical impedance, rating, phase range and sign","definition of new EastStolle345 versus existingStolle345 and Stolle230 terminals","complete2025 metered interface member/terminal definition","external-only or independently scheduled control policy; do not fit this internal PAR to P32"]),
        omitted_plant_proposals=[dict(plant_id=55368,reason="Historical WesternNYWindPower6.6MW appears B, but current2025 operating-table corroboration not established; do not confuse with126MW Wethersfield plant56902 in C."),dict(plant_id=63866,reason="ProposedHighviewSolar C listing alone is insufficient to certify active2025 plant/EIA mapping."),dict(plant_id=66675,reason="No currentGoldBook electrical zone found.")],
        recommendation="Apply only explicit station-zone corrections in a new child replay. Keep capacities and admission frozen. Preserve inherited interface operators as proxies until full2025 physical membership and detailed western-terminal crosswalk are sourced.")
    (OUT/"physical_source_scope.json").write_text(json.dumps(source_note,indent=2)+"\n",encoding="utf-8")
    use(str(Path(__file__).relative_to(ROOT).as_posix()))
    unchanged=all(sha(ROOT/p)==h for p,h in DEPENDENCIES.items())
    check("all_frozen_inputs_unchanged",unchanged)
    save("checks.csv",pd.DataFrame(CHECKS))
    summary=dict(status="complete_numerical_and_P32_audit_with_source_confirmed_site_zone_proposals",started_utc=started,completed_utc=datetime.now(timezone.utc).isoformat(),head=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),checks=len(CHECKS),failed_checks=0,paired_hours=int(q.sum()),confirmed_operator_or_channel_bugs=[],source_confirmed_site_zone_proposals=proposals,physical2025_meter_membership_verified=False,raw_source_units="P32 headerFlow(MWH); existing numeric power convention preserved without fitted scale",observations_used_for_corrections=False,dependencies=[dict(path=p,sha256=h)for p,h in DEPENDENCIES.items()],all_frozen_inputs_unchanged=unchanged)
    (OUT/"mapping_summary.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:summary[k]for k in ["status","checks","failed_checks","paired_hours","all_frozen_inputs_unchanged"]},indent=2))


if __name__=="__main__":
    main()
