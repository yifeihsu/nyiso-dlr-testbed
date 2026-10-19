"""Score a predeclared 2x2 input experiment after independent physical validation."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'output/nygrid_2025_postrepair_diagnosis/ablations'
CONVENTIONS=['legacy_signed_literal_from','oriented_source_side','oriented_target_side']
STATES=['pre_may','may21','may30','post_dover']


def record(path):
    with path.open('rb') as f: h=hashlib.file_digest(f,'sha256').hexdigest()
    return {'path':path.relative_to(ROOT).as_posix(),'sha256':h,'bytes':path.stat().st_size}


def vec(d,key,dtype=float):return np.asarray(d[key],dtype=dtype).reshape(-1)


def stats(p,o):
    e=p-o;n=len(e)
    if not n:return {'hours':0,**{k:np.nan for k in ['mae_public_MW','bias_public_MW','rmse_public_MW','wape_percent','mean_prediction_public_MW']}}
    assert np.isfinite(e).all()
    return {'hours':n,'mae_public_MW':float(abs(e).mean()),'bias_public_MW':float(e.mean()),
        'rmse_public_MW':float(np.sqrt(np.mean(e**2))),'wape_percent':float(100*abs(e).sum()/abs(o).sum()),
        'mean_prediction_public_MW':float(p.mean())}


def main():
    recipe_path=OUT/'scenario_recipe.json';recipe=json.loads(recipe_path.read_text())
    assert recipe['predeclared_before_ablation_solves_and_metrics'] and not recipe['P32_observations_read_to_construct_interventions']
    reference_path=ROOT/'output/nygrid_2025_moses_repair/annual/moses_repair_v1/comparison/comparison_arrays.npz'
    reference=np.load(reference_path,allow_pickle=False);source=reference['source_qualified'];state=reference['topology_state_index'];gamma=float(reference['gamma'])
    assert source.sum()==8651;names=reference['interface_names'];observed=reference['observed'];times=reference['timestamp_utc']
    predictions={'B':{c:reference['current_baseline_'+c] for c in CONVENTIONS},'GP':{c:reference['candidate_'+c] for c in CONVENTIONS}}
    qualified={'B':reference['current_baseline_qualified'],'GP':reference['candidate_qualified']}
    ops_path=ROOT/'output/nygrid_2025_acpf_profile_audit/alignment/interface_operator_terms.csv';ops=pd.read_csv(ops_path)
    network_path=ROOT/'output/nygrid_2025_moses_repair/annual/moses_repair_v1/annual_network.mat';templates=loadmat(network_path,simplify_cells=True)['templates']
    dependencies=[recipe_path,reference_path,ops_path,network_path];counts={}
    for scenario in ['G','P']:
        run=OUT/f'{scenario}_v1';rp=run/'annual_receipt.json';vp=run/'annual_validation.json';producer=json.loads(rp.read_text());validation=json.loads(vp.read_text())
        assert producer['completed'] and validation['passed'] and validation['completed']
        assert producer['qualified_hours']==validation['qualified_hours']
        axes_path=run/'axes.mat';axes=loadmat(axes_path,simplify_cells=True);keys=vec(axes,'branch_keys',str);parents=vec(axes,'branch_parent_row',int);keymap={x:i for i,x in enumerate(keys)}
        dependencies += [rp,vp,axes_path];qualified[scenario]=np.zeros(8760,bool);predictions[scenario]={c:np.full((8760,7),np.nan) for c in CONVENTIONS};seen=np.zeros(8760,bool)
        for mon in range(1,13):
            path=run/'monthly'/f'ablation_{mon:02d}.mat';d=loadmat(path,simplify_cells=True,variable_names=['hour_index','qualified','source_qualified','PF','PT']);dependencies.append(path)
            assert record(path)['sha256']==producer['months'][mon-1]['output']['sha256']
            ix=vec(d,'hour_index',int)-1;q=vec(d,'qualified',bool);assert not seen[ix].any();seen[ix]=True;qualified[scenario][ix]=q
            assert np.array_equal(vec(d,'source_qualified',bool),source[ix]) and np.all(~q|source[ix])
            for s in np.unique(state[ix]):
                use=np.flatnonzero(q&(state[ix]==s));hh=ix[use]
                if not len(use):continue
                terms=ops[ops.state==STATES[int(s)-1]];assert len(terms)==34
                local_keys=vec(templates[int(s)-1],'branch_keys',str);values={c:np.zeros((len(use),7)) for c in CONVENTIONS}
                for term in terms.itertuples(index=False):
                    assert local_keys[int(term.first_runtime_branch_row)-1]==term.first_runtime_branch_key
                    assert local_keys[int(term.last_runtime_branch_row)-1]==term.last_runtime_branch_key
                    f=keymap[term.first_runtime_branch_key];t=keymap[term.last_runtime_branch_key];k=int(term.interface_index)-1;sign=int(term.coefficient)
                    assert parents[f]==parents[t]==term.original_branch_row and names[k]==term.interface
                    pf=d['PF'][use,f];pt=d['PT'][use,t]
                    values[CONVENTIONS[0]][:,k]+=sign*pf
                    values[CONVENTIONS[1]][:,k]+=pf if sign>0 else pt
                    values[CONVENTIONS[2]][:,k]+=-pt if sign>0 else -pf
                for c in CONVENTIONS:predictions[scenario][c][hh]=values[c]/gamma
        assert seen.all();counts[scenario]=int(qualified[scenario].sum())
    common=source.copy()
    for label in ['B','G','P','GP']:common &=qualified[label]
    months=pd.DatetimeIndex(pd.to_datetime(times,utc=True)).tz_convert('America/New_York').month.to_numpy()
    periods={'annual':np.ones(8760,bool),**{f'month_{m:02d}':months==m for m in range(1,13)},**{f'state_{STATES[s-1]}':state==s for s in range(1,5)}}
    rows=[];effect_rows=[]
    for c in CONVENTIONS:
        for period,mask in periods.items():
            use=common&mask
            for k,name in enumerate(names):
                values={label:stats(predictions[label][c][use,k],observed[use,k]) for label in ['B','G','P','GP']}
                for label,value in values.items():rows.append({'scenario':label,'period':period,'convention':c,'interface':name,'cohort':'same_all_four_qualified',**value})
                for metric in ['mae_public_MW','bias_public_MW','rmse_public_MW','wape_percent','mean_prediction_public_MW']:
                    b,g,p,gp=[values[label][metric] for label in ['B','G','P','GP']]
                    phi_g=.5*((g-b)+(gp-p));phi_p=.5*((p-b)+(gp-g));interaction=gp-g-p+b
                    if use.any():assert abs(phi_g+phi_p-(gp-b))<1e-9
                    effect_rows.append({'period':period,'convention':c,'interface':name,'metric':metric,'hours':int(use.sum()),
                        'B':b,'G':g,'P':p,'GP':gp,'combined_change':gp-b,'G_first_marginal':g-b,'G_after_P_marginal':gp-p,
                        'P_first_marginal':p-b,'P_after_G_marginal':gp-g,'G_Shapley_effect':phi_g,'P_Shapley_effect':phi_p,
                        'interaction':interaction,'interpretation':'Within-model controlled source-input attribution only; not real-system or physical-meter causality.'})
    metric_path=OUT/'factorial_metrics.csv';effect_path=OUT/'factorial_attribution.csv';pd.DataFrame(rows).to_csv(metric_path,index=False);pd.DataFrame(effect_rows).to_csv(effect_path,index=False)
    arrays={'hour_index':reference['hour_index'],'timestamp_utc':times,'interface_names':names,'source_qualified':source,
            'common_qualified':common,'observed':observed,'gamma':gamma,'topology_state_index':state}
    for label in ['B','G','P','GP']:
        arrays[f'{label}_qualified']=qualified[label]
        for c in CONVENTIONS:arrays[f'{label}_{c}']=predictions[label][c]
    array_path=OUT/'factorial_arrays.npz';np.savez_compressed(array_path,**arrays)
    hourly=[]
    for name in ['MOSES SOUTH','TOTAL EAST']:
        k=int(np.flatnonzero(names==name)[0]);pr={label:predictions[label][CONVENTIONS[0]][:,k] for label in ['B','G','P','GP']}
        er={label:abs(pr[label]-observed[:,k]) for label in pr}
        for h in np.flatnonzero(common):hourly.append({'hour_index':int(h+1),'timestamp_utc':times[h],'month':int(months[h]),'interface':name,'observed_public_MW':float(observed[h,k]),
            **{f'{label}_prediction_public_MW':float(pr[label][h]) for label in pr},
            'G_prediction_Shapley_MW':float(.5*((pr['G'][h]-pr['B'][h])+(pr['GP'][h]-pr['P'][h]))),
            'P_prediction_Shapley_MW':float(.5*((pr['P'][h]-pr['B'][h])+(pr['GP'][h]-pr['G'][h]))),
            'prediction_interaction_MW':float(pr['GP'][h]-pr['G'][h]-pr['P'][h]+pr['B'][h]),
            'G_absolute_error_Shapley_MW':float(.5*((er['G'][h]-er['B'][h])+(er['GP'][h]-er['P'][h]))),
            'P_absolute_error_Shapley_MW':float(.5*((er['P'][h]-er['B'][h])+(er['GP'][h]-er['G'][h]))),
            'absolute_error_interaction_MW':float(er['GP'][h]-er['G'][h]-er['P'][h]+er['B'][h])})
    hourly_path=OUT/'hourly_Moses_TotalEast_attribution.csv';hour_frame=pd.DataFrame(hourly);hour_frame.to_csv(hourly_path,index=False)
    effects=pd.DataFrame(effect_rows)
    for name in ['MOSES SOUTH','TOTAL EAST']:
        row=effects[(effects.interface==name)&(effects.metric=='mae_public_MW')&(effects.period=='annual')&(effects.convention==CONVENTIONS[0])].iloc[0]
        check=hour_frame[hour_frame.interface==name]
        assert abs(check.G_absolute_error_Shapley_MW.mean()-row.G_Shapley_effect)<1e-9
        assert abs(check.P_absolute_error_Shapley_MW.mean()-row.P_Shapley_effect)<1e-9
    receipt={'passed':True,'completed':True,'created_utc':datetime.now(timezone.utc).isoformat(),'source_qualified_hours':int(source.sum()),
        'scenario_qualified_hours':{k:int(v.sum()) for k,v in qualified.items()},'same_all_four_qualified_hours':int(common.sum()),
        'excluded_or_failed_not_promoted':True,'all_8760_rows_retained':True,'source_recipe_predeclared':True,
        'all_seven_interfaces_scored':True,'conventions':CONVENTIONS,'attribution_sign':'Negative MAE effect means improvement; signed bias and prediction effects retain their algebraic sign.',
        'Shapley_sum_and_hourly_error_decomposition_verified':True,'within_model_causality_only':True,
        'physical_P32_meter_equivalence_verified':False,'no_P32_fitting_or_source_mutation':True,
        'inputs':[record(p) for p in dependencies],'outputs':[record(p) for p in [metric_path,effect_path,array_path,hourly_path]],'producer':record(Path(__file__))}
    (OUT/'factorial_scoring_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    selected=effects[(effects.period=='annual')&(effects.convention==CONVENTIONS[0])&(effects.metric.isin(['mae_public_MW','bias_public_MW']))]
    print(json.dumps({k:receipt[k] for k in ['passed','scenario_qualified_hours','same_all_four_qualified_hours']}))
    print(selected[['interface','metric','B','G','P','GP','combined_change','G_Shapley_effect','P_Shapley_effect','interaction']].to_string(index=False))


if __name__=='__main__':main()
