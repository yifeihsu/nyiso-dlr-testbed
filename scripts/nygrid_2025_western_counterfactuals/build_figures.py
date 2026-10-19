"""Static scientific figures for the predeclared matched western experiments."""
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from common import OUT,atomic_json,record,require

def build():
    annual=pd.read_csv(OUT/'comparison/annual_metrics.csv')
    monthly=pd.read_csv(OUT/'comparison/monthly_metrics.csv')
    require(set(annual.hours)=={8651},'Figure includes incomparable cohorts')
    modes=['baseline','niagara_legacy_bounded_outside_ab','niagara_month_shape_literal_outside_ab']
    labels=['Baseline','Bounded legacy Niagara rule','EIA monthly mean; same hourly shape']
    colors=['#7a8592','#286fac','#ad731a'];markers=['o','s','^']
    selected=annual[annual.scenario.isin(modes)&annual.interface.isin(['DYSINGER EAST','WEST CENTRAL'])]
    require(len(selected)==6,'Incomplete figure input')
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11,'axes.spines.top':False,
        'axes.spines.right':False,'axes.edgecolor':'#82909e','text.color':'#28313d','axes.labelcolor':'#28313d'})
    fig,axes=plt.subplots(1,2,figsize=(14.4,7.2),gridspec_kw={'width_ratios':[1,1.1]})
    fig.subplots_adjust(left=.15,right=.96,top=.73,bottom=.24,wspace=.34)
    handles=[]
    for i,(mode,label,color,marker) in enumerate(zip(modes,labels,colors,markers)):
        values=selected[selected.scenario.eq(mode)].set_index('interface').loc[['DYSINGER EAST','WEST CENTRAL'],'mae_public_mw'].to_numpy()
        y=np.arange(2)+(i-1)*.23
        bars=axes[0].barh(y,values,height=.20,color=color,label=label)
        handles.append(bars)
        for yy,value in zip(y,values):axes[0].text(value+1.3,yy,f'{value:.1f}',va='center',fontsize=10)
        rows=monthly[monthly.scenario.eq(mode)&monthly.interface.eq('DYSINGER EAST')].sort_values('month')
        require(rows.month.tolist()==list(range(1,13)),'Missing monthly figure point')
        axes[1].plot(rows.month,rows.bias_public_mw,label=label,color=color,marker=marker,linewidth=1.7,markersize=4)
    axes[0].set_yticks([0,1],['Dysinger East','West Central']);axes[0].invert_yaxis();axes[0].set_xlim(0,290)
    axes[0].set_xlabel('Mean absolute error (public-equivalent MW)')
    axes[0].set_title('Annual western MAE',loc='left',fontweight='bold',pad=15)
    axes[0].grid(axis='x',color='#e7ebef');axes[0].set_axisbelow(True)
    axes[1].axhline(0,color='#465361',linewidth=.9)
    axes[1].set_xticks(range(1,13),['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'],fontsize=9)
    axes[1].set_xlim(.8,12.2);axes[1].set_ylabel('Predicted − observed (public-equivalent MW)')
    axes[1].set_title('Dysinger monthly signed bias',loc='left',fontweight='bold',pad=15)
    axes[1].grid(axis='y',color='#e7ebef');axes[1].set_axisbelow(True)
    fig.suptitle('Controlled western-flow tests, 2025',x=.15,y=.97,ha='left',fontsize=21,fontweight='bold')
    fig.text(.15,.90,'8,651 identical hours • fixed external flows and zonal loads • dated topology • no interface fitting',fontsize=11)
    fig.legend(handles,labels,loc='lower left',bbox_to_anchor=(.15,.805),ncol=3,frameon=False,fontsize=10)
    fig.text(.15,.075,'Niagara changes are balanced by other conventional hydro outside Zones A/B. St. Lawrence and pumped storage remain fixed.\n'
        'The legacy hypothesis is explicitly capacity-bounded in 277 hours. The monthly case tests a source mean, retaining the baseline shape.\n'
        'Within-zone load tests and independent zone-cut operators leave both western predictions unchanged; physical gate membership remains unresolved.',fontsize=9.5)
    folder=OUT/'figures';folder.mkdir(parents=True,exist_ok=True)
    outputs=[]
    for suffix in ['png','pdf','svg']:
        path=folder/('matched_western_tests.'+suffix);fig.savefig(path,dpi=180,facecolor='white');outputs.append(path)
    plt.close(fig)
    selected.to_csv(folder/'plotted_annual_scores.csv',index=False,lineterminator='\n');outputs.append(folder/'plotted_annual_scores.csv')
    atomic_json(folder/'figure_validation.json',dict(passed=True,fixed_hours=8651,source_values_checked=True,
        no_causal_error_share_claim=True,inputs=[record(OUT/'comparison/annual_metrics.csv'),record(OUT/'comparison/monthly_metrics.csv'),record(Path(__file__))],
        outputs=[record(p) for p in outputs]))

if __name__=='__main__':build()
