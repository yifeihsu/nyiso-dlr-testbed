function test_ac_dlr_adapter()
%TEST_AC_DLR_ADAPTER Independent dimensional and preservation checks.
root=fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
addpath(fullfile(root,'System Matpower Format','NY_Lite'));
c=readtable(fullfile(root,'output','nygrid_2025_ac_system','engineering','thermal_conductors.csv'),'TextType','string');
ids=["PRYSMIAN_ACSR_HAWK_477_0_26_7";"PRYSMIAN_ACSS_MALLARD_795_0_30_19"];
[ok,ci]=ismember(ids,c.catalog_id);assert(all(ok));
s=table([1;1],["fixture";"fixture"],["section1";"section2"],[5000;8000],[2;2],[1;2],[345;345], ...
    ids,[75;95],[25;25],[75;95], ...
    'VariableNames',{'branch_row','branch_key','segment_id','segment_length_m','circuits','bundle_count','base_kv', ...
    'catalog_id','reference_temperature_c','temperature_min_c','temperature_max_c'});
m=struct('version','2','baseMVA',100);
m.bus=[1 3 0 0 0 0 1 1.02 0.5 345 1 1.1 .9;2 1 0 0 0 0 1 1 0 345 1 1.1 .9];
m.branch=[1 2 .001 .02 .10 1000 0 0 0 0 1 -360 360];
m.gen=[1 0 0 1000 -1000 1 100 1 1000 0 zeros(1,11)];
m.gencost=[2 0 0 3 .01 1 0];m.dcline=zeros(6,23);m.userdata.test='preserve';
m=ac_dlr_apply_resistance(m,s,c,s.reference_temperature_c);
required=sum([ac_conductor_resistance(c(ci(1),:),75)*5000/2; ...
    ac_conductor_resistance(c(ci(2),:),95)*8000/4])/(345^2/100);
names=strings(0,1);passed=false(0,1);errors=zeros(0,1);
record('segment_resistance_sum',abs(m.branch(3)-required)<1e-15,abs(m.branch(3)-required));
rr=ac_conductor_resistance(c(ci(2),:),95);
interp_expected=c.r_ac75_ohm_per_m(ci(2))+.16*(c.r_ac200_ohm_per_m(ci(2))-c.r_ac75_ohm_per_m(ci(2)));
record('manufacturer_AC_temperature_interpolation',abs(rr-interp_expected)<1e-15,abs(rr-interp_expected));
reject('reject_cold_extrapolation',@()ac_conductor_resistance(c(ci(1),:),24));
reject('reject_ACSR_hot_extrapolation',@()ac_conductor_resistance(c(ci(1),:),76));
old=m;m2=ac_dlr_apply_resistance(m,s,c,[50;60]);m3=ac_dlr_apply_resistance(m2,s,c,[50;60]);
record('resistance_update_does_not_compound',isequal(m2,m3),0);
other=setdiff(1:13,3);
record('temperature_update_preserves_six_transfers_and_controls',isequal(old.dcline,m2.dcline)&&isequal(old.gen,m2.gen) ...
    &&isequal(old.userdata,m2.userdata)&&isequal(old.gencost,m2.gencost)&&isequal(old.branch(other),m2.branch(other)),0);
w=table(25,1.5,90,1000,101325,'VariableNames',{'ambient_c','wind_m_s','wind_angle_deg','solar_w_m2','pressure_pa'});
lim=ac_dlr_limits(m,s,c,w);
expected_limit=min(lim.segment.ampacity_subconductor_a.*s.circuits.*s.bundle_count);
record('heterogeneous_path_uses_limiting_section_phase_ampacity',abs(expected_limit-lim.branch.series_phase_limit_a)<1e-12,0);
hot=w;hot.ambient_c=40;hot.wind_m_s=.3;lh=ac_dlr_limits(m,s,c,hot);
record('adverse_weather_reduces_limits',all(lh.segment.ampacity_subconductor_a<lim.segment.ampacity_subconductor_a),0);
sf=s;sf.circuits(1)=1.5;reject('reject_fractional_circuit',@()ac_dlr_limits(m,sf,c,w));
bad=m;bad.bus(2,10)=138;reject('reject_voltage_changing_thermal_branch',@()ac_dlr_limits(bad,s,c,w));
v=m.bus(:,8).*exp(1i*deg2rad(m.bus(:,9)));[~,yf,yt]=makeYbus(m.baseMVA,m.bus,m.branch);
from=m.baseMVA*v(1)*conj(yf*v);to=m.baseMVA*v(2)*conj(yt*v);
m.branch(1,14:17)=[real(from) imag(from) real(to) imag(to)];m.success=true;
a=ac_dlr_current_audit(m,s,c,s.reference_temperature_c,lim);
expected_I=abs((v(1)-v(2))/(m.branch(3)+1i*m.branch(4)))*100000/(sqrt(3)*345);
record('direct_AC_current_without_gamma_lift',max(abs(a.segment.series_phase_current_a-expected_I))<1e-10, ...
    max(abs(a.segment.series_phase_current_a-expected_I)));
record('parallel_and_bundle_subconductor_current',abs(a.segment.subconductor_current_a(1)/a.segment.subconductor_current_a(2)-2)<1e-12,0);
record('three_phase_loss_matches_independent_MATPOWER_terminals',a.maximum_loss_identity_error_mw<1e-9,a.maximum_loss_identity_error_mw);
terminal_I=abs(yf*v)*100000/(sqrt(3)*345);
record('charging_current_excluded_from_heating',abs(terminal_I-expected_I)>1e-3,abs(terminal_I-expected_I));
tl=table(1,terminal_I*.999,abs(yt*v)*100000/(sqrt(3)*345)*1.1, ...
    'VariableNames',{'branch_row','total_terminal_current_limit_from_a','total_terminal_current_limit_to_a'});
