function out = normalize_perform_ny_source(options)
%NORMALIZE_PERFORM_NY_SOURCE Inventory the immutable original PERFORM NY case.
% Canonical electrical values come from shunts_as_z_load (1576/2371/615).
% RAW and generator metadata recover device IDs and source-control roles;
% they never overwrite canonical parameters, status, loads, or dispatch.
% Parallel circuits that are electrically identical remain explicitly ambiguous.
if nargin < 1, options = struct(); end
if ~isfield(options,'write_outputs'), options.write_outputs = false; end
h = fileparts(mfilename('fullpath')); root = fileparts(fileparts(h));
if ~isfield(options,'output_dir')
    options.output_dir = fullfile(root,'output','ny_only_package_a','source_inventory');
end
manifest = readtable(fullfile(h,'perform_ny_source_manifest.csv'), ...
    'TextType','string','Delimiter',',','ReadVariableNames',true,'VariableNamingRule','preserve');
paths = fullfile(root,manifest.relative_path);
for k=1:height(manifest)
    assert(isfile(paths(k)), 'perform_source:Missing','Pinned source file is missing.');
    assert(file_sha(paths(k)) == manifest.sha256_lf_normalized(k), ...
        'perform_source:Hash','Pinned source content changed: %s',paths(k));
end
canonical_path = paths(manifest.source_role == "canonical_matpower");
raw_path = paths(manifest.source_role == "raw_device_identity");
meta_path = paths(manifest.source_role == "generator_identity_metadata");
assert(isscalar(canonical_path) && isscalar(raw_path) && isscalar(meta_path));
addpath(fileparts(canonical_path),'-begin');
m = nyiso_On_Peak_v23_shunts_as_z_load;
assert(isequal([size(m.bus,1),size(m.branch,1),size(m.gen,1)],[1576 2371 615]), ...
    'perform_source:Dimensions','Unexpected canonical source dimensions.');
[records,sections] = psse_read(char(raw_path),0);
[raw,~] = psse_parse(records,sections,0,33);
assert(size(raw.trans3.num,1)==0 && size(raw.twodc.num,1)==0, ...
    'perform_source:Unsupported','Explicit mapping required for newly present three-winding/DC devices.');
opts = detectImportOptions(meta_path,'VariableNamingRule','preserve');
names = intersect(["GenID","GenType","GenFuel","EIAPlantCode", ...
    "EIAPC-IDorPC-UC","Supplemental_ID"],string(opts.VariableNames));
opts = setvartype(opts,cellstr(names),'string');
meta = readtable(meta_path,opts);
assert(height(meta)==615 && isequal(meta.GEN_BUS,m.gen(:,1)), ...
    'perform_source:GenMetadata','Generator metadata rows do not align with canonical buses.');
gen = generator_inventory(m,raw,meta);
boundary = boundary_reconciliation(m,gen,h);
bus = bus_inventory(m,raw,gen);
branch = branch_inventory(m,raw);
[shunt,alias] = shunt_inventory(m,raw,gen);
controls = control_inventory(m,raw,gen,branch,shunt);
unresolved = unresolved_inventory(gen,branch,shunt);
% Identity mappings explicitly keep source bus IDs and canonical row pointers.
mapping = [table(bus.device_key,repmat("bus",height(bus),1),bus.source_bus_row, ...
    bus.source_bus,'VariableNames',{'device_key','record_family','source_row','canonical_model_id'}); ...
    table(branch.device_key,repmat("branch",height(branch),1),branch.source_branch_row, ...
    branch.source_branch_row,'VariableNames',{'device_key','record_family','source_row','canonical_model_id'}); ...
    table(gen.device_key,repmat("generator",height(gen),1),gen.source_gen_row, ...
    gen.source_gen_row,'VariableNames',{'device_key','record_family','source_row','canonical_model_id'})];
out = struct('source',m,'source_manifest',manifest,'canonical_source_path',canonical_path, ...
    'canonical_sha256',manifest.sha256_lf_normalized(manifest.source_role == "canonical_matpower"), ...
    'bus_inventory',bus,'branch_inventory',branch,'generator_inventory',gen, ...
    'shunt_inventory',shunt,'control_inventory',controls,'shunt_alias_inventory',alias, ...
    'boundary_reconciliation',boundary,'unresolved_records',unresolved, ...
    'source_to_model_mapping',mapping,'source_immutable',true, ...
    'electrical_parameters_modified',false,'operating_point_solved',false, ...
    'source_vintage',"PERFORM_NY_2019_v23",'power_scale',"historical_actual_mw", ...
    'electrical_baseline_qualified',false,'contemporary_validation_coverage',"none",'dlr_ready',false);
