"""Small numerical helpers for the declared Moses residual diagnostics."""
import numpy as np
import pandas as pd


def metrics(prediction, observation):
    prediction = np.asarray(prediction, float); observation = np.asarray(observation, float)
    assert prediction.shape == observation.shape and np.isfinite(prediction).all() and np.isfinite(observation).all()
    error = prediction - observation; absolute = abs(error); n = len(error)
    if not n:
        return {'hours': 0}
    denominator = float(abs(observation).sum())
    return {'hours': n, 'MAE_public_MW': float(absolute.mean()),
        'RMSE_public_MW': float(np.sqrt(np.mean(error ** 2))), 'bias_public_MW': float(error.mean()),
        'WAPE_percent': float(100 * absolute.sum() / denominator) if denominator > 0 else None,
        'observed_mean_public_MW': float(observation.mean()), 'observed_mean_absolute_public_MW': float(abs(observation).mean()),
        'prediction_mean_public_MW': float(prediction.mean()), 'positive_error_fraction': float(np.mean(error > 0)),
        'absolute_error_p95_public_MW': float(np.quantile(absolute, .95)),
        'absolute_error_max_public_MW': float(absolute.max()),
        **{f'error_q{int(p * 100):02d}_public_MW': float(np.quantile(error, p)) for p in [.01, .05, .25, .5, .75, .95, .99]}}


def distribution(values):
    values = np.asarray(values, float); assert np.isfinite(values).all()
    return {'hours': len(values), 'mean_public_MW': float(values.mean()), 'mean_absolute_public_MW': float(abs(values).mean()),
        'minimum_public_MW': float(values.min()), 'maximum_public_MW': float(values.max()),
        **{f'q{int(p * 100):02d}_public_MW': float(np.quantile(values, p)) for p in [.01, .05, .25, .5, .75, .95, .99]}}


def pearson(a, b):
    a = np.asarray(a, float); b = np.asarray(b, float)
    assert len(a) == len(b) and np.isfinite(a).all() and np.isfinite(b).all()
    if len(a) < 3 or np.ptp(a) == 0 or np.ptp(b) == 0:
        return None
    return float(np.corrcoef(a, b)[0, 1])


def spearman(a, b):
    return pearson(pd.Series(a).rank(method='average').to_numpy(), pd.Series(b).rank(method='average').to_numpy())


def demean(values, groups):
    frame = pd.DataFrame({'value': values, 'group': groups})
    return (frame.value - frame.groupby('group').value.transform('mean')).to_numpy()


def shifted(values, lag):
    """At evaluation position t return original value at t+lag; never wrap."""
    values = np.asarray(values, float); out = np.full(values.shape, np.nan)
    if lag == 0: return values.copy()
    if lag > 0: out[:-lag] = values[lag:]
    else: out[-lag:] = values[:lag]
    return out


def lag_availability(available, states, lag):
    available = np.asarray(available, bool); states = np.asarray(states)
    result = np.zeros(len(available), bool)
    if lag == 0: return available.copy()
    if lag > 0:
        result[:-lag] = available[lag:] & (states[:-lag] == states[lag:])
    else:
        result[-lag:] = available[:lag] & (states[-lag:] == states[:lag])
    return result


def strict_triplet(qualified, states, *series):
    qualified = np.asarray(qualified, bool)
    result = qualified.copy()
    for lag in [-1, 0, 1]:
        result &= lag_availability(qualified, states, lag)
        for values in series: result &= np.isfinite(shifted(values, lag))
    return result


def contiguous_pairs(qualified, states):
    return np.asarray(qualified, bool) & lag_availability(qualified, states, -1)


def grouped_metrics(prediction, observation, eligible, groups, group_kind):
    rows = []
    for name in sorted(set(np.asarray(groups)[eligible])):
        selected = eligible & (np.asarray(groups) == name)
        rows.append({'group_kind': group_kind, 'group_value': str(name), **metrics(prediction[selected], observation[selected])})
    return rows


def finite_json(value):
    if isinstance(value, dict): return {str(k): finite_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)): return [finite_json(v) for v in value]
    if isinstance(value, np.ndarray): return finite_json(value.tolist())
    if isinstance(value, np.generic): return finite_json(value.item())
    if isinstance(value, float) and not np.isfinite(value): return None
    return value