terminal_audit=ac_terminal_current_audit(m,tl);
record('actual_voltage_terminal_current_limit_rejects_excess',~terminal_audit.passed ...
    &&abs(terminal_audit.table.actual_from_current_a-terminal_I)<1e-10, ...
    abs(terminal_audit.table.actual_from_current_a-terminal_I));
% Exercise the shared analytic current-squared derivatives with terminal Y,
% including charging, instead of assuming the series-only test covers it.
d=struct('branch',[m.branch;m.branch],'Yseries',[yf;yt],'limit_pu',[1;1]);
x=[deg2rad(m.bus(:,9));m.bus(:,8)];mu=[.7;1.1];step=1e-6;
[~,J,H]=dlr_series_constraint(x,d,mu);Jn=zeros(2,4);Hn=zeros(4);
for k=1:4
    dx=zeros(4,1);dx(k)=step;
    [hp,jp]=dlr_series_constraint(x+dx,d);[hm,jm]=dlr_series_constraint(x-dx,d);
    Jn(:,k)=(hp-hm)/(2*step);Hn(:,k)=(jp'*mu-jm'*mu)/(2*step);
end
ej=max(abs(full(J)-Jn),[],'all');eh=max(abs(full(H)-Hn),[],'all');
record('terminal_current_constraint_Jacobian',ej<1e-5,ej);
record('terminal_current_constraint_Hessian',eh<1e-4,eh);
% Exercise both terminal callbacks together in an actual small ACOPF.
% An intermediate section may have only one real hardware endpoint.
probe=m;probe.branch=probe.branch(:,1:13);probe.bus(2,3:4)=[50 20];probe.gen(1,2)=50;
hardware=table(1,1000,NaN,'VariableNames',{'branch_row','total_terminal_current_limit_from_a','total_terminal_current_limit_to_a'});
conductor_ends=table(1,900,900,'VariableNames',hardware.Properties.VariableNames);
probe=add_ac_terminal_current_limits(probe,hardware);
probe=add_ac_terminal_current_limits(probe,conductor_ends,'conductor_section_end_ampacity');
po=mpoption('verbose',0,'out.all',0,'opf.ac.solver','MIPS','mips.max_it',100);
[pr,ps]=runopf(probe,po);
pa=ac_terminal_current_audit(pr,hardware);pe=ac_terminal_current_audit(pr,conductor_ends);
fprintf('TERMINAL_COMPOSITION success%d hardware%d conductor%d ratios%.8g/%.8g\n',ps,pa.passed,pe.passed,pa.maximum_fraction,pe.maximum_fraction);
record('two_distinct_terminal_callbacks_compose_in_ACOPF',ps&&pa.passed&&pe.passed ...
    &&isequaln(probe.userdata.ac_system.terminal_current_limits,hardware) ...
    &&isequaln(probe.userdata.ac_system.conductor_section_end_current_limits,conductor_ends),0);
bad=m;bad.branch(3)=bad.branch(3)*1.01;reject('reject_electrical_thermal_R_mismatch',@()ac_dlr_current_audit(bad,s,c,s.reference_temperature_c,lim));
for j=1:2
    h=ac_conductor_heat(s.temperature_max_c(j),lim.segment.ampacity_subconductor_a(j),c(ci(j),:),w);
    record("zero_heat_at_weather_ampacity_section"+string(j),abs(h.net_w_m)<1e-10,abs(h.net_w_m));
end
out=fullfile(root,'output','nygrid_2025_ac_system','thermal');if ~isfolder(out),mkdir(out);end
writetable(table(names,passed,errors,'VariableNames',{'test','passed','error'}),fullfile(out,'adapter_tests.csv'));
proof=struct('passed',all(passed),'tests',numel(passed),'MATLAB_version',version, ...
    'test_scope','two-section fixed-voltage physical fixture plus preservation and dimensional guards;not a full-network solve', ...
    'dependencies',struct([]));
paths=[string(fullfile(root,'scripts','nygrid_2025_ac_system','thermal','test_ac_dlr_adapter.m')); ...
    string(fullfile(root,'output','nygrid_2025_ac_system','engineering','thermal_conductors.csv'))];
fn=dir(fullfile(root,'scripts','nygrid_2025_ac_system','thermal','*.m'));
for k=1:numel(fn),paths(end+1)=string(fullfile(fn(k).folder,fn(k).name));end %#ok<AGROW>
paths=unique(paths);
proof.dependencies=repmat(struct('path','','sha256',''),numel(paths),1);
for k=1:numel(paths),proof.dependencies(k)=struct('path',char(paths(k)),'sha256',filehash(paths(k)));end
fid=fopen(fullfile(out,'adapter_validation.json'),'w');fprintf(fid,'%s\n',jsonencode(proof,'PrettyPrint',true));fclose(fid);
disp(table(names,passed,errors));assert(all(passed),'acDLR:Tests','Adapter validation failed.');
    function record(name,ok,error_value)
        names(end+1,1)=string(name);passed(end+1,1)=logical(ok);errors(end+1,1)=error_value;
    end
    function reject(name,fun)
        failed=false;try,fun();catch,failed=true;end;record(name,failed,0);
    end
end
function digest=filehash(path)
e=java.security.MessageDigest.getInstance('SHA-256');fid=fopen(path,'rb');clean=onCleanup(@()fclose(fid));
while ~feof(fid),b=fread(fid,1048576,'*uint8');if ~isempty(b),e.update(typecast(b,'int8'));end,end
b=typecast(e.digest(),'uint8');digest=lower(reshape(dec2hex(b,2)',1,[]));
end
