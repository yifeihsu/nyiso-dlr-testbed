function report=benchmark_compact_runtime()
% Warmed fixed100-hour benchmark; MATLAB profiler isolates actual overhead.
root=fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
addpath(fullfile(root,'scripts','nygrid_2025_compact_ac','core'));
addpath(fullfile(root,'scripts','nygrid_2025_acpf_profile_audit','acpf'));
out=fullfile(root,'output','nygrid_2025_compact_ac','validation','benchmark');if ~isfolder(out),mkdir(out);end
cache=load_profile_cache();registry=readtable(fullfile(root,'output','nygrid_2025_slim','network','bus_register.csv'));anchors=double(registry.model_bus(:));
prior=jsondecode(fileread(fullfile(root,'output','nygrid_2025_acpf_profile_audit','acpf','cache_parity_and_benchmark.json')));
hours=prior.benchmark_hours(:);assert(numel(hours)==100);
opt=mpoption('model','AC','verbose',0,'out.all',0,'pf.alg','NR','pf.nr.max_it',50,'pf.tol',1e-10,'pf.enforce_q_lims',0,'exp.use_legacy_core',1);
for h=[2630 8508],m=profile_case_from_cache(cache,h);c=compact_ac_build(m,anchors);compact_ac_solve(c,opt);end
ws=warning;cleanup=onCleanup(@()warning(ws));warning('off','MATLAB:nearlySingularMatrix');warning('off','MATLAB:singularMatrix');
profile clear;profile on;
rows=struct([]);tall=tic;
for h=hours'
    t=tic;m=profile_case_from_cache(cache,h);input_seconds=toc(t);
    t=tic;c=compact_ac_build(m,anchors);build_seconds=toc(t);
    t=tic;[r,a]=compact_ac_solve(c,opt);solve_seconds=toc(t);
    rows=[rows struct('hour',h,'input_seconds',input_seconds,'build_seconds',build_seconds,'solve_recovery_audit_seconds',solve_seconds, ...
        'NR_seconds',r.et,'PF_converged',r.success,'full_equation_gate',a.AC_equation_gate,'profile_gate',a.P_profile_preservation_gate)]; %#ok<AGROW>
end
elapsed=toc(tall);profile off;profiling=profile('info');save(fullfile(out,'MATLAB_profile.mat'),'profiling');
ft=profiling.FunctionTable;hot=struct([]);
for k=1:numel(ft)
    child=0;if ~isempty(ft(k).Children),child=sum([ft(k).Children.TotalTime]);end
    hot=[hot struct('function_name',ft(k).FunctionName,'calls',ft(k).NumCalls,'total_seconds',ft(k).TotalTime,'self_seconds',max(0,ft(k).TotalTime-child))]; %#ok<AGROW>
end
[~,order]=sort([hot.self_seconds],'descend');hot=hot(order);hot=hot(1:min(25,numel(hot)));
report=struct('completed',true,'benchmark_hours',hours,'benchmark_count',100,'warmup_hours',[2630 8508], ...
    'elapsed_seconds',elapsed,'projected_8651_seconds',elapsed/100*8651,'PF_converged',sum([rows.PF_converged]), ...
    'equation_qualified',sum([rows.full_equation_gate]),'profile_preserved',sum([rows.profile_gate]), ...
    'mean_input_seconds',mean([rows.input_seconds]),'mean_build_seconds',mean([rows.build_seconds]), ...
    'mean_solve_recovery_audit_seconds',mean([rows.solve_recovery_audit_seconds]),'mean_NR_seconds',mean([rows.NR_seconds]), ...
    'MATLAB_profiler_enabled_for_this_timing',true,'top_self_time_functions',hot,'rows',rows);
writetable(struct2table(rows),fullfile(out,'runtime_by_hour.csv'));writetable(struct2table(hot),fullfile(out,'profile_hotspots.csv'));
fid=fopen(fullfile(out,'compact_runtime_benchmark.json'),'w');fprintf(fid,'%s\n',jsonencode(report,'PrettyPrint',true));fclose(fid);
fprintf('COMPACT_BENCHMARK 100hours %.2fs annual%.1fs build%.3f solve%.3f NR%.4f converge%d\n',elapsed,report.projected_8651_seconds,report.mean_build_seconds,report.mean_solve_recovery_audit_seconds,report.mean_NR_seconds,report.PF_converged);
disp(struct2table(hot(1:min(12,numel(hot)))));
end
