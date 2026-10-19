"""Export source-backed scientific diagnostic figures (no model fitting)."""
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/nygrid_2025_remaining_errors'

def main():
    dest=OUT/'figures';dest.mkdir(exist_ok=True)
    annual=pd.read_csv(OUT/'baseline/annual_metrics.csv').sort_values('mae_public_MW')
    monthly=pd.read_csv(OUT/'baseline/month_metrics.csv');hour=pd.read_csv(OUT/'baseline/local_hour_metrics.csv')
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False,'axes.titleweight':'bold','figure.facecolor':'white','savefig.facecolor':'white'})
    fig,axes=plt.subplots(1,2,figsize=(12,5),layout='constrained')
    labels={'DYSINGER EAST':'Dysinger East','WEST CENTRAL':'West Central','TOTAL EAST':'Total East','MOSES SOUTH':'Moses South','CENTRAL EAST - VC':'Central East – VC','UPNY CONED':'UPNY–ConEd','SPR/DUN-SOUTH':'SPR/DUN–South'}
    ax=axes[0];ax.barh([labels[x] for x in annual.interface],annual.mae_public_MW,color='#2763A8',height=.65)
    for i,val in enumerate(annual.mae_public_MW):ax.text(val+8,i,f'{val:.0f}',va='center')
    ax.set_xlim(0,560);ax.set_xlabel('Mean absolute error (public-scale MW)');ax.set_title('Annual interface errors');ax.grid(axis='x',alpha=.18);ax.set_axisbelow(True)
    colors=['#2763A8','#C07B1B','#555555'];styles=['-','--',':']
    for interface,col,style in zip(['DYSINGER EAST','WEST CENTRAL','TOTAL EAST'],colors,styles):
        x=monthly[monthly.interface.eq(interface)].sort_values('group')
        axes[1].plot(x.group,x.bias_public_MW,label=labels[interface],color=col,linestyle=style,linewidth=2,marker='o',markersize=3)
    axes[1].axhline(0,color='#333333',linewidth=.8);axes[1].set_xticks(range(1,13),['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'],rotation=45,ha='right')
    axes[1].set_ylabel('Model minus observation (public-scale MW)');axes[1].set_title('Monthly signed errors');axes[1].legend(frameon=False,fontsize=9);axes[1].grid(alpha=.18)
    fig.suptitle('Current loss-consistent AC model • 8,170 qualified hours in 2025',fontsize=13)
    fig.savefig(dest/'remaining_interface_errors.png',dpi=180);fig.savefig(dest/'remaining_interface_errors.pdf');plt.close(fig)
    a=np.load(ROOT/'output/nygrid_2025_ac_loss_revision/comparison/combined/comparison_arrays.npz');q=a['revised_qualified'];e=a['revised_legacy_signed_literal_from'][q]-a['observed'][q]
    fig,axes=plt.subplots(1,2,figsize=(11,4.7),layout='constrained')
    axes[0].scatter(e[:,0],e[:,1],s=4,alpha=.15,color='#2763A8',rasterized=True)
    axes[0].plot([-1100,1100],[-1100,1100],color='#333333',lw=.9,ls='--');axes[0].set(xlim=(-1100,1100),ylim=(-1100,1100),xlabel='Dysinger East error (public MW)',ylabel='West Central error (public MW)',title='Shared western residual')
    axes[0].text(.04,.94,f'Correlation {np.corrcoef(e[:,:2].T)[0,1]:.4f}\nMean |difference| {np.mean(abs(e[:,1]-e[:,0])):.1f} MW',transform=axes[0].transAxes,va='top')
    for interface,col,style in zip(['DYSINGER EAST','WEST CENTRAL'],colors,styles):
        x=hour[hour.interface.eq(interface)].sort_values('group');axes[1].plot(x.group,x.bias_public_MW,color=col,ls=style,lw=2,label=labels[interface])
    axes[1].axhline(0,color='#333333',lw=.8);axes[1].set_xticks([0,3,6,9,12,15,18,21,23]);axes[1].set(xlabel='Hour in America/New_York',ylabel='Mean model minus observation (public MW)',title='Mean error by local hour');axes[1].legend(frameon=False);axes[1].grid(alpha=.18)
    fig.suptitle('Frozen model cuts; physical P32 meter equivalence remains unverified',fontsize=12)
    fig.savefig(dest/'western_shared_residual.png',dpi=180);fig.savefig(dest/'western_shared_residual.pdf');plt.close(fig)
    print('Wrote two PNG/PDF figure pairs from saved annual diagnostics.')
if __name__=='__main__':main()
