function mpc = npcc_nygrid_2025_dover_dc(hour_index, mode, impedance_family)
%NPCC_NYGRID_2025_DOVER_DC Applied Dover line/PAR engineering reconstruction.
% Default bounded mode tracks qualified external posted P34 bank-flow targets
% within a declared gamma-scaled40deg model limit. Both-native-zero hours use
% an explicit neutral/normal-topology assumption, not zero intertie flow.
% Actual taps, factory impedances, breaker states and physical thermal/AC
% feasibility remain unverified. 'exact' is an unbounded diagnostic only.
if nargin<1, hour_index=1; end
if nargin<2 || isempty(mode), mode='bounded'; end
if nargin<3 || isempty(impedance_family), impedance_family='x_nominal'; end
assert(isnumeric(hour_index)&&isscalar(hour_index)&&isfinite(hour_index) ...
    &&hour_index==floor(hour_index)&&hour_index>=1&&hour_index<=8760, ...
    'Dover:Hour','Use a valid integer2025 physical-hour index.');
assert(any(strcmp(mode,{'neutral','bounded','exact'})), 'Dover:Mode','Choose bounded, neutral, or diagnostic exact.');
assert(any(strcmp(impedance_family,{'x_low','x_nominal','x_high'})), ...
    'Dover:Impedance','Unknown conditional impedance family.');
assert(~strcmp(mode,'exact')||strcmp(impedance_family,'x_nominal'), ...
    'Dover:ExactFamily','Exact tracking is a nominal-impedance diagnostic only.');
