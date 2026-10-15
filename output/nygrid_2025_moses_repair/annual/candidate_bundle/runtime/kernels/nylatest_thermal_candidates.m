function [segments,ledger,conductors,forward]=nylatest_thermal_candidates(m)
%NYGRID_RX_THERMAL_CANDIDATES R/X-conditioned synthetic conductor screening.
% Reuses the current case's declared thermal metadata without changing m.
% Installed circuit identity is not required. Catalog/geometry forward R AND
% X must match every electrical section. B mismatch is disclosed separately.
data=nylatest_data();
reg=data.thermal.branch_registry;conductors=data.thermal.conductors;
geometry=data.thermal.geometry;conflicts=data.thermal.cable_conflicts;
assert(isequal(sort(double(conflicts.branch_row)),[300;309;310;386]),'rxThermal:ConflictLedger','Unexpected cable-conflict identity ledger.');
for name={'branch_key','classification','source_role','parameter_basis'}
    reg.(name{1})=fillmissing(string(reg.(name{1})),'constant',"");
end
assert(isfield(m.userdata,'ac_loss_revision')&&strcmp(m.userdata.ac_loss_revision.impedance_mode,'released_equivalent'), ...
    'rxThermal:Case','Use the unchanged released-equivalent loss-consistent AC case.');
assert(~m.userdata.ac_system.current_gamma_lift&&m.baseMVA>0,'rxThermal:CurrentBase','Use the actual synthetic AC current base without gamma lifting.');
assert(numel(unique(string(conductors.catalog_id)))==height(conductors),'rxThermal:Catalog','Duplicate conductor catalog IDs.');
allsegments=m.userdata.ac_system.thermal_segments;
if iscell(allsegments),allsegments=struct2table([allsegments{:}]);elseif isstruct(allsegments),allsegments=struct2table(allsegments);end
required={'branch_row','branch_key','segment_id','catalog_id','segment_length_m','circuits','bundle_count','base_kv', ...
    'gmd_m','bundle_spacing_m','reference_temperature_c','temperature_min_c','temperature_max_c', ...
    'bare_overhead_thermal_model_applicable','reference_r_pu','reference_x_pu'};
assert(istable(allsegments)&&all(ismember(required,allsegments.Properties.VariableNames)),'rxThermal:SegmentSchema','Incomplete declared thermal segment metadata.');
for name={'branch_row','segment_length_m','circuits','bundle_count','base_kv','gmd_m','bundle_spacing_m', ...
        'reference_temperature_c','temperature_min_c','temperature_max_c','reference_r_pu','reference_x_pu'}
    allsegments.(name{1})=double(allsegments.(name{1}));
end
for name={'branch_key','segment_id','catalog_id'},allsegments.(name{1})=string(allsegments.(name{1}));end
parents=double(m.userdata.ac_system.branch_parent_row(:));keys=string(m.userdata.ac_system.branch_keys(:));
map=m.userdata.ac_sections.branch_map;np=max(parents);ns=height(allsegments);
assert(all(isfinite(allsegments.branch_row)&allsegments.branch_row==fix(allsegments.branch_row) ...
    &allsegments.branch_row>=1&allsegments.branch_row<=size(m.branch,1)),'rxThermal:SegmentRows','Invalid runtime branch row.');
assert(all(keys(allsegments.branch_row)==allsegments.branch_key),'rxThermal:SegmentKeys','Thermal segment keys do not match the electrical section axes.');
assert(numel(unique(allsegments.branch_key+"::"+allsegments.segment_id))==ns,'rxThermal:SegmentKeys','Duplicate segment keys.');
if ismember('original_branch_row',allsegments.Properties.VariableNames)
    assert(all(double(allsegments.original_branch_row)==parents(allsegments.branch_row)), ...
        'rxThermal:ParentKeys','Thermal parent and electrical parent axes differ.');
