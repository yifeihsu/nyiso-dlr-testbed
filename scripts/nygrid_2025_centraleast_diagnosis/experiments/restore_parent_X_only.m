function [variant,ledger]=restore_parent_X_only(detailed,full_parent,selection)
% Diagnostic intervention only: restore selected originalDC total X values.
% Keep R/B/tap/phase/status, devices and all operating controls unchanged.
parents=detailed.userdata.ac_system.branch_parent_row(:);n=size(full_parent.branch,1);
total=accumarray(parents,detailed.branch(:,4),[n 1]);reference=full_parent.branch(:,4);
changed=find(abs(total-reference)>1e-12&full_parent.branch(:,11)>0);
root=fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
persistent registry
if isempty(registry)
    t=readtable(fullfile(root,'output','nygrid_2025_centraleast_diagnosis','model_delta','x_changed_corridors.csv'));
    registry=sort(unique(t.branch_row));assert(numel(registry)==33);
end
assert(isequal(changed,registry(full_parent.branch(registry,11)>0)), ...
    'ceDiagnosis:XCount','Active engineering X-change cohort differs from the independent ledger.');
if ischar(selection)||isstring(selection)
    assert(strcmp(selection,'all_changed'));chosen=registry;
else
    chosen=selection(:);assert(all(ismember(chosen,changed)));
end
variant=detailed;ledger=zeros(numel(chosen),4);
for j=1:numel(chosen)
    p=chosen(j);rows=find(parents==p);weights=detailed.branch(rows,4)/total(p);
    assert(abs(sum(weights)-1)<1e-12&&all(weights>0));
    variant.branch(rows,4)=weights*reference(p);
    ledger(j,:)=[p total(p) reference(p) numel(rows)];
end
keep=setdiff(1:size(detailed.branch,2),4);
assert(isequal(variant.branch(:,keep),detailed.branch(:,keep))&&isequal(variant.bus,detailed.bus) ...
    &&isequal(variant.gen,detailed.gen)&&isequal(variant.dcline,detailed.dcline));
variant.userdata.diagnostic_X_restoration=struct('diagnostic_not_repair',true,'parent_rows',chosen, ...
    'only_X_changed',true,'originalDC_total_X_restored',true,'section_X_proportions_preserved',true, ...
    'R_B_tap_phase_status_shunts_and_operating_controls_preserved',true,'observed_interface_flows_used',false);
end
