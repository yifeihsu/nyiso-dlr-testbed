function [gen, allocation, remaining] = ny_lite_allocate_pg_delta(gen, gen_idx, delta_mw, weights)
%NY_LITE_ALLOCATE_PG_DELTA Allocate an incremental PG change within limits.

PG=2; GEN_STATUS=8; PMAX=9; PMIN=10;
gen_idx = unique(gen_idx(:));
if isempty(gen_idx), error('ny_lite_allocate_pg_delta:EmptyPool', 'Generator pool is empty.'); end
if any(gen_idx < 1 | gen_idx > size(gen,1)), error('Generator index outside matrix.'); end
if any(gen(gen_idx,GEN_STATUS)<=0), error('Generator pool contains an offline unit.'); end
if nargin < 4 || isempty(weights), weights = ones(numel(gen_idx),1); end
weights=weights(:);
if numel(weights)~=numel(gen_idx) || any(weights<0) || sum(weights)<=0
    error('ny_lite_allocate_pg_delta:BadWeights', 'Weights must be nonnegative with positive sum.');
end
allocation=zeros(numel(gen_idx),1);
remaining=delta_mw;
for iter=1:100
    if abs(remaining)<1e-8, break; end
    pg=gen(gen_idx,PG);
    if remaining>0, room=gen(gen_idx,PMAX)-pg; else, room=pg-gen(gen_idx,PMIN); end
    active=room>1e-10;
    if ~any(active), break; end
    w=weights; w(~active)=0; w=w/sum(w);
    step=remaining*w;
    if remaining>0, step=min(step,room); else, step=max(step,-room); end
    gen(gen_idx,PG)=pg+step;
    allocation=allocation+step;
    remaining=delta_mw-sum(allocation);
end
end
