function [budget,detail]=nylatest_budget(m,r,p)
% Sum parent-corridor Joule losses, then apply declared ownership once.
V=r.bus(:,8).*exp(1j*deg2rad(r.bus(:,9)));
[ok,f]=ismember(m.branch(:,1),m.bus(:,1));assert(all(ok));[ok,t]=ismember(m.branch(:,2),m.bus(:,1));assert(all(ok));
tap=m.branch(:,9);tap(tap==0)=1;tap=tap.*exp(1j*deg2rad(m.branch(:,10)));
ys=zeros(size(f));on=m.branch(:,11)>0;assert(all(m.branch(on,3)>=0));
ys(on)=1./complex(m.branch(on,3),m.branch(on,4));
I=ys.*(V(f)./tap-V(t));loss=m.baseMVA*m.branch(:,3).*abs(I).^2;
assert(all(isfinite(loss))&&all(loss>=0));
parent_loss=accumarray(p.parent,loss,[size(p.loss_ownership,2) 1]);budget=p.loss_ownership*parent_loss;
detail=struct('branch_Joule_loss_MW',loss,'parent_loss_MW',parent_loss, ...
    'maximum_terminal_loss_identity_MW',max(abs(loss-r.branch(:,14)-r.branch(:,16))), ...
    'ownership_total_error_MW',sum(budget)-sum(loss));
end