out.validation = validate_perform_ny_inventory(out);
assert(out.validation.pass,'perform_source:Inventory','Inventory accounting failed.');
if options.write_outputs
    if ~isfolder(options.output_dir),mkdir(options.output_dir);end
    fields = ["source_manifest","bus_inventory","branch_inventory","generator_inventory", ...
        "shunt_inventory","control_inventory","shunt_alias_inventory", ...
        "boundary_reconciliation","unresolved_records","source_to_model_mapping"];
    for name=fields
        ny_lite_writetable_lf(out.(name),fullfile(options.output_dir,"perform_ny_"+name+".csv"));
    end
    ny_lite_writetable_lf(out.validation.gates,fullfile(options.output_dir,'perform_ny_normalization_gates.csv'));
end
end

function g = generator_inventory(m,raw,meta)
n=size(m.gen,1);id=clean_id(meta.GenID);rawid=clean_id(string(raw.gen.txt(:,2)));
key="PERFORM2019:GEN:"+string(m.gen(:,1))+":"+id;
rawkey="PERFORM2019:GEN:"+string(raw.gen.num(:,1))+":"+rawid;
assert(numel(unique(rawkey))==numel(rawkey) && numel(unique(key))==n, ...
    'perform_source:GenIdentity','Duplicate generator bus/unit identity.');
[found,ri]=ismember(key,rawkey);assert(all(found),'perform_source:GenIdentity','Generator ID absent from RAW.');
fuel=string(m.genfuel);type=string(m.gentype);
assert(isequal(fuel,string(meta.GenFuel)) && isequal(type,string(meta.GenType)), ...
    'perform_source:GenRole','Canonical and metadata generation classes disagree.');
role=repmat("native_generation",n,1);
role(startsWith(type,"PS "))="native_pumped_storage";
role(startsWith(type,"BA ") | startsWith(type,"FW "))="native_energy_storage";
role(fuel=="import")="external_boundary_proxy";
role(fuel=="reference")="reference_placeholder";
role(ismissing(fuel) | strlength(strtrim(fuel))==0)="unresolved_generator_role";
native=startsWith(role,"native_");qplaceholder=max(abs(m.gen(:,4:5)),[],2)>=9000;
ireg=numbers(raw.gen,8);ireg=ireg(ri);regulated=ireg;
regulated(regulated==0)=m.gen(regulated==0,1);
assert(all(ismember(regulated,m.bus(:,1))),'perform_source:RegulatedBus','Unknown regulated bus.');
treatment=repmat("retain_native_P_Q_bounds_status_and_explicit_voltage_policy",n,1);
treatment(role=="external_boundary_proxy")="remove_generator_and_apply_separate_scheduled_P_fixed_Q";
treatment(role=="reference_placeholder")="remove_reference_placeholder_use_separate_declared_bounded_Q_policy";
treatment(role=="unresolved_generator_role")="exclude_until_role_resolved";
treatment(native & regulated~=m.gen(:,1))= ...
    "retain_canonical_local_PV_RAW_remote_regulation_not_implemented";
g=table((1:n)',m.gen(:,1),id,key,role,perform_nyiso_zone_letters(m,m.gen(:,1)), ...
    m.gen(:,8),raw.gen.num(ri,15),ri,ireg,regulated,m.gen(:,2),m.gen(:,3), ...
    m.gen(:,10),m.gen(:,9),m.gen(:,5),m.gen(:,4),m.gen(:,6),type,fuel, ...
    clean_text(meta.EIAPlantCode),clean_text(meta.("EIAPC-IDorPC-UC")), ...
    native,qplaceholder,m.gen(:,8)~=raw.gen.num(ri,15),treatment, ...
    repmat("canonical_fuel_type_and_RAW_bus_unit_ID",n,1), ...
    'VariableNames',{'source_gen_row','source_bus','source_generator_id','device_key', ...
    'source_device_role','source_zone','canonical_status','raw_status','raw_gen_row', ...
    'raw_ireg','regulated_bus','source_pg_mw','source_qg_mvar','source_pmin_mw', ...
    'source_pmax_mw','source_qmin_mvar','source_qmax_mvar','source_voltage_target_pu', ...
    'source_gen_type','source_gen_fuel','source_eia_plant_code','source_eia_unit_key', ...
    'native_generation_member','q_bounds_are_placeholder','raw_canonical_status_mismatch', ...
    'recommended_treatment','role_evidence'});
