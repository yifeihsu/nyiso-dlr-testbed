function out=test_compact_interface_ac_cost
%TEST_COMPACT_INTERFACE_AC_COST Finite-difference nonlinear derivative guards.
c=ext2int(loadcase('case9'));nl=size(c.branch,1);nb=size(c.bus,1);
[~,d.Yf,d.Yt]=makeYbus(c.baseMVA,c.bus,c.branch);d.branch=c.branch;d.baseMVA=c.baseMVA;
d.F=sparse(1:nl,c.branch(:,1),1,nl,nb);d.T=sparse(1:nl,c.branch(:,2),1,nl,nb);
d.Cf=sparse([1 1 2],[1 4 7],[1 -.3 .8],2,nl);d.Ct=sparse([1 2],[6 8],[.4 1],2,nl);
d.target=[120;-35];d.scale=[500;400];x=[linspace(-.08,.1,nb)';linspace(.97,1.05,nb)'];
[~,g,H]=compact_interface_ac_cost(x,d);h=1e-6;gn=zeros(size(x));Hn=zeros(numel(x));
for k=1:numel(x)
    dx=zeros(size(x));dx(k)=h;
    [fp,gp]=compact_interface_ac_cost(x+dx,d);[fm,gm]=compact_interface_ac_cost(x-dx,d);
    gn(k)=(fp-fm)/(2*h);Hn(:,k)=(gp-gm)/(2*h);
end
ge=max(abs(g-gn));he=max(abs(H-Hn),[],'all');
assert(ge<1e-5&&he<1e-3,'compact_cost:Derivatives','Analytic derivatives fail finite differences.');
assert(max(abs(H-H'),[],'all')<1e-10);
out=table(["gradient_central_difference";"hessian_central_difference";"hessian_symmetric"],true(3,1), ...
    'VariableNames',{'test','passed'});disp(out);
end
