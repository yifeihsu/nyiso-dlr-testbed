"""Create slide-size vector figures from frozen 2019 study CSVs only.

No simulations, fitting, network changes or study-output rewrites occur here.
CSV data retain exact saved precision; TeX/figure labels round for presentation.
"""
from pathlib import Path
import calendar
import hashlib
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from PIL import Image, ImageOps, ImageDraw

ROOT=Path(__file__).resolve().parents[4]
DEST=Path(__file__).resolve().parent.parent
FIG=DEST/'figures'; DATA=DEST/'data'
SOURCE=ROOT/'output/nygrid_compact_2019'
NAMES=['Dysinger East','West Central','Total East','Moses South','Central East','UpNY-Coned','Dun/SPR-South']
SHORT=['Dysinger East','West Central','Total East','Moses South','Central East','UpNY-Coned','Dun/SPR-South']
COLORS={'navy':'#122A42','blue':'#256399','teal':'#0F8480','amber':'#DB8F18','grid':'#E2E7EC','muted':'#536778'}
MODELS=['reference_NY46__paper_roles','compact51__paper_roles','compact51_marcy__paper_roles']
LABELS=['NYgrid reference','Compact 51','Compact + Marcy']
MODEL_COLORS=[COLORS['navy'],COLORS['blue'],COLORS['teal']]
SOURCE_PATHS=[ROOT/'output/nygrid_2019/annual_reproduction_interface_metrics.csv',
              SOURCE/'annual_monthly_metrics.csv',SOURCE/'best_snapshots.csv',
              SOURCE/'best_snapshot_interface_errors.csv',
              SOURCE/'verification/selected_hour_source_quality.csv',
              SOURCE/'verification/independent_validation.json']

plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'text.color':COLORS['navy'],
    'axes.labelcolor':COLORS['navy'],'xtick.color':COLORS['muted'],'ytick.color':COLORS['navy'],
    'axes.edgecolor':COLORS['muted'],'axes.linewidth':.6,'axes.labelsize':10,
    'xtick.labelsize':9,'ytick.labelsize':10,'pdf.fonttype':42,'ps.fonttype':42,
    'figure.facecolor':'white','savefig.facecolor':'white','hatch.linewidth':.4})

def csv(t,name):
    t.to_csv(DATA/name,index=False,float_format='%.12g',lineterminator='\n')

def figure(width,height):
    return plt.figure(figsize=(width/2.54,height/2.54),dpi=200)

def header(fig,title,subtitle):
    fig.text(.015,.975,title,fontsize=12,fontweight='bold',va='top')
    fig.text(.015,.914,subtitle,fontsize=9,va='top',color=COLORS['muted'])

def style(ax,orientation='x'):
    ax.spines[['top','right']].set_visible(False)
    ax.tick_params(length=0,pad=4)
    ax.grid(axis=orientation,color=COLORS['grid'],linewidth=.65,zorder=0)
    ax.set_axisbelow(True)

dimensions=[]
def save(fig,stem,w,h,rows):
    fig.savefig(FIG/(stem+'.pdf'),metadata={'Title':stem,'Author':'Project research update',
        'Subject':'Source-backed DC interface comparison; no AC or thermal qualification'})
    fig.savefig(FIG/(stem+'.png'),dpi=220)
    assert b'/Subtype /Image' not in (FIG/(stem+'.pdf')).read_bytes(),'Expected vector-only PDF'
    dimensions.append(dict(figure=stem+'.pdf',width_cm=w,height_cm=h,source_rows=rows,
        vector_pdf=True,preview=stem+'.png'))
    plt.close(fig)

def tex_table(name,columns,rows,alignment):
    text=['% Generated from frozen study CSVs; requires booktabs.','\\begin{tabular}{'+alignment+'}',
          '\\toprule',' & '.join(columns)+' \\\\','\\midrule']
    text += [' & '.join(map(str,row))+' \\\\' for row in rows]
    text += ['\\bottomrule','\\end{tabular}','']
    (DATA/name).write_text('\n'.join(text),encoding='utf-8')