% regulated_bus retains the RAW intended target for source traceability.
% MATPOWER's canonical generator model instead regulates its terminal bus.
g.canonical_regulated_bus=g.source_bus;
g.raw_remote_control_omitted=g.regulated_bus~=g.canonical_regulated_bus;
end

function b = boundary_reconciliation(m,g,h)
selected=~g.native_generation_member;
b=g(selected,{'source_gen_row','source_bus','source_generator_id','device_key', ...
    'source_device_role','canonical_status','raw_status','source_pg_mw','source_qg_mvar'});
old=readtable(fullfile(h,'s12_external_boundary_groups.csv'),'TextType','string');
[present,j]=ismember(b.source_gen_row,old.gen_index);
group=repmat("UNASSIGNED_REFERENCE",height(b),1);
group(present)=old.p32_interface_name(j(present));
reason=repmat("present_in_legacy_schedule_map",height(b),1);
ref=b.source_device_role=="reference_placeholder";
reason(ref)="reference_placeholder_is_not_an_external_schedule";
missing=~present & ~ref;
assert(nnz(missing)==1 && b.source_bus(missing)==69 && b.source_generator_id(missing)=="X", ...
    'perform_source:BoundaryReconciliation','Unexpected omitted boundary identity.');
group(missing)="SCH - PJ - NY";
reason(missing)="legacy_fixed_P_heuristic_omitted_colocated_variable_P_import_canonical_offline";
b.proposed_schedule_group=group;b.boundary_member=~ref;
b.effective_pg_mw=b.source_pg_mw.*(b.canonical_status>0);
b.effective_qg_mvar=b.source_qg_mvar.*(b.canonical_status>0);
b.legacy_schedule_member=present;b.reconciliation_reason=reason;
% Effective values describe the original canonical source only. The boundary
% assembler applies the separately declared removal/Q policy for the RF row.
assert(all(m.gen(b.source_gen_row,1)==b.source_bus));
end

function b = bus_inventory(m,raw,g)
n=size(m.bus,1);ids=m.bus(:,1);
[found,ri]=ismember(ids,raw.bus.num(:,1));assert(all(found));
role=repmat("junction",n,1);load=m.bus(:,3)~=0 | m.bus(:,4)~=0;
role(load)="gross_load";
native=ismember(ids,g.source_bus(g.native_generation_member));
boundary=ismember(ids,g.source_bus(g.source_device_role=="external_boundary_proxy"));
reference=ismember(ids,g.source_bus(g.source_device_role=="reference_placeholder"));
shunt=m.bus(:,5)~=0 | m.bus(:,6)~=0;
role=add_role(role,native,"native_generation_terminal");
role=add_role(role,boundary,"boundary_injection_landing");
role=add_role(role,reference,"source_reference_placeholder_terminal");
role=add_role(role,shunt,"canonical_static_shunt");
b=table((1:n)',ids,"PERFORM2019:BUS:"+string(ids),string(m.bus_name),m.bus(:,10), ...
    perform_nyiso_zone_letters(m),m.bus(:,7),m.bus(:,2),raw.bus.num(ri,4),role, ...
    m.bus(:,3),m.bus(:,4),m.bus(:,5),m.bus(:,6),m.bus(:,8),m.bus(:,9), ...
    m.bus(:,13),m.bus(:,12),native,boundary,reference, ...
    'VariableNames',{'source_bus_row','source_bus','device_key','source_bus_name', ...
    'base_kv','source_zone','source_area','canonical_bus_type','raw_bus_type','electrical_role', ...
    'gross_pd_mw','gross_qd_mvar','source_gs_mw','source_bs_mvar', ...
    'source_vm_pu','source_va_deg','source_vmin_pu','source_vmax_pu', ...
    'has_native_generation','has_boundary_proxy','has_reference_placeholder'});
