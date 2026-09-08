function out=replay_compact_partial_spc_dlr(folder)
%REPLAY_COMPACT_PARTIAL_SPC_DLR Independent frozen-dispatch AC and heat checks.
% Reconstructs the electrical source chain and all realizations. Never calls
% an optimizer, changes generator bounds, or treats saved passed flags as proof.
root=fileparts(mfilename('fullpath'));addpath(fullfile(root,'System Matpower Format','NY_Lite'));
if nargin<1,folder=fullfile(root,'output','compact_ny_2025','partial_spc_thermal');end
mf=readtable(fullfile(folder,'campaign_manifest.csv'),'TextType','string');
assert(height(mf)==1&&mf.artifact=="campaign.mat" ...
    &&ny_reference_file_sha256(fullfile(folder,'campaign.mat'))==mf.sha256, ...
    'partial_spc_dlr_replay:Artifact','Thermal artifact fingerprint changed.');
d=load(fullfile(folder,'campaign.mat'),'out');s=d.out;c=compact_partial_spc_dlr_contract;
[code,runtime]=compact_partial_spc_dlr_code_manifest;
assert(isequal(code,s.code_manifest)&&isequal(runtime,s.runtime_manifest), ...
    'partial_spc_dlr_replay:Code','Thermal code or numerical runtime changed.');
assert(isequal(c,s.contract)&&isequal(c.weather,s.weather) ...
    &&~s.weather_observed&&~s.physical_conductor_verified&&~s.interface_targets_used ...
    &&~s.fresh_holdout_validation&&~s.historical_as_operated_reconstruction, ...
    'partial_spc_dlr_replay:Scope','Synthetic weather or claim scope changed.');
assert(height(s.electrical_source_fingerprints)==2&&numel(unique(s.electrical_source_fingerprints.relative_path))==2, ...
    'partial_spc_dlr_replay:Source','Expected electrical MAT and its independent manifest.');
for k=1:height(s.electrical_source_fingerprints)
    p=project_file(root,s.electrical_source_fingerprints.relative_path(k));
    assert(ny_reference_file_sha256(p)==s.electrical_source_fingerprints.sha256(k), ...
        'partial_spc_dlr_replay:Source','Electrical input bytes changed.');
end
ep=project_file(root,s.electrical_input_relative_path);
assert(ny_reference_file_sha256(ep)==s.electrical_input_sha256, ...
    'partial_spc_dlr_replay:Source','Electrical reference fingerprint changed.');
er=replay_compact_2025_partial_spc(fileparts(ep));assert(er.passed,'partial_spc_dlr_replay:Electrical','Source electrical replay failed.');
d=load(ep,'out');e=d.out;
assert(e.electrical_baseline_qualified&&all(e.case_summary.electrically_qualified) ...
    &&s.electrical_all_registered_cases_qualified&&isequal(e.code_manifest,s.electrical_code_manifest) ...
    &&isequaln(e.source_manifest,s.electrical_source_manifest), ...
    'partial_spc_dlr_replay:Source','Electrical provenance or qualification changed.');
j=find(e.case_summary.variant_id==c.electrical_variant_id&e.case_summary.scenario_id==c.electrical_scenario_id);assert(isscalar(j));
f=e.cases{j};
assert(s.electrical_scenario_id==c.electrical_scenario_id&&s.electrical_variant_id==c.electrical_variant_id ...
    &&isequaln(f.result,s.reference_electrical_case)&&isequal(f.snapshot.branch_keys,s.reference_branch_keys) ...
    &&isequal(f.snapshot.generator_keys,s.reference_generator_keys), ...
    'partial_spc_dlr_replay:Reference','Nominal source snapshot or device identity changed.');
pd=load(project_file(root,e.parent_relative_path),'out');vi=find(e.variants.variant_id==c.electrical_variant_id);assert(isscalar(vi));
b=apply_compact_2025_partial_spc(pd.out.modern_build,table2struct(e.variants(vi,2:end)));
selection=compact_partial_spc_dlr_selection(b,f.snapshot);
realizations=build_dlr_corridor_realizations(f.result,selection);lib=dlr_conductor_library;
assert(isequaln(selection,s.selection)&&isequaln(realizations,s.realizations)&&isequal(lib,s.conductors) ...
    &&isequaln(b.partial_spc_source_manifest,s.infrastructure_source_manifest), ...
    'partial_spc_dlr_replay:Realization','Reconstructed overhead realization or source register changed.');
assert(height(s.summary)==4&&numel(s.cases)==4 ...
    &&isequal(s.summary.weather_scenario,c.weather.scenario_id), ...
    'partial_spc_dlr_replay:Scope','The four preregistered synthetic weather cases are required.');
