"""Standalone scientific diagnostic figures; no generation reconstruction."""
from pathlib import Path
import json
import hashlib
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'output/nygrid_2025_moses_source_diagnosis'


def main():
    data = pd.read_csv(OUT / 'balance_hourly.csv')
    data = data.loc[data.qualified].copy()
    assert len(data) == 8651
    hour = data.groupby('hour_local').agg(
        StLawrence_PG_MW=('StLawrence_PG_MW', 'mean'),
        residual_MW=('residual_primary_MW', 'mean'),
        hours=('hour_index', 'size'))
    hour.to_csv(OUT / 'daily_shape_figure_data.csv')
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 11,
                         'axes.spines.top': False, 'axes.spines.right': False,
                         'axes.titleweight': 'bold', 'figure.facecolor': 'white'})
    fig, axes = plt.subplots(2, 1, figsize=(10, 7), sharex=True,
                            gridspec_kw={'height_ratios': [1, 1]})
    axes[0].plot(hour.index, hour.StLawrence_PG_MW, color='#185ca8', lw=2.5, marker='o', ms=4)
    axes[0].axhline(802.5, ls='--', color='#727a86', lw=1.2)
    axes[0].text(0.3, 811, 'Current imposed upper bound: 802.5 MW', color='#59616e', fontsize=10)
    axes[0].set(ylabel='St. Lawrence generation (MW)', ylim=(480, 845),
                title='The modeled St. Lawrence profile has a strong daily shape')
    axes[1].axhline(0, color='#727a86', lw=1)
    axes[1].plot(hour.index, hour.residual_MW, color='#c65c22', lw=2.5, marker='o', ms=4)
    axes[1].fill_between(hour.index, 0, hour.residual_MW, color='#c65c22', alpha=.12)
    axes[1].set(ylabel='Mean Moses residual (MW)', xlabel='Local hour (America/New_York)',
                title='Moses residual changes sign between night and day', ylim=(-160, 125),
                xlim=(-.3, 23.3), xticks=np.arange(0, 24, 2))
    for h, xytext in [(3, (5, -145)), (17, (16, 105))]:
        axes[1].annotate(f'{h:02d}:00  {hour.loc[h, "residual_MW"]:+.1f} MW',
                         xy=(h, hour.loc[h, 'residual_MW']), xytext=xytext,
                         fontsize=10, ha='center', arrowprops={'arrowstyle': '-', 'color': '#686f79'})
    for ax in axes:
        ax.grid(axis='y', alpha=.17)
        ax.set_axisbelow(True)
    fig.text(.09, .015,
             '2025 qualified cohort: 8,651 hours. Residual = model minus observation; public-scale MW.\n'
             'Daily means show association, not causal attribution or measured plant output.',
             fontsize=9, color='#4c5562')
    fig.tight_layout(rect=(0, .07, 1, 1))
    fig.savefig(OUT / 'daily_shape_diagnosis.png', dpi=170)
    fig.savefig(OUT / 'daily_shape_diagnosis.pdf')
    plt.close(fig)
    r = {'status': 'rendered', 'qualified_hours': len(data),
         'input_sha256': hashlib.sha256((OUT / 'balance_hourly.csv').read_bytes()).hexdigest(),
         'plot_scope': 'Descriptive daily means, no fitted coefficients or causal attribution.',
         'hour3_mean_residual_MW': hour.loc[3, 'residual_MW'],
         'hour17_mean_residual_MW': hour.loc[17, 'residual_MW']}
    (OUT / 'figure_receipt.json').write_text(json.dumps(r, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
