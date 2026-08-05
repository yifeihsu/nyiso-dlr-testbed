function rows = run_npcc_baseline_audit(output_file)
%RUN_NPCC_BASELINE_AUDIT Run a real MATPOWER baseline audit and write CSV.

if nargin<1 || isempty(output_file)
    output_file=fullfile(fileparts(mfilename('fullpath')),'baseline_npcc_summary.csv');
end
case_dir=fileparts(fileparts(mfilename('fullpath'))); addpath(case_dir); addpath(fileparts(mfilename('fullpath')));
if exist('runpf','file')~=2 || exist('loadcase','file')~=2
    error('run_npcc_baseline_audit:MatpowerMissing','MATPOWER is required.');
end
define_constants;
mpc0=attach_nyiso_zone_metadata(loadcase('npcc_original'));
struct_hash=ny_lite_case_fingerprint(mpc0); op_hash=ny_lite_operating_point_fingerprint(mpc0);
mpopt=mpoption('verbose',0,'out.all',0);
results0=runpf(mpc0,mpopt);
rows={};
rows(end+1,:)={'power_flow_success',double(results0.success),'flag','runpf',''};
rows(end+1,:)={'structural_fingerprint',NaN,'text','input',struct_hash};
rows(end+1,:)={'operating_point_fingerprint',NaN,'text','input',op_hash};
if ~results0.success
    write_summary_csv(output_file,rows); return;
end
results0=attach_nyiso_zone_metadata(results0);
ny_mask=results0.userdata.nyiso_zone_id>0; online=results0.gen(:,GEN_STATUS)>0;
ny_gen=ismember(results0.gen(:,GEN_BUS),results0.bus(ny_mask,BUS_I));
rows(end+1,:)={'total_system_load',sum(results0.bus(:,PD)),'MW','runpf',''};
rows(end+1,:)={'total_NY_load',sum(results0.bus(ny_mask,PD)),'MW','runpf',''};
rows(end+1,:)={'NY_generation',sum(results0.gen(online & ny_gen,PG)),'MW','runpf',''};
rows(end+1,:)={'system_losses',sum(results0.branch(:,PF)+results0.branch(:,PT)),'MW','runpf',''};
rows(end+1,:)={'minimum_voltage',min(results0.bus(:,VM)),'p.u.','runpf',''};
rows(end+1,:)={'maximum_voltage',max(results0.bus(:,VM)),'p.u.','runpf',''};
rows(end+1,:)={'max_P_above_PMAX',max([0;results0.gen(online,PG)-results0.gen(online,PMAX)]),'MW','audit',''};
rows(end+1,:)={'max_P_below_PMIN',max([0;results0.gen(online,PMIN)-results0.gen(online,PG)]),'MW','audit',''};
rows(end+1,:)={'max_Q_above_QMAX',max([0;results0.gen(online,QG)-results0.gen(online,QMAX)]),'MVAr','audit',''};
rows(end+1,:)={'max_Q_below_QMIN',max([0;results0.gen(online,QMIN)-results0.gen(online,QG)]),'MVAr','audit',''};
ref_buses=results0.bus(results0.bus(:,BUS_TYPE)==REF,BUS_I);
rows(end+1,:)={'reference_bus_id',ref_buses(1),'bus','runpf',''};
defs=ny_lite_interface_definitions(results0); flows=ny_lite_interface_flows(results0,defs);
for k=1:numel(flows)
    rows(end+1,:)={['interface_' flows(k).interface_name],flows(k).flow_mw,'MW','runpf',flows(k).zone_boundary}; %#ok<AGROW>
end
write_summary_csv(output_file,rows);
end
function write_summary_csv(path,rows)
fid=fopen(path,'w'); if fid<0,error('Cannot open %s.',path);end
cleanup=onCleanup(@()fclose(fid)); fprintf(fid,'metric,value,unit,source,note\n');
for k=1:size(rows,1)
    if isnan(rows{k,2}), value=''; else, value=sprintf('%.10g',rows{k,2}); end
    fprintf(fid,'%s,%s,%s,%s,%s\n',esc(rows{k,1}),value,esc(rows{k,3}),esc(rows{k,4}),esc(rows{k,5}));
end
end
function out=esc(v)
out=char(v); if any(out==',')||any(out=='"'),out=['"' strrep(out,'"','""') '"'];end
end