records=table();
for k=1:4
    v=s.cases{k};q=logical(s.summary.synthetic_electrothermal_qualified(k));
    assert(q==v.synthetic_electrothermal_qualified,'partial_spc_dlr_replay:Qualification','Conflicting saved qualification flags.');
    pass=false;dp=NaN;dv=NaN;heat=NaN;fraction=NaN;
    if q
        assert(isequal(v.weather,c.weather(k,:)),'partial_spc_dlr_replay:Weather','Saved case weather differs from contract.');
        expected=apply_dlr_temperature_resistance(f.result,realizations,v.temperature_c);
        hardware(v.result,expected);hardware(v.bounded_result,expected);
        assert(isequal(find(v.bounded_result.bus(:,2)==3),find(f.result.bus(:,2)==3)), ...
            'partial_spc_dlr_replay:Hardware','The bounded native reference identity changed.');
        ba=audit_ny_ac_reference(v.bounded_result,struct('branch_keys',f.snapshot.branch_keys,'generator_keys',f.snapshot.generator_keys));
        assert(ba.passed,'partial_spc_dlr_replay:Bounds','Saved bounded dispatch fails finite hardware limits.');
        fresh=runpf(v.bounded_result,mpoption('verbose',0,'out.all',0,'pf.enforce_q_lims',1,'pf.tol',1e-10));
        hardware(fresh,expected);
        a=audit_ny_ac_reference(fresh,struct('branch_keys',f.snapshot.branch_keys,'generator_keys',f.snapshot.generator_keys));
        dp=max(abs(fresh.gen(:,2)-v.bounded_result.gen(:,2)));
        dv=max(abs(fresh.bus(:,8)-v.bounded_result.bus(:,8)));
        assert(max(abs(fresh.gen(:,2)-v.result.gen(:,2)))<1e-3 ...
            &&max(abs(fresh.bus(:,8)-v.result.bus(:,8)))<1e-4, ...
            'partial_spc_dlr_replay:Dispatch','Fresh bounded-dispatch replay differs from saved PF.');
        fresh_v=v;fresh_v.result=fresh;
        guards=test_dlr_operating_guards(fresh_v,realizations);
        ca=dlr_series_current_audit(fresh,realizations,v.temperature_c);
        [ok,ci]=ismember(realizations.conductor_code,lib.conductor_code);assert(all(ok));
        residual=zeros(height(realizations),1);amps=residual;equilibrium=residual;
        for n=1:height(realizations)
            w=c.weather(k,:);conductor=lib(ci(n),:);amp=dlr_steady_ampacity(conductor,w);amps(n)=amp.ampacity_amp;
            h=dlr_heat_balance(v.temperature_c(n),ca.subconductor_current_amp(n),conductor,w);residual(n)=h.net_w_m;
            equilibrium(n)=fzero(@(T)netheat(T,ca.subconductor_current_amp(n),conductor,w),[w.ambient_c-1 200]);
        end
        heat=max(abs(residual));fraction=max(ca.subconductor_current_amp./amps);
        pass=a.passed&&ba.passed&&all(guards.passed)&&dp<1e-3&&dv<1e-4 ...
            &&heat<=.025&&max(abs(equilibrium-v.temperature_c))<=.005 ...
            &&all(v.temperature_c<=lib.temperature_limit_c(ci)+.005)&&fraction<=1+1e-6;
        assert(pass,'partial_spc_dlr_replay:Physics','Fresh AC, ampacity or thermal equilibrium failed.');
    end
    records=[records;table(c.weather.scenario_id(k),q,pass,dp,dv,heat,fraction, ...
        'VariableNames',{'weather_scenario','saved_qualified','passed','fresh_P_adjustment_mw', ...
        'fresh_VM_adjustment_pu','fresh_max_heat_residual_w_m','fresh_max_ampacity_fraction'})]; %#ok<AGROW>
end
expected_qualification=s.options.run_tests&&~isempty(s.tests)&&all(s.tests.passed)&&all(records.passed);
assert(s.research_thermal_baseline_qualified==expected_qualification, ...
    'partial_spc_dlr_replay:Qualification','Campaign qualification must reflect all independent weather cases and tests.');
out=struct('passed',all(records.passed)&&expected_qualification,'records',records, ...
    'optimizer_called',false,'electrical_source_replayed',er.passed,'source_and_code_verified',true, ...
    'weather_observed',false,'physical_asset_validation',false,'scope',c.scope);
end
function hardware(m,expected)
assert(m.baseMVA==expected.baseMVA&&isequal(size(m.bus),size(expected.bus)) ...
    &&size(m.branch,1)==size(expected.branch,1)&&size(m.gen,1)==size(expected.gen,1) ...
    &&isequal(m.branch(:,1:13),expected.branch(:,1:13)) ...
    &&isequal(m.bus(:,[1 3:7 10:13]),expected.bus(:,[1 3:7 10:13])) ...
    &&isequal(m.gen(:,[1 4:5 7:21]),expected.gen(:,[1 4:5 7:21])), ...
    'partial_spc_dlr_replay:Hardware','Only registered R(T) and bounded operating controls may change.');
end
function h=netheat(t,i,c,w)
r=dlr_heat_balance(t,i,c,w);h=r.net_w_m;
end
function p=project_file(root,relative)
p=char(java.io.File(fullfile(root,replace(string(relative),"\","/"))).getCanonicalPath());
r=string(char(java.io.File(root).getCanonicalPath()));
assert(startsWith(lower(string(p)),lower(r+filesep)),'partial_spc_dlr_replay:Source','Input must remain inside the repository.');
end
