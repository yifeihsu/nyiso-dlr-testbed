function [result,audit,full,allocation]=run_nygrid_latest_acpf(hour_index,options)
%RUN_NYGRID_LATEST_ACPF Current148-bus coupled AC/loss-accounting PF only.
if nargin<1||isempty(hour_index),hour_index=8508;end
if nargin<2,options=struct();end
if isfield(options,'backend'),assert(strcmp(options.backend,'compact'),'nylatest:Backend','The current packaged model uses the compact AC backend.');end
if isfield(options,'loss_mode'),assert(strcmp(options.loss_mode,'boundary_consistent'),'nylatest:LossPolicy','The current packaged model uses boundary-consistent losses.');end
if isfield(options,'impedance_mode'),assert(strcmp(options.impedance_mode,'released_equivalent'),'nylatest:Impedance','The current packaged model preserves the released-equivalent R/X/B.');end
options.backend='compact';options.loss_mode='boundary_consistent';
m=load_nygrid_latest(hour_index);
[result,audit,full,allocation]=nylatest_coupled_solve(m,options);
end
