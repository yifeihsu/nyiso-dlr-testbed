function run_probes()
% Bounded diagnostic interventions on copies of the sealed current model.
root=fileparts(fileparts(fileparts(mfilename('fullpath'))));
out=fullfile(root,'output','nygrid_2025_remaining_errors','probes');
addpath(fullfile(root,'scripts','nygrid_2025_latest_handoff','runtime'));
setup=setup_nygrid_latest(root,'C:/Users/Holiday/OneDrive/Documents/MATLAB/matpower');
input=load(fullfile(out,'probe_inputs.mat'));plan=jsondecode(fileread(fullfile(out,'probe_plan.json')));
ops=readtable(fullfile(root,'output','nygrid_2025_acpf_profile_audit','alignment','interface_operator_terms.csv'),'TextType','string');
variants=string(plan.variants);hours=input.hour_index(:);nh=numel(hours);nv=numel(variants);
flows=nan(nh,nv,7);losses=nan(nh,nv,14);parent_losses=nan(nh,nv,2);audits=struct([]);
for i=1:nh
    base=load_nygrid_latest(hours(i));assert(max(abs(base.gen(:,2)-input.baseline_PG(i,:)'))<1e-9);
    p=nylatest_prepare_policy(base);pjm=find(p.external_gen_group==14);
    operator_states=["pre_may","may21","may30","post_dover"];
    s=base.userdata.latest_runtime.state_index;assert(s==plan.samples(i).state_index);
    terms=ops(ops.state==operator_states(s),:);
    assert(height(terms)==34&&isequal(unique(terms.interface_index),(1:7)'));
    assert(all(p.parent(terms.first_runtime_branch_row)==terms.original_branch_row));
    for j=1:nv
        m=base;v=variants(j);row=struct('hour_index',hours(i),'variant',v,'qualified',false,'status',"not_run", ...
            'nodal_P_residual_model_MW',NaN,'nodal_Q_residual_model_MVAr',NaN,'regional_import_residual_model_MW',NaN, ...
            'voltage_bound_violation_pu',NaN,'Q_bound_violation_model_MVAr',NaN,'maximum_NY_zonal_loss_fraction',NaN, ...
            'native_PG_sum_change_model_MW',0,'PJM_baseline_PG_sum_change_model_MW',0,'operating_qualified',false,'elapsed_seconds',NaN);
        try
            if j>=2&&j<=5
                assert(input.hydro_feasible(i,j-1),'probe:Infeasible','Hydro redistribution violates aggregate finite capability.');
                m.gen(:,2)=reshape(input.hydro_PG(i,j-1,:),[],1);
            elseif any(j==[6,8])
                cap=p.Pmax(pjm)-p.Pmin(pjm);frac=(sum(p.baseline_PG(pjm))-sum(p.Pmin(pjm)))/sum(cap);
                assert(frac>=0&&frac<=1);m.gen(pjm,2)=p.Pmin(pjm)+frac*cap;
                m.gen(pjm,9:10)=repmat(m.gen(pjm,2),1,2);m.gen(pjm,8)=p.Pmax(pjm)>0;
            elseif j>=9
                k=find(p.parent==41);assert(numel(k)==1);m.branch(k,3:4)=[.0018,.0089];
                if j==10,m.branch(k,5)=.07;end
            end
            if any(j==[7,8])
                m.userdata.latest_runtime.loss_static.generator_share(pjm)=p.Pmax(pjm)/sum(p.Pmax(pjm));
            end
            m.userdata.ac_system.generator_p_reference=m.gen(:,2);
            external=m.userdata.ac_system.external_generator_mask;
            qc=m.userdata.ac_system.generator_q_cap;
            qc(external)=sqrt(max(0,m.userdata.ac_system.generator_assumed_s_cap(external).^2-m.gen(external,2).^2));
            m.userdata.ac_system.generator_q_cap=qc;m.gen(external,4)=qc(external);m.gen(external,5)=-qc(external);
            row.native_PG_sum_change_model_MW=sum(m.gen(p.native,2)-base.gen(p.native,2));
            row.PJM_baseline_PG_sum_change_model_MW=sum(m.gen(pjm,2)-base.gen(pjm,2));
            assert(abs(row.native_PG_sum_change_model_MW)<1e-8&&abs(row.PJM_baseline_PG_sum_change_model_MW)<1e-8);
            assert(isequal(m.bus,base.bus)&&isequal(m.dcline,base.dcline));
            [~,a,r,allocation]=nylatest_coupled_solve(m);
            row.qualified=a.loss_allocation_gate&&a.reduction_and_equation_gate;row.status=string(a.loss_status);
            row.nodal_P_residual_model_MW=a.max_nodal_P_residual_mw;row.nodal_Q_residual_model_MVAr=a.max_nodal_Q_residual_mvar;
            row.regional_import_residual_model_MW=a.regional_NY_import_residual_MW;
            row.voltage_bound_violation_pu=a.max_voltage_bound_violation_pu;row.Q_bound_violation_model_MVAr=a.max_Q_bound_violation_mvar;
            row.maximum_NY_zonal_loss_fraction=a.maximum_NY_zonal_loss_fraction;row.operating_qualified=a.passed;row.elapsed_seconds=a.elapsed_seconds;
            if row.qualified
                for c=1:7
                    term=terms(terms.interface_index==c,:);assert(~isempty(term));flows(i,j,c)=sum(term.coefficient.*r.branch(term.first_runtime_branch_row,14))/input.gamma;
                end
                losses(i,j,:)=allocation.actual_budget_MW;
                for k=1:2
                    parent=[41,224];b=find(p.parent==parent(k));parent_losses(i,j,k)=sum(r.branch(b,14)+r.branch(b,16));
                end
            end
        catch err
            row.status=string(err.identifier)+": "+string(err.message);
        end
        audits=[audits;row]; %#ok<AGROW>
        fprintf('hour%d %s qualified%d %s\n',hours(i),v,row.qualified,row.status);
    end
    save(fullfile(out,'probe_results.mat'),'flows','losses','parent_losses','hours','variants','audits','setup','-v7');
    writetable(struct2table(audits),fullfile(out,'probe_audit.csv'));
end
end
