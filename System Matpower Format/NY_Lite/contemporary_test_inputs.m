function out = contemporary_test_inputs()
%CONTEMPORARY_TEST_INPUTS Actual archive import and adversarial accounting tests.
h = fileparts(mfilename('fullpath'));
files = fullfile(h,'contemporary_source_data', ...
    ["20260801palIntegrated.csv";"20260815palIntegrated.csv";"20260825palIntegrated.csv"]);
all_inputs = contemporary_import_nyiso_loads(files);
assert(height(all_inputs) == 792 && numel(unique(all_inputs.scenario_id)) == 72);
assert(all(all_inputs.power_scale == "actual_mw"));
c = research_model_contract;
assert(validate_research_inputs(all_inputs,c).pass);
inputs = all_inputs(all_inputs.scenario_id == all_inputs.scenario_id(1),:);
assert(abs(sum(inputs.value)-18600.504) < 1e-6, 'Raw August 1 midnight EDT sum changed.');
assert(all(inputs.timestamp_utc == "2026-08-01T04:00:00Z"));

mpc = struct('version','2','baseMVA',100,'bus',zeros(12,13), ...
    'branch',zeros(1,13),'gen',zeros(1,21));
mpc.bus(:,1) = (1001:1012)'; mpc.bus(:,3) = 10; mpc.bus(:,4) = 2;
allocation = table((1001:1011)',string(('A':'K')'),ones(11,1),0.2*ones(11,1), ...
    repmat("test:explicit_allocation_and_qp_assumption",11,1), ...
    'VariableNames',{'bus_id','zone','weight','q_over_p','source_uri'});
[loaded, report] = contemporary_apply_loads(mpc,inputs,allocation,c);
assert(abs(sum(loaded.bus(1:11,3))-sum(inputs.value)) < 1e-8);
assert(max(abs(loaded.bus(1:11,4)-0.2*inputs.value)) < 1e-10);
assert(isequal(loaded.branch,mpc.branch) && isequal(loaded.gen,mpc.gen));
assert(isequal(loaded.bus(12,:),mpc.bus(12,:)) && report.normalization_factor == 1);
later = all_inputs(all_inputs.scenario_id == all_inputs.scenario_id(12),:);
[next,~] = contemporary_apply_loads(mpc,later,allocation,c);
assert(abs(sum(next.bus(1:11,3))-sum(loaded.bus(1:11,3))) > 1, ...
    'Actual-MW time variation was suppressed.');
reordered = allocation(end:-1:1,:);
assert(isequal(contemporary_apply_loads(mpc,inputs,reordered,c).bus,loaded.bus));

tests = 6;
bad = inputs; bad.power_scale(:) = "historical_similarity_scaled"; reject(bad,c,"scale:"); tests=tests+1;
bad = inputs; bad.entity_id(2) = bad.entity_id(1); reject(bad,c,"accounting:"); tests=tests+1;
bad = [inputs;inputs(1,:)]; bad.scenario_id(end) = "alias";
bad.accounting_id(end) = "alias"; reject(bad,c,"accounting:"); tests=tests+1;
bad = inputs; bad.timestamp_utc(:) = "2019-08-01T04:00:00Z"; reject(bad,c,"vintage:"); tests=tests+1;
bad = inputs; bad.timestamp_utc(:) = "2026-09-07T04:00:00Z"; reject(bad,c,"vintage:"); tests=tests+1;
bad = inputs; bad.timestamp_utc(1) = "2026-08-01T05:00:00Z"; reject(bad,c,"scenario:"); tests=tests+1;
bad = inputs; bad.value(1) = NaN; reject(bad,c,"value:"); tests=tests+1;
bad = inputs; bad.value(1) = -1; reject(bad,c,"load:"); tests=tests+1;
bad = inputs; bad.unit(1) = "kW"; reject(bad,c,"unit:"); tests=tests+1;
bad = inputs; bad.provenance_class(1) = "synthetic_fixture"; reject(bad,c,"provenance:"); tests=tests+1;
bad = inputs; bad.source_sha256(1) = "unknown"; reject(bad,c,"provenance:"); tests=tests+1;
bad = inputs; bad.target_use(1) = "calibration_target"; bad.dataset_split(1) = "held_out";
reject(bad,c,"evidence:"); tests=tests+1;
bad = inputs; bad.provenance_class(1) = "declared_assumption"; bad.target_use(1) = "validation_target";
reject(bad,c,"evidence:"); tests=tests+1;
bad = inputs(1:10,:); reject(bad,c,"load:"); tests=tests+1;
bad_allocation = allocation; bad_allocation.weight(1) = 0.9;
must_error(@() contemporary_apply_loads(mpc,inputs,bad_allocation,c), 'contemporary_apply_loads:Weights'); tests=tests+1;
bad_allocation = allocation; bad_allocation.bus_id(2) = bad_allocation.bus_id(1);
must_error(@() contemporary_apply_loads(mpc,inputs,bad_allocation,c), 'contemporary_apply_loads:Allocation'); tests=tests+1;
g = contemporary_generator_inventory(mpc,"fixture");
rr = contemporary_validate_registers([],g);
assert(rr.pass && ~rr.release_ready && ~isempty(rr.release_blockers)); tests=tests+1;
g.release_eligible(:)=true;
rr = contemporary_validate_registers([],g);
assert(~rr.pass && any(rr.errors == "unverified_generator_marked_eligible")); tests=tests+1;
a = readtable(fullfile(h,'contemporary_asset_register.csv'),'TextType','string');
bad_assets = a; bad_assets.status_known_by(1) = "2026-09-07";
rr = contemporary_validate_registers(bad_assets);
assert(~rr.pass && any(rr.errors == "asset_status_date_after_cutoff")); tests=tests+1;
bad_assets = a; bad_assets.implemented(:) = "true";
rr = contemporary_validate_registers(bad_assets);
assert(~rr.pass && any(rr.errors == "future_or_unverified_asset_implemented")); tests=tests+1;
bad_assets = a; bad_assets.overhead_dlr_eligible(:) = "true";
rr = contemporary_validate_registers(bad_assets);
assert(~rr.pass && any(rr.errors == "nonoverhead_asset_marked_overhead_dlr_eligible")); tests=tests+1;
bad_assets = [a;a(1,:)]; rr = contemporary_validate_registers(bad_assets);
assert(~rr.pass && any(rr.errors == "duplicate_asset_id")); tests=tests+1;
out = struct('pass',true,'checks',tests,'public_load_points',72, ...
    'public_load_rows',792,'release_ready',false);
fprintf('Contemporary input tests: %d checks passed; 72 real public load points.\n',tests);
end

function reject(inputs, contract, expected)
r = validate_research_inputs(inputs,contract,struct('fail_on_error',false));
assert(~r.pass && any(contains(r.errors,expected)), 'Expected validator rejection: %s',expected);
end

function must_error(fn, id)
try
    fn();
catch ME
    assert(strcmp(ME.identifier,id),'Unexpected error: %s',ME.message); return;
end
error('contemporary_test_inputs:MissingError','Expected %s',id);
end
