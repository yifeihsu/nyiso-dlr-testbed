"""Independent compiled-model/source readback and delivery review.

Only writes review artifacts. Model checks operate on saved arrays and a fresh
loader/policy check, without rerunning the annual AC calculation. Final map and
package gates are added only when their actual artifacts are available.
"""
from datetime import datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'output/nygrid_2025_moses_repair'
BASE=ROOT/'output/nygrid_2025_physical_repair'
DEPS={}


def sha(path):
    with Path(path).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()


def read(path):
    path=Path(path);DEPS[path.relative_to(ROOT).as_posix()]=sha(path);return path


def require(value,message):
    if not bool(value):raise AssertionError(message)


def exact(a,b,label):
    a,b=np.asarray(a),np.asarray(b)
    require(a.shape==b.shape,label+' shape differs')
    if a.dtype.kind in 'biufc' and b.dtype.kind in 'biufc':ok=np.array_equal(a,b,equal_nan=True)
    else:ok=np.array_equal(a,b)
    require(ok,label+' values differ')


def close(a,b,label,tol=1e-8):
    a,b=np.asarray(a),np.asarray(b)
    require(a.shape==b.shape and np.allclose(a,b,rtol=0,atol=tol,equal_nan=True),label)
    finite=np.isfinite(a)&np.isfinite(b)
    return float(np.max(abs(a[finite]-b[finite]),initial=0))


