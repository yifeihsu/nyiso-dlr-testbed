function scenarios = nyiso_public_default_scenarios()
%NYISO_PUBLIC_DEFAULT_SCENARIOS Seed public NYISO calibration timestamps.
%   These timestamps were selected from 2019 public NYISO data so that the
%   public load/interface targets are contemporaneous with the 2019 PERFORM
%   network snapshot. Selection criteria mirror the earlier 2025 set.

scenario_id = { ...
    'S1_2019_SUMMER_PEAK_PUBLIC'
    'S2_2019_WINTER_PEAK_PUBLIC'
    'S3_2019_SHOULDER_LIGHT_LOAD_PUBLIC'
    'S4_2019_HIGH_NYC_LI_LOAD_PUBLIC'
    'S5_2019_HIGH_TOTAL_EAST_PUBLIC'
    'S6_2019_LOW_TOTAL_EAST_PUBLIC'};
timestamp = { ...
    '2019-07-20 16:00'
    '2019-01-21 18:00'
    '2019-04-21 04:00'
    '2019-07-17 16:00'
    '2019-07-17 08:00'
    '2019-07-27 02:00'};
notes = { ...
    'summer max total load from July 2019 P-58C (30396.9 MW)'
    'winter max total load from January 2019 P-58C (24727.6 MW)'
    'shoulder minimum total load from April 2019 P-58C (11951.1 MW)'
    'summer max NYC plus Long Island load from July 2019 P-58C (15816.5 MW)'
    'maximum on-the-hour Total East flow from July 2019 P-32 (5781.1 MW)'
    'minimum on-the-hour Total East flow from July 2019 P-32 (2206.4 MW)'};

scenarios = table(scenario_id, timestamp, notes);
end