end

function b = branch_inventory(m,raw)
[converted,~]=psse_convert({},raw,0);r=converted.branch;
nl=size(raw.branch.num,1);nt=size(raw.trans2.num,1);n=size(m.branch,1);
assert(nl+nt==n,'perform_source:BranchCount','RAW branch-family counts changed.');
rid=[clean_id(string(raw.branch.txt(:,3)));clean_id(string(raw.trans2.txt(:,4)))];
kind=[repmat("ac_branch_unresolved_line_cable_or_equivalent",nl,1);repmat("two_winding_transformer",nt,1)];
prefix=[repmat("AC",nl,1);repmat("XFMR",nt,1)];
rawkey="PERFORM2019:"+prefix+":"+string(min(r(:,1:2),[],2))+":"+ ...
    string(max(r(:,1:2),[],2))+":"+rid;
assert(numel(unique(rawkey))==n,'perform_source:BranchIdentity','RAW branch identities are not unique.');
used=false(n,1);mapping=zeros(n,1);ambiguous=false(n,1);parameter_match=false(n,1);
candidates=strings(n,1);delta=zeros(n,1);
for k=1:n
    endpoint=find(r(:,1)==m.branch(k,1) & r(:,2)==m.branch(k,2));
    distance=max(abs(r(endpoint,3:10)-m.branch(k,3:10)),[],2);
    exact=endpoint(distance<=1e-6);
    if isempty(exact)
        available=endpoint(~used(endpoint));
        assert(numel(available)==1,'perform_source:BranchIdentity','Unresolved unique RAW branch mapping.');
        mapped=available;choices=endpoint;
    else
        choices=exact;available=exact(~used(exact));
        assert(~isempty(available),'perform_source:BranchAccounting','RAW circuit assigned more than once.');
        mapped=available(1);parameter_match(k)=true;
    end
    mapping(k)=mapped;used(mapped)=true;ambiguous(k)=numel(choices)>1;
    candidates(k)=strjoin(rawkey(choices),";");
    delta(k)=max(abs(r(mapped,3:10)-m.branch(k,3:10)));
end
assert(all(used),'perform_source:BranchAccounting','Unmapped RAW branch remains.');
confidence=repmat("unique_RAW_endpoint_and_electrical_parameter_match",n,1);
confidence(ambiguous)="electrically_identical_parallel_assignment_not_unique_physical_identity";
confidence(~parameter_match)="unique_RAW_endpoint_identity_with_canonical_parameter_difference";
control=zeros(n,1);regulated=zeros(n,1);tx=mapping>nl;
control(tx)=numbers(raw.trans2,30,mapping(tx)-nl);
regulated(tx)=numbers(raw.trans2,31,mapping(tx)-nl);
family=kind(mapping);family(m.branch(:,4)<0 & ~tx)="series_compensation_branch";
b=table((1:n)',rawkey(mapping),m.branch(:,1),m.branch(:,2),rid(mapping), ...
    family,m.branch(:,11),r(mapping,11),mapping,confidence,~ambiguous, ...
    candidates,parameter_match,delta,m.branch(:,3),m.branch(:,4),m.branch(:,5), ...
    m.branch(:,6),m.branch(:,7),m.branch(:,8),m.branch(:,9),m.branch(:,10), ...
    control,regulated,repmat(false,n,1), ...
    'VariableNames',{'source_branch_row','device_key','source_from_bus','source_to_bus', ...
    'raw_circuit_id','source_device_role','canonical_status','raw_status', ...
    'raw_converted_branch_row','identity_confidence','individual_circuit_identity_resolved', ...
    'raw_identity_candidates','raw_canonical_parameters_match','raw_parameter_max_abs_difference', ...
    'source_r_pu','source_x_pu','source_b_pu','source_rate_a_mva','source_rate_b_mva', ...
    'source_rate_c_mva','source_tap','source_shift_deg','raw_transformer_control_mode', ...
    'raw_regulated_bus','overhead_thermal_eligible'});
end

