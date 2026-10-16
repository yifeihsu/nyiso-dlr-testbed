function validate_matlab_moses(artifact_folder)
%VALIDATE_MATLAB_MOSES Independent corrected-landing and PAR diagnostic checks.
% The promoted loader permits the source-confirmed hydro-zone repair only.
% PAR orientations are applied manually here as unpromoted diagnostic fixtures.
root=fileparts(fileparts(fileparts(mfilename('fullpath'))));
if nargin<1,artifact_folder=fullfile(root,'output','nygrid_2025_moses_audit');end
addpath(fullfile(root,'System Matpower Format'));
clear npcc_nygrid_2025_moses_corrected_dc npcc_nygrid_2025_slim_dc npcc_nygrid_2025_full_dc
assert(~isempty(which('rundcpf')),'mosesValidation:MATPOWER','MATPOWER must be on the configured MATLAB path.');
baseline=fullfile(root,'output','nygrid_2025_dispatch','dispatch');
d=load(fullfile(baseline,'dispatch.mat'),'timestamp_utc','dispatch_qualified','gen_pg','bus_pd','bus_qd','dc_pf','hour_index');
q=logical(d.dispatch_qualified(:));assert(nnz(q)==8663);
t=datetime(string(d.timestamp_utc),'InputFormat',"yyyy-MM-dd'T'HH:mm:ss'Z'",'TimeZone','UTC');
t.TimeZone='America/New_York';quarter=[];
for mo=[1 4 7 10],quarter=[quarter;find(month(t)==mo&q,1)];end %#ok<AGROW>
good=find(q);[~,peak]=max(sum(d.bus_pd(good,:),2));[~,valley]=min(sum(d.bus_pd(good,:),2));
dst=find(month(t)==11&day(t)==2&hour(t)==1&q);
par_path=fullfile(artifact_folder,'exchanges','par_stlawrence_hourly_2025.csv');
par=readtable(par_path,'Delimiter',',','ReadVariableNames',true, ...
    'VariableNamingRule','preserve','TextType','string');
assert(all(ismember({'coverage_qualified','combined_raw_mw'},par.Properties.VariableNames)), ...
    'mosesValidation:PARSchema','Expected exact CSV qualification and flow columns.');
par_qualified=ismember(lower(string(par.coverage_qualified)),["true","1"]);
options=mpoption('model','DC','verbose',0,'out.all',0);checks=table();
files={fullfile(baseline,'dispatch.mat'),fullfile(baseline,'dispatch_bounds.mat'), ...
    fullfile(root,'output','nygrid_2025_slim','network','network_cases.mat'),par_path, ...
    fullfile(artifact_folder,'corrected','fleet','fleet_register.csv'), ...
    which('npcc_nygrid_2025_moses_corrected_dc'),which('npcc_nygrid_2025_slim_dc'), ...
    which('npcc_nygrid_2025_full_dc'),which('npcc_nygrid_2025_slim_interfaces'), ...
    fullfile(root,'scripts','nygrid_2025_moses_audit','dc_control.py'),[mfilename('fullpath'),'.m']};
