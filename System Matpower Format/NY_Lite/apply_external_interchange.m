function [mpc, report] = apply_external_interchange(mpc, schedule, options)
%APPLY_EXTERNAL_INTERCHANGE Apply explicit external-to-NY transactions.
%   options.method is REQUIRED unless every schedule row supplies method.
%   Supported methods:
%     generator_redispatch   - preserve native loads; increase external PG
%                              and decrease NY PG by equal MW.
%     balanced_injection_test - source/sink PD transaction for PTDF screening.

if nargin < 2 || isempty(schedule)
    error('apply_external_interchange:ScheduleRequired', 'An interchange schedule is required.');
end
if nargin < 3, options=struct(); end
if ~isfield(options,'method'), options.method=''; end
if ~isfield(options,'schedule_file')
    options.schedule_file=fullfile(fileparts(mfilename('fullpath')), ...
        'ny_external_interchange_schedule.csv');
end
if ~isfield(options,'allow_repeat'), options.allow_repeat=false; end

mpc=attach_nyiso_zone_metadata(mpc);
rows=normalize_schedule(schedule,options);
if ~isfield(mpc.userdata,'ny_lite'), mpc.userdata.ny_lite=struct(); end
if ~isfield(mpc.userdata.ny_lite,'applied_interchange_transactions')
    mpc.userdata.ny_lite.applied_interchange_transactions={};
end
applied_ids=mpc.userdata.ny_lite.applied_interchange_transactions;
report=struct([]);

for k=1:numel(rows)
    r=rows(k);
    method=options.method;
    if isempty(method) && isfield(r,'method'), method=r.method; end
    if isempty(method)
        error('apply_external_interchange:MethodRequired', ...
            'Specify generator_redispatch or balanced_injection_test explicitly.');
    end
    method=lower(strtrim(char(method)));
    if ~any(strcmp(method, {'generator_redispatch','balanced_injection_test'}))
        error('apply_external_interchange:BadMethod','Unsupported method %s.',method);
    end
    txid=r.transaction_id;
    if any(strcmp(txid, applied_ids)) && ~options.allow_repeat
        error('apply_external_interchange:RepeatedTransaction', ...
            'Transaction %s has already been applied.',txid);
    end
    validate_boundary_buses(mpc,r.external_source_bus,r.ny_sink_bus);

    pre_pd=sum(mpc.bus(:,3)); pre_qd=sum(mpc.bus(:,4)); pre_pg=sum(mpc.gen(mpc.gen(:,8)>0,2));
    source_alloc=[]; sink_alloc=[];
    if strcmp(method,'balanced_injection_test')
        ei=find(mpc.bus(:,1)==r.external_source_bus,1);
        ni=find(mpc.bus(:,1)==r.ny_sink_bus,1);
        mpc.bus(ei,3)=mpc.bus(ei,3)-r.scheduled_import_mw;
        mpc.bus(ni,3)=mpc.bus(ni,3)+r.scheduled_import_mw;
        mpc.bus(ei,4)=mpc.bus(ei,4)-r.scheduled_mvar;
        mpc.bus(ni,4)=mpc.bus(ni,4)+r.scheduled_mvar;
    else
        source_idx=resolve_pool(mpc,r,'external');
        sink_idx=resolve_pool(mpc,r,'ny');
        [mpc.gen,source_alloc,rem1]=ny_lite_allocate_pg_delta( ...
            mpc.gen,source_idx,r.scheduled_import_mw,[]);
        if abs(rem1)>1e-6, error('Insufficient external source headroom for %s.',txid); end
        [mpc.gen,sink_alloc,rem2]=ny_lite_allocate_pg_delta( ...
            mpc.gen,sink_idx,-r.scheduled_import_mw,[]);
        if abs(rem2)>1e-6, error('Insufficient NY sink down-room for %s.',txid); end
        if abs(r.scheduled_mvar)>1e-9
            warning('apply_external_interchange:ReactiveIgnored', ...
                'scheduled_mvar is ignored in generator_redispatch mode.');
        end
    end

    rec=struct('transaction_id',txid,'method',method, ...
        'scheduled_import_mw',r.scheduled_import_mw, ...
        'net_system_load_change_mw',sum(mpc.bus(:,3))-pre_pd, ...
        'net_system_load_change_mvar',sum(mpc.bus(:,4))-pre_qd, ...
        'net_system_generation_change_mw',sum(mpc.gen(mpc.gen(:,8)>0,2))-pre_pg, ...
        'source_allocation_mw',source_alloc(:)', 'sink_allocation_mw',sink_alloc(:)');
    if isempty(report), report=rec; else, report(end+1)=rec; end %#ok<AGROW>
    applied_ids{end+1}=txid; %#ok<AGROW>
