function [values,weights]=physical_interface_flows(result,parent,full_parent)
% Exact same original-parent, first/last-physical-terminal operator as audit.
% Columns: legacy signed literal-from; oriented source; oriented target; loss.
root=fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
persistent definitions
if isempty(definitions),definitions=jsondecode(fileread(fullfile(root,'output','nygrid_2025_downstate','replay','interface_definitions.json')));end
nb=size(result.branch,1);mapping=full_parent.('if').map;ni=numel(definitions);assert(ni==7);
assert(isequal(string({definitions.interface})',string(full_parent.userdata.slim.interface_names(:))));
weights.PF=zeros(ni,nb,3);weights.PT=zeros(ni,nb,3);
for j=1:ni
    signed=mapping(mapping(:,1)==definitions(j).inherited_interface_id,2);assert(~isempty(signed));
    for member=signed(:)'
        p=abs(member);sgn=sign(member);chain=find(parent==p);
        cursor=full_parent.branch(p,1);target=full_parent.branch(p,2);remaining=chain(:)';ordered=[];
        while ~isempty(remaining)
            next=remaining(result.branch(remaining,1)==cursor);assert(isscalar(next));
            ordered(end+1)=next;remaining(remaining==next)=[];cursor=result.branch(next,2); %#ok<AGROW>
        end
        assert(~isempty(ordered)&&cursor==target&&all(result.branch(ordered,11)>0));
        first=ordered(1);last=ordered(end);
        weights.PF(j,first,1)=weights.PF(j,first,1)+sgn;
        if sgn>0
            weights.PF(j,first,2)=weights.PF(j,first,2)+1;weights.PT(j,last,3)=weights.PT(j,last,3)-1;
        else
            weights.PT(j,last,2)=weights.PT(j,last,2)+1;weights.PF(j,first,3)=weights.PF(j,first,3)-1;
        end
    end
end
values=zeros(ni,4);
for k=1:3,values(:,k)=weights.PF(:,:,k)*result.branch(:,14)+weights.PT(:,:,k)*result.branch(:,16);end
values(:,4)=values(:,2)-values(:,3);
end