extreme_table=table();
for topology={'dated','year_end'}
    topology=topology{1};
    for control={'hydro_zone_corrected','hydro_zone_par_from_moses','hydro_zone_par_toward_moses'}
        control=control{1};variant=[topology,'_',control];diagnostic=~strcmp(control,'hydro_zone_corrected');
        path=fullfile(artifact_folder,'replay',[variant,'.mat']);
        p=load(path,'hour_index','qualified','network_state_ids','branch_pf','bus_va','interface_pf', ...
            'corrected_generator_buses','equivalent_shift_deg','source_control_branch_row','raw_PAR_to_branch_sign','gamma');
        assert(isequal(p.hour_index(:),d.hour_index(:)));
        expected=q;if diagnostic,expected=q&par_qualified;end
        assert(isequal(logical(p.qualified(:)),expected),'mosesValidation:Cohort','Saved qualification mask changed.');
        selected=quarter;
        if diagnostic
            qualified=find(expected);[~,mi]=min(p.equivalent_shift_deg(qualified));[~,ma]=max(p.equivalent_shift_deg(qualified));
            selected=[selected;qualified(mi);qualified(ma)]; %#ok<AGROW>
            if strcmp(topology,'dated')
                for key={"refined_2025_may21_case","refined_2025_case"}
                    selected=[selected;find(string(p.network_state_ids)==key{1}&expected,1)]; %#ok<AGROW>
                end
            end
            extreme_table=[extreme_table;table(string(variant),min(p.equivalent_shift_deg(expected)),max(p.equivalent_shift_deg(expected)))]; %#ok<AGROW>
        elseif strcmp(topology,'dated')
            for key=unique(string(p.network_state_ids))'
                indices=find(string(p.network_state_ids)==key&expected);
                selected=[selected;indices(1);indices(end)]; %#ok<AGROW>
            end
            selected=[selected;good(peak);dst]; %#ok<AGROW>
        else
            selected=[selected;good(peak);good(valley)]; %#ok<AGROW>
        end
        for h=unique(selected)'
            assert(expected(h),'mosesValidation:Selection','Selected hour is unqualified.');
            m=npcc_nygrid_2025_moses_corrected_dc(h,'hydro_zone_corrected',topology);
            assert(isequal(m.gen(:,1),p.corrected_generator_buses(:)),'mosesValidation:Landing','Generator bus correction differs.');
            assert(isequal(m.bus(1:140,3),d.bus_pd(h,:)')&&isequal(m.bus(1:140,4),d.bus_qd(h,:)'));
            assert(all(m.bus(141:end,3:6)==0,'all'),'mosesValidation:AddedInjection','Added stations have nonzero injection.');
            assert(isequal(m.gen(:,2),d.gen_pg(h,:)')&&isequal(m.dcline(:,4),d.dc_pf(h,:)'));
            row=double(p.source_control_branch_row);
            assert(row==211&&isequal(m.branch(row,1:2),[48 100]));
            if diagnostic
                m.branch(row,10)=p.equivalent_shift_deg(h);
                m.userdata.moses_correction.manual_PAR_diagnostic=true;
                m.userdata.moses_correction.operationally_promoted=false;
                m.userdata.moses_correction.PAR_direction_verified=false;
            else
                assert(m.branch(row,10)==0,'mosesValidation:PrimaryControl','Confirmed hydro repair must not enable unverified PAR control.');
            end
            [r,ok]=rundcpf(m,options);assert(ok,'mosesValidation:Solve','DC solve failed.');
            measured=npcc_nygrid_2025_slim_interfaces(r);
            branch_error=max(abs(r.branch(:,14)-p.branch_pf(h,:)'));
            angle_error=max(abs(r.bus(:,9)-p.bus_va(h,:)'));
            generation_error=max(abs(r.gen(:,2)-d.gen_pg(h,:)'));
            bounds_error=max([0;r.gen(:,10)-r.gen(:,2);r.gen(:,2)-r.gen(:,9)]);
            interface_error=max(abs(measured.model_mw-p.interface_pf(h,:)'));
            target_error=0;
            if diagnostic
                target_error=abs(r.branch(row,14)-p.raw_PAR_to_branch_sign*p.gamma*par.combined_raw_mw(h));
            end
            assert(max([branch_error,angle_error,generation_error,bounds_error,interface_error,target_error])<1e-7, ...
                'mosesValidation:Mismatch','MATPOWER differs from saved corrected/diagnostic replay.');
            checks=[checks;table(string(variant),h,diagnostic,p.equivalent_shift_deg(h),branch_error,angle_error, ...
                generation_error,bounds_error,interface_error,target_error)]; %#ok<AGROW>
        end
        files{end+1}=path; %#ok<AGROW>
    end
end
gap_rejected=false;
try,npcc_nygrid_2025_moses_corrected_dc(find(~q,1));
catch err,gap_rejected=strcmp(err.identifier,'nygrid2025:UnqualifiedHour');end
assert(gap_rejected,'mosesValidation:MissingSource','Missing-source hour was accepted.');
diagnostic_loader_rejected=false;
try,npcc_nygrid_2025_moses_corrected_dc(good(1),'hydro_zone_par_from_moses');
catch err,diagnostic_loader_rejected=strcmp(err.identifier,'mosesCorrection:Control');end
assert(diagnostic_loader_rejected,'mosesValidation:Promotion','Unverified PAR orientation exposed as an operational loader mode.');
checks.Properties.VariableNames={'variant','hour_index','unpromoted_PAR_diagnostic','equivalent_shift_degree', ...
    'branch_error_model_mw','angle_error_degree','generation_change_model_mw','bound_violation_model_mw', ...
    'interface_error_model_mw','PAR_target_error_model_mw'};
extreme_table.Properties.VariableNames={'variant','minimum_equivalent_shift_degree','maximum_equivalent_shift_degree'};
output=fullfile(artifact_folder,'validation');if ~isfolder(output),mkdir(output);end
writetable(checks,fullfile(output,'matlab_checks.csv'));
writetable(extreme_table,fullfile(output,'matlab_PAR_diagnostic_extremes.csv'));
dependencies=struct('path',{},'sha256',{});
for j=1:numel(files),dependencies(end+1)=struct('path',files{j},'sha256',file_sha256(files{j}));end %#ok<AGROW>
summary=struct('passed',true,'fresh_MATPOWER_snapshots',height(checks), ...
    'primary_confirmed_repair_snapshots',nnz(~checks.unpromoted_PAR_diagnostic), ...
    'unpromoted_PAR_diagnostic_snapshots',nnz(checks.unpromoted_PAR_diagnostic), ...
    'maximum_branch_error_model_mw',max(checks.branch_error_model_mw), ...
    'maximum_generation_change_model_mw',max(checks.generation_change_model_mw), ...
    'maximum_bound_violation_model_mw',max(checks.bound_violation_model_mw), ...
    'maximum_interface_error_model_mw',max(checks.interface_error_model_mw), ...
    'maximum_PAR_target_error_model_mw',max(checks.PAR_target_error_model_mw), ...
    'maximum_absolute_equivalent_SHIFT_degree',max(abs(checks.equivalent_shift_degree)), ...
    'missing_source_hour_rejected',gap_rejected,'unpromoted_PAR_loader_mode_rejected',diagnostic_loader_rejected, ...
    'equivalent_SHIFT_is_physical_PAR_tap_measurement',false,'PAR_direction_verified',false, ...
    'PAR_scenarios_promoted',false,'AC_or_thermal_feasibility_certified',false, ...
    'MATPOWER_solver',which('rundcpf'),'MATLAB_version',version,'dependencies',dependencies);
fid=fopen(fullfile(output,'matlab_validation.json'),'w');assert(fid>=0);cleanup=onCleanup(@()fclose(fid));
fprintf(fid,'%s\n',jsonencode(summary,'PrettyPrint',true));disp(summary);
end

function digest=file_sha256(path)
engine=java.security.MessageDigest.getInstance('SHA-256');fid=fopen(path,'rb');assert(fid>=0);cleanup=onCleanup(@()fclose(fid));
while ~feof(fid),bytes=fread(fid,1048576,'*uint8');if ~isempty(bytes),engine.update(typecast(bytes,'int8'));end,end
raw=typecast(engine.digest(),'uint8');digest=lower(reshape(dec2hex(raw,2)',1,[]));
end
