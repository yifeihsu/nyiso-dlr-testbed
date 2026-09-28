"""Rebuild the source-backed static research figure from saved campaign CSVs."""
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

root = Path(__file__).resolve().parent
out = root / 'output' / 'compact_ny_2025'
electrical = out / 'electrical_fixed_peak'
folder = out / 'figures'
folder.mkdir(exist_ok=True)
ledger = pd.read_csv(electrical / 'S1_2025_SUMMER_PEAK_PUBLIC' / 'bus_injection_ledger.csv')
loads = pd.read_csv(electrical / 'source_loads.csv')
loads = loads[loads.scenario_id.eq('S1_2025_SUMMER_PEAK_PUBLIC')].set_index('zone')
zonal = ledger.groupby('zone')[['parent_pd_mw', 'pd_gross_mw']].sum().reindex(list('ABCDEFGHIJK'))
zonal['old_load_share_percent'] = zonal.parent_pd_mw / zonal.parent_pd_mw.sum() * 100
zonal['modeled_load_share_percent'] = zonal.pd_gross_mw / zonal.pd_gross_mw.sum() * 100
zonal['NYISO_scaled_load_mw'] = loads.target_load_mw
zonal['zonal_load_error_mw'] = zonal.pd_gross_mw - zonal.NYISO_scaled_load_mw
assert zonal.zonal_load_error_mw.abs().max() < 1e-6
zonal.to_csv(folder / 'summer_peak_zonal_load_comparison.csv', lineterminator='\n')
cases = pd.read_csv(electrical / 'case_summary.csv')
cases = cases[cases.vintage.eq(2025)].copy()
cases['scenario_number'] = cases.scenario_id.str.extract(r'S(\d+)').astype(int)
cases = cases.sort_values('scenario_number')
trace = pd.read_csv(out / 'thermal' / 'weather_mismatch_transient.csv')
plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10,
                     'axes.spines.top': False, 'axes.spines.right': False,
                     'axes.titleweight': 'bold'})
fig, axs = plt.subplots(1, 3, figsize=(15, 4.7), layout='constrained')
x = np.arange(11)
axs[0].bar(x - .19, zonal.old_load_share_percent, .38, color='#aeb8c4', label='Previous static allocation')
axs[0].bar(x + .19, zonal.modeled_load_share_percent, .38, color='#146d92', label='2025 NYISO-shaped input')
axs[0].set(xticks=x, xticklabels=list('ABCDEFGHIJK'), ylabel='Share of NY gross demand (%)', xlabel='NYISO zone', title='Zonal demand is corrected')
axs[0].legend(frameon=False, fontsize=8, loc='upper left')
colors = ['#146d92'] * 4 + ['#c06b32'] * 2
axs[1].bar(range(6), cases.proxy_max_error_mw, color=colors)
axs[1].set(xticks=range(6), xticklabels=['S1', 'S2', 'S3', 'S4', 'S5*', 'S6*'],
           yscale='log', ylim=(1, 2200), ylabel='Largest interface-proxy error (benchmark MW)',
           title='Calibration differs from prediction', xlabel='* Unused for fitting; frozen dispatch rule')
for x, value in enumerate(cases.proxy_max_error_mw):
    axs[1].text(x, value * 1.18, f'{value:.1f}', ha='center', va='bottom', fontsize=9)
axs[2].plot(trace.time_s / 60, trace.forecast_temperature_c, color='#146d92', label='Forecast: 2 m/s crosswind')
axs[2].plot(trace.time_s / 60, trace.actual_scenario_temperature_c, color='#c06b32', label='Scenario: wind drops at 20 min')
axs[2].axhline(75, color='#555555', ls='--', lw=1, label='Assumed 75°C limit')
axs[2].set(xlabel='Time (minutes)', ylabel='Conductor temperature (°C)', title='Weather errors can cause overheating')
axs[2].legend(frameon=False, fontsize=8, loc='upper left')
fig.suptitle('66-bus NPCC-derived New York research baseline', fontsize=15, fontweight='bold')
fig.supxlabel('Selected 2025 summer benchmark = 10,902 MW. Interface operators and conductor realizations are approximations.\n'
              'Temperature trace uses prescribed current and synthetic weather; it is separate from the steady AC thermal solves.', fontsize=9)
fig.savefig(folder / 'compact_ny_2025_validation.png', dpi=180)
fig.savefig(folder / 'compact_ny_2025_validation.pdf')
print(zonal[['pd_gross_mw', 'modeled_load_share_percent', 'zonal_load_error_mw']].round(4).to_string())
