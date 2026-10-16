function out = validate_s13_phase1c_candidate(built,options)
%VALIDATE_S13_PHASE1C_CANDIDATE Recompute source identity and electrical gates.
% This deliberately validates construction, never electrical-model promotion.
if nargin<2,options=struct();end
if ~isfield(options,'fail_on_error'),options.fail_on_error=true;end
[PQ,~,~,~,BUS_I,BUS_TYPE,PD,QD,GS,BS,~,VM,VA,BASE_KV]=idx_bus;
[F_BUS,T_BUS,BR_R,~,~,~,~,~,~,~,~,~,~,~,~,~,~,ANGMIN,ANGMAX]=idx_brch;
[GEN_BUS,PG,QG,~,~,~,~,GEN_STATUS]=idx_gen;
[src,bm,em,~,sha]=s13_phase1c_source;
base=build_s13_phase1b_candidate(struct('write_outputs',false,'verbose',false));
m=built.candidate;r=built.phase1c_report;
gate=strings(0,1);passed=false(0,1);measured=zeros(0,1);limit=zeros(0,1);
added=bm.model_action=="appended_zero_injection_terminal";
mr=(263:262+height(em))';sr=em.source_branch_row;
[found,mi]=ismember(bm.model_bus,m.bus(:,BUS_I));[~,si]=ismember(bm.source_bus,src.bus(:,BUS_I));
add('dimensions',isequal([size(m.bus,1),size(m.branch,1),size(m.gen,1)], ...
    [149+sum(added),262+height(em),62]));
add('all_selected_terminals_present',all(found));
if ~all(found)||size(m.branch,1)<max(mr)
    finish();return
end
add('unique_model_bus_ids',numel(unique(m.bus(:,BUS_I)))==size(m.bus,1));
add('common_source_mva_base',m.baseMVA==src.baseMVA&&m.baseMVA==base.candidate.baseMVA);
add('immutable_phase1b_bus_rows',isequaln(m.bus(1:149,:),base.candidate.bus));
add('immutable_phase1b_branch_rows',isequaln(m.branch(1:262,:),base.candidate.branch));
add('immutable_phase1b_generators',isequaln(m.gen,base.candidate.gen));
add('immutable_phase1a_report',isequaln(built.phase1a_report,base.phase1a_report));
add('immutable_phase1b_report',isequaln(built.phase1b_report,base.phase1b_report));
add('source_sha256',string(r.source_sha256)==sha);
add('source_bus_manifest',isequaln(r.source_bus_manifest,bm));
add('source_branch_manifest',isequaln(r.source_branch_manifest,em));
add('source_bus_names',isequal(upper(strtrim(string(m.bus_name(mi)))),upper(strtrim(bm.source_bus_name))));
add('source_voltage_levels',isequal(m.bus(mi,BASE_KV),src.bus(si,BASE_KV)));
add('physical_zone_H_I_distinction',isequal(string(m.userdata.nyiso_physical_zone(mi)),bm.physical_zone));
add('zero_injection_added_terminals',all(m.bus(mi(added),[PD QD GS BS])==0,'all'));
add('added_terminals_PQ',all(m.bus(mi(added),BUS_TYPE)==PQ));
add('added_terminal_voltage_limits',isequal(m.bus(mi(added),12:13),src.bus(si(added),12:13)));
[~,f]=ismember(em.source_from_bus,bm.source_bus);[~,t]=ismember(em.source_to_bus,bm.source_bus);
add('source_branch_endpoints',isequal(m.branch(mr,[F_BUS T_BUS]),[bm.model_bus(f),bm.model_bus(t)]));
add('source_branch_parameters_and_controls',isequal(m.branch(mr,3:11),src.branch(sr,3:11)));
add('neutral_branch_angle_limits',all(m.branch(mr,ANGMIN)==-360)&all(m.branch(mr,ANGMAX)==360));
add('traceable_unique_source_rows',isequal(r.branch_map.source_branch_row,sr)&& ...
    isequal(r.branch_map.model_branch_row,mr));
add('registered_branch_endpoints',isequal(r.branch_map.model_from_bus,bm.model_bus(f))&& ...
    isequal(r.branch_map.model_to_bus,bm.model_bus(t))&& ...
    isequal(r.branch_map.source_from_bus,em.source_from_bus)&& ...
    isequal(r.branch_map.source_to_bus,em.source_to_bus));
paramnames={'source_r_pu','source_x_pu','source_b_pu','source_rate_a_mva', ...
    'source_rate_b_mva','source_rate_c_mva'};
add('registered_source_parameters',isequal(table2array(r.branch_map(:,paramnames)), ...
    table2array(em(:,paramnames))));
add('no_fabricated_circuit_ids',isequal(r.branch_map.source_circuit_id,"PERFORM_ROW_"+string(sr)));
add('no_phase1c_dlr_flags',~any(r.branch_map.dlr_eligible)&&~any(r.physical_register.dlr_eligible));
add('metadata_report_consistency',isequaln(m.userdata.s13.phase1c_report,r)&& ...
    isequaln(m.userdata.s13.overlay_report,built.overlay_report));
add('cumulative_phase1c_branch_register',isequaln(built.overlay_report.branch_map(end-height(em)+1:end,:),r.branch_map));
add('cumulative_phase1c_bus_register',isequaln(built.overlay_report.bus_map(end-sum(added)+1:end,:),r.bus_map));
add('cumulative_phase1c_physical_register',isequaln(built.overlay_report.physical_register(end-height(em)+1:end,:),r.physical_register));
common=intersect(r.branch_map.Properties.VariableNames,r.physical_register.Properties.VariableNames);
add('physical_branch_register_agreement',isequaln(r.branch_map(:,common),r.physical_register(:,common)));
fields={'bus_map','branch_map','physical_register','operator_map','path_register', ...
    'residual_register','residual_shunt_register'};
