"""Separate historical DC permutation invariance from physical circuit identity."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from scipy.io import loadmat

from audit_source_crosswalk import ROOT, OUT, PINS, VARIANTS, require, sha, maxabs, branch_law


def build():
    before={p:sha(ROOT/p) for p in PINS}
    require(before==PINS,"Pinned source changed")
    ledger=pd.read_csv(OUT/"PERFORM_source_to_model.csv",keep_default_na=False)
    receipt=json.loads((OUT/"source_crosswalk_receipt.json").read_text())
    require(receipt["passed"] and receipt["outputs"]["PERFORM_source_to_model.csv"]==sha(OUT/"PERFORM_source_to_model.csv"),"Crosswalk receipt mismatch")
    full=loadmat(ROOT/"output/nygrid_2025_downstate/network/network_cases.mat",simplify_cells=True)
    slim=loadmat(ROOT/"output/nygrid_2025_slim/network/network_cases.mat",simplify_cells=True)
    mapped=ledger[(ledger.full191_branch_row>0)&(ledger.individual_RAW_identity_resolved==0)]
    records=[]
    for candidates,group in mapped.groupby("raw_identity_candidates"):
        all_group=ledger[ledger.raw_identity_candidates==candidates]
        complete=len(group)==len(all_group)==len(candidates.split(";"))
        rows=group.full191_branch_row.to_numpy(int)-1
        signs=np.where(group.source_from_bus.to_numpy(int)<group.source_to_bus.to_numpy(int),1.,-1.)
        for variant in VARIANTS:
            F,phase,_=branch_law(full[variant+"_case"])
            recovery=slim["recovery"][variant]
            H=(F@recovery["angle_lift"])[rows]*signs[:,None]
            h=(F@recovery["angle_offset"]+phase)[rows]*signs
            spread=maxabs(H-H[0]);offsetspread=maxabs(h-h[0])
            records.append(dict(raw_identity_candidates=candidates,variant=variant,
                                source_rows=";".join(map(str,group.source_branch_row)),
                                full191_rows=";".join(map(str,group.full191_branch_row)),
                                source_from_name=group.iloc[0].source_from_name,source_to_name=group.iloc[0].source_to_name,
                                candidate_count=len(candidates.split(";")),historical_source_rows_in_group=len(all_group),
                                embedded_rows=len(group),complete_historical_parallel_bundle=complete,
                                max_oriented_operator_spread_MW_per_rad=spread,max_offset_spread_model_MW=offsetspread,
                                historical_DC_individual_operator_permutation_invariant=bool(complete and spread<1e-8 and offsetspread<1e-8),
                                historical_DC_bundle_sum_permutation_invariant=complete,
                                physical_circuit_identity_resolved=False,physical_2025_identity_established=False,
                                promotion_rule="separate_2025_terminal_lineage_member_count_status_metering_required"))
    result=pd.DataFrame(records)
    require(len(result)==26*5,"Parallel group audit coverage changed")
    after={p:sha(ROOT/p) for p in PINS}
    require(before==after,"Input changed during audit")
    result.to_csv(OUT/"historical_parallel_identity_checks.csv",index=False)
    report=dict(passed=True,created_utc=datetime.now(timezone.utc).isoformat(),groups=26,group_state_checks=len(result),
                complete_historical_bundle_checks=int(result.complete_historical_parallel_bundle.sum()),
                historical_DC_individual_operator_permutation_invariant_checks=int(result.historical_DC_individual_operator_permutation_invariant.sum()),
                max_oriented_operator_spread_MW_per_rad=float(result.max_oriented_operator_spread_MW_per_rad.max()),
                physical_2025_identity_established=False,observations_used=False,source_hashes_unchanged=True,
                limitations="Historical numerical permutation invariance never establishes a utility circuit number, 2025 member list, in-service status, resection lineage, or actual meter-end losses.",
                inputs={**before,"source_crosswalk_receipt.json":sha(OUT/"source_crosswalk_receipt.json"),"PERFORM_source_to_model.csv":sha(OUT/"PERFORM_source_to_model.csv")},
                outputs={"historical_parallel_identity_checks.csv":sha(OUT/"historical_parallel_identity_checks.csv")},script_sha256=sha(__file__))
    (OUT/"parallel_identity_receipt.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({k:report[k] for k in ["passed","groups","group_state_checks","complete_historical_bundle_checks","historical_DC_individual_operator_permutation_invariant_checks","max_oriented_operator_spread_MW_per_rad"]},indent=2))


if __name__=="__main__":
    build()
