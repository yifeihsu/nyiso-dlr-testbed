function report=run_nyrepair_annual(run_label,resume)
% Versioned current-runtime replay. Call only after the candidate is frozen.
% Resume authenticates completed monthly checkpoints; old deliveries are read-only.
if nargin<1,run_label='physical_repair_v1';end
if nargin<2,resume=false;end
assert(ischar(run_label)&&~isempty(regexp(run_label,'^[A-Za-z][A-Za-z0-9_-]{0,63}$','once')));
root=fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
annual=fullfile(root,'output','nygrid_2025_physical_repair','annual');out=fullfile(annual,run_label);
bundle=fullfile(annual,'baseline_bundle');runtime=fullfile(bundle,'runtime');addpath(runtime);
core=fullfile(root,'scripts','nygrid_2025_physical_repair','core');addpath(core);
setup=setup_nygrid_latest(bundle,'C:/Users/Holiday/OneDrive/Documents/MATLAB/matpower');
candidate_path=fullfile(root,'output','nygrid_2025_physical_repair','candidate_receipt.json');
assert(isfile(candidate_path),'nyrepair:Unfrozen','Freeze the candidate receipt before annual replay.');
candidate_receipt=jsondecode(fileread(candidate_path));
assert(isfield(candidate_receipt,'passed')&&candidate_receipt.passed,'nyrepair:CandidateGate','Candidate validation has not passed.');
assert(strcmp(which('nyrepair_apply_case'),fullfile(core,'nyrepair_apply_case.m')));
frozen=load(fullfile(annual,'frozen_baseline_axes.mat'));[model,model_receipt]=nylatest_data();
assert(isequal(double(model.axis.hour_index(:)),double(frozen.hour_index(:))) ...
    &&isequal(string(model.axis.timestamp_utc(:)),string(frozen.timestamp_utc)) ...
    &&isequal(logical(model.axis.source_qualified(:)),logical(frozen.source_qualified(:))));
assert(model.scale_factor_gamma==frozen.gamma&&nnz(frozen.source_qualified)==8651&&nnz(frozen.current_baseline_qualified)==8170);
if isfolder(out),assert(resume,'nyrepair:PreserveRun','Use a new label or explicitly resume this identical frozen run.');else,mkdir(out);end
monthly=fullfile(out,'monthly');if ~isfolder(monthly),mkdir(monthly);end
records=collect_source_records(root,setup,annual,candidate_path);started=tic;
options=struct('backend','compact','loss_mode','boundary_consistent');
hour_index=(1:8760)';timestamp_utc=cellstr(string(model.axis.timestamp_utc(:)));
source_qualified=logical(frozen.source_qualified(:));current_baseline_qualified=logical(frozen.current_baseline_qualified(:));
gamma=double(frozen.gamma);topology_state_index=double(model.axis.state_index(:));topology_state_names=cellstr(string(model.axis.state_names(:)));
clock=datetime(string(timestamp_utc),'InputFormat','yyyy-MM-dd''T''HH:mm:ss''Z''','TimeZone','UTC');clock.TimeZone='America/New_York';model_month=month(clock);
canonical=load_nygrid_latest(double(model.axis.template_hours(4)));[canonical,~]=nyrepair_apply_case(canonical);
bus_id=canonical.bus(:,1);base_kv=canonical.bus(:,10);branch_keys=cellstr(string(canonical.userdata.ac_system.branch_keys(:)));
branch_parent_row=canonical.userdata.ac_system.branch_parent_row;branch_from_bus=canonical.branch(:,1);branch_to_bus=canonical.branch(:,2);
generator_bus_id=canonical.gen(:,1);external_generator_rows_1based=find(model.external.generator_mask);
DC_from_bus=canonical.dcline(:,1);DC_to_bus=canonical.dcline(:,2);retained_bus_ids=double(model.retained_bus_ids(:));
axesfile=fullfile(out,'annual_axes.mat');networkfile=fullfile(out,'annual_network.mat');
if isfile(axesfile)
    prior=load(axesfile,'source_records','candidate_sha256','hour_index','timestamp_utc');
    assert(isequal(prior.source_records,records)&&strcmp(prior.candidate_sha256,nylatest_file_sha256(candidate_path)),'nyrepair:ChangedResume','Frozen replay sources changed.');
    assert(isequal(prior.hour_index,hour_index)&&isequal(prior.timestamp_utc,timestamp_utc));