function [s,a] = shunt_inventory(m,raw,g)
rawid=clean_id(string(raw.gen.txt(:,2)));qs=find(rawid=="QS");
swbus=raw.swshunt.num(:,1);n=numel(swbus);
assert(numel(qs)==34 && n==34 && all(~ismember(qs,g.raw_gen_row)), ...
    'perform_source:ShuntAccounting','QS generators must not be copied into canonical generator set.');
[found,bi]=ismember(swbus,m.bus(:,1));[found_q,qi]=ismember(swbus,raw.gen.num(qs,1));
assert(all(found&found_q) && numel(unique(swbus))==n);
qr=qs(qi);binit=raw.swshunt.num(:,10);
assert(max(abs(m.bus(bi,6)-binit))<1e-9 && nnz(m.bus(:,6))==nnz(binit), ...
    'perform_source:ShuntAccounting','Canonical static BS differs from registered BINIT.');
blocks=strings(n,1);
for k=1:n
    parts=strings(0,1);
    for j=11:2:size(raw.swshunt.num,2)-1
        nj=numbers(raw.swshunt,j,k);bj=numbers(raw.swshunt,j+1,k);
        if isfinite(nj)&&isfinite(bj),parts(end+1)=string(nj)+"x"+string(bj);end %#ok<AGROW>
    end
    blocks(k)=strjoin(parts,";");
end
key="PERFORM2019:SWITCHED_SHUNT:"+string(swbus);
s=table(key,swbus,repmat("switched_shunt_frozen_as_bus_susceptance",n,1), ...
    numbers(raw.swshunt,4),numbers(raw.swshunt,2),binit,m.bus(bi,6), ...
    qr,raw.gen.num(qr,15),blocks,numbers(raw.swshunt,5),numbers(raw.swshunt,6), ...
    numbers(raw.swshunt,7),true(n,1),false(n,1), ...
    repmat("retain_canonical_BS_once_do_not_add_QS_generator_or_enable_switching",n,1), ...
    'VariableNames',{'device_key','source_bus','source_device_role','raw_switched_status', ...
    'raw_mode','raw_binit_mvar','canonical_bs_mvar','raw_QS_gen_row','raw_QS_status', ...
    'raw_blocks_count_times_mvar','raw_voltage_upper_pu','raw_voltage_lower_pu', ...
    'raw_remote_bus','already_in_canonical_bus_BS','add_as_generator','recommended_treatment'});
a=table("PERFORM2019:GEN:"+string(swbus)+":QS",key,swbus,qr, ...
    repmat("alternative_shunts_as_gen_only",n,1),false(n,1),true(n,1), ...
    'VariableNames',{'alternative_generator_key','canonical_shunt_key','source_bus', ...
    'raw_gen_row','source_representation','present_in_canonical_gen','present_in_canonical_bus_BS'});
end

function c = control_inventory(m,raw,g,b,s)
ng=height(g);type=repmat("PV_voltage_control",ng,1);
type(g.canonical_status<=0)="offline_generator_control";
type(g.source_device_role=="external_boundary_proxy")="boundary_proxy_PV_to_be_replaced_by_fixed_PQ";
type(g.source_device_role=="reference_placeholder")="reference_placeholder_to_be_removed";
c=table(g.device_key+":CONTROL",g.device_key,g.source_bus,type,g.canonical_status>0, ...
    g.regulated_bus,g.source_voltage_target_pu,g.source_qmin_mvar,g.source_qmax_mvar, ...
    g.q_bounds_are_placeholder,g.recommended_treatment, ...
    'VariableNames',{'control_key','device_key','source_bus','source_control_role', ...
    'canonical_enabled','regulated_bus','setpoint_pu','qmin_mvar','qmax_mvar', ...
    'bounds_are_placeholder','recommended_treatment'});
tx=b.source_device_role=="two_winding_transformer";nb=nnz(tx);
t=table(b.device_key(tx)+":TAP_CONTROL",b.device_key(tx),b.source_from_bus(tx), ...
    repmat("fixed_transformer_tap_no_automatic_control",nb,1),false(nb,1), ...
    b.raw_regulated_bus(tx),nan(nb,1),nan(nb,1),nan(nb,1),false(nb,1), ...
    repmat("retain_fixed_canonical_tap_and_shift_no_PAR_inferred",nb,1), ...
    'VariableNames',c.Properties.VariableNames);
