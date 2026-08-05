function mpc = npcc_ny_lite_v3_calibrated(varargin) %#ok<INUSD>
%NPCC_NY_LITE_V3_CALIBRATED Guard against accidental use before calibration.
error('npcc_ny_lite_v3_calibrated:NotAvailable', ...
    ['No calibrated NY-lite case exists yet. Use npcc_ny_lite_v3_composed_initial ' ...
     'for screening, populate matched Perform targets, and complete X/R/B/rating calibration first.']);
mpc = struct(); %#ok<UNRCH>
end
