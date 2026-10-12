"""Trace charging and reactive series losses in saved failed AC trial points.

Diagnostic trial voltages are not feasible operating states. No parameter,
reactive bound, compensation amount or capability is fitted by this script.
"""
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT=Path(__file__).resolve().parents[3]
FOLDER=ROOT/'output/nygrid_2025_ac_system/ac_validation/electrical_revision02'


def main():
    line_tables=[];bus_tables=[];receipts=[]
    for path in sorted(FOLDER.glob('hour_[0-9][0-9][0-9][0-9].mat')):
        data=loadmat(path,simplify_cells=True);m=data['m'];r=data['r'];a=data['a']
        h=int(a['hour_index']);b=m['bus'];br=m['branch'];g=r['gen'];dc=r['dcline']
        ix={int(bus):i for i,bus in enumerate(b[:,0])}
        fi=np.array([ix[int(v)] for v in br[:,0]]);ti=np.array([ix[int(v)] for v in br[:,1]])
        V=r['bus'][:,7]*np.exp(1j*np.deg2rad(r['bus'][:,8]))
        tau=br[:,8].copy();tau[tau==0]=1;tap=tau*np.exp(1j*np.deg2rad(br[:,9]))
        on=br[:,10]>0
        I=np.zeros(len(br),complex);I[on]=(V[fi[on]]/tap[on]-V[ti[on]])/(br[on,2]+1j*br[on,3])
        Qcf=100*br[:,4]/2*abs(V[fi]/tap)**2*on
        Qct=100*br[:,4]/2*abs(V[ti])**2*on
        Qseries=100*br[:,3]*abs(I)**2
        Qsaved=r['branch'][:,14]+r['branch'][:,16]
        err=Qsaved-(Qseries-Qcf-Qct)
        assert np.max(abs(err))<1e-6
        lines=pd.DataFrame({'hour_index':h,'branch_row':np.arange(1,len(br)+1),
            'from_bus':br[:,0].astype(int),'to_bus':br[:,1].astype(int),'active':on,
            'from_base_kv':b[fi,9],'to_base_kv':b[ti,9], 'B_pu':br[:,4],
            'from_charging_at_trial_voltage_MVAr':Qcf,'to_charging_at_trial_voltage_MVAr':Qct,
            'total_charging_at_trial_voltage_MVAr':Qcf+Qct,
            'series_X_reactive_loss_at_trial_current_MVAr':Qseries,
            'total_terminal_Q_outflow_MVAr':Qsaved,'reactive_branch_identity_error_MVAr':err})
        line_tables.append(lines)
        charge=np.bincount(fi,weights=Qcf,minlength=len(b))+np.bincount(ti,weights=Qct,minlength=len(b))
        gb=np.array([ix[int(v)] for v in g[:,0]]);gon=g[:,7]>0
        Qgen=np.bincount(gb,weights=g[:,2]*gon,minlength=len(b))
        Qmin=np.bincount(gb,weights=m['gen'][:,4]*gon,minlength=len(b))
        Qmax=np.bincount(gb,weights=m['gen'][:,3]*gon,minlength=len(b))
        residual=data['detail']['Q_residual_mvar']
        buses=pd.DataFrame({'hour_index':h,'bus_id':b[:,0].astype(int),'bus_name':m['bus_name'],
            'trial_voltage_pu':abs(V),'positive_Q_residual_is_excess_injection_MVAr':residual,
            'allocated_line_charging_at_trial_voltage_MVAr':charge,
            'bus_shunt_injection_at_trial_voltage_MVAr':b[:,5]*abs(V)**2,
            'Qload_MVAr':b[:,3],'Qgen_at_trial_MVAr':Qgen,
            'Qgen_lower_bound_MVAr':Qmin,'Qgen_upper_bound_MVAr':Qmax})
        bus_tables.append(buses)
        receipts.append({'hour':h,'solver_success':bool(r['success']),
            'case_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'overlay_sha256':m['userdata']['ac_system']['branch_parameter_overlay_sha256'],
            'maximum_reactive_branch_identity_error_MVAr':float(np.max(abs(err))),
            'total_line_charging_at_trial_voltage_MVAr':float(np.sum(Qcf+Qct)),
            'top_Q_residual_buses':buses.iloc[np.argsort(abs(residual))[-4:][::-1]][['bus_id','positive_Q_residual_is_excess_injection_MVAr']].to_dict('records')})
    pd.concat(line_tables,ignore_index=True).to_csv(FOLDER/'reactive_branch_mechanisms.csv',index=False)
    pd.concat(bus_tables,ignore_index=True).to_csv(FOLDER/'reactive_bus_mechanisms.csv',index=False)
    report={'diagnostic_complete':True,'diagnostic_only':True,'feasible_operating_states_claimed':False,
        'compensation_sized_or_fitted':False,'bounds_or_inputs_modified':False,'cases':receipts,
        'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (FOLDER/'reactive_diagnostic_receipt.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'complete':True,'cases':len(receipts),'maximum_Q_identity_error_MVAr':max(x['maximum_reactive_branch_identity_error_MVAr'] for x in receipts)}))


if __name__=='__main__':
    main()
