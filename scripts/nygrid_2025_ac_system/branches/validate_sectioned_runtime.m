function validate_sectioned_runtime()
% Read-only cross-language compiler checks; no OPF/PF or operating claim.
root=fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
folder=fullfile(root,'output','nygrid_2025_ac_system','branches');
rawfile=fullfile(folder,'revision_03_composite_capacity','engineering_overlay.mat');
prefile=fullfile(root,'output','nygrid_2025_line_parameters','overlays','engineering_nominal','full191_network_cases.mat');
postfile=fullfile(root,'output','nygrid_2025_dover_parameters','network','x_nominal.mat');
fixturefile=fullfile(folder,'sectioned_design_fixtures.mat');
planfile=fullfile(folder,'sectioned_design_plan.mat');
raw=load(rawfile);pre=load(prefile);post=load(postfile);fixtures=load(fixturefile);plan=load(planfile);
labels={'pre_may','may21','may30','post_dover'};
parents={pre.refined_2025_pre_may_case,pre.refined_2025_may21_case,pre.refined_2025_may30_case,post.full_case};
checks=table();
for k=1:numel(labels)
    m=parents{k};n=size(m.branch,1);m.branch(:,3:8)=raw.branch_reference(1:n,3:8);m.branch(211,11)=0;
    [out,info]=nygrid_ac_apply_sections(m,raw.branch_keys(1:n));expected=fixtures.cases.(labels{k});reference=fixtures.runtime.(labels{k});
    bus_error=max(abs(out.bus-expected.bus),[],'all');branch_error=max(abs(out.branch-expected.branch),[],'all');
    assert(bus_error<1e-12&&branch_error<1e-12);
    assert(isequal(info.branch_keys(:),reference.branch_keys(:)));
    assert(isequaln(info.terminal_current_limit_A,reference.terminal_current_limit_A) ...
        &&isequaln(info.static_cable_current_limit_A,reference.static_cable_current_limit_A));
    thermal_error=compare_segments(info.thermal_segments,reference.thermal_segments);
    cable_error=compare_segments(info.cable_segments,reference.cable_segments);
    assert(max(thermal_error,cable_error)<1e-12);
    assert(isequal(out.gen,m.gen)&&isequal(out.dcline,m.dcline)&&size(out.bus,1)==size(m.bus,1)+75);
    assert(all(out.bus(size(m.bus,1)+1:end,3:6)==0,'all'));
    checks=[checks;table(string(labels{k}),size(out.bus,1),size(out.branch,1),bus_error,branch_error,thermal_error,cable_error, ...
        info.added_bus_count,numel(info.thermal_segments),numel(info.cable_segments), ...
        'VariableNames',{'state','buses','branch_records','bus_matrix_error','branch_matrix_error','OH_segment_error', ...
        'cable_segment_error','added_zero_injection_nodes','OH_segments','cable_sections'})]; %#ok<AGROW>
end
% Real dated states keep all split long lines in service. Exercise the branch
% that omits both computational nodes and its associated fixed reactors.
m=post.full_case;m.branch(:,3:8)=raw.branch_reference(:,3:8);m.branch(211,11)=0;
[on,oninfo]=nygrid_ac_apply_sections(m,raw.branch_keys);
m.branch(185,11)=0;
[off,offinfo]=nygrid_ac_apply_sections(m,raw.branch_keys);
removed=double(plan.section_count(185))-1;
ids=60000+185*100+(1:removed);
assert(removed==5&&offinfo.added_bus_count==70&&~any(ismember(ids,off.bus(:,1))) ...
    &&off.branch(185,11)==0&&size(off.branch,1)==size(on.branch,1)-removed);
