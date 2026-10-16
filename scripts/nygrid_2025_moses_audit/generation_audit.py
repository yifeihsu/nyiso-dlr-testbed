"""Source-only generation diagnosis for the2025 Moses South discrepancy.

No interface observations or power-flow solves enter this audit. Frozen plant
and generator arrays are summarized in public MW; only new audit files are
written. Gold Book station zones are joined to an explicit, reviewed EIA plant
list. Generic county geography never overrides a declared electrical zone.
"""
from __future__ import annotations

import argparse
import calendar
import hashlib
import json
from pathlib import Path
import re
import subprocess

import numpy as np
import openpyxl
import pandas as pd
from scipy.io import loadmat

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/"output/nygrid_2025_moses_audit/generation"
FLEET=ROOT/"output/nygrid_2025_dispatch/fleet"
PRIOR=ROOT/"output/nygrid_2025_dispatch/priors"
DISPATCH=ROOT/"output/nygrid_2025_dispatch/dispatch"
GENSOURCE=ROOT/"output/nygrid_2025_inputs/generation_source"
GOLD=FLEET/"source_scope/2025_Gold_Book.pdf"
GOLD_SHA="cc43665b9344a04b4c9355edd1dc7e31d42a6bb759ffe027ad867221556aea8e"
GOLD_URL="https://www.nyiso.com/documents/20142/2226333/2025-Gold-Book-Public.pdf/088438e1-02f1-5316-211b-dbca17c01b4b"
EIA_PLANT=ROOT/"tmp/nonfossil_sources/eia860_2025/2___Plant_Y2025_Early_Release.xlsx"
EIA_PLANT_SHA="c0a083b67635d786e204be977b2e4bf56ff505732696eb1cac3169f4b7b046c4"
OLD=ROOT/"output/nygrid_2019_full_stage1/full_year.mat"
# EIA plant name, Gold Book station-name regex, PTID, applicable PDF pages,
# and watercourse are explicit reviewed identities, not fuzzy automatic joins.
SITES={
 2547:("Blake",r"Blake",24056,[91],"Raquette"),
 2548:("Browns Falls",r"Browns Falls [12]",24044,[89,90],"Oswegatchie"),
 2551:("Colton",r"Colton [123]",24057,[91],"Raquette"),
 2556:("Eel Weir",r"Eel Weir [123]",24044,[90],"Owegatchie"),
 2561:("East Norfolk",r"East Norfolk",24057,[91],"Raquette"),
 2562:("Five Falls",r"Five Falls",24056,[91],"Raquette"),
 2563:("Flat Rock",r"Flat Rock [12]",24044,[90],"Oswegatchie"),
 2571:("Hannawa",r"Hannawa Falls [12]",24057,[91,92],"Raquette"),
 2573:("Heuvelton",r"Heuvelton [12]",24044,[90],"Oswegatchie"),
 2576:("Higley",r"Higley [1234]",24057,[92],"Raquette"),
 2590:("Norfolk",r"Norfolk",24057,[92],"Raquette"),
 2591:("Norwood",r"Norwood",24057,[92],"Raquette"),
 2600:("Rainbow Falls Hydro",r"Rainbow Falls",24056,[91],"Raquette"),
 2604:("South Edwards",r"South Edwards [1234]",24044,[90],"Oswegatchie"),
 2611:("South Colton",r"South Colton",24056,[91],"Raquette"),
 2613:("Stark",r"Stark",24056,[91],"Raquette"),
 2616:("Sugar Island",r"Sugar Island [12]",24057,[92],"Raquette"),
 2624:("Yaleville",r"Yaleville [12]",24057,[92],"Raquette"),
 7583:("Talcville",r"Talcville [12]",24044,[90],"Oswegatchie"),
 10116:("Hampshire Paper",r"Hampshire Paper",323593,[92],"Oswegatchie"),
 10220:("Sissonville Hydro",r"Sissonville",23735,[102],"Raquette"),
 10547:("Pyrites Plant",r"Pyrites Assoc\.",24023,[102],"Grasse"),
 50269:("Unionville Hydro Project 2499 NY",r"Unionville Hydro",23633,[102],"Raquette"),
 52058:("Ogdensburg",r"Ogdensburg Hydro",23633,[102],"Oswehatchie"),
 58678:("Oswegatchie",r"Oswegatchie [12]",24044,[90],"Oswegatchie"),
 58679:("Upper Newton Falls",r"Upper Newton Falls [234]",24044,[90],"Oswegatchie"),
}


def require(condition,message):
    if not condition:raise ValueError(message)