else
    candidate_sha256=nylatest_file_sha256(candidate_path);source_records=records;
    save(axesfile,'hour_index','timestamp_utc','source_qualified','current_baseline_qualified','gamma','topology_state_index','topology_state_names', ...
        'model_month','bus_id','base_kv','branch_keys','branch_parent_row','branch_from_bus','branch_to_bus','generator_bus_id', ...
        'external_generator_rows_1based','DC_from_bus','DC_to_bus','retained_bus_ids','options','run_label','source_records', ...
        'candidate_sha256','candidate_receipt','setup','model_receipt','-v7');
end
templates=cell(4,1);ib=cell(4,1);il=cell(4,1);gb=cell(4,1);
for state=1:4
    h=double(model.axis.template_hours(state));old=load_nygrid_latest(h);[m,change]=nyrepair_apply_case(old);
    assert(isequal(old.bus(:,1),m.bus(:,1))&&isequal(old.branch(:,1:2),m.branch(:,1:2))&&isequal(old.gen,m.gen)&&isequal(old.dcline,m.dcline));
    assert(isequal(old.bus(:,3:4),m.bus(:,3:4))&&isequal(old.userdata.latest_runtime.retained_bus_ids,m.userdata.latest_runtime.retained_bus_ids));
    [ok,ib{state}]=ismember(m.bus(:,1),bus_id);assert(all(ok));
    keys=cellstr(string(m.userdata.ac_system.branch_keys(:)));[ok,il{state}]=ismember(keys,branch_keys);assert(all(ok));
    [ok,gb{state}]=ismember(m.gen(:,1),bus_id);assert(all(ok));
    p=nylatest_prepare_policy(m);
    templates{state}=struct('state_index',state,'template_hour',h,'baseMVA',m.baseMVA,'bus',m.bus,'branch',m.branch,'gen',m.gen,'dcline',m.dcline, ...
        'old_bus',old.bus,'old_branch',old.branch,'branch_keys',{keys},'branch_parent_row',m.userdata.ac_system.branch_parent_row, ...
        'policy',p,'retained_bus_ids',retained_bus_ids,'candidate_change',change,'current_limits',current_limits(m));
end
if ~isfile(networkfile),save(networkfile,'templates','-v7');else,prior=load(networkfile,'templates');assert(isequaln(prior.templates,templates));end
nb=numel(bus_id);nl=numel(branch_keys);ng=numel(generator_bus_id);
flags={'PF_converged','AC_equation_gate','loss_allocation_gate','reduction_and_equation_gate','VQ_and_generator_assumption_gate','full_operating_gate'};
scalars={'native_PG_change_from_original_MW','HQ_PG_change_from_original_MW','NY_gross_load_accounting_residual_MW', ...
    'regional_NY_import_residual_MW','max_P_bound_violation_mw','max_Q_bound_violation_mvar','max_assumed_generator_S_bound_violation_mva', ...
    'max_voltage_bound_violation_pu','min_voltage_pu','max_voltage_pu','max_equipment_MVA_violation','max_fixed_transfer_P_change_mw', ...
    'max_transfer_Q_bound_violation_mvar','max_nodal_P_residual_mw','max_nodal_Q_residual_mvar','loss_budget_residual_MW', ...
    'reference_PG_change_from_original_MW','maximum_NY_zonal_loss_fraction','minimum_NY_served_PD_MW','loss_iterations','total_NR_iterations', ...
    'recovery_voltage_error_pu','recovered_current_error_A','max_series_loss_identity_error_mw'};
