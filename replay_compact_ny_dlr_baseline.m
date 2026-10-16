function out=replay_compact_ny_dlr_baseline
%REPLAY_COMPACT_NY_DLR_BASELINE Fresh AC/heat checks without optimization.
root=fileparts(mfilename('fullpath'));addpath(fullfile(root,'System Matpower Format'));
addpath(fullfile(root,'System Matpower Format','NY_Lite'));
folder=fullfile(root,'output','compact_ny_2025','thermal');d=load(fullfile(folder,'compact_ny_dlr_campaign.mat'),'out');
saved=d.out;records=table();
reference_file=saved.options.electrical_path;
if strlength(saved.electrical_input_relative_path)>0,reference_file=fullfile(root,saved.electrical_input_relative_path);end
e=load(reference_file,'out');j=find(e.out.inputs.snapshots.scenario_id==saved.electrical_scenario_id);assert(isscalar(j));
fit=e.out.cases{j};assert(isequaln(fit.result,saved.reference_electrical_case),'dlr:ReferenceChanged','Electrical source state changed.');
selection=compact_dlr_selection(e.out.modern_build,fit.snapshot);
realizations=build_dlr_corridor_realizations(fit.result,selection);
assert(isequaln(realizations,saved.realizations),'dlr:RealizationChanged','Reconstructed conductor realization differs.');
for k=1:height(saved.weather)
    [m,t]=npcc_ny_2025_synthetic_dlr(saved.weather.scenario_id(k));
    frozen=apply_dlr_temperature_resistance(fit.result,realizations,t.temperature_c);
    assert(isequal(m.branch(:,1:13),frozen.branch(:,1:13)) ...
        &&isequal(m.bus(:,[1 3:7 10:13]),frozen.bus(:,[1 3:7 10:13])) ...
        &&isequal(m.gen(:,[1 4:5 7:10]),frozen.gen(:,[1 4:5 7:10])), ...
        'dlr:HardwareChanged','Only registered R(T) and bounded operating controls may change.');
    r=runpf(m,mpoption('verbose',0,'out.all',0,'pf.enforce_q_lims',1,'pf.tol',1e-10));a=audit_ny_ac_reference(r);
    v=saved.cases{k};v.result=r;checks=test_dlr_operating_guards(v,t.realizations);
    dp=max(abs(r.gen(:,2)-m.gen(:,2)));dv=max(abs(r.bus(:,8)-m.bus(:,8)));
    pass=a.passed&&all(checks.passed)&&dp<1e-3&&dv<1e-4;assert(pass,'dlr:Replay','Fresh electrical/thermal replay failed.');
    records=[records;table(saved.weather.scenario_id(k),pass,dp,dv,'VariableNames', ...
        {'weather_scenario','passed','fresh_P_adjustment_mw','fresh_VM_adjustment_pu'})]; %#ok<AGROW>
end
out=struct('passed',all(records.passed),'records',records,'optimizer_called',false, ...
    'physical_asset_validation',false,'scope',"synthetic_lumped_overhead_models_only");
end
