function out=audit_interface_operators
%AUDIT_INTERFACE_OPERATORS Trace published row formulas to actual endpoints.
% Read-only with respect to upstream code/data and saved smoke models. The
% semantic operator is constructed exclusively from npcc.csv zones and the
% paper's Table I directed zone pairs, before any observation is inspected.
root=fileparts(fileparts(fileparts(mfilename('fullpath'))));
addpath(fullfile(root,'System Matpower Format','NY_Lite'));
upstream=fullfile(root,'tmp','nygrid_2019_reproduction','upstream');
input_file=fullfile(root,'output','nygrid_2019','unmodified_smoke_mirror_legacy.mat');
output_dir=fullfile(root,'output','nygrid_2019');
zone_file=fullfile(upstream,'Data','npcc.csv');
d=load(input_file);if isfield(d,'cases2'),cases=d.cases2;else,cases=d.cases;end
bi=readtable(zone_file,'TextType','string');
assert(numel(unique(bi.idx))==height(bi),'nygrid_operator:Identity','Original bus IDs must be unique.');
names=["Dysinger East";"West Central";"Total East";"Moses South";"Central East";"UpNY-Coned";"Dun/SPR-South"];
map_ids=[1;2;3;4;5;8;10];
literal={[-32;34;37;47];[-28;-29;33;50];[-14;-12;-3;-6;8];[-24;-18;-23];[-14;-12;-3;-6];[65;-66];[73;74]};
pairs={['A' 'B'];['B' 'C'];['E' 'F';'E' 'G'];['D' 'E'];['E' 'F'];['G' 'H'];['I' 'J']};
formula_lines=[9;10;11;12;13;16;18];
mapping_lines=[420;421;422;423;424;427;429];
terms=table();formulas=table();flows=table();all_branches=table();validation=table();
operators=cell(numel(cases),1);
for k=1:numel(cases)
    assert(~isempty(cases{k}),'nygrid_operator:Input','Missing smoke case.');
    m=cases{k}.input;r=cases{k}.result;nr=size(m.branch,1);
    assert(isequal(m.branch(:,1:13),r.branch(:,1:13))&&r.success, ...
        'nygrid_operator:Input','Smoke result must preserve its input branch ordering.');
    [ok,fi]=ismember(m.branch(:,1),bi.idx);[ok2,ti]=ismember(m.branch(:,2),bi.idx);
    assert(all(ok&ok2),'nygrid_operator:Identity','A reduced branch endpoint lacks an original npcc.csv identity.');
    zf=string(bi.zone(fi));zt=string(bi.zone(ti));nf=string(bi.name(fi));nt=string(bi.name(ti));
    branches=table(repmat(k,nr,1),(1:nr)',m.branch(:,1),m.branch(:,2),nf,nt,zf,zt,m.branch(:,11), ...
        'VariableNames',{'smoke_case','branch_row','from_bus','to_bus','from_name','to_name','from_zone','to_zone','status'});
    all_branches=[all_branches;branches]; %#ok<AGROW>
    semantic=zeros(7,nr);mapped=zeros(7,nr);plotting=zeros(7,nr);
    signed_map=cell(7,1);signed_semantic=cell(7,1);
    for j=1:7
        for q=1:size(pairs{j},1)
            source=string(pairs{j}(q,1));sink=string(pairs{j}(q,2));
            forward=zf==source&zt==sink;reverse=zf==sink&zt==source;
            semantic(j,forward)=1;semantic(j,reverse)=-1;
        end
        signed_map{j}=m.if.map(m.if.map(:,1)==map_ids(j),2);
        assert(~isempty(signed_map{j})&&all(abs(signed_map{j})<=nr) ...
            &&numel(unique(abs(signed_map{j})))==numel(signed_map{j}));
        mapped(j,abs(signed_map{j}))=sign(signed_map{j});
        plotting(j,abs(literal{j}))=sign(literal{j});
        jj=find(semantic(j,:));signed_semantic{j}=jj(:).*semantic(j,jj)';
        assert(~isempty(jj)&&all(m.branch(jj,11)>0), ...
            'nygrid_operator:Topology','Every semantic interface needs active directed crossings.');
        formulas=[formulas;table(k,names(j),map_ids(j), ...
            join(string(literal{j}),";"),join(string(signed_map{j}),";"),join(string(signed_semantic{j}),";"), ...
            isequal(mapped(j,:),semantic(j,:)),isequal(plotting(j,:),semantic(j,:)), ...
            nnz(plotting(j,:)~=semantic(j,:)),formula_lines(j),mapping_lines(j),false, ...
            'VariableNames',{'smoke_case','interface','released_map_id','literal_plot_signed_rows', ...
            'released_if_map_signed_rows','semantic_zone_crossing_signed_rows','if_map_matches_semantics', ...
            'literal_plot_matches_semantics','different_coefficient_count','flow4Plot_source_line', ...
            'updateOpCond_source_line','observations_used_for_operator_construction'})]; %#ok<AGROW>
        for method=["literal_plot";"released_if_map";"semantic_zone_crossing"]'
            switch method
                case "literal_plot",ids=literal{j};
                case "released_if_map",ids=signed_map{j};
                otherwise,ids=signed_semantic{j};
            end
            for q=1:numel(ids)
                row=abs(ids(q));coef=sign(ids(q));
                terms=[terms;table(k,names(j),method,row,coef,m.branch(row,1),m.branch(row,2), ...
                    nf(row),nt(row),zf(row),zt(row),m.branch(row,11),semantic(j,row),coef==semantic(j,row),false, ...
                    'VariableNames',{'smoke_case','interface','operator_variant','branch_row','PF_coefficient', ...
                    'from_bus','to_bus','from_name','to_name','from_zone','to_zone','status', ...
                    'semantic_PF_coefficient','coefficient_matches_semantic_cut','observations_used_for_construction'})]; %#ok<AGROW>
            end
        end
    end
    assert(isequal(mapped,semantic),'nygrid_operator:SemanticMismatch', ...
        'Released interface map does not match independently constructed zone cuts.');
    operators{k}=struct('literal_plot',plotting,'released_if_map',mapped,'semantic_zone_crossing',semantic, ...
        'semantic_signed_rows',{signed_semantic},'interface_names',names,'released_map_ids',map_ids, ...
        'branch_endpoints',m.branch(:,1:2),'branch_status',m.branch(:,11),'constructed_without_observations',true);
    validation=[validation;table(k,all(all(mapped==semantic)),nnz(any(plotting~=semantic,2)), ...
        max(abs((mapped-semantic)*r.branch(:,14))),false, ...
        'VariableNames',{'smoke_case','all_seven_if_maps_match_independent_zone_semantics', ...
        'interfaces_with_literal_plot_index_error','if_map_vs_semantic_flow_difference_mw','targets_used_to_select_operators'})]; %#ok<AGROW>