end
[known_catalog,ci]=ismember(allsegments.catalog_id,string(conductors.catalog_id));
valid=false(ns,1);segment_reason=strings(ns,1);policy=strings(ns,1);
r_calc=nan(ns,1);x_calc=nan(ns,1);b_calc=nan(ns,1);gmr_bundle=nan(ns,1);
for j=1:ns
    s=allsegments(j,:);p=parents(s.branch_row);[found,k]=ismember(p,double(reg.branch_row));assert(found);
    reasons=strings(0,1);[okf,f]=ismember(m.branch(s.branch_row,1),m.bus(:,1));[okt,t]=ismember(m.branch(s.branch_row,2),m.bus(:,1));assert(okf&&okt);
    if ~known_catalog(j),reasons(end+1)="unknown_catalog_id";end
    if ~asbool(s.bare_overhead_thermal_model_applicable),reasons(end+1)="not_a_bare_overhead_realization";end
    if ismember('current_gamma_lift',s.Properties.VariableNames)&&asbool(s.current_gamma_lift)
        reasons(end+1)="gamma_scaled_thermal_current_metadata";
    end
    if abs(s.base_kv-m.bus(f,10))>1e-9||abs(s.base_kv-m.bus(t,10))>1e-9
        reasons(end+1)="segment_voltage_base_differs_from_electrical_endpoints";
    end
    mult=isfinite(s.circuits)&&s.circuits>=1&&s.circuits==fix(s.circuits) ...
        &&isfinite(s.bundle_count)&&s.bundle_count>=1&&s.bundle_count<=8&&s.bundle_count==fix(s.bundle_count);
    if ~mult,reasons(end+1)="nonphysical_circuit_or_bundle_multiplicity";end
    dims=all(isfinite([s.segment_length_m s.base_kv s.gmd_m s.bundle_spacing_m])) ...
        &&all([s.segment_length_m s.base_kv s.gmd_m s.bundle_spacing_m]>0);
    if ~dims,reasons(end+1)="nonpositive_or_nonfinite_geometry_dimension";end
    [has_geometry,gi]=ismember(s.base_kv,double(geometry.nominal_kv));
    design=string(reg.classification(k))=="design_based_overhead" ...
        &&string(reg.parameter_basis(k))=="preserved_source_design_line_only_R_X_B" ...
        &&ismember('parameter_basis',s.Properties.VariableNames)&&startsWith(string(s.parameter_basis),"source_design");
    if design,policy(j)="explicit_source_design_geometry";else,policy(j)="declared_voltage_class_geometry_window";end
    if ~has_geometry,reasons(end+1)="no_declared_geometry_window_for_voltage";
    elseif dims&&mult
        g=geometry(gi,:);bundles=str2double(split(string(g.allowed_bundle_counts),';'));
        if s.circuits>g.nparallel_max_default,reasons(end+1)="circuit_count_exceeds_declared_search_window";end
        if ~design&&(~ismember(s.bundle_count,bundles)||s.gmd_m<g.gmd_min_m-1e-10||s.gmd_m>g.gmd_max_m+1e-10)
            reasons(end+1)="outside_declared_phase_geometry_or_bundle_window";
        end
        if s.bundle_spacing_m<g.bundle_spacing_min_m-1e-10||s.bundle_spacing_m>g.bundle_spacing_max_m+1e-10
            reasons(end+1)="outside_declared_bundle_spacing_window";
        end
    end
    if known_catalog(j)
        c=conductors(ci(j),:);
        fields={'diameter_m','gmr_m','r_ac25_ohm_per_m','r_ac75_ohm_per_m','r_ac200_ohm_per_m', ...
            'heat_capacity_j_m_k','emissivity','absorptivity'};
        catalog_consistent=true;
        for q=1:numel(fields)
            name=fields{q};
            if ismember(name,s.Properties.VariableNames)
                a=double(s.(name));b=double(c.(name));
                catalog_consistent=catalog_consistent&&((isnan(a)&&isnan(b))||(isfinite(a)&&isfinite(b)&&abs(a-b)<=max(1e-12,1e-9*abs(b))));
            end
        end
        if ~catalog_consistent,reasons(end+1)="segment_material_properties_differ_from_catalog";end
        temp=all(isfinite([s.temperature_min_c s.reference_temperature_c s.temperature_max_c])) ...
            &&s.temperature_min_c>=c.temperature_min_c&&s.temperature_max_c<=c.temperature_max_c ...
            &&s.temperature_min_c<=s.reference_temperature_c&&s.reference_temperature_c<=s.temperature_max_c ...
            &&s.temperature_min_c>=c.resistance_supported_min_c&&s.temperature_max_c<=c.resistance_supported_max_c;
        if ~temp,reasons(end+1)="outside_supported_resistance_or_declared_temperature_policy";end
        if dims&&mult&&temp
            try
                gm=bundle_gmr(c.gmr_m,s.bundle_count,s.bundle_spacing_m);
                rc=bundle_gmr(c.diameter_m/2,s.bundle_count,s.bundle_spacing_m);
                assert(s.gmd_m>max(gm,rc),'rxThermal:PhaseGeometry','Phase GMD must exceed the conductor bundle radii.');
                rsub=nylatest_conductor_resistance(c,s.reference_temperature_c);
                omega=2*pi*60;zbase=s.base_kv^2/m.baseMVA;
                r_calc(j)=rsub*s.segment_length_m/(s.circuits*s.bundle_count)/zbase;
                x_calc(j)=omega*2e-7*log(s.gmd_m/gm)*s.segment_length_m/s.circuits/zbase;
                b_calc(j)=s.circuits*omega*2*pi*8.8541878128e-12/log(s.gmd_m/rc)*s.segment_length_m*zbase;
                gmr_bundle(j)=gm;
                if abs(r_calc(j)-s.reference_r_pu)>1e-11||abs(x_calc(j)-s.reference_x_pu)>1e-10
                    reasons(end+1)="stored_segment_RX_differs_from_catalog_geometry_forward_model";
                end
            catch err
                reasons(end+1)="invalid_catalog_geometry_forward_model_"+string(err.identifier);
            end
        end
    end
    valid(j)=isempty(reasons)&&all(isfinite([r_calc(j) x_calc(j) b_calc(j)]))&&min([r_calc(j) x_calc(j) b_calc(j)])>0;
    if valid(j),segment_reason(j)="catalog_temperature_geometry_forward_model_passed";else,segment_reason(j)=join(reasons,'; ');end
