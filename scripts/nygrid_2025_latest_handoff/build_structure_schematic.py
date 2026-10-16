"""Print-sized current-model schematic; no geographic or historical content."""
from pathlib import Path
import hashlib
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/nygrid_2025_latest_handoff/structure'


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    plt.rcParams.update({'font.family':'DejaVu Sans','svg.fonttype':'none'})
    fig=plt.figure(figsize=(6.8,2.2),dpi=300,facecolor='white')
    ax=fig.add_axes([0,0,1,1]);ax.set_xlim(0,6.8);ax.set_ylim(0,2.2);ax.axis('off')
    ink='#20242A';blue='#245A81';edge='#8C969E';fill='#F3F5F7'
    labels=[('Detailed AC network','266 / 267 buses\n485 / 488 branch rows'),
            ('Passive elimination','118 / 119 interior\nvoltages'),
            ('Retained AC solve','148 bus voltages\ncoupled loss equations'),
            ('Exact recovery','Detailed voltages\nand branch currents'),
            ('Conductor screen','179 / 180 parents\nsteady heat balance')]
    x=[.12+1.34*j for j in range(5)];y=.95;w=1.18;h=.78
    for j,(title,body) in enumerate(labels):
        ax.add_patch(FancyBboxPatch((x[j],y),w,h,boxstyle='round,pad=0.025,rounding_size=0.045',
            linewidth=.75,edgecolor=blue if j==2 else edge,facecolor='#EAF1F6' if j==2 else fill))
        ax.text(x[j]+w/2,y+h-.16,title,ha='center',va='center',fontsize=7.35,fontweight='bold',color=ink)
        ax.text(x[j]+w/2,y+.28,body,ha='center',va='center',fontsize=7.45,color=ink,linespacing=1.28)
        if j<4:
            ax.add_patch(FancyArrowPatch((x[j]+w+.035,y+h/2),(x[j+1]-.035,y+h/2),arrowstyle='-|>',
                mutation_scale=8,linewidth=.9,color=blue))
    ax.text(3.4,2.02,'100 MVA  ·  60 Hz  ·  amperes at the model electrical base',ha='center',va='center',fontsize=8.2,color=blue)
    inputs=[(3.39,2.25,'Hourly power inputs and controls\nVoltage-dependent loss injections'),
            (6.07,1.28,'Conductor eligibility\n+ explicit weather')]
    for center,width,text in inputs:
        low=.18;height=.44
        ax.add_patch(FancyBboxPatch((center-width/2,low),width,height,boxstyle='round,pad=0.02,rounding_size=0.035',
            linewidth=.6,edgecolor=edge,facecolor='white'))
        ax.text(center,low+height/2,text,ha='center',va='center',fontsize=7.35,color=ink,linespacing=1.2)
        ax.add_patch(FancyArrowPatch((center,low+height+.035),(center,y-.045),arrowstyle='-|>',
            mutation_scale=8,linewidth=.8,color=blue))
    png=OUT/'current_model_schematic.png';svg=OUT/'current_model_schematic.svg'
    fig.savefig(png,dpi=300,facecolor='white');fig.savefig(svg,facecolor='white');plt.close(fig)
    result=dict(passed=True,width_inches=6.8,height_inches=2.2,png_pixels=[2040,660],
        scope='Nongeographic current-model representation and recovery/thermal data flow',
        sources=['current_structure_inventory.json'],
        files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [png,svg]})
    (OUT/'schematic_receipt.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
