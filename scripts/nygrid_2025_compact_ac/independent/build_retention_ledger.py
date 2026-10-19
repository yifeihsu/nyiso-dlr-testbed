"""Readable union bus ledger with independent retention reasons by topology."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json
import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'output/nygrid_2025_compact_ac/independent'


def record(p):
    with p.open('rb') as f:h=hashlib.file_digest(f,'sha256').hexdigest()
    return dict(path=p.relative_to(ROOT).as_posix(),sha256=h)


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    anchors_path=ROOT/'output/nygrid_2025_slim/network/bus_register.csv'
    fixture_path=ROOT/'output/nygrid_2025_ac_system/branches/sectioned_design_fixtures.mat'
    lineage_path=ROOT/'output/nygrid_2025_acpf_profile_audit/structure/bus_lineage_all267.csv'
    anchors=pd.read_csv(anchors_path).model_bus.to_numpy(int);anchor_set=set(anchors)
    lineage=pd.read_csv(lineage_path).set_index('model_bus')
    d=loadmat(fixture_path,simplify_cells=True)
    items={};summaries=[]
    for state in ['pre_may','may21','may30','post_dover']:
        m=d['cases'][state];bus=np.asarray(m['bus']);names=np.asarray(m['bus_name']).astype(str)
        gen_bus=set(np.asarray(m['gen'])[:,0].astype(int))
        dc_bus=set(np.asarray(m['dcline'])[:,:2].astype(int).reshape(-1))
        kept=eliminated=shunted_eliminated=0
        for i,row in enumerate(bus):
            bid=int(row[0]);anchor=bid in anchor_set
            flags=dict(requested_148_anchor=anchor,nonzero_specified_P_Q=bool(np.any(row[2:4]!=0)),
                registered_generator_terminal=bid in gen_bus,controlled_transfer_terminal=bid in dc_bus,
                PV_or_reference_bus=bool(row[1] in [2,3]),fixed_bus_shunt_present=bool(np.any(row[4:6]!=0)))
            needed=any(flags[k] for k in ['nonzero_specified_P_Q','registered_generator_terminal','controlled_transfer_terminal','PV_or_reference_bus'])
            retain=anchor or needed
            kept+=int(retain);eliminated+=int(not retain);shunted_eliminated+=int(not retain and flags['fixed_bus_shunt_present'])
            if bid not in items:
                l=lineage.loc[bid]
                items[bid]=dict(bus_id=bid,bus_name=names[i],nominal_kV=float(row[9]),
                    lineage_kind=str(l.lineage_kind),source_key=str(l.source_key),
                    requested_148_anchor=anchor,
                    reason='requested_retained_interface' if anchor else 'passive_zero_specified_injection;voltage_and_branch_currents_recovered',
                    is_new_physical_substation_claim=False,dated_states={})
            items[bid]['dated_states'][state]=dict(present=True,retained=retain,
                full_bus_type=int(row[1]),reason_flags=flags,PD_MW=float(row[2]),QD_MVAr=float(row[3]),
                GS_MW_at1pu=float(row[4]),BS_MVAr_at1pu=float(row[5]),
                fixed_shunt_retained_in_Y_even_if_bus_eliminated=True)
        assert kept==148 and eliminated==len(bus)-148
        summaries.append(dict(state=state,full_bus_count=len(bus),retained_count=kept,eliminated_count=eliminated,
            additional_required_nodes_above_requested148=0,eliminated_buses_with_fixed_shunts=shunted_eliminated))
    for entry in items.values():
        for state in ['pre_may','may21','may30','post_dover']:
            entry['dated_states'].setdefault(state,dict(present=False,retained=False))
    assert len(items)==267 and set(anchors)=={k for k,v in items.items() if v['requested_148_anchor']}
    result=dict(passed=True,created_utc=datetime.now(timezone.utc).isoformat(),
        scope='Independent retained/eliminated reasons for the requested 148-bus interface across four dated detailed fixtures',
        minimality_claim='No extra node is required above the user-chosen 148 for this fixed-control model; global minimum order is not proved.',
        convention='Fixed shunts belong to Y and do not create nonlinear specified-injection ports.',
        summaries=summaries,buses=[items[k] for k in sorted(items)],
        dependencies=[record(p) for p in [anchors_path,fixture_path,lineage_path,Path(__file__)]])
    (OUT/'bus_retention_ledger.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(passed=True,canonical_buses=len(items),summaries=summaries),indent=2))


if __name__=='__main__':main()
