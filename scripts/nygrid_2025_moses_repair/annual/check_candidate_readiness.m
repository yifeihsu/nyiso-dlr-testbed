function receipt=check_candidate_readiness()
% Source-selected preflight for the compiled candidate, never P32-selected.
root=fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
annual=fullfile(root,'output','nygrid_2025_moses_repair','annual');bundle=fullfile(annual,'candidate_bundle');
out=fullfile(root,'output','nygrid_2025_moses_repair','validation');if ~isfolder(out),mkdir(out);end
contract=jsondecode(fileread(fullfile(annual,'replay_contract.json')));assert(contract.candidate_bound);
addpath(fullfile(bundle,'runtime'));setup=setup_nygrid_latest(bundle,'C:/Users/Holiday/OneDrive/Documents/MATLAB/matpower');
[model,~]=nylatest_data();candidate_path=fullfile(annual,'candidate_receipt.json');proof=jsondecode(fileread(candidate_path));assert(proof.passed);
for k=1:numel(proof.files)
    assert(strcmp(nylatest_file_sha256(fullfile(root,proof.files(k).path)),proof.files(k).sha256),'mosesReadiness:ChangedCandidate','Frozen candidate dependency changed.');
end
g=load(fullfile(root,'output','nygrid_2025_moses_repair','generation','generation_candidate.mat'),'stlawrence_rows_1based');
stl=double(g.stlawrence_rows_1based(:));boundary=double(model.boundary_injections.generator_rows(:));
assert(numel(stl)==16&&numel(model.generator_bus_ids)==contract.candidate_generator_rows);
q=logical(model.axis.source_qualified(:));times=datetime(string(model.axis.timestamp_utc(:)), ...
    'InputFormat','yyyy-MM-dd''T''HH:mm:ss''Z''','TimeZone','UTC');times.TimeZone='America/New_York';months=month(times);
hours=[349;1093;1765;2509;3135;3229;3469;3613;3973;4693;5477;5605;6181;6901;7645;8365;8605];
for mon=1:12
    ix=find(q&months==mon);[~,j]=max(sum(model.profiles.generator_PG_MW(ix,stl),2));hours(end+1)=ix(j); %#ok<AGROW>
end
ix=find(q);[~,j]=min(model.profiles.generator_PG_MW(ix,boundary));hours(end+1)=ix(j);
[~,j]=max(model.profiles.generator_PG_MW(ix,boundary));hours(end+1)=ix(j);
hours=unique(hours);assert(all(q(hours)));rows=struct([]);
code=fileread(fullfile(root,'scripts','nygrid_2025_moses_repair','annual','run_moses_annual.m'));
for h=hours'
    m=load_nygrid_latest(h);p=nylatest_prepare_policy(m);
    assert(all(m.gen(boundary,4:5)==0,'all')&&all(m.gen(boundary,9:10)==m.gen(boundary,2),'all'));
    assert(~any(ismember(boundary,p.native))&&all(p.generator_share(boundary)==0));
    active=m.gen(:,8)>0;active(boundary)=false;types=ones(size(m.bus,1),1);
    types(ismember(m.bus(:,1),m.gen(active,1)))=2;types(m.bus(:,1)==p.reference_bus)=3;
    assert(isequal(types,m.bus(:,2)),'mosesReadiness:BoundaryPV','Fixed boundary injection created voltage control.');
    [c,a,r,allocation]=nylatest_coupled_solve(m);
    a.HQ_PG_change_from_original_MW=r.gen(p.HQ,2)-m.gen(p.HQ,2);a.full_operating_gate=a.passed;
    for name={'flags','scalars'}
        declaration=regexp(code,[name{1},'=\{(.*?)\};'],'tokens','once');assert(~isempty(declaration));
        keys=regexp(declaration{1},'''([^'']+)''','tokens');
        for k=1:numel(keys),key=keys{k}{1};assert(isfield(a,key)&&isscalar(a.(key)),'mosesReadiness:Schema','Missing annual audit scalar: %s',key);end
    end
    qualified=a.PF_converged&&a.AC_equation_gate&&a.loss_allocation_gate&&a.reduction_and_equation_gate;
    fixedP=max(abs(r.gen(boundary,2)-m.gen(boundary,2)));fixedQ=max(abs(r.gen(boundary,3)));
    assert(qualified&&fixedP<1e-8&&fixedQ<1e-8,'mosesReadiness:Candidate','Candidate preflight failed qualification/fixedPQ.');
    assert(size(r.gen,1)==numel(model.generator_bus_ids)&&size(c.recovered_line_current_A,1)==size(r.branch,1));
    assert(numel(c.retained_bus_ids)==148&&numel(allocation.actual_budget_MW)==14);
    rows=[rows;struct('hour_index',h,'state_index',m.userdata.latest_runtime.state_index, ...
        'qualified',qualified,'fixed_boundary_P_error_MW',fixedP,'fixed_boundary_Q_MVAr',fixedQ, ...
        'maximum_nodal_P_residual_MW',a.max_nodal_P_residual_mw,'maximum_nodal_Q_residual_MVAr',a.max_nodal_Q_residual_mvar, ...
        'regional_import_residual_MW',a.regional_NY_import_residual_MW,'maximum_voltage_bound_violation_pu',a.max_voltage_bound_violation_pu, ...
        'full_operating_qualified',a.passed)]; %#ok<AGROW>
    fprintf('MOSES_PREFLIGHT h%d state%d qualified%d fixedQ%.3g\n',h,m.userdata.latest_runtime.state_index,qualified,fixedQ);
end
assert(isequal(unique([rows.state_index]),1:4));
% Compare compact and full-network Newton on a source-selected January peak.
h=hours(1);m=load_nygrid_latest(h);[~,ac,rc]=nylatest_coupled_solve(m);[~,ad,rd]=nylatest_coupled_solve(m,struct('backend','detailed'));
assert(ac.loss_allocation_gate&&ad.loss_allocation_gate&&ac.reduction_and_equation_gate&&ad.reduction_and_equation_gate);
vc=rc.bus(:,8).*exp(1j*deg2rad(rc.bus(:,9)));vd=rd.bus(:,8).*exp(1j*deg2rad(rd.bus(:,9)));
verr=max(abs(vc-vd));serr=max(abs(rc.branch(:,14:17)-rd.branch(:,14:17)),[],'all');assert(verr<1e-8&&serr<1e-5);
writetable(struct2table(rows),fullfile(out,'candidate_preflight_hours.csv'));
receipt=struct('passed',true,'hours',hours','selection','17priorrepresentativehours plus monthly StLawrence input peaks and PV20 source extremes; no P32 input', ...
    'generator_rows',numel(model.generator_bus_ids),'fixed_transfer_rows',size(m.dcline,1),'boundary_rows',boundary', ...
    'all_four_states',true,'fixed_PQ_contract_passed',true,'all_declared_annual_fields_available',true, ...
    'detailed_compact_hour',h,'detailed_compact_voltage_error_pu',verr,'detailed_compact_PQ_error_MVA',serr, ...
    'candidate_sha256',nylatest_file_sha256(candidate_path),'setup',setup,'whole_network_operating_feasibility_claimed',false,'annual_started',false);
fid=fopen(fullfile(out,'candidate_readiness.json'),'w');assert(fid>=0);fprintf(fid,'%s\n',jsonencode(receipt,'PrettyPrint',true));fclose(fid);
disp('MOSES_CANDIDATE_READINESS_PASS');
end
