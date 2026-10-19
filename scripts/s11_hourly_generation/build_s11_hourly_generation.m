function summary = build_s11_hourly_generation(options)
%BUILD_S11_HOURLY_GENERATION Model dispatch on the existing hourly S11 loads.
%   Public schedules and all load timestamps are inputs. This does not infer
%   historical plant dispatch. Separate months are independent snapshots.
if nargin < 1, options = struct(); end
root = fileparts(fileparts(fileparts(mfilename('fullpath'))));
addpath(fullfile(root,'System Matpower Format'), ...
    fullfile(root,'System Matpower Format','NY_Lite'));
output_dir = fullfile(root,'output','s11_hourly_generation');
if ~isfield(options,'worker_count'), options.worker_count = 4; end
if ~isfield(options,'chunk_size'), options.chunk_size = 256; end
if ~isfield(options,'indices'), options.indices = []; end
if ~isfield(options,'retry_failed'), options.retry_failed = false; end
if ~isfield(options,'output_dir'), options.output_dir = output_dir; end
output_dir = options.output_dir;
if ~isfolder(output_dir), mkdir(output_dir); end
saved = load(fullfile(root,'output','s11_hourly_load_profiles', ...
    's11_hourly_load_profiles.mat'),'profile');
loads = saved.profile;
base = npcc_ny_lite_s11_dlr_pf_base;
nb = size(base.bus,1); ng = size(base.gen,1); nt = numel(loads.timestamp_utc);
assert(nb == 49 && ng == 49 && nt == 4416);
assert(isequal(base.bus(:,1),loads.bus_id));
boundary_file = fullfile(root,'output','s11_hourly_generation', ...
    'interchange_boundary_applied_mw.csv');
io = detectImportOptions(boundary_file,'TextType','string');
io = setvartype(io,1:3,'string');
boundary = readtable(boundary_file,io);
time_fields = {'timestamp_utc','timestamp_local','source_time_zone'};
for k = 1:3
    assert(isequal(string(boundary.(time_fields{k})),string(loads.(time_fields{k}))), ...
        'Interchange and load timestamps differ.');
end
mapping = readtable(fullfile(root,'output','s11_hourly_generation', ...
    'interchange_mapping.csv'),'TextType','string');
