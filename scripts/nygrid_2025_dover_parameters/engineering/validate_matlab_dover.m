function validate_matlab_dover()
% Independent fresh DC solves of full192 and condensed148 Dover models.
% Fixed-voltage two-port AC algebra is diagnostic, not a system AC validation.
root=fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
folder=fullfile(root,'output','nygrid_2025_dover_parameters');
addpath(fullfile(root,'System Matpower Format'));
fixture_file=fullfile(folder,'replay','matlab_fixtures.mat');
receipt_file=fullfile(folder,'replay','replay_receipt.json');
assert(isfile(fixture_file)&&isfile(receipt_file),'doverAudit:Fixture','Final fixtures are required.');
receipt=jsondecode(fileread(receipt_file));
assert(receipt.passed&&~receipt.internal_interface_observations_read);
assert(strcmp(receipt.preferred_scenario,'bounded_x_nominal'), ...
    'doverAudit:BoundedRequired','Wait for the final bounded-control replay.');
fixture_hash=file_sha256(fixture_file);receipt_hash=file_sha256(receipt_file);
assert(strcmp(fixture_hash,receipt.fixture_file.sha256));
d=load(fixture_file);
states_file=fullfile(folder,'replay','operating_states.mat');states=load(states_file);
assert(strcmp(file_sha256(states_file),receipt.operating_state_file.sha256));
if iscell(d.fixtures),fixtures=[d.fixtures{:}];else,fixtures=d.fixtures;end
names=unique(string({fixtures.scenario}));
families={'x_nominal','x_low','x_high'};
assert(all(ismember("bounded_"+string(families),names))&&all(ismember("neutral_"+string(families),names)));
fixed_hours=sort(double(receipt.fixture_hours(:)'));
for name=names
    hrs=sort(double([fixtures(strcmp({fixtures.scenario},name)).hour_index]));
    assert(isequal(hrs,fixed_hours),'doverAudit:Cohort','Every scenario must use the fixed fixture hours.');
end
assert(numel(fixed_hours)>=5&&numel(unique(fixed_hours))==numel(fixed_hours));
bounded_fixtures=fixtures(strcmp({fixtures.mode},'bounded'));
assert(any([bounded_fixtures.phase_bound_active])&&any([bounded_fixtures.ambiguous_zero_mode]), ...
    'doverAudit:ControlCoverage','Fixtures must cover both saturation and unknown-mode neutral fallback.');
clear npcc_nygrid_2025_dover_dc
options=mpoption('model','DC','verbose',0,'out.all',0);
checks=table();files={fixture_file,receipt_file,states_file,fullfile(folder,'network','network_receipt.json')};
for family=families
    files{end+1}=fullfile(folder,'network',[family{1},'.mat']); %#ok<AGROW>
end
for f=fixtures(:)'
    family=char(f.impedance);mode=char(f.mode);h=double(f.hour_index);
    n=load(fullfile(folder,'network',[family,'.mat']));rec=n.recovery;
    parent=npcc_nygrid_2025_line_estimated_dc(h,'dated','engineering_nominal');
    m=npcc_nygrid_2025_dover_dc(h,mode,family);
    assert(size(m.bus,1)==148&&size(m.branch,1)==274&&size(m.gen,1)==1464&&size(m.dcline,1)==6);
    assert(isequal(m.bus,parent.bus)&&isequal(m.gen,parent.gen)&&isequal(m.dcline,parent.dcline), ...
        'doverAudit:InputMutation','Dover overlay changed frozen operating inputs.');
    assert(isequal(m.genfuel,parent.genfuel)&&isequal(m.bus_name,parent.bus_name));
    assert(m.branch(211,11)==0&&isequal(m.dcline(5:6,1:3),repmat([100 48 1],2,1)));
    assert(max(abs(m.gen(:,2)-f.gen_pg(:)))<1e-7&&max(abs(m.bus(:,3)-f.bus_pd(:)))<1e-7 ...
        &&max(abs(m.bus(:,4)-f.bus_qd(:)))<1e-7&&max(abs(m.dcline(:,4)-f.dc_pf(:)))<1e-7);
    psi=double(f.bank_shift_model_deg(:));
    u=m.userdata.dover;
    assert(u.new_parameters_applied&&~u.pre_cutover_parent_preserved&&~u.factory_impedances_known ...
        &&~u.actual_physical_taps_observed&&~u.hourly_bypass_state_observed&&~u.physical_flowgates_certified&&u.DC_only);
    assert(isequal(u.bank_ptids,[625149;625150])&&all(u.bank_shift_model_deg==psi));
    assert(u.ambiguous_zero_native_mode==logical(f.ambiguous_zero_mode) ...
        &&u.phase_bound_active==logical(f.phase_bound_active));
    assert(u.neutral_fallback==(strcmp(mode,'bounded')&&logical(f.ambiguous_zero_mode)));
    assert(u.exact_tracking_diagnostic_only==strcmp(mode,'exact'));
    assert(max(abs(u.raw_posted_bank_values-states.raw_posted_hourly_values(h,:)'))==0 ...
        &&max(abs(u.target_forward_bank_model_mw+double(d.gamma)*u.raw_posted_bank_values))<1e-10 ...
        &&max(abs(u.simulated_forward_bank_model_mw-f.bank_flow_model_mw(:)))<1e-10);
    assert(all(u.bank_nameplate_mva_is_source_information==750) ...
        &&all(u.necessary_numeric_P_screen_model_mw==750*double(d.gamma)));
    branch_expected=n.slim_case.branch;branch_expected(211,11)=0;
    branch_expected(:,10)=branch_expected(:,10)+rec.slim_shift_phase_basis*psi;
    assert(max(abs(m.branch-branch_expected),[],'all')<1e-9,'doverAudit:PhaseInsertion','Condensed phase shifts differ.');
    if strcmp(mode,'bounded'),assert(max(abs(psi))<=double(d.gamma)*40+1e-10);end
    if strcmp(mode,'neutral'),assert(all(psi==0));end
    [r,ok]=rundcpf(m,options);assert(ok,'doverAudit:SlimSolve','Condensed DC solve failed.');
    interfaces=npcc_nygrid_2025_slim_interfaces(r);
    slim_pf_error=max(abs(r.branch(:,14)-f.branch_pf(:)));
    slim_va_error=max(abs(r.bus(:,9)-f.bus_va(:)));
    interface_error=max(abs(interfaces.model_mw-f.interface_pf(:)));
    pg_error=max(abs(r.gen(:,2)-m.gen(:,2)));
    bound_error=max([0;r.gen(:,10)-r.gen(:,2);r.gen(:,2)-r.gen(:,9)]);
    dc_error=max(abs(r.dcline(:,4)-m.dcline(:,4)));
    % Full assembly uses the source topology directly, not the phase reducer.
    full=m;full.bus=n.full_case.bus;full.branch=n.full_case.branch;
    [found,ix]=ismember(m.bus(:,1),full.bus(:,1));assert(all(found));
    full.bus(:,2)=1;full.bus(:,3:6)=0;full.bus(:,8)=1;full.bus(:,9)=0;
    full.bus(ix,:)=m.bus;
    full.bus_name=n.full_case.bus_name(:);
    full.branch(211,11)=0;full.branch([411 412],10)=psi;
    assert(size(full.bus,1)==192&&size(full.branch,1)==413);
    assert(all(full.bus(~ismember(full.bus(:,1),m.bus(:,1)),3:6)==0,'all'));
    [rf,ok]=rundcpf(full,options);assert(ok,'doverAudit:FullSolve','Full DC solve failed.');
    full_pf_error=max(abs(rf.branch(:,14)-f.full_branch_pf(:)));
    full_va_error=max(abs(rf.bus(:,9)-f.full_bus_va(:)));
    bank_error=max(abs(rf.branch([411 412],14)-f.bank_flow_model_mw(:)));
    full_interface=rec.full_interface_branch_matrix*rf.branch(:,14);
    full_if_error=max(abs(full_interface-interfaces.model_mw));
    theta=deg2rad(r.bus(:,9));phase=deg2rad(psi);
    recovered_va=rad2deg(rec.angle_lift*theta+rec.angle_offset(:)+rec.angle_phase_basis*phase);
    recovered_pf=rec.branch_angle_matrix*theta+rec.branch_flow_offset(:)+rec.branch_flow_phase_basis*phase;
    recovered_pf(211)=0;
    recovered_va_error=max(abs(recovered_va-rf.bus(:,9)));
    recovered_pf_error=max(abs(recovered_pf-rf.branch(:,14)));
    pg_error=max([pg_error;abs(rf.gen(:,2)-m.gen(:,2))]);
    bound_error=max([bound_error;rf.gen(:,10)-rf.gen(:,2);rf.gen(:,2)-rf.gen(:,9)]);
    dc_error=max([dc_error;abs(rf.dcline(:,4)-m.dcline(:,4))]);
    assert(max([slim_pf_error,slim_va_error,interface_error,pg_error,bound_error,dc_error, ...
        full_pf_error,full_va_error,bank_error,full_if_error,recovered_va_error,recovered_pf_error])<1e-7, ...
        'doverAudit:SolveMismatch','MATPOWER and saved Python result differ.');
    checks=[checks;table(string(f.scenario),h,slim_pf_error,slim_va_error,interface_error, ...
        full_pf_error,full_va_error,bank_error,full_if_error,recovered_va_error,recovered_pf_error,pg_error,bound_error,dc_error, ...
        'VariableNames',{'scenario','hour_index','slim_branch_error_model_mw','slim_angle_error_deg', ...
        'saved_interface_error_model_mw','full_branch_error_model_mw','full_angle_error_deg','bank_flow_error_model_mw', ...
        'full_vs_slim_interface_error_model_mw','recovered_full_angle_error_deg','recovered_full_flow_error_model_mw', ...
        'generation_change_model_mw','bound_violation_model_mw','six_transfer_error_model_mw'})]; %#ok<AGROW>
end

% The dated transition must leave all earlier operating cases exactly intact.
precutover_checks=table();
for h=[1,3360,3576,8471]
    assert(states.qualified(h)&&~states.post_full_service(h));
    parent=npcc_nygrid_2025_line_estimated_dc(h,'dated','engineering_nominal');
    for family=families
        for mode={'bounded','neutral'}
            m=npcc_nygrid_2025_dover_dc(h,mode{1},family{1});
            for field={'bus','branch','gen','dcline','genfuel','bus_name'}
                assert(isequal(m.(field{1}),parent.(field{1})),'doverAudit:PreCutover','Pre-cutover parent changed.');
            end
            assert(isequal(m.userdata.slim.interface_angle_matrix,parent.userdata.slim.interface_angle_matrix) ...
                &&isequal(m.userdata.slim.interface_flow_offset,parent.userdata.slim.interface_flow_offset));
            assert(~m.userdata.dover.new_parameters_applied&&m.userdata.dover.pre_cutover_parent_preserved);
            precutover_checks=[precutover_checks;table(h,string(family{1}),string(mode{1}), ...
                string(m.userdata.slim.network_state),true,'VariableNames', ...
                {'hour_index','impedance','mode','network_state','identical_parent_case'})]; %#ok<AGROW>
        end
    end
end
default_case=npcc_nygrid_2025_dover_dc(fixed_hours(1));
explicit_case=npcc_nygrid_2025_dover_dc(fixed_hours(1),'bounded','x_nominal');
assert(isequal(default_case,explicit_case),'doverAudit:DefaultPolicy','Default must be bounded nominal.');
guard_checks=table();
guard_checks=[guard_checks;expect_error('unknown_mode', ...
    @()npcc_nygrid_2025_dover_dc(fixed_hours(1),'unsupported','x_nominal'),{'Dover:Mode'})];
guard_checks=[guard_checks;expect_error('unknown_impedance', ...
    @()npcc_nygrid_2025_dover_dc(fixed_hours(1),'bounded','unsupported'),{'Dover:Impedance'})];
guard_checks=[guard_checks;expect_error('exact_non_nominal_rejected', ...
    @()npcc_nygrid_2025_dover_dc(fixed_hours(1),'exact','x_low'),{'Dover:ExactFamily'})];
for bad_hour=[0,8761,1.5]
    guard_checks=[guard_checks;expect_error(sprintf('invalid_hour_%g',bad_hour), ...
        @()npcc_nygrid_2025_dover_dc(bad_hour),{'Dover:Hour'})]; %#ok<AGROW>
end
missing=find(~logical(states.qualified(:)),1);assert(~isempty(missing));
guard_checks=[guard_checks;expect_error('unqualified_hour', ...
    @()npcc_nygrid_2025_dover_dc(missing),{'Dover:UnqualifiedHour'})];
guard_checks=[guard_checks;expect_error('unsolved_interface_request', ...
    @()npcc_nygrid_2025_slim_interfaces(default_case),{'nygridSlim:UnsolvedCase'})];

% Independent complex-tap, parallel-bank terminal-power check with MATPOWER.
ac_checks=table();
for family=families
    n=load(fullfile(folder,'network',[family{1},'.mat']));
    x=n.full_case.branch(411,4);
    bus=zeros(2,13);bus(:,1)=[1;2];bus(:,2)=[3;1];bus(:,8)=1;bus(:,10)=345;bus(:,12:13)=repmat([1.1 .9],2,1);
    for shift={[0;0],[10;-7]}
        shifts=shift{1};branch=zeros(2,13);branch(:,1:2)=repmat([1 2],2,1);branch(:,4)=x;
        branch(:,9)=1;branch(:,10)=shifts;branch(:,11:13)=repmat([1 -360 360],2,1);
        [Ybus,Yf,Yt]=makeYbus(100,bus,branch);v=[1.02*exp(1i*.07);.99*exp(-1i*.04)];
        sf=100*v(1)*conj(Yf*v);st=100*v(2)*conj(Yt*v);
        a=exp(1i*deg2rad(shifts));iseries=(v(1)./a-v(2))/(1i*x);
        expected_f=100*v(1)*conj(iseries./conj(a));expected_t=100*v(2)*conj(-iseries);
        terminal_error=max(abs([sf-expected_f;st-expected_t]));
        loss_error=max(abs(real(sf+st)));q_error=max(abs(imag(sf+st)-100*x*abs(iseries).^2));
        ybus_error=max(abs(100*v.*conj(Ybus*v)-[sum(sf);sum(st)]));
        assert(max([terminal_error,loss_error,q_error,ybus_error])<1e-8);
        ac_checks=[ac_checks;table(string(family{1}),shifts(1),shifts(2),terminal_error,loss_error,q_error,ybus_error, ...
            'VariableNames',{'impedance','bank_A_shift_deg','bank_B_shift_deg','terminal_power_error_mva', ...
            'real_loss_error_mw','reactive_loss_error_mvar','Ybus_terminal_error_mva'})]; %#ok<AGROW>
    end
end
files=[files,{which('npcc_nygrid_2025_dover_dc'),which('npcc_nygrid_2025_line_estimated_dc'), ...
    which('npcc_nygrid_2025_western_corrected_dc'),which('npcc_nygrid_2025_slim_interfaces'),[mfilename('fullpath'),'.m']}];
assert(strcmp(fixture_hash,file_sha256(fixture_file))&&strcmp(receipt_hash,file_sha256(receipt_file)), ...
    'doverAudit:ConcurrentMutation','Replay changed during validation; rerun against final evidence.');
dependencies=struct('path',{},'sha256',{});
for k=1:numel(files),dependencies(end+1)=struct('path',files{k},'sha256',file_sha256(files{k}));end %#ok<AGROW>
out=fullfile(folder,'validation');if ~isfolder(out),mkdir(out);end
writetable(checks,fullfile(out,'matlab_checks.csv'));writetable(ac_checks,fullfile(out,'matlab_two_bank_phasor_checks.csv'));
writetable(precutover_checks,fullfile(out,'matlab_pre_cutover_checks.csv'));
writetable(guard_checks,fullfile(out,'matlab_guard_checks.csv'));
summary=struct('passed',true,'fresh_slim148_DC_solves',height(checks),'fresh_full192_DC_solves',height(checks), ...
    'scenario_count',numel(names),'fixed_sample_hours',fixed_hours, ...
    'maximum_slim_branch_error_model_mw',max(checks.slim_branch_error_model_mw), ...
    'maximum_full_branch_error_model_mw',max(checks.full_branch_error_model_mw), ...
    'maximum_full_angle_error_deg',max(checks.full_angle_error_deg), ...
    'maximum_bank_flow_error_model_mw',max(checks.bank_flow_error_model_mw), ...
    'maximum_full_vs_slim_interface_error_model_mw',max(checks.full_vs_slim_interface_error_model_mw), ...
    'maximum_recovered_full_flow_error_model_mw',max(checks.recovered_full_flow_error_model_mw), ...
    'maximum_generation_change_model_mw',max(checks.generation_change_model_mw), ...
    'maximum_generation_bound_violation_model_mw',max(checks.bound_violation_model_mw), ...
    'maximum_six_transfer_error_model_mw',max(checks.six_transfer_error_model_mw), ...
    'fixed_complex_voltage_parallel_PST_checks',height(ac_checks), ...
    'maximum_two_bank_terminal_power_error_mva',max(ac_checks.terminal_power_error_mva), ...
    'pre_cutover_exact_parent_identity_checks',height(precutover_checks),'wrapper_guard_checks',height(guard_checks), ...
    'default_bounded_nominal_policy_checked',true,'saturated_and_ambiguous_zero_fixture_coverage',true, ...
    'full_system_AC_or_factory_impedance_or_hardware_taps_certified',false, ...
    'MATLAB_version',version,'MATPOWER_DC_solver',which('rundcpf'),'dependencies',dependencies);
fid=fopen(fullfile(out,'matlab_validation.json'),'w');assert(fid>=0);cleanup=onCleanup(@()fclose(fid));
fprintf(fid,'%s\n',jsonencode(summary,'PrettyPrint',true));disp(summary);
end

function row=expect_error(name,call,identifiers)
rejected=false;identifier="";
try,call();catch err,identifier=string(err.identifier);rejected=any(strcmp(err.identifier,identifiers));end
assert(rejected,'doverAudit:MissingGuard','Expected guard did not reject %s; returned %s.',name,identifier);
row=table(string(name),true,identifier,'VariableNames',{'check','passed','error_identifier'});
end

function digest=file_sha256(path)
engine=java.security.MessageDigest.getInstance('SHA-256');fid=fopen(path,'rb');assert(fid>=0);cleanup=onCleanup(@()fclose(fid));
while ~feof(fid),bytes=fread(fid,1048576,'*uint8');if ~isempty(bytes),engine.update(typecast(bytes,'int8'));end,end
raw=typecast(engine.digest(),'uint8');digest=lower(reshape(dec2hex(raw,2)',1,[]));
end
