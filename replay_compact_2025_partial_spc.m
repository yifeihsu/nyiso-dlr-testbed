function out=replay_compact_2025_partial_spc(folder)
%REPLAY_COMPACT_2025_PARTIAL_SPC Rebuild topology/priors and independently PF.
root=fileparts(mfilename('fullpath'));addpath(fullfile(root,'System Matpower Format','NY_Lite'));
if nargin<1,folder=fullfile(root,'output','compact_ny_2025','partial_spc');end
manifest=readtable(fullfile(folder,'campaign_manifest.csv'),'TextType','string');
assert(height(manifest)==1&&manifest.artifact=="campaign.mat");
assert(ny_reference_file_sha256(fullfile(folder,'campaign.mat'))==manifest.sha256,'partial_spc_replay:Artifact','Changed campaign.');
d=load(fullfile(folder,'campaign.mat'),'out');o=d.out;define_constants;
assert(ny_reference_file_sha256(fullfile(root,o.parent_relative_path))==o.parent_sha256,'partial_spc_replay:Parent','Changed parent.');
assert(~o.internal_interface_targets_used&&~o.interface_parameters_fitted&&~o.fresh_holdout_validation ...
    &&~o.historical_as_operated_reconstruction&&o.topology_as_of=="2025-12-31");
assert(~isempty(o.case_summary)&&height(o.case_summary)==numel(o.cases) ...
    &&height(unique(o.case_summary(:,{'variant_id','scenario_id'})))==height(o.case_summary), ...
    'partial_spc_replay:Inventory','Missing or duplicate saved operating states.');
for k=1:height(o.code_manifest)
    assert(sha_lf(fullfile(root,o.code_manifest.relative_path(k)))==o.code_manifest.sha256_lf_normalized(k), ...
        'partial_spc_replay:Code','Changed code %s.',o.code_manifest.relative_path(k));
end
for k=1:height(o.source_manifest)
    assert(sha_lf(fullfile(root,o.source_manifest.source_path(k)))==o.source_manifest.sha256_lf_normalized(k), ...
        'partial_spc_replay:Source','Changed source %s.',o.source_manifest.source_path(k));
end
parent_replay=replay_compact_generation_reconstruction(fileparts(fullfile(root,o.parent_relative_path)));assert(parent_replay.passed);
d=load(fullfile(root,o.parent_relative_path),'out');parent=d.out;records=table();
ids=parent.case_summary.scenario_id(parent.case_summary.vintage==2025&parent.case_summary.input_coverage_qualified);
expected=table(repmat("nominal",numel(ids),1),ids,'VariableNames',{'variant_id','scenario_id'});
assert(nnz(o.variants.variant_id=="nominal")==1&&numel(unique(o.variants.variant_id))==height(o.variants));
for v=find(o.variants.variant_id~="nominal")'
    expected=[expected;table(o.variants.variant_id(v),"S1_2025_SUMMER_PEAK_PUBLIC", ...
        'VariableNames',expected.Properties.VariableNames)]; %#ok<AGROW>
end
assert(isequal(sortrows(expected,{'variant_id','scenario_id'}), ...
    sortrows(o.case_summary(:,{'variant_id','scenario_id'}),{'variant_id','scenario_id'})), ...
    'partial_spc_replay:Inventory','Saved campaign does not cover its registered nominal and sensitivity states.');
for k=1:height(o.case_summary)
    row=o.case_summary(k,:);v=find(o.variants.variant_id==row.variant_id);assert(isscalar(v));
    b=apply_compact_2025_partial_spc(parent.modern_build,table2struct(o.variants(v,2:end)));
    s=build_compact_nyiso_operating_snapshot(b,parent.inputs,row.scenario_id);
    s.operators=compact_nyiso_interface_operator_variant(s.candidate,s.branch_keys);
    s=apply_compact_independent_generation_prior(s,parent.source_priors,parent.named_source_priors);
    f=o.cases{k};pass=false;hardware=false;priors=false;ac=false;dp=NaN;dv=NaN;df=NaN;
    if ~isempty(f)
        assert(~f.internal_interface_fit_used&&all(isnan(f.snapshot.interface_targets.target_flow_mw)) ...
            &&f.snapshot.snapshot.campaign_role=="revisited_counterfactual_diagnostic", ...
            'partial_spc_replay:Scope','Saved state must be a target-free counterfactual diagnostic.');
        hardware=isequal(s.candidate,f.snapshot.candidate)&&isequal(s.branch_keys,f.snapshot.branch_keys) ...
            &&isequal(s.generator_keys,f.snapshot.generator_keys);
        priors=isequal(s.Pg_prior_mw,f.snapshot.Pg_prior_mw)&&isequal(s.Pg_sigma_mw,f.snapshot.Pg_sigma_mw);
        fresh=runpf(f.result,mpoption('verbose',0,'out.all',0,'pf.tol',1e-10,'pf.enforce_q_lims',1));
        a=audit_ny_ac_reference(fresh,struct('branch_keys',s.branch_keys,'generator_keys',s.generator_keys));ac=a.passed;
        hardware=hardware&&isequal(fresh.branch(:,1:13),f.input.branch(:,1:13)) ...
            &&isequal(fresh.bus(:,[BUS_I PD QD GS BS BASE_KV VMIN VMAX]),f.input.bus(:,[BUS_I PD QD GS BS BASE_KV VMIN VMAX])) ...
            &&isequal(fresh.gen(:,[GEN_BUS GEN_STATUS PMIN PMAX QMIN QMAX]),f.input.gen(:,[GEN_BUS GEN_STATUS PMIN PMAX QMIN QMAX]));
        dp=max(abs(fresh.gen(:,PG)-f.result.gen(:,PG)));dv=max(abs(fresh.bus(:,VM)-f.result.bus(:,VM)));
        flow=s.operators.from_coefficients*fresh.branch(:,PF)+s.operators.to_coefficients*fresh.branch(:,PT);
        df=max(abs(flow-f.residuals.model_flow_mw));
        pass=row.electrically_qualified&&f.electrical_baseline_qualified&&hardware&&priors&&ac&&dp<1e-3&&dv<1e-4&&df<1e-3;
    end
    records=[records;table(row.variant_id,row.scenario_id,pass,hardware,priors,ac,dp,dv,df, ...
        'VariableNames',{'variant_id','scenario_id','passed','topology_and_injections_rebuilt', ...
        'generation_prior_rebuilt','independent_pf_audit_passed','dispatch_difference_mw','voltage_difference_pu','flow_difference_mw'})]; %#ok<AGROW>
end
out=struct('records',records,'passed',~isempty(records)&&all(records.passed),'optimizer_called',false,'interface_targets_used',false, ...
    'parent_and_code_verified',true,'source_manifest_verified',true,'fresh_holdout_validation',false, ...
    'historical_as_operated_reconstruction',false);
end
function h=sha_lf(path)
fid=fopen(path,'rb');assert(fid>=0);guard=onCleanup(@()fclose(fid));b=fread(fid,Inf,'*uint8'); %#ok<NASGU>
b=uint8(strrep(strrep(char(b'),sprintf('\r\n'),sprintf('\n')),sprintf('\r'),sprintf('\n')));
md=java.security.MessageDigest.getInstance('SHA-256');md.update(b);
h=string(lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2)',1,[])));
end
