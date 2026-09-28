function out = build_s13_phase1c_candidate(options)
%BUILD_S13_PHASE1C_CANDIDATE Reproducible, unpromoted downstate topology.
% Copies a connected 23-terminal/53-element PERFORM subnetwork, reusing
% Millwood and East Garden City. Source injections are audited, not copied.
% The Phase 1B wrapper and its canonical CSVs are never overwritten.
if nargin < 1, options = struct(); end
if ~isfield(options,'write_outputs'), options.write_outputs = true; end
if ~isfield(options,'verbose'), options.verbose = true; end
h = fileparts(mfilename('fullpath'));
if ~isfield(options,'output_dir'), options.output_dir = h; end
addpath(h); addpath(fileparts(h));
define_constants;
[src, bm, em, source_path, source_sha] = s13_phase1c_source;
base = build_s13_phase1b_candidate(struct('write_outputs',false,'verbose',false));
m = base.candidate;
assert(size(m.bus,1)==149 && size(m.branch,1)==262, ...
    'build_s13_phase1c_candidate:Parent','Unexpected Phase 1B dimensions.');
[~, si] = ismember(bm.source_bus,src.bus(:,BUS_I));
added = bm.model_action == "appended_zero_injection_terminal";
assert(~any(ismember(bm.model_bus(added),m.bus(:,BUS_I))), ...
    'build_s13_phase1c_candidate:DuplicateBus','An appended ID already exists.');
zmeta = nyiso_zone_metadata;
for k = 1:height(bm)
    if ~added(k)
        j = find(m.bus(:,BUS_I)==bm.model_bus(k));
        assert(numel(j)==1 && upper(strtrim(string(m.bus_name{j}))) == ...
            upper(strtrim(bm.source_bus_name(k))) && ...
            m.bus(j,BASE_KV)==bm.source_base_kv(k) && ...
            string(m.userdata.nyiso_physical_zone{j})==bm.physical_zone(k), ...
            'build_s13_phase1c_candidate:Attachment','Attachment identity mismatch.');
        continue
    end
    row = zeros(1,size(m.bus,2)); row(1:13) = src.bus(si(k),1:13);
    row(BUS_I)=bm.model_bus(k); row(BUS_TYPE)=PQ;
    row([PD QD GS BS])=0; row(BUS_AREA)=3;
    % Initial guesses only, with the same source phasor frame as Millwood.
    anchor=find(m.bus(:,BUS_I)==74); sa=find(src.bus(:,BUS_I)==897);
    row(VA)=row(VA)+m.bus(anchor,VA)-src.bus(sa,VA);
    row(VM)=row(VM)*m.bus(anchor,VM)/src.bus(sa,VM);
    m.bus(end+1,:)=row; m.bus_name{end+1,1}=char(bm.source_bus_name(k));
    zi=find(string({zmeta.letter})==bm.physical_zone(k));
    entry=struct('bus_id',bm.model_bus(k),'physical_zone',zmeta(zi).letter, ...
        'load_allocation_group',zmeta(zi).letter,'nyiso_zone_name',zmeta(zi).name, ...
        'nyiso_zone_id',zmeta(zi).id,'perform_zone_code',zmeta(zi).perform_zone_code);
    m.userdata.ny_lite.transit_zone_metadata(end+1)=entry;
end
sr=em.source_branch_row; mr=(263:262+height(em))';
[~,f]=ismember(em.source_from_bus,bm.source_bus);
[~,t]=ismember(em.source_to_bus,bm.source_bus);
br=zeros(height(em),size(m.branch,2)); br(:,1:13)=src.branch(sr,1:13);
br(:,F_BUS)=bm.model_bus(f); br(:,T_BUS)=bm.model_bus(t);
br(:,ANGMIN)=-360; br(:,ANGMAX)=360; m.branch=[m.branch;br];
m=attach_nyiso_zone_metadata(m);

