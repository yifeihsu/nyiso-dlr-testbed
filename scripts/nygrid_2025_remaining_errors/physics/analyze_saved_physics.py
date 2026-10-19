"""Saved-array loss/voltage concentration and residual association diagnostics.

No PF, OPF, fitting, model alteration or existing-output regeneration occurs.
All statistics use the same 8,170 equation/accounting-qualified current hours.
Correlations and post-hoc strata are descriptive, never causal attributions.
"""
from pathlib import Path
from datetime import datetime,timezone
from collections import Counter
import hashlib,json,subprocess

import numpy as np
import pandas as pd
from scipy import sparse
from scipy.io import loadmat

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'output/nygrid_2025_remaining_errors/physics'
ANNUAL=ROOT/'output/nygrid_2025_ac_loss_revision/validation/annual/released_equivalent_boundary_consistent'
COMPARISON=ROOT/'output/nygrid_2025_ac_loss_revision/comparison/combined'
ZONES=list('ABCDEFGHIJK')


def record(path):
    with path.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
    return dict(path=path.relative_to(ROOT).as_posix(),sha256=digest)


def corr(a,b):
    good=np.isfinite(a)&np.isfinite(b);a=a[good];b=b[good]
    if len(a)<3 or np.std(a)==0 or np.std(b)==0:return None
    return float(np.corrcoef(a,b)[0,1])


