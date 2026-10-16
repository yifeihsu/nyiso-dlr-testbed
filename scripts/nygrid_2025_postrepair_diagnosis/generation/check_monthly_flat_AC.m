function receipt=check_monthly_flat_AC()
% Twelve predeclared source-selected pairs; only in-memory HY PG changes.
root=fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
out=fullfile(root,'output','nygrid_2025_postrepair_diagnosis','generation','shape_ac');if ~isfolder(out),mkdir(out);end
controlpath=fullfile(root,'output','nygrid_2025_postrepair_diagnosis','generation','monthly_flat_generation_control.mat');
c=load(controlpath);runtime=fullfile(root,'scripts','nygrid_2025_moses_repair','delivery','runtime');addpath(runtime);
setup=setup_nygrid_latest(root,'C:/Users/Holiday/OneDrive/Documents/MATLAB/matpower');[model,mreceipt]=nylatest_data();
controlhash=nylatest_file_sha256(controlpath);hours=double(c.source_selected_hour_index(:));hydro=double(c.hydro_rows_1based(:));gamma=double(c.gamma);
assert(numel(hours)==12&&all(model.axis.source_qualified(hours))&&gamma==model.scale_factor_gamma);
ops=readtable(fullfile(root,'output','nygrid_2025_acpf_profile_audit','alignment','interface_operator_terms.csv'),'TextType','string');ops=ops(ops.interface=="MOSES SOUTH",:);
evidence=readtable(fullfile(root,'output','nygrid_2025_postrepair_diagnosis','hourly_evidence.csv'));
rows=struct([]);witness=cell(12,1);
for k=1:12
 h=hours(k);m=load_nygrid_latest(h);before=m;p=nylatest_prepare_policy(m);native=logical(p.native);assert(nnz(native)==1437);
 [tf,br]=ismember(m.gen(:,1),m.bus(:,1));assert(all(tf));d=native&p.bus_group(br)==4;
 m.gen(hydro,2)=c.hydro_PG_public_MW(h,:)'*gamma;
 m.userdata.ac_system.generator_p_reference=m.gen(:,2);
 w=m.userdata.ac_system.p_objective_weight;m.gencost(hydro,6)=-2*w(hydro).*m.gen(hydro,2);m.gencost(hydro,7)=w(hydro).*m.gen(hydro,2).^2;
 unchanged=setdiff(1:size(m.gen,1),hydro);assert(isequaln(m.gen(unchanged,:),before.gen(unchanged,:)));
 assert(isequaln(m.gen(:,[1,3:21]),before.gen(:,[1,3:21])));
 for name={'bus','branch','dcline'},assert(isequaln(m.(name{1}),before.(name{1})));end
 assert(max(abs(m.gen(:,2)-before.gen(:,2)))-max(abs(m.gen(hydro,2)-before.gen(hydro,2)))<1e-10);
 deltaNative=sum(m.gen(native,2)-before.gen(native,2));deltaHY=sum(m.gen(hydro,2)-before.gen(hydro,2));assert(max(abs([deltaNative,deltaHY]))<1e-8);
 deltaD=sum(m.gen(d,2)-before.gen(d,2))/gamma;assert(abs(deltaD-c.native_D_delta_public_MW(h))<1e-8);
 assert(all(m.gen(:,2)>=m.gen(:,10)-1e-8)&all(m.gen(:,2)<=m.gen(:,9)+1e-8));
 [cb,ab,rb,lb]=nylatest_coupled_solve(before);[ca,aa,ra,la]=nylatest_coupled_solve(m);
 assert(ab.PF_converged&&ab.AC_equation_gate&&ab.loss_allocation_gate&&ab.reduction_and_equation_gate);
 assert(aa.PF_converged&&aa.AC_equation_gate&&aa.loss_allocation_gate&&aa.reduction_and_equation_gate);
 assert(abs(ra.gen(1466,3))<1e-10&&ra.gen(1466,2)==m.gen(1466,2));
 terms=ops(ops.state==string(model.axis.state_labels(m.userdata.latest_runtime.state_index)),:);
 [fb,mb,tb]=flow(rb,terms,gamma);[fa,ma,ta]=flow(ra,terms,gamma);
 assert(abs(fb-evidence.current_Moses_primary_MW(h))<1e-7);
 closure=(fa-fb)-deltaD-(ta-tb);assert(abs(closure)<1e-7&&abs((ma-mb)-deltaD)<1e-7);
 observed=evidence.Moses_observed_MW(h);
 row=struct('hour_index',h,'state_index',m.userdata.latest_runtime.state_index,'source_selected_without_P32',true, ...
  'current_Moses_public_MW',fb,'control_Moses_public_MW',fa,'observed_Moses_public_MW',observed, ...
  'native_D_delta_public_MW',deltaD,'Moses_delta_public_MW',fa-fb,'terminal_correction_delta_public_MW',ta-tb,'cut_closure_error_public_MW',closure, ...
  'current_residual_public_MW',fb-observed,'control_residual_public_MW',fa-observed,'control_equation_qualified',true, ...
  'current_operating_qualified',ab.passed,'control_operating_qualified',aa.passed, ...
  'control_max_nodal_P_residual_MW',aa.max_nodal_P_residual_mw,'control_max_nodal_Q_residual_MVAr',aa.max_nodal_Q_residual_mvar, ...
  'HY_total_change_model_MW',deltaHY,'native_total_change_model_MW',deltaNative,'fixed_PV20_Q_MVAr',ra.gen(1466,3));
 rows=[rows;row]; %#ok<AGROW>
 witness{k}=struct('hour_index',h,'current_input_bus',before.bus,'current_input_gen',before.gen,'control_input_bus',m.bus,'control_input_gen',m.gen, ...
  'input_branch',m.branch,'input_dcline',m.dcline,'current_solved_bus',rb.bus,'current_solved_gen',rb.gen,'current_solved_branch',rb.branch, ...
  'control_solved_bus',ra.bus,'control_solved_gen',ra.gen,'control_solved_branch',ra.branch,'current_audit',ab,'control_audit',aa, ...
  'current_actual_budget_MW',lb.actual_budget_MW,'control_actual_budget_MW',la.actual_budget_MW, ...
  'current_recovered_line_current_A',cb.recovered_line_current_A,'control_recovered_line_current_A',ca.recovered_line_current_A);
 fprintf('MONTHLY_FLAT_AC h%d current%.6f control%.6f Ddelta%.6f terminaldelta%.6f closure%.3g\n',h,fb,fa,deltaD,ta-tb,closure);
