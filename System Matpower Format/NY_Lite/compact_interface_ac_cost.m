function [f,g,H]=compact_interface_ac_cost(x,d)
%COMPACT_INTERFACE_AC_COST Exact AC interface residual objective derivatives.
% d operates on internal MATPOWER rows. Targets/scales are in MW.
if iscell(x),va=x{1};vm=x{2};else
    nb=size(d.Yf,2);va=x(1:nb);vm=x(nb+1:2*nb);end
V=vm.*exp(1i*va);
[dfa,dfm,dta,dtm,Sf,St]=dSbr_dV(d.branch,d.Yf,d.Yt,V);
p=d.baseMVA*real(d.Cf*Sf+d.Ct*St);e=(p-d.target)./d.scale;
f=sum(e.^2);
if nargout>1
    J=d.baseMVA*real([d.Cf*dfa+d.Ct*dta,d.Cf*dfm+d.Ct*dtm]);
    g=2*J'*(e./d.scale);
end
if nargout>2
    mu=2*d.baseMVA*(e./d.scale);
    [a,b,c,e2]=d2Sbr_dV2(d.F,d.Yf,V,d.Cf'*mu);
    [aa,bb,cc,ee]=d2Sbr_dV2(d.T,d.Yt,V,d.Ct'*mu);
    H=2*J'*spdiags(1./d.scale.^2,0,numel(d.scale),numel(d.scale))*J+ ...
        real([a+aa,b+bb;c+cc,e2+ee]);
end
end
