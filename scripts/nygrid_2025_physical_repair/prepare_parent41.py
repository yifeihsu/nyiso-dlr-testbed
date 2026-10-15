"""Freeze the existing imported-R/X conductor candidate without PF fitting."""
from pathlib import Path
from datetime import datetime,timezone
import importlib.util,hashlib,json
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/nygrid_2025_physical_repair/physics'
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def main():
    OUT.mkdir(parents=True,exist_ok=True)
    inference=ROOT/'scripts/nygrid_2025_conductor_inference/infer_conductors.py'
    spec=importlib.util.spec_from_file_location('repair_rx_inference',inference);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    summary,candidates=mod.infer(.0018,.0089,115.,100.,.07)
    assert len(candidates)==32
    c=candidates[0];assert c['catalog_id']=='PRYSMIAN_ACSS_MALLARD_795_0_30_19' and c['circuits']==4 and c['bundle_count']==1
    catalog=pd.read_csv(mod.CATALOG);con=catalog.set_index('catalog_id').loc[c['catalog_id']].to_dict();con['catalog_id']=c['catalog_id']
    electrical=mod.physics.electrical(con,c['length_m'],c['circuits'],c['bundle_count'],c['GMD_m'],c['bundle_spacing_m'],c['reference_temperature_C'],115.,100.)
    old_path=ROOT/'output/nygrid_2025_ac_system/branches/thermal_segments.csv'
    s=pd.read_csv(old_path).query('branch_row == 41').iloc[0].to_dict()
    for key in ['catalog_id','diameter_m','gmr_m','r_ac25_ohm_per_m','r_ac75_ohm_per_m','r_ac200_ohm_per_m','heat_capacity_j_m_k','emissivity','absorptivity','temperature_min_c','temperature_max_c','reference_temperature_c']:s[key]=con[key]
    s.update(segment_length_m=c['length_m'],circuits=c['circuits'],bundle_count=c['bundle_count'],gmd_m=c['GMD_m'],bundle_spacing_m=c['bundle_spacing_m'],
             reference_r_pu=.0018,reference_x_pu=.0089,reference_b_pu=c['derived_B_pu'],r_ref_ohm_per_m_per_subconductor=c['conductor_reference_resistance_ohm_per_m'],
             reactance_ohm_per_m_per_circuit=electrical['x_ohm_per_m_per_circuit'] if 'x_ohm_per_m_per_circuit' in electrical else .0089*115**2/100*c['circuits']/c['length_m'],
             capacitance_f_per_m_per_circuit=c['derived_B_pu']/(mod.physics.OMEGA*c['circuits']*c['length_m']*(115**2/100)),
             parameter_basis='imported_RX_conditioned_synthetic_catalog_realization_with_geometric_B',
             route_length_verified=False,installed_conductor_identified=False,current_gamma_lift=False,
             parallel_circuit_mutual_coupling_modeled=False,bare_overhead_thermal_model_applicable=True)
    for k,v in list(s.items()):
        if hasattr(v,'item'):s[k]=v.item()
    sources=[Path(__file__),inference,mod.ENGINE,mod.CATALOG,mod.GEOMETRY,old_path,ROOT/'output/nygrid_2025_conductor_inference/feasible_candidate_realizations.csv']
    plan={'schema_version':1,'created_utc':datetime.now(timezone.utc).isoformat(),'parent':41,
          'baseline_R_X_B':[.0598327463184317,.2040452503006289,.024765209011782266],
          'repaired_R_X_B':[.0018,.0089,c['derived_B_pu']],
          'selection_policy':'Use rank1 of the already-declared imported-RX catalog/geometry inference with originalB used only for ranking; no PF, voltage, interface residual or geographic chord selects parameters.',
          'candidate_count':len(candidates),'selected_candidate':c,'thermal_segment':s,
          'thermal_registry_parameter_basis':s['parameter_basis'],'thermal_registry_length_min_m':5.,'thermal_registry_length_max_m':250000.,
          'terminal_current_policy':'Retain the existing aggregate2000A apparatus ceiling independently of the four-circuit conductor hypothesis; do not multiply hardware capacity or relax a limit to obtain qualification.',
          'source_static_MVA_limits_changed':False,'installed_asset_identity_claimed':False,
          'geometric_B_differs_from_imported_B':True,'imported_B_pu':.07,
          'sources':[{'path':p.relative_to(ROOT).as_posix(),'sha256':sha(p)} for p in sources]}
    target=OUT/'parent41_parameters.json'
    if target.exists():
        old=json.loads(target.read_text());a=old.copy();b=plan.copy();a.pop('created_utc');b.pop('created_utc');assert a==b
    else:target.write_text(json.dumps(plan,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({'parent':41,'new_RXB':plan['repaired_R_X_B'],'catalog':c['catalog_id'],'length_m':c['length_m'],'circuits':c['circuits']}))
if __name__=='__main__':main()
