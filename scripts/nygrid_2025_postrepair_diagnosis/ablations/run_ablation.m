function report=run_ablation(scenario)
% Compact all-hour diagnostic export; no baseline or source overwrite.
assert(any(strcmp(scenario,{'G','P'})));
[root,out,recipe,setup]=ablation_setup();bridge=jsondecode(fileread(fullfile(out,'bridge_receipt.json')));
assert(bridge.passed&&strcmp(bridge.recipe_sha256,nylatest_file_sha256(fullfile(out,'scenario_recipe.json'))));
run=fullfile(out,[scenario,'_v1']);assert(~isfolder(run),'ablation:PreserveRun','Choose a new version before replacing an existing ablation.');mkdir(run);mkdir(fullfile(run,'monthly'));
source_axes=load(fullfile(out,'source_axes.mat'));[data,~]=nylatest_data();
axes_source=fullfile(root,'output','nygrid_2025_moses_repair','annual','moses_repair_v1','annual_axes.mat');
axes=load(axes_source,'bus_id','base_kv','branch_keys','branch_parent_row','branch_from_bus','branch_to_bus','generator_bus_id','DC_from_bus','DC_to_bus','retained_bus_ids');
source=logical(source_axes.source_qualified(:));state=double(source_axes.topology_state_index(:));months=double(source_axes.model_month(:));
assert(nnz(source)==8651&&isequal(double(source_axes.hour_index(:)),(1:8760)'));
assert(isequal(string(data.axis.timestamp_utc(:)),string(source_axes.timestamp_utc)));
nb=numel(axes.bus_id);nl=numel(axes.branch_keys);ng=numel(axes.generator_bus_id);ndc=numel(axes.DC_from_bus);assert(ng==1466&&ndc==6);
ib=cell(4,1);il=cell(4,1);gb=cell(4,1);
for s=1:4
    m=ablation_load(double(data.axis.template_hours(s)),scenario);
    [ok,ib{s}]=ismember(m.bus(:,1),axes.bus_id);assert(all(ok));
    [ok,il{s}]=ismember(string(m.userdata.ac_system.branch_keys(:)),string(axes.branch_keys(:)));assert(all(ok));
    [ok,gb{s}]=ismember(m.gen(:,1),axes.bus_id);assert(all(ok));
end
records=collect_records(root,out,setup,axes_source);started=tic;
save(fullfile(run,'axes.mat'),'-struct','axes','-v7');
options=struct('backend','compact','loss_mode','boundary_consistent');
flags={'PF_converged','AC_equation_gate','loss_allocation_gate','reduction_and_equation_gate','VQ_and_generator_assumption_gate','full_operating_gate'};
scalars={'max_nodal_P_residual_mw','max_nodal_Q_residual_mvar','regional_NY_import_residual_MW','max_voltage_bound_violation_pu', ...
    'max_Q_bound_violation_mvar','max_assumed_generator_S_bound_violation_mva','max_equipment_MVA_violation','fixed_boundary_P_change_MW','fixed_boundary_Q_MVAr'};
month_receipts=struct([]);quality=cell(12,1);samples=struct([]);
for mon=1:12
    hh=find(months==mon);nh=numel(hh);tm=tic;
    chunk=struct('scenario',scenario,'hour_index',hh,'topology_state_index',state(hh),'gamma',double(source_axes.gamma), ...
        'source_qualified',source(hh),'PF_attempted',false(nh,1),'qualified',false(nh,1),'solver_exception',false(nh,1));
    chunk.loss_status=repmat({'source_excluded'},nh,1);chunk.exception_identifier=repmat({''},nh,1);
    for name={'VM','VA','PD','QD','bus_PG','bus_QG'},chunk.(name{1})=nan(nh,nb);end
    for name={'PF','QF','PT','QT','branch_SHIFT'},chunk.(name{1})=nan(nh,nl);end
    chunk.gen_PG=nan(nh,ng);chunk.fixed_boundary_QG=nan(nh,1);
    for name={'DC_PF','DC_PT','DC_QF','DC_QT'},chunk.(name{1})=nan(nh,ndc);end
    chunk.NY_gross_target_MW=nan(nh,11);chunk.NY_served_PD_MW=nan(nh,11);chunk.actual_budget_MW=nan(nh,14);
    chunk.regional_import_target_MW=nan(nh,3);chunk.regional_import_solved_MW=nan(nh,3);chunk.external_PG_increment_MW=nan(nh,3);
    chunk.retained_VM=nan(nh,148);chunk.retained_VA=nan(nh,148);
    for name=flags,chunk.(name{1})=false(nh,1);end
    for name=scalars,chunk.(name{1})=nan(nh,1);end
    for j=1:nh
        h=hh(j);if ~source(h),continue;end
        chunk.PF_attempted(j)=true;
        try
            [base,meta]=ablation_load(h,scenario);s=state(h);
            [c,a,r,allocation]=nylatest_coupled_solve(base,options);m=allocation.final_input;a.full_operating_gate=a.passed;
            for name=flags,chunk.(name{1})(j)=a.(name{1});end
            for name=scalars,chunk.(name{1})(j)=a.(name{1});end
            chunk.qualified(j)=a.PF_converged&&a.AC_equation_gate&&a.loss_allocation_gate&&a.reduction_and_equation_gate;
            chunk.loss_status{j}=a.loss_status;
            chunk.VM(j,ib{s})=r.bus(:,8);chunk.VA(j,ib{s})=r.bus(:,9);chunk.PD(j,ib{s})=m.bus(:,3);chunk.QD(j,ib{s})=m.bus(:,4);
            chunk.bus_PG(j,:)=accumarray(gb{s},r.gen(:,2),[nb 1]);chunk.bus_QG(j,:)=accumarray(gb{s},r.gen(:,3),[nb 1]);
            chunk.PF(j,il{s})=r.branch(:,14);chunk.QF(j,il{s})=r.branch(:,15);chunk.PT(j,il{s})=r.branch(:,16);chunk.QT(j,il{s})=r.branch(:,17);
            chunk.branch_SHIFT(j,il{s})=m.branch(:,10);chunk.gen_PG(j,:)=r.gen(:,2);chunk.fixed_boundary_QG(j)=r.gen(1466,3);
            chunk.DC_PF(j,:)=r.dcline(:,4);chunk.DC_PT(j,:)=r.dcline(:,5);chunk.DC_QF(j,:)=r.dcline(:,6);chunk.DC_QT(j,:)=r.dcline(:,7);
            chunk.NY_gross_target_MW(j,:)=allocation.NY_gross_target_MW;chunk.NY_served_PD_MW(j,:)=allocation.NY_served_PD_MW;
            chunk.actual_budget_MW(j,:)=allocation.actual_budget_MW;chunk.regional_import_target_MW(j,:)=allocation.regional_import_target_MW;
            chunk.regional_import_solved_MW(j,:)=allocation.regional_import_solved_MW;chunk.external_PG_increment_MW(j,:)=allocation.external_PG_increment_MW;
            chunk.retained_VM(j,:)=c.bus(:,8);chunk.retained_VA(j,:)=c.bus(:,9);
            if ismember(h,double(recipe.source_selected_bridge_hours))
                samples=[samples;struct('hour_index',h,'input',base,'final_input',m,'result',r,'allocation',allocation,'metadata',meta)]; %#ok<AGROW>
            end
        catch err
            if ~strcmp(err.identifier,'acLoss:NoAdmissibleState'),rethrow(err);end
            chunk.solver_exception(j)=true;chunk.loss_status{j}=['exception:',err.identifier];chunk.exception_identifier{j}=err.identifier;
            fprintf('ABLATION_%s failed h%d: %s\n',scenario,h,err.message);
        end
        if mod(j,250)==0,fprintf('ABLATION_%s month%02d position%d/%d qualified%d\n',scenario,mon,j,nh,nnz(chunk.qualified));end
    end
    path=fullfile(run,'monthly',sprintf('ablation_%02d.mat',mon));save(path,'-struct','chunk','-v7');
    qt=table(hh,source(hh),chunk.PF_attempted,chunk.qualified,chunk.solver_exception,string(chunk.loss_status), ...
        'VariableNames',{'hour_index','source_qualified','PF_attempted','qualified','solver_exception','loss_status'});
    for name=[flags scalars],qt.(name{1})=chunk.(name{1});end
    quality{mon}=qt;
    mr=struct('month',mon,'completed',true,'source_qualified',nnz(source(hh)),'qualified',nnz(chunk.qualified), ...
        'full_operating_qualified',nnz(chunk.full_operating_gate),'solver_exceptions',nnz(chunk.solver_exception),'elapsed_seconds',toc(tm),'output',record(path));
    month_receipts=[month_receipts;mr]; %#ok<AGROW>
    progress=struct('scenario',scenario,'completed',false,'months_complete',mon,'qualified_hours',sum([month_receipts.qualified]),'months',month_receipts);
    write_json(fullfile(run,'progress.json'),progress);
    fprintf('ABLATION_%s month%02d complete %d/%d qualified %.1fs\n',scenario,mon,mr.qualified,mr.source_qualified,mr.elapsed_seconds);
end
assert(isequal(records,collect_records(root,out,setup,axes_source)),'ablation:ChangedSource','A source or numerical implementation changed during replay.');
q=sortrows(vertcat(quality{:}),'hour_index');assert(isequal(q.hour_index,(1:8760)')&&isequal(q.PF_attempted,source));
writetable(q,fullfile(run,'hour_quality.csv'));save(fullfile(run,'sample_results.mat'),'samples','-v7');
report=struct('completed',true,'scenario',scenario,'months_complete',12,'source_qualified_hours',nnz(source),'qualified_hours',nnz(q.qualified), ...
    'solver_exceptions',nnz(q.solver_exception),'VQ_qualified_hours',nnz(q.VQ_and_generator_assumption_gate),'full_operating_qualified_hours',nnz(q.full_operating_gate), ...
    'all8760_clock_rows_retained',true,'source_files_unchanged',true,'new_source_qualification',false,'elapsed_seconds',toc(started), ...
    'recipe_sha256',nylatest_file_sha256(fullfile(out,'scenario_recipe.json')),'source_records',records,'months',month_receipts, ...
    'outputs',[record(fullfile(run,'axes.mat')),record(fullfile(run,'hour_quality.csv')),record(fullfile(run,'sample_results.mat'))]);
write_json(fullfile(run,'annual_receipt.json'),report);disp(report);
end

function records=collect_records(root,out,setup,axes_source)
recipe=jsondecode(fileread(fullfile(out,'scenario_recipe.json')));paths=cell(numel(recipe.inputs),1);
for k=1:numel(paths),paths{k}=fullfile(root,recipe.inputs(k).path);end
paths=[paths;{fullfile(out,'scenario_recipe.json');fullfile(out,'source_axes.mat');fullfile(out,'bridge_receipt.json');axes_source}];
folder=fileparts(mfilename('fullpath'));items=dir(fullfile(folder,'*.m'));
for k=1:numel(items),paths{end+1}=fullfile(items(k).folder,items(k).name);end
for folder={'lib','mips/lib','mp-opt-model/lib','mptest/lib'}
    items=dir(fullfile(setup.matpower_root,folder{1},'**','*.m'));for k=1:numel(items),paths{end+1}=fullfile(items(k).folder,items(k).name);end %#ok<AGROW>
end
paths=sort(unique(paths));records=struct('path',{},'sha256',{},'bytes',{});
for k=1:numel(paths),records(end+1)=record(paths{k});end %#ok<AGROW>
end
function r=record(path)
d=dir(path);assert(isscalar(d));r=struct('path',path,'sha256',nylatest_file_sha256(path),'bytes',d.bytes);
end
function write_json(path,value)
fid=fopen(path,'w');assert(fid>=0);fprintf(fid,'%s\n',jsonencode(value,'PrettyPrint',true));fclose(fid);
end
