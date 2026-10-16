function full=restore_full_DC_parent(prior,root)
% Restore the authoritative pre-AC-engineering191/192 topology and injections.
full=prior;
if prior.userdata.dover.new_parameters_applied
    n=load(fullfile(root,'output','nygrid_2025_dover_parameters','network','x_nominal.mat'),'full_case');
    source=n.full_case;
else
    n=load(fullfile(root,'output','nygrid_2025_line_parameters','overlays','engineering_nominal','full191_network_cases.mat'));
    source=n.(prior.userdata.slim.network_state);
end
full.bus=source.bus;full.branch=source.branch;full.bus_name=source.bus_name(:);
[ok,ix]=ismember(prior.bus(:,1),full.bus(:,1));assert(all(ok));
full.bus(:,2)=1;full.bus(:,3:6)=0;full.bus(:,8)=1;full.bus(:,9)=0;
full.bus(ix,:)=prior.bus;
full.branch(211,11)=0;
if prior.userdata.dover.new_parameters_applied
    full.branch(411:412,10)=prior.userdata.dover.bank_shift_model_deg(:);
end
full.('if')=source.('if');
assert(all(full.bus(~ismember(full.bus(:,1),prior.bus(:,1)),3:6)==0,'all'));
assert(isequal(full.gen,prior.gen)&&isequal(full.dcline,prior.dcline));
end
