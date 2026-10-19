function [h,dh,H]=dlr_series_constraint(x,d,lambda)
%DLR_SERIES_CONSTRAINT Exact series-current squared inequality in per unit.
% d.Yseries excludes charging. Equipment MVA constraints remain in MATPOWER.
if iscell(x),va=x{1};vm=x{2};else,nb=size(d.Yseries,2);va=x(1:nb);vm=x(nb+1:end);end
v=vm.*exp(1i*va);i=d.Yseries*v;h=real(i.*conj(i))-d.limit_pu.^2;
if nargout>1
    [da,dm,~,~,i]=dIbr_dV(d.branch,d.Yseries,-d.Yseries,v,0);
    di=spdiags(conj(i),0,numel(i),numel(i));dh=2*real([di*da di*dm]);
end
if nargout>2
    d2i=@(v,mu)d2Ibr_dV2(d.Yseries,v,mu,0);
    [aa,am,ma,mm]=d2Abr_dV2(d2i,da,dm,i,v,lambda);
    H=[aa am;ma mm];
end
end
