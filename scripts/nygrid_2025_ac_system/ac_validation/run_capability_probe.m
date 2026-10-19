function run_capability_probe()
% Reproduce the rejected early hourly-external-Q policy on frozen initial R/X/B.
% This diagnostic is not the delivered loader's static-capacity external policy.
root=fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
addpath(fullfile(root,'System Matpower Format'));
out=fullfile(root,'output','nygrid_2025_ac_system','ac_validation','hourly_external_Q_trial');
if ~isfolder(out),mkdir(out);end
checks=struct([]);
for h=[4000 8508]
    nb=191+(h==8508);
    baseline=load(fullfile(root,'output','nygrid_2025_ac_system','ac_validation','initial_diagnostic',sprintf('full%d_h%d_input.mat',nb,h)));
    m=baseline.m;ng=size(m.gen,1);cap=max(abs(m.gen(:,9:10)),[],2);
    qcap=cap*tan(acos(.95));qcap(m.gen(:,8)==0)=0;
    m.gen(:,3)=0;m.gen(:,4)=qcap;m.gen(:,5)=-qcap;m.gen(:,7)=max(cap/.95,1);
    m.bus(:,12)=min(m.bus(:,12),1.05);m.bus(:,13)=max(m.bus(:,13),.95);
    m.bus(:,8)=min(max(m.bus(:,8),m.bus(:,13)),m.bus(:,12));m.bus(:,9)=0;
    [~,gb]=ismember(m.gen(:,1),m.bus(:,1));m.gen(:,6)=m.bus(gb,8);
    wp=1./max(cap,1);wq=.01./max(qcap,1);p0=m.gen(:,2);
    m.gencost=[2*ones(ng,1),zeros(ng,2),3*ones(ng,1),wp,-2*wp.*p0,wp.*p0.^2; ...
        2*ones(ng,1),zeros(ng,2),3*ones(ng,1),wq,zeros(ng,2)];
    m.userdata.ac_system=struct('external_generator_mask',strcmp(m.genfuel(:),'Import'), ...
        'diagnostic_only',true,'external_Q_based_on_hourly_schedule',true);
    opt=mpoption('model','AC','verbose',1,'out.all',0,'opf.ac.solver','MIPS', ...
        'opf.violation',1e-7,'mips.feastol',1e-8,'mips.gradtol',1e-6, ...
        'mips.comptol',1e-7,'mips.max_it',150,'mips.step_control',1);
    t=tic;[r,success]=runopf(m,opt);elapsed=toc(t);
    a=struct('hour',h,'success',logical(success),'seconds',elapsed, ...
        'P_viol',max([0;r.gen(:,10)-r.gen(:,2);r.gen(:,2)-r.gen(:,9)]), ...
        'Q_viol',max([0;r.gen(:,5)-r.gen(:,3);r.gen(:,3)-r.gen(:,4)]), ...
        'V_viol',max([0;r.bus(:,13)-r.bus(:,8);r.bus(:,8)-r.bus(:,12)]), ...
        'V_min',min(r.bus(:,8)),'V_max',max(r.bus(:,8)), ...
        'AC_losses',sum(r.branch(:,14)+r.branch(:,16)), ...
        'native_P_change',sum(r.gen(~m.userdata.ac_system.external_generator_mask,2)-m.gen(~m.userdata.ac_system.external_generator_mask,2)), ...
        'external_P_change',max(abs(r.gen(m.userdata.ac_system.external_generator_mask,2)-m.gen(m.userdata.ac_system.external_generator_mask,2))), ...
        'objective',r.f,'raw_output',r.raw.output);
    fprintf('CAPABILITY h%d success%d %.1fs Pviol%.3g Qviol%.3g Vviol%.3g losses%.3f\n',h,success,elapsed,a.P_viol,a.Q_viol,a.V_viol,a.AC_losses);
    save(fullfile(out,sprintf('h%d.mat',h)),'m','r','opt','a');checks=[checks a]; %#ok<AGROW>
    fid=fopen(fullfile(out,'capability_probe.json'),'w');fprintf(fid,'%s\n',jsonencode(checks,'PrettyPrint',true));fclose(fid);
end
end
