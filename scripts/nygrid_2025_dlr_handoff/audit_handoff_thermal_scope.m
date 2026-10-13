function report=audit_handoff_thermal_scope()
% Independent cached-point screen/eligibility audit; no new PF or OPF solve.
root=fileparts(fileparts(fileparts(mfilename('fullpath'))));
addpath(fullfile(root,'scripts','nygrid_2025_dlr_handoff','runtime'));
addpath(fullfile(root,'scripts','nygrid_2025_ac_system','thermal'));
addpath(fullfile(root,'scripts','nygrid_2025_ac_system','ac_validation'));
addpath(fullfile(root,'scripts','nygrid_2025_ac_loss_revision','core'));
addpath(fullfile(root,'System Matpower Format','NY_Lite'));
out=fullfile(root,'output','nygrid_2025_dlr_handoff','independent_thermal_scope');if ~isfolder(out),mkdir(out);end
paths={fullfile(root,'scripts','nygrid_2025_dlr_handoff','runtime','nygrid_handoff_thermal_candidates.m'), ...
       fullfile(root,'scripts','nygrid_2025_dlr_handoff','runtime','screen_nygrid_2025_loss_pf_thermal.m')};
before_hashes=cellfun(@file_sha256,paths,'UniformOutput',false);
weather=table(25,.6096,90,1000,101325,'VariableNames', ...
    {'ambient_c','wind_m_s','wind_angle_deg','solar_w_m2','pressure_pa'});
checks=struct([]);outputs=struct([]);inputs=struct([]);
for h=[4000 8508]
    file=fullfile(root,'output','nygrid_2025_ac_loss_revision','validation','representative_factorial',sprintf('h%04d_cell4.mat',h));
    d=load(file,'r','audit','allocation');inputs=[inputs record(root,file)]; %#ok<AGROW>
    cached=struct('full',d.r,'audit',d.audit,'allocation',d.allocation);before=cached;
    s=screen_nygrid_2025_loss_pf_thermal(cached,weather);
    assert(isequaln(cached,before),'handoffReview:Mutation','Screen mutated its caller inputs.');
    assert(s.screening_completed&&s.numerical_identities_passed);
    assert(~s.installed_asset_DLR_qualification&&~s.whole_system_operating_qualification ...
        &&~s.OPF_run&&~s.electrical_solution_changed&&~s.current_gamma_rescaling_applied ...
        &&~s.resistance_temperature_feedback_run&&~s.conductor_temperature_equilibrium_solved);
    assert(~s.inherited_VQ_operating_qualification&&s.inherited_electrical_audit.loss_allocation_gate);
    ledger=s.candidate_and_exclusion_ledger;segments=s.candidate_segments;
    allowed=ledger.research_screen_eligible;excluded=[224 300 309 310 386];
    assert(~any(ismember(ledger.original_parent_row(allowed),excluded)));
    assert(all(ledger.active(allowed)&ledger.same_voltage(allowed)&ledger.unity_tap(allowed)&ledger.zero_phase(allowed) ...
        &ledger.source_keyed_or_documented_design(allowed)&ledger.catalog_reference_R_matches(allowed)));
    assert(all(~ledger.installed_asset_DLR_verified));
    % Independently calculate current and heating from the solved phasors.
    r=d.r;V=r.bus(:,8).*exp(1i*pi/180*r.bus(:,9));rows=segments.branch_row;
    [ok,f]=ismember(r.branch(rows,1),r.bus(:,1));assert(all(ok));[ok,t]=ismember(r.branch(rows,2),r.bus(:,1));assert(all(ok));
    assert(all(abs(r.bus(f,10)-segments.base_kv)<1e-9)&all(abs(r.bus(t,10)-segments.base_kv)<1e-9));
    Ipu=(V(f)-V(t))./complex(r.branch(rows,3),r.branch(rows,4));
    phase=abs(Ipu)*r.baseMVA*1000./(sqrt(3)*r.bus(f,10));sub=phase./segments.circuits./segments.bundle_count;
    assert(max(abs(phase-s.segment_screen.series_phase_current_a))<1e-8);
    assert(max(abs(sub-s.segment_screen.subconductor_current_a))<1e-8);
    T=segments.reference_temperature_c;res=zeros(height(segments),1);
    below=T<=75;
    res(below)=segments.r_ac25_ohm_per_m(below)+(segments.r_ac75_ohm_per_m(below)-segments.r_ac25_ohm_per_m(below)).*(T(below)-25)/50;
    res(~below)=segments.r_ac75_ohm_per_m(~below)+(segments.r_ac200_ohm_per_m(~below)-segments.r_ac75_ohm_per_m(~below)).*(T(~below)-75)/125;
    heat=3*segments.circuits.*segments.bundle_count.*sub.^2.*res.*segments.segment_length_m/1e6;
    err=max(abs(heat-s.segment_screen.joule_loss_mw));assert(err<1e-8);
    branch_rows=s.branch_screen.branch_row;[okf,fi]=ismember(r.branch(branch_rows,1),r.bus(:,1));[okt,ti]=ismember(r.branch(branch_rows,2),r.bus(:,1));assert(all(okf&okt));
    saved_f=hypot(r.branch(branch_rows,14),r.branch(branch_rows,15))*1000./(sqrt(3)*r.bus(fi,10).*abs(V(fi)));
    saved_t=hypot(r.branch(branch_rows,16),r.branch(branch_rows,17))*1000./(sqrt(3)*r.bus(ti,10).*abs(V(ti)));
    terminal_error=max(abs([saved_f-s.branch_screen.from_terminal_current_A;saved_t-s.branch_screen.to_terminal_current_A]));assert(terminal_error<1e-6);
    assert(s.maximum_Joule_loss_identity_error_MW<1e-7&&s.maximum_heat_residual_at_ampacity_W_per_m<1e-8);
    % Failure paths that materially protect use of the result.
    no_weather=false;try,screen_nygrid_2025_loss_pf_thermal(cached,[]);catch e,no_weather=strcmp(e.identifier,'handoff:ExplicitWeather');end
    bad=cached;bad.audit.loss_allocation_gate=false;unqualified=false;
    try,screen_nygrid_2025_loss_pf_thermal(bad,weather);catch e,unqualified=strcmp(e.identifier,'handoff:UnqualifiedPF');end
    keyed=repmat(weather,height(segments),1);keyed.branch_key=segments.branch_key;keyed.segment_id=segments.segment_id;
    keyed.branch_key([1 2])=keyed.branch_key([2 1]);bad_order=false;
    try,screen_nygrid_2025_loss_pf_thermal(cached,keyed);catch e,bad_order=strcmp(e.identifier,'handoff:WeatherOrder');end
    assert(no_weather&&unqualified&&bad_order);
    ledger_file=fullfile(out,sprintf('candidate_ledger_h%04d.csv',h));writetable(ledger,ledger_file);
    segment_file=fullfile(out,sprintf('independent_segment_currents_h%04d.csv',h));
    independent=table(rows,segments.branch_key,segments.segment_id,phase,sub,heat, ...
        'VariableNames',{'runtime_branch_row','branch_key','segment_id','phase_current_A','subconductor_current_A','joule_MW'});
    writetable(independent,segment_file);outputs=[outputs record(root,ledger_file) record(root,segment_file)]; %#ok<AGROW>
    c=struct('hour_index',h,'candidate_parents',s.candidate_parent_count,'candidate_runtime_rows',s.candidate_runtime_branch_count, ...
        'candidate_segments',s.candidate_segment_count,'excluded_parents',s.excluded_parent_count, ...
        'maximum_series_utilization',s.maximum_series_ampacity_utilization,'maximum_section_end_utilization',s.maximum_section_end_ampacity_utilization, ...
        'all_candidate_conductor_envelopes_satisfied',s.all_candidate_current_envelopes_satisfied,'inherited_operating_qualified',false, ...
        'maximum_independent_Joule_value_error_MW',err,'maximum_independent_terminal_current_error_A',terminal_error, ...
        'input_preservation_and_explicit_weather_qualification_key_guards_passed',true,'passed',true);
    checks=[checks c]; %#ok<AGROW>
    fprintf('HANDOFF_THERMAL_REVIEW h%d parents%d rows%d segments%d series%.5g ends%.5g passed\n',h,c.candidate_parents,c.candidate_runtime_rows,c.candidate_segments,c.maximum_series_utilization,c.maximum_section_end_utilization);
