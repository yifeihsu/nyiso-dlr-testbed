"""Versioned site-specific Gold Book D-to-E hydro landing correction.

Consumes frozen source records and writes only a new corrected fleet folder.
Fleet IDs, unit identities, capacity/admission fields, priors, and dispatch MW
are immutable. Bus selection uses the original same-zone nearest-parent rule.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime,timezone
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess

from generation_audit import ROOT,OUT,FLEET,PRIOR,DISPATCH,GOLD,GOLD_SHA,EIA_PLANT,EIA_PLANT_SHA,SITES,sha,require

DEFAULT=ROOT/"output/nygrid_2025_moses_audit/corrected/fleet"
ALLOWED={"zone","zone_mapping_policy","bus_id","parent_bus_name","parent_bus_zone","mapping_method",
         "bus_landing_proxy","mapping_distance_km","source_zone_parent_bus_zone_conflict"}


def read(path):
    with Path(path).open(encoding="utf-8-sig",newline="") as stream:
        reader=csv.DictReader(stream);return list(reader),reader.fieldnames


def write(path,rows,fields=None):
    with Path(path).open("w",encoding="utf-8",newline="") as stream:
        writer=csv.DictWriter(stream,fieldnames=fields or list(rows[0]),lineterminator="\n")
        writer.writeheader();writer.writerows(rows)


def distance(lat1,lon1,lat2,lon2):
    p1,p2=math.radians(lat1),math.radians(lat2)
    value=math.sin((p2-p1)/2)**2+math.cos(p1)*math.cos(p2)*math.sin(math.radians(lon2-lon1)/2)**2
    return 6371.0088*2*math.asin(min(1.,math.sqrt(value)))


def build(output=DEFAULT):
    output=Path(output).resolve()
    require(not (output/"fleet_register.csv").exists(),"Choose a fresh repair output; existing fleet is preserved")
    sites,_=read(OUT/"confirmed_hydro_zone_corrections.csv")
    require(len(sites)==26 and {int(s["plant_id"]) for s in sites}==set(SITES),"Unreviewed or duplicate correction site")
    require(sha(GOLD)==GOLD_SHA and sha(EIA_PLANT)==EIA_PLANT_SHA,"Primary source hash mismatch")
    byplant={int(s["plant_id"]):s for s in sites}
    for pid,s in byplant.items():
        require(s["plant_name"]==SITES[pid][0] and s["old_zone"]=="D" and s["corrected_zone"]=="E","Correction identity mismatch")
        require(s["goldbook_sha256"]==GOLD_SHA and s["eia_plant_sha256"]==EIA_PLANT_SHA,"Crosswalk source mismatch")
    frozen=[FLEET/"fleet_register.csv",FLEET/"fleet_bounds.npz",FLEET/"fleet_bounds.mat",PRIOR/"dispatch_priors.npz",
            DISPATCH/"dispatch.mat",DISPATCH/"dispatch_priors.mat",DISPATCH/"dispatch_bounds.mat"]
    initial={str(p.relative_to(ROOT)).replace("\\","/"):sha(p) for p in frozen}
    original,fields=read(FLEET/"fleet_register.csv")
    parent,_=read(FLEET/"source_parent/npcc.csv")
    targets=[r for r in parent if r["zone"]=="E"]
    require(len(original)==2245 and len({r["device_key"] for r in original})==2245,"Fleet identity changed")
    revised=[];changes=[];landings=[]
    for old in original:
        new=old.copy();pid=int(old["plant_id"])
        if pid in byplant:
            evidence=byplant[pid]
            require(old["plant_name"]==evidence["plant_name"] and old["county"]=="St Lawrence" and old["fuel_category"]=="Hydro","Candidate source identity changed")
            require(old["zone"]=="D" and old["parent_bus_zone"]=="D" and old["coordinates_available"]=="1","Unexpected original landing")
            require(not old["legacy_source_gen_rows"],"A known legacy landing requires separate review")
            ranked=[(distance(float(old["latitude"]),float(old["longitude"]),float(b["ycoord"]),float(b["xcoord"])),int(b["idx"]),b) for b in targets]
            km,bid,bus=min(ranked,key=lambda v:(v[0],v[1]))
            table="III2b" if "III-2b" in evidence["goldbook_table"] else "III2a"
            new.update(zone="E",zone_mapping_policy=f"NYISO_GoldBook2025_{table}_station_zone_verified_EIA_plant_join",
                       bus_id=str(bid),parent_bus_name=bus["name"],parent_bus_zone="E",
                       mapping_method="same_zone_nearest_parent_bus_geographic_proxy",bus_landing_proxy="1",
                       mapping_distance_km=str(km),source_zone_parent_bus_zone_conflict="0")
            for field in fields:
                if new[field]!=old[field]:
                    require(field in ALLOWED,"Unrelated fleet field changed")
                    changes.append(dict(fleet_id=old["fleet_id"],device_key=old["device_key"],plant_id=pid,
                                        field=field,old_value=old[field],new_value=new[field],
                                        goldbook_PTID=evidence["goldbook_PTID"],goldbook_pdf_pages=evidence["goldbook_pdf_pages"],
                                        reason="primary_station_electrical_zone_overrides_generic_county_proxy"))
            landings.append(dict(fleet_id=old["fleet_id"],device_key=old["device_key"],plant_id=pid,plant_name=old["plant_name"],
                                 eia_generator_id=old["eia_generator_id"],old_zone="D",new_zone="E",old_bus=old["bus_id"],new_bus=bid,
                                 new_parent_bus_name=bus["name"],new_mapping_distance_km=km,
                                 dispatch_eligible_default=old["dispatch_eligible_default"],source_status=old["source_status"],
                                 policy="existing_same_zone_nearest_parent_bus_rule;no_observed_flow_target;capacity_prior_PG_unchanged"))
        revised.append(new)
    require(len(landings)==55,"Unexpected corrected unit count")
    require([r["fleet_id"] for r in revised]==[r["fleet_id"] for r in original],"Fleet order changed")
    for a,b in zip(original,revised):
        require(all(a[k]==b[k] for k in fields if k not in ALLOWED),"Unit identity, admission, or capability changed")
    output.mkdir(parents=True,exist_ok=True)
    write(output/"fleet_register.csv",revised,fields)
    write(output/"changed_fields.csv",changes)
    write(output/"plant_zone_corrections.csv",sites)
    write(output/"corrected_bus_landings.csv",landings)
    for name in ["fleet_bounds.npz","fleet_bounds.mat"]:
        shutil.copyfile(FLEET/name,output/name)
        require(sha(output/name)==sha(FLEET/name),"Capacity copy is not byte identical")
    parent_out=output/"source_parent";parent_out.mkdir(exist_ok=True)
    for source in sorted((FLEET/"source_parent").iterdir()):
        if source.is_file():shutil.copyfile(source,parent_out/source.name)
    protected_unchanged=all(sha(ROOT/path)==digest for path,digest in initial.items())
    require(protected_unchanged,"Frozen input changed while building repair")
    contract=dict(prior_npz_path=str((PRIOR/"dispatch_priors.npz").relative_to(ROOT)).replace("\\","/"),
                  prior_npz_sha256=sha(PRIOR/"dispatch_priors.npz"),prior_values_copied_or_modified=False,
                  reuse_basis="hydro priors are per-plant/prime-mover split among unchanged EIA units; zone and bus do not enter those values",
                  caveat="Original zonal-prior diagnostic tables remain frozen; any corrected zonal summaries must regroup unchanged unit values using this corrected fleet")
    (output/"reuse_prior_contract.json").write_text(json.dumps(contract,indent=2)+"\n")
    source_paths=frozen+[GOLD,EIA_PLANT,OUT/"confirmed_hydro_zone_corrections.csv",OUT/"goldbook_zone_evidence.csv",Path(__file__)]
    source_paths+=sorted((FLEET/"source_parent").glob("*"))
    write(output/"source_manifest.csv",[dict(path=str(p.relative_to(ROOT)).replace("\\","/"),sha256=sha(p),role="frozen_source_or_reviewed_repair_evidence") for p in source_paths if p.is_file()])
    head=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
    receipt=dict(status="confirmed_site_zone_mapping_repair_created",created_utc=datetime.now(timezone.utc).isoformat(),
                 checkout_HEAD_at_creation=head,source_GoldBook_sha256=GOLD_SHA,inventory_rows=len(revised),
                 corrected_plants=26,corrected_inventory_generator_rows=55,changed_field_cells=len(changes),
                 corrected_admitted_dispatch_rows=sum(r["dispatch_eligible_default"]=="1" for r in landings),
                 destination_bus_counts={str(b):sum(int(r["new_bus"])==b for r in landings) for b in sorted({int(r["new_bus"]) for r in landings})},
                 all_fleet_ids_device_keys_capacity_availability_admission_fields_unchanged=True,
                 hourly_PG_prior_bounds_modified=False,optimization_weights_and_statewide_balance_target_modified=False,
                 original_builders_modified=False,original_outputs_unchanged=True,source_hashes=initial,
                 scope="only26_primary_source_confirmed_stations;otherStLawrenceCountyplants_not_reassigned",
                 existing_bus_landing_policy="same-zone nearest original retained parent bus; geography remains a coarse model proxy",
                 fleet_register_sha256=sha(output/"fleet_register.csv"),changed_fields_sha256=sha(output/"changed_fields.csv"),
                 fleet_bounds_npz_sha256=sha(output/"fleet_bounds.npz"),no_power_flow_or_annual_dispatch_run=True)
    (output/"repair_receipt.json").write_text(json.dumps(receipt,indent=2)+"\n")
    print(json.dumps(receipt,indent=2));return receipt


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--output",type=Path,default=DEFAULT)
    build(parser.parse_args().output)