% All nonzero source devices remain explicit unresolved operating inputs.
ng=zeros(height(bm),1); pg=ng; qg=ng;
for k=1:height(bm)
    g=src.gen(:,GEN_BUS)==bm.source_bus(k) & src.gen(:,GEN_STATUS)>0;
    ng(k)=sum(g); pg(k)=sum(src.gen(g,PG)); qg(k)=sum(src.gen(g,QG));
end
injections=table(bm.source_bus,bm.model_bus,src.bus(si,PD),src.bus(si,QD), ...
    src.bus(si,GS),src.bus(si,BS),ng,pg,qg, ...
    repmat("source_devices_not_copied_pending_aggregate_redistribution",height(bm),1), ...
    'VariableNames',{'source_bus','model_bus','source_pd_mw','source_qd_mvar', ...
    'source_gs_mw','source_bs_mvar','active_source_generators','source_pg_mw', ...
    'source_qg_mvar','policy'});

% Form the same seven register schemas without changing the older rows.
r=base.overlay_report;
b=blank(r.bus_map,sum(added)); ids=find(added);
for k=1:numel(ids)
    j=ids(k); s=si(j);
    b.model_bus(k)=bm.model_bus(j); b.model_bus_name(k)=bm.source_bus_name(j);
    b.model_action(k)="appended_physical_terminal";
    b.terminal_electrical_policy(k)="pq_zero_injection_devices_audited_separately";
    b.overlay_path_id(k)="phase1c_downstate_mesh";
    b.npcc_attachment_bus(k)=74; b.source_attachment_bus(k)=897;
    b.source_model(k)="full_PERFORM_2019_case"; b.source_case(k)=source_path;
    b.source_bus(k)=bm.source_bus(j); b.source_bus_name(k)=bm.source_bus_name(j);
    b.source_base_kv(k)=src.bus(s,BASE_KV); b.source_area(k)=src.bus(s,BUS_AREA);
    b.model_area(k)=3; b.physical_zone(k)=bm.physical_zone(j);
    b.source_vm_pu(k)=src.bus(s,VM); b.source_va_deg(k)=src.bus(s,VA);
    b.source_pd_mw(k)=src.bus(s,PD); b.source_qd_mvar(k)=src.bus(s,QD);
    b.source_gs_mw(k)=src.bus(s,GS); b.source_bs_mvar(k)=src.bus(s,BS);
    b.mapping_confidence(k)="exact_source_row_name_voltage_zone";
    b.implementation_status(k)="implemented_unpromoted_phase1c";
end
e=blank(r.branch_map,height(em));
e.model_branch_row=mr; e.model_from_bus=br(:,F_BUS); e.model_to_bus=br(:,T_BUS);
e.overlay_path_id(:)="phase1c_downstate_mesh";
e.npcc_attachment_from_bus(:)=74; e.npcc_attachment_to_bus(:)=9003;
e.source_model(:)="full_PERFORM_2019_case"; e.source_case(:)=source_path;
e.source_branch_row=sr; e.source_from_bus=em.source_from_bus; e.source_to_bus=em.source_to_bus;
% These are source-row keys, deliberately not fabricated PSS/E circuit IDs.
e.source_circuit_id="PERFORM_ROW_"+string(sr);
cols={'source_r_pu','source_x_pu','source_b_pu','source_rate_a_mva', ...
    'source_rate_b_mva','source_rate_c_mva'};
for k=1:numel(cols), e.(cols{k})=em.(cols{k}); end
e.branch_classification(:)="source_circuit_raw_id_unresolved";
e.branch_classification(src.bus(si(f),BASE_KV)~=src.bus(si(t),BASE_KV))= ...
    "source_transformer_raw_id_unresolved";
