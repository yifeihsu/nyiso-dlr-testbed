function report=validate_reference_recovery()
% Test exact AC elimination against saved detailed profile-PF operating points.
% No detailed PF is rerun, and no model parameter or profile is changed.
root=fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
addpath(fullfile(root,'System Matpower Format'));
out=fullfile(root,'output','nygrid_2025_compact_ac','validation');if ~isfolder(out),mkdir(out);end
baseline=fullfile(root,'output','nygrid_2025_acpf_profile_audit','acpf');
sample=load(fullfile(baseline,'representative_h8508.mat'),'m');
retained=sample.m.userdata.source_dc.slim.bus_ids(:);assert(numel(retained)==148);
hours=[2630 4194 523 3360 4000 8508 8471 8472];checks=struct([]);
for h=hours
    saved=fullfile(baseline,sprintf('representative_h%04d.mat',h));
    if isfile(saved)
        d=load(saved,'m','r');m=d.m;V=d.r.bus(:,8).*exp(1j*deg2rad(d.r.bus(:,9)));
        observed_from=complex(d.r.branch(:,14),d.r.branch(:,15));observed_to=complex(d.r.branch(:,16),d.r.branch(:,17));
    else
        m=npcc_nygrid_2025_ac(h);
        axis=load(fullfile(baseline,'annual_axes.mat'),'model_month');
        d=load(fullfile(baseline,'monthly',sprintf('profile_PF_2025_%02d.mat',axis.model_month(h))), ...
            'hour_index','bus_id','branch_keys','VM','VA','PF','QF','PT','QT','computed_current_available');
        j=find(d.hour_index==h);assert(isscalar(j)&&d.computed_current_available(j));
        [ok,ib]=ismember(m.bus(:,1),d.bus_id);assert(all(ok));
        [ok,il]=ismember(string(m.userdata.ac_system.branch_keys),string(d.branch_keys));assert(all(ok));
        V=d.VM(j,ib)'.*exp(1j*deg2rad(d.VA(j,ib)'));
        observed_from=complex(d.PF(j,il)',d.QF(j,il)');observed_to=complex(d.PT(j,il)',d.QT(j,il)');
    end
    ref=compact_reference_operators(m,retained);Vr=V(ref.retained_full_rows);lifted=ref.voltage_lift*Vr;
    If=ref.Yfrom*lifted;It=ref.Yto*lifted;Is=ref.Yseries*lifted;
    Sf=m.baseMVA*lifted(ref.from_bus_rows).*conj(If);St=m.baseMVA*lifted(ref.to_bus_rows).*conj(It);
    current_base=m.baseMVA*1000./(sqrt(3)*m.bus(ref.to_bus_rows,10));
    current_error=max(abs((ref.Yseries*V-Is).*current_base));
    a=struct('hour_index',h,'full_buses',size(m.bus,1),'retained_buses',numel(retained),'eliminated_buses',numel(ref.eliminated_full_rows), ...
        'maximum_complex_voltage_recovery_error_pu',max(abs(lifted-V)), ...
        'maximum_branch_complex_power_error_MVA',max([abs(Sf-observed_from);abs(St-observed_to)]), ...
        'maximum_complex_series_current_error_A',current_error, ...
        'zero_current_lift_relative_residual',ref.zero_current_lift_relative_residual, ...
        'minimum_passivity_eigenvalue',ref.minimum_passivity_eigenvalue, ...
        'eliminated_block_condition_estimate',ref.eliminated_block_condition_estimate, ...
        'detailed_solution_was_read_from_sealed_profile_PF',true,'detailed_PF_rerun',false, ...
        'native_compact_PF_solved',false,'passed',false);
    a.passed=a.maximum_complex_voltage_recovery_error_pu<1e-8 ...
        &&a.maximum_branch_complex_power_error_MVA<1e-5&&a.maximum_complex_series_current_error_A<1e-4;
    assert(a.passed,'compactReference:SavedPoint','Saved-point algebra failed at hour%d.',h);
    checks=[checks a]; %#ok<AGROW>
    fprintf('REFERENCE_AC_KRON h%d retained148 E%d Verr%.3g Serr%.3g Ierr%.3g\n',h,numel(ref.eliminated_full_rows), ...
        a.maximum_complex_voltage_recovery_error_pu,a.maximum_branch_complex_power_error_MVA,current_error);
end
report=struct('passed',all([checks.passed]),'checks',checks,'retained_bus_ids',retained, ...
    'only_saved_point_recovery_validated_here',true,'native_compact_convergence_not_yet_claimed',true, ...
    'physical_qualification_of_parent_not_upgraded',true,'internal_NYISO_observations_used',false);
fid=fopen(fullfile(out,'independent_reference_recovery.json'),'w');fprintf(fid,'%s\n',jsonencode(report,'PrettyPrint',true));fclose(fid);
writetable(struct2table(checks),fullfile(out,'independent_reference_recovery.csv'));
end
