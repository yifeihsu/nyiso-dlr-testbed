"""Paired annual DC replay with immutable generator output and source cohort.

No observation is loaded here. Numeric network assumptions are declared by the
construction register; interface observations are read only by score_refinement.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from scipy.io import loadmat, savemat

ROOT = Path(__file__).resolve().parents[2]
DEFAULT = ROOT / "output/nygrid_2025_downstate"
BASELINE = ROOT / "output/nygrid_2025_dispatch/dispatch"
sys.path.insert(0, str(ROOT / "scripts/nygrid_2019"))
from replay_dc import network, predict
from validate_refinement import zone_interface_operators, parent_operator_definitions


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def state_schedule(times, dated):
    if not dated:
        return np.full(len(times), "refined_2025_case", dtype=object)
    states = np.full(len(times), "refined_2025_pre_may_case", dtype=object)
    for date, key in [("2025-05-21T04:00:00Z", "refined_2025_may21_case"),
                      ("2025-05-30T04:00:00Z", "refined_2025_may30_case"),
                      ("2025-12-20T04:00:00Z", "refined_2025_case")]:
        states[np.asarray(times).astype(str) >= date] = key
    return states


def replay(folder=DEFAULT):
    folder = Path(folder).resolve()
    output = folder / "replay"
    output.mkdir(parents=True, exist_ok=True)
    baseline_reference = json.loads((folder / "validation/baseline_reference.json").read_text())
    for item in baseline_reference["artifacts"]:
        require(sha(ROOT / item["path"]) == item["sha256"], "Frozen baseline changed: " + item["path"])
    d = loadmat(BASELINE / "dispatch.mat", simplify_cells=True)
    saved_parent = loadmat(BASELINE / "dispatch_network.mat", simplify_cells=True)
    n = loadmat(folder / "network/network_cases.mat", simplify_cells=True)
    busreg = pd.read_csv(folder / "network/bus_register.csv", keep_default_na=False)
    zones = dict(zip(busreg.model_bus.astype(int), busreg.accounting_zone.astype(str)))
    gamma = float(d["gamma"])
    require(gamma == float(n["gamma"]), "Frozen scale changed")
    valid = np.asarray(d["dispatch_qualified"], bool)
    hours = np.asarray(d["hour_index"], int)
    times = np.asarray(d["timestamp_utc"]).astype(str)
    parent = d["base_case"]
    definitions = parent_operator_definitions(parent, {int(k): zones[int(k)] for k in parent["bus"][:, 0]})
    (output / "interface_definitions.json").write_text(json.dumps(definitions, indent=2) + "\n")
    plans = [
        ("expanded_identity", "expanded_identity_case", "identity"),
        ("source_detail_2019", "refined_2019_case", "identity"),
        ("upgrades_year_end", "refined_2025_case", "identity"),
        ("upgrades_dated", "dated", "identity"),
        ("assets_year_end", "refined_2025_case", "asset"),
        ("assets_dated", "dated", "asset"),
        ("nyes_assumption_year_end", "refined_2025_nyes_case", "asset"),
    ]
    rows, membership = [], []
    for name, state, mapping in plans:
        states = state_schedule(times, True) if state == "dated" else np.full(len(hours), state, object)
        W = np.asarray(n["load_allocation_" + mapping], float)
        load = np.asarray(d["bus_pd"]) @ W.T
        pg, dc = np.asarray(d["gen_pg"]), np.asarray(d["dc_pf"])
        nb, nl = W.shape[0], len(n[states[0]]["branch"])
        flow, angle, interface = [np.full((len(hours), width), np.nan) for width in [nl, nb, 7]]
        residual, slack = np.full(len(hours), np.nan), np.full(len(hours), np.nan)
        for key in sorted(set(states)):
            indices = np.flatnonzero(valid & (states == key))
            require(len(indices) > 0, "Topology state has no qualified hours")
            case = copy.deepcopy(n[key])
            case["gen"][:, 0] = n["generator_bus_" + mapping]
            result = predict(network(case), load[indices], pg[indices], dc[indices])
            maximum_slack = np.max(abs(result["result_pg"] - pg[indices]))
            require(maximum_slack < 1e-7, "Refinement would require redispatch or slack adjustment")
            op = zone_interface_operators(case, zones)
            flow[indices], angle[indices] = result["flow"], result["angle_deg"]
            id_lookup = {int(value): j for j, value in enumerate(case["bus"][:, 0])}
            refs = np.array([id_lookup[int(value)] for value in np.asarray(d["reference_bus"])[indices]])
            angle[indices] -= angle[indices, refs][:, None]
            interface[indices] = flow[indices] @ op.T
            residual[indices] = result["nodal_residual_mw"]
            slack[indices] = np.max(abs(result["result_pg"] - pg[indices]), axis=1)
            for j, definition in enumerate(definitions):
                for br in np.flatnonzero(op[j]):
                    membership.append(dict(variant=name, state=key, interface=definition["interface"],
                        branch_row=br + 1, branch_key=str(n["branch_keys"][br]), coefficient=op[j, br]))
        if name == "expanded_identity":
            require(np.max(abs(interface[valid] - saved_parent["inherited_interface_pf"][valid])) < 1e-7,
                    "Algebraic expansion changed inherited interface flows")
            require(np.max(abs(angle[valid, :140] - saved_parent["bus_va"][valid])) < 1e-7,
                    "Algebraic expansion changed retained bus angles")
        payload = dict(hour_index=hours, timestamp_utc=times.astype(object), qualified=valid,
            network_state_ids=states, branch_pf=flow, bus_va=angle, interface_pf=interface,
            reference_bus=d["reference_bus"], gamma=gamma, load_allocation_name=mapping,
            generator_mapping_name=mapping, nodal_residual_mw=residual, hypothetical_slack_change_mw=slack)
        path = output / (name + ".mat")
        savemat(path, payload, do_compression=True, oned_as="column")
        row = dict(variant=name, qualified_hours=int(valid.sum()), source_gap_hours=int((~valid).sum()),
            buses=nb, branch_records=nl, generator_count=pg.shape[1], dc_channels=dc.shape[1],
            maximum_nodal_residual_model_mw=float(np.nanmax(residual)),
            maximum_hypothetical_slack_change_model_mw=float(np.nanmax(slack)),
            injection_mapping=mapping, chronology="dated_2025" if state == "dated" else "fixed_topology",
            file=path.relative_to(ROOT).as_posix(), sha256=sha(path))
        rows.append(row)
        print(json.dumps(row), flush=True)
    pd.DataFrame(rows).to_csv(output / "replay_summary.csv", index=False, lineterminator="\n")
    pd.DataFrame(membership).to_csv(output / "interface_membership.csv", index=False, lineterminator="\n")
    dependencies = [BASELINE / f for f in ["dispatch.mat", "dispatch_bounds.mat", "dispatch_network.mat"]]
    dependencies += [folder / "network/network_cases.mat", folder / "network/bus_register.csv", Path(__file__),
                     Path(__file__).with_name("validate_refinement.py"), ROOT / "scripts/nygrid_2019/replay_dc.py"]
    receipt = dict(status="completed_fixed_dispatch_DC_replay", qualified_hours=int(valid.sum()),
        missing_source_hours=int((~valid).sum()), frozen_gamma=gamma,
        plotted_MW_conversion="public_equivalent_MW = model_MW / frozen_gamma",
        per_device_generation_and_bounds="referenced_unchanged_from_frozen_baseline",
        bus_PD_QD="baseline_hourly_arrays multiplied by declared allocation transpose",
        DC_schedules_and_endpoints="unchanged_four_signed_channels",
        observation_data_read=False, physical_2025_flowgate_membership_verified=False,
        project_status_precision="RCC day-only dates activate next local midnight; Dover HB23 activates2025-12-20T04Z",
        dependencies=[dict(path=p.relative_to(ROOT).as_posix(), sha256=sha(p)) for p in dependencies], variants=rows)
    (output / "provenance.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--folder", type=Path, default=DEFAULT)
    replay(parser.parse_args().folder)
