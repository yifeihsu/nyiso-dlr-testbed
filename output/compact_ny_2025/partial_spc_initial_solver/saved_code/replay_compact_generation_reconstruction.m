function out=replay_compact_generation_reconstruction(folder)
%REPLAY_COMPACT_GENERATION_RECONSTRUCTION Fresh PF, priors and research cuts.
% This does not call an optimizer or read newly scored interface targets.
root=fileparts(mfilename('fullpath'));addpath(fullfile(root,'System Matpower Format','NY_Lite'));
if nargin<1,folder=fullfile(root,'output','compact_ny_2025','generation_reconstruction');end
manifest=readtable(fullfile(folder,'campaign_manifest.csv'),'TextType','string');
assert(height(manifest)==1&&manifest.artifact=="campaign.mat");
path=fullfile(folder,manifest.artifact);
assert(ny_reference_file_sha256(path)==manifest.sha256,'generation_replay:Artifact','Saved campaign bytes changed.');
loaded=load(path,'out');o=loaded.out;define_constants;
for k=1:height(o.code_manifest)
    r=o.code_manifest(k,:);assert(sha_lf(fullfile(root,r.relative_path))==r.sha256_lf_normalized, ...
        'generation_replay:Code','Changed code %s.',r.relative_path);
end
for k=1:height(o.source_manifest)
    r=o.source_manifest(k,:);assert(sha_lf(fullfile(root,r.source_path))==r.sha256_lf_normalized, ...
        'generation_replay:Source','Changed source %s.',r.source_path);
end
assert(~o.internal_interface_targets_used&&~o.interface_scoring_performed ...
    &&all(isnan(o.inputs.interfaces.target_flow_mw))&&all(isnan(o.inputs.interfaces.actual_flow_mw)), ...
    'generation_replay:Leakage','Campaign must contain target-free predictions.');
records=table();
for k=1:numel(o.cases)
    f=o.cases{k};sc=o.case_summary(k,:);if isempty(f),assert(~sc.input_coverage_qualified);continue;end
    assert(~f.internal_interface_fit_used&&all(isnan(f.snapshot.interface_targets.target_flow_mw)));
    prior=apply_compact_independent_generation_prior(f.snapshot,o.source_priors,o.named_source_priors);
    priors_same=isequal(prior.Pg_prior_mw,f.snapshot.Pg_prior_mw)&&isequal(prior.Pg_sigma_mw,f.snapshot.Pg_sigma_mw);
    op=compact_nyiso_interface_operator_variant(f.result,f.snapshot.branch_keys);
    operators_same=isequal(op.from_coefficients,f.snapshot.operators.from_coefficients) ...
        &&isequal(op.to_coefficients,f.snapshot.operators.to_coefficients);
    ref=f.result;
    fresh=runpf(ref,mpoption('verbose',0,'out.all',0,'pf.tol',1e-10,'pf.enforce_q_lims',1));
    audit=audit_ny_ac_reference(fresh,struct('branch_keys',f.snapshot.branch_keys,'generator_keys',f.snapshot.generator_keys));
    hardware=isequal(fresh.branch(:,1:13),f.input.branch(:,1:13)) ...
        &&isequal(fresh.bus(:,[BUS_I PD QD GS BS BASE_KV VMIN VMAX]),f.input.bus(:,[BUS_I PD QD GS BS BASE_KV VMIN VMAX])) ...
        &&isequal(fresh.gen(:,[GEN_BUS GEN_STATUS PMIN PMAX QMIN QMAX]),f.input.gen(:,[GEN_BUS GEN_STATUS PMIN PMAX QMIN QMAX]));
    dp=max(abs(fresh.gen(:,PG)-ref.gen(:,PG)));dv=max(abs(fresh.bus(:,VM)-ref.bus(:,VM)));
    flow=op.from_coefficients*fresh.branch(:,PF)+op.to_coefficients*fresh.branch(:,PT);
    df=max(abs(flow-f.residuals.model_flow_mw));
    pass=f.electrical_baseline_qualified&&audit.passed&&hardware&&priors_same&&operators_same&&dp<1e-3&&dv<1e-4&&df<1e-3;
    records=[records;table(sc.scenario_id,pass,audit.passed,hardware,priors_same,operators_same,dp,dv,df, ...
        'VariableNames',{'scenario_id','passed','fresh_pf_audit_passed','hardware_frozen','source_prior_reconstructed', ...
        'interface_operator_reconstructed','dispatch_difference_mw','voltage_difference_pu','proxy_flow_difference_mw'})]; %#ok<AGROW>
end
out=struct('records',records,'passed',height(records)==nnz(o.case_summary.input_coverage_qualified)&&all(records.passed), ...
    'registered_scenarios',height(o.case_summary),'eligible_scenarios',nnz(o.case_summary.input_coverage_qualified), ...
    'skipped_scenarios',o.case_summary(~o.case_summary.input_coverage_qualified,:), ...
    'code_manifest_verified',true,'source_manifest_verified',true,'optimizer_called',false, ...
    'internal_targets_used',false,'observed_zonal_generation_validated',false,'exact_public_interface_validation',false);
end

function hash=sha_lf(file)
fid=fopen(file,'rb');assert(fid>=0);guard=onCleanup(@()fclose(fid));bytes=fread(fid,Inf,'*uint8'); %#ok<NASGU>
bytes=uint8(strrep(strrep(char(bytes'),sprintf('\r\n'),sprintf('\n')),sprintf('\r'),sprintf('\n')));
md=java.security.MessageDigest.getInstance('SHA-256');md.update(bytes);
hash=string(lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2)',1,[])));
end
