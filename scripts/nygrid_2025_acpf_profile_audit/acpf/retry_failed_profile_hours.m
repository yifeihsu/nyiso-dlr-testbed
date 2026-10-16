function report=retry_failed_profile_hours()
% Recover numerical starts only. All source P/Q, VG, converter and network data stay fixed.
root=fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
base=fullfile(root,'output','nygrid_2025_acpf_profile_audit','acpf');out=fullfile(base,'NR_recovery');if ~isfolder(out),mkdir(out);end
primary=jsondecode(fileread(fullfile(base,'annual_profile_PF_receipt.json')));assert(primary.completed);
cache=load_profile_cache();canonical=cache.canonical;hours=primary.failed_NR_hours(:);
bus_id=canonical.bus(:,1);branch_keys=canonical.userdata.ac_system.branch_keys(:);nb=numel(bus_id);nl=numel(branch_keys);
available=false(8760,1);year_VM=nan(8760,nb);year_VA=year_VM;
for mon=1:12
    c=load(fullfile(base,'monthly',sprintf('profile_PF_2025_%02d.mat',mon)), ...
        'hour_index','VM','VA','computed_current_available');
    available(c.hour_index)=c.computed_current_available;year_VM(c.hour_index,:)=c.VM;year_VA(c.hour_index,:)=c.VA;
end
assert(all(cache.qualified(hours)&~available(hours)));
% Check public-case equality on failed hours, in addition to the first parity cohort.
parity_hours=hours(unique(round(linspace(1,numel(hours),3))));
for h=parity_hours'
    m=profile_case_from_cache(cache,h);public=npcc_nygrid_2025_ac(h);
    assert(isequal(m.bus,public.bus)&&isequal(m.gen,public.gen)&&isequal(m.branch,public.branch) ...
        &&isequal(m.dcline,public.dcline)&&isequal(m.gencost,public.gencost));
end
opt=mpoption('model','AC','verbose',0,'out.all',0,'pf.alg','NR','pf.nr.max_it',50, ...
    'pf.tol',1e-10,'pf.enforce_q_lims',0,'exp.use_legacy_core',1);
