function [segments,ledger,conductors]=nygrid_handoff_thermal_candidates(m)
% Conservative source-keyed/design-line whitelist, not all synthetic OH labels.
% Eligibility supports a synthetic research screen, never installed-asset use.
root=fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
reg=readtable(fullfile(root,'output','nygrid_2025_ac_system','branches','branch_assignments.csv'),'TextType','string');
for name={'branch_key','classification','source_role','parameter_basis'}
    reg.(name{1})=fillmissing(string(reg.(name{1})), 'constant', "");
end
conductors=readtable(fullfile(root,'output','nygrid_2025_ac_system','engineering','thermal_conductors.csv'),'TextType','string');
assert(isfield(m.userdata,'ac_loss_revision')&&strcmp(m.userdata.ac_loss_revision.impedance_mode,'released_equivalent'), ...
    'handoff:RevisedCase','Use the released-equivalent loss-consistent PF case.');
allsegments=m.userdata.ac_system.thermal_segments;
if iscell(allsegments),allsegments=struct2table([allsegments{:}]);elseif isstruct(allsegments),allsegments=struct2table(allsegments);end
for key={'branch_row','circuits','bundle_count','base_kv','segment_length_m','reference_temperature_c','temperature_min_c','temperature_max_c'}
    allsegments.(key{1})=double(allsegments.(key{1}));
end
for key={'branch_key','segment_id','catalog_id'},allsegments.(key{1})=string(allsegments.(key{1}));end
parents=double(m.userdata.ac_system.branch_parent_row(:));keys=string(m.userdata.ac_system.branch_keys(:));
assert(all(keys(allsegments.branch_row)==allsegments.branch_key));
map=m.userdata.ac_sections.branch_map;np=max(parents);rows=struct([]);keep=false(height(allsegments),1);
[known_catalog,ci]=ismember(allsegments.catalog_id,string(conductors.catalog_id));
for p=1:np
    r=find(parents==p);[found,k]=ismember(p,double(reg.branch_row));assert(found);
    first=r(map.physical_terminal_from(r));last=r(map.physical_terminal_to(r));assert(isscalar(first)&&isscalar(last));
    [okf,f]=ismember(m.branch(r,1),m.bus(:,1));[okt,t]=ismember(m.branch(r,2),m.bus(:,1));assert(all(okf&okt));
    active=all(m.branch(r,11)>0);same_voltage=all(abs(m.bus(f,10)-m.bus(t,10))<1e-9);
    unity_tap=all(m.branch(r,9)==0|m.branch(r,9)==1);zero_phase=all(m.branch(r,10)==0);
    classification=string(reg.classification(k));role=string(reg.source_role(k));basis=string(reg.parameter_basis(k));
    source_circuit=role=="exact_historical_source_circuit";
    documented_design=classification=="design_based_overhead"&&basis=="preserved_source_design_line_only_R_X_B";
    overhead=ismember(classification,["synthetic_overhead_corridor","design_based_overhead"]);
    source_keyed=source_circuit||documented_design;
    sg=find(ismember(allsegments.branch_row,r));catalog_ok=~isempty(sg)&&all(known_catalog(sg));
    segment_kv_matches=false;
    if ~isempty(sg)
        [~,sf]=ismember(m.branch(allsegments.branch_row(sg),1),m.bus(:,1));
        [~,st]=ismember(m.branch(allsegments.branch_row(sg),2),m.bus(:,1));
        segment_kv_matches=all(abs(allsegments.base_kv(sg)-m.bus(sf,10))<1e-9) ...
            &&all(abs(allsegments.base_kv(sg)-m.bus(st,10))<1e-9);
    end
    valid_segments=catalog_ok&&segment_kv_matches&&all(allsegments.segment_length_m(sg)>0)&&all(allsegments.circuits(sg)>=1) ...
        &&all(allsegments.bundle_count(sg)>=1)&&all(asbool(allsegments.bare_overhead_thermal_model_applicable(sg)));
    R_match=false;
    if valid_segments
        R_match=true;
        for rr=r(:)'
            sr=sg(allsegments.branch_row(sg)==rr);if isempty(sr),R_match=false;break;end
            ohms=0;
            try
                for z=sr(:)'
                    resistance=ac_conductor_resistance(conductors(ci(z),:),allsegments.reference_temperature_c(z));
                    ohms=ohms+resistance*allsegments.segment_length_m(z)/(allsegments.circuits(z)*allsegments.bundle_count(z));
                end
                expected=ohms/(allsegments.base_kv(sr(1))^2/m.baseMVA);
                R_match=R_match&&abs(m.branch(rr,3)-expected)<max(1e-10,1e-8*abs(expected));
            catch
                R_match=false;
            end
        end
    end
    reasons=strings(0,1);
    if ~active,reasons(end+1)="inactive_or_inconsistent_runtime_status";end
    if p==224,reasons(end+1)="released_network_equivalent_not_an_identified_conductor";end
    if ismember(p,[300 309 310 386]),reasons(end+1)="known_source_identity_or_overhead_vs_cable_conflict";end
    if ~overhead,reasons(end+1)="non_overhead_class_"+classification;end
    if ~source_keyed,reasons(end+1)="no_specific_historical_circuit_or_documented_line_design_provenance";end
    if ~same_voltage,reasons(end+1)="voltage_changing_object";end
    if ~unity_tap,reasons(end+1)="nonunity_transformer_tap";end
    if ~zero_phase,reasons(end+1)="phase_shifter_or_PAR";end
    if ~isempty(sg)&&~segment_kv_matches,reasons(end+1)="segment_voltage_base_differs_from_electrical_endpoints";end
    if ~valid_segments,reasons(end+1)="missing_or_incompatible_conductor_segment_realization";end
    if valid_segments&&~R_match,reasons(end+1)="electrical_R_differs_from_catalog_reference_temperature";end
    eligible=isempty(reasons);
    if eligible
        keep(sg)=true;
        if documented_design,tier='design_line_with_unverified_installed_conductor_and_equipment';else,tier='historical_circuit_key_with_synthetic_conductor_realization';end
        reason='admitted_for_synthetic_research_screen_only';
    else,tier='excluded';reason=char(join(reasons,'; '));end
    row=struct('original_parent_row',p,'original_corridor_key',char(reg.branch_key(k)), ...
        'from_bus',m.branch(first,1),'to_bus',m.branch(last,2),'classification',char(classification), ...
        'source_role',char(role),'parameter_basis',char(basis),'active',active,'same_voltage',same_voltage, ...
        'unity_tap',unity_tap,'zero_phase',zero_phase,'thermal_segment_count',numel(sg), ...
        'segment_base_kv_matches_endpoints',segment_kv_matches, ...
        'catalog_reference_R_matches',R_match,'source_keyed_or_documented_design',source_keyed, ...
        'research_screen_eligible',eligible,'eligibility_tier',tier,'reason',reason, ...
        'installed_asset_DLR_verified',false);
    rows=[rows row]; %#ok<AGROW>
end
segments=allsegments(keep,:);ledger=struct2table(rows);
assert(~any(ismember(parents(segments.branch_row),[224 300 309 310 386])));
assert(all(segments.circuits==fix(segments.circuits))&&all(segments.bundle_count==fix(segments.bundle_count)));
end

function value=asbool(value)
if islogical(value),return;end
if isnumeric(value),value=value~=0;else,value=ismember(lower(string(value)),["true","1"]);end
end