def residualize_month(value,months):
    out=np.asarray(value,float).copy()
    for m in np.unique(months):out[months==m]-=np.mean(out[months==m],axis=0)
    return out


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    assert head=='303b626bcab43215c839ad7e175e7274f25b4bdc'
    # Explicit preservation boundary for the user's existing uncommitted map.
    status=subprocess.check_output(['git','status','--porcelain','-z','--','scripts/nygrid_2025_latest_map','output/nygrid_2025_latest_map'],cwd=ROOT).decode('utf-8')
    protected=[]
    for item in status.split('\0'):
        if not item:continue
        p=ROOT/item[3:]
        if p.is_file():protected.append(record(p))
    npz=COMPARISON/'comparison_arrays.npz'
    with np.load(npz,allow_pickle=False) as data:a={k:data[k].copy() for k in data.files}
    q=a['revised_qualified'].astype(bool);assert q.sum()==8170 and np.array_equal(q,a['paired_qualified'])
    assert not a['operating_qualified'].any()
    hours=np.arange(1,8761);times=a['timestamp_utc'].astype(str);gamma=float(a['gamma']);labels=a['interface_names'].astype(str)
    local=pd.to_datetime(times,utc=True).tz_convert('America/New_York');months=local.month.to_numpy()
    predicted=a['revised_legacy_signed_literal_from'];observed=a['observed'];error=predicted-observed
    registry_path=ROOT/'output/nygrid_2025_ac_system/branches/branch_assignments.csv'
    registry=pd.read_csv(registry_path).set_index('branch_row')
    template_path=ROOT/'output/nygrid_2025_latest_handoff/structure_inputs/post_dover.mat'
    template=loadmat(template_path,simplify_cells=True)
    ownership=np.asarray(template['loss_ownership']);assert ownership.shape==(14,413)
    canonical=loadmat(ANNUAL/'annual_axes.mat',simplify_cells=True)
    parent=np.asarray(canonical['branch_parent_row']).astype(int)-1;keys=np.asarray(canonical['branch_keys']).astype(str)
    ids=np.asarray(canonical['bus_id']).astype(int);assert len(ids)==267 and len(keys)==488
    aggregate=sparse.coo_matrix((np.ones(488),(np.arange(488),parent)),shape=(488,413)).tocsr()
    loss=np.full((8760,413),np.nan);parent_current=np.full((8760,413),np.nan)
    voltage=np.full((8760,267),np.nan);state=np.zeros(8760,int);budget=np.full((8760,14),np.nan)
    paths=[npz,registry_path,template_path,ANNUAL/'annual_axes.mat']
    for month in range(1,13):
        p=ANNUAL/f'monthly/profile_PF_2025_{month:02d}.mat';paths.append(p)
        d=loadmat(p,simplify_cells=True,variable_names=['hour_index','timestamp_utc','PF','PT','Iseries','branch_parent_row','branch_keys','branch_active','branch_present',
            'VM','bus_id','bus_present','topology_state_index','actual_budget_MW','computed_current_available'])
        h=np.asarray(d['hour_index'],int)-1;good=q[h];hh=h[good]
        assert np.array_equal(np.asarray(d['computed_current_available'],bool),good)
        assert np.array_equal(np.asarray(d['branch_parent_row']).astype(int)-1,parent)
        assert np.array_equal(np.asarray(d['branch_keys']).astype(str),keys) and np.array_equal(np.asarray(d['bus_id']).astype(int),ids)
        assert np.array_equal(np.asarray(d['timestamp_utc']).astype(str),times[h])
        active=np.asarray(d['branch_active'],bool)[good]
        instantaneous=np.where(active,d['PF'][good]+d['PT'][good],0.)
        assert np.isfinite(instantaneous).all() and instantaneous.min()>-1e-7
        loss[hh]=instantaneous@aggregate
        for pp in range(413):
            use=parent==pp
            currents=np.where(active[:,use],d['Iseries'][good][:,use],0.)
            parent_current[hh,pp]=np.max(currents,axis=1)
        voltage[hh]=np.where(np.asarray(d['bus_present'],bool)[good],d['VM'][good],np.nan)
        state[h]=np.asarray(d['topology_state_index']).astype(int)
        budget[hh]=d['actual_budget_MW'][good]
    assert np.isfinite(loss[q]).all() and np.isnan(loss[~q]).all()
    allocation_error=float(np.max(abs(loss[q]@ownership.T-budget[q])))
    assert allocation_error<1e-6
    assert np.max(abs(budget[q,:11]-a['NY_allocated_loss_MW'][q]))<1e-6
    total=loss[q].sum(axis=1);gross=a['NY_gross_target_MW'];fractions=a['NY_allocated_loss_MW']/gross
    current_R=np.bincount(np.asarray(template['branch_parent_row'],int)-1,weights=template['branch'][:,2],minlength=413)
    current_X=np.bincount(np.asarray(template['branch_parent_row'],int)-1,weights=template['branch'][:,3],minlength=413)
    current_B=np.bincount(np.asarray(template['branch_parent_row'],int)-1,weights=template['branch'][:,4],minlength=413)
    current_preserved=np.isclose(current_R,registry.original_r_pu.to_numpy(),rtol=0,atol=1e-11)&np.isclose(current_X,registry.original_x_pu.to_numpy(),rtol=0,atol=1e-10)
    rank=[]
    for pp in range(413):
        reg=registry.loc[pp+1];v=loss[q,pp];tag='imported_RX_preserved' if current_preserved[pp] else 'prior_engineering_redesign'
        if pp+1==224:tag='released_network_equivalent_unverified_R'
        rank.append(dict(parent_row=pp+1,branch_key=reg.branch_key,from_bus=int(reg.from_bus),to_bus=int(reg.to_bus),from_name=reg.from_name,to_name=reg.to_name,
            from_kV=reg.base_kv,to_kV=reg.to_base_kv,classification=reg.classification,source_role=reg.source_role,current_parameter_origin=tag,
            original_R_pu=reg.original_r_pu,original_X_pu=reg.original_x_pu,original_B_pu=reg.original_b_pu,
            current_R_pu=current_R[pp],current_X_pu=current_X[pp],current_B_pu=current_B[pp],
            R_ratio_to_original=current_R[pp]/reg.original_r_pu if reg.original_r_pu>0 else None,
            X_ratio_to_original=current_X[pp]/reg.original_x_pu if reg.original_x_pu>0 else None,
            mean_loss_model_MW=float(v.mean()),median_loss_model_MW=float(np.median(v)),p95_loss_model_MW=float(np.percentile(v,95)),max_loss_model_MW=float(v.max()),
            share_of_all_cohort_loss=float(v.sum()/loss[q].sum()),max_series_current_to_side_base_A=float(parent_current[q,pp].max()),
            zone_E_owned_share=float(ownership[4,pp]),zone_F_owned_share=float(ownership[5,pp]),
            parameter_basis=reg.parameter_basis,thermal_or_installed_impedance_truth_established=False))
    ranked=pd.DataFrame(rank).sort_values('mean_loss_model_MW',ascending=False)
    zone_rows=[]
    for z,zone in enumerate(ZONES):
        f=fractions[q,z];contribution=loss[q]*ownership[z];order=np.argsort(contribution.mean(axis=0))[::-1]
        for pp in order:
            if contribution[:,pp].sum()==0:continue
            zone_rows.append(dict(zone=zone,parent_row=int(pp+1),from_name=registry.loc[pp+1].from_name,to_name=registry.loc[pp+1].to_name,
                loss_ownership_weight=float(ownership[z,pp]),mean_assigned_loss_model_MW=float(contribution[:,pp].mean()),
                share_of_zone_assigned_loss=float(contribution[:,pp].sum()/contribution.sum()),max_assigned_loss_model_MW=float(contribution[:,pp].max())))
    zone_contribution=pd.DataFrame(zone_rows)
    zone_summary=[]
    for j,z in enumerate(ZONES):
        v=fractions[q,j];h=int(hours[q][np.argmax(v)])
        zone_summary.append(dict(zone=z,hours=int(q.sum()),mean_loss_fraction=float(v.mean()),median_loss_fraction=float(np.median(v)),p95_loss_fraction=float(np.percentile(v,95)),max_loss_fraction=float(v.max()),
            hours_above25pct=int((v>.25).sum()),hours_above50pct=int((v>.5).sum()),hours_above75pct=int((v>.75).sum()),hours_above90pct=int((v>.9).sum()),
            maximum_hour_index=h,maximum_timestamp_utc=times[h-1],mean_gross_model_MW=float(gross[q,j].mean()),mean_assigned_loss_model_MW=float(budget[q,j].mean())))
    qvol=voltage[q];low=np.nanmin(qvol,axis=1);high=np.nanmax(qvol,axis=1)
    byid={int(v):i for i,v in enumerate(template['bus'][:,0])};names=np.asarray(template['bus_name']).astype(str)
    bus_rows=[]
    for j,bid in enumerate(ids):
        v=qvol[:,j];finite=np.isfinite(v);idx=byid[int(bid)];incident=np.flatnonzero((template['branch'][:,0]==bid)|(template['branch'][:,1]==bid))
        parent_ids=np.unique(np.asarray(template['branch_parent_row'])[incident].astype(int)).tolist()
        bus_rows.append(dict(bus_id=int(bid),name=names[idx],base_kV=float(template['bus'][idx,9]),present_qualified_hours=int(finite.sum()),
            over_1p05_hours=int(np.sum(v>1.05+1e-7)),under_0p95_hours=int(np.sum(v<.95-1e-7)),
            maximum_VM_pu=float(np.nanmax(v)),minimum_VM_pu=float(np.nanmin(v)),
            numerical_section_bus=bool(int(bid)>60000),incident_parent_rows=';'.join(map(str,parent_ids))))
    voltage_table=pd.DataFrame(bus_rows).sort_values(['over_1p05_hours','maximum_VM_pu'],ascending=False)
    features=pd.DataFrame(dict(hour_index=hours[q],timestamp_utc=times[q],month=months[q],state_index=state[q],
        total_AC_loss_model_MW=total,NY_assigned_loss_model_MW=budget[q,:11].sum(axis=1),
        E_loss_fraction=fractions[q,4],F_loss_fraction=fractions[q,5],max_NY_loss_fraction=fractions[q].max(axis=1),
        parent41_loss_model_MW=loss[q,40],parent224_loss_model_MW=loss[q,223],
        all_other_parent_loss_model_MW=total-loss[q,40]-loss[q,223],
        NY_gross_target_model_MW=gross[q].sum(axis=1),minimum_VM_pu=low,maximum_VM_pu=high))
    for j,name in enumerate(labels):features['error_'+name+'_public_MW']=error[q,j]
    associations=[]
    feature_names=['total_AC_loss_model_MW','E_loss_fraction','F_loss_fraction','parent41_loss_model_MW','parent224_loss_model_MW','NY_gross_target_model_MW','maximum_VM_pu']
    for field in feature_names:
        x=features[field].to_numpy();xm=residualize_month(x,months[q])
        for j,name in enumerate(labels):
            for transform,y in [('signed_error',error[q,j]),('absolute_error',abs(error[q,j]))]:
                associations.append(dict(feature=field,interface=name,error_quantity=transform,hours=8170,
                    Pearson_r=corr(x,y),within_month_demeaned_Pearson_r=corr(xm,residualize_month(y,months[q])),
                    interpretation='descriptive_association_only_not_causal;all_operating_gates_unqualified'))
    strata=[]
    for feature in ['E_loss_fraction','F_loss_fraction']:
        x=features[feature].to_numpy()
        for threshold in [.25,.5,.75,.9]:
            for group,mask in [('at_or_below',x<=threshold),('above',x>threshold)]:
                if not mask.any():continue
                for j,name in enumerate(labels):
                    v=error[q,j][mask]
                    strata.append(dict(feature=feature,threshold=threshold,stratum=group,interface=name,hours=int(mask.sum()),
                        mean_error_public_MW=float(v.mean()),MAE_public_MW=float(abs(v).mean()),
                        mean_total_loss_model_MW=float(total[mask].mean()),mean_feature_fraction=float(x[mask].mean()),
                        interpretation='posthoc_cohort_description_not_a_controlled_effect'))
    dc_path=ROOT/'output/nygrid_2025_western_audit/replay/dated_combined.mat';paths.append(dc_path)
    dc=loadmat(dc_path,simplify_cells=True,variable_names=['hour_index','timestamp_utc','qualified','interface_pf','gamma'])
    assert np.array_equal(dc['hour_index'],hours) and np.array_equal(np.asarray(dc['timestamp_utc']).astype(str),times)
    assert np.asarray(dc['qualified'],bool)[q].all() and float(dc['gamma'])==gamma
    dcp=np.asarray(dc['interface_pf'])/gamma;paired=[]
    for j,name in enumerate(labels):
        ce=error[q,j];de=dcp[q,j]-observed[q,j];delta=predicted[q,j]-dcp[q,j]
        paired.append(dict(interface=name,hours=8170,current_AC_MAE_public_MW=float(abs(ce).mean()),corrected_DC_MAE_public_MW=float(abs(de).mean()),
            current_AC_bias_public_MW=float(ce.mean()),corrected_DC_bias_public_MW=float(de.mean()),
            AC_minus_DC_mean_public_MW=float(delta.mean()),AC_minus_DC_MAE_public_MW=float(abs(delta).mean()),
            same_source_inputs=True,comparison_is_not_a_physical_truth_claim=True))
    extreme=[]
    for criterion,values in [('max_E_loss_fraction',fractions[q,4]),('max_F_loss_fraction',fractions[q,5]),('max_parent41_loss',loss[q,40]),
                             ('max_parent224_loss',loss[q,223]),('max_total_loss',total),('max_voltage',high),('min_voltage',-low)]:
        ii=int(np.argmax(values));h=int(hours[q][ii]);top=np.argsort(loss[h-1])[::-1][:5]
        extreme.append(dict(criterion=criterion,hour_index=h,timestamp_utc=times[h-1],total_loss_model_MW=float(total[ii]),
            E_loss_fraction=float(fractions[h-1,4]),F_loss_fraction=float(fractions[h-1,5]),minimum_VM_pu=float(low[ii]),maximum_VM_pu=float(high[ii]),
            top5_loss_parents=';'.join(str(int(p+1)) for p in top),selected_from_physics_not_observation_error=True))
    # Fixed original regional capability weights are an alternate prior, not
    # a unit or station identity correction inferred from a bus name.
    bundle_path=ROOT/'output/nygrid_2025_latest_handoff/model/latest_model.mat';paths.append(bundle_path)
    bundle=loadmat(bundle_path,simplify_cells=True)['model'];pol=bundle['loss_static'][3]
    ext_rows=np.asarray(pol['finite_external_generator_rows']).astype(int);gengroup=np.asarray(pol['external_gen_group']).astype(int)
    caps=dict(zip(ext_rows,np.asarray(pol['finite_external_Pmax_MW']).astype(float)))
    use=np.flatnonzero(gengroup==14)+1;weights=np.asarray(pol['generator_share'])[use-1]
    pmax=np.array([caps[int(row)] for row in use]);capacity_weight=pmax/pmax.sum()
    pjm=pd.DataFrame(dict(generator_row=use,bus_id=np.asarray(bundle['generator_bus_ids'])[use-1],
        frozen_generation_share=weights,finite_Pmax_proxy_model_MW=pmax,capacity_proportional_share=capacity_weight,
        share_delta=capacity_weight-weights,interpretation='regional_boundary_proxy_prior_not_observed_unit_dispatch'))
    baseline_generation_path=ROOT/'output/nygrid_2025_western_audit/dispatch/all_boundary_actual_dispatch.mat';paths.append(baseline_generation_path)
    baseline_generation=loadmat(baseline_generation_path,simplify_cells=True,variable_names=['gen_pg'])['gen_pg'][q][:,use-1]
    assert np.all(baseline_generation.sum(axis=1)>0)
    normalized_baseline=baseline_generation/baseline_generation.sum(axis=1,keepdims=True)
    baseline_share_error=float(np.max(abs(normalized_baseline-capacity_weight)))
    hypotheses=pd.DataFrame([
        dict(track='remaining_interface_error',priority=1,assumption='Native zonal hydro allocation and hourly priors in A/B/D',
             evidence='Corrected DC and current AC have almost identical DY/WC/MS errors on8170 matched hours; complete-cut accounting isolates source terms.',
             smallest_probe='Calendar-selected bounded ±100 publicMW Niagara/StLawrence redistribution with statewideHY fixed and donor constraints recorded.',
             interpretation='Mechanism sensitivity only; evaluate independent energy evidence before a source correction.'),
        dict(track='remaining_interface_error',priority=2,assumption='External PJM spatial injection and loss-allocation priors',
             evidence='Capacity-proportional PG and loss weights already equal the baseline. TE midpoint redistribution requires the actual C/G landing accounting.',
             smallest_probe='If needed, use a distinct bounded spatial redistribution at fixed regional total; first show it differs from baseline without reading observations.',
             interpretation='Zero response from a capacity-proportional no-op is not evidence of physical insensitivity.'),
        dict(track='physical_validity',priority=1,assumption='Long synthetic-line charging, fixed compensation and reactive controls',
             evidence='All8170 qualified hours have overvoltage; parent195 and185 numerical interiors violate throughout.',
             smallest_probe='First inspect saved endpoint/interior voltages and assumed charging/reactor/PV policies; no new global reactive retuning is justified by this audit.',
             interpretation='A numerical or interface-score improvement does not establish voltage/reactive feasibility.'),
        dict(track='physical_validity',priority=2,assumption='Parent41 geographic-length-driven R/X redesign',
             evidence='77.897modelMW mean loss;96.27percent of F assigned-loss energy; R andX much larger than imported tuple.',
             smallest_probe='Separate importedRX holding currentB and importedRXB counterfactuals on the predeclared calendar cohort.',
             interpretation='Admittance-only sensitivity; no conductor, installed-asset or operational promotion.'),
        dict(track='physical_validity',priority=3,assumption='Parent224 unresolved released resistance',
             evidence='39.136modelMW mean loss;50.82percent of E assigned-loss energy; importedR has no physical derivation.',
             smallest_probe='Use existing source/cut identities first; any loss-isolation intervention must be labeled diagnostic and preserve finite capability and source schedules.',
             interpretation='Do not choose replacement resistance by NYISO error or convergence.'),
    ])
    tables={'parent_loss_concentration':ranked,'zonal_loss_contributions':zone_contribution,'zonal_loss_fraction_summary':pd.DataFrame(zone_summary),
        'voltage_bound_concentration':voltage_table,'hourly_physics_features':features,'residual_physics_associations':pd.DataFrame(associations),
        'loss_fraction_residual_strata':pd.DataFrame(strata),'current_AC_vs_corrected_DC_same_hours':pd.DataFrame(paired),
        'physics_extreme_hours':pd.DataFrame(extreme),'PJM_proxy_share_priors':pjm,'ranked_unverified_assumptions':hypotheses}
    outputs=[]
    for name,table in tables.items():
        path=OUT/(name+'.csv');table.to_csv(path,index=False);outputs.append(record(path))
    previous_bridge_path=ROOT/'output/nygrid_2025_centraleast_diagnosis/summary/diagnosis_summary.json';paths.append(previous_bridge_path)
    bridge=json.loads(previous_bridge_path.read_text())
    western_path=ROOT/'output/nygrid_2025_western_audit/effects/western_component_summary.csv';paths.append(western_path)
    reactor_path=ROOT/'output/nygrid_2025_ac_system/branches/post_dover_reactor_ledger.csv';paths.append(reactor_path)
    reactors=pd.read_csv(reactor_path).set_index('original_branch_row')
    persistent_voltage_context=[]
    for parent_row in [195,185]:
        row=registry.loc[parent_row];reactor=reactors.loc[parent_row]
        persistent_voltage_context.append(dict(parent_row=parent_row,from_name=row.from_name,to_name=row.to_name,nominal_kV=float(row.base_kv),
            declared_equivalent_length_m=float(row.route_length_m),current_R_pu=float(current_R[parent_row-1]),current_X_pu=float(current_X[parent_row-1]),current_B_pu=float(current_B[parent_row-1]),
            imported_R_pu=float(row.original_r_pu),imported_X_pu=float(row.original_x_pu),imported_B_pu=float(row.original_b_pu),
            nominal_charging_MVAr_at_1pu=float(reactor.nominal_line_charging_mvar),declared_reactor_fraction=float(reactor.fraction),
            nominal_reactor_absorption_MVAr_at_1pu=float(reactor.applied_total_reactor_mvar_at1pu),
            interpretation='Stored synthetic construction assumptions; nominal values are not measured charging or a verified installed compensation design.'))
    for p in paths:assert p.is_file()
    # Preserve each pre-existing map edit byte-for-byte.
    for r in protected:assert record(ROOT/r['path'])['sha256']==r['sha256'],r['path']
    f_contrib=zone_contribution.query("zone=='F' and parent_row==41").iloc[0]
    e_contrib=zone_contribution.query("zone=='E' and parent_row==224").iloc[0]
    report=dict(passed=True,created_utc=datetime.now(timezone.utc).isoformat(),baseline_HEAD=head,
        scope='Current saved annual loss/voltage concentration and remaining interface-error associations; no new PF/OPF/annual replay or source changes',
        hours=8170,units=dict(branch_losses='modelMW',interface_residuals='publicMW already stored in comparisonNPZ',gamma=gamma),
        qualified_cohort_only=True,failed_iterates_included=False,operating_qualified_hours=0,
        mean_total_loss_model_MW=float(total.mean()),maximum_total_loss_model_MW=float(total.max()),
        parent41=dict(mean_loss_model_MW=float(loss[q,40].mean()),maximum_loss_model_MW=float(loss[q,40].max()),
            share_of_all_cohort_loss=float(loss[q,40].sum()/loss[q].sum()),share_of_F_assigned_loss=float(f_contrib.share_of_zone_assigned_loss),
            ownership='Both endpoints are zoneF; whole loss assignedF. It cancels from complete-zone midpoint balances.',
            original_R_X_B=[float(registry.loc[41][f'original_{x}_pu']) for x in ['r','x','b']],
            current_R_X_B=[float(current_R[40]),float(current_X[40]),float(current_B[40])]),
        parent224=dict(mean_loss_model_MW=float(loss[q,223].mean()),maximum_loss_model_MW=float(loss[q,223].max()),
            share_of_all_cohort_loss=float(loss[q,223].sum()/loss[q].sum()),share_of_E_assigned_loss=float(e_contrib.share_of_zone_assigned_loss),
            ownership='Half zoneE and half zoneG; releasedR remains an unverified network-equivalent parameter.',current_R_X_B=[.02,.0147,0.]),
        voltage=dict(hours_above_upper_limit=int((high>1.05+1e-7).sum()),hours_below_lower_limit=int((low<.95-1e-7).sum()),
            minimum_pu=float(low.min()),maximum_pu=float(high.max()),worst_overvoltage_rows=voltage_table.head(8).to_dict('records')),
        loss_allocation_reconstruction_maximum_error_model_MW=allocation_error,
        source_prior_findings=dict(western_AC_vs_DC_difference_small=True,
            PJM_original_vs_capacity_share_L1=float(abs(capacity_weight-weights).sum()),
            PJM_all8170_baseline_PG_share_max_difference_from_capacity_proportional=baseline_share_error,
            PJM_capacity_proportional_baseline_PG_and_loss_share_variants_are_no_ops=baseline_share_error<1e-12 and float(abs(capacity_weight-weights).sum())<1e-12,
            external_proxy_identity='Finite regional generation equivalents, not observed individual plant schedules; bus names alone do not establish a defect.'),
        persistent_overvoltage_construction_context=persistent_voltage_context,
        saved_counterfactual_scope=dict(CE_bridge_hours=bridge['hours'],CE_bridge_baseline=bridge['baseline_HEAD'],
            current_model_causal_attribution=False,reason='The saved bridge uses the older single-slackAC model and its8494-hour cohort. Its solved-loss reconstruction and row224X effect cannot be transferred as a causal decomposition of the current loss-consistent residuals.',
            western_effect_scope='The saved western source correction is source-conditioned DC evidence on its own8651-hour cohort; current matched-8170 AC/DC table is supplied separately.'),
        recommendations=[
            'Use complete-cut accounting to distinguish fixed zonal/source terms, external landing distribution and signed terminal half-loss corrections before perturbing impedance.',
            'Bounded Niagara/StLawrence hydro redistributions preserve statewideHY and are suitable mechanism probes for western/northern cut residuals; use a calendar-selected cohort and retain donor/capacity records.',
            'PJM baseline-PG redistribution and loss-participation-weight changes are separate assumptions; hold regional totals and finite originalP/S caps, and rebuild policy/context before solving.',
            'Use ac_loss_apply_budget (packaged nylatest_apply_budget) to update allocated externalP and its Q-circle slice at unchangedS; never keep oldQ bounds after changing externalP.',
            'A parent41 importedRX (and separately importedRXB) probe diagnoses the oversized withinF loss mechanism. It is an admittance sensitivity, not a new conductor realization or a promised interface-error repair.',
            'Parent224R is unresolved: any loss-isolation experiment must remain explicitly diagnostic, with no observation-selected replacement or operational promotion.',
            'Inspect the recurring overvoltage locations and their charging/shunt/PV assumptions separately; improving a power-flow score cannot establish voltage/reactive feasibility.'
        ],association_limit='Pearson and month-demeaned correlations/strata are descriptive, post-hoc and noncausal. Calendar selection and controlled probes are required for intervention claims.',
        user_uncommitted_map_files_preserved=True,protected_user_map_files=protected,
        inputs=[record(p) for p in paths]+[record(Path(__file__).resolve())],outputs=outputs)
    target=OUT/'physics_review.json';target.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ['passed','hours','mean_total_loss_model_MW','maximum_total_loss_model_MW','parent41','parent224','voltage','source_prior_findings']},indent=2))


if __name__=='__main__':main()