def model_review():
    candidate_path=read(OUT/'candidate_receipt.json');candidate=json.loads(candidate_path.read_text())
    require(candidate['passed'],'Candidate is not sealed')
    for item in candidate['files']:
        require(sha(read(ROOT/item['path']))==item['sha256'],'Frozen candidate dependency changed: '+item['path'])
    receipt=json.loads(read(OUT/'model/model_receipt.json').read_text())
    for item in receipt['model_files']:
        require(sha(read(OUT/'model'/item['name']))==item['sha256'],'Model file seal changed')
    m=loadmat(OUT/'model/latest_model.mat',simplify_cells=True)['model']
    old=loadmat(read(BASE/'model/latest_model.mat'),simplify_cells=True)['model']
    g=loadmat(read(OUT/'generation/generation_candidate.mat'),simplify_cells=True)
    routing=loadmat(read(OUT/'boundary/boundary_rerouting.mat'),simplify_cells=True)
    pv=pd.read_csv(read(OUT/'boundary/PV20_hourly_source.csv'))
    boundary_proof=json.loads(read(OUT/'boundary/boundary_verification_receipt.json').read_text())
    generation_policy=json.loads(read(OUT/'generation/generation_policy.json').read_text())
    inventory=pd.read_csv(read(OUT/'generation/StLawrence_dated_unit_admission.csv'))
    registry=pd.read_csv(read(OUT/'model/model_generator_register.csv'))
    old_registry=pd.read_csv(read(ROOT/'output/nygrid_2025_western_audit/corrected/model_generator_register.csv'))
    runtime=json.loads(read(OUT/'delivery/independent_runtime_loader_review.json').read_text())
    require(runtime['passed'] and runtime['new_AC_solves']==0 and runtime['model_sha256']==receipt['model_file']['sha256'],'Fresh runtime review is not for this model')
    require(len(registry)==1466 and registry.device_key.is_unique,'Generator identity axis changed')
    exact(registry.device_key.iloc[:1464].to_numpy(),old_registry.device_key.to_numpy(),'Original generator device identities')
    require(registry.device_key.iloc[1464]=='EIA860:2025:PLANT:2694:GEN:21' and registry.device_key.iloc[1465]=='NYISO:P34:PTID:325270:SANDBAR_BOUNDARY_PROXY','Appended compound device identities')
    require(runtime['all_thermal_tables_and_prior_physical_repair_metadata_unchanged'],'Thermal and prior physical repairs were not checked')
    q=np.asarray(m['axis']['source_qualified'],bool);gamma=float(m['scale_factor_gamma'])
    exact(q,np.asarray(old['axis']['source_qualified'],bool),'Original source qualification')
    exact(q,np.asarray(g['source_qualified'],bool),'Generation qualification')
    exact(q,np.asarray(routing['source_qualified'],bool),'Boundary qualification')
    require(q.shape==(8760,) and q.sum()==8651 and gamma==old['scale_factor_gamma'],'Physical-hour/cohort/gamma contract')
    exact(m['generator_bus_ids'][:1464],old['generator_bus_ids'],'Original generator buses')
    exact(m['generator_bus_ids'][1464:],[48,49],'Appended generator buses')
    exact(m['external']['generator_mask'][:1464],old['external']['generator_mask'],'Original external mask')
    exact(m['external']['generator_mask'][1464:],[0,1],'Native unit and boundary classification')
    b=m['boundary_injections'];require(int(b['generator_rows'])==1466 and int(b['NY_bus_ids'])==49 and int(b['source_PTIDs'])==325270 and b['fixed_Q_MVAr']==0,'PV20 compiled identity')
    require(not b['physical_meter_equivalence_certified'] and not b['AC_impedance_invented'] and not b['SouthHero_and_intervening_losses_measured'],'Compiled physical-source claims exceed the evidence')
    require(not boundary_proof['whole_2025_physical_Moses_meter_equivalence_verified'],'Boundary ledger falsely certifies the physical meter')
    require(m['moses_source_repair']['candidate_receipt_sha256']==sha(candidate_path),'Static model not bound to sealed candidate')
    require(m['moses_source_repair']['plant_hourly_generation_is_reconstruction'],'Hourly plant generation misrepresented')
    require('engineering bound' in generation_policy['StLawrence_engineering_upper_bound'],'Nameplate policy must remain an engineering assumption')
    extcap=np.asarray(m['external']['capability_proxy_MW'])
    exact(extcap[:-1],old['external']['capability_proxy_MW'],'Existing finite external proxies')
    require(extcap[-1]==0 and m['external']['boundary_proxy_cap_is_hourly_absolute_fixed_P'],'Fixed-PQ capability sentinel')
    state_checks=[]
    for si,(new,prior,p,op)in enumerate(zip(m['templates'],old['templates'],m['loss_static'],old['loss_static']),1):
        for name in ['bus','branch','dcline']:
            exact(new[name],prior[name],f'State {si} full {name} array')
        exact(p['native'][:1464],op['native'],'Existing native mask')
        exact(p['native'][1464:],[1,0],'Appended native mask')
        exact(p['external_gen_group'][:1464],op['external_gen_group'],'Existing external groups')
        exact(p['external_gen_group'][1464:],[0,12],'Appended external groups')
        exact(p['generator_share'][:1464],op['generator_share'],'Existing loss weights')
        exact(p['generator_share'][1464:],[0,0],'Appended loss weights')
        exact(p['finite_external_generator_rows'],op['finite_external_generator_rows'],'Finite loss-balancer rows')
        require(1466 not in p['finite_external_generator_rows'],'PV20 became a loss balancer')
        require(new['gen'][1465,0]==49 and np.all(new['gen'][1465,2:5]==0),'PV20 fixed Q in static template')
        require(np.all(new['gen'][1465,8:10]==new['gen'][1465,1]),'PV20 Pmin/Pmax differ from fixed P')
        for parent in [41,185,195]:
            rows=np.flatnonzero(np.asarray(p['parent'])==parent)
            exact(new['branch'][rows],prior['branch'][rows],f'Physical repair parent {parent}')
        state_checks.append(dict(state_index=si,all_bus_branch_and_six_transfer_arrays_preserved=True,
            previous_parents_41_185_195_preserved=True,fixed_boundary_zero_Q=True,PV20_excluded_from_loss_participation=True))

    hy=np.asarray(g['hydro_rows_1based'],int)-1;st=np.asarray(g['stlawrence_rows_1based'],int)-1
    pool=np.asarray(routing['ISONE_pool_rows_1based'],int)-1
    require(len(st)==16 and 1464 in st and len(pool)==9,'Source row sets differ')
    unchanged=np.setdiff1d(np.arange(1464),np.r_[hy[hy<1464],pool])
    unchanged_bounds=np.setdiff1d(np.arange(1464),st[st<1464])
    full_stl=np.empty((8760,16));full_limits=np.empty((8760,16));full_pv=np.empty(8760)
    max_errors={k:0.0 for k in ['compiled_hydro_source_MW','compiled_PV20_source_MW','compiled_ISONE_pool_MW','regional_import_preservation_MW','global_active_input_preservation_MW','hourly_native_hydro_total_preservation_MW']}
    for i,item in enumerate(m['profile_shards']):
        new=loadmat(read(OUT/'model'/item['name']),simplify_cells=True)['profiles']
        prior=loadmat(read(BASE/'model'/item['name']),simplify_cells=True)['profiles']
        sl=slice(i*4380,(i+1)*4380);good=q[sl]
        for name in ['bus_PD_MW','bus_QD_MVAr','fixed_transfer_PF_MW','dover_bank_phase_shift_deg']:
            exact(new[name],prior[name],name)
        pg=np.asarray(new['generator_PG_MW'])/gamma;oldpg=np.asarray(prior['generator_PG_MW'])/gamma
        max_errors['compiled_hydro_source_MW']=max(max_errors['compiled_hydro_source_MW'],close(pg[:,hy],g['hydro_PG_public_MW'][sl],'Compiled hydro source'))
        max_errors['compiled_PV20_source_MW']=max(max_errors['compiled_PV20_source_MW'],close(pg[:,1465],pv.PV20_SandBar_import_to_NY_proxy_MW.to_numpy()[sl],'P34 PV20 sign/gamma'))
        max_errors['compiled_ISONE_pool_MW']=max(max_errors['compiled_ISONE_pool_MW'],close(pg[:,pool],routing['ISONE_pool_PG_public_MW'][sl],'Compiled regional pool'))
        exact(new['generator_PG_MW'][:,unchanged],prior['generator_PG_MW'][:,unchanged],'Other fuel/HQ generation')
        for name in ['generator_Pmin_MW','generator_Pmax_MW']:
            exact(new[name][:,unchanged_bounds],prior[name][:,unchanged_bounds],'Other generator bounds')
            close(new[name][:,1465]/gamma,pg[:,1465],'Fixed signed PV20 bound')
        close(new['generator_Pmin_MW'][:,st]/gamma,g['stlawrence_Pmin_public_MW'][sl],'StLawrence Pmin')
        close(new['generator_Pmax_MW'][:,st]/gamma,g['stlawrence_Pmax_public_MW'][sl],'StLawrence Pmax')
        for key,err in [
            ('regional_import_preservation_MW',pg[good][:,pool].sum(axis=1)+pg[good,1465]-oldpg[good][:,pool].sum(axis=1)),
            ('global_active_input_preservation_MW',pg[good].sum(axis=1)-oldpg[good].sum(axis=1)),
            ('hourly_native_hydro_total_preservation_MW',pg[good][:,hy].sum(axis=1)-oldpg[good][:,hy[hy<1464]].sum(axis=1))]:
            max_errors[key]=max(max_errors[key],float(np.max(abs(err))))
            require(max_errors[key]<1e-7,key)
        full_stl[sl]=pg[:,st];full_limits[sl]=new['generator_Pmax_MW'][:,st]/gamma;full_pv[sl]=pg[:,1465]
    times=pd.DatetimeIndex(pd.to_datetime(g['timestamp_utc'],utc=True));months=times.tz_convert('America/New_York').month
    for month in range(1,13):
        records=inventory[inventory.month.eq(month)]
        require(len(records)==16 and records.monthly_inventory_status.eq('OP').sum()==15,'Monthly unit admission count')
        expected=records.set_index('model_gen_row_1based').loc[st+1,'engineering_Pmax_public_MW'].to_numpy()
        close(full_limits[months==month],np.broadcast_to(expected,(sum(months==month),16)),'Monthly status/capability admission')
        require(records.loc[records.monthly_inventory_status.eq('OA'),'eia_generator_id'].item()==(26 if month<=2 else 21),'Dated unit availability')
    require(np.isfinite(full_stl[q]).all() and np.isfinite(full_pv[q]).all(),'Qualified compiled profiles incomplete')
    energy=pd.read_csv(read(OUT/'generation/StLawrence_monthly_energy_ledger.csv'))
    monthly_error=[]
    for month in range(1,13):
        target=energy.loc[energy.month.eq(month),'EIA_monthly_target_MWh'].item()
        monthly_error.append(float(full_stl[months==month].sum()-target))
    require(max(abs(np.asarray(monthly_error)))<1e-5,'Compiled plant monthly energy differs from EIA targets')
    report=dict(passed=True,status='compiled_model_and_source_contract_passed_delivery_not_yet_complete',created_utc=datetime.now(timezone.utc).isoformat(),
        model_sha256=receipt['model_file']['sha256'],candidate_receipt_sha256=sha(candidate_path),source_qualified_hours=int(q.sum()),
        generator_rows=1466,native_rows=1437,PV20_fixed_PQ_row_1based=1466,PV20_bus=49,StLawrence_unit21_row_1based=1465,
        dated_unit26_row_1based=317,all_original_1464_row_identities_preserved=True,max_errors_public_MW=max_errors,
        maximum_monthly_StLawrence_energy_error_MWh=float(max(abs(np.asarray(monthly_error)))),
        state_checks=state_checks,fresh_runtime_cases=len(runtime['cases']),PV20_Q_zero_and_no_voltage_control_verified=True,
        full_physical_P32_meter_equivalence_claimed=False,monthly_unit_status_interpreted_as_engineering_availability=True,
        profile_exclusions_remain109=True,new_AC_power_flows=0,delivery_complete=False,pending=['final_map','final_documents','final_archive'],
        inputs=[dict(path=p,sha256=h)for p,h in DEPS.items()],review_script_sha256=sha(Path(__file__)))
    require(all(sha(ROOT/p)==h for p,h in DEPS.items()),'Review inputs changed during inspection')
    path=OUT/'delivery/independent_model_source_review.json';path.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k]for k in ['status','source_qualified_hours','max_errors_public_MW','maximum_monthly_StLawrence_energy_error_MWh','fresh_runtime_cases']},indent=2))


