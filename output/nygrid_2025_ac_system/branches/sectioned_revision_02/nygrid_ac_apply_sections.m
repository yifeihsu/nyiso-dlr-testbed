function [mpc,info]=nygrid_ac_apply_sections(mpc,branch_keys)
%NYGRID_AC_APPLY_SECTIONS Declared cascaded-pi and fixed-reactor design layer.
% Input is the unsolved full191/192 case after the frozen engineering overlay.
% Generator powers, six-transfer controls and original PD/QD/GS are preserved.
% Hardware ampere limits apply only at original ends. Static cable-conductor
% ampere ceilings apply on every cable section and have no IEEE738 claim.
root=fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
folder=fullfile(root,'output','nygrid_2025_ac_system','branches');
file=fullfile(folder,'sectioned_design_plan.mat');receipt=fullfile(folder,'sectioned_design_receipt.json');
assert(isfile(file)&&isfile(receipt),'acSections:MissingDesign','Build the sectioned design first.');
persistent p signature
fi=dir(file);ri=dir(receipt);current=[fi.bytes fi.datenum ri.bytes ri.datenum];
if isempty(p)||~isequal(signature,current)
    proof=jsondecode(fileread(receipt));
    assert(proof.passed&&proof.design_construction_checked&&~proof.operating_AC_or_thermal_solver_run, ...
        'acSections:Proof','Invalid construction proof.');
    assert(strcmp(file_sha256(file),proof.plan_file.sha256),'acSections:Fingerprint','Section plan differs from receipt.');
    p=load(file);signature=current;
end
assert(~isfield(mpc,'userdata')||~isfield(mpc.userdata,'ac_sections'), ...
    'acSections:AlreadyApplied','Do not apply segmentation or reactors twice.');
n0=size(mpc.branch,1);nb0=size(mpc.bus,1);
assert(ismember(n0,[410 413])&&ismember(nb0,[191 192])&&size(mpc.branch,2)==13, ...
    'acSections:ParentShape','Use an unsolved full191/192 engineering case.');