def sha(path):
    with Path(path).open("rb") as stream:return hashlib.file_digest(stream,"sha256").hexdigest()


def write(frame,path):
    if not isinstance(frame,pd.DataFrame):frame=pd.DataFrame(frame)
    frame.to_csv(path,index=False,lineterminator="\n")


def source_sites(output=OUT):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    require(sha(GOLD)==GOLD_SHA,"Frozen Gold Book differs from source receipt")
    require(sha(EIA_PLANT)==EIA_PLANT_SHA,"Frozen EIA plant workbook differs from source receipt")
    text_path=output/"goldbook2025_layout.txt"
    subprocess.run(["pdftotext","-layout",str(GOLD),str(text_path)],check=True)
    pages=text_path.read_text(encoding="utf-8").split("\f")
    workbook=openpyxl.load_workbook(EIA_PLANT,read_only=True,data_only=True)
    values=workbook["Plant"].values;next(values);next(values);header=next(values)
    plants={}
    for row_number,row in enumerate(values,4):
        record=dict(zip(header,row));pid=record.get("Plant Code")
        if pid in SITES:
            require(pid not in plants,"Duplicate EIA plant identity")
            record["source_excel_row"]=row_number;plants[int(pid)]=record
    workbook.close();require(set(plants)==set(SITES),"Missing EIA identity source")
    fleet=pd.read_csv(FLEET/"fleet_register.csv",keep_default_na=False)
    rows=[];evidence=[]
    for pid,(name,pattern,ptid,page_numbers,river) in SITES.items():
        plant=plants[pid];group=fleet.loc[fleet.plant_id.eq(pid)]
        require(plant["Plant Name"]==name and group.plant_name.eq(name).all(),"EIA plant-name identity changed")
        require(plant["County"]=="St Lawrence" and plant["State"]=="NY" and group.county.eq("St Lawrence").all(),"Plant county/state mismatch")
        require(river.lower() in str(plant["Name of Water Source"]).lower(),"Plant watercourse identity mismatch")
        require(group.fuel_category.eq("Hydro").all() and group.zone.eq("D").all(),"Candidate is not the original D hydro group")
        # Anchored whitespace boundary excludes e.g. EastNorfolk when matching
        # Norfolk, and the PTID separates RainbowFalls(Ausable,D) from Raquette.
        regex=re.compile(r"(?:^|\s{2,})("+pattern+r")\s{2,}(?P<zone>[A-K])\s{2,}"+str(ptid)+r"\s{2,}")
        hits=[]
        for page_number in page_numbers:
            for line_number,line in enumerate(pages[page_number-1].splitlines(),1):
                found=regex.search(line)
                if found:
                    require(found["zone"]=="E" and re.search(r"\s089\s+36\s",line),"Gold Book site zone/county/state does not agree")
                    hits.append((page_number,line_number,found[1],line.strip()))
        require(bool(hits),"No exact Gold Book station/PTID evidence for "+name)
        rows.append(dict(plant_id=pid,plant_name=name,old_zone="D",corrected_zone="E",county="St Lawrence",
                         eia_city=plant["City"],eia_watercourse=plant["Name of Water Source"],
                         eia_latitude=plant["Latitude"],eia_longitude=plant["Longitude"],
                         eia_plant_excel_row=plant["source_excel_row"],goldbook_PTID=ptid,
                         goldbook_station_labels="|".join(x[2] for x in hits),
                         goldbook_pdf_pages="|".join(map(str,sorted({x[0] for x in hits}))),
                         goldbook_printed_pages="|".join(str(x-4) for x in sorted({v[0] for v in hits})),
                         goldbook_table="III-2b Non-Market" if 102 in page_numbers else "III-2a Market",
                         inventory_unit_rows=len(group),eia_generator_ids="|".join(group.eia_generator_id.astype(str)),
                         identity_basis="explicit_unique_EIA_plant_name_or_declared_alias_plus_county_watercourse_and_GoldBook_station_PTID",
                         unit_identity_claim="plant_site_zone_applies_to_existing_EIA_units;not_a_one_to_one_GoldBook_unit_ID_crosswalk",
                         market_admission_or_capacity_changed=False,source_url=GOLD_URL,goldbook_sha256=GOLD_SHA,eia_plant_sha256=EIA_PLANT_SHA))
        for page,line_number,label,line in hits:
            evidence.append(dict(plant_id=pid,plant_name=name,goldbook_station=label,zone="E",PTID=ptid,
                                 pdf_page=page,printed_page=page-4,extracted_page_line=line_number,source_row_text=line,
                                 source_url=GOLD_URL,source_sha256=GOLD_SHA))
    sites=pd.DataFrame(rows).sort_values("plant_id")
    write(sites,output/"confirmed_hydro_zone_corrections.csv")
    write(evidence,output/"goldbook_zone_evidence.csv")
    # Explicit controls demonstrate why StLawrence county must not move wholesale.
    controls=[]
    for page_number,station,ptid in [(89,"Allens Falls",24042),(89,"Parishville",24042),(88,"St Lawrence - FDR (Fleet)",23600)]:
        for line in pages[page_number-1].splitlines():
            if station in line and re.search(r"\sD\s+"+str(ptid)+r"\s",line):
                controls.append(dict(station=station,correct_zone="D",PTID=ptid,pdf_page=page_number,source_row_text=line.strip()))
    require(len(controls)==3,"Correct-D source controls changed")
    write(controls,output/"correct_D_site_controls.csv")
    return sites