def main():
    FIG.mkdir(parents=True,exist_ok=True);DATA.mkdir(parents=True,exist_ok=True)
    annual_source=pd.read_csv(SOURCE_PATHS[0])
    annual_source=annual_source[(annual_source.scope=='primary_all_naive_hours')&
        (annual_source.operator_variant=='corrected_released_if_map')].set_index('interface').loc[NAMES].reset_index()
    metrics=pd.read_csv(SOURCE_PATHS[1]);best=pd.read_csv(SOURCE_PATHS[2]);details=pd.read_csv(SOURCE_PATHS[3])
    assert len(annual_source)==7 and (annual_source.observations==8760).all()
    assert len(metrics)==520 and len(best)==30 and len(details)==210
    contracts=[
        dict(figure='01_nygrid_annual_interface_wape',question='How large is the released NYgrid DC interface mismatch over 2019?',
             takeaway='Error varies by interface; West Central has the largest actual-flow WAPE.',family='horizontal_bar',rows=7,
             scope='8760 timezone-naive 2019 local hours, corrected if.map; no source-quality filter',width_cm=11.8,height_cm=7.5),
        dict(figure='02_annual_model_comparison',question='How does topology change affect the same annual inputs and role definitions?',
             takeaway='The two added Marcy reactances reduce Central East error but increase UpNY-Coned error.',family='grouped_horizontal_bar',rows=21,
             scope='Same scaled source injections and corrected paper-role operator semantics; annual WAPE',width_cm=13.0,height_cm=8.0),
        dict(figure='03_monthly_pooled_wape',question='Does the annual paper-role improvement persist across months?',
             takeaway='The Marcy variant improves pooled WAPE over Compact 51 in every month; the reference remains better overall.',family='three_series_line',rows=36,
             scope='12 calendar months in 2019; pool all seven overlapping interfaces with flow-weighted denominator',width_cm=13.0,height_cm=7.2),
        dict(figure='04_selected_snapshot_flows',question='How closely do two retrospectively selected hours reproduce observed flows?',
             takeaway='Both chosen hours align closely, but these are post-selection development examples.',family='faceted_paired_dot',rows=14,
             scope='Reference Jan8 best pooled vs compactMarcy July3 best minimax; actual-scale GW; equal panel scales',width_cm=13.0,height_cm=7.7)]
    for c in contracts:
        c.update(renderer='matplotlib vector PDF',delivery='16:9 Beamer slide',
                 palette=COLORS,non_color_encoding='ordered groups, hatches and line/marker styles',
                 qualification='DC only; retrospective development comparison')
    (DATA/'chart_contracts.json').write_text(json.dumps(contracts,indent=2)+'\n',encoding='utf-8')
    # First figure and exact source-rich data table.
    annual_source.insert(0,'interface_index',np.arange(1,8))
    annual_source['interface_label']=SHORT
    csv(annual_source,'01_nygrid_annual_interface_wape.csv')
    fig=figure(11.8,7.5);header(fig,'NYgrid annual interface error','2019 | 8,760 local hours | corrected paper operator')
    ax=fig.add_axes([.32,.24,.63,.58]); y=np.arange(7)
    ax.barh(y,annual_source.actual_flow_wape_pct,height=.58,color=COLORS['blue'],edgecolor=COLORS['navy'],linewidth=.4)
    ax.set_yticks(y,SHORT);ax.invert_yaxis();ax.set_xlim(0,53);ax.set_xticks([0,10,20,30,40,50])
    ax.set_xlabel('Actual-flow WAPE (%)',labelpad=6);style(ax)
    for yy,val in zip(y,annual_source.actual_flow_wape_pct):ax.text(val+.7,yy,f'{val:.1f}',va='center',fontsize=10)
    fig.text(.015,.027,'WAPE = 100 Σ |model − observed| / Σ |observed|',fontsize=8.5,color=COLORS['muted'])
    save(fig,'01_nygrid_annual_interface_wape',11.8,7.5,7)
    tex_table('annual_nygrid_table.tex',['Interface','WAPE (\\%)','MAE (MW)'],
        [[r.interface,f'{r.actual_flow_wape_pct:.2f}',f'{r.mae_mw:.1f}'] for r in annual_source.itertuples()],'lrr')
    # Annual three-model comparison; verify reference equality across exports.
    comparison=pd.DataFrame({'interface_index':np.arange(1,8),'interface':NAMES})
    annual_rows=[]
    for model,column in zip(MODELS,['nygrid_wape_pct','compact51_wape_pct','compact_marcy_wape_pct']):
        t=metrics[(metrics.experiment==model)&(metrics.period=='annual')].set_index('interface').loc[NAMES]
        comparison[column]=t.wape_pct.to_numpy()
        annual_rows.append(t.reset_index())
    assert np.max(np.abs(comparison.nygrid_wape_pct-annual_source.actual_flow_wape_pct))<1e-8
    comparison['hours']=8760;comparison['operator_roles']='corrected_paper_roles'
    comparison['injection_policy']='same_NYgrid_native_solved_PG_net_PD_and_fixed_AC_DC_HQ_boundary'
    csv(comparison,'02_annual_model_comparison.csv')
    csv(pd.concat(annual_rows,ignore_index=True),'02_annual_model_comparison_long.csv')
    fig=figure(13,8);header(fig,'Annual interface error across networks','2019 | identical scaled inputs | paper-role operators')
    ax=fig.add_axes([.29,.27,.67,.52]);offsets=[-.24,0,.24];hatches=['','///','']
    for k,col in enumerate(['nygrid_wape_pct','compact51_wape_pct','compact_marcy_wape_pct']):
        ax.barh(y+offsets[k],comparison[col],height=.205,label=LABELS[k],color=MODEL_COLORS[k],
            edgecolor=MODEL_COLORS[k],linewidth=.5,hatch=hatches[k],alpha=.96)
    ax.set_yticks(y,SHORT);ax.invert_yaxis();ax.set_xlim(0,55);ax.set_xticks([0,10,20,30,40,50]);style(ax)
    ax.set_xlabel('Actual-flow WAPE (%)',labelpad=6)
    fig.legend(*ax.get_legend_handles_labels(),loc='lower center',bbox_to_anchor=(.55,.015),ncol=3,
               fontsize=8.4,frameon=False,handlelength=1.4,columnspacing=1.2)
    save(fig,'02_annual_model_comparison',13,8,21)
    rows=[[r.interface,f'{r.nygrid_wape_pct:.2f}',f'{r.compact51_wape_pct:.2f}',f'{r.compact_marcy_wape_pct:.2f}'] for r in comparison.itertuples()]
    pooled=metrics[(metrics.period=='annual')&(metrics.interface=='ALL_SEVEN_POOLED')].set_index('experiment')
    rows.append(['\\midrule Pooled']+[f'{pooled.loc[m,"wape_pct"]:.2f}' for m in MODELS])
    tex_table('annual_comparison_table.tex',['Interface','NYgrid','Compact 51','+ Marcy'],rows,'lrrr')
    # Twelve-month series, all monthly cells, no best-month selection.
    monthly=pd.DataFrame({'month':np.arange(1,13),'month_label':[calendar.month_abbr[m] for m in range(1,13)]})
    month_long=[]
    for model,column in zip(MODELS,['nygrid_wape_pct','compact51_wape_pct','compact_marcy_wape_pct']):
        t=metrics[(metrics.experiment==model)&(metrics.interface=='ALL_SEVEN_POOLED')&metrics.period.str.startswith('month_')].copy()
        t['month']=t.period.str[-2:].astype(int);t=t.sort_values('month');assert len(t)==12
        monthly[column]=t.wape_pct.to_numpy();monthly['hours']=t.hours.to_numpy();monthly['interface_observations']=t.observations.to_numpy()
        month_long.append(t)
    assert monthly.hours.sum()==8760 and monthly.interface_observations.sum()==61320
    csv(monthly,'03_monthly_pooled_wape.csv');csv(pd.concat(month_long,ignore_index=True),'03_monthly_pooled_wape_long.csv')
    fig=figure(13,7.2);header(fig,'Monthly pooled interface error','2019 | seven interfaces | identical scaled source inputs')
    ax=fig.add_axes([.12,.25,.85,.54]);styles=[('o','-'),('s','--'),('D','-')]
    for k,col in enumerate(['nygrid_wape_pct','compact51_wape_pct','compact_marcy_wape_pct']):
        marker,ls=styles[k];ax.plot(monthly.month,monthly[col],label=LABELS[k],color=MODEL_COLORS[k],
            marker=marker,linestyle=ls,linewidth=1.6,markersize=4,markerfacecolor='white' if k==1 else MODEL_COLORS[k])
    ax.set_xticks(np.arange(1,13),monthly.month_label);ax.set_xlim(.7,12.3);ax.set_ylim(0,24);ax.set_yticks([0,5,10,15,20])
    ax.set_ylabel('Pooled WAPE (%)');style(ax,'y')
    fig.legend(*ax.get_legend_handles_labels(),loc='lower center',bbox_to_anchor=(.54,.066),ncol=3,
        fontsize=8.6,frameon=False,handlelength=1.7,columnspacing=1.1)
    fig.text(.015,.024,'Pooled over overlapping interfaces; not a statewide energy-balance error.',fontsize=8,color=COLORS['muted'])
    save(fig,'03_monthly_pooled_wape',13,7.2,36)
    tex_table('monthly_pooled_table.tex',['Month','Hours','NYgrid','Compact 51','+ Marcy'],
        [[r.month_label,str(r.hours),f'{r.nygrid_wape_pct:.2f}',f'{r.compact51_wape_pct:.2f}',f'{r.compact_marcy_wape_pct:.2f}'] for r in monthly.itertuples()],'lrrrr')
    # Two matched seven-interface paired-dot panels, same horizontal units.
    chosen=[('reference_NY46__paper_roles','2019-01-08 15:00:00','pooled'),
            ('compact51_marcy__paper_roles','2019-07-03 04:00:00','minimax')]
    snaps=[]
    for k,(model,time,criterion) in enumerate(chosen):
        t=details[(details.experiment==model)&(details.timestamp==time)&(details.criterion==criterion)].set_index('interface').loc[NAMES].reset_index()
        assert len(t)==7 and (t['rank']==1).all()
        t.insert(0,'panel',k+1);t.insert(1,'interface_index',np.arange(1,8))
        t['observed_gw']=t.observed_actual_mw/1000;t['predicted_gw']=t.predicted_actual_scale_mw/1000
        t['retrospectively_selected']=True;t['is_holdout']=False;snaps.append(t)
    snapshot=pd.concat(snaps,ignore_index=True);csv(snapshot,'04_selected_snapshot_flows.csv')
    for k,t in enumerate(snaps):csv(t,f'04_selected_snapshot_panel_{k+1}.csv')
    fig=figure(13,7.7);header(fig,'Selected-hour observed and modeled flows','Retrospective examples | same 0–5.2 GW scale in both panels')
    panel_titles=['NYgrid reference\nJan 8, 15:00','Compact + Marcy\nJul 3, 04:00']
    for k,t in enumerate(snaps):
        ax=fig.add_axes([.28+.365*k,.25,.33,.46])
        for yy,o,p in zip(y,t.observed_gw,t.predicted_gw):
            ax.plot([o,p],[yy,yy],color=COLORS['muted'],linewidth=1.4,zorder=2)
        ax.scatter(t.observed_gw,y-.065,s=27,facecolor='white',edgecolor=COLORS['navy'],linewidth=1,zorder=3)
        ax.scatter(t.predicted_gw,y+.065,s=23,marker='D',color=COLORS['teal'],zorder=3)
        ax.set_yticks(y,SHORT if k==0 else ['']*7);ax.set_ylim(6.6,-.6);ax.set_xlim(0,5.2)
        ax.set_xticks([0,1,2,3,4,5]);style(ax)
        ax.set_title(panel_titles[k],fontsize=10,fontweight='bold',pad=8)
    handles=[Line2D([0],[0],linestyle='none',marker='o',markerfacecolor='white',markeredgecolor=COLORS['navy'],label='Observed'),
             Line2D([0],[0],linestyle='none',marker='D',color=COLORS['teal'],label='Modeled')]
    fig.legend(handles=handles,loc='lower center',bbox_to_anchor=(.64,.045),ncol=2,fontsize=9,frameon=False)
    fig.text(.635,.151,'Flow (GW, actual scale)',fontsize=9,ha='center')
    fig.text(.015,.024,'Compact values divided by fixed γ = 0.3586622254 for display.',fontsize=8,color=COLORS['muted'])
    save(fig,'04_selected_snapshot_flows',13,7.7,14)
    wide=pd.DataFrame({'interface':NAMES})
    for k,t in enumerate(snaps):
        prefix='jan8' if k==0 else 'jul3'
        for col,new in [('observed_actual_mw','observed_mw'),('predicted_actual_scale_mw','modeled_mw'),('absolute_error_pct','error_pct')]:wide[prefix+'_'+new]=t[col].to_numpy()
    csv(wide,'selected_snapshot_table.csv')
    tex_table('selected_snapshot_table.tex',['Interface','Jan 8 err.','Jul 3 err.'],
        [[r.interface,f'{r.jan8_error_pct:.2f}\\%',f'{r.jul3_error_pct:.2f}\\%'] for r in wide.itertuples()],'lrr')
    # Compact lookup tables for main slides and appendix; no optional heatmap
    # because a 3x7 percentage matrix duplicates exact table lookup better.
    selected=best[best.experiment==MODELS[2]].copy();csv(selected,'compact_best_rankings.csv')
    tex_table('compact_best_rankings_table.tex',['Criterion','Rank','2019 hour','Pooled','Worst'],
        [[r.criterion,str(r.rank),pd.Timestamp(r.timestamp).strftime('%b %d %H:%M'),
          f'{r.pooled_error_pct:.2f}\\%',f'{r.worst_interface_error_pct:.2f}\\%'] for r in selected.itertuples()],'llcrr')
    quality=pd.read_csv(SOURCE_PATHS[4]);csv(quality,'selected_hour_quality.csv')
    (DATA/'figure_usage.tex').write_text('''% All figures are vector PDF, at their native slide-ready dimensions.
% Example: \\includegraphics[width=11.8cm]{figures/01_nygrid_annual_interface_wape.pdf}
% The other three figures are 13cm wide. Tables require \\usepackage{booktabs}.
% Native pgfplots can read CSV columns directly, e.g.:
% \\addplot table[x=month,y=nygrid_wape_pct,col sep=comma]{data/03_monthly_pooled_wape.csv};
% \\addplot table[x=month,y=compact51_wape_pct,col sep=comma]{data/03_monthly_pooled_wape.csv};
% \\addplot table[x=month,y=compact_marcy_wape_pct,col sep=comma]{data/03_monthly_pooled_wape.csv};
''',encoding='utf-8')
    notes='''# Figure data and claim boundaries

All graphics use frozen CSVs from the completed studies. No model or operating input is changed or fitted here.

WAPE = 100 sum(abs(modeled - observed)) / sum(abs(observed)). The annual result has 8,760 timezone-naive local-hour labels; each individual interface has 8,760 comparisons. Pooled results contain 61,320 comparisons of seven overlapping interfaces. Primary annual figures retain source interpolation and DST treatment; no quality-filtered selection is substituted.

The NYgrid reference uses corrected released if.map operators, not the erroneous literal plotting-row selection. Comparison figures use the same paper allocation roles for all networks and the same scaled NYgrid native solved generation, net demand, and fixed model-derived AC/DC/HQ NY boundary injections. The Marcy diagnostic adds the paper's two reactances to the compact DC network. It does not establish physical upgrade disposition, AC feasibility, line ratings, or DLR validity.

The compact network uses fixed gamma 0.358662225381536 for every load, generation, boundary injection and observed comparison. WAPE is scale invariant. The selected-flow figure divides scaled compact values by gamma so both panels use actual-scale GW. That display conversion does not turn the compact network into an actual-MW model.

January 8 15:00 is the NYgrid best pooled hour; July 3 04:00 is the compact + Marcy best minimax hour. Both were selected retrospectively from already examined annual data. They are not held-out validation. All seven interfaces at those hours have 12 unique raw samples, no imputation and no ambiguous DST flag.

The current physical-zone operator sensitivity is intentionally not mixed into these three paper-role series. Its annual pooled WAPE worsens from 19.07209610% to 19.67048524% with the same Marcy change; a differently defined interface cut can produce a different comparison.

The two annual figures are deliberately both bar charts: the first reports one model across seven interfaces; the second compares three models within each interface. The monthly series uses all 12 months. The paired-point panels label all seven discrete interfaces and use equal 0–5.2 GW scales, instead of treating seven points as an unlabeled statistical scatter sample.

CSV tables retain precision from source files and contextual fields. Figure and LaTeX table display values are rounded only for legibility. Numeric interface_index/month/panel fields support native pgfplots without parsing labels. All TeX tables are input-ready tabular fragments requiring booktabs. No image-based table is used.
'''
    (DATA/'README.md').write_text(notes,encoding='utf-8')
    csv(pd.DataFrame(dimensions),'figure_dimensions.csv')
    sources=[]
    for path in SOURCE_PATHS:
        sources.append(dict(relative_path=path.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                            hash_policy='raw_bytes',role='frozen_study_output'))
    script=Path(__file__).resolve();sources.append(dict(relative_path=script.relative_to(ROOT).as_posix(),
        sha256=hashlib.sha256(script.read_bytes()).hexdigest(),hash_policy='raw_bytes',role='figure_generation_code'))
    csv(pd.DataFrame(sources),'source_hash_manifest.csv')
    # Preview contact sheet for manual visual QA only; PDF graphics are vector.
    previews=[]
    for item in dimensions:
        image=Image.open(FIG/item['preview']).convert('RGB');image.thumbnail((1100,700))
        tile=Image.new('RGB',(1140,750),'#eef1f5');tile.paste(image,((1140-image.width)//2,30));previews.append(tile)
    sheet=Image.new('RGB',(2280,1500),'white')
    for i,tile in enumerate(previews):sheet.paste(tile,((i%2)*1140,(i//2)*750))
    sheet.save(FIG/'contact_sheet.png')
    result=dict(status='generated_pending_visual_QA',figure_count=4,dimensions=dimensions,
                row_counts={'annual_interfaces':7,'annual_grouped_comparisons':21,'monthly_series_cells':36,'selected_interface_panels':14},
                studies_rerun=False,source_mutations=False,AC_or_thermal_claim=False)
    (DATA/'figure_build_report.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
