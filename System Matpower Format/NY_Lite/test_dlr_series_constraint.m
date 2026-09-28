function tests=test_dlr_series_constraint
%TEST_DLR_SERIES_CONSTRAINT Independent derivatives and solved constraint.
c=ext2int(loadcase('case9'));c.branch(2,5)=.35;
r=[2;3;5];d.branch=c.branch(r,:);n=numel(r);nb=size(c.bus,1);
y=1./(d.branch(:,3)+1i*d.branch(:,4));
d.Yseries=sparse((1:n)',d.branch(:,1),y,n,nb)-sparse((1:n)',d.branch(:,2),y,n,nb);
d.limit_pu=ones(n,1);x=[linspace(-.08,.1,nb)';linspace(.97,1.05,nb)'];mu=[.7;1.3;.4];
[~,j,H]=dlr_series_constraint(x,d,mu);step=1e-6;jn=zeros(n,numel(x));hn=zeros(numel(x));
for k=1:numel(x)
    dx=zeros(size(x));dx(k)=step;
    [hp,jp]=dlr_series_constraint(x+dx,d);[hm,jm]=dlr_series_constraint(x-dx,d);
    jn(:,k)=(hp-hm)/(2*step);hn(:,k)=(jp'-jm')*mu/(2*step);
end
je=max(abs(j-jn),[],'all');he=max(abs(H-hn),[],'all');
tests=table(["series_current_constraint_Jacobian";"series_current_constraint_Hessian"], ...
    [je<1e-5;he<1e-3],[je;he],'VariableNames',{'test','passed','max_error'});
assert(all(tests.passed),'dlr:ConstraintDerivative','Exact current constraint derivative mismatch.');disp(tests);
end
