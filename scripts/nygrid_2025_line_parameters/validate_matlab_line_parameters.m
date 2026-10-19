function validate_matlab_line_parameters()
% Fresh MATPOWER checks for line-parameter scenarios; no full-network AC claim.
root=fileparts(fileparts(fileparts(mfilename('fullpath'))));
folder=fullfile(root,'output','nygrid_2025_line_parameters');
addpath(fullfile(root,'System Matpower Format'));
fixture_file=fullfile(folder,'replay','matlab_fixtures.mat');
assert(isfile(fixture_file),'lineEstimateAudit:Fixtures','Wait for the complete predetermined Python fixtures.');
d=load(fixture_file);
if iscell(d.fixtures),fixtures=[d.fixtures{:}];else,fixtures=d.fixtures;end
assert(numel(fixtures)==35,'lineEstimateAudit:FixtureCount','Expected seven unique predetermined hours for five scenarios.');
scenarios={'identity_reference','engineering_nominal','geometry_spacing_80pct', ...
    'geometry_spacing_120pct','ground_image_30ft'};
assert(isequal(sort(unique(string({fixtures.name}))),sort(string(scenarios))));
clear npcc_nygrid_2025_line_estimated_dc
options=mpoption('model','DC','verbose',0,'out.all',0);
checks=table();fixed_hours=[];
for scenario=scenarios
    ix=strcmp({fixtures.name},scenario{1});hours=sort(double([fixtures(ix).hour_index]));
    assert(numel(hours)==7&&numel(unique(hours))==7);
    if isempty(fixed_hours),fixed_hours=hours;else,assert(isequal(fixed_hours,hours));end
end
for f=fixtures(:)'
    name=char(f.name);h=double(f.hour_index);
    original=npcc_nygrid_2025_western_corrected_dc(h,'dated','combined');
    m=npcc_nygrid_2025_line_estimated_dc(h,'dated',name);
    assert(size(m.bus,1)==148&&size(m.branch,1)==274&&size(m.gen,1)==1464&&size(m.dcline,1)==6);
    assert(m.baseMVA==original.baseMVA&&m.baseMVA==100);
    assert(isequal(m.bus,original.bus)&&isequal(m.gen,original.gen)&&isequal(m.dcline,original.dcline), ...
        'lineEstimateAudit:InputMutation','Only branch parameters and corresponding recovery operators may change.');
    assert(isequal(m.genfuel,original.genfuel)&&isequal(m.bus_name,original.bus_name));
    assert(isequal(m.branch(:,[1 2 11]),original.branch(:,[1 2 11])), ...
        'lineEstimateAudit:TopologyMutation','Parameter scenarios must preserve endpoint/status topology.');
    assert(m.branch(211,11)==0&&isequal(m.dcline(5:6,1:3),repmat([100 48 1],2,1)));
    assert(m.userdata.nygrid2025.scale_factor_gamma==double(d.gamma));
    assert(strcmp(m.userdata.line_estimation.scenario,name));
    assert(~m.userdata.line_estimation.physical_flowgates_certified ...
        &&~m.userdata.line_estimation.AC_equivalent ...
        &&m.userdata.line_estimation.original_generation_bounds_load_and_six_transfers_preserved);
    input_generation=max(abs(m.gen(:,2)-f.gen_pg(:)));
    input_p=max(abs(m.bus(:,3)-f.bus_pd(:)));
    input_q=max(abs(m.bus(:,4)-f.bus_qd(:)));
    assert(max([input_generation,input_p,input_q])<1e-7, ...
        'lineEstimateAudit:FixtureInputs','Loader inputs disagree with frozen Python fixture.');
    assert(max([0;m.gen(:,10)-m.gen(:,2);m.gen(:,2)-m.gen(:,9)])<1e-7);
    identity_error=0;
    if strcmp(name,'identity_reference')
        identity_error=max(abs(m.branch-original.branch),[],'all');
        assert(identity_error<1e-9,'lineEstimateAudit:Identity','Identity overlay differs from the old source-controlled baseline.');
        assert(max(abs(m.userdata.slim.interface_angle_matrix-original.userdata.slim.interface_angle_matrix),[],'all')<1e-8);
        assert(max(abs(m.userdata.slim.interface_flow_offset-original.userdata.slim.interface_flow_offset),[],'all')<1e-8);
    end
    [r,ok]=rundcpf(m,options);
    assert(ok,'lineEstimateAudit:DCSolve','Fresh parameter-scenario DC solve failed.');
    recovered=npcc_nygrid_2025_slim_interfaces(r);
    branch_error=max(abs(r.branch(:,14)-f.branch_pf(:)));
    angle_error=max(abs(r.bus(:,9)-f.bus_va(:)));
    interface_error=max(abs(recovered.model_mw-f.interface_pf(:)));
    generation_error=max(abs(r.gen(:,2)-m.gen(:,2)));
    bound_error=max([0;r.gen(:,10)-r.gen(:,2);r.gen(:,2)-r.gen(:,9)]);
    transfer_error=max(abs(r.dcline(:,4)-original.dcline(:,4)));
    assert(max([branch_error,angle_error,interface_error,generation_error,bound_error,transfer_error])<1e-7, ...
        'lineEstimateAudit:Mismatch','Fresh MATPOWER solve differs from Python or frozen controls.');
    checks=[checks;table(string(name),h,string(m.userdata.slim.network_state),input_generation,input_p,input_q,branch_error,angle_error, ...
        interface_error,generation_error,bound_error,transfer_error,identity_error,'VariableNames', ...
        {'scenario','hour_index','network_state','input_PG_error_model_mw','input_PD_error_model_mw','input_QD_error_model_mvar', ...
        'branch_error_model_mw','angle_error_degree','interface_error_model_mw','generation_change_model_mw', ...
        'bound_violation_model_mw','six_transfer_error_model_mw','identity_branch_parameter_error'})]; %#ok<AGROW>