end
allsegments.forward_r_pu=r_calc;allsegments.forward_x_pu=x_calc;allsegments.forward_b_pu=b_calc;
allsegments.forward_bundle_gmr_m=gmr_bundle;allsegments.forward_segment_valid=valid;
allsegments.forward_segment_reason=segment_reason;allsegments.geometry_policy=policy;
allsegments.original_parent_row=parents(allsegments.branch_row);
ratio_floor_by_voltage=nan(height(geometry),1);
for k=1:height(geometry),ratio_floor_by_voltage(k)=catalog_ratio_floor(geometry.nominal_kv(k),geometry,conductors);end
rows=struct([]);branchrows=struct([]);keep=false(ns,1);
for p=1:np
    r=find(parents==p);[found,k]=ismember(p,double(reg.branch_row));assert(found);
    first=r(map.physical_terminal_from(r));last=r(map.physical_terminal_to(r));assert(isscalar(first)&&isscalar(last));
    [okf,f]=ismember(m.branch(r,1),m.bus(:,1));[okt,t]=ismember(m.branch(r,2),m.bus(:,1));assert(all(okf&okt));
    classification=string(reg.classification(k));sg=find(ismember(allsegments.branch_row,r));
    active=all(m.branch(r,11)>0);same_voltage=all(abs(m.bus(f,10)-m.bus(t,10))<1e-9);
    tap=all(m.branch(r,9)==0|m.branch(r,9)==1);phase=all(m.branch(r,10)==0);
    overhead=ismember(classification,["synthetic_overhead_corridor","design_based_overhead"]);
    lengths=sum(allsegments.segment_length_m(sg));design=classification=="design_based_overhead" ...
        &&string(reg.parameter_basis(k))=="preserved_source_design_line_only_R_X_B";
    kv=m.bus(f(1),10);if kv<200,length_max=250000;elseif kv<300,length_max=500000;elseif kv<400,length_max=700000;else,length_max=1000000;end
    length_ok=~isempty(sg)&&isfinite(lengths)&&lengths>=5-1e-6&&lengths<=length_max+1e-6;
    segment_ok=~isempty(sg)&&all(valid(sg));complete=~isempty(sg)&&all(ismember(r,allsegments.branch_row(sg)));
    max_R=NaN;max_X=NaN;max_B=NaN;R_match=false;X_match=false;B_match=false;
    if complete
        er=zeros(numel(r),1);ex=er;eb=er;
        for q=1:numel(r)
            rr=r(q);sr=sg(allsegments.branch_row(sg)==rr);fr=sum(r_calc(sr));fx=sum(x_calc(sr));fb=sum(b_calc(sr));
            er(q)=abs(fr-m.branch(rr,3));ex(q)=abs(fx-m.branch(rr,4));eb(q)=abs(fb-m.branch(rr,5));
            br=struct('original_parent_row',p,'runtime_branch_row',rr,'branch_key',char(keys(rr)), ...
                'segment_count',numel(sr),'R_target_pu',m.branch(rr,3),'X_target_pu',m.branch(rr,4),'B_target_pu',m.branch(rr,5), ...
                'forward_R_pu',fr,'forward_X_pu',fx,'forward_B_pu',fb, ...
                'R_absolute_error_pu',er(q),'X_absolute_error_pu',ex(q),'B_absolute_error_pu',eb(q), ...
                'R_relative_error',er(q)/max(abs(m.branch(rr,3)),eps),'X_relative_error',ex(q)/max(abs(m.branch(rr,4)),eps), ...
                'B_relative_error',eb(q)/max(abs(m.branch(rr,5)),eps),'B_used_as_eligibility_gate',false, ...
                'segment_physical_checks_passed',all(valid(sr)));
            branchrows=[branchrows br]; %#ok<AGROW>
        end
        max_R=max(er);max_X=max(ex);max_B=max(eb);R_match=all(er<=1e-11);X_match=all(ex<=1e-10);B_match=all(eb<=1e-10);
    end
    current_R=sum(m.branch(r,3));current_X=sum(m.branch(r,4));
    original_R=double(reg.original_r_pu(k));original_X=double(reg.original_x_pu(k));
    imported_RX=abs(current_R-original_R)<=1e-11&&abs(current_X-original_X)<=1e-10;
    if imported_RX,target_basis='imported_RX';else,target_basis='prior_engineered_RX';end
    [has_conflict,conflict_index]=ismember(p,double(conflicts.branch_row));
    conflict_finding='';conflict_source='';
    if has_conflict
        assert(string(conflicts.branch_key(conflict_index))==string(reg.branch_key(k)),'rxThermal:ConflictKey','Cable evidence key differs from current parent.');
        conflict_finding=char(conflicts.finding(conflict_index));conflict_source=char(conflicts.source_ids(conflict_index)+" / "+conflicts.source_locator(conflict_index));
    end
    ratio_floor=NaN;below_floor=false;
    if overhead&&same_voltage&&~design&&current_R>0&&current_X>0
        [has_geo,gi]=ismember(m.bus(f(1),10),geometry.nominal_kv);if has_geo,ratio_floor=ratio_floor_by_voltage(gi);end
        below_floor=isfinite(ratio_floor)&&current_X/current_R<ratio_floor-1e-10;
    end
    reasons=strings(0,1);
    if ~active,reasons(end+1)="inactive_or_inconsistent_runtime_status";end
    if has_conflict,reasons(end+1)="cable_corridor_evidence_conflict";end
    if ~overhead,reasons(end+1)="non_overhead_class_"+classification;end
    if ~same_voltage,reasons(end+1)="voltage_changing_object";end
    if ~tap,reasons(end+1)="nonunity_transformer_tap";end
    if ~phase,reasons(end+1)="phase_shifter_or_PAR";end
    if below_floor,reasons(end+1)="current_X_over_R_below_declared_catalog_geometry_minimum";end
    if isempty(sg),reasons(end+1)="no_conductor_realization_metadata_for_current_RX";
    else
        if ~complete,reasons(end+1)="not_every_electrical_section_has_a_thermal_realization";end
        if ~segment_ok,reasons(end+1)="segment_catalog_temperature_or_geometry_validation_failed";end
        if ~length_ok,reasons(end+1)="route_length_outside_broad_voltage_class_synthetic_window";end
        if ~R_match,reasons(end+1)="forward_catalog_R_differs_from_current_electrical_R";end
        if ~X_match,reasons(end+1)="forward_geometry_X_differs_from_current_electrical_X";end
    end
    eligible=isempty(reasons);if eligible,keep(sg)=true;reason='admitted_for_RX_conditioned_synthetic_research_screen';else,reason=char(join(reasons,'; '));end
    row=struct('original_parent_row',p,'original_corridor_key',char(reg.branch_key(k)), ...
        'from_bus',m.branch(first,1),'to_bus',m.branch(last,2),'classification',char(classification), ...
        'source_role',char(reg.source_role(k)),'parameter_basis',char(reg.parameter_basis(k)), ...
        'cable_conflict_evidence',conflict_finding,'cable_conflict_source',conflict_source, ...
        'RX_target_basis',target_basis,'current_parent_R_pu',current_R,'current_parent_X_pu',current_X, ...
        'imported_parent_R_pu',original_R,'imported_parent_X_pu',original_X,'imported_RX_preserved',imported_RX, ...
        'catalog_geometry_minimum_X_over_R',ratio_floor,'current_RX_below_catalog_geometry_minimum',below_floor, ...
        'active',active,'same_voltage',same_voltage,'unity_tap',tap,'zero_phase',phase,'thermal_segment_count',numel(sg), ...
        'runtime_branch_count',numel(r),'total_route_length_m',lengths,'broad_voltage_length_policy_passed',length_ok, ...
        'synthetic_length_min_m',5,'synthetic_length_max_m',length_max, ...
        'historical_geographic_length_min_m',double(reg.length_min_m(k)), ...
        'historical_geographic_length_max_m',double(reg.length_max_m(k)), ...
        'geographic_chord_used_as_eligibility_gate',false, ...
        'all_segment_physical_checks_passed',segment_ok,'all_runtime_sections_covered',complete, ...
        'forward_R_matches_current_case',R_match,'forward_X_matches_current_case',X_match, ...
        'geometric_B_matches_current_case',B_match,'maximum_section_R_error_pu',max_R, ...
        'maximum_section_X_error_pu',max_X,'maximum_section_B_error_pu',max_B, ...
        'B_used_as_eligibility_gate',false,'research_screen_eligible',eligible,'reason',reason, ...
        'installed_circuit_identity_required',false,'installed_asset_DLR_verified',false, ...
        'electrical_parameters_changed',false);
    rows=[rows row]; %#ok<AGROW>