month_receipts=struct([]);quality=cell(12,1);
for mon=1:12
    path=fullfile(monthly,sprintf('profile_PF_2025_%02d.mat',mon));qpath=fullfile(monthly,sprintf('profile_PF_2025_%02d_quality.csv',mon));
    apath=fullfile(monthly,sprintf('profile_PF_2025_%02d_audits.mat',mon));rpath=fullfile(monthly,sprintf('profile_PF_2025_%02d_receipt.json',mon));
    if isfile(rpath)
        assert(resume);mr=jsondecode(fileread(rpath));assert(mr.month==mon&&mr.completed);
        for k=1:numel(mr.outputs),assert(strcmp(nylatest_file_sha256(mr.outputs(k).path),mr.outputs(k).sha256));end
        qt=readtable(qpath,'TextType','string');
        for name=[{'source_qualified','PF_attempted','solver_exception','qualified'} flags],qt.(name{1})=logical(qt.(name{1}));end
        quality{mon}=qt;month_receipts=[month_receipts;mr]; %#ok<AGROW>
        fprintf('REPAIR_YEAR reuse month%02d qualified%d\n',mon,mr.policy_equation_qualified);continue;
    end
    assert(~isfile(path)&&~isfile(qpath)&&~isfile(apath),'nyrepair:IncompleteCheckpoint','Preserve incomplete monthly files and choose a fresh label.');
    month_start=tic;hh=find(model_month==mon);nh=numel(hh);
    chunk=struct('hour_index',hh,'timestamp_utc',{timestamp_utc(hh)},'gamma',gamma,'source_qualified',source_qualified(hh), ...
        'current_baseline_qualified',current_baseline_qualified(hh),'bus_id',bus_id,'base_kv',base_kv,'branch_keys',{branch_keys}, ...
        'branch_parent_row',branch_parent_row,'branch_from_bus',branch_from_bus,'branch_to_bus',branch_to_bus,'generator_bus_id',generator_bus_id, ...
        'DC_from_bus',DC_from_bus,'DC_to_bus',DC_to_bus,'topology_state_index',topology_state_index(hh), ...
        'external_generator_rows_1based',external_generator_rows_1based,'retained_bus_ids',retained_bus_ids);
    for name={'VM','VA','PD','QD','bus_PG','bus_QG'},chunk.(name{1})=nan(nh,nb);end
    for name={'PF','QF','PT','QT','Iseries','Ifrom','Ito','branch_SHIFT'},chunk.(name{1})=nan(nh,nl);end
    for name={'gen_PG','gen_QG','gen_Pmin','gen_Pmax','gen_Qmin','gen_Qmax','gen_S_cap'},chunk.(name{1})=nan(nh,ng);end
    chunk.gen_status=false(nh,ng);
    for name={'DC_PF','DC_PT','DC_QF','DC_QT'},chunk.(name{1})=nan(nh,6);end
    chunk.external_gen_PG=nan(nh,28);chunk.NY_gross_target_MW=nan(nh,11);chunk.NY_served_PD_MW=nan(nh,11);
    chunk.NY_served_QD_MVAr=nan(nh,11);chunk.actual_budget_MW=nan(nh,14);
    chunk.regional_import_target_MW=nan(nh,3);chunk.regional_import_solved_MW=nan(nh,3);chunk.external_PG_increment_MW=nan(nh,3);
    chunk.retained_VM=nan(nh,148);chunk.retained_VA=nan(nh,148);chunk.bus_present=false(nh,nb);chunk.branch_present=false(nh,nl);chunk.branch_active=false(nh,nl);
    chunk.PF_attempted=false(nh,1);chunk.solver_exception=false(nh,1);chunk.computed_current_available=false(nh,1);chunk.qualified=false(nh,1);
    chunk.loss_status=repmat({'source_excluded'},nh,1);chunk.total_call_seconds=nan(nh,1);chunk.exception_identifier=repmat({''},nh,1);
    for name=flags,chunk.(name{1})=false(nh,1);end
    for name=scalars,chunk.(name{1})=nan(nh,1);end
    audits=cell(nh,1);traces=cell(nh,1);exceptions=cell(nh,1);
    for j=1:nh
        h=hh(j);if ~source_qualified(h),continue;end
        chunk.PF_attempted(j)=true;chunk.loss_status{j}='attempt_started';t=tic;
        try
            old=load_nygrid_latest(h);[baseline,~]=nyrepair_apply_case(old);s=topology_state_index(h);
            assert(isequal(old.gen,baseline.gen)&&isequal(old.dcline,baseline.dcline)&&isequal(old.bus(:,3:4),baseline.bus(:,3:4)));
            [compact,a,r,allocation]=nylatest_coupled_solve(baseline,options);
            p=allocation.policy_contract;m=allocation.final_input;
            a.HQ_PG_change_from_original_MW=r.gen(p.HQ,2)-baseline.gen(p.HQ,2);a.full_operating_gate=a.passed;
            chunk.total_call_seconds(j)=toc(t);audits{j}=a;traces{j}=allocation.trace;chunk.loss_status{j}=a.loss_status;
            for name=flags,chunk.(name{1})(j)=a.(name{1});end
            for name=scalars,chunk.(name{1})(j)=a.(name{1});end
            good=a.PF_converged&&a.AC_equation_gate&&a.loss_allocation_gate&&a.reduction_and_equation_gate;
            chunk.qualified(j)=good;chunk.computed_current_available(j)=good;
            assert(isequal(compact.retained_bus_ids(:),retained_bus_ids));
            chunk.retained_VM(j,:)=compact.bus(:,8);chunk.retained_VA(j,:)=compact.bus(:,9);
            chunk.VM(j,ib{s})=r.bus(:,8);chunk.VA(j,ib{s})=r.bus(:,9);chunk.PD(j,ib{s})=m.bus(:,3);chunk.QD(j,ib{s})=m.bus(:,4);
            chunk.bus_present(j,ib{s})=true;chunk.branch_present(j,il{s})=true;chunk.branch_active(j,il{s})=m.branch(:,11)>0;chunk.branch_SHIFT(j,il{s})=m.branch(:,10);
            chunk.bus_PG(j,:)=accumarray(gb{s},r.gen(:,2),[nb 1])';chunk.bus_QG(j,:)=accumarray(gb{s},r.gen(:,3),[nb 1])';
            chunk.gen_PG(j,:)=r.gen(:,2);chunk.gen_QG(j,:)=r.gen(:,3);chunk.gen_Pmin(j,:)=m.gen(:,10);chunk.gen_Pmax(j,:)=m.gen(:,9);
            chunk.gen_Qmin(j,:)=m.gen(:,5);chunk.gen_Qmax(j,:)=m.gen(:,4);chunk.gen_S_cap(j,:)=m.userdata.ac_system.generator_assumed_s_cap;chunk.gen_status(j,:)=m.gen(:,8)>0;
            chunk.PF(j,il{s})=r.branch(:,14);chunk.QF(j,il{s})=r.branch(:,15);chunk.PT(j,il{s})=r.branch(:,16);chunk.QT(j,il{s})=r.branch(:,17);
            chunk.Ifrom(j,il{s})=compact.recovered_line_current_A(:,1);chunk.Ito(j,il{s})=compact.recovered_line_current_A(:,2);chunk.Iseries(j,il{s})=compact.recovered_line_current_A(:,3);
            chunk.DC_PF(j,:)=r.dcline(:,4);chunk.DC_PT(j,:)=r.dcline(:,5);chunk.DC_QF(j,:)=r.dcline(:,6);chunk.DC_QT(j,:)=r.dcline(:,7);
            chunk.external_gen_PG(j,:)=r.gen(external_generator_rows_1based,2);
            chunk.NY_gross_target_MW(j,:)=allocation.NY_gross_target_MW;chunk.NY_served_PD_MW(j,:)=allocation.NY_served_PD_MW;chunk.NY_served_QD_MVAr(j,:)=allocation.NY_served_QD_MVAr;
            chunk.actual_budget_MW(j,:)=allocation.actual_budget_MW;chunk.regional_import_target_MW(j,:)=allocation.regional_import_target_MW;
            chunk.regional_import_solved_MW(j,:)=allocation.regional_import_solved_MW;chunk.external_PG_increment_MW(j,:)=allocation.external_PG_increment_MW;
        catch err
            % Programming, schema, mapping and export defects must stop the
            % campaign rather than masquerading as thousands of PF failures.
            if ~strcmp(err.identifier,'acLoss:NoAdmissibleState'),rethrow(err);end
            chunk.solver_exception(j)=true;chunk.qualified(j)=false;chunk.computed_current_available(j)=false;
            chunk.loss_status{j}=['exception:',err.identifier];chunk.exception_identifier{j}=err.identifier;chunk.total_call_seconds(j)=toc(t);
            exceptions{j}=struct('hour_index',h,'identifier',err.identifier,'message',err.message,'report',getReport(err,'extended'));
            fprintf('REPAIR_YEAR exception h%d %s\n',h,err.identifier);
        end
        if mod(j,100)==0,fprintf('REPAIR_YEAR month%02d position%d/%d qualified%d elapsed%.1fs\n',mon,j,nh,nnz(chunk.qualified),toc(month_start));end
    end
    save(path,'-struct','chunk','-v7');save(apath,'hh','audits','traces','exceptions','-v7');
    q=table(chunk.hour_index,string(chunk.timestamp_utc),chunk.source_qualified,chunk.PF_attempted,chunk.solver_exception,chunk.qualified, ...
        string(chunk.loss_status),string(chunk.exception_identifier),chunk.total_call_seconds, ...
        'VariableNames',{'hour_index','timestamp_utc','source_qualified','PF_attempted','solver_exception','qualified','loss_status','exception_identifier','total_call_seconds'});
    for name=[flags scalars],q.(name{1})=chunk.(name{1});end
    writetable(q,qpath);quality{mon}=q;
    mr=struct('month',mon,'completed',true,'hour_positions',nh,'source_qualified',nnz(chunk.source_qualified),'PF_attempted',nnz(chunk.PF_attempted), ...
        'PF_converged',nnz(chunk.PF_converged),'policy_equation_qualified',nnz(chunk.qualified),'VQ_qualified',nnz(chunk.VQ_and_generator_assumption_gate), ...
        'full_operating_qualified',nnz(chunk.full_operating_gate),'solver_exceptions',nnz(chunk.solver_exception),'elapsed_seconds',toc(month_start), ...
        'outputs',[file_record(path),file_record(qpath),file_record(apath)]);
    write_json(rpath,mr);month_receipts=[month_receipts;mr]; %#ok<AGROW>
    write_json(fullfile(out,'annual_progress.json'),progress_record(false,run_label,month_receipts,toc(started)));
    fprintf('REPAIR_YEAR month%02d complete source%d qualified%d physical%d exceptions%d %.1fs\n',mon,mr.source_qualified,mr.policy_equation_qualified,mr.full_operating_qualified,mr.solver_exceptions,mr.elapsed_seconds);
