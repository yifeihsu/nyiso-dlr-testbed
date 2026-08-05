function [csv_file, source_name] = nyiso_public_monthly_csv(feed, timestamp, options)
%NYISO_PUBLIC_MONTHLY_CSV Download/extract a NYISO monthly CSV archive.

if nargin < 3, options = struct(); end
helper_dir = fileparts(mfilename('fullpath'));
if ~isfield(options, 'cache_dir') || isempty(options.cache_dir)
    options.cache_dir = fullfile(helper_dir, 'nyiso_public_cache');
end
if ~exist(options.cache_dir, 'dir'), mkdir(options.cache_dir); end

timestamp = nyiso_public_timestamp(timestamp);
month_token = datestr(timestamp, 'yyyymm');
day_token = datestr(timestamp, 'yyyymmdd');

switch lower(feed)
    case {'p58c','palintegrated'}
        subdir = 'palIntegrated';
        suffix = 'palIntegrated';
    case {'p32','externallimitsflows'}
        subdir = 'ExternalLimitsFlows';
        suffix = 'ExternalLimitsFlows';
    otherwise
        error('nyiso_public_monthly_csv:BadFeed', 'Unknown NYISO feed %s.', feed);
end

archive_dir = fullfile(options.cache_dir, [month_token '_' suffix]);
if ~exist(archive_dir, 'dir'), mkdir(archive_dir); end

csv_file = fullfile(archive_dir, [day_token suffix '.csv']);
source_name = [month_token '01' suffix '_csv.zip'];
if exist(csv_file, 'file') == 2
    return;
end

zip_file = fullfile(archive_dir, source_name);
if exist(zip_file, 'file') ~= 2
    url = sprintf('https://mis.nyiso.com/public/csv/%s/%s', subdir, source_name);
    websave(zip_file, url);
end
unzip(zip_file, archive_dir);
if exist(csv_file, 'file') ~= 2
    error('nyiso_public_monthly_csv:CsvMissing', ...
        'Expected daily CSV was not found after extracting %s.', zip_file);
end
end
