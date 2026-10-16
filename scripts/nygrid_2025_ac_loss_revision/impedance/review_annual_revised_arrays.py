"""Independent annual readback of revised148-bus AC/loss-accounting results.

No producer solver or accounting implementation is imported. Rebuilds full
branch laws, KCL, passive-interior recovery and source accounting from arrays.
"""
from pathlib import Path
from datetime import datetime,timezone
import argparse,copy,hashlib,json
import numpy as np
import pandas as pd
from scipy.io import loadmat
from scipy.linalg import solve

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'output/nygrid_2025_ac_loss_revision/impedance'
REGIONS=['ISONE','ONTARIO','PJM'];ZONES=list('ABCDEFGHIJK')


def record(p):
    with p.open('rb') as f:h=hashlib.file_digest(f,'sha256').hexdigest()
    return dict(path=p.relative_to(ROOT).as_posix(),sha256=h)


def vec(d,k,dtype=float):return np.asarray(d[k],dtype=dtype).reshape(-1)
def mx(x):return float(np.max(abs(np.asarray(x)),initial=0))
def region(area):return {1:'ISONE',2:'NY',3:'NY',4:'ONTARIO',5:'PJM',6:'PJM'}[int(area)]


def build_Y(bus,branch,base):
    lookup={int(x):i for i,x in enumerate(bus[:,0])};Y=np.diag((bus[:,4]+1j*bus[:,5])/base).astype(complex)
    for b in branch:
        if b[10]<=0:continue
        f,t=lookup[int(b[0])],lookup[int(b[1])];y=1/complex(b[2],b[3]);bc=1j*b[4]/2
        tap=(b[8] if b[8] else 1)*np.exp(1j*np.deg2rad(b[9]))
        Y[f,f]+=(y+bc)/abs(tap)**2;Y[t,t]+=y+bc;Y[f,t]-=y/np.conj(tap);Y[t,f]-=y/tap
    return Y