for k=1:numel(fields)
    old=base.overlay_report.(fields{k});new=built.overlay_report.(fields{k});
    add(['immutable_register_' fields{k}],height(new)>=height(old)&& ...
        isequaln(new(1:height(old),:),old));
end
a=r.injection_audit;
add('source_device_audit_complete',height(a)==height(bm)&& ...
    isequal(a.source_bus,bm.source_bus)&&isequal(a.model_bus,bm.model_bus)&& ...
    isequal(a.source_pd_mw,src.bus(si,PD))&&isequal(a.source_qd_mvar,src.bus(si,QD))&& ...
    isequal(a.source_gs_mw,src.bus(si,GS))&&isequal(a.source_bs_mvar,src.bus(si,BS)));
pg=zeros(height(bm),1);qg=pg;ng=pg;
for k=1:height(bm)
    g=src.gen(:,GEN_BUS)==bm.source_bus(k)&src.gen(:,GEN_STATUS)>0;
    pg(k)=sum(src.gen(g,PG));qg(k)=sum(src.gen(g,QG));ng(k)=sum(g);
end
add('source_generation_audit',isequal(a.source_pg_mw,pg)&&isequal(a.source_qg_mvar,qg)&& ...
    isequal(a.active_source_generators,ng));
add('overlaps_explicitly_unresolved',~isempty(r.overlap_audit)&&~any(r.overlap_audit.resolved));
add('construction_and_delivery_fail_closed',~m.userdata.s13.construction_source_qualified&& ...
    ~m.userdata.s13.promotion_eligible&&~m.userdata.s13.dlr_delivery_eligible&& ...
    ~m.userdata.npcc_perform_overlay.construction_source_qualified&& ...
    ~m.userdata.npcc_perform_overlay.promotion_eligible&& ...
    ~m.userdata.npcc_perform_overlay.dlr_delivery_eligible&& ...
    ~r.construction_source_qualified&&~r.promotion_eligible&&~r.dlr_delivery_eligible);

% Stamp source and candidate independently into the source-terminal order.
% This exercises R/X/B, transformer ratio/shift and all 53 parallel rows.
sbranch=src.branch(sr,1:13);sbranch(:,1)=f;sbranch(:,2)=t;
cbranch=m.branch(mr,1:13);
[~,cbranch(:,1)]=ismember(cbranch(:,1),bm.model_bus);
[~,cbranch(:,2)]=ismember(cbranch(:,2),bm.model_bus);
bus=src.bus(si,1:13);bus(:,BUS_I)=(1:height(bm))';bus(:,[GS BS])=0;
[ys,yfs,yts]=makeYbus(src.baseMVA,bus,sbranch);
[yc,yfc,ytc]=makeYbus(m.baseMVA,bus,cbranch);
err=norm(yc-ys,'fro');addnum('admittance_identity',err,1e-10);
v=src.bus(si,VM).*exp(1i*pi/180*src.bus(si,VA));
err=max(abs([yfc*v-yfs*v;ytc*v-yts*v]));addnum('terminal_current_identity',err,1e-10);
mineig=min(real(eig(full((yc+yc')/2))));
addnum('passive_admittance_negative_eigenvalue',max(0,-mineig),1e-9);
add('nonnegative_series_resistance',all(cbranch(:,BR_R)>=0));
G=graph(cbranch(:,1),cbranch(:,2),[],height(bm));
add('connected_source_mesh',numel(unique(conncomp(G)))==1);
op=r.operator_map;
add('public_operator_claims_blocked',~any(op.is_exact_public_operator));
zf=bm.physical_zone(f);zt=bm.physical_zone(t);
expected=find((zf=="I"&zt=="J")|(zf=="J"&zt=="I")| ...
    (zf=="K"&zt=="J")|(zf=="J"&zt=="K")| ...
    (zf=="H"&zt=="I")|(zf=="I"&zt=="H"));
add('complete_selected_component_operators',isequal(sort(op.model_branch_row),sort(mr(expected))));
ok=true;
for k=1:height(op)
    j=find(mr==op.model_branch_row(k));
    if numel(j)~=1,ok=false;continue;end
    pair=[bm.physical_zone(f(j)),bm.physical_zone(t(j))];
    name=op.interface_name(k);
    if name=="Dunwoodie_I_J_source_component",wanted=["I","J"];
    elseif name=="Dunwoodie_K_J_source_component",wanted=["K","J"];
    elseif name=="H_I_northern_approach",wanted=["H","I"];
    else,ok=false;continue;end
    if op.operator_sign(k)==-1,pair=fliplr(pair);end
    ok=ok&&isequal(pair,wanted);
end
add('component_operator_zone_orientation',ok);
finish();

    function add(name,value)
        gate(end+1,1)=string(name);passed(end+1,1)=logical(value);
        measured(end+1,1)=double(~value);limit(end+1,1)=0;
    end
    function addnum(name,value,tolerance)
        gate(end+1,1)=string(name);passed(end+1,1)=isfinite(value)&&value<=tolerance;
        measured(end+1,1)=value;limit(end+1,1)=tolerance;
    end
    function finish()
        gates=table(gate,passed,measured,limit);
        out=struct('gates',gates,'all_passed',all(passed),'promotion_eligible',false, ...
            'scope','source_row_identity_and_passive_construction_only');
        if options.fail_on_error&&~out.all_passed
            error('validate_s13_phase1c_candidate:GateFailure','Failed: %s',strjoin(gate(~passed),', '));
        end
    end
end
