"""Read-only CE/TE physical-scope diagnosis using a source-directed PV20 term."""
from datetime import datetime,timezone
import hashlib,json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'output/nygrid_2025_postrepair_diagnosis/boundary'
REPAIR=ROOT/'output/nygrid_2025_moses_repair'
DEPS={}


def sha(p):
    with Path(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()


def read(p):
    p=Path(p);DEPS[p.relative_to(ROOT).as_posix()]=sha(p);return p


def require(v,msg):
    if not bool(v):raise AssertionError(msg)


def stats(pred,obs,mask):
    p=np.asarray(pred)[mask];o=np.asarray(obs)[mask];e=p-o
    require(np.isfinite(e).all(),'Nonfinite prediction on fixed cohort')
    return dict(hours=len(e),MAE_MW=float(abs(e).mean()),RMSE_MW=float(np.sqrt(np.mean(e**2))),
        bias_MW=float(e.mean()),WAPE_percent=float(100*abs(e).sum()/abs(o).sum()),
        p95_absolute_error_MW=float(np.quantile(abs(e),.95)),positive_error_hours=int((e>0).sum()),
        mean_prediction_MW=float(p.mean()),mean_observation_MW=float(o.mean()))


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    contract=json.loads(read(Path(__file__).with_name('readout_contract.json')).read_text())
    apath=read(REPAIR/'annual/moses_repair_v1/comparison/comparison_arrays.npz')
    a=np.load(apath);names=a['interface_names'].astype(str).tolist();q=a['paired_qualified'].astype(bool)
    require(q.sum()==8651 and np.array_equal(q,a['source_qualified']) and np.array_equal(q,a['candidate_qualified']) and np.array_equal(q,a['current_baseline_qualified']),'Cohorts differ')
    old=np.load(read(ROOT/'output/nygrid_2025_physical_repair/annual/physical_repair_v1/comparison/comparison_arrays.npz'))
    current=a['candidate_legacy_signed_literal_from'];baseline=a['current_baseline_legacy_signed_literal_from'];observed=a['observed']
    require(np.allclose(baseline,old['candidate_legacy_signed_literal_from'],equal_nan=True,rtol=0,atol=1e-10),'Baseline readout changed')
    require(np.array_equal(a['timestamp_utc'],old['timestamp_utc']) and len(q)==8760,'Physical clocks differ')
    pv=pd.read_csv(read(REPAIR/'boundary/PV20_hourly_source.csv'))
    require(np.array_equal(pv.timestamp_utc.to_numpy(str),a['timestamp_utc'].astype(str)),'PV20 source axis differs')
    imported=pv.PV20_SandBar_import_to_NY_proxy_MW.to_numpy();exported=-imported
    require(np.isfinite(exported[q]).all() and (exported[q]>=0).all(),'Current qualified PV20 source coverage/sign differs')
    aggregation=[]
    for method in ['backward_hold','linear','arithmetic_mean']:
        difference=pv[f'PV20_{method}_import_to_NY_proxy_MW'].to_numpy()[q]-imported[q]
        aggregation.append(dict(method=method,hours=int(q.sum()),mean_difference_MW=float(difference.mean()),
            mean_absolute_difference_MW=float(abs(difference).mean()),maximum_absolute_difference_MW=float(abs(difference).max()),
            full_physical_measurement_uncertainty_bound=False))
    pd.DataFrame(aggregation).to_csv(OUT/'PV20_aggregation_sensitivity_scale.csv',index=False,lineterminator='\n')
    time=pd.DatetimeIndex(pd.to_datetime(a['timestamp_utc'].astype(str),utc=True));month=time.tz_convert('America/New_York').month.to_numpy()
    terms=pd.read_csv(read(ROOT/'output/nygrid_2025_acpf_profile_audit/alignment/interface_operator_terms.csv'))
    operator_contract=json.loads(read(ROOT/'output/nygrid_2025_acpf_profile_audit/alignment/interface_operator_contract.json').read_text())
    require(operator_contract['p32_physical_flowgate_binding']=='unestablished','Review changed operator qualification')
    defs=pd.read_csv(read(ROOT/'output/nygrid_2025_flowgate_definitions/definitions/all_seasonal_members.csv'))
    physical=defs.loc[defs.gate_id.isin(['central_east','total_east','moses_south'])].copy()
    pvdefs=physical[physical.circuit_id.astype(str).eq('PV20')]
    require(len(pvdefs)==6 and set(pvdefs.gate_id)=={'central_east','total_east'} and pvdefs.source_zone_direction.eq('D -> N').all(),'Official PV20 scope changed')
    require(pvdefs.metered_end.eq('from').all(),'PV20 meter end changed')
    physical.to_csv(OUT/'official_seasonal_membership.csv',index=False,lineterminator='\n')
    physical.groupby(['gate_id','edition','source_zone_direction']).size().reset_index(name='printed_terms').to_csv(OUT/'official_boundary_family_counts.csv',index=False,lineterminator='\n')
    for p,h in physical[['source_pdf','source_pdf_sha256']].drop_duplicates().itertuples(index=False,name=None):
        require(sha(read(ROOT/p))==h,'Official definition source changed')
    m=loadmat(read(REPAIR/'model/latest_model.mat'),simplify_cells=True)['model']
    state_rows=[]
    for state,template,policy in zip(['pre_may','may21','may30','post_dover'],m['templates'],m['loss_static']):
        groups=dict(zip(template['bus'][:,0].astype(int),np.asarray(policy['bus_group'],int)))
        selected=terms[terms.state.eq(state)]
        te=selected[selected.interface.eq('TOTAL EAST')].set_index('original_branch_row').coefficient.to_dict()
        ce=selected[selected.interface.eq('CENTRAL EAST - VC')].set_index('original_branch_row').coefficient.to_dict()
        require(te=={33:-1,36:-1,40:-1,42:-1,224:1} and ce=={33:-1,36:-1,40:-1,42:-1},'Frozen TE/CE identity changed')
        for row in selected[selected.interface.isin(['TOTAL EAST','CENTRAL EAST - VC','MOSES SOUTH'])].itertuples(index=False):
            state_rows.append(dict(state=state,interface=row.interface,parent=row.original_branch_row,coefficient=row.coefficient,
                from_bus=row.original_from_bus,to_bus=row.original_to_bus,from_group=int(groups[row.original_from_bus]),to_group=int(groups[row.original_to_bus]),
                explicit_PV20_term=False,physical_circuit_mapping_certified=False))
    pd.DataFrame(state_rows).to_csv(OUT/'frozen_operator_scope.csv',index=False,lineterminator='\n')
    jte,jce,jmo=[names.index(x)for x in ['TOTAL EAST','CENTRAL EAST - VC','MOSES SOUTH']]
    h=pd.DataFrame(dict(hour_index=a['hour_index'],timestamp_utc=a['timestamp_utc'],month_local=month,qualified=q,
        PV20_import_proxy_MW=imported,PV20_outward_export_proxy_MW=exported))
    metrics=[];effects=[]
    for label,j in [('TOTAL EAST',jte),('CENTRAL EAST - VC',jce),('MOSES SOUTH',jmo)]:
        h[label+'_observation_MW']=observed[:,j]
        for model,pred in [('baseline',baseline[:,j]),('candidate',current[:,j])]:
            h[label+'_'+model+'_legacy_MW']=pred
            variants={'legacy':pred}
            if label!='MOSES SOUTH':variants['legacy_plus_PV20_export_proxy']=pred+exported
            for variant,value in variants.items():
                h[label+'_'+model+'_'+variant+'_residual_MW']=value-observed[:,j]
                for mo in range(13):
                    mask=q if mo==0 else q&(month==mo)
                    metrics.append(dict(interface=label,model=model,readout=variant,month=mo,**stats(value,observed[:,j],mask),
                        physical_P32_operator_certified=False,new_AC_solve=False,default_promoted=False))
        for mo in range(13):
            mask=q if mo==0 else q&(month==mo);delta=current[mask,j]-baseline[mask,j]
            effects.append(dict(interface=label,month=mo,hours=int(mask.sum()),mean_candidate_minus_baseline_MW=float(delta.mean()),
                mean_absolute_candidate_minus_baseline_MW=float(abs(delta).mean()),mean_PV20_export_proxy_MW=float(exported[mask].mean()),
                qualified_zero_PV20_hours=int((exported[mask]==0).sum())))
    h['baseline_TE_minus_CE_parent224_readout_MW']=baseline[:,jte]-baseline[:,jce]
    h['candidate_TE_minus_CE_parent224_readout_MW']=current[:,jte]-current[:,jce]
    h['observed_TE_minus_CE_MW']=observed[:,jte]-observed[:,jce]
    h['candidate_minus_baseline_parent224_readout_MW']=h.candidate_TE_minus_CE_parent224_readout_MW-h.baseline_TE_minus_CE_parent224_readout_MW
    pd.DataFrame(metrics).to_csv(OUT/'readout_sensitivity_metrics.csv',index=False,lineterminator='\n')
    pd.DataFrame(effects).to_csv(OUT/'candidate_readout_changes.csv',index=False,lineterminator='\n')
    h.to_csv(OUT/'hourly_boundary_readouts.csv',index=False,lineterminator='\n')
    # Rebuild the complete current northern input identity without solving PF.
    # Here the model's gross-load convention absorbs its declared loss shares;
    # this exact model identity is not a physical-meter equivalence certificate.
    gamma=float(a['gamma']);genbus=np.asarray(m['generator_bus_ids'],int)
    ext=np.asarray(m['external']['generator_mask'],bool)
    groups=dict(zip(m['templates'][0]['bus'][:,0].astype(int),np.asarray(m['loss_static'][0]['bus_group'],int)))
    require(np.array_equal(m['templates'][0]['bus'][:140,0],np.arange(1,141)),'Gross-profile bus order changed')
    nativeD=(~ext)&np.array([groups[int(b)]==4 for b in genbus])
    reg=pd.read_csv(read(REPAIR/'model/model_generator_register.csv'))
    stl=(pd.to_numeric(reg.plant_id,errors='coerce').to_numpy()==2694)&~ext
    require(stl.sum()==16 and (nativeD[stl]).all(),'Plant/zone allocation changed')
    dload=np.array([groups[b]==4 for b in range(1,141)])
    north=pd.DataFrame(dict(hour_index=a['hour_index'],timestamp_utc=a['timestamp_utc'],qualified=q))
    fields=['native_D_MW','StLawrence_MW','HQ_import_MW','Ontario_PAR_import_MW','PV20_import_proxy_MW','gross_D_load_MW']
    values=np.full((8760,len(fields)),np.nan)
    for si,item in enumerate(m['profile_shards']):
        block=loadmat(read(REPAIR/'model'/item['name']),simplify_cells=True)['profiles']
        take=slice(si*4380,(si+1)*4380);pg=np.asarray(block['generator_PG_MW'])/gamma
        values[take]=np.column_stack([pg[:,nativeD].sum(axis=1),pg[:,stl].sum(axis=1),pg[:,1463],
            np.asarray(block['fixed_transfer_PF_MW'])[:,4:6].sum(axis=1)/gamma,pg[:,1465],
            np.asarray(block['bus_PD_MW'])[:,dload].sum(axis=1)/gamma])
    for k,name in enumerate(fields):north[name]=values[:,k]
    north['other_native_D_MW']=north.native_D_MW-north.StLawrence_MW
    north['input_midpoint_MW']=north.native_D_MW+north.HQ_import_MW+north.Ontario_PAR_import_MW+north.PV20_import_proxy_MW-north.gross_D_load_MW
    solved_mid=(a['candidate_oriented_source_side'][:,jmo]+a['candidate_oriented_target_side'][:,jmo])/2
    north['saved_midpoint_MW']=solved_mid
    north['signed_terminal_correction_MW']=current[:,jmo]-solved_mid
    north['primary_Moses_MW']=current[:,jmo];north['observed_Moses_MW']=observed[:,jmo]
    north['current_residual_MW']=current[:,jmo]-observed[:,jmo]
    north['identity_error_MW']=north.input_midpoint_MW+north.signed_terminal_correction_MW-current[:,jmo]
    identity_error=float(np.max(abs(north.identity_error_MW[q])))
    require(identity_error<1e-8,'Current northern input identity does not close')
    north.to_csv(OUT/'northern_balance_identity.csv',index=False,lineterminator='\n')
    for p in [
        'output/nygrid_2025_flowgate_definitions/definitions/central_north_2025_qualifiers.json',
        'output/nygrid_2025_flowgate_definitions/sources/central_north/NYISO_CEVC24_2024.pdf',
        'output/nygrid_2025_p34_qualification/sources/primary_evidence_conclusion.json',
        'output/nygrid_2025_p34_qualification/sources/NYISO_PARdiagram_version1_0.pdf',
        'output/nygrid_2025_p34_qualification/sources/NYISO_PARdiagram_version1_0.pdf.receipt.json',
        'output/nygrid_2025_par_controls/sources/direction/NYISO_ParFlowDiagrams27.pdf',
        'output/nygrid_2025_moses_repair/boundary/boundary_verification_receipt.json',
        'output/nygrid_2025_moses_repair/boundary/PV20_source_receipt.json']:
        read(ROOT/p)
    annual=[x for x in metrics if x['month']==0]
    metric_frame=pd.DataFrame(metrics)
    monthly_summary=[]
    for gate in ['TOTAL EAST','CENTRAL EAST - VC']:
        z=metric_frame[(metric_frame.interface==gate)&metric_frame.month.gt(0)].pivot(index='month',columns=['model','readout'],values='MAE_MW')
        monthly_summary.append(dict(interface=gate,months=12,
            candidate_worse_than_baseline_same_legacy_months=int((z[('candidate','legacy')]>z[('baseline','legacy')]).sum()),
            candidate_worse_than_baseline_same_augmented_readout_months=int((z[('candidate','legacy_plus_PV20_export_proxy')]>z[('baseline','legacy_plus_PV20_export_proxy')]).sum()),
            candidate_PV20_readout_addition_improves_MAE_months=int((z[('candidate','legacy_plus_PV20_export_proxy')]<z[('candidate','legacy')]).sum())))
    mores=current[q,jmo]-observed[q,jmo]
    report=dict(status='completed_source_directed_readout_sensitivity_no_operator_promotion',created_utc=datetime.now(timezone.utc).isoformat(),
        qualified_hours=8651,analysis_contract=contract,annual_metrics=annual,
        exact_frozen_operator_identity='TOTAL_EAST_legacy = CENTRAL_EAST_VC_legacy + PF_at_parent224_original_from_terminal',
        mean_candidate_minus_baseline_parent224_readout_MW=float(h.loc[q,'candidate_minus_baseline_parent224_readout_MW'].mean()),
        frozen_CE_members=4,frozen_TE_members=5,physical_CE_printed_members=8,physical_TE_printed_members=29,
        physical_CE_other_groups=['E -> F','D -> N'],physical_TE_other_groups=['E -> F','E -> G','D -> N','P -> G','P -> J','PJM RECo -> G'],
        source_directed_added_coefficient_to_import_positive_PV20=-1,
        monthly_comparison_summary=monthly_summary,current_northern_balance_identity_max_error_MW=identity_error,
        physical_PV20_component_membership_verified=True,entire_physical_operator_certified=False,
        CEVC_generic_definition_contains_PV20=True,exact_public_CEVC_P32_expression_certified=False,
        P34_native_unit_and_publication_origin_independently_resolved=False,
        historical_SandBar_sign_corroborated_on='2026-01-09 and2026-07-17',historical_2025_sign_effective_date_certified=False,
        full_SouthHero_and_meter_gap_error_bound_MW=None,
        partial_context=dict(SouthHero29_1A_planning_peak_MVA=6.66,complete_error_bound=False,
            current_Moses_MAE_MW=float(abs(mores).mean()),current_Moses_bias_MW=float(mores.mean()),
            hypothetical_bound_formula='If an independent bound B on the complete hourly meter correction existed, MAE could improve by no more than B. No such complete source-supported B was established.'),
        interpretation=[
            'Both frozen CE and TE readouts share four coarse E-F corridor terms. A shared decrease can improve a positive CE bias while worsening a negative TE bias without establishing a globally worse network.',
            'PV20 exits ZoneD toward NewEngland. The physical source-table direction adds its outward export, which is minus the adopted import-positive SandBar proxy. This sign was not selected by score.',
            'The candidate explicitly routes PV20 outside the main NY cut, whereas its frozen CE/TE comparison operators still omit that component. An old coarse readout may contain compensating routing error; this sensitivity does not identify a unique causal attribution.',
            'TE also includes PJM-to-eastern-NY paths absent from the frozen NY-only functional. Adding PV20 alone does not reconstruct all physical TE terms, their meter ends or the P32 expression.',
            'Moses does not include PV20 in its seven-term meter. PV20 belongs in the northern-area injection balance; do not add the same proxy directly to the Moses meter readout a second time.',
            'The 6.66MVA planning datum concerns one feeder, not the complete SouthHero net injection plus line/PAR losses and bypass flow. It cannot supply a source-certified complete uncertainty interval.'
        ],
        no_source_or_model_changes=True,new_AC_solves=0,source_hashes_unchanged=all(sha(ROOT/p)==v for p,v in DEPS.items()),
        dependencies=[dict(path=p,sha256=v)for p,v in DEPS.items()],script_sha256=sha(Path(__file__)))
    require(report['source_hashes_unchanged'],'Protected input changed during diagnosis')
    (OUT/'boundary_readout_receipt.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(pd.DataFrame(annual)[['interface','model','readout','MAE_MW','bias_MW','WAPE_percent']].to_string(index=False))
    print(json.dumps(dict(mean_PV20_export=float(exported[q].mean()),mean_parent224_change=report['mean_candidate_minus_baseline_parent224_readout_MW'],partial_context=report['partial_context']),indent=2))


if __name__=='__main__':main()