keys=string(branch_keys(:));
assert(numel(keys)==n0&&isequal(keys,string(p.base_branch_keys(1:n0))'), ...
    'acSections:ParentKeys','Original branch identities differ.');
assert(mpc.baseMVA==100&&p.baseMVA==100&&isequal(mpc.branch(:,1:2),p.base_branch_reference(1:n0,1:2)) ...
    &&max(abs(mpc.branch(:,3:5)-p.base_branch_reference(1:n0,3:5)),[],'all')<1e-10, ...
    'acSections:ParentParameters','Apply the frozen raw engineering R/X/B before sectioning.');
oldbus=mpc.bus;oldbranch=mpc.branch;oldgen=mpc.gen;
if isfield(mpc,'dcline'),olddc=mpc.dcline;else,olddc=[];end
if isfield(mpc,'bus_name'),names=mpc.bus_name(:);else,names=cellstr("BUS "+string(mpc.bus(:,1)));end
raw_limits=p.base_terminal_current_limit_A;
limits=raw_limits(1:n0,:);cable_limits=nan(n0,2);
parent_rows=(1:n0)';section_index=ones(n0,1);section_counts=ones(n0,1);
physical_from=true(n0,1);physical_to=true(n0,1);
base_thermal=struct_rows(p.base_thermal_segments);base_cable=struct_rows(p.base_cable_segments);
thermal=struct([]);cables=struct([]);reactors=struct([]);added=struct([]);
for i=1:n0
    z=oldbranch(i,:);active=z(11)>0;n=1;
    if active,n=double(p.section_count(i));end
    f=z(1);t=z(2);rf=find(oldbus(:,1)==f);rt=find(oldbus(:,1)==t);
    assert(isscalar(rf)&&isscalar(rt),'acSections:Endpoint','Unknown original bus.');
    rows=i;
    if n>1
        assert(nnz([base_thermal.branch_row]==i)<=1,'acSections:HeterogeneousLongLine', ...
            'A long heterogeneous OH corridor requires an explicitly ordered section construction.');
        assert(ismember(z(9),[0 1])&&z(10)==0&&oldbus(rf,10)==oldbus(rt,10), ...
            'acSections:NonLine','Only equal-voltage, zero-phase line circuits may be split.');
        internal=60000+100*i+(1:n-1);
        assert(~any(ismember(internal,mpc.bus(:,1))),'acSections:BusCollision','Internal bus IDs collide.');
        for j=1:n-1
            frac=j/n;a=oldbus(rf,:);b=oldbus(rt,:);v=zeros(1,13);
            v(1)=internal(j);v(2)=1;v(7)=a(7);v(8)=(1-frac)*a(8)+frac*b(8);
            v(9)=(1-frac)*a(9)+frac*b(9);v(10)=a(10);v(11)=a(11);
            v(12)=min(a(12),b(12));v(13)=max(a(13),b(13));
            assert(v(12)>v(13)&&v(13)>0,'acSections:VoltageBounds','Invalid internal-bus range.');
            mpc.bus(end+1,:)=v;names{end+1,1}=sprintf('SYNTHETIC LINE %d INTERNAL %d',i,j);
            added_row=struct('bus_id',internal(j),'original_branch_row',i, ...
                'original_corridor_key',char(keys(i)),'stationing_fraction',frac, ...
                'computational_line_section_bus',true,'physical_station_claim',false);
            if isempty(added),added=added_row;else,added(end+1)=added_row;end %#ok<AGROW>
        end
        nodes=[f internal t];limits(i,2)=NaN;physical_to(i)=false;
        for j=1:n
            part=z;part(1:2)=nodes(j:j+1);part(3:5)=part(3:5)/n;
            part(6:8)=0; % exact hardware A at physical ends; no invented apparatus at taps
            key=string(sprintf('%s:SECTION:%d_OF_%d',p.base_branch_keys{i},j,n));
            if j==1
                mpc.branch(i,:)=part;keys(i)=key;section_counts(i)=n;
            else
                r=size(mpc.branch,1)+1;mpc.branch(r,:)=part;keys(r,1)=key;rows(end+1)=r; %#ok<AGROW>
                limits(r,:)=[NaN NaN];if j==n,limits(r,2)=raw_limits(i,2);end
                cable_limits(r,:)=[NaN NaN];parent_rows(r,1)=i;section_index(r,1)=j;section_counts(r,1)=n;
                physical_from(r,1)=false;physical_to(r,1)=j==n;
            end
        end
    end
    if active
        for j=1:n
            r=rows(j);
            if any([base_cable.branch_row]==i),cable_limits(r,:)=raw_limits(i,:);end
            ts=base_thermal([base_thermal.branch_row]==i);
            cs=base_cable([base_cable.branch_row]==i);
            for k=1:numel(ts)
                s=section_record(ts(k),i,char(p.base_branch_keys{i}),r,char(keys(r)),j,n);
                if isempty(thermal),thermal=s;else,thermal(end+1)=s;end %#ok<AGROW>
            end
            for k=1:numel(cs)
                s=section_record(cs(k),i,char(p.base_branch_keys{i}),r,char(keys(r)),j,n);
                if isempty(cables),cables=s;else,cables(end+1)=s;end %#ok<AGROW>
            end
        end
    end
    if p.reactor_total_nominal_mvar(i)>0
        q=0;if active,q=double(p.reactor_total_nominal_mvar(i));end
        mpc.bus(rf,6)=mpc.bus(rf,6)-q/2;mpc.bus(rt,6)=mpc.bus(rt,6)-q/2;
        reactor_row=struct('original_branch_row',i,'original_corridor_key',char(p.base_branch_keys{i}), ...
            'from_bus',f,'to_bus',t,'associated_line_active',active, ...
            'applied_total_reactor_mvar_at1pu',q,'from_bus_BS_delta_mvar',-q/2,'to_bus_BS_delta_mvar',-q/2, ...
            'policy',char(p.reactor_policy{i}),'fraction',.75, ...
            'actual_absorption_follows_voltage_squared',true,'asbuilt_equipment_claim',false);
        if isempty(reactors),reactors=reactor_row;else,reactors(end+1)=reactor_row;end %#ok<AGROW>
    end
end
mpc.bus_name=names;
assert(numel(unique(keys))==numel(keys),'acSections:DuplicateKey','Runtime keys must be unique.');
assert(isequaln(mpc.bus(1:nb0,[1:5 7:13]),oldbus(:,[1:5 7:13])) ...
    &&all(mpc.bus(nb0+1:end,3:6)==0,'all')&&isequaln(mpc.gen,oldgen), ...
    'acSections:OperatingInput','Original input or new-node injection changed.');
if ~isempty(olddc),assert(isequaln(mpc.dcline,olddc),'acSections:TransferMutation','Fixed transfers changed.');end
for i=1:n0
    use=parent_rows==i;
    assert(max(abs(sum(mpc.branch(use,3:5),1)-oldbranch(i,3:5)))<1e-12, ...
        'acSections:CoefficientSum','Section totals differ from corridor R/X/B.');
    assert(nnz(isfinite(limits(use,1)))==isfinite(raw_limits(i,1)) ...
        &&nnz(isfinite(limits(use,2)))==isfinite(raw_limits(i,2)), ...
        'acSections:ArtificialHardware','Artificial taps acquired hardware limits.');
end
mapping=table((1:size(mpc.branch,1))',keys,parent_rows,section_index,section_counts,physical_from,physical_to, ...
    'VariableNames',{'runtime_branch_row','runtime_branch_key','original_branch_row','section_index','section_count', ...
    'physical_terminal_from','physical_terminal_to'});
info=struct('status',p.metadata.status,'design_passed',true,'design_receipt_sha256',file_sha256(receipt), ...
    'design_plan_sha256',file_sha256(file),'sectioned_design_plan_sha256',file_sha256(file), ...
    'branch_keys',{cellstr(keys)},'branch_parent_row',parent_rows, ...
    'branch_map',mapping,'added_bus_map',added,'thermal_segments',thermal,'cable_segments',cables, ...
    'terminal_current_limit_A',limits,'static_cable_current_limit_A',cable_limits, ...
    'reactor_ledger',reactors,'original_bus_count',nb0,'original_branch_count',n0, ...
    'added_bus_count',size(mpc.bus,1)-nb0,'added_branch_count',size(mpc.branch,1)-n0, ...
    'original_bus_BS',oldbus(:,6),'reactor_BS_delta',mpc.bus(1:nb0,6)-oldbus(:,6), ...
    'old_PD_QD_GS_gen_and_transfers_preserved',true,'current_gamma_lift',false, ...
    'whole_system_AC_or_thermal_qualification_claimed',false);
if ~isfield(mpc,'userdata'),mpc.userdata=struct();end
mpc.userdata.ac_sections=info;
end

function rows=struct_rows(value)
if iscell(value),rows=[value{:}];else,rows=value;end
end
function s=section_record(s,parent,key,row,runtimekey,j,n)
s.original_branch_row=parent;s.original_corridor_key=key;s.branch_row=row;s.branch_key=runtimekey;
s.section_index=j;s.section_count=n;s.corridor_segment_length_m=s.segment_length_m;s.segment_length_m=s.segment_length_m/n;
s.reference_r_pu=s.reference_r_pu/n;s.reference_x_pu=s.reference_x_pu/n;s.reference_b_pu=s.reference_b_pu/n;
end
function digest=file_sha256(path)
engine=java.security.MessageDigest.getInstance('SHA-256');fid=fopen(path,'rb');assert(fid>=0);cleanup=onCleanup(@()fclose(fid));
while ~feof(fid),bytes=fread(fid,1048576,'*uint8');if ~isempty(bytes),engine.update(typecast(bytes,'int8'));end,end
raw=typecast(engine.digest(),'uint8');digest=lower(reshape(dec2hex(raw,2)',1,[]));
end
