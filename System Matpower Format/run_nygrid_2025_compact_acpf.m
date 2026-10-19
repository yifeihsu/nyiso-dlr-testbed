function [result,audit,recovered]=run_nygrid_2025_compact_acpf(input,mpopt)
%RUN_NYGRID_2025_COMPACT_ACPF Solve the148-bus complex AC equivalent.
% INPUT is an hour index, a compact_ac_build model, or a detailed MATPOWER
% case to reduce. RESULT.bus contains only retained nodes. RECOVERED is the
% algebraically recovered detailed MATPOWER result, including line powers.
% No OPF is used. Convergence and physical operating qualification differ.
if nargin<1||isempty(input),input=8508;end
if nargin<2,mpopt=[];end
root=fileparts(fileparts(mfilename('fullpath')));
addpath(fullfile(root,'scripts','nygrid_2025_compact_ac','core'));
if isnumeric(input)
    c=npcc_nygrid_2025_compact_ac(input);
elseif isfield(input,'model_kind')&&strcmp(input.model_kind,'compact_complex_admittance_AC')
    c=input;
else
    c=compact_ac_build(input);
end
[result,audit,recovered]=compact_ac_solve(c,mpopt);
end
