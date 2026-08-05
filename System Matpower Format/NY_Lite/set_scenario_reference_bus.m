function [mpc, report] = set_scenario_reference_bus(mpc, selector, options)
%SET_SCENARIO_REFERENCE_BUS Move the real-power slack to an external unit.
%   selector is a generator index by default. Set options.selector_type to
%   'bus_id' to select an online generator at a bus.

if nargin < 2 || isempty(selector), error('A reference generator or bus selector is required.'); end
if nargin < 3, options=struct(); end
if ~isfield(options,'selector_type'), options.selector_type='gen_idx'; end
if ~isfield(options,'require_external'), options.require_external=true; end

BUS_I=1; BUS_TYPE=2; PQ=1; PV=2; REF=3; GEN_BUS=1; GEN_STATUS=8;
mpc=attach_nyiso_zone_metadata(mpc);
if strcmpi(options.selector_type,'bus_id')
    gi=find(mpc.gen(:,GEN_BUS)==selector & mpc.gen(:,GEN_STATUS)>0,1);
    if isempty(gi), error('No online generator at bus %d.',selector); end
else
    gi=selector;
    if gi<1 || gi>size(mpc.gen,1) || mpc.gen(gi,GEN_STATUS)<=0
        error('Selected reference generator is invalid or offline.');
    end
end
new_bus=mpc.gen(gi,GEN_BUS);
new_bi=find(mpc.bus(:,BUS_I)==new_bus,1);
if options.require_external && mpc.userdata.nyiso_zone_id(new_bi)>0
    error('Selected reference bus %d is inside NY; choose an external balancing unit.',new_bus);
end
old_bi=find(mpc.bus(:,BUS_TYPE)==REF);
old_buses=mpc.bus(old_bi,BUS_I);
for k=1:numel(old_bi)
    hasgen=any(mpc.gen(:,GEN_BUS)==old_buses(k) & mpc.gen(:,GEN_STATUS)>0);
    if hasgen, mpc.bus(old_bi(k),BUS_TYPE)=PV; else, mpc.bus(old_bi(k),BUS_TYPE)=PQ; end
end
mpc.bus(new_bi,BUS_TYPE)=REF;
report=struct('reference_gen_idx',gi,'reference_bus_id',new_bus, ...
    'previous_reference_bus_ids',old_buses(:)');
mpc.userdata.ny_lite.reference_bus_report=report;
end