ext = find(strcmp(base.genfuel,'external_schedule'));
assert(isequal(ext,(42:49)'));
boundary_names = {'HQ_NY_MOSES','NE_NY_NORTHFIELD','NE_NY_PV', ...
    'OH_NY_NIAGARA','PJM_NY_WATERCURE','PJM_NY_WRHL', ...
    'PJM_NY_RAMAPO','PJM_NY_GOETHALS'};
assert(height(mapping) == 8, 'Expected eight S11 external equivalents.');
assert(isequal(string(mapping.external_interface_name),string(boundary_names(:))) && ...
    isequal(mapping.bus_id,base.gen(ext,1)), 'Boundary identity/order mismatch.');
external_pg = boundary{:,boundary_names}';
assert(all(isfinite(external_pg),'all'), 'Applied interchange must be complete.');
strict = read_bool(boundary.all_primary_coverage_qualified);
imputed = read_bool(boundary.schedule_imputed);
assert(all(xor(strict,imputed)), 'Every hour needs an explicit schedule source class.');
physical = readtable(fullfile(root,'System Matpower Format','NY_Lite', ...
    's11_physical_circuit_map.csv'),'TextType','string');
trusted = false(size(base.branch,1),1);
trusted(physical.branch_index(physical.branch_classification == "physical_circuit")) = true;
assert(nnz(trusted) == 5);
solver_options = struct('trusted_branch_mask',trusted);

indices = options.indices;
if isempty(indices), indices = 1:nt; end
indices = unique(indices(:)');
assert(all(indices >= 1 & indices <= nt & indices == fix(indices)));
operating = struct('bus_id',base.bus(:,1),'gen_bus_id',base.gen(:,1), ...
    'gen_id',{cellstr(compose("S11_G%03d_BUS%d_%s",(1:ng)',base.gen(:,1),string(base.genfuel)))}, ...
    'genfuel',{base.genfuel},'gentype',{base.gentype},'base_gen',base.gen, ...
    'base_bus',base.bus,'base_branch',base.branch, ...
    'external_gen_indices',ext,'trusted_branch_indices',find(trusted), ...
    'timestamp_utc',{loads.timestamp_utc},'timestamp_local',{loads.timestamp_local}, ...
    'source_time_zone',{loads.source_time_zone}, ...
    'pg_mw',nan(ng,nt),'qg_mvar',nan(ng,nt),'vg_pu',nan(ng,nt), ...
    'gen_status',nan(ng,nt),'bus_vm_pu',nan(nb,nt), ...
    'bus_va_deg',nan(nb,nt),'bus_type',nan(nb,nt), ...
    'external_pg_mw',external_pg,'valid',false(nt,1), ...
    'source_coverage_qualified',strict,'schedule_imputed',imputed, ...
    'dispatch_is_observed',false,'chronological_ramps_enforced',false, ...
    'source_fleet_policy','saved_S11_aggregate_capabilities_for_both_vintages', ...
    'array_orientation','generator_or_bus_by_hour');
diagnostics = cell(nt,1);
previous_elapsed = 0;
if options.retry_failed
    prior = load(fullfile(output_dir,'s11_hourly_operating_profiles.mat'), ...
        'operating','diagnostics');
    assert(isequaln(prior.operating.base_gen,base.gen) && ...
        isequaln(prior.operating.base_bus,base.bus) && ...
        isequaln(prior.operating.base_branch,base.branch) && ...
        isequaln(prior.operating.external_pg_mw,external_pg) && ...
        isequaln(prior.operating.timestamp_utc,loads.timestamp_utc), ...
        'Cannot retry against changed network, fleet, schedules, or timestamps.');
    operating = prior.operating; diagnostics = prior.diagnostics;
    indices = find(~operating.valid)';
    previous_diagnostics = diagnostics; previous_valid = operating.valid; %#ok<NASGU>
    save(fullfile(output_dir,'retry_before.mat'),'previous_diagnostics','previous_valid','-v7');
    prior_summary = jsondecode(fileread(fullfile(output_dir,'generation_summary.json')));
    previous_elapsed = prior_summary.elapsed_seconds;
    copyfile(fullfile(output_dir,'generation_summary.json'), ...
        fullfile(output_dir,'initial_generation_summary.json'));
    copyfile(fullfile(output_dir,'hourly_validation.csv'), ...
        fullfile(output_dir,'initial_hourly_validation.csv'));
end
if options.worker_count > 1 && license('test','Distrib_Computing_Toolbox')
    pool = gcp('nocreate');
    if isempty(pool), pool = parpool('Processes',options.worker_count); end
    worker_count = min(pool.NumWorkers,options.worker_count);
else
    worker_count = 0;
end
fprintf('S11 hourly generation: %d requested hours, %d workers.\n',numel(indices),worker_count);
campaign_clock = tic;
for start = 1:options.chunk_size:numel(indices)
    hours = indices(start:min(start+options.chunk_size-1,numel(indices)));
    answers = cell(numel(hours),1); notes = cell(numel(hours),1);
    if worker_count > 0
        parfor (k = 1:numel(hours), worker_count)
            h = hours(k);
            [answers{k},notes{k}] = solve_s11_dispatch_hour(base, ...
                loads.pd_mw(:,h),loads.qd_mvar(:,h),external_pg(:,h),solver_options);
        end
    else
        for k = 1:numel(hours)
            h = hours(k);
            [answers{k},notes{k}] = solve_s11_dispatch_hour(base, ...
                loads.pd_mw(:,h),loads.qd_mvar(:,h),external_pg(:,h),solver_options);
        end
    end
    for k = 1:numel(hours)
        h = hours(k); diagnostics{h} = notes{k};
        if ~notes{k}.success, continue; end
        r = answers{k};
        operating.pg_mw(:,h) = r.gen(:,2);
        operating.qg_mvar(:,h) = r.gen(:,3);
        operating.vg_pu(:,h) = r.gen(:,6);
        operating.gen_status(:,h) = r.gen(:,8);
        operating.bus_vm_pu(:,h) = r.bus(:,8);
        operating.bus_va_deg(:,h) = r.bus(:,9);
        operating.bus_type(:,h) = r.bus(:,2);
        operating.valid(h) = true;
    end
    fprintf('Completed %d/%d; valid %d; elapsed %.1fs.\n', ...
        min(start+options.chunk_size-1,numel(indices)),numel(indices), ...
        nnz(operating.valid),toc(campaign_clock));
    save(fullfile(output_dir,'s11_hourly_operating_profiles.mat'), ...
        'operating','diagnostics','-v7');
end
completed = find(~cellfun(@isempty,diagnostics))';
summary = export_outputs(output_dir,base,loads,operating,diagnostics,completed);
summary.this_run_hours = numel(indices);
summary.retry_failed_only = logical(options.retry_failed);
summary.elapsed_seconds = previous_elapsed + toc(campaign_clock);
summary.worker_count = worker_count;
write_json(fullfile(output_dir,'generation_summary.json'),summary);
disp(jsonencode(summary,PrettyPrint=true));
end

function result = read_bool(input)
if islogical(input) || isnumeric(input), result = logical(input); return; end
assert(all(ismember(lower(string(input)),["true","false","1","0"])));
result = ismember(lower(string(input)),["true","1"]);
end

function summary = export_outputs(folder,base,loads,o,notes,requested)
n = numel(o.timestamp_utc); ng = size(base.gen,1);
time = table(string(o.timestamp_utc),string(o.timestamp_local), ...
    string(o.source_time_zone),o.valid,o.source_coverage_qualified,o.schedule_imputed, ...
    'VariableNames',{'timestamp_utc','timestamp_local','source_time_zone', ...
    'generation_valid','interchange_source_qualified','interchange_gap_completed'});
names = cellstr(compose('gen_%03d',1:ng));
for pair = { {'pg_mw','gen_pg_mw.csv'}, {'qg_mvar','gen_qg_mvar.csv'}, ...
        {'vg_pu','gen_vg_pu.csv'}, {'gen_status','gen_status.csv'} }
    item = pair{1};
    writetable([time,array2table(o.(item{1})','VariableNames',names)],fullfile(folder,item{2}));
end
role = repmat("reactive_control",ng,1);
role(base.gen(:,9)>0 & ~strcmp(base.genfuel,'external_schedule')) = "internal_active_aggregate";
role(strcmp(base.genfuel,'reference_boundary_equivalent')) = "zero_P_reference_Q_provenance";
role(o.external_gen_indices) = "external_schedule";
gen_map = table((1:ng)',string(o.gen_id),o.gen_bus_id,string(o.genfuel), ...
    string(o.gentype),role,base.gen(:,10),base.gen(:,9),base.gen(:,5),base.gen(:,4), ...
    'VariableNames',{'original_gen_row','gen_id','bus_id','genfuel','gentype','role', ...
    'online_pmin_mw','online_pmax_mw','online_qmin_mvar','online_qmax_mvar'});
writetable(gen_map,fullfile(folder,'generator_mapping.csv'));
state = repmat("not_run",n,1); reason = strings(n,1); off_rows = strings(n,1);
runtime = nan(n,1); attempts = nan(n,1);
metric_names = {'maximum_p_violation_mw','maximum_q_violation_mvar', ...
    'maximum_voltage_violation_pu','maximum_trusted_branch_violation_mva', ...
    'maximum_ac_mismatch_mva','maximum_external_error_mw', ...
    'maximum_legacy_branch_loading_ratio','ac_branch_loss_mw','shunt_active_demand_mw'};
metrics = nan(n,numel(metric_names));
standard_pf = false(n,1); q_pf = false(n,1);
for h = requested
    d = notes{h};
    state(h) = string(d.status);
    reason(h) = string(d.reason);
    if isfield(d,'offline_rows'), off_rows(h) = strjoin(string(d.offline_rows),';'); end
    if isfield(d,'solve_seconds'), runtime(h) = d.solve_seconds; end
    if isfield(d,'attempt_count'), attempts(h) = d.attempt_count; end
    for k = 1:numel(metric_names)
        if isfield(d,metric_names{k}), metrics(h,k) = d.(metric_names{k}); end
    end
    standard_pf(h) = d.standard_pf_success;
    q_pf(h) = d.q_limit_pf_success;
end
internal = setdiff((1:ng)',o.external_gen_indices);
internal_pg = sum(o.pg_mw(internal,:),1)';
external_pg = sum(o.external_pg_mw,1)';
pd = sum(loads.pd_mw,1)';
net_network = internal_pg + external_pg - pd;
ledger = [time,table(state,reason,off_rows,runtime,attempts,pd,internal_pg,external_pg,net_network, ...
    'VariableNames',{'status','reason','offline_gen_rows','solve_seconds','attempts', ...
    'load_mw','internal_generation_mw','scheduled_net_import_mw', ...
    'network_loss_and_shunt_consumption_mw'})];
ledger = [ledger,table(standard_pf,q_pf, ...
    'VariableNames',{'standard_pf_success','q_limit_pf_success'}), ...
    array2table(metrics,'VariableNames',metric_names)];
writetable(ledger,fullfile(folder,'hourly_validation.csv'));
summary = struct('requested_hours',numel(requested),'total_aligned_hours',n, ...
    'valid_hours',nnz(o.valid),'invalid_requested_hours',sum(~o.valid(requested)), ...
    'not_run_hours',n-numel(requested),'generator_table_rows',ng, ...
    'internal_active_aggregates',sum(role=="internal_active_aggregate"), ...
    'external_equivalents',numel(o.external_gen_indices), ...
    'source_qualified_interchange_hours',nnz(o.source_coverage_qualified), ...
    'gap_completed_interchange_hours',nnz(o.schedule_imputed), ...
    'dispatch_is_observed',false,'chronological_ramps_enforced',false, ...
    'all_hours_ac_valid',all(o.valid),'minimum_internal_generation_mw',min(internal_pg(o.valid)), ...
    'maximum_internal_generation_mw',max(internal_pg(o.valid)), ...
    'hours_with_modeled_aggregate_shutdown',sum(any(o.gen_status(internal,:)==0,1)));
summary.invalid_hour_indices = requested(~o.valid(requested));
summary.maximum_valid_hour_ac_mismatch_mva = max(metrics(o.valid,5));
summary.maximum_valid_hour_p_violation_mw = max(metrics(o.valid,1));
summary.maximum_valid_hour_q_violation_mvar = max(metrics(o.valid,2));
summary.maximum_valid_hour_voltage_violation_pu = max(metrics(o.valid,3));
summary.maximum_valid_hour_trusted_branch_violation_mva = max(metrics(o.valid,4));
end

function write_json(filename,value)
fid = fopen(filename,'w'); assert(fid>=0);
cleanup = onCleanup(@() fclose(fid));
fprintf(fid,'%s\n',jsonencode(value,PrettyPrint=true));
end