end
assert(isequal(sort(unique(checks.network_state)),sort(["refined_2025_pre_may_case"; ...
    "refined_2025_may21_case";"refined_2025_may30_case";"refined_2025_case"])), ...
    'lineEstimateAudit:StateCoverage','The predetermined cohort must cover all four dated network states.');

guard_checks=table();
guard_checks=[guard_checks;expect_error('unknown_scenario', ...
    @()npcc_nygrid_2025_line_estimated_dc(fixed_hours(1),'dated','unregistered_scenario'),{'lineEstimate:Scenario'})];
guard_checks=[guard_checks;expect_error('unknown_topology', ...
    @()npcc_nygrid_2025_line_estimated_dc(fixed_hours(1),'unknown','engineering_nominal'),{'westernCorrection:Topology'})];
for bad_hour=[0,8761,1.5]
    guard_checks=[guard_checks;expect_error(sprintf('invalid_hour_%g',bad_hour), ...
        @()npcc_nygrid_2025_line_estimated_dc(bad_hour,'dated','engineering_nominal'),{'nygrid2025:HourIndex'})]; %#ok<AGROW>
end
coverage=load(fullfile(root,'output','nygrid_2025_dispatch','dispatch','dispatch.mat'),'dispatch_qualified','timestamp_utc');
sample_times=datetime(string(coverage.timestamp_utc(fixed_hours)),'InputFormat',"yyyy-MM-dd'T'HH:mm:ss'Z'",'TimeZone','UTC');
sample_times.TimeZone='America/New_York';
assert(all(ismember([1,4,7,10],month(sample_times))), ...
    'lineEstimateAudit:SeasonCoverage','The predetermined cohort must include January, April, July and October.');
missing=find(~logical(coverage.dispatch_qualified(:)),1);
assert(~isempty(missing));
guard_checks=[guard_checks;expect_error('missing_original_source_hour', ...
    @()npcc_nygrid_2025_line_estimated_dc(missing,'dated','engineering_nominal'),{'nygrid2025:UnqualifiedHour'})];
guard_checks=[guard_checks;expect_error('unsolved_interface_request', ...
    @()npcc_nygrid_2025_slim_interfaces(npcc_nygrid_2025_line_estimated_dc(fixed_hours(1),'dated','engineering_nominal')), ...
    {'nygridSlim:UnsolvedCase'})];

% Fixed-complex-voltage two-bus diagnostic: MATPOWER itself forms Ybus/Yf/Yt.
% No runpf on the 148-bus DC-equivalent network is performed or implied.
estimates_file=fullfile(folder,'estimates','parameter_estimates.csv');
estimates=readtable(estimates_file,'TextType','string');
one=estimates(estimates.scenario_name=="engineering_nominal"&estimates.full191_branch_key=="CV:PV_CV_F84",:);
assert(height(one)==1);
bus=zeros(2,13);bus(:,1)=[1;2];bus(:,2)=[3;1];bus(:,8)=1;bus(:,10)=345;bus(:,12:13)=repmat([1.1 .9],2,1);
line=zeros(1,13);line(1:5)=[1 2 one.r_pu one.x_pu one.b_pu];line(11:13)=[1 -360 360];
[Ybus,Yf,Yt]=makeYbus(100,bus,line);
vtests={[1;1],[1.03*exp(1i*.06);.99*exp(-1i*.03)]};ac_checks=table();
for k=1:numel(vtests)
    v=vtests{k};sf=100*v(1)*conj(Yf*v);st=100*v(2)*conj(Yt*v);
    terminal=100*v.*conj(Ybus*v);
    iseries=(v(1)-v(2))/complex(one.r_pu,one.x_pu);
    expected_loss=100*one.r_pu*abs(iseries)^2;
    expected_q_loss=100*one.x_pu*abs(iseries)^2 ...
        -100*one.b_pu/2*(abs(v(1))^2+abs(v(2))^2);
    ploss_error=abs(real(sf+st)-expected_loss);
    qbalance_error=abs(imag(sf+st)-expected_q_loss);
    ybus_terminal_error=max(abs([sf;st]-terminal));
    assert(max([ploss_error,qbalance_error,ybus_terminal_error])<1e-9);
    charging_error=0;
    if k==1
        charging_error=max(abs([imag(sf),imag(st)]+one.b_pu*100/2));
        assert(charging_error<1e-10&&abs(real(sf)+real(st))<1e-12);
    end
    ac_checks=[ac_checks;table(k,real(sf),imag(sf),real(st),imag(st),ploss_error, ...
        qbalance_error,ybus_terminal_error,charging_error,'VariableNames', ...
        {'fixed_voltage_case','PF_mw','QF_mvar','PT_mw','QT_mvar','real_loss_error_mw', ...
         'reactive_balance_error_mvar','Ybus_terminal_error_mva','B_half_shunt_error_mvar'})]; %#ok<AGROW>
