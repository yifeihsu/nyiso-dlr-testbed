function [result,audit,recovered,allocation]=run_nygrid_2025_loss_consistent_acpf(input,options)
%RUN_NYGRID_2025_LOSS_CONSISTENT_ACPF Versioned148-bus loss-accounting replay.
% INPUT is a2025hour or unrevised detailed NYGRID case. This is PF-only.
% Default: published E-G network equivalent and boundary-consistent losses.
if nargin<1||isempty(input),input=8508;end
if nargin<2,options=struct();end
if ~isfield(options,'impedance_mode'),options.impedance_mode='released_equivalent';end
root=fileparts(fileparts(mfilename('fullpath')));
addpath(fullfile(root,'scripts','nygrid_2025_ac_loss_revision','core'));
if isnumeric(input),m=npcc_nygrid_2025_ac(input);else,m=input;end
m=ac_loss_prepare_case(m,options.impedance_mode);
if isfield(options,'loss_mode')&&strcmp(options.loss_mode,'legacy_single_slack')
    [result,audit,recovered,allocation]=ac_loss_solve(m,options);
elseif isfield(options,'loss_solver')&&strcmp(options.loss_solver,'outer_fixed_point')
    [result,audit,recovered,allocation]=ac_loss_solve(m,options);
else
    [result,audit,recovered,allocation]=ac_loss_coupled_solve(m,options);
end
end