e.construction_method(:)="direct_perform_electrical_copy_neutral_angle_bounds";
e.dlr_eligible(:)=false; e.dlr_data_status(:)="electrical_scope_only";
e.mapping_confidence(:)="exact_sha256_source_row_electrical_identity";
e.residual_overlap_status(:)="unresolved_aggregate_overlap_no_fit";
e.implementation_status(:)="implemented_unpromoted_phase1c";
p=blank(r.physical_register,height(e));
shared=intersect(e.Properties.VariableNames,p.Properties.VariableNames);
for k=1:numel(shared),p.(shared{k})=e.(shared{k});end
path=blank(r.path_register,1);
path.overlay_path_id="phase1c_downstate_mesh"; path.phase_id="phase1c";
path.npcc_attachment_from_bus=74;path.npcc_attachment_to_bus=9003;
path.source_attachment_from_bus=897;path.source_attachment_to_bus=589;
path.from_zone="H";path.to_zone="K";
path.implementation_status="implemented_unpromoted_phase1c";
path.mapping_confidence="source_row_identity_operating_devices_unmapped";
operators=component_operators(r.operator_map,e,bm,f,t);
r.bus_map=[r.bus_map;b];r.branch_map=[r.branch_map;e];
r.physical_register=[r.physical_register;p];r.path_register=[r.path_register;path];
r.operator_map=[r.operator_map;operators];
r.phase_id='cumulative_through_phase1c';r.current_phase='phase1c';
r.included_phases=["phase1a";"phase1b";"phase1c"];r.phase_count=3;
r.buses_added=r.buses_added+sum(added);r.branches_added=r.branches_added+height(em);
r.case_size=[size(m.bus,1),size(m.branch,1),size(m.gen,1)];
r.physical_branch_rows=r.branch_map.model_branch_row;r.source_branch_rows=r.branch_map.source_branch_row;
r.added_bus_ids=[base.candidate.userdata.npcc_perform_overlay.added_bus_ids;bm.model_bus(added)];
r.added_bus_rows=[base.candidate.userdata.npcc_perform_overlay.added_bus_rows;(150:size(m.bus,1))'];
r.operator_status='partial_cumulative_source_operator_components';

% CE UG is an aggregate Zone-I proxy, not a source Dunwoodie attachment.
% Its incident old branches are candidates for a future joint port fit.
old=base.candidate.branch;
overlap_rows=find(ismember(old(:,F_BUS),[74 78 79 82 9003]) & ...
    ismember(old(:,T_BUS),[74 78 79 82 9003]));
overlaps=table(overlap_rows,old(overlap_rows,F_BUS),old(overlap_rows,T_BUS), ...
    repmat("possible_downstate_aggregate_overlap",numel(overlap_rows),1), ...
    repmat("unchanged_pending_terminal_and_injection_correspondence",numel(overlap_rows),1), ...
    false(numel(overlap_rows),1),'VariableNames',{'model_branch_row','from_bus', ...
    'to_bus','classification','action','resolved'});
coverage=table(["H_to_J_approach";"I_to_J_cut";"K_to_J_cut";"Lake_Success"; ...
    "CE_UG_to_Dunwoodie";"downstate_load_and_generation";"passive_residualization"], ...
    ["source_backed_via_physical_Zone_I";"explicit_345_and_138_kv_components"; ...
    "partial_Tremont_Great_Neck_and_Jamaica_Valley_Stream";"source_identity_unresolved"; ...
    "aggregate_proxy_mapping_unresolved";"source_devices_audited_not_transferred"; ...
    "blocked_without_common_terminal_and_operating_evidence"], ...
    'VariableNames',{'requirement','status'});
report=struct('phase_id','phase1c','bus_map',b,'branch_map',e,'physical_register',p, ...
    'operator_map',operators,'path_register',path,'source_bus_manifest',bm, ...
    'source_branch_manifest',em,'source_sha256',source_sha, ...
    'source_hash_policy','sha256_utf8_text_lf_normalized', ...
    'injection_audit',injections, ...
    'overlap_audit',overlaps,'coverage',coverage,'buses_added',sum(added), ...
    'branches_added',height(em),'added_bus_ids',bm.model_bus(added), ...
    'physical_branch_rows',mr,'source_branch_rows',sr,'case_size',r.case_size, ...
    'construction_source_qualified',false,'promotion_eligible',false, ...
    'dlr_delivery_eligible',false,'status','partial_downstate_construction_checkpoint');
m.userdata.s13.current_phase='phase1c';m.userdata.s13.status=report.status;
m.userdata.s13.phase_reports.phase1c=report;m.userdata.s13.phase1c_report=report;
m.userdata.s13.overlay_report=r;
m.userdata.s13.construction_blockers={ ...
    'Downstate aggregate injection and control mapping unresolved', ...
    'Lake Success and complete public operator identity unresolved', ...
    'Passive residual equivalents and full-NPCC operating-source qualification pending'};
m.userdata.npcc_perform_overlay.current_phase='phase1c';
m.userdata.npcc_perform_overlay.added_bus_ids=[m.userdata.npcc_perform_overlay.added_bus_ids;bm.model_bus(added)];
m.userdata.npcc_perform_overlay.added_bus_rows=[m.userdata.npcc_perform_overlay.added_bus_rows;(150:size(m.bus,1))'];
m.userdata.npcc_perform_overlay.physical_branch_rows=r.physical_branch_rows;
m.userdata.npcc_perform_overlay.source_branch_rows=r.source_branch_rows;
out=struct('candidate',m,'phase1c_report',report,'overlay_report',r, ...
    'phase1b_report',base.phase1b_report,'phase1a_report',base.phase1a_report, ...
    'phase_reports',m.userdata.s13.phase_reports);
out.validation=validate_s13_phase1c_candidate(out,struct('fail_on_error',true));
if options.write_outputs
    if ~isfolder(options.output_dir),mkdir(options.output_dir);end
    fields={'bus_map','branch_map','physical_register','operator_map','path_register', ...
        'injection_audit','overlap_audit','coverage'};
    for k=1:numel(fields)
        ny_lite_writetable_lf(report.(fields{k}),fullfile(options.output_dir, ...
            ['s13_phase1c_' fields{k} '.csv']));
    end
    ny_lite_writetable_lf(out.validation.gates,fullfile(options.output_dir,'s13_phase1c_validation.csv'));
end
if options.verbose
    fprintf('Phase 1C partial checkpoint: %d buses, %d branches, %d generators; promotion blocked.\n',r.case_size);
end
end

function t=blank(prototype,n)
t=table();
for name=string(prototype.Properties.VariableNames)
    value=prototype.(name);
    if isstring(value),t.(name)=strings(n,size(value,2));
    elseif islogical(value),t.(name)=false(n,size(value,2));
    else,t.(name)=zeros(n,size(value,2),'like',value);end
end
end

function o=component_operators(prototype,e,b,f,t)
o=prototype([],:);zf=b.physical_zone(f);zt=b.physical_zone(t);
families=["I" "J";"K" "J";"H" "I"];
labels=["Dunwoodie_I_J_source_component";"Dunwoodie_K_J_source_component";"H_I_northern_approach"];
for k=1:size(families,1)
    positive=zf==families(k,1)&zt==families(k,2);
    negative=zf==families(k,2)&zt==families(k,1);
    take=find(positive|negative);part=blank(prototype,numel(take));
    part.interface_name(:)=labels(k);part.component_name=e.source_circuit_id(take);
    part.model_branch_row=e.model_branch_row(take);part.operator_sign=double(positive(take))-double(negative(take));
    part.source_branch_row=e.source_branch_row(take);part.source_circuit_id=e.source_circuit_id(take);
    part.is_exact_public_operator(:)=false;part.operator_status(:)="partial_source_zone_cut_not_public_operator";
    part.notes(:)="Use source-side to-end power for received imports; signed from-end convention includes directional losses.";
    o=[o;part]; %#ok<AGROW>
end
end
