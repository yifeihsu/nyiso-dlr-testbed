# 2019 released model versus current 2025 model: error metrics

Calculated October 18, 2026 (America/New_York) from saved hourly predictions.
No power-flow simulation, model correction, deck change or map change was made.
The current-model pointer still identifies moses_repair_v1.

## Comparison populations

- 2019: the authors' released 57-bus DC case, original supplied 2019 inputs,
  8,760 prepared local-hour observations and the pinned authors' interface map.
- 2025: the current modified AC case, 8,651 source-qualified physical hours,
  using the frozen legacy_signed_literal_from diagnostic convention.
- All interface power values are public-scale MW. The current prediction
  arrays already contain the model-to-public conversion; it is not applied again.

The comparison uses different years, inputs, physics, selected hours and
observation preparation. It does not isolate the effect of topology changes.
Physical meter equivalence across years remains unverified. These are
recomputed released-model scores, not values quoted from the paper's
limit-normalized error figure.

## Files and definitions

- per_interface_metrics.csv: 14 annual interface/year rows.
- comparison.csv: seven interfaces with both years and their differences.
- monthly_metrics.csv: 168 month/interface/year rows.
- aggregate_metrics.csv: four rows separating equal-interface means and pooled
  interface-hour metrics.
- calculation_receipt.json: exact definitions, source identities and hashes.
- independent_review.json: separate recomputation from the hourly source arrays.

Error is predicted minus observed. Bias is its signed mean; MAE averages its
absolute value; RMSE is the square root of its mean square. Error SD uses the
population convention. Median and P95 errors summarize absolute hourly errors.
P95 is an error-tail description, not a confidence interval.

WAPE is 100 times the sum of absolute errors divided by the sum of absolute
observed flows. nRMSE uses mean absolute observed flow as its denominator.
Normalized bias uses the same denominator and is not hourly MPE.

MAPE is provided both for all exactly nonzero observations and for observations
whose absolute flow is at least 100 MW. The latter is a fixed diagnostic
threshold with exported coverage; the two years need not retain the same share
of observations. sMAPE uses the mean of 200 times absolute error divided by
the sum of absolute predicted and observed flow; both-zero terms count as zero.

Columns ending in delta_*_pp are percentage-point changes. Columns named
relative_change_*_percent are percentage changes relative to the 2019 value.

## Averaging

macro_equal_interface averages each metric across the seven interfaces.
For median/P95, this means the average of seven individual quantiles.

pooled_interface_hours recomputes each metric on all interface-hour
observations. Pooled RMSE, WAPE and quantiles differ from the arithmetic mean
of interface metrics. In that row, the generic hours column returned by the
metric function counts interface-hour observations; hours_per_interface gives
the actual clock-position count. interface_hour_observations states the
expanded sample count explicitly.

The interfaces overlap electrically. These aggregates are descriptive
benchmark statistics and must not be interpreted as statewide energy errors.
Signed bias can cancel across hours and interfaces; the mean absolute
interface bias is therefore also exported.

## Reproduction

From the repository root:

~~~powershell
python scripts/nygrid_2019_2025_error_metrics/compare_metrics.py
~~~

This verifies the current pointer, source receipts and hashes before reading
the saved data. It reconstructs 2019 interface predictions directly from branch
flows and the authors' pinned interface map. Sources are fingerprinted again
after calculation.

The optional prepare_inline.py script projects reviewed results for the
installed Data chart and source-receipt renderers. The inline response files
live in the chat's visualization directory and are not standalone website
deliverables.