end
assert(strcmp(controlhash,nylatest_file_sha256(controlpath)));
writetable(struct2table(rows),fullfile(out,'monthly_flat_AC_comparison.csv'));save(fullfile(out,'monthly_flat_AC_witness.mat'),'witness','-v7');
receipt=struct('passed',true,'scope','Twelve source-selected monthly maximum absolute nativeD injection-change hours, fresh current/control AC pairs', ...
 'hours',hours','hour_selection_used_observations',false,'current_model_changed',false,'annual_sensitivity_claimed',false, ...
 'all_control_equation_qualified',all([rows.control_equation_qualified]),'current_operating_qualified',nnz([rows.current_operating_qualified]),'control_operating_qualified',nnz([rows.control_operating_qualified]), ...
 'sample_current_Moses_MAE_public_MW',mean(abs([rows.current_residual_public_MW])),'sample_control_Moses_MAE_public_MW',mean(abs([rows.control_residual_public_MW])), ...
 'maximum_cut_closure_error_public_MW',max(abs([rows.cut_closure_error_public_MW])), ...
 'maximum_terminal_correction_delta_public_MW',max(abs([rows.terminal_correction_delta_public_MW])), ...
 'maximum_control_nodal_P_residual_MW',max(abs([rows.control_max_nodal_P_residual_MW])),'maximum_control_nodal_Q_residual_MVAr',max(abs([rows.control_max_nodal_Q_residual_MVAr])), ...
 'model_sha256',mreceipt.model_file.sha256,'control_sha256',controlhash,'setup',setup,'points',rows);
fid=fopen(fullfile(out,'monthly_flat_AC_receipt.json'),'w');assert(fid>=0);fprintf(fid,'%s\n',jsonencode(receipt,'PrettyPrint',true));fclose(fid);
end
function [primary,midpoint,terminal]=flow(r,terms,gamma)
primary=0;source=0;target=0;
for j=1:height(terms)
 f=terms.first_runtime_branch_row(j);t=terms.last_runtime_branch_row(j);sg=terms.coefficient(j);
 primary=primary+sg*r.branch(f,14);
 if sg>0,source=source+r.branch(f,14);target=target-r.branch(t,16);
 else,source=source+r.branch(t,16);target=target-r.branch(f,14);end
end
primary=primary/gamma;midpoint=(source+target)/(2*gamma);terminal=primary-midpoint;
end
