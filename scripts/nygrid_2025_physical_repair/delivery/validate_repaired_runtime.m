function report=validate_repaired_runtime()
% Fresh authoring comparison of frozen repair application and compiled model.
root=fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
out=fullfile(root,'output','nygrid_2025_physical_repair','delivery','validation');if ~isfolder(out),mkdir(out);end
vendor='C:/Users/Holiday/OneDrive/Documents/MATLAB/matpower';
oldruntime=fullfile(root,'scripts','nygrid_2025_latest_handoff','runtime');
newruntime=fullfile(root,'scripts','nygrid_2025_physical_repair','delivery','runtime');
addpath(oldruntime);setup_nygrid_latest(root,vendor);
addpath(fullfile(root,'scripts','nygrid_2025_physical_repair','core'));
hours=[523 3360 4000 8508];expected=cell(4,1);
for j=1:4
    m=load_nygrid_latest(hours(j));[m,~]=nyrepair_apply_case(m);
    [result,audit,full,allocation]=nylatest_coupled_solve(m);
    assert(result.success&&audit.AC_equation_gate&&audit.loss_allocation_gate&&audit.reduction_and_equation_gate);
    expected{j}=struct('input',m,'result',result,'audit',audit,'full',full,'allocation',allocation,'operators',nylatest_compact_build(m));
end
addpath(newruntime);clear nylatest_paths nylatest_data load_nygrid_latest setup_nygrid_latest;
setup=setup_nygrid_latest(root,vendor);[data,receipt]=nylatest_data();rows=struct([]);
baseline=jsondecode(fileread(fullfile(root,'output','nygrid_2025_latest_handoff','model','model_receipt.json')));
assert(isequal(string({receipt.model_files(2:3).sha256}),string({baseline.model_files(2:3).sha256})));
for j=1:4
    old=expected{j};m=load_nygrid_latest(hours(j));
    for name={'bus','gen','branch','gencost','dcline'},assert(isequaln(m.(name{1}),old.input.(name{1})),name{1});end
    for name={'ac_system','ac_sections','ac_loss_revision','physical_repair','physical_repair_185195'}
        assert(isequaln(m.userdata.(name{1}),old.input.userdata.(name{1})),name{1});
    end
    c=nylatest_compact_build(m);operator_error=0;
    for name={'Yfull','Yred','voltage_lift','YfL','YtL','YseriesL'}
        operator_error=max(operator_error,max(abs(c.(name{1})-old.operators.(name{1})),[],'all'));
    end
    operator_error=norm(operator_error,inf); % JSON requires a full scalar.
    [result,audit,full,allocation]=run_nygrid_latest_acpf(hours(j));
    voltage_error=max(abs(complex_voltage(full)-complex_voltage(old.full)));
    branch_PQ_error=max(abs(full.branch(:,14:17)-old.full.branch(:,14:17)),[],'all');
    generator_PQ_error=max(abs(full.gen(:,2:3)-old.full.gen(:,2:3)),[],'all');
    current_error=max(abs(result.recovered_line_current_A-old.result.recovered_line_current_A),[],'all');
    loss_error=max(abs(allocation.actual_budget_MW-old.allocation.actual_budget_MW));
    assert(operator_error<1e-12&&voltage_error<1e-10&&max([branch_PQ_error,generator_PQ_error,current_error,loss_error])<1e-7);
    for name={'PF_converged','AC_equation_gate','loss_allocation_gate','reduction_and_equation_gate','VQ_and_generator_assumption_gate','passed'}
        assert(isequal(audit.(name{1}),old.audit.(name{1})),name{1});
    end
    w=table(25,.6096,90,1000,101325,'VariableNames',{'ambient_c','wind_m_s','wind_angle_deg','solar_w_m2','pressure_pa'});
    screen=screen_nygrid_latest_dlr(struct('full',full,'audit',audit,'allocation',allocation),w);
    assert(screen.numerical_identities_passed);
    row=struct('hour_index',hours(j),'passed',true,'loader_arrays_and_metadata_exact',true, ...
        'operator_max_error',operator_error,'voltage_error_pu',voltage_error,'branch_PQ_error_MVA',branch_PQ_error, ...
        'generator_PQ_error_MVA',generator_PQ_error,'current_error_A',current_error,'loss_budget_error_MW',loss_error, ...
        'thermal_parent_count',screen.candidate_parent_count,'thermal_identity_error_MW',screen.maximum_Joule_loss_identity_error_MW, ...
        'VQ_generator_gate',audit.VQ_and_generator_assumption_gate,'full_operating_gate',audit.passed);
    rows=[rows;row]; %#ok<AGROW>
    fprintf('REPAIRED_RUNTIME h%d exact1 Verror%.3g Ierror%.3g thermal%d\n',hours(j),voltage_error,current_error,screen.candidate_parent_count);
end
report=struct('passed',true,'scope','Four-state source-repair versus compiled derivative runtime; fresh coupled PF and thermal identity checks', ...
    'profile_shards_byte_identical',true,'source_mask_preserved',nnz(data.axis.source_qualified)==8651, ...
    'candidate_receipt_sha256',data.physical_repair.candidate_receipt_sha256,'model_sha256',receipt.model_file.sha256, ...
    'setup',setup,'points',rows,'annual_replay_claimed',false);
writetable(struct2table(rows),fullfile(out,'runtime_comparison.csv'));
fid=fopen(fullfile(out,'runtime_validation_receipt.json'),'w');assert(fid>=0);cleanup=onCleanup(@()fclose(fid));fprintf(fid,'%s\n',jsonencode(report,'PrettyPrint',true));
end

function V=complex_voltage(m),V=m.bus(:,8).*exp(1j*deg2rad(m.bus(:,9)));end