def delivery_review():
    model_gate_path=read(OUT/'delivery/independent_model_source_review.json')
    model_gate=json.loads(model_gate_path.read_text())
    require(model_gate['passed'],'Compiled model review missing')
    for item in model_gate['inputs']:
        require(sha(ROOT/item['path'])==item['sha256'],'A model-reviewed input changed: '+item['path'])
    model_path=read(OUT/'model/latest_model.mat');m=loadmat(model_path,simplify_cells=True)['model']
    gamma=float(m['scale_factor_gamma']);source=np.asarray(m['axis']['source_qualified'],bool)
    mapdir=OUT/'delivery/map'
    annual=json.loads(read(mapdir/'annual_data.json').read_text(encoding='utf-8'))
    payload=json.loads(read(mapdir/'map_data.json').read_text(encoding='utf-8'))
    require(payload['annual']==annual,'Standalone and embedded-map annual data differ')
    page_path=read(mapdir/'network_map.html');page=page_path.read_text(encoding='utf-8')
    hit=re.search(r'<script[^>]*id=["\']network-data["\'][^>]*>(.*?)</script>',page,re.S)
    require(hit is not None and json.loads(hit.group(1))==payload,'HTML payload differs from reviewed data')
    require(not re.search(r'<script[^>]+src=["\']https?://',page),'External runtime script in offline map')
    exact(np.array([x['sourceQualified']for x in annual['hours']]),source,'Map source mask')
    exact(np.array([x['hour']for x in annual['hours']]),np.arange(1,8761),'Map full physical-hour axis')
    require(annual['metadata']['compiledModelSha256']==sha(model_path),'Map points at a different model')
    require(annual['metadata']['gamma']==gamma and payload['interfaces']['gamma']==gamma,'Map public-unit gamma differs')
    require(not annual['metadata']['physicalP32MeterCorrespondenceCertified'],'Map overclaims physical meter certification')
    require('historical sign applicability' in annual['metadata']['northernBoundaryDefinition'],'Map loses the historical sign qualification')
    require('excludes all 29 external equivalents' in annual['metadata']['generationDefinition'],'Map native definition omits external rows')
    exact(annual['northernInputNames'],['St. Lawrence generation','HQ import','PV20 Sand Bar proxy import'],'Northern series names')
    northern=np.asarray(annual['northernInputsModelMW'],float);native=np.asarray(annual['zoneSeriesModelMW']['generation'],float)
    require(northern.shape==(8760,3) and native.shape==(8760,11),'Map northern/native series dimensions')
    require(np.isnan(northern[~source]).all() and np.isnan(native[~source]).all(),'Source-excluded map input values must be null')
    genb=np.asarray(m['generator_bus_ids'],int);external=np.asarray(m['external']['generator_mask'],bool)
    require(external[1463] and external[1465] and not external[1464] and (~external).sum()==1437,'Map source classification')
    registry=pd.read_csv(read(OUT/'model/model_generator_register.csv'))
    st=(pd.to_numeric(registry.plant_id,errors='coerce').to_numpy()==2694)&~external
    require(st.sum()==16,'Map StLawrence series omitted dated unit21')
    bg=dict(zip(m['templates'][0]['bus'][:,0].astype(int),np.asarray(m['loss_static'][0]['bus_group'],int)))
    groups=np.array([bg[int(bus)]for bus in genb]);map_errors=dict(northern_model_MW=0.0,native_generation_model_MW=0.0,PV20_public_sign_and_gamma_MW=0.0)
    rawpv=pd.read_csv(read(OUT/'boundary/PV20_hourly_source.csv')).PV20_SandBar_import_to_NY_proxy_MW.to_numpy()
    for i,shard in enumerate(m['profile_shards']):
        profiles=loadmat(read(OUT/'model'/shard['name']),simplify_cells=True)['profiles'];pg=np.asarray(profiles['generator_PG_MW'])
        sl=slice(i*4380,(i+1)*4380);q=source[sl]
        expected=np.column_stack([pg[:,st].sum(axis=1),pg[:,1463],pg[:,1465]])
        map_errors['northern_model_MW']=max(map_errors['northern_model_MW'],close(northern[sl][q],expected[q],'Map northern inputs'))
        zonal=np.column_stack([pg[:,(groups==zone)&~external].sum(axis=1)for zone in range(1,12)])
        map_errors['native_generation_model_MW']=max(map_errors['native_generation_model_MW'],close(native[sl][q],zonal[q],'Map native sums excluding HQ/PV20'))
    map_errors['PV20_public_sign_and_gamma_MW']=close(northern[source,2]/gamma,rawpv[source],'Public display PV20 sign/gamma')
    valid=np.array([h['qualified']for h in annual['hours']],bool);flows=np.asarray(annual['interfaceFlowsModelMW'],float)
    require(np.isnan(flows[~valid]).all(),'Unqualified solved flows shown in map')
    map_gate_names=['scientific_data_receipt.json','independent_annual_data_review.json','geography_independent_review.json','independent_ui_flow_math_review.json','independent_embedded_payload_review.json','interaction_validation.json','browser_visual_review.json','build_receipt.json']
    for name in map_gate_names:
        gate=json.loads(read(mapdir/name).read_text());require(gate['passed'],'Map gate failed: '+name)
    ui=read(ROOT/'scripts/nygrid_2025_moses_repair/delivery/map/map.js').read_text(encoding='utf-8')
    require("Number(v)/(units==='public'?Number(annual.gamma||defs.gamma):1)" in ui,'Public power conversion code changed and needs review')
    require("pv<0?'export ':'import '" in ui,'PV20 sign label code changed and needs review')

    docs=OUT/'delivery/docs';docx=read(docs/'NYGRID_2025_MOSES_REPAIR_MODEL_STRUCTURE.docx')
    # DOCX inspection uses the authoritative bundled document runtime. The
    # numerical model/map reader uses the research Python with SciPy installed.
    document_python=Path('C:/Users/Holiday/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe')
    probe="import sys,json,zipfile,xml.etree.ElementTree as E; z=zipfile.ZipFile(sys.argv[1]); x=E.fromstring(z.read('word/document.xml')); print(json.dumps(' '.join(t.text or '' for t in x.findall('.//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t'))))"
    prose=json.loads(subprocess.run([str(document_python),'-c',probe,str(docx)],capture_output=True,text=True,check=True).stdout)
    for expected in ['1,466','1,437','855 MW','historical-sign assumption','13 October 2025','27 March 2026','not certified','109']:
        require(expected in prose,'Document omitted verified identity or qualification: '+expected)
    dictionary=read(docs/'DATA_DICTIONARY.md').read_text(encoding='utf-8')
    require('sentinel' in dictionary.lower() and ('abs(PG)' in dictionary or 'absolute PG' in dictionary),'Dictionary must explain the fixed-PQ capability sentinel')
    start=read(docs/'START_HERE.md').read_text(encoding='utf-8')
    require('8,651' in start and '0 passed the' in start,'Startup guide qualification counts need review')
    render=OUT/'delivery/document_render';render_receipt=json.loads(read(render/'word_export_receipt.json').read_text())
    require(render_receipt['inputSHA256']==sha(docx),'Rendered document is stale')
    pages=sorted(render.glob('page-*.png'));require(len(pages)==11,'Changed pagination requires visual review')
    page_hashes=[dict(path=read(p).relative_to(ROOT).as_posix(),sha256=sha(p))for p in pages]
    for name in ['structure_document_content_review.json','structure_document_visual_review.json']:
        require(json.loads(read(OUT/'delivery'/name).read_text())['passed'],'Document authoring review failed')

    builder_path=read(ROOT/'scripts/nygrid_2025_moses_repair/delivery/build_package.py');builder=builder_path.read_text(encoding='utf-8')
    for expected in ["REPAIR/'model'/name",'independent_model_source_review.json','independent_runtime_loader_review.json','boundary_verification_receipt.json','SOURCE_PATH_INDEX.json',"historical_model_versions_included=False"]:
        require(expected in builder,'Package selection omits an independently checked dependency: '+expected)
    report=dict(passed=True,status='model_map_documents_and_package_selection_review_passed_ready_for_archive_build',
        created_utc=datetime.now(timezone.utc).isoformat(),compiled_model_sha256=sha(model_path),model_source_review_sha256=sha(model_gate_path),
        map_HTML_sha256=sha(page_path),map_numeric_errors=map_errors,all_8760_physical_hours_preserved=True,source_qualified_hours=int(source.sum()),
        map_qualified_flow_hours=int(valid.sum()),operating_qualified_hours=sum(h['operatingQualified']for h in annual['hours']),
        map_northern_series_includes_all16_StLawrence_units=True,map_native_generation_excludes_HQ_and_PV20=True,
        PV20_sign_and_single_gamma_conversion_verified=True,map_source_and_solution_masks_distinguished=True,
        document_sha256=sha(docx),document_inspection_runtime=str(document_python),document_pages=11,document_visual_review='All eleven rendered pages visually inspected; revised page6 with dated energization evidence re-inspected. No clipping, overlap or missing glyphs observed.',
        rendered_page_hashes=page_hashes,physical_boundary_assumptions_and_unresolved_meter_equivalence_disclosed=True,
        fixed_PQ_zero_capability_sentinel_documented=True,package_selection_review='Reviewed actual builder source: corrected model only, current documentation, source-policy evidence, all fresh review receipts and portable source-path index. Byte inventory and archive verification are separate future gates.',
        package_builder_sha256=sha(builder_path),archive_verified=False,cold_archive_execution_verified=False,archive_verification_pending=True,
        no_new_AC_power_flows_run_by_this_review=True,unresolved_content_findings=[],
        inputs=[dict(path=p,sha256=h)for p,h in DEPS.items()],review_script_sha256=sha(Path(__file__)))
    require(all(sha(ROOT/p)==h for p,h in DEPS.items()),'A reviewed delivery input changed during inspection')
    dest=OUT/'delivery/independent_delivery_review.json';dest.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k]for k in ['status','map_HTML_sha256','map_numeric_errors','document_sha256','archive_verification_pending']},indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--stage',choices=['model','delivery'],default='model');args=parser.parse_args()
    if args.stage=='model':model_review()
    else:delivery_review()
