function result = npcc_nygrid_2025_slim_interfaces(solved_case)
%NPCC_NYGRID_2025_SLIM_INTERFACES Recover the comparable legacy flow functionals.
% Values are modelMW; public-equivalentMW divides by the frozen gamma.
assert(isstruct(solved_case)&&isfield(solved_case,'success')&&solved_case.success, ...
    'nygridSlim:UnsolvedCase','Pass a successful rundcpf result.');
assert(isfield(solved_case,'userdata')&&isfield(solved_case.userdata,'slim'), ...
    'nygridSlim:MissingRecovery','Use the slim-case loader first.');
meta=solved_case.userdata.slim;
assert(isequal(solved_case.bus(:,1),meta.bus_ids),'nygridSlim:BusOrder','Solved bus order differs from recovery metadata.');
flow=meta.interface_angle_matrix*deg2rad(solved_case.bus(:,9))+meta.interface_flow_offset(:);
result=table(string(meta.interface_names(:)),flow,flow/meta.gamma, ...
    'VariableNames',{'interface','model_mw','public_equivalent_mw'});
end
