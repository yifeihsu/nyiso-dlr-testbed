function report=probe_solver_starts()
% Alternate numerical starts for failed fixed-parameter representative cases.
% Changes only starting voltages and QG, never any constraint, PG prior or cost.
root=fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
addpath(fullfile(root,'System Matpower Format'));
out=fullfile(root,'output','nygrid_2025_ac_system','ac_validation','electrical_solver_starts');
if ~isfolder(out),mkdir(out);end
seed=load(fullfile(root,'output','nygrid_2025_ac_system','ac_validation','electrical_final','hour_2630.mat'),'r');
assert(seed.r.success);rows=struct([]);
opt=mpoption('model','AC','verbose',0,'out.all',0,'opf.ac.solver','IPOPT', ...
    'opf.start',2,'opf.violation',1e-7,'ipopt.opts.max_iter',250, ...
    'ipopt.opts.tol',1e-9,'ipopt.opts.bound_relax_factor',0);
for h=[4194 523 4000]
    original=npcc_nygrid_2025_ac(h);
    for mode=["original_case_state" "minimum_load_voltage_seed"]
        m=original;
        if mode=="minimum_load_voltage_seed"
            [found,ix]=ismember(m.bus(:,1),seed.r.bus(:,1));assert(all(found));
            m.bus(:,8:9)=seed.r.bus(ix,8:9);
            m.gen(:,3)=min(max(seed.r.gen(:,3),m.gen(:,5)),m.gen(:,4));
            [found,gb]=ismember(m.gen(:,1),m.bus(:,1));assert(all(found));m.gen(:,6)=m.bus(gb,8);
        end
        assert(isequal(m.branch,original.branch)&&isequal(m.dcline,original.dcline)&&isequal(m.gencost,original.gencost) ...
            &&isequal(m.bus(:,[1:7 10:13]),original.bus(:,[1:7 10:13])) ...
            &&isequal(m.gen(:,[1 2 4 5 7:21]),original.gen(:,[1 2 4 5 7:21])));
        t=tic;[r,ok]=runopf(m,opt);elapsed=toc(t);[a,detail]=audit_ac_solution(m,r);
        a.hour_index=h;a.initialization=char(mode);a.opf_start=2;a.seconds=elapsed;
        a.model_constraints_and_PG_prior_and_objective_unchanged=true;
        a.sectioned_design_plan_sha256=m.userdata.ac_system.sectioned_design_plan_sha256;
        a.generator_capability_policy_sha256=m.userdata.ac_system.generator_capability_policy_sha256;
        a.ACPF_replay_passed=false;
        if ok
            [pf,pa,pf_detail,pf_input,pf_options]=replay_acpf_solution(m,r);
            a.ACPF_replay_passed=pa.passed;a.passed=a.passed&&pa.passed;
            save(fullfile(out,sprintf('h%d_%s_ACPF.mat',h,mode)),'pf','pa','pf_detail','pf_input','pf_options');
        end
        save(fullfile(out,sprintf('h%d_%s.mat',h,mode)),'m','r','opt','a','detail');
        rows=[rows a]; %#ok<AGROW>
        fprintf('START_PROBE h%d %s success%d audit%d P%.4g Q%.4g MVA%.4g\n',h,mode,ok,a.passed, ...
            a.max_nodal_P_residual_mw,a.max_nodal_Q_residual_mvar,a.max_equipment_MVA_violation);
        if a.passed,break;end
    end
end
report=struct('complete',true,'parameter_fitting_performed',false,'constraints_changed',false, ...
    'global_infeasibility_proved',false,'checks',rows);
fid=fopen(fullfile(out,'solver_start_diagnostics.json'),'w');fprintf(fid,'%s\n',jsonencode(report,'PrettyPrint',true));fclose(fid);
end
