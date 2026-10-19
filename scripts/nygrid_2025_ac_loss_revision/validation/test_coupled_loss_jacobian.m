function report=test_coupled_loss_jacobian()
% Central-difference audit of coupled polar F/J and nonlocal loss response.
root=fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
addpath(fullfile(root,'System Matpower Format'));
addpath(fullfile(root,'scripts','nygrid_2025_ac_loss_revision','core'));
addpath(fullfile(root,'scripts','nygrid_2025_compact_ac','core'));
out=fullfile(root,'output','nygrid_2025_ac_loss_revision','validation','jacobian');if ~isfolder(out),mkdir(out);end
definitions={8508,'compact',false,false;8508,'detailed',false,false;4194,'compact',false,false;8508,'compact',true,false;8508,'compact',false,true};
checks=struct([]);started=tic;
for z=1:size(definitions,1)
    h=definitions{z,1};backend=definitions{z,2};saturation=definitions{z,3};perturb=definitions{z,4};
    fixture=load(fullfile(root,'output','nygrid_2025_ac_loss_revision','validation','pairs','initial_stress',sprintf('h%04d.mat',h)), 'base','cf');
    base=ac_loss_prepare_case(fixture.base,'released_equivalent');ctx=ac_loss_coupled_context(base,backend);
    [ok,ix]=ismember(ctx.mode_bus_ids,fixture.cf.bus(:,1));assert(all(ok));
    V=fixture.cf.bus(ix,8).*exp(1j*deg2rad(fixture.cf.bus(ix,9)));
    if saturation
        use=find(ctx.policy.external_gen_group==12);first=use(1);
        ctx.policy.Pmax(first)=ctx.policy.baseline_PG(first)+.01;
    end
    if perturb
        Va=angle(V);Vm=abs(V);Va(ctx.pvpq)=Va(ctx.pvpq)+.001*cos((1:numel(ctx.pvpq))');
        Vm(ctx.pq)=Vm(ctx.pq).*(1+.0002*sin((1:numel(ctx.pq))'));V=Vm.*exp(1j*Va);
    end
    [F,J,state]=ac_loss_coupled_equations(ctx,V,true);assert(state.valid);
    n=numel(V);Va=angle(V);Vm=abs(V);evaluations=0;
    for delta=[1e-6 3e-7]
        dSpecA=complex(zeros(n));dSpecM=complex(zeros(n));dFA=zeros(numel(F),n);dFM=zeros(numel(F),n);
        for j=1:n
            plus=Va;minus=Va;plus(j)=plus(j)+delta;minus(j)=minus(j)-delta;
            [Fp,~,sp]=ac_loss_coupled_equations(ctx,Vm.*exp(1j*plus),false);
            [Fm,~,sm]=ac_loss_coupled_equations(ctx,Vm.*exp(1j*minus),false);assert(sp.valid&&sm.valid);
            dFA(:,j)=(Fp-Fm)/(2*delta);dSpecA(:,j)=(sp.specified_S_pu-sm.specified_S_pu)/(2*delta);
            plus=Vm;minus=Vm;plus(j)=plus(j)+delta;minus(j)=minus(j)-delta;
            [Fp,~,sp]=ac_loss_coupled_equations(ctx,plus.*exp(1j*Va),false);
            [Fm,~,sm]=ac_loss_coupled_equations(ctx,minus.*exp(1j*Va),false);assert(sp.valid&&sm.valid);
            dFM(:,j)=(Fp-Fm)/(2*delta);dSpecM(:,j)=(sp.specified_S_pu-sm.specified_S_pu)/(2*delta);
            evaluations=evaluations+4;
        end
        Jfd=[dFA(:,ctx.pvpq) dFM(:,ctx.pq)];
        a=struct('fixture_hour',h,'backend',backend,'voltage_variables',n,'PF_unknowns',size(J,1), ...
            'synthetic_external_saturation',saturation,'non_solution_voltage_perturbation',perturb,'finite_difference_step',delta, ...
            'specifiedS_angle_relative_inf_error',norm(dSpecA-state.dSspec_dVa,inf)/max(1,norm(state.dSspec_dVa,inf)), ...
            'specifiedS_magnitude_relative_inf_error',norm(dSpecM-state.dSspec_dVm,inf)/max(1,norm(state.dSspec_dVm,inf)), ...
            'PF_Jacobian_relative_inf_error',norm(Jfd-J,inf)/max(1,norm(J,inf)), ...
            'PF_Jacobian_maximum_absolute_error',max(abs(Jfd-J),[],'all'), ...
            'active_global_identity_residual_MW',abs(state.active_global_identity_residual_MW), ...
            'maximum_active_global_angle_derivative_MW_per_rad',max(abs(state.active_identity_dVa_MW)), ...
            'maximum_active_global_magnitude_derivative_MW_per_pu',max(abs(state.active_identity_dVm_MW)), ...
            'passed',false);
        a.passed=max([a.specifiedS_angle_relative_inf_error,a.specifiedS_magnitude_relative_inf_error,a.PF_Jacobian_relative_inf_error])<1e-5 ...
            &&a.active_global_identity_residual_MW<1e-6&&a.maximum_active_global_angle_derivative_MW_per_rad<1e-5 ...
            &&a.maximum_active_global_magnitude_derivative_MW_per_pu<1e-5;
        checks=[checks a]; %#ok<AGROW>
        save(fullfile(out,sprintf('case%d_delta%g.mat',z,delta)),'ctx','V','F','J','state','dSpecA','dSpecM','Jfd','a');
        fprintf('COUPLED_FD h%d %s saturation%d perturb%d step%.1g pass%d JSrel%.3g/%.3g Jrel%.3g identity%.3gMW\n', ...
            h,backend,saturation,perturb,delta,a.passed,a.specifiedS_angle_relative_inf_error,a.specifiedS_magnitude_relative_inf_error,a.PF_Jacobian_relative_inf_error,a.active_global_identity_residual_MW);
    end
end
report=struct('completed',true,'passed',all([checks.passed]),'checks',checks,'finite_difference_cases',numel(checks), ...
    'relative_error_tolerance_declared',1e-5,'elapsed_seconds',toc(started), ...
    'all_angles_and_all_voltage_magnitudes_checked',true,'same_policy_equations_and_controls',true, ...
    'synthetic_saturation_is_test_only',true,'global_active_identity_checked_away_from_solution',true, ...
    'annual_run_started',false,'OPF_used',false);
writetable(struct2table(checks),fullfile(out,'jacobian_checks.csv'));
fid=fopen(fullfile(out,'jacobian_receipt.json'),'w');fprintf(fid,'%s\n',jsonencode(report,'PrettyPrint',true));fclose(fid);
end