end
assert(isequal(records,collect_source_records(root,setup,annual,candidate_path)),'nyrepair:SourceChanged','Replay input or numerical code changed during this attempt.');
q=vertcat(quality{:});q=sortrows(q,'hour_index');assert(isequal(q.hour_index,(1:8760)')&&isequal(logical(q.PF_attempted),source_qualified));
writetable(q,fullfile(out,'annual_hour_quality.csv'));
good=logical(q.qualified);report=progress_record(true,run_label,month_receipts,toc(started));
report.replay_integrity_passed=sum(q.PF_attempted)==8651;report.source_files_unchanged_during_replay=true;report.source_records=records;
report.all_8760_clock_rows_exported=true;report.source_qualified_hours=8651;report.frozen_current_baseline_qualified_hours=8170;
report.paired_current_baseline_hours=nnz(current_baseline_qualified&good);report.new_success_hours=find(source_qualified&~current_baseline_qualified&good);
report.lost_current_success_hours=find(current_baseline_qualified&~good);report.rejected_source_hours=find(source_qualified&~good);
report.candidate_sha256=nylatest_file_sha256(candidate_path);report.options=options;report.generator_count=ng;report.canonical_bus_count=nb;report.canonical_branch_count=nl;
report.native_voltage_solver_unknowns_retained_bus_count=148;report.no_full_network_Newton_used=true;report.OPF_or_observation_fitting_used=false;
report.failed_or_partial_iterates_retained_and_flagged=true;report.full_physical_qualification_separate_from_accounting=true;report.global_infeasibility_not_inferred_from_failed_iterations=true;
report.outputs=[file_record(axesfile),file_record(networkfile),file_record(fullfile(out,'annual_hour_quality.csv'))];
write_json(fullfile(out,'annual_receipt.json'),report);write_json(fullfile(out,'annual_progress.json'),report);
fprintf('REPAIR_YEAR_COMPLETE source8651 qualified%d paired%d exceptions%d elapsed%.1fs\n',nnz(good),report.paired_current_baseline_hours,nnz(q.solver_exception),report.elapsed_seconds);
end

function r=progress_record(complete,label,months,elapsed)
r=struct('completed',complete,'run_label',label,'months_complete',numel(months),'attempted_hours',sum([months.PF_attempted]), ...
    'PF_converged_hours',sum([months.PF_converged]),'policy_equation_qualified_hours',sum([months.policy_equation_qualified]), ...
    'VQ_and_generator_assumption_qualified_hours',sum([months.VQ_qualified]),'full_operating_qualified_hours',sum([months.full_operating_qualified]), ...
    'solver_exceptions',sum([months.solver_exceptions]),'elapsed_seconds',elapsed,'months',months);
end

function records=collect_source_records(root,setup,annual,candidate)
paths={candidate,fullfile(annual,'replay_contract.json'),fullfile(annual,'frozen_baseline_axes.mat'),[mfilename('fullpath'),'.m']};
paths{end+1}=fullfile(root,'output','nygrid_2025_physical_repair','physics','parent41_parameters.json');
for folder={setup.runtime_root,fullfile(root,'scripts','nygrid_2025_physical_repair','core')}
    items=dir(fullfile(folder{1},'**','*.m'));for k=1:numel(items),paths{end+1}=fullfile(items(k).folder,items(k).name);end %#ok<AGROW>
end
physics=fullfile(root,'scripts','nygrid_2025_physical_repair','physics','nyrepair_apply_185195.m');
assert(isfile(physics));paths{end+1}=physics;
model=fullfile(annual,'baseline_bundle','model');
for name={'latest_model.mat','profiles_h0001_4380.mat','profiles_h4381_8760.mat','model_receipt.json'},paths{end+1}=fullfile(model,name{1});end %#ok<AGROW>
for folder={'lib','mips/lib','mp-opt-model/lib','mptest/lib'}
    items=dir(fullfile(setup.matpower_root,folder{1},'**','*.m'));for k=1:numel(items),paths{end+1}=fullfile(items(k).folder,items(k).name);end %#ok<AGROW>
end
paths=sort(unique(paths));records=struct('path',{},'sha256',{},'bytes',{});
for k=1:numel(paths),records(end+1)=file_record(paths{k});end %#ok<AGROW>
end

function r=file_record(path)
item=dir(path);assert(isscalar(item)&&~item.isdir);r=struct('path',path,'sha256',nylatest_file_sha256(path),'bytes',item.bytes);
end

function limits=current_limits(m)
limits=struct('kind',{},'branch_row',{},'from_A',{},'to_A',{});
for name={'terminal_current_limits','conductor_section_end_current_limits','cable_section_static_current_limits'}
    if ~isfield(m.userdata.ac_system,name{1}),continue;end
    t=m.userdata.ac_system.(name{1});
    limits(end+1)=struct('kind',name{1},'branch_row',t.branch_row, ...
        'from_A',t.total_terminal_current_limit_from_a,'to_A',t.total_terminal_current_limit_to_a); %#ok<AGROW>
end
end

function write_json(path,value)
tmp=[path,'.tmp'];fid=fopen(tmp,'w');assert(fid>=0);fprintf(fid,'%s\n',jsonencode(value,'PrettyPrint',true));fclose(fid);
[ok,message]=movefile(tmp,path,'f');assert(ok,message);
end
