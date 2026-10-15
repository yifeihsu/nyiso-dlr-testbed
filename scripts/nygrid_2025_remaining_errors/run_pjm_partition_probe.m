function run_pjm_partition_probe()
% A genuine finite-bound direction, following discovery of capacity-share no-ops.
root=fileparts(fileparts(fileparts(mfilename('fullpath'))));out=fullfile(root,'output','nygrid_2025_remaining_errors','probes');
addpath(fullfile(root,'scripts','nygrid_2025_latest_handoff','runtime'));
setup_nygrid_latest(root,'C:/Users/Holiday/OneDrive/Documents/MATLAB/matpower');
input=load(fullfile(out,'probe_inputs.mat'));plan=jsondecode(fileread(fullfile(out,'probe_plan.json')));
supplement=struct('created_utc',char(datetime('now','TimeZone','UTC','Format','yyyy-MM-dd''T''HH:mm:ssXXX')), ...
    'purpose','Sensitivity to PJM spatial generation allocation, not a historical dispatch correction', ...
    'selection','Reuse all15 calendar-selected frozenhours; no residual ranking', ...
    'variant_rule','Transfer100publicMW between external generator buses130 and134 in both directions; keep original PJM lossweights; reject finite-bound violations', ...
    'topological_basis','Bus134 directly touches NY zoneC via parent79; bus130 is connected to bus124 at the zoneG parent90 landing. These are proxy locations, not certified historical generators.', ...
    'held_fixed','All regional baselinePGtotals, nativePG,HQ,load,sixDC/PARtargets and all admittances', ...
    'new_annual_model_candidate',false);
path=fullfile(out,'pjm_partition_plan.json');
if isfile(path)
    prior=jsondecode(fileread(path));assert(isequal(rmfield(prior,'created_utc'),rmfield(supplement,'created_utc')),'probe:PlanChanged','Frozen supplement differs.');
else
    fid=fopen(path,'w');fprintf(fid,'%s\n',jsonencode(supplement,'PrettyPrint',true));fclose(fid);
end
ops=readtable(fullfile(root,'output','nygrid_2025_acpf_profile_audit','alignment','interface_operator_terms.csv'),'TextType','string');
states=["pre_may","may21","may30","post_dover"];variants=["pjm_130_to134_100MW","pjm_134_to130_100MW"];rows=struct([]);
for i=1:numel(input.hour_index)
    h=input.hour_index(i);base=load_nygrid_latest(h);p=nylatest_prepare_policy(base);
    r130=find(base.gen(:,1)==130&p.external_gen_group==14);r134=find(base.gen(:,1)==134&p.external_gen_group==14);assert(isscalar(r130)&&isscalar(r134));
    terms=ops(ops.state==states(base.userdata.latest_runtime.state_index),:);assert(height(terms)==34);
    for j=1:2
        m=base;delta=100*input.gamma*(3-2*j);m.gen(r130,2)=m.gen(r130,2)-delta;m.gen(r134,2)=m.gen(r134,2)+delta;
        row=struct('hour_index',h,'variant',variants(j),'qualified',false,'status',"not_run",'maximum_flow_response_public_MW',NaN, ...
            'PJM_PG_conservation_model_MW',sum(m.gen(p.external_gen_group==14,2)-base.gen(p.external_gen_group==14,2)), ...
            'max_regional_import_residual_model_MW',NaN,'max_voltage_bound_violation_pu',NaN,'max_Q_bound_violation_model_MVAr',NaN);
        for c=1:7,row.(sprintf('flow_%d_public_MW',c))=NaN;end
        try
            assert(all(m.gen(:,2)>=p.Pmin-1e-8&m.gen(:,2)<=p.Pmax+1e-8),'probe:Infeasible','Redistribution exceeds finite original P bounds.');
            assert(abs(row.PJM_PG_conservation_model_MW)<1e-8&&isequal(m.gen(p.native,2),base.gen(p.native,2)));
            m.gen([r130 r134],9:10)=repmat(m.gen([r130 r134],2),1,2);
            m.userdata.ac_system.generator_p_reference=m.gen(:,2);
            external=m.userdata.ac_system.external_generator_mask;qc=m.userdata.ac_system.generator_q_cap;
            qc(external)=sqrt(max(0,m.userdata.ac_system.generator_assumed_s_cap(external).^2-m.gen(external,2).^2));
            m.userdata.ac_system.generator_q_cap=qc;m.gen(external,4)=qc(external);m.gen(external,5)=-qc(external);
            [~,a,r]=nylatest_coupled_solve(m);row.qualified=a.loss_allocation_gate&&a.reduction_and_equation_gate;row.status=string(a.loss_status);
            row.max_regional_import_residual_model_MW=a.regional_NY_import_residual_MW;row.max_voltage_bound_violation_pu=a.max_voltage_bound_violation_pu;row.max_Q_bound_violation_model_MVAr=a.max_Q_bound_violation_mvar;
            if row.qualified
                for c=1:7
                    term=terms(terms.interface_index==c,:);assert(~isempty(term)&&all(p.parent(term.first_runtime_branch_row)==term.original_branch_row));
                    row.(sprintf('flow_%d_public_MW',c))=sum(term.coefficient.*r.branch(term.first_runtime_branch_row,14))/input.gamma;
                end
            end
        catch err,row.status=string(err.identifier)+": "+string(err.message);end
        rows=[rows;row]; %#ok<AGROW>
        fprintf('PJMprobe hour%d %s qualified%d\n',h,variants(j),row.qualified);
    end
    writetable(struct2table(rows),fullfile(out,'pjm_partition_results.csv'));
end
end
