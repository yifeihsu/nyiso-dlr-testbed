function run_current_diagnostic()
% Fresh unchanged-input diagnostics; convergence is not AC feasibility.
root=fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
addpath(fullfile(root,'System Matpower Format'));
out=fullfile(root,'output','nygrid_2025_ac_system','ac_validation','initial_diagnostic');
if ~isfolder(out),mkdir(out);end
rows=struct([]); inventories=struct([]);
fprintf('MATPOWER runopf=%s; IPOPT=%s\n',which('runopf'),which('ipopt'));
for h=[4000 8508]
    original=npcc_nygrid_2025_dover_dc(h,'bounded','x_nominal');
    for detail=[false true]
        m=original;label='current148';
        if detail
            if original.userdata.dover.new_parameters_applied
                n=load(fullfile(root,'output','nygrid_2025_dover_parameters','network','x_nominal.mat'));
                c=n.full_case;c.branch(411:412,10)=original.userdata.dover.bank_shift_model_deg;
            else
                n=load(fullfile(root,'output','nygrid_2025_line_parameters','overlays','engineering_nominal','full191_network_cases.mat'));
                c=n.(original.userdata.slim.network_state);
            end
            m.bus=c.bus;m.branch=c.branch;m.bus_name=c.bus_name(:);
            [ok,ix]=ismember(original.bus(:,1),m.bus(:,1));assert(all(ok));
            m.bus(:,3:4)=0;m.bus(ix,3:4)=original.bus(:,3:4);
            m.bus(:,2)=1;m.bus(ismember(m.bus(:,1),m.gen(m.gen(:,8)>0,1)),2)=2;
            refs=original.bus(original.bus(:,2)==3,1);m.bus(ismember(m.bus(:,1),refs),2)=3;
            m.branch(211,11)=0;label=sprintf('full%d',size(m.bus,1));
        end
        cost_size=[0 0];cost_models=[];
        if isfield(m,'gencost'),cost_size=size(m.gencost);cost_models=unique(m.gencost(:,1))';end
        inventory=struct('hour',h,'case',label,'buses',size(m.bus,1),'branches',size(m.branch,1), ...
            'generators',size(m.gen,1),'dclines',size(m.dcline,1),'baseMVA',m.baseMVA, ...
            'sum_PD',sum(m.bus(:,3)),'sum_QD',sum(m.bus(:,4)),'sum_PG',sum(m.gen(:,2)), ...
            'sum_Qmax',sum(m.gen(:,4)),'sum_Qmin',sum(m.gen(:,5)), ...
            'nonzero_Q_limits',nnz(m.gen(:,4)~=0|m.gen(:,5)~=0), ...
            'sum_GS',sum(m.bus(:,5)),'sum_BS',sum(m.bus(:,6)), ...
            'nonpositive_active_X',nnz(m.branch(:,11)>0&m.branch(:,4)<=0), ...
            'active_unrated',nnz(m.branch(:,11)>0&m.branch(:,6)==0), ...
            'gencost_size',cost_size,'cost_models',cost_models, ...
            'has_userfcn',isfield(m,'userfcn'),'dcline_matrix',m.dcline);
        inventories=[inventories inventory]; %#ok<AGROW>
        fprintf('%s hour%d: PD %.3f QD %.3f Qbounds[%.3f,%.3f], %d nonzero-Q rows\n',label,h,inventory.sum_PD,inventory.sum_QD,inventory.sum_Qmin,inventory.sum_Qmax,inventory.nonzero_Q_limits);
        save(fullfile(out,sprintf('%s_h%d_input.mat',label,h)),'m');
        for method={'PF_NR','OPF_MIPS'}
            a=struct('hour',h,'case',label,'method',method{1},'success',false,'seconds',NaN, ...
                'error_identifier','','error_message','','VM_min',NaN,'VM_max',NaN, ...
                'P_bound_violation',NaN,'Q_bound_violation',NaN,'transfer_Q_bound_violation',NaN,'V_bound_violation',NaN,'objective',NaN);
            t=tic;
            try
                opt=mpoption('model','AC','verbose',1,'out.all',0,'pf.alg','NR','pf.nr.max_it',40,'pf.tol',1e-8,'pf.enforce_q_lims',0,'opf.ac.solver','MIPS','mips.max_it',60);
                if strcmp(method{1},'PF_NR'),[r,ok]=runpf(m,opt);else,[r,ok]=runopf(m,opt);end
                a.success=logical(ok);a.VM_min=min(r.bus(:,8));a.VM_max=max(r.bus(:,8));
                a.P_bound_violation=max([0;r.gen(:,10)-r.gen(:,2);r.gen(:,2)-r.gen(:,9)]);
                a.Q_bound_violation=max([0;r.gen(:,5)-r.gen(:,3);r.gen(:,3)-r.gen(:,4)]);
                a.transfer_Q_bound_violation=max([0;m.dcline(:,12)-r.dcline(:,6);r.dcline(:,6)-m.dcline(:,13);m.dcline(:,14)-r.dcline(:,7);r.dcline(:,7)-m.dcline(:,15)]);
                a.V_bound_violation=max([0;r.bus(:,13)-r.bus(:,8);r.bus(:,8)-r.bus(:,12)]);
                if isfield(r,'f'),a.objective=r.f;end
                save(fullfile(out,sprintf('%s_h%d_%s.mat',label,h,method{1})),'r','opt');
            catch err
                a.error_identifier=err.identifier;a.error_message=err.message;
            end
            a.seconds=toc(t);rows=[rows a]; %#ok<AGROW>
            fprintf('DIAGNOSTIC %s h%d %s success%d elapsed%.2f Qviol%.6g Vviol%.6g error=%s\n',label,h,method{1},a.success,a.seconds,a.Q_bound_violation,a.V_bound_violation,a.error_identifier);
            report=struct('diagnostic_complete',false,'unchanged_inputs',true,'assumptions_added',false,'inventories',inventories,'results',rows);
            fid=fopen(fullfile(out,'current_ac_diagnostic.json'),'w');fprintf(fid,'%s\n',jsonencode(report,'PrettyPrint',true));fclose(fid);
        end
    end
end
report.diagnostic_complete=true;fid=fopen(fullfile(out,'current_ac_diagnostic.json'),'w');fprintf(fid,'%s\n',jsonencode(report,'PrettyPrint',true));fclose(fid);
end