end

out=fullfile(folder,'validation');if ~isfolder(out),mkdir(out);end
writetable(checks,fullfile(out,'matlab_checks.csv'));
writetable(guard_checks,fullfile(out,'matlab_guard_checks.csv'));
writetable(ac_checks,fullfile(out,'matlab_two_bus_pi_checks.csv'));
files={fixture_file,estimates_file,fullfile(folder,'estimates','engineering_basis.json'), ...
    which('npcc_nygrid_2025_line_estimated_dc'),which('npcc_nygrid_2025_western_corrected_dc'), ...
    which('npcc_nygrid_2025_par_controlled_dc'),which('npcc_nygrid_2025_moses_corrected_dc'), ...
    which('npcc_nygrid_2025_slim_dc'),which('npcc_nygrid_2025_full_dc'), ...
    which('npcc_nygrid_2025_slim_interfaces'),[mfilename('fullpath'),'.m']};
for scenario=scenarios
    files{end+1}=fullfile(folder,'overlays',scenario{1},'network_cases.mat'); %#ok<AGROW>
    files{end+1}=fullfile(folder,'overlays',scenario{1},'overlay_receipt.json'); %#ok<AGROW>
end
receipt_file=fullfile(folder,'replay','replay_receipt.json');
if isfile(receipt_file),files{end+1}=receipt_file;end
dependencies=struct('path',{},'sha256',{});
for k=1:numel(files)
    dependencies(end+1)=struct('path',files{k},'sha256',file_sha256(files{k})); %#ok<AGROW>
end
summary=struct('passed',true,'fresh_MATPOWER_DC_snapshots',height(checks),'scenarios',5, ...
    'predetermined_state_and_season_hours',fixed_hours,'observations_selected_hours',false, ...
    'maximum_branch_error_model_mw',max(checks.branch_error_model_mw), ...
    'maximum_angle_error_degree',max(checks.angle_error_degree), ...
    'maximum_interface_error_model_mw',max(checks.interface_error_model_mw), ...
    'maximum_generation_change_model_mw',max(checks.generation_change_model_mw), ...
    'maximum_bound_violation_model_mw',max(checks.bound_violation_model_mw), ...
    'maximum_six_transfer_error_model_mw',max(checks.six_transfer_error_model_mw), ...
    'wrapper_guard_checks_passed',height(guard_checks),'fixed_voltage_two_bus_AC_pi_checks',height(ac_checks), ...
    'maximum_two_bus_loss_error_mw',max(ac_checks.real_loss_error_mw), ...
    'maximum_two_bus_charging_half_error_mvar',max(ac_checks.B_half_shunt_error_mvar), ...
    'full148_bus_AC_validated',false,'facility_thermal_feasibility_validated',false, ...
    'MATLAB_version',version,'MATPOWER_DC_solver',which('rundcpf'), ...
    'MATPOWER_Ybus_builder',which('makeYbus'),'dependencies',dependencies);
fid=fopen(fullfile(out,'matlab_validation.json'),'w');assert(fid>=0);cleanup=onCleanup(@()fclose(fid));
fprintf(fid,'%s\n',jsonencode(summary,'PrettyPrint',true));disp(summary);
end

function row=expect_error(name,call,identifiers)
rejected=false;identifier="";
try,call();catch err,identifier=string(err.identifier);rejected=any(strcmp(err.identifier,identifiers));end
assert(rejected,'lineEstimateAudit:MissingGuard','Expected guard did not reject %s; returned %s.',name,identifier);
row=table(string(name),true,identifier,'VariableNames',{'check','passed','error_identifier'});
end

function digest=file_sha256(path)
engine=java.security.MessageDigest.getInstance('SHA-256');fid=fopen(path,'rb');assert(fid>=0);cleanup=onCleanup(@()fclose(fid));
while ~feof(fid),bytes=fread(fid,1048576,'*uint8');if ~isempty(bytes),engine.update(typecast(bytes,'int8'));end,end
raw=typecast(engine.digest(),'uint8');digest=lower(reshape(dec2hex(raw,2)',1,[]));
end