root=fileparts(fileparts(mfilename('fullpath')));
folder=fullfile(root,'output','nygrid_2025_dover_parameters');
statesfile=fullfile(folder,'replay','operating_states.mat');
replayproof=fullfile(folder,'replay','replay_receipt.json');
assert(isfile(statesfile)&&isfile(replayproof),'Dover:MissingStates','Build and validate the Dover replay first.');
persistent states states_signature cached_family n network_signature
si=dir(statesfile);pi=dir(replayproof);signature=[si.bytes si.datenum pi.bytes pi.datenum];
if isempty(states)||~isequal(states_signature,signature)
    proof=jsondecode(fileread(replayproof));
    assert(proof.passed&&~proof.internal_interface_observations_read ...
        &&strcmp(file_sha256(statesfile),proof.operating_state_file.sha256), ...
        'Dover:StateProof','Dover operating states differ from the validated receipt.');
    states=load(statesfile);states_signature=signature;
    assert(isequal(states.hour_index(:),(1:8760)')&&strcmp(states.cutover_utc,'2025-12-20T04:00:00Z'), ...
        'Dover:StateAxes','Unexpected hour axis or full-service boundary.');
end
assert(logical(states.qualified(hour_index)),'Dover:UnqualifiedHour','Hour is outside the validated fixed comparison cohort.');
mpc=npcc_nygrid_2025_line_estimated_dc(hour_index,'dated','engineering_nominal');
assert(states.gamma==mpc.userdata.nygrid2025.scale_factor_gamma,'Dover:Scale','Power scaling changed.');
mpc.userdata.dover=struct('mode',char(mode),'impedance_family',char(impedance_family), ...
    'full_service_cutover_utc',states.cutover_utc,'new_parameters_applied',false, ...
    'pre_cutover_parent_preserved',true,'first_partial_energization_date_not_inferred',true, ...
    'factory_impedances_known',false,'actual_physical_taps_observed',false, ...
    'hourly_bypass_state_observed',false,'P34_numeric_as_MW_convention_verified',false, ...
    'original_six_transfers_preserved',true,'physical_flowgates_certified',false,'DC_only',true);
if ~logical(states.post_full_service(hour_index)),return;end
networkfile=fullfile(folder,'network',[char(impedance_family),'.mat']);
networkproof=fullfile(folder,'network','network_receipt.json');
assert(isfile(networkfile)&&isfile(networkproof),'Dover:MissingNetwork','Missing Dover network artifact.');
ni=dir(networkfile);pi=dir(networkproof);signature=[ni.bytes ni.datenum pi.bytes pi.datenum];
if isempty(n)||~strcmp(cached_family,impedance_family)||~isequal(network_signature,signature)
    proof=jsondecode(fileread(networkproof));
    match=find(strcmp({proof.scenarios.scenario},impedance_family));
    assert(proof.passed&&isscalar(match)&&strcmp(file_sha256(networkfile),proof.scenarios(match).sha256), ...
        'Dover:NetworkProof','Dover network differs from the validated receipt.');
    n=load(networkfile);cached_family=char(impedance_family);network_signature=signature;
    assert(strcmp(n.metadata.valid_from_utc,states.cutover_utc),'Dover:EffectiveDate','Network effective date differs.');
end
if strcmp(mode,'exact'),key=['exact_tracking_',char(impedance_family)];else,key=[char(mode),'_',char(impedance_family)];end
control=states.controls.(key);phase=control.bank_shift_model_deg(hour_index,:)';
assert(numel(phase)==2&&all(isfinite(phase)), 'Dover:MissingPhase','Missing validated bank phase state.');
if strcmp(mode,'bounded')
    assert(all(abs(phase)<=40*states.gamma+1e-8),'Dover:PhaseRange','Bounded model-angle assumption exceeded.');
    if logical(control.neutral_fallback(hour_index))
        assert(all(phase==0),'Dover:ZeroMode','Ambiguous zero channels must not force zero intertie flow.');
    end
end
c=n.slim_case;rec=n.recovery;
assert(size(c.bus,1)==148&&size(c.branch,1)==274&&isequal(c.bus(:,1),mpc.bus(:,1)) ...
    &&isequal(c.branch(:,1:2),mpc.branch(:,1:2)), 'Dover:Axes','Original retained identities changed.');
assert(size(mpc.dcline,1)==6&&mpc.branch(211,11)==0&&c.branch(211,11)==1, ...
    'Dover:TransferIdentity','Original PAR/DC substitution contract changed.');
mpc.branch=c.branch;mpc.branch(211,11)=0;
mpc.branch(:,10)=mpc.branch(:,10)+rec.slim_shift_phase_basis*phase;
mpc.userdata.slim.interface_angle_matrix=rec.interface_angle_matrix;
mpc.userdata.slim.interface_flow_offset=rec.interface_flow_offset(:)+rec.interface_phase_basis*deg2rad(phase);
mpc.userdata.line_estimation.Dover_PAR_impedance_unresolved_line_only_estimates_not_applied=false;
mpc.userdata.line_estimation.Dover_conditional_line_and_PAR_parameters_applied=true;
mpc.userdata.dover.new_parameters_applied=true;
mpc.userdata.dover.pre_cutover_parent_preserved=false;
mpc.userdata.dover.conditional_impedance_not_factory_test=true;
mpc.userdata.dover.bank_ptids=[625149;625150];
mpc.userdata.dover.bank_shift_model_deg=phase;
mpc.userdata.dover.uniform_power_unscaled_angle_proxy_deg=phase/states.gamma;
mpc.userdata.dover.unscaled_angle_proxy_is_not_tap_telemetry=true;
mpc.userdata.dover.normal_bypass_open_assumed=true;
mpc.userdata.dover.ambiguous_zero_native_mode=logical(control.ambiguous_zero_native_mode(hour_index));
mpc.userdata.dover.neutral_fallback=logical(control.neutral_fallback(hour_index));
mpc.userdata.dover.phase_bound_active=logical(control.phase_bound_active(hour_index));
mpc.userdata.dover.raw_posted_bank_values=states.raw_posted_hourly_values(hour_index,:)';
mpc.userdata.dover.target_forward_bank_model_mw=states.forward_NY_to_CT_model_mw(hour_index,:)';
mpc.userdata.dover.simulated_forward_bank_model_mw=control.bank_flow_model_mw(hour_index,:)';
mpc.userdata.dover.bank_nameplate_mva_is_source_information=[750;750];
mpc.userdata.dover.necessary_numeric_P_screen_model_mw=[750;750]*states.gamma;
mpc.userdata.dover.actual_Q_cooling_and_terminal_limits_unverified=true;
mpc.userdata.dover.exact_tracking_diagnostic_only=strcmp(mode,'exact');
end

function digest=file_sha256(path)
engine=java.security.MessageDigest.getInstance('SHA-256');fid=fopen(path,'rb');assert(fid>=0);cleanup=onCleanup(@()fclose(fid));
while ~feof(fid),bytes=fread(fid,1048576,'*uint8');if ~isempty(bytes),engine.update(typecast(bytes,'int8'));end,end
raw=typecast(engine.digest(),'uint8');digest=lower(reshape(dec2hex(raw,2)',1,[]));
end
