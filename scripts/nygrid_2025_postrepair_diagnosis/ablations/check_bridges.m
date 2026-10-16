function receipt=check_bridges()
[root,out,recipe,setup]=ablation_setup();hours=double(recipe.source_selected_bridge_hours(:));assert(numel(hours)==12);
rows=struct([]);sample=struct([]);
for k=1:numel(hours)
    h=hours(k);
    for scenario={'B','GP'}
        label=scenario{1};[m,meta]=ablation_load(h,label);[~,a,r,allocation]=nylatest_coupled_solve(m);
        assert(a.PF_converged&&a.AC_equation_gate&&a.loss_allocation_gate&&a.reduction_and_equation_gate);
        if strcmp(label,'B'),run=fullfile(root,'output','nygrid_2025_physical_repair','annual','physical_repair_v1');
        else,run=fullfile(root,'output','nygrid_2025_moses_repair','annual','moses_repair_v1');end
        path=fullfile(run,'monthly',sprintf('profile_PF_2025_%02d.mat',k));
        d=load(path,'hour_index','bus_id','branch_keys','VM','VA','PF','QF','PT','QT','gen_PG','gen_QG','gen_Pmin','gen_Pmax','gen_Qmin','gen_Qmax','gen_S_cap','gen_status','regional_import_target_MW');
        j=find(d.hour_index==h);assert(isscalar(j));[ok,ib]=ismember(m.bus(:,1),d.bus_id);assert(all(ok));
        keys=cellstr(string(m.userdata.ac_system.branch_keys));[ok,il]=ismember(keys,d.branch_keys);assert(all(ok));
        v=r.bus(:,8).*exp(1j*deg2rad(r.bus(:,9)));oldv=d.VM(j,ib)'.*exp(1j*deg2rad(d.VA(j,ib)'));
        verr=max(abs(v-oldv));pqerr=max(abs(r.branch(:,14:17)-[d.PF(j,il)',d.QF(j,il)',d.PT(j,il)',d.QT(j,il)']),[],'all');
        n=size(d.gen_PG,2);generr=max(abs(r.gen(1:n,2:3)-[d.gen_PG(j,:)',d.gen_QG(j,:)']),[],'all');
        f=allocation.final_input;caperr=max(abs([f.gen(1:n,10),f.gen(1:n,9),f.gen(1:n,5),f.gen(1:n,4),f.userdata.ac_system.generator_assumed_s_cap(1:n)] ...
            -[d.gen_Pmin(j,:)',d.gen_Pmax(j,:)',d.gen_Qmin(j,:)',d.gen_Qmax(j,:)',d.gen_S_cap(j,:)']),[],'all');
        assert(isequal(f.gen(1:n,8)>0,d.gen_status(j,:)'));
        targeterr=max(abs(allocation.regional_import_target_MW-d.regional_import_target_MW(j,:)'));
        assert(verr<1e-8&&pqerr<1e-5&&generr<1e-5&&caperr<1e-7&&targeterr<1e-7,'ablation:Bridge','Bridge mismatch %s h%d',label,h);
        rows=[rows;struct('scenario',label,'month',k,'hour_index',h,'state_index',m.userdata.latest_runtime.state_index, ...
            'complex_voltage_error_pu',verr,'branch_PQ_error_MVA',pqerr,'generator_PQ_error_MVA',generr,'capability_error',caperr,'regional_target_error_MW',targeterr)]; %#ok<AGROW>
        sample=[sample;struct('scenario',label,'hour_index',h,'input',m,'result',r,'allocation',allocation,'metadata',meta)]; %#ok<AGROW>
    end
    for scenario={'G','P'}
        [m,meta]=ablation_load(h,scenario{1});sample=[sample;struct('scenario',scenario{1},'hour_index',h,'input',m,'result',[],'allocation',[],'metadata',meta)]; %#ok<AGROW>
    end
    fprintf('ABLATION_BRIDGE month%02d h%d passed\n',k,h);
end
path=fullfile(out,'bridge_samples.mat');save(path,'sample','-v7');writetable(struct2table(rows),fullfile(out,'bridge_comparison.csv'));
receipt=struct('passed',true,'bridged_scenarios',{{'B','GP'}},'source_selected_hours',hours','comparisons',numel(rows), ...
    'sample_input_scenarios',{{'B','G','P','GP'}},'no_interface_observations_read',true,'max_complex_voltage_error_pu',max([rows.complex_voltage_error_pu]), ...
    'max_branch_PQ_error_MVA',max([rows.branch_PQ_error_MVA]),'max_capability_error',max([rows.capability_error]), ...
    'recipe_sha256',nylatest_file_sha256(fullfile(out,'scenario_recipe.json')),'samples_sha256',nylatest_file_sha256(path),'setup',setup);
fid=fopen(fullfile(out,'bridge_receipt.json'),'w');assert(fid>=0);fprintf(fid,'%s\n',jsonencode(receipt,'PrettyPrint',true));fclose(fid);
disp('ABLATION_BRIDGES_PASS');
end
