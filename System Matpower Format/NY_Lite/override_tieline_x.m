function candidates = override_tieline_x(candidates, candidate_name, x_value)
%OVERRIDE_TIELINE_X Return candidates with one BR_X value replaced.

idx = find(strcmp({candidates.name}, candidate_name), 1);
if isempty(idx)
    error('override_tieline_x:UnknownCandidate', ...
        'No tie-line candidate named %s exists.', candidate_name);
end
if ~isscalar(x_value) || ~isfinite(x_value) || x_value <= 0
    error('override_tieline_x:BadReactance', ...
        'Reactance override must be a positive finite scalar.');
end
candidates(idx).br_x_initial = x_value;
end