end
segments=allsegments(keep,:);ledger=struct2table(rows);forward=struct2table(branchrows);
[ok,k]=ismember(segments.original_parent_row,ledger.original_parent_row);assert(all(ok));
segments.RX_target_basis=string(ledger.RX_target_basis(k));
if ~isempty(forward)
    [ok,k]=ismember(forward.original_parent_row,ledger.original_parent_row);assert(all(ok));
    forward.RX_target_basis=string(ledger.RX_target_basis(k));forward.research_screen_eligible=ledger.research_screen_eligible(k);
end
end

function ratio=catalog_ratio_floor(kv,geometry,conductors)
% Independent lower bound at each catalog's declared reference temperature.
% Circuit count and length cancel from X/R. This does not select a candidate.
[found,k]=ismember(kv,double(geometry.nominal_kv));if ~found,ratio=NaN;return;end
g=geometry(k,:);bundles=str2double(split(string(g.allowed_bundle_counts),';'));ratio=Inf;
for j=1:height(conductors)
    c=conductors(j,:);r=nylatest_conductor_resistance(c,c.reference_temperature_c);
    for n=bundles(:)'
        gm=bundle_gmr(c.gmr_m,n,g.bundle_spacing_max_m);
        if g.gmd_min_m>gm
            ratio=min(ratio,2*pi*60*2e-7*log(g.gmd_min_m/gm)*n/r);
        end
    end
end
end

function value=bundle_gmr(single,count,spacing)
assert(single>0&&spacing>2*single,'rxThermal:BundleGeometry','Invalid subconductor radius or adjacent spacing.');
if count==1,value=single;else,radius=spacing/(2*sin(pi/count));value=(single*count*radius^(count-1))^(1/count);end
end

function value=asbool(value)
if islogical(value),return;end
if isnumeric(value),value=value~=0;else,value=ismember(lower(string(value)),["true","1"]);end
end
