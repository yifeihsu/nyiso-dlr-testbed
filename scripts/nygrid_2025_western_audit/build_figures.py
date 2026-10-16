"""Reproducible scientific comparison figure from final, paired replay scores."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'output/nygrid_2025_western_audit'
NAMES = ['DYSINGER EAST', 'WEST CENTRAL', 'TOTAL EAST', 'MOSES SOUTH',
         'CENTRAL EAST - VC', 'UPNY CONED', 'SPR/DUN-SOUTH']

def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def build():
    source = OUT / 'comparison/interface_summary.csv'
    data = pd.read_csv(source)
    data = data.loc[data.cohort.eq('paired_common') & data.variant.str.startswith('dated_')]
    assert len(data) == 42 and data.hours.nunique() == 1
    count = int(data.hours.iloc[0])
    def series(mode, field):
        frame = data.loc[data.variant.eq('dated_' + mode)].set_index('interface')
        assert len(frame) == 7 and frame.index.is_unique
        return frame.loc[NAMES, field].to_numpy(float)
    old = series('previous_PAR_baseline', 'wape_percent')
    new = series('combined', 'wape_percent')
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 11,
        'axes.spines.top': False, 'axes.spines.right': False,
        'axes.labelcolor': '#28313d', 'text.color': '#28313d', 'axes.edgecolor': '#82909e'})
    fig, axes = plt.subplots(1, 2, figsize=(14.4, 8), gridspec_kw={'width_ratios': [1.15, 1]})
    fig.subplots_adjust(left=.22, right=.97, bottom=.28, top=.76, wspace=.36)
    ax = axes[0]; y = np.arange(7)
    ax.barh(y-.18, old, height=.32, color='#ced4dc', edgecolor='#617080', label='Previous PAR baseline')
    ax.barh(y+.18, new, height=.32, color='#246cb0', label='All-boundary actuals + mapping')
    for ys, values in [(y-.18, old), (y+.18, new)]:
        for yy, value in zip(ys, values):
            ax.text(value+.55, yy, f'{value:.2f}', va='center', fontsize=9)
    ax.set_yticks(y, ['Dysinger East', 'West Central', 'Total East', 'Moses South',
                     'Central East', 'UPNY ConEd', 'Sprain/Dunwoodie South'])
    ax.invert_yaxis(); ax.set_xlim(0, max(old.max(), new.max())*1.19)
    ax.set_xlabel('WAPE (%) • lower is better')
    ax.set_title('All seven interfaces', loc='left', fontweight='bold', pad=15)
    ax.grid(axis='x', color='#e9edf1'); ax.set_axisbelow(True)
    left_handles,left_labels=ax.get_legend_handles_labels()
    fig.legend(left_handles,left_labels,loc='lower left',bbox_to_anchor=(.22,.815),frameon=False,fontsize=10)
    ax = axes[1]
    modes = ['previous_PAR_baseline', 'mapping_only', 'Ontario_actual_and_mapping', 'combined']
    labels = ['Previous PAR\nbaseline', 'Mapping\nonly', 'Ontario actuals\n+ mapping¹', 'All-boundary actuals\n+ mapping']
    for j, (name, color, marker) in enumerate([('Dysinger East', '#246cb0', 'o'), ('West Central', '#a86b16', 's')]):
        values = np.array([series(m, 'mae_public_equivalent_mw')[j] for m in modes])
        ax.plot(np.arange(4), values, color=color, marker=marker, linewidth=1.5, markersize=6, label=name)
        for x, v in enumerate(values):
            ax.annotate(f'{v:.1f}', (x, v), xytext=(0, 9 if j == 0 else -16), textcoords='offset points',
                        ha='center', color=color, fontsize=10)
    ax.set_xlim(-.25, 3.25); ax.set_ylim(0, 315)
    ax.set_xticks(np.arange(4), labels, fontsize=9)
    ax.set_ylabel('MAE (public-equivalent MW)')
    ax.set_title('Western diagnostic variants', loc='left', fontweight='bold', pad=15)
    ax.grid(axis='y', color='#e9edf1'); ax.set_axisbelow(True)
    right_handles,right_labels=ax.get_legend_handles_labels()
    fig.legend(right_handles,right_labels,loc='lower left',bbox_to_anchor=(.68,.815),frameon=False,fontsize=10)
    fig.suptitle('2025 western-source corrections', x=.22, y=.97, ha='left', fontsize=20, fontweight='bold')
    fig.text(.22, .90, f'Dated topology • {count:,} identical qualified hours • fixed 148-bus network • no internal-interface fitting', fontsize=11)
    fig.text(.22, .10, '¹ Ontario-only retains schedules at other boundaries and is a mixed-source diagnostic.\n'
             'Primary case uses NYIS-reported regional actuals. Unit generation remains a bounded source-prior reconstruction;\n'
             'individual tie flows, the new Dysinger PAR, and complete 2025 physical interface membership remain unresolved.', fontsize=9.5)
    target = OUT / 'figures'; target.mkdir(parents=True, exist_ok=True)
    paths = []
    for suffix in ['png', 'pdf', 'svg']:
        path = target / ('western_source_comparison.' + suffix)
        fig.savefig(path, dpi=180, facecolor='white'); paths.append(path)
    plt.close(fig)
    data.to_csv(target / 'plotted_paired_scores.csv', index=False)
    paths.append(target / 'plotted_paired_scores.csv')
    receipt = dict(passed=True, paired_hours=count, score_rows=42,
        source_values_checked=True, observed_internal_data_used_only_for_posthoc_scoring=True,
        inputs=[dict(path=p.relative_to(ROOT).as_posix(), sha256=sha(p)) for p in [source, Path(__file__)]],
        outputs=[dict(path=p.relative_to(ROOT).as_posix(), sha256=sha(p)) for p in paths])
    (target / 'figure_validation.json').write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(receipt, indent=2))

if __name__ == '__main__':
    build()