assert(all(b.raw_transformer_control_mode(tx)==0),'perform_source:TransformerControl', ...
    'New active transformer control requires an explicit policy.');
ns=height(s);
t2=table(s.device_key+":CONTROL",s.device_key,s.source_bus, ...
    repmat("static_BINIT_switched_control_disabled",ns,1),false(ns,1), ...
    s.raw_remote_bus,nan(ns,1),nan(ns,1),nan(ns,1),false(ns,1),s.recommended_treatment, ...
    'VariableNames',c.Properties.VariableNames);
c=[c;t;t2];
c.raw_regulated_bus=c.regulated_bus;
c.regulated_bus(1:ng)=g.canonical_regulated_bus;
c.raw_remote_control_omitted=[g.raw_remote_control_omitted;false(nb+ns,1)];
c.source_control_role(c.raw_remote_control_omitted & c.canonical_enabled)= ...
    "PV_local_control_RAW_remote_target_not_implemented";
end

function t=unresolved_inventory(g,b,s)
t=table(strings(0,1),strings(0,1),strings(0,1),strings(0,1), ...
    'VariableNames',{'device_key','issue','electrical_use_policy','thermal_use_policy'});
for k=1:height(b)
    if startsWith(b.source_device_role(k),"ac_branch_unresolved")
        t=[t;{b.device_key(k),"line_cable_or_equivalent_not_identified", ...
            "retain_pinned_canonical_electrical_element","ineligible_until_physical_or_synthetic_realization_declared"}]; %#ok<AGROW>
    end
    if ~b.individual_circuit_identity_resolved(k)
        t=[t;{b.device_key(k),"electrically_identical_parallel_ID_assignment_ambiguous", ...
            "preserve_all_parallel_elements_and_candidate_ID_set","no_individual_physical_circuit_claim"}]; %#ok<AGROW>
    end
    if ~b.raw_canonical_parameters_match(k)
        t=[t;{b.device_key(k),"RAW_and_canonical_electrical_parameters_differ", ...
            "canonical_parameters_govern_RAW_is_identity_metadata","no_RAW_parameter_identity_claim"}]; %#ok<AGROW>
    end
end
for k=find(g.q_bounds_are_placeholder)'
    t=[t;{g.device_key(k),"source_9900_MVAr_placeholder_bounds", ...
        g.recommended_treatment(k),"not_a_conductor_device"}]; %#ok<AGROW>
end
for k=find(g.raw_canonical_status_mismatch)'
    t=[t;{g.device_key(k),"RAW_and_canonical_status_differ", ...
        "canonical_status_governs_no_implicit_reactivation","not_a_conductor_device"}]; %#ok<AGROW>
end
for k=find(g.raw_remote_control_omitted)'
    t=[t;{g.device_key(k),"RAW_remote_voltage_target_not_implemented_in_canonical_MATPOWER", ...
        g.recommended_treatment(k),"not_a_conductor_device"}]; %#ok<AGROW>
end
for k=1:height(s)
    t=[t;{s.device_key(k),"switching_blocks_not_enabled_in_static_canonical_case", ...
        s.recommended_treatment(k),"not_a_conductor_device"}]; %#ok<AGROW>
end
end

function r=add_role(r,mask,value)
r(mask & r=="junction")=value;
multi=mask & r~=value;r(multi)=r(multi)+"|"+value;
end

function value=numbers(section,column,rows)
if nargin<3,rows=(1:size(section.num,1))';end
value=section.num(rows,column);missing=isnan(value);
if any(missing),value(missing)=str2double(erase(string(section.txt(rows(missing),column)),"'"));end
end

function s=clean_id(s)
s=upper(strtrim(erase(string(s),"'")));
assert(all(~ismissing(s)&strlength(s)>0),'perform_source:BlankID','Stable source unit/circuit ID is missing.');
end

function s=clean_text(s)
s=strtrim(string(s));s(ismissing(s))="";
end

function sha=file_sha(path)
text=fileread(path);text=strrep(text,sprintf('\r\n'),sprintf('\n'));
text=strrep(text,sprintf('\r'),sprintf('\n'));
digest=java.security.MessageDigest.getInstance('SHA-256');digest.update(unicode2native(text,'UTF-8'));
sha=string(lower(reshape(dec2hex(typecast(digest.digest(),'uint8'),2).',1,[])));
end