def main(run_dir,partial=False):
    run_dir=run_dir.resolve();paths=[Path(__file__)]
    def mat(path,**kw):paths.append(path);return loadmat(path,simplify_cells=True,**kw)
    axes=mat(run_dir/'annual_axes.mat')
    if partial:
        captured=json.loads((run_dir/'annual_progress.json').read_text());months_to_check=int(captured['months_complete'])
        snapshot=OUT/f"{captured['run_label']}_partial_{months_to_check:02d}_progress_snapshot.json"
        snapshot.write_text(json.dumps(captured,indent=2)+'\n');paths.append(snapshot)
        records=axes['source_records'];records=[records] if isinstance(records,dict) else list(records)
        producer=dict(completed=False,options=axes['options'],source_records=records,run_label=captured['run_label'],
            policy_equation_qualified_hours=captured['qualified'],solver_exceptions=captured['solver_exceptions'])
    else:
        p=run_dir/'annual_loss_policy_receipt.json';producer=json.loads(p.read_text());paths.append(p)
        assert producer['completed'] and producer['source_files_unchanged_during_replay'] and producer['replay_integrity_passed']
        months_to_check=12
    assert producer['options']['backend']=='compact'
    mode=producer['options']['impedance_mode'];lossmode=producer['options']['loss_mode']
    assert mode in ['released_equivalent','legacy_engineering'] and lossmode in ['boundary_consistent','legacy_single_slack']
    for item in producer['source_records']:
        f=Path(item['path'])
        with f.open('rb') as stream:current_hash=hashlib.file_digest(stream,'sha256').hexdigest()
        assert current_hash==item['sha256'],str(f)
    ids=vec(axes,'bus_id',int);keys=vec(axes,'branch_keys',str)
    lookup={int(x):i for i,x in enumerate(ids)};keylookup={x:i for i,x in enumerate(keys)}
    dispatch=mat(ROOT/'output/nygrid_2025_dispatch/dispatch/dispatch.mat',variable_names=['hour_index','timestamp_utc','bus_pd','bus_qd','dc_pf','reference_bus','gamma'])
    western=mat(ROOT/'output/nygrid_2025_western_audit/dispatch/all_boundary_actual_dispatch.mat',
        variable_names=['hour_index','timestamp_utc','gen_pg','P34_control_targets_model_mw','qualified','actual_regional_import_public_mw','region_labels','external_generator_rows_1based','native_generator_rows_1based'])
    landing=mat(ROOT/'output/nygrid_2025_western_audit/replay/dated_combined.mat',variable_names=['corrected_generator_buses'])
    operating=mat(ROOT/'output/nygrid_2025_inputs/model/operating_inputs.mat',variable_names=['base_case','zone_names','zonal_load_model_mw'])
    dover=mat(ROOT/'output/nygrid_2025_dover_parameters/replay/operating_states.mat',variable_names=['qualified','controls','timestamp_utc','gamma'])
    shares_path=ROOT/'output/nygrid_2025_western_audit/dispatch/all_boundary_external_generator_shares.csv';paths.append(shares_path)
    shares=pd.read_csv(shares_path).sort_values('model_gen_row_1based');ext=shares.model_gen_row_1based.to_numpy(int)-1
    genbus=vec(landing,'corrected_generator_buses',int);native=vec(western,'native_generator_rows_1based',int)-1
    caps=operating['base_case']['gen'][shares.parent_gen_row.to_numpy(int)-1]
    assert np.array_equal(caps[:,0].astype(int),shares.bus_id.to_numpy(int))
    assert np.array_equal(ext+1,vec(western,'external_generator_rows_1based',int)) and len(ext)==28
    assert np.array_equal(vec(axes,'generator_bus_id',int),genbus)
    HQ=np.flatnonzero(shares.region.to_numpy(str)=='HQ');assert len(HQ)==1;HQ=int(HQ[0])
    register_path=ROOT/'output/nygrid_2025_downstate/network/bus_register.csv';paths.append(register_path)
    registry=pd.read_csv(register_path,keep_default_na=False)
    anchors_path=ROOT/'output/nygrid_2025_slim/network/bus_register.csv';paths.append(anchors_path)
    anchors=pd.read_csv(anchors_path).model_bus.to_numpy(int);keepglobal=np.asarray([lookup[x] for x in anchors]);assert len(anchors)==148
    full=mat(ROOT/'output/nygrid_2025_line_parameters/overlays/engineering_nominal/full191_network_cases.mat')
    post=mat(ROOT/'output/nygrid_2025_dover_parameters/network/x_nominal.mat')
    npz=ROOT/'output/nygrid_2025_dover_parameters/replay/bounded_x_nominal.npz';paths.append(npz)
    with np.load(npz,allow_pickle=False) as d:state_names=d['network_state_ids'].astype(str);times=d['timestamp_utc'].astype(str);q=d['qualified'].astype(bool)
    ordered=['refined_2025_pre_may_case','refined_2025_may21_case','refined_2025_may30_case','refined_2025_case']
    states=np.asarray([ordered.index(s)+1 for s in state_names]);gamma=float(dispatch['gamma'])
    assert np.array_equal(times,vec(axes,'timestamp_utc',str)) and np.array_equal(q,vec(axes,'source_qualified',bool))
    assert np.array_equal(states,vec(axes,'topology_state_index',int)) and np.array_equal(q,vec(dover,'qualified',bool)) and q.sum()==8651
    assert np.array_equal(times,vec(dispatch,'timestamp_utc',str)) and np.array_equal(times,vec(western,'timestamp_utc',str))
    assert gamma==float(axes['gamma'])==float(dover['gamma']) and list(operating['zone_names'])==ZONES
    months=pd.to_datetime(times,utc=True).tz_convert('America/New_York').month.to_numpy()
    source_dc=np.column_stack([dispatch['dc_pf'],western['P34_control_targets_model_mw']])
    gross=operating['zonal_load_model_mw'];import_target=western['actual_regional_import_public_mw'][:,:3]*gamma
    templates={};template_changes=[]
    for state,hour in enumerate([1,3360,3576,8472],1):
        c=mat(ROOT/f'output/nygrid_2025_compact_ac/models/compact_ac_h{hour:04d}.mat')['model'];m=c['detailed_mpc']
        bus=np.asarray(m['bus']).copy();br=np.asarray(m['branch']).copy();parent=np.asarray(c['branch_parent_row'],int)
        p224=np.flatnonzero(parent==224);assert len(p224)==2
        if mode=='released_equivalent':br[p224,2:5]=[.01,.00735,0];br[p224,5:8]=0
        original=post['full_case'] if state==4 else full[ordered[state-1]]
        zones=np.asarray(post['full_bus_zones'] if state==4 else full['bus_zones']).astype(str)
        origbi={int(x):i for i,x in enumerate(original['bus'][:,0])};bi={int(x):i for i,x in enumerate(bus[:,0])}
        b=np.asarray([lookup[int(x)] for x in bus[:,0]]);l=np.asarray([keylookup[x] for x in np.asarray(c['branch_keys']).astype(str)])
        assert np.array_equal(vec(axes,'branch_parent_row',int)[l],parent)
        assert np.array_equal(vec(axes,'branch_from_bus',int)[l],br[:,0]) and np.array_equal(vec(axes,'branch_to_bus',int)[l],br[:,1])
        assert np.array_equal(vec(axes,'base_kv')[b],bus[:,9])
        k=np.asarray([bi[x] for x in anchors]);e=np.asarray([j for j in range(len(bus)) if j not in set(k)])
        assert np.all(bus[e,2:4]==0) and not np.isin(genbus,bus[e,0]).any()
        assert np.array_equal(genbus,m['gen'][:,0])
        f=np.asarray([bi[int(x)] for x in br[:,0]]);t=np.asarray([bi[int(x)] for x in br[:,1]])
        owner=np.zeros((len(br),14));wf=np.zeros((len(br),3));wt=wf.copy();D=np.zeros((6,3))
        for j,r in enumerate(original['branch']):
            members=np.flatnonzero(parent==j+1);of,ot=map(int,r[:2]);fi,ti=origbi[of],origbi[ot]
            rf,rt=region(original['bus'][fi,6]),region(original['bus'][ti,6])
            if rf==rt=='NY':owner[members,ZONES.index(zones[fi])]+=.5;owner[members,ZONES.index(zones[ti])]+=.5
            else:
                extregion=rf if rf!='NY' else rt;assert extregion in REGIONS
                assert rf==rt or 'NY' in (rf,rt)
                group=REGIONS.index(extregion);owner[members,11+group]=1
                if rf!=rt and r[10]>0 and j!=210:
                    first=members[br[members,0]==of];last=members[br[members,1]==ot];assert len(first)==len(last)==1
                    if rf=='NY':wf[first[0],group]=-1
                    else:wt[last[0],group]=-1
        for j,r in enumerate(m['dcline']):
            rf=region(original['bus'][origbi[int(r[0])],6]);rt=region(original['bus'][origbi[int(r[1])],6]);assert rt=='NY';D[j,REGIONS.index(rf)]=1
        nyzones=[np.asarray([bi[int(x)] for x in registry.loc[registry.accounting_zone==z,'model_bus'] if int(x) in bi]) for z in ZONES]
        templates[state]=(m,bus,br,parent,b,l,k,e,f,t,owner,wf,wt,D,nyzones)
        template_changes.append(dict(state=state,parent224_rows_1based=(p224+1).tolist(),parent224_R_X_B=br[p224,2:5].sum(axis=0).tolist(),all_non224_parameters_preserved=True))
    tolerances={'branch_law_MVA':1e-6,'current_A':1e-5,'KCL_MVA':1e-5,'loss_identity_MW':1e-6,'passive_voltage_recovery_pu':1e-8,
        'NY_gross_MW':1e-5,'regional_import_MW':1e-5,'loss_budget_MW':1e-5,'native_bus_PG_MW':1e-5,'HQ_PG_MW':1e-8,
        'external_P_bounds_MW':1e-5,'external_loss_increment_MW':1e-5,'served_load_shape_MW':1e-7,'QD_ratio_MVAr':1e-7,'DC_schedule_MW':1e-8}
    maximum={k:0. for k in tolerances};seen=np.zeros(8760,bool);goodall=seen.copy();exceptionall=seen.copy();attemptall=seen.copy()
    oldcohort_path=ROOT/'output/nygrid_2025_acpf_profile_audit/comparison/comparison_arrays.npz';paths.append(oldcohort_path)
    with np.load(oldcohort_path,allow_pickle=False) as oldarchive:oldgood=oldarchive['ACPF_comparison_cohort'].astype(bool)
    assert oldgood.sum()==8494
    failures=[];summary=[];min_attempted_NY_PD=np.inf;min_qualified_fraction=np.inf;max_qualified_lossfraction=0.
    negative_attempt_hours=[];nonpositive_zone_attempt_hours=[];qualified_equivalent=[];qualified_zone_rows=[]
    for month in range(1,months_to_check+1):
        d=mat(run_dir/f'monthly/profile_PF_2025_{month:02d}.mat');h=vec(d,'hour_index',int)-1
        assert np.array_equal(h,np.flatnonzero(months==month)) and not seen[h].any();seen[h]=True
        assert np.array_equal(vec(d,'timestamp_utc',str),times[h]) and float(d['gamma'])==gamma
        assert np.array_equal(vec(d,'source_qualified',bool),q[h]) and np.array_equal(vec(d,'topology_state_index',int),states[h])
        assert str(d['impedance_mode'])==mode and str(d['loss_mode'])==lossmode
        for key,expected in [('bus_id',ids),('branch_keys',keys),('generator_bus_id',genbus),('external_generator_rows_1based',ext+1),('retained_bus_ids',anchors)]:
            assert np.array_equal(vec(d,key,str if key=='branch_keys' else int),expected)
        for field in ['branch_parent_row','branch_from_bus','branch_to_bus','base_kv','DC_from_bus','DC_to_bus']:
            assert np.array_equal(vec(d,field),vec(axes,field))
        attempted=vec(d,'PF_attempted',bool);exceptions=vec(d,'solver_exception',bool);assert np.array_equal(attempted,q[h])
        attemptall[h]=attempted;exceptionall[h]=exceptions
        good=q[h]&vec(d,'PF_converged',bool)&vec(d,'AC_equation_gate',bool)&vec(d,'reduction_and_equation_gate',bool)
        if lossmode=='boundary_consistent':good&=vec(d,'loss_allocation_gate',bool)
        goodall[h]=good;assert np.array_equal(good,vec(d,'computed_current_available',bool))
        old=mat(ROOT/f'output/nygrid_2025_acpf_profile_audit/acpf/monthly/profile_PF_2025_{month:02d}.mat',variable_names=['hour_index','AC_equation_gate','P_profile_preservation_gate','source_qualified','bus_present','branch_present','branch_active'])
        og=vec(old,'source_qualified',bool)&vec(old,'AC_equation_gate',bool)&vec(old,'P_profile_preservation_gate',bool);assert np.array_equal(oldgood[h],og)
        assert np.array_equal(og,vec(d,'frozen_old_qualified',bool))
        assert np.array_equal(d['retained_VM'][good],d['VM'][good][:,keepglobal]) and np.array_equal(d['retained_VA'][good],d['VA'][good][:,keepglobal])
        for j in np.flatnonzero(q[h]&~good):
            sv=np.asarray(d['NY_served_PD_MW'])[j];bg=np.asarray(d['actual_budget_MW'])[j,:11]
            failures.append(dict(hour_index=int(h[j]+1),loss_status=str(np.asarray(d['loss_status']).reshape(-1)[j]),solver_exception=bool(exceptions[j]),old_qualified=bool(og[j]),valid_prediction=False,
                minimum_reported_NY_zonal_served_fraction=float(np.min(sv/gross[h[j]])) if np.isfinite(sv).all() else None,
                maximum_reported_NY_loss_fraction=float(np.max(bg/gross[h[j]])) if np.isfinite(bg).all() else None))
        for state in np.unique(states[h]):
            m,bus,br,parent,b,l,k,e,f,t,owner,wf,wt,D,nyzones=templates[int(state)];base=float(m['baseMVA']);on=br[:,10]>0
            returned=np.flatnonzero((states[h]==state)&q[h]&~exceptions)
            for field in ['bus_present','branch_present','branch_active']:assert np.array_equal(np.asarray(d[field],bool)[returned],np.asarray(old[field],bool)[returned])
            allny=np.unique(np.concatenate(nyzones));candidatePD=d['PD'][np.ix_(returned,b[allny])]
            finitePD=candidatePD[np.isfinite(candidatePD)];min_attempted_NY_PD=min(min_attempted_NY_PD,float(finitePD.min(initial=np.inf)))
            negative_attempt_hours.extend((h[returned[np.any(np.isfinite(candidatePD)&(candidatePD < -1e-9),axis=1)]]+1).tolist())
            candidate_zone=np.column_stack([np.sum(d['PD'][np.ix_(returned,b[zz])],axis=1) for zz in nyzones])
            nonpositive_zone_attempt_hours.extend((h[returned[np.any(np.isfinite(candidate_zone)&(candidate_zone<=0),axis=1)]]+1).tolist())
            use=np.flatnonzero((states[h]==state)&good);hu=h[use]
            if not len(use):continue
            V=d['VM'][np.ix_(use,b)]*np.exp(1j*np.deg2rad(d['VA'][np.ix_(use,b)]));assert np.isfinite(V).all()
            shifts=np.broadcast_to(br[:,9],(len(use),len(br))).copy()
            if state==4:
                phase=dover['controls']['bounded_x_nominal']['bank_shift_model_deg'][hu];assert np.array_equal(d['Dover_model_SHIFT_deg'][use],phase);shifts[:,410:412]=phase
            else:assert np.isnan(d['Dover_model_SHIFT_deg'][use]).all()
            tap=np.where(br[:,8]==0,1.,br[:,8])*np.exp(1j*np.deg2rad(shifts));y=np.zeros(len(br),complex);y[on]=1/(br[on,2]+1j*br[on,3]);bc=np.where(on,1j*br[:,4]/2,0j)
            Is=y*(V[:,f]/tap-V[:,t]);If=Is/np.conj(tap)+bc*V[:,f]/abs(tap)**2;It=-Is+bc*V[:,t]
            F=base*V[:,f]*np.conj(If);T=base*V[:,t]*np.conj(It)
            maximum['branch_law_MVA']=max(maximum['branch_law_MVA'],mx(F-d['PF'][np.ix_(use,l)]-1j*d['QF'][np.ix_(use,l)]),mx(T-d['PT'][np.ix_(use,l)]-1j*d['QT'][np.ix_(use,l)]))
            for name,value in [('Ifrom',abs(If)*base*1000/(np.sqrt(3)*bus[f,9])),('Ito',abs(It)*base*1000/(np.sqrt(3)*bus[t,9])),('Iseries',abs(Is)*base*1000/(np.sqrt(3)*bus[t,9]))]:
                maximum['current_A']=max(maximum['current_A'],mx(value-d[name][np.ix_(use,l)]))
            losses=(F+T).real;maximum['loss_identity_MW']=max(maximum['loss_identity_MW'],mx(losses-base*br[:,2]*abs(Is)**2))
            PD=d['PD'][np.ix_(use,b)];QD=d['QD'][np.ix_(use,b)];assert np.all(PD[:,e]==0) and np.all(QD[:,e]==0)
            net=d['bus_PG'][np.ix_(use,b)]+1j*d['bus_QG'][np.ix_(use,b)]-PD-1j*QD-abs(V)**2*(bus[:,4]-1j*bus[:,5])
            for j,r in enumerate(m['dcline']):
                fi=np.flatnonzero(bus[:,0]==r[0])[0];ti=np.flatnonzero(bus[:,0]==r[1])[0]
                net[:,fi]+=-d['DC_PF'][use,j]+1j*d['DC_QF'][use,j];net[:,ti]+=d['DC_PT'][use,j]+1j*d['DC_QT'][use,j]
            for j in range(len(br)):net[:,f[j]]-=F[:,j];net[:,t[j]]-=T[:,j]
            maximum['KCL_MVA']=max(maximum['KCL_MVA'],mx(net))
            maximum['DC_schedule_MW']=max(maximum['DC_schedule_MW'],mx(d['DC_PF'][use]-source_dc[hu]),mx(d['DC_PT'][use]-source_dc[hu]))
            budgets=losses@owner;imports=F.real@wf+T.real@wt+d['DC_PT'][use]@D
            maximum['loss_budget_MW']=max(maximum['loss_budget_MW'],mx(budgets-d['actual_budget_MW'][use]))
            if lossmode=='boundary_consistent':maximum['regional_import_MW']=max(maximum['regional_import_MW'],mx(imports-import_target[hu]))
            assert mx(imports-d['regional_import_solved_MW'][use])<1e-5 and mx(import_target[hu]-d['regional_import_target_MW'][use])<1e-8
            zonal=np.column_stack([PD[:,zz].sum(axis=1) for zz in nyzones]);zq=np.column_stack([QD[:,zz].sum(axis=1) for zz in nyzones])
            assert mx(zonal-d['NY_served_PD_MW'][use])<1e-7 and mx(zq-d['NY_served_QD_MVAr'][use])<1e-7 and mx(gross[hu]-d['NY_gross_target_MW'][use])<1e-8
            ratio=zonal/gross[hu];min_qualified_fraction=min(min_qualified_fraction,float(ratio.min()));max_qualified_lossfraction=max(max_qualified_lossfraction,float((budgets[:,:11]/gross[hu]).max()))
            assert np.all(PD[:,allny]>=-1e-9) and np.all(ratio>0),'Qualified result violates positive delivered-demand domain'
            eq_loss=losses[:,parent==224].sum(axis=1);total_loss=losses.sum(axis=1)
            for j,hh in enumerate(hu):
                qualified_equivalent.append(dict(hour_index=int(hh+1),equivalent224_loss_model_MW=float(eq_loss[j]),
                    total_AC_loss_model_MW=float(total_loss[j]),equivalent224_share_of_total_AC_loss=float(eq_loss[j]/total_loss[j]),
                    equivalent224_share_of_NY_assigned_loss=float(eq_loss[j]/budgets[j,:11].sum())))
                for zz,zone in enumerate(ZONES):qualified_zone_rows.append(dict(hour_index=int(hh+1),zone=zone,gross_model_MW=float(gross[hh,zz]),
                    served_model_MW=float(zonal[j,zz]),assigned_loss_model_MW=float(budgets[j,zz]),served_fraction=float(ratio[j,zz]),loss_fraction=float(budgets[j,zz]/gross[hh,zz])))
            if lossmode=='boundary_consistent':maximum['NY_gross_MW']=max(maximum['NY_gross_MW'],mx(zonal+budgets[:,:11]-gross[hu]))
            expectedPD=np.zeros_like(PD);expectedQD=np.zeros_like(QD);expectedPD[:,:140]=dispatch['bus_pd'][hu];expectedQD[:,:140]=dispatch['bus_qd'][hu]
            for j,zz in enumerate(nyzones):expectedPD[:,zz]*=ratio[:,j,None];expectedQD[:,zz]*=ratio[:,j,None]
            maximum['served_load_shape_MW']=max(maximum['served_load_shape_MW'],mx(PD-expectedPD));maximum['QD_ratio_MVAr']=max(maximum['QD_ratio_MVAr'],mx(QD-expectedQD))
            extPG=d['external_gen_PG'][use];expectedbus=np.zeros_like(PD)
            bi={int(x):i for i,x in enumerate(bus[:,0])}
            for j in native:expectedbus[:,bi[int(genbus[j])]]+=western['gen_pg'][hu,j]
            for j,gb in enumerate(genbus[ext]):expectedbus[:,bi[int(gb)]]+=extPG[:,j]
            gd=d['bus_PG'][np.ix_(use,b)]-expectedbus
            if lossmode=='legacy_single_slack':gd[:,bi[50]]=0
            maximum['native_bus_PG_MW']=max(maximum['native_bus_PG_MW'],mx(gd));maximum['HQ_PG_MW']=max(maximum['HQ_PG_MW'],mx(extPG[:,HQ]-western['gen_pg'][hu,ext[HQ]]))
            if lossmode=='boundary_consistent':
                maximum['native_bus_PG_MW']=max(maximum['native_bus_PG_MW'],mx(vec(d,'native_PG_change_from_original_MW')[use]))
            maximum['external_P_bounds_MW']=max(maximum['external_P_bounds_MW'],float(np.maximum(0,np.maximum(caps[:,9]-extPG,extPG-caps[:,8])).max()))
            increments=np.column_stack([(extPG-western['gen_pg'][hu][:,ext])[:,shares.region.to_numpy(str)==rr].sum(axis=1) for rr in REGIONS])
            assert mx(increments-d['external_PG_increment_MW'][use])<1e-7
            if lossmode=='boundary_consistent':maximum['external_loss_increment_MW']=max(maximum['external_loss_increment_MW'],mx(increments-budgets[:,11:]))
            if state!=4:
                Y=build_Y(bus,br,base);ve=-solve(Y[np.ix_(e,e)],Y[np.ix_(e,k)]@V[:,k].T,assume_a='gen').T
                maximum['passive_voltage_recovery_pu']=max(maximum['passive_voltage_recovery_pu'],mx(ve-V[:,e]))
            else:
                for j in range(len(use)):
                    qbr=br.copy();qbr[:,9]=shifts[j];Y=build_Y(bus,qbr,base);ve=-solve(Y[np.ix_(e,e)],Y[np.ix_(e,k)]@V[j,k],assume_a='gen')
                    maximum['passive_voltage_recovery_pu']=max(maximum['passive_voltage_recovery_pu'],mx(ve-V[j,e]))
        summary.append(dict(month=month,source_qualified=int(q[h].sum()),revised_qualified=int(good.sum()),frozen_old_qualified=int(og.sum()),paired=int((good&og).sum()),new=int((good&~og).sum()),lost=int((og&~good).sum())))
        print(f'Independent revised annual month{month:02d}: qualified{good.sum()} new{(good&~og).sum()} lost{(og&~good).sum()}',flush=True)
    assert np.array_equal(seen,months<=months_to_check) and attemptall.sum()==q[seen].sum() and oldgood.sum()==8494
    assert goodall.sum()==producer['policy_equation_qualified_hours'] and exceptionall.sum()==producer['solver_exceptions']
    if not partial:assert seen.all() and (oldgood&goodall).sum()==producer['paired_old_new_qualified_hours']
    for name,limit in tolerances.items():assert maximum[name]<limit,(name,maximum[name],limit)
    suffix=f'partial_{months_to_check:02d}' if partial else 'annual'
    failedout=OUT/f"{producer['run_label']}_{suffix}_independent_failed_hours.csv";pd.DataFrame(failures).to_csv(failedout,index=False)
    eqtable=pd.DataFrame(qualified_equivalent);eqout=OUT/f"{producer['run_label']}_{suffix}_equivalent224_loss.csv";eqtable.to_csv(eqout,index=False)
    zonetable=pd.DataFrame(qualified_zone_rows);zone_summary=[]
    for z,g in zonetable.groupby('zone'):
        zone_summary.append(dict(zone=z,qualified_hours=len(g),minimum_served_fraction=float(g.served_fraction.min()),
            maximum_loss_fraction=float(g.loss_fraction.max()),mean_loss_fraction=float(g.loss_fraction.mean()),
            minimum_allocated_loss_model_MW=float(g.assigned_loss_model_MW.min()),maximum_allocated_loss_model_MW=float(g.assigned_loss_model_MW.max())))
    zoneout=OUT/f"{producer['run_label']}_{suffix}_zonal_loss_ranges.csv";pd.DataFrame(zone_summary).to_csv(zoneout,index=False)
    report=dict(passed=True,completed=not partial,created_utc=datetime.now(timezone.utc).isoformat(),
        scope='Independent saved-array physics, recovery, protected-parameter and source-accounting review of completed months only' if partial else 'Independent completed annual saved-array physics, recovery, protected-parameter and source-accounting review',
        months_checked=months_to_check,run_label=producer['run_label'],options=producer['options'],source_qualified_hours=int(q[seen].sum()),revised_qualified_hours=int(goodall.sum()),
        full_annual_source_qualified_hours=8651,full_annual_frozen_old_qualified_hours=8494,evaluated_frozen_old_qualified_hours=int((oldgood&seen).sum()),
        paired_hours=int((oldgood&goodall).sum()),new_hours=int((q&~oldgood&goodall).sum()),lost_hours=int((oldgood&seen&~goodall).sum()),
        unqualified_source_hours=int((q&seen&~goodall).sum()),solver_exceptions=int(exceptionall.sum()),
        full_network_branch_laws_KCL_loss_current_and_voltage_recovery_checked=True,
        original_non224_R_X_B_taps_phase_and_shunts_used_without_adjustment=True,parent224_expected_parameter_checks=template_changes,
        original_native_HQ_profiles_and_finite_external_caps_checked=True,NY_gross_served_loss_and_regional_import_equations_checked=True,
        frozen_time_source_masks_and_canonical_original_branch_axes_preserved=True,all_rejected_hours_excluded_from_prediction_checks=True,
        minimum_finite_NY_bus_PD_across_all_returned_attempts_MW=min_attempted_NY_PD,
        returned_attempts_with_finite_negative_NY_bus_PD_hours=negative_attempt_hours,
        returned_attempts_with_nonpositive_NY_zonal_served_demand_hours=nonpositive_zone_attempt_hours,
        qualified_positive_domain_violations=0,
        minimum_qualified_NY_zonal_served_fraction=min_qualified_fraction,maximum_qualified_NY_zonal_loss_fraction=max_qualified_lossfraction,
        equivalent224_qualified_loss_ranges=dict(minimum_model_MW=float(eqtable.equivalent224_loss_model_MW.min()),mean_model_MW=float(eqtable.equivalent224_loss_model_MW.mean()),
            maximum_model_MW=float(eqtable.equivalent224_loss_model_MW.max()),minimum_share_total_AC_loss=float(eqtable.equivalent224_share_of_total_AC_loss.min()),
            mean_share_total_AC_loss=float(eqtable.equivalent224_share_of_total_AC_loss.mean()),maximum_share_total_AC_loss=float(eqtable.equivalent224_share_of_total_AC_loss.max())),
        zonal_loss_ranges=zone_summary,
        maximum_independent_errors=maximum,tolerances=tolerances,months=summary,
        limitations=['Qualification here certifies the stated synthetic equations and accounting. It is not as-built impedance, physical interface membership or operating-feasibility certification.',
            'Failed or partial iterates are retained and flagged. Their nonconvergence is not proof of global infeasibility.',
            'The source-equivalent R=.02 remains unverified physically; no alternative R is selected by convergence or NYISO scoring.'],
        dependencies=[record(p) for p in dict.fromkeys(paths)],outputs=[record(failedout),record(eqout),record(zoneout)])
    target=OUT/f"{producer['run_label']}_{suffix}_arrays_independent_review.json";target.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ['dependencies','outputs','months','parent224_expected_parameter_checks']},indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--run-dir',type=Path,required=True);parser.add_argument('--partial',action='store_true');args=parser.parse_args();main(args.run_dir,args.partial)
