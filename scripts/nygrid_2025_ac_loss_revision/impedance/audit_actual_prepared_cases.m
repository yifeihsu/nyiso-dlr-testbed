function report=audit_actual_prepared_cases()
% Independent actual-builder audit. No PF, OPF or baseline mutation.
root=fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
addpath(fullfile(root,'System Matpower Format'));
addpath(fullfile(root,'scripts','nygrid_2025_ac_loss_revision','core'));
addpath(fullfile(root,'scripts','nygrid_2025_ac_system','thermal'));
out=fullfile(root,'output','nygrid_2025_ac_loss_revision','impedance');
folder=fullfile(out,'actual_case_checks');if ~isfolder(folder),mkdir(folder);end
recommendation_file=fullfile(out,'impedance_recommendation.json');
recommendation=jsondecode(fileread(recommendation_file));assert(recommendation.passed);
target=reshape(recommendation.accepted_R_X_B_pu,1,3);assert(isequal(target,[.02 .0147 0]));
core=fullfile(root,'scripts','nygrid_2025_ac_loss_revision','core','ac_loss_prepare_case.m');
initial_hash=file_sha256(core);hours=[1 3360 3576 8472 8508];checks=struct([]);artifacts=struct([]);
conductors=readtable(fullfile(root,'output','nygrid_2025_ac_system','engineering','thermal_conductors.csv'),'TextType','string');
for h=hours
    before=npcc_nygrid_2025_ac(h);
    frozen_file=fullfile(root,'output','nygrid_2025_compact_ac','models',sprintf('compact_ac_h%04d.mat',h));
    frozen=load(frozen_file,'model');reference=frozen.model.detailed_mpc;
    for name={'bus','branch','gen','dcline','gencost'}
        assert(isequaln(before.(name{1}),reference.(name{1})),'independent:SourceDrift','Current public input differs from frozen detailed input.');
    end
    after=ac_loss_prepare_case(before);
    parents=before.userdata.ac_system.branch_parent_row(:);rows=find(parents==224);other=find(parents~=224);
    assert(numel(rows)==2&&before.branch(rows(1),1)==38&&before.branch(rows(end),2)==77);
    assert(isequal(after.branch(rows,3:5),repmat(target/2,2,1)));
    assert(isequal(after.branch(other,:),before.branch(other,:)));
    assert(isequal(after.branch(:,[1 2 9:13]),before.branch(:,[1 2 9:13])));
    assert(all(after.branch(rows,6:8)==0,'all'));
    for name={'bus','gen','dcline','gencost'}
        assert(isequaln(after.(name{1}),before.(name{1})),'independent:UnlistedMutation','Unexpected bus/device/cost mutation.');
    end
    assert(isequal(after.branch(parents==225,:),before.branch(parents==225,:)));
    assert(isequal(after.userdata.ac_system.branch_keys,before.userdata.ac_system.branch_keys));
    assert(isequal(after.userdata.ac_system.branch_parent_row,parents));
    assert(isequaln(after.userdata.ac_sections.reactor_ledger,before.userdata.ac_sections.reactor_ledger));
    assert(isequaln(after.userdata.ac_sections.reactor_BS_delta,before.userdata.ac_sections.reactor_BS_delta));
    assert(~any([before.userdata.ac_sections.reactor_ledger.original_branch_row]==224));
    assert(after.userdata.ac_loss_revision.parent224_reactor_removed_MVAr==0);
    assert(after.userdata.ac_loss_revision.parent224_is_released_network_equivalent);
    assert(~after.userdata.ac_loss_revision.parent224_physical_impedance_validated ...
        &&~after.userdata.ac_loss_revision.parent224_conductor_DLR_eligible ...
        &&~after.userdata.ac_loss_revision.parent224_temperature_resistance_update_allowed ...
        &&~after.userdata.ac_loss_revision.OPF_supported);
    oldts=before.userdata.ac_system.thermal_segments;newts=after.userdata.ac_system.thermal_segments;
    assert(istable(newts)&&~any(ismember(newts.branch_row,rows)));
    assert(isequaln(newts,oldts(~ismember(oldts.branch_row,rows),:)));
    section_rows_before=thermal_rows(before.userdata.ac_sections.thermal_segments);
    section_rows_after=thermal_rows(after.userdata.ac_sections.thermal_segments);
    assert(~any(ismember(section_rows_after,rows)) ...
        &&isequal(section_rows_after,section_rows_before(~ismember(section_rows_before,rows))));
    for key={'terminal_current_limits','conductor_section_end_current_limits','cable_section_static_current_limits'}
        if isfield(before.userdata.ac_system,key{1})
            old=before.userdata.ac_system.(key{1});new=after.userdata.ac_system.(key{1});
            assert(isequaln(new,old(~ismember(old.branch_row,rows),:)));
            assert(~any(ismember(new.branch_row,rows)));
        end
    end
    assert(all(isnan(after.userdata.ac_sections.terminal_current_limit_A(rows,:)),'all'));
    assert(isequaln(after.userdata.ac_sections.terminal_current_limit_A(other,:), ...
        before.userdata.ac_sections.terminal_current_limit_A(other,:)));
    assert(~after.userdata.ac_system.terminal_current_constraints_applied ...
        &&~after.userdata.ac_system.thermal_constraints_applied);
    assert(~isfield(after.userfcn,'formulation'));
    expected_fcn=before.userfcn;if isfield(expected_fcn,'formulation'),expected_fcn=rmfield(expected_fcn,'formulation');end
    assert(isequaln(after.userfcn,expected_fcn)); % Keep dcline conversion/recovery callbacks.
    % The ordinary resistance updater has no remaining segment record for224.
    temperature_updated=ac_dlr_apply_resistance(after,newts,conductors,newts.reference_temperature_c);
    assert(isequal(temperature_updated.branch(rows,3),after.branch(rows,3)));
    double_guard=false;try,ac_loss_prepare_case(after);catch err,double_guard=strcmp(err.identifier,'acLoss:AlreadyApplied');end
    thermal_input=before;thermal_input.userdata.ac_dlr=struct('branch_rows',rows);
    thermal_guard=false;try,ac_loss_prepare_case(thermal_input);catch err,thermal_guard=strcmp(err.identifier,'acLoss:ThermalPreparedInput');end
    assert(double_guard&&thermal_guard);
    legacy=ac_loss_prepare_case(before,'legacy_engineering');
    for name={'bus','branch','gen','dcline','gencost','userfcn'}
        assert(isequaln(legacy.(name{1}),before.(name{1})));
    end
    % Independent complex-series elimination of the retained numerical tap.
    sections=after.branch(rows,:);ids=unique(sections(:,1:2));Y=zeros(numel(ids));
    for j=1:2
        f=find(ids==sections(j,1));t=find(ids==sections(j,2));y=1/complex(sections(j,3),sections(j,4));
        Y(f,f)=Y(f,f)+y;Y(t,t)=Y(t,t)+y;Y(f,t)=Y(f,t)-y;Y(t,f)=Y(t,f)-y;
    end
    [ok,k]=ismember([38;77],ids);assert(all(ok));e=setdiff((1:numel(ids))',k);
    reduced=Y(k,k)-Y(k,e)*(Y(e,e)\Y(e,k));expected=[1 -1;-1 1]/complex(target(1),target(2));
    schur_error=max(abs(reduced-expected),[],'all');assert(schur_error<1e-12);
    before_bus=before.bus;after_bus=after.bus;before_branch=before.branch;after_branch=after.branch; %#ok<NASGU>
    before_gen=before.gen;after_gen=after.gen;before_dcline=before.dcline;after_dcline=after.dcline; %#ok<NASGU>
    savefile=fullfile(folder,sprintf('prepared_h%04d_numeric.mat',h));
    save(savefile,'h','before_bus','after_bus','before_branch','after_branch','before_gen','after_gen', ...
        'before_dcline','after_dcline','parents','rows','section_rows_before','section_rows_after','schur_error');
    artifacts=[artifacts rec(root,savefile)]; %#ok<AGROW>
    c=struct('hour_index',h,'full_bus_count',size(after.bus,1),'full_branch_count',size(after.branch,1), ...
        'parent224_runtime_rows',rows(:)','parent224_R_X_B',sum(after.branch(rows,3:5),1), ...
        'frozen_source_numeric_arrays_match_public_loader',true,'only224_R_X_B_and_unqualified_ratings_changed',true, ...
        'all_bus_gen_dcline_and_cost_arrays_unchanged',true,'all_other_branch_parameters_unchanged',true, ...
        'sibling225_unchanged',true,'bus_shunts_unchanged_no224_reactor_existed',true, ...
        'all224_conductor_and_current_limit_entries_removed',true,'remaining_conductor_rows_preserved',true, ...
        'temperature_resistance_updater_cannot_change224',true,'formulation_callbacks_removed_other_callbacks_preserved',true, ...
        'constraint_applied_flags_cleared',true,'double_application_and_thermal_prepared_inputs_rejected',true, ...
        'legacy_engineering_numeric_mode_unchanged',true,'complex_series_equivalence_error_pu',schur_error,'passed',true);
    checks=[checks c]; %#ok<AGROW>
    fprintf('INDEPENDENT_PREPARE h%d PASS rows%d/%d R%.7g X%.7g B%.7g\n',h,rows(1),rows(2),sum(after.branch(rows,3)),sum(after.branch(rows,4)),sum(after.branch(rows,5)));
end
% Synthetic guard fixture: reverse an explicitly identified224reactor once.
fixture=before;ledger=fixture.userdata.ac_sections.reactor_ledger;z=ledger(1);
z.original_branch_row=224;z.original_corridor_key='PARENT:224';z.from_bus=38;z.to_bus=77;
z.associated_line_active=true;z.applied_total_reactor_mvar_at1pu=24;
z.from_bus_BS_delta_mvar=-12;z.to_bus_BS_delta_mvar=-12;ledger(end+1)=z;
fixture.userdata.ac_sections.reactor_ledger=ledger;[ok,ends]=ismember([38;77],fixture.bus(:,1));assert(all(ok));
fixture.bus(ends,6)=fixture.bus(ends,6)-12;fixture.userdata.ac_sections.reactor_BS_delta(ends)=fixture.userdata.ac_sections.reactor_BS_delta(ends)-12;
clean=ac_loss_prepare_case(fixture);assert(isequal(clean.bus,before.bus));
assert(isequal(clean.userdata.ac_sections.reactor_BS_delta,before.userdata.ac_sections.reactor_BS_delta));
assert(clean.userdata.ac_loss_revision.parent224_reactor_removed_MVAr==24);
assert(isequaln(clean.userdata.ac_sections.reactor_ledger(1:end-1),before.userdata.ac_sections.reactor_ledger));
assert(clean.userdata.ac_sections.reactor_ledger(end).applied_total_reactor_mvar_at1pu==0);
assert(strcmp(initial_hash,file_sha256(core)),'independent:SourceChanged','Builder changed during audit.');
dependencies=[rec(root,core),rec(root,mfilename('fullpath')+".m"),rec(root,recommendation_file), ...
    rec(root,fullfile(root,'System Matpower Format','npcc_nygrid_2025_ac.m')), ...
    rec(root,fullfile(root,'scripts','nygrid_2025_ac_system','thermal','ac_dlr_apply_resistance.m')), ...
    rec(root,fullfile(root,'output','nygrid_2025_ac_system','engineering','thermal_conductors.csv'))];
for h=hours,dependencies(end+1)=rec(root,fullfile(root,'output','nygrid_2025_compact_ac','models',sprintf('compact_ac_h%04d.mat',h)));end %#ok<AGROW>
report=struct('passed',true,'scope','Independent actual ac_loss_prepare_case audit; no PF or OPF run', ...
    'hours',hours,'checks',checks,'optional_reactor_reversal_fixture_passed',true, ...
    'physical_impedance_or_operating_feasibility_claimed',false,'baseline_models_changed',false, ...
    'source_hash_stable_during_audit',true,'dependencies',dependencies,'outputs',artifacts);
fid=fopen(fullfile(out,'actual_case_implementation_review.json'),'w');assert(fid>=0);
fprintf(fid,'%s\n',jsonencode(report,'PrettyPrint',true));fclose(fid);
end

function rows=thermal_rows(value)
if istable(value),rows=value.branch_row;
elseif iscell(value),rows=cellfun(@(x)x.branch_row,value);
else,rows=[value.branch_row];end
rows=rows(:);
end
function r=rec(root,path)
path=char(path);r=struct('path',strrep(strrep(path,[root filesep],''),'\','/'),'sha256',file_sha256(path));
end
function digest=file_sha256(path)
engine=java.security.MessageDigest.getInstance('SHA-256');fid=fopen(path,'rb');assert(fid>=0);cleanup=onCleanup(@()fclose(fid));
while ~feof(fid),bytes=fread(fid,1048576,'*uint8');if ~isempty(bytes),engine.update(typecast(bytes,'int8'));end,end
raw=typecast(engine.digest(),'uint8');digest=lower(reshape(dec2hex(raw,2)',1,[]));
end