ws=warning;cleanup=onCleanup(@()warning(ws));warning('off','MATLAB:nearlySingularMatrix');warning('off','MATLAB:singularMatrix');
flat=empty_pack(hours,cache,canonical);previous=flat;final=flat;
attempts=cell(2*numel(hours),1);count=0;t=tic;
for j=1:numel(hours)
    h=hours(j);original=profile_case_from_cache(cache,h);last_audit=[];
    for strategy=1:2
        m=original;seed_hour=NaN;
        if strategy==1
            m.bus(:,8)=1;m.bus(:,9)=0;label='flat_initial_PQ_voltage';
        else
            seed_hour=find(available&(1:8760)'<h,1,'last');assert(~isempty(seed_hour));
            [ok,ib]=ismember(m.bus(:,1),bus_id);assert(all(ok));
            v=year_VM(seed_hour,ib)';angle=year_VA(seed_hour,ib)';valid=isfinite(v)&isfinite(angle);
            m.bus(valid,8)=v(valid);m.bus(valid,9)=angle(valid);label='previous_equation_qualified_voltage';
        end
        assert(isequal(m.gen,original.gen)&&isequal(m.dcline,original.dcline)&&isequal(m.branch,original.branch) ...
            &&isequal(m.bus(:,[1:7 10:13]),original.bus(:,[1:7 10:13])));
        [r,~]=runpf(m,opt);[a,detail]=audit_profile_pf(m,r);
        a.retry_strategy=label;a.seed_hour=seed_hour;a.only_initial_VM_VA_changed=true;
        count=count+1;attempts{count}=a;last_audit=a;
        if strategy==1,flat=store_point(flat,j,m,r,a,detail,seed_hour);else,previous=store_point(previous,j,m,r,a,detail,seed_hour);end
        final=store_point(final,j,m,r,a,detail,seed_hour);final.selected_strategy{j}=label;
        if a.computed_current_available
            [~,ib]=ismember(m.bus(:,1),bus_id);available(h)=true;year_VM(h,ib)=r.bus(:,8);year_VA(h,ib)=r.bus(:,9);break;
        end
    end
    if mod(j,25)==0||j==numel(hours)
        fprintf('PROFILE_RECOVERY done%d/%d recovered%d last_hour%d last_success%d %.1fs\n',j,numel(hours),nnz(final.computed_current_available),h,last_audit.PF_converged,toc(t));
    end
end
save(fullfile(out,'flat_initialization_attempts.mat'),'-struct','flat','-v7');
save(fullfile(out,'previous_voltage_initialization_attempts.mat'),'-struct','previous','-v7');
save(fullfile(out,'recovery_selected_states.mat'),'-struct','final','-v7');
aa=[attempts{1:count}];writetable(struct2table(aa),fullfile(out,'recovery_attempt_quality.csv'));
report=struct('completed',true,'primary_failed_hours',numel(hours),'public_loader_failed_hour_parity',parity_hours, ...
    'attempts',count,'flat_attempts',nnz(flat.PF_attempted),'flat_recovered',nnz(flat.computed_current_available), ...
    'previous_voltage_attempts',nnz(previous.PF_attempted),'previous_voltage_recovered',nnz(previous.computed_current_available), ...
    'recovered_hours',hours(final.computed_current_available),'remaining_unresolved_hours',hours(~final.computed_current_available), ...
    'recovered_hour_count',nnz(final.computed_current_available),'remaining_unresolved_count',nnz(~final.computed_current_available), ...
    'VQ_and_generator_assumption_qualified_recoveries',nnz(final.VQ_and_generator_assumption_gate), ...
    'primary_outputs_overwritten',false,'source_profiles_controls_or_parameters_changed',false,'OPF_used',false, ...
    'VG_and_converter_voltage_setpoints_preserved',true,'initialization_only',true, ...
    'previous_seed_uses_only_earlier_equation_qualified_profile_PF',true,'global_infeasibility_proved',false,'seconds',toc(t));
fid=fopen(fullfile(out,'NR_recovery_receipt.json'),'w');fprintf(fid,'%s\n',jsonencode(report,'PrettyPrint',true));fclose(fid);
end

function p=empty_pack(hours,cache,canonical)
n=numel(hours);nb=size(canonical.bus,1);nl=size(canonical.branch,1);
p=struct('hour_index',hours,'timestamp_utc',{cache.dispatch.timestamp_utc(hours)},'gamma',cache.dispatch.gamma, ...
    'bus_id',canonical.bus(:,1),'branch_keys',{canonical.userdata.ac_system.branch_keys(:)}, ...
    'branch_parent_row',canonical.userdata.ac_system.branch_parent_row,'branch_from_bus',canonical.branch(:,1),'branch_to_bus',canonical.branch(:,2));
for name={'VM','VA','PD','QD','bus_PG','bus_QG'},p.(name{1})=nan(n,nb);end
for name={'PF','QF','PT','QT','Iseries','Ifrom','Ito'},p.(name{1})=nan(n,nl);end
for name={'DC_PF','DC_PT','DC_QF','DC_QT'},p.(name{1})=nan(n,6);end
for name={'PF_attempted','PF_converged','AC_equation_gate','P_profile_preservation_gate','VQ_and_generator_assumption_gate','computed_current_available'},p.(name{1})=false(n,1);end
p.source_qualified=cache.qualified(hours);p.previous_seed_hour=nan(n,1);p.selected_strategy=repmat({''},n,1);
p.branch_present=false(n,nl);p.branch_active=false(n,nl);p.bus_present=false(n,nb);
end

function p=store_point(p,j,m,r,a,d,seed)
[ok,ib]=ismember(m.bus(:,1),p.bus_id);assert(all(ok));[ok,il]=ismember(string(m.userdata.ac_system.branch_keys),string(p.branch_keys));assert(all(ok));
p.PF_attempted(j)=true;p.previous_seed_hour(j)=seed;
for name={'PF_converged','AC_equation_gate','P_profile_preservation_gate','VQ_and_generator_assumption_gate','computed_current_available'},p.(name{1})(j)=a.(name{1});end
p.VM(j,ib)=r.bus(:,8);p.VA(j,ib)=r.bus(:,9);p.PD(j,ib)=m.bus(:,3);p.QD(j,ib)=m.bus(:,4);p.bus_present(j,ib)=true;
[~,ig]=ismember(r.gen(:,1),p.bus_id);p.bus_PG(j,:)=accumarray(ig,r.gen(:,2),[numel(p.bus_id) 1])';p.bus_QG(j,:)=accumarray(ig,r.gen(:,3),[numel(p.bus_id) 1])';
p.PF(j,il)=r.branch(:,14);p.QF(j,il)=r.branch(:,15);p.PT(j,il)=r.branch(:,16);p.QT(j,il)=r.branch(:,17);
p.Iseries(j,il)=d.series_current_amp;p.Ifrom(j,il)=d.from_terminal_current_amp;p.Ito(j,il)=d.to_terminal_current_amp;
p.branch_present(j,il)=true;p.branch_active(j,il)=m.branch(:,11)>0;
p.DC_PF(j,:)=r.dcline(:,4);p.DC_PT(j,:)=r.dcline(:,5);p.DC_QF(j,:)=r.dcline(:,6);p.DC_QT(j,:)=r.dcline(:,7);
end
