function out=apply_compact_independent_generation_prior(snapshot,priors,named_priors)
%APPLY_COMPACT_INDEPENDENT_GENERATION_PRIOR Source totals, no interface fit.
% Each zonal total is assigned above online PMIN in proportion to PMAX-PMIN.
% Out-of-range assignments are clipped per generator, never moved to another
% zone. Named source estimates are subsets reserved before generic allocation.
% No-generator source totals remain explicitly unallocated in the ledger.
if nargin<3,named_priors=table();end
required={'scenario_id','zone','prior_public_mw','prior_benchmark_mw','coverage_qualified','source_method'};
assert(istable(priors)&&all(ismember(required,priors.Properties.VariableNames)), ...
    'independent_prior:Schema','Required source-prior columns are missing.');
assert(isfield(snapshot,'scenario_id')&&isfield(snapshot,'candidate')&&isfield(snapshot,'generator_keys'), ...
    'independent_prior:Snapshot','Snapshot identity, candidate and generator keys required.');
id=string(snapshot.scenario_id);p=priors(string(priors.scenario_id)==id,:);z=string(p.zone);
assert(height(p)==11&&isequal(sort(z),string(('A':'K')')), ...
    'independent_prior:Zones','Exactly one source row for each A-K zone is required.');
assert(islogical(p.coverage_qualified)&&all(p.coverage_qualified), ...
    'independent_prior:SourceCoverage','Source-prior coverage must be explicitly qualified.');
assert(all(isfinite(p.prior_public_mw)&p.prior_public_mw>=0) ...
    &&all(isfinite(p.prior_benchmark_mw)&p.prior_benchmark_mw>=0) ...
    &&all(~ismissing(string(p.source_method))&strlength(string(p.source_method))>0), ...
    'independent_prior:SourceValue','Finite nonnegative generation and explicit source methods required.');
assert(isfield(snapshot,'snapshot')&&istable(snapshot.snapshot)&&height(snapshot.snapshot)==1 ...
    &&ismember('scale_factor_gamma',snapshot.snapshot.Properties.VariableNames), ...
    'independent_prior:Scale','Snapshot must declare its public-to-benchmark scale.');
gamma=snapshot.snapshot.scale_factor_gamma;
assert(isscalar(gamma)&&isfinite(gamma)&&gamma>0 ...
    &&max(abs(p.prior_benchmark_mw-gamma*p.prior_public_mw))<1e-6, ...
    'independent_prior:Scale','Source generation and snapshot power scales differ.');
define_constants;m=snapshot.candidate;ng=size(m.gen,1);keys=string(snapshot.generator_keys(:));
assert(numel(keys)==ng&&numel(unique(keys))==ng&&all(strlength(keys)>0), ...
    'independent_prior:Keys','Generator keys must be unique and row aligned.');
[ok,at]=ismember(m.gen(:,GEN_BUS),m.bus(:,BUS_I));assert(all(ok));
bz=string(m.userdata.nyiso_physical_zone(:));assert(numel(bz)==size(m.bus,1)&&all(ismember(bz,z)));
gz=bz(at);on=m.gen(:,GEN_STATUS)>0;lo=m.gen(:,PMIN);hi=m.gen(:,PMAX);
assert(all(isfinite(lo)&isfinite(hi)&lo<=hi), ...
    'independent_prior:Capability','Finite ordered inherited active-power bounds required.');
named=table();named_rows=zeros(0,1);named_found=false(0,1);
if ~isempty(named_priors)
    assert(istable(named_priors)&&all(ismember([required,{'generator_key'}],named_priors.Properties.VariableNames)), ...
        'independent_prior:NamedSchema','Named source-prior columns missing.');
    named=named_priors(string(named_priors.scenario_id)==id,:);
    assert(numel(unique(string(named.generator_key)))==height(named)&&all(ismember(string(named.zone),z)), ...
        'independent_prior:NamedIdentity','Named keys must be unique and have valid source zones.');
    assert(islogical(named.coverage_qualified)&&all(named.coverage_qualified) ...
        &&all(isfinite(named.prior_public_mw)&named.prior_public_mw>=0&isfinite(named.prior_benchmark_mw)&named.prior_benchmark_mw>=0) ...
        &&all(~ismissing(string(named.source_method))&strlength(string(named.source_method))>0), ...
        'independent_prior:NamedCoverage','Qualified finite named source estimates required.');
    assert(all(abs(named.prior_benchmark_mw-gamma*named.prior_public_mw)<1e-6), ...
        'independent_prior:NamedScale','Named source and snapshot power scales differ.');
    [named_found,named_rows]=ismember(string(named.generator_key),keys);
    assert(all(gz(named_rows(named_found))==string(named.zone(named_found))), ...
        'independent_prior:NamedIdentity','Named source zone differs from model device zone.');
end
reserved=false(ng,1);reserved(named_rows(named_found))=true;
prior=zeros(ng,1);raw=prior;share=prior;sigma=ones(ng,1);sigma_before_floor=prior;
zone_ledger=table();named_totals=zeros(11,1);named_bounded=named_totals;generic_totals=named_totals;
for k=1:11
    zone=string(char('A'+k-1));r=p(z==zone,:);ix=find(gz==zone&on);
    target=r.prior_benchmark_mw;zone_sigma=max(50,.15*target);
    capacity=max(0,hi(ix)-lo(ix));available=sum(capacity);minimum=sum(lo(ix));maximum=sum(hi(ix));
    named_target=0;named_ix=zeros(0,1);
    if ~isempty(named)
        nk=find(string(named.zone)==zone);named_target=sum(named.prior_benchmark_mw(nk));
        assert(named_target<=target+1e-6,'independent_prior:NamedSubset','Named estimates exceed the zonal source total.');
        for j=nk'
            if named_found(j)&&on(named_rows(j)),raw(named_rows(j))=named.prior_benchmark_mw(j);end
        end
        named_ix=ix(reserved(ix));
    end
    generic=ix(~reserved(ix));generic_capacity=max(0,hi(generic)-lo(generic));
    generic_available=sum(generic_capacity);remaining=max(0,target-named_target);
    if ~isempty(generic)
        if generic_available>0
            raw(generic)=lo(generic)+(remaining-sum(lo(generic)))*generic_capacity/generic_available;
        else
            raw(generic)=lo(generic); % Fixed devices cannot allocate an additional target.
        end
    end
    if ~isempty(ix)
        if available>0,share(ix)=capacity/available;end
        prior(ix)=min(hi(ix),max(lo(ix),raw(ix)));
        sigma_before_floor(ix)=zone_sigma*sqrt(share(ix));
        sigma(ix)=max(1,sigma_before_floor(ix));
    end
    requested_assigned=sum(raw(ix));assigned=sum(prior(ix));
    unmapped=target-requested_assigned;clipping=requested_assigned-assigned;
    coeff=sum(share(ix).^2./sigma(ix).^2);effective_sigma=Inf;if coeff>0,effective_sigma=1/sqrt(coeff);end
    reason="represented_within_zone";
    if isempty(ix),reason="no_online_generator_source_total_unallocated";
    elseif available==0,reason="fixed_capability_only_unallocated_difference";
    elseif abs(clipping)>1e-8,reason="source_assignment_clipped_to_inherited_bounds";end
    zone_ledger=[zone_ledger;table(id,zone,r.prior_public_mw,target,numel(ix),available,minimum,maximum, ...
        requested_assigned,assigned,unmapped,clipping,target-assigned,zone_sigma,effective_sigma, ...
        nnz(sigma_before_floor(ix)<1),reason,string(r.source_method),true,false, ...
        'VariableNames',{'scenario_id','zone','source_prior_public_mw','source_prior_benchmark_mw', ...
        'online_generator_count','allocatable_headroom_mw','online_pmin_mw','online_pmax_mw', ...
        'raw_generator_prior_mw','bounded_generator_prior_mw','unallocated_source_prior_mw', ...
        'clipped_source_prior_mw','total_unrepresented_prior_mw','zone_sigma_mw', ...
        'effective_coherent_zone_sigma_mw','generator_sigma_floor_count','allocation_status', ...
        'source_method','source_coverage_qualified','observed_zonal_generation'})]; %#ok<AGROW>
    named_totals(k)=named_target;named_bounded(k)=sum(prior(named_ix));generic_totals(k)=remaining;
end
zone_ledger.named_source_subset_mw=named_totals;
zone_ledger.named_bounded_generator_prior_mw=named_bounded;
zone_ledger.generic_source_residual_mw=generic_totals;
generator_ledger=table(repmat(id,ng,1),(1:ng)',keys,m.gen(:,GEN_BUS),gz,on,lo,hi,share,raw,prior, ...
    raw-prior,sigma_before_floor,sigma,repmat(false,ng,1), ...
    'VariableNames',{'scenario_id','model_gen_row','generator_key','model_bus','zone','online', ...
    'pmin_mw','pmax_mw','within_zone_capacity_share','raw_prior_mw','bounded_prior_mw', ...
    'clipped_prior_mw','sigma_before_floor_mw','sigma_mw','observed_generator_dispatch'});
out=snapshot;out.candidate.gen(:,PG)=prior;out.Pg_prior_mw=prior;out.Pg_sigma_mw=sigma;
out.generation_participation=[];out.prior_loss_fraction=NaN;
out.prior_method="independent_source_zone_totals_within_zone_headroom_allocation_no_loss_rescaling";
out.independent_source_priors=sortrows(p,'zone');out.independent_prior_zone_ledger=zone_ledger;
out.independent_prior_generator_ledger=generator_ledger;
out.independent_named_source_priors=named;
named_ledger=named;
if ~isempty(named)
    named_ledger.model_gen_row=named_rows;named_ledger.model_key_found=named_found;
    named_ledger.bounded_prior_mw=zeros(height(named),1);named_ledger.assigned_online=false(height(named),1);
    for j=1:height(named)
        if named_found(j)&&on(named_rows(j))
            named_ledger.assigned_online(j)=true;named_ledger.bounded_prior_mw(j)=prior(named_rows(j));
        end
    end
    named_ledger.unallocated_source_prior_mw=named.prior_benchmark_mw.*~named_ledger.assigned_online;
    named_ledger.clipped_source_prior_mw=named.prior_benchmark_mw.*named_ledger.assigned_online-named_ledger.bounded_prior_mw;
    named_ledger.observed_generator_dispatch=false(height(named),1);
end
out.independent_named_prior_ledger=named_ledger;
out.independent_prior_policy=struct('zone_sigma_floor_mw',50,'zone_sigma_fraction',.15, ...
    'generator_sigma_floor_mw',1,'allocation',"PMIN_plus_source_excess_times_online_headroom_share", ...
    'cross_zone_reallocation',false,'source_loss_rescaling',false,'interface_targets_used',false, ...
    'unmapped_or_clipped_source_totals_preserved',true,'generator_capacity_changes',false, ...
    'named_estimates_are_zonal_subsets',true,'sigma_uses_all_online_headroom_before_named_reservation',true);
out.heldout_interfaces_used_in_prior=false;out.electrical_baseline_qualified=false;out.dlr_ready=false;
assert(abs(sum(zone_ledger.source_prior_benchmark_mw)-sum(prior) ...
    -sum(zone_ledger.total_unrepresented_prior_mw))<1e-7,'independent_prior:Accounting','Source-prior accounting failed.');
end