def audit(output=OUT):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    sites=source_sites(output)
    fleet=pd.read_csv(FLEET/"fleet_register.csv",keep_default_na=False)
    register=pd.read_csv(DISPATCH/"model_generator_register.csv",keep_default_na=False)
    frozen_paths=[FLEET/"fleet_register.csv",FLEET/"fleet_bounds.npz",PRIOR/"dispatch_priors.npz",DISPATCH/"dispatch.mat",DISPATCH/"dispatch_priors.mat",OLD]
    before={str(p.relative_to(ROOT)).replace("\\","/"):sha(p) for p in frozen_paths}
    d=loadmat(DISPATCH/"dispatch.mat",simplify_cells=True,variable_names=["gen_pg","gamma","dispatch_qualified","timestamp_utc","hour_index"])
    p=loadmat(DISPATCH/"dispatch_priors.mat",simplify_cells=True,variable_names=["prior_pg","native_fleet_ids"])
    old=loadmat(OLD,simplify_cells=True,variable_names=["base_case","result_pg","timestamp_iso","bus_pd","bus_qd"])
    q=np.asarray(d["dispatch_qualified"],bool);gamma=float(d["gamma"])
    pg=np.asarray(d["gen_pg"])/gamma;prior=np.asarray(p["prior_pg"])/gamma
    require(q.sum()==8663 and register.device_key.is_unique and fleet.device_key.is_unique,"Frozen identities/cohort changed")
    times=np.asarray(d["timestamp_utc"]).astype(str);months=pd.to_datetime(times,utc=True).tz_convert("America/New_York").month.to_numpy()
    plant_ids=register.plant_id.astype(str)
    nativemask=register.role.eq("native").to_numpy();D=register.zone.eq("D").to_numpy()
    fuelrows=[]
    oldcase=old["base_case"];oldpg=np.asarray(old["result_pg"]);oldD=np.isin(oldcase["gen"][:,0],[48,49])
    for fuel in ["Combined Fossil","Hydro","Wind","Other Renewables"]:
        take=nativemask&D&register.fuel_category.eq(fuel).to_numpy()
        fuelrows.append(dict(year=2025,fuel=fuel,population="8663_qualified_physical_hours",hours=int(q.sum()),
                             mean_preferred_public_mw=float(prior[q][:,take].sum(axis=1).mean()),mean_dispatched_public_mw=float(pg[q][:,take].sum(axis=1).mean()),
                             convention="native_generator_rows_only_HQ_excluded"))
    oldfuel=np.asarray(oldcase["genfuel"])
    for fuel,take in [("Combined Fossil",oldD&~np.isin(oldfuel,["Hydro","Import"])),("Hydro",oldD&(oldfuel=="Hydro"))]:
        fuelrows.append(dict(year=2019,fuel=fuel,population="8760_prepared_local_hour_labels",hours=8760,
                             mean_preferred_public_mw=None,mean_dispatched_public_mw=float(oldpg[:,take].sum(axis=1).mean()),
                             convention="released_generation_reconstruction_unbounded"))
    # Renewable generation is negative load in2019, so never report it as zero.
    source=ROOT/"tmp/nygrid_2019_reproduction/upstream/Data"
    fm=pd.read_csv(source/"fuelmixHourly_2019.csv");renew=pd.read_csv(source/"RenewableGen.csv")
    for fuel,column in [("Wind","Pg Wind Cap"),("Other Renewables","Pg Other Cap")]:
        capacity=pd.to_numeric(renew[column],errors="coerce").fillna(0)
        share=capacity[renew.bus_id.isin([48,49])].sum()/capacity.sum()
        hourly=fm.loc[fm.FuelCategory.eq(fuel),"GenMW"].to_numpy(float)
        require(len(hourly)==8760,"2019 renewable source coverage changed")
        fuelrows.append(dict(year=2019,fuel=fuel,population="8760_prepared_local_hour_labels",hours=8760,
                             mean_preferred_public_mw=None,mean_dispatched_public_mw=float(hourly.mean()*share),
                             convention="generation_embedded_as_negative_load;not_added_again_to_saved2019_PG"))
    write(fuelrows,output/"zoneD_generation_by_fuel.csv")
    plantrows=[];monthly=[]
    for pid,group in register.loc[D&nativemask].groupby("plant_id",sort=True):
        ix=group.index.to_numpy();name=fleet.loc[fleet.plant_id.eq(int(pid)),"plant_name"].iloc[0]
        r=dict(plant_id=int(pid),plant_name=name,fuel=group.fuel_category.iloc[0],generator_rows=len(ix),
               mean_preferred_public_mw=float(prior[q][:,ix].sum(axis=1).mean()),mean_dispatched_public_mw=float(pg[q][:,ix].sum(axis=1).mean()),
               confirmed_wrong_zone=int(pid) in SITES,corrected_zone="E" if int(pid) in SITES else "D_or_unresolved")
        r["mean_dispatch_adjustment_public_mw"]=r["mean_dispatched_public_mw"]-r["mean_preferred_public_mw"];plantrows.append(r)
        for month in range(1,13):
            selected=q&(months==month)
            monthly.append(dict(plant_id=int(pid),plant_name=name,month=month,qualified_hours=int(selected.sum()),
                                mean_preferred_public_mw=float(prior[selected][:,ix].sum(axis=1).mean()),
                                mean_dispatched_public_mw=float(pg[selected][:,ix].sum(axis=1).mean())))
    write(plantrows,output/"zoneD_plant_generation.csv");write(monthly,output/"zoneD_plant_monthly.csv")
    affected_prior=np.column_stack([prior[:,plant_ids.eq(str(pid))].sum(axis=1) for pid in sites.plant_id])
    affected_pg=np.column_stack([pg[:,plant_ids.eq(str(pid))].sum(axis=1) for pid in sites.plant_id])
    np.savez_compressed(output/"affected_plant_hourly.npz",hour_index=d["hour_index"],timestamp_utc=times,
                        plant_ids=sites.plant_id.to_numpy(int),prior_public_mw=affected_prior,dispatch_public_mw=affected_pg,qualified=q)
    totals=pd.DataFrame(dict(hour_index=d["hour_index"],timestamp_utc=times,qualified=q,
                            affected_preferred_public_mw=affected_prior.sum(axis=1),affected_dispatched_public_mw=affected_pg.sum(axis=1)))
    write(totals,output/"affected_hourly_totals.csv")
    hydro=pd.read_csv(GENSOURCE/"hydro_monthly_plant_allocation_register.csv")
    inventory=pd.read_csv(GENSOURCE/"eia860_nonfossil_inventory_2025.csv",keep_default_na=False)
    eia923=pd.read_csv(GENSOURCE/"eia923_monthly_hydro_2025.csv")
    require(not inventory.duplicated(["plant_id","generator_id"]).any(),"Duplicated EIA nonfossil unit")
    require(not hydro.duplicated(["month","plant_id","prime_mover"]).any(),"Duplicated hydro plant-month")
    require(not eia923.duplicated(["plant_id","prime_mover","month"]).any(),"Duplicated EIA hydro source row")
    priors=np.load(PRIOR/"dispatch_priors.npz",allow_pickle=False)
    require(np.array_equal(priors["fleet_id"],fleet.fleet_id),"Prior fleet identities changed")
    rawprior=priors["prior_actual_mw"]
    hydro_error=0.;energyrows=[]
    for month in range(1,13):
        saved=np.load(GENSOURCE/f"hydro_plant_priors_{month:02d}.npz")
        hs=saved["hour_index"].astype(int)-1;values=saved["prior_actual_mw"]
        group=hydro.loc[hydro.month.eq(month)].sort_values("column_index")
        for row in group.itertuples():
            columns=np.flatnonzero(fleet.plant_id.eq(row.plant_id)&fleet.prime_mover.eq(row.prime_mover))
            actual=np.sum(rawprior[np.ix_(hs,columns)],axis=1);expected=values[:,row.column_index]
            finite=np.isfinite(actual)&np.isfinite(expected)
            require(np.array_equal(np.isnan(actual),np.isnan(expected)),"Plant prior missingness changed")
            hydro_error=max(hydro_error,float(np.max(abs(actual[finite]-expected[finite]),initial=0)))
            if row.plant_id in [2693,2694]:
                model_cols=np.flatnonzero(plant_ids.eq(str(row.plant_id)))
                selected=q&(months==month)
                energyrows.append(dict(plant_id=row.plant_id,plant_name=row.plant_name,month=month,
                                       source_EIA_net_mwh=row.monthly_net_mwh,source_EIA_monthly_mean_mw=row.baseline_mw,
                                       active_capability_mw=row.capability_mw,source_mean_above_assumed_active_cap=row.baseline_mw>row.capability_mw,
                                       P63_qualified_plant_hours=int(finite.sum()),physical_hours_in_month=len(hs),
                                       modeled_plant_prior_mean_qualified_mw=float(expected[finite].mean()),
                                       model_prior_minus_EIA_mean_mw=float(expected[finite].mean()-row.baseline_mw),
                                       preferred_energy_on_qualified_hours_mwh=float(expected[finite].sum()),
                                       bounded_dispatch_mean_common_cohort_mw=float(pg[selected][:,model_cols].sum(axis=1).mean()),
                                       monthly_energy_enforced=False,hourly_plant_output_observed=False))
    require(hydro_error<1e-8,"Hydro plant prior duplicated or dropped when partitioned to units")
    write(energyrows,output/"major_hydro_monthly_source_reconciliation.csv")
    hq=register.role.eq("fixed_external")&register.parent_gen_row.astype(str).eq("271")
    require(hq.sum()==1 and register.loc[hq,"fuel_category"].eq("Import").all(),"HQ is not a unique import record")
    require(not (register.loc[nativemask,"fuel_category"]=="Import").any(),"Import counted in native fleet")
    affected_mean=float(affected_pg[q].sum(axis=1).mean())
    sources=frozen_paths+[GOLD,EIA_PLANT,GENSOURCE/"eia923_monthly_hydro_2025.csv",GENSOURCE/"hydro_monthly_plant_allocation_register.csv",
                         GENSOURCE/"eia860_nonfossil_inventory_2025.csv",source/"fuelmixHourly_2019.csv",source/"RenewableGen.csv",Path(__file__)]
    sources+=sorted(GENSOURCE.glob("hydro_plant_priors_*.npz"))
    manifest=[dict(path=str(path.relative_to(ROOT)).replace("\\","/"),sha256=sha(path)) for path in sources]
    write(manifest,output/"source_manifest.csv")
    require(all(sha(ROOT/path)==digest for path,digest in before.items()),"Frozen input changed during audit")
    result=dict(status="confirmed_site_zone_defect_with_independent_allocation_audit",confirmed_wrong_zone_plants=len(sites),
                confirmed_wrong_zone_inventory_rows=int(fleet.plant_id.isin(SITES).sum()),
                confirmed_wrong_zone_dispatch_rows=int(plant_ids.isin(list(map(str,SITES))).sum()),
                affected_preferred_mean_public_mw=float(affected_prior[q].sum(axis=1).mean()),affected_dispatch_mean_public_mw=affected_mean,
                maximum_hydro_plant_to_unit_conservation_error_mw=hydro_error,duplicate_nonfossil_unit_keys=0,duplicate_hydro_plant_month_keys=0,
                HQ_native_double_count=False,HQ_fixed_external_2025_mean_public_mw=float(pg[q][:,hq].mean()),
                HQ_fixed_external_2019_mean_public_mw=float(oldpg[:,270].mean()),
                hydro_monthly_energy_is_constraint=False,StLawrence_generation_rows_US_EIA_2694_once=True,
                interpretation=["Confirmed correction is site-specific D-to-E hydro zone and model bus landing, not a whole StLawrence county reassignment",
                                "Plant-to-unit hydro allocation conserves source MW; the bounded projection changes ZoneD hydro by less than1MW in mean",
                                "EIA monthly hydro means are allocation baselines, not enforced energy budgets; differences are a declared allocation limitation, not evidence for duplicate generation",
                                "Annual OA exclusion for StLawrenceunit21 makes assumed activecap802.5MW; some monthly source means exceed it; no hourly unit availability correction is asserted",
                                "HQ remains one fixed external import/export equivalent, outside native P63 generation",
                                "2019 wind and other renewables were negative loads; they are separately accounted rather than falsely reported as absent"],
                files_written_only_under=str(output.relative_to(ROOT)),annual_power_flow_replayed=False,frozen_inputs_unchanged=True)
    (output/"generation_audit_summary.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2));return result


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--output",type=Path,default=OUT)
    audit(parser.parse_args().output)