assert(~any([offinfo.thermal_segments.original_branch_row]==185));
reactor=offinfo.reactor_ledger([offinfo.reactor_ledger.original_branch_row]==185);
assert(isscalar(reactor)&&~reactor.associated_line_active&&reactor.applied_total_reactor_mvar_at1pu==0);
f=find(m.bus(:,1)==m.branch(185,1));t=find(m.bus(:,1)==m.branch(185,2));q=double(plan.reactor_total_nominal_mvar(185));
delta=off.bus(1:size(m.bus,1),6)-on.bus(1:size(m.bus,1),6);expected_delta=zeros(size(delta));expected_delta([f,t])=q/2;
assert(max(abs(delta-expected_delta))<1e-10&&abs(q-607.2794681638039)<1e-9);
guard=table();
guard=[guard;expect_error('double_application',@()nygrid_ac_apply_sections(on,oninfo.branch_keys),'acSections:AlreadyApplied')];
badkeys=raw.branch_keys;badkeys{1}='WRONG';
guard=[guard;expect_error('changed_parent_key',@()nygrid_ac_apply_sections(m,badkeys),'acSections:ParentKeys')];
bad=m;bad.branch(1,3)=bad.branch(1,3)+.01;
guard=[guard;expect_error('changed_R_before_compiler',@()nygrid_ac_apply_sections(bad,raw.branch_keys),'acSections:ParentParameters')];
bad=m;counts=plan.section_count(:);first=find(counts(1:size(m.branch,1))>1&m.branch(:,11)>0,1);bad.branch(first,10)=1;
guard=[guard;expect_error('phase_shifter_not_split_as_line',@()nygrid_ac_apply_sections(bad,raw.branch_keys),'acSections:NonLine')];
files={rawfile,prefile,postfile,fixturefile,planfile,fullfile(folder,'sectioned_design_receipt.json'), ...
    which('nygrid_ac_apply_sections'),[mfilename('fullpath'),'.m']};
dependencies=struct('path',{},'sha256',{});
for k=1:numel(files),dependencies(end+1)=struct('path',files{k},'sha256',file_sha256(files{k}));end %#ok<AGROW>
writetable(checks,fullfile(folder,'sectioned_matlab_parity_checks.csv'));
writetable(guard,fullfile(folder,'sectioned_matlab_guard_checks.csv'));
report=struct('passed',true,'cross_language_topology_states',height(checks),'wrapper_guards',height(guard), ...
    'maximum_bus_matrix_error',max(checks.bus_matrix_error),'maximum_branch_matrix_error',max(checks.branch_matrix_error), ...
    'maximum_OH_segment_error',max(checks.OH_segment_error),'maximum_cable_segment_error',max(checks.cable_segment_error), ...
    'inactive_split_corridor_row',185,'inactive_split_internal_nodes_omitted',removed, ...
    'inactive_split_reactor_mvar_omitted',q,'no_transfer_generator_or_original_PD_QD_GS_change',true, ...
    'new_OPF_or_PF_run',false,'MATLAB_version',version,'dependencies',dependencies);
fid=fopen(fullfile(folder,'sectioned_matlab_runtime_validation.json'),'w');assert(fid>=0);cleanup=onCleanup(@()fclose(fid));
fprintf(fid,'%s\n',jsonencode(report,'PrettyPrint',true));disp(report);
end
function error_value=compare_segments(a,b)
if iscell(a),a=[a{:}];end;if iscell(b),b=[b{:}];end
assert(numel(a)==numel(b));error_value=0;
for j=1:numel(a)
    assert(a(j).branch_row==b(j).branch_row&&strcmp(a(j).branch_key,b(j).branch_key) ...
        &&strcmp(a(j).catalog_id,b(j).catalog_id)&&a(j).circuits==b(j).circuits&&a(j).bundle_count==b(j).bundle_count);
    for f={'segment_length_m','reference_r_pu','reference_x_pu','reference_b_pu'}
        error_value=max(error_value,abs(a(j).(f{1})-b(j).(f{1})));
    end
end
end
function row=expect_error(name,call,identifier)
rejected=false;got="";try,call();catch err,got=string(err.identifier);rejected=strcmp(err.identifier,identifier);end
assert(rejected,'acSections:MissingGuard','Guard %s returned %s.',name,got);
row=table(string(name),true,got,'VariableNames',{'test','passed','error_identifier'});
end
function digest=file_sha256(path)
engine=java.security.MessageDigest.getInstance('SHA-256');fid=fopen(path,'rb');assert(fid>=0);cleanup=onCleanup(@()fclose(fid));
while ~feof(fid),bytes=fread(fid,1048576,'*uint8');if ~isempty(bytes),engine.update(typecast(bytes,'int8'));end,end
raw=typecast(engine.digest(),'uint8');digest=lower(reshape(dec2hex(raw,2)',1,[]));
end