end
mpc.userdata.ny_lite.applied_interchange_transactions=applied_ids;
mpc.userdata.ny_lite.interchange_report=report;
end

function rows=normalize_schedule(input,options)
if ischar(input) || (exist('isstring','builtin') && isstring(input))
    token=char(input);
    if exist(token,'file')==2
        tbl=readtable(token);
    else
        tbl=readtable(options.schedule_file);
        names=cellfun(@lower,tbl.Properties.VariableNames,'UniformOutput',false);
        sc=find(strcmp(names,'scenario_id'),1);
        vals=tbl{:,sc}; if iscell(vals), mask=strcmp(vals,token); else, mask=strcmp(cellstr(vals),token); end
        tbl=tbl(mask,:);
        if height(tbl)==0, error('Unknown interchange scenario %s.',token); end
    end
    input=tbl;
end
if (exist('istable','builtin') || exist('istable','file')) && istable(input)
    rows=table2struct(input);
elseif isstruct(input)
    rows=input;
else
    error('Interchange schedule must be a struct, table, CSV path, or scenario_id.');
end
required={'transaction_id','external_source_bus','ny_sink_bus','scheduled_import_mw'};
for k=1:numel(rows)
    for j=1:numel(required)
        if ~isfield(rows(k),required{j}), error('Schedule lacks %s.',required{j}); end
    end
    rows(k).transaction_id=tochar(rows(k).transaction_id);
    rows(k).external_source_bus=tonumber(rows(k).external_source_bus);
    rows(k).ny_sink_bus=tonumber(rows(k).ny_sink_bus);
    rows(k).scheduled_import_mw=tonumber(rows(k).scheduled_import_mw);
    if ~isfield(rows(k),'scheduled_mvar') || isemptyvalue(rows(k).scheduled_mvar), rows(k).scheduled_mvar=0; else, rows(k).scheduled_mvar=tonumber(rows(k).scheduled_mvar); end
    if ~isfield(rows(k),'method'), rows(k).method=''; else, rows(k).method=tochar(rows(k).method); end
end
end

function validate_boundary_buses(mpc,external_bus,ny_bus)
ei=find(mpc.bus(:,1)==external_bus,1); ni=find(mpc.bus(:,1)==ny_bus,1);
if isempty(ei) || isempty(ni), error('Interchange source/sink bus is missing.'); end
if external_bus==ny_bus, error('External source and NY sink buses must differ.'); end
if mpc.userdata.nyiso_zone_id(ei)>0, error('External source bus %d is inside NY.',external_bus); end
if mpc.userdata.nyiso_zone_id(ni)==0, error('NY sink bus %d is outside NY.',ny_bus); end
end

function idx=resolve_pool(mpc,r,side)
if strcmp(side,'external')
    idxfield='external_source_gen_idx'; busfield='external_source_bus';
else
    idxfield='ny_sink_gen_idx'; busfield='ny_sink_bus';
end
idx=[];
if isfield(r,idxfield) && ~isemptyvalue(r.(idxfield))
    idx=parse_index_list(r.(idxfield));
end
if isempty(idx)
    bus=r.(busfield);
    idx=find(mpc.gen(:,1)==bus & mpc.gen(:,8)>0);
end
if isempty(idx), error('No online generator found for %s pool.',side); end
end

function idx=parse_index_list(value)
if isnumeric(value), idx=value(:); return; end
s=tochar(value); if isempty(strtrim(s)), idx=[]; return; end
parts=regexp(s,'[; ,]+','split'); idx=str2double(parts(:)); idx=idx(isfinite(idx));
end
function tf=isemptyvalue(v)
if isempty(v), tf=true; elseif isnumeric(v), tf=all(isnan(v)); else, tf=isempty(strtrim(tochar(v))); end
end
function x=tonumber(v)
if iscell(v), v=v{1}; end
if isnumeric(v), x=double(v); else, x=str2double(char(v)); end
if ~isfinite(x), error('Schedule contains a nonnumeric required value.'); end
end
function s=tochar(v)
if iscell(v), v=v{1}; end
if isnumeric(v), s=num2str(v); else, s=char(v); end
end
