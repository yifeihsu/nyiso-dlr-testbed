function flows = ny_lite_interface_flows(results, defs)
%NY_LITE_INTERFACE_FLOWS Sum PF/PT-metered MW flows by subpath and aggregate.

if nargin < 2 || isempty(defs), defs=ny_lite_interface_definitions(results); end
PF=14; PT=16;
if size(results.branch,2)<PT
    error('ny_lite_interface_flows:MissingPowerFlowColumns', ...
        'Run a MATPOWER AC power flow before calculating interface flows.');
end
flows=struct([]);
keys={};
for k=1:numel(defs)
    key=[defs(k).interface_name '|' defs(k).zone_boundary];
    if ~any(strcmp(key, keys)), keys{end+1}=key; end %#ok<AGROW>
end
for j=1:numel(keys)
    parts=regexp(keys{j},'\|','split'); name=parts{1}; boundary=parts{2};
    idx=find(strcmp({defs.interface_name},name) & strcmp({defs.zone_boundary},boundary));
    value=0;
    for n=idx
        if strcmpi(defs(n).flow_column, 'PF')
            p = results.branch(defs(n).branch_index, PF);
        elseif strcmpi(defs(n).flow_column, 'PT')
            p = results.branch(defs(n).branch_index, PT);
        else
            error('ny_lite_interface_flows:UnknownFlowColumn', ...
                'Unknown flow column %s.', defs(n).flow_column);
        end
        value=value+defs(n).sign*p;
    end
    rec=struct('interface_name',name,'aggregate_name',defs(idx(1)).aggregate_name, ...
        'zone_boundary',boundary,'flow_mw',value,'branch_count',numel(idx), ...
        'result_type','subpath');
    if isempty(flows), flows=rec; else, flows(end+1)=rec; end %#ok<AGROW>
end
aggs=unique({defs.aggregate_name},'stable');
for a=1:numel(aggs)
    sub=find(strcmp({flows.aggregate_name},aggs{a}) & strcmp({flows.result_type},'subpath'));
    if numel(sub)<=1 && strcmp(flows(sub).interface_name,aggs{a}), continue; end
    rec=struct('interface_name',aggs{a},'aggregate_name',aggs{a}, ...
        'zone_boundary',strjoin(unique({flows(sub).zone_boundary},'stable'),'/'), ...
        'flow_mw',sum([flows(sub).flow_mw]), ...
        'branch_count',sum([flows(sub).branch_count]),'result_type','aggregate');
    flows(end+1)=rec; %#ok<AGROW>
end
end