end
after_hashes=cellfun(@file_sha256,paths,'UniformOutput',false);assert(isequal(before_hashes,after_hashes));
paths=[paths,{[mfilename('fullpath'),'.m'], ...
    fullfile(root,'output','nygrid_2025_ac_system','branches','branch_assignments.csv'), ...
    fullfile(root,'output','nygrid_2025_ac_system','engineering','thermal_conductors.csv'), ...
    fullfile(root,'scripts','nygrid_2025_ac_system','thermal','ac_dlr_current_audit.m'), ...
    fullfile(root,'scripts','nygrid_2025_ac_system','thermal','ac_dlr_limits.m')}];
dependencies=inputs;for k=1:numel(paths),dependencies(end+1)=record(root,paths{k});end %#ok<AGROW>
report=struct('passed',true,'scope','Independent read-only cached-point thermal eligibility/current/heating review; no electrical solve', ...
    'all_source_and_operating_qualifications_preserved',true,'source_helper_hashes_stable',true, ...
    'fresh_PF_or_OPF_run',false,'physical_asset_DLR_or_feasible_operating_case_claimed',false, ...
    'checks',checks,'dependencies',dependencies,'outputs',outputs);
fid=fopen(fullfile(out,'independent_thermal_scope_review.json'),'w');assert(fid>=0);fprintf(fid,'%s\n',jsonencode(report,'PrettyPrint',true));fclose(fid);
end

function r=record(root,path)
r=struct('path',strrep(strrep(char(path),[root filesep],''),'\','/'),'sha256',file_sha256(path));
end
function digest=file_sha256(path)
engine=java.security.MessageDigest.getInstance('SHA-256');fid=fopen(path,'rb');assert(fid>=0);cleanup=onCleanup(@()fclose(fid));
while ~feof(fid),bytes=fread(fid,1048576,'*uint8');if ~isempty(bytes),engine.update(typecast(bytes,'int8'));end,end
raw=typecast(engine.digest(),'uint8');digest=lower(reshape(dec2hex(raw,2)',1,[]));
end