end
% Observe numerical consequences only AFTER constructing/validating operators.
for k=1:numel(cases)
    r=cases{k}.result;m=cases{k}.input;op=operators{k};
    actual=d.rows{k};assert(height(actual)==7);
    [ok,ai]=ismember(names,string(actual.interface));assert(all(ok));observed=actual.observed_mw(ai);
    sim=op.literal_plot*r.branch(:,14);sem=op.semantic_zone_crossing*r.branch(:,14);
    [ok,li]=ismember(map_ids,m.if.lims(:,1));assert(all(ok));limit=m.if.lims(li,3);
    assert(all(isfinite(limit)&limit>0)&&max(abs(sim-actual.simulated_mw(ai)))<1e-8, ...
        'nygrid_operator:Reproduction','Literal plotting formulas fail to reproduce the saved upstream output.');
    pct=NaN(7,1);positive=observed~=0;pct(positive)=100*abs(sem(positive)-observed(positive))./abs(observed(positive));
    flows=[flows;table(repmat(k,7,1),actual.timestamp(ai),names,observed,limit,sim,sem, ...
        100*(observed-sim)./limit,100*(observed-sem)./limit,abs(sem-observed),pct, ...
        sign(sim).*sign(observed)<0,sign(sem).*sign(observed)<0,false(7,1), ...
        'VariableNames',{'smoke_case','timestamp','interface','observed_mw','positive_limit_mw', ...
        'literal_plot_simulated_mw','semantic_if_map_simulated_mw','literal_paper_signed_error_pct', ...
        'semantic_paper_signed_error_pct','semantic_absolute_error_mw','semantic_actual_relative_error_pct', ...
        'literal_opposite_direction','semantic_opposite_direction','observations_used_for_operator_construction'})]; %#ok<AGROW>
end
paths=[string(input_file);string(zone_file);string(fullfile(upstream,'Utility','flow4Plot.m')); ...
    string(fullfile(upstream,'updateOpCond.m'));string(mfilename('fullpath'))+".m"];
fingerprints=strings(numel(paths),1);relative_path=fingerprints;
for k=1:numel(paths)
    fingerprints(k)=ny_reference_file_sha256(paths(k));relative_path(k)=replace(extractAfter(paths(k),strlength(root)+1),"\","/");
end
source_manifest=table(relative_path,fingerprints,'VariableNames',{'relative_path','sha256'});
out=struct('operators',{operators},'formulas',formulas,'terms',terms,'branch_inventory',all_branches, ...
    'smoke_flow_comparison',flows,'validation',validation,'source_manifest',source_manifest, ...
    'passed',all(validation.all_seven_if_maps_match_independent_zone_semantics) ...
        &&all(validation.interfaces_with_literal_plot_index_error==5), ...
    'operator_choice_uses_observations',false,'upstream_modified',false, ...
    'scope',"two_saved_smoke_cases_endpoint_and_zone_audit_not_a_reproduction_of_the_published_annual_figure");
for field=["formulas","terms","branch_inventory","smoke_flow_comparison","validation","source_manifest"]
    ny_lite_writetable_lf(out.(field),fullfile(output_dir,"operator_audit_"+field+".csv"));
end
save(fullfile(output_dir,'operator_audit.mat'),'out','-v7');
ny_lite_writetable_lf(table("operator_audit.mat",ny_reference_file_sha256(fullfile(output_dir,'operator_audit.mat')), ...
    'VariableNames',{'artifact','sha256'}),fullfile(output_dir,'operator_audit_manifest.csv'));
disp(validation);disp(flows);
end
