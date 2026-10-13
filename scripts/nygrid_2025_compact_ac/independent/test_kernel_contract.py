"""Run independent MATLAB mutation/control fixtures for the compact kernel.

Only new independent JSON evidence is written. Source and reference cases
are not edited. Full PF comparisons are limited to one existing profile.
"""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,os,shutil,subprocess

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'output/nygrid_2025_compact_ac/independent'
CORE=ROOT/'scripts/nygrid_2025_compact_ac/core'


def record(path):
    with path.open('rb') as f:h=hashlib.file_digest(f,'sha256').hexdigest()
    return dict(path=path.relative_to(ROOT).as_posix(),sha256=h)


MATLAB=r"""
addpath('scripts/nygrid_2025_compact_ac/core');
addpath('scripts/nygrid_2025_ac_system/thermal');
addpath('scripts/nygrid_2025_ac_system/ac_validation');
addpath('scripts/nygrid_2025_acpf_profile_audit/acpf');
addpath('System Matpower Format/NY_Lite');
d=load('output/nygrid_2025_acpf_profile_audit/acpf/representative_h8508.mat');m=d.m;
fingerprints=struct('file',{},'saved_operator_fingerprint',{},'recomputed_operator_fingerprint',{},'matched',{});
files=dir('output/nygrid_2025_compact_ac/models/compact_ac_h*.mat');assert(numel(files)==5);
for fi=1:numel(files)
    saved=load(fullfile(files(fi).folder,files(fi).name));current=compact_ac_operator_fingerprint(saved.model);
    assert(strcmp(current,saved.model.operator_fingerprint));
    fingerprints(end+1)=struct('file',files(fi).name,'saved_operator_fingerprint',saved.model.operator_fingerprint, ...
        'recomputed_operator_fingerprint',current,'matched',true);
end
c=compact_ac_build(m);assert(size(c.bus,1)==148&&isempty(c.promoted_bus_ids));
opt=mpoption('model','AC','pf.alg','NR','pf.tol',1e-10,'pf.nr.max_it',50, ...
    'pf.enforce_q_lims',0,'exp.use_legacy_core',1,'verbose',0,'out.all',0);
checks=struct('test',{},'passed',{},'error',{});e=c.eliminated_full_rows(1);eid=m.bus(e,1);
names={'source_R','source_X','source_B','source_phase','source_tap','source_BS','source_GS','source_status'};
for j=1:numel(names)
    cc=c;
    switch j
        case 1,cc.detailed_mpc.branch(1,3)=cc.detailed_mpc.branch(1,3)*1.01;
        case 2,cc.detailed_mpc.branch(1,4)=cc.detailed_mpc.branch(1,4)*1.01;
        case 3,cc.detailed_mpc.branch(1,5)=cc.detailed_mpc.branch(1,5)+.01;
        case 4,cc.detailed_mpc.branch(411,10)=cc.detailed_mpc.branch(411,10)+1;
        case 5,cc.detailed_mpc.branch(411,9)=cc.detailed_mpc.branch(411,9)*1.01;
        case 6,cc.detailed_mpc.bus(e,6)=cc.detailed_mpc.bus(e,6)+1;
        case 7,cc.detailed_mpc.bus(e,5)=cc.detailed_mpc.bus(e,5)+1;
        case 8,cc.detailed_mpc.branch(1,11)=0;
    end
    got='';try,compact_ac_solve(cc,opt);catch err,got=err.identifier;end
    assert(strcmp(got,'compactAC:StaleNetwork'),'independent:MissingSourceGuard','Mutation %s produced %s',names{j},got);
    checks(end+1)=struct('test',names{j},'passed',true,'error',0);
end
names={'operator_Yred','operator_lift','operator_YfL','operator_YtL','operator_seriesL', ...
    'operator_from_current_base','operator_to_current_base','operator_retained_row_map','operator_branch_key','operator_branch_parent'};
for j=1:numel(names)
    cc=c;
    switch j
        case 1,cc.Yred(1,1)=cc.Yred(1,1)+.01;
        case 2,cc.voltage_lift(e,1)=cc.voltage_lift(e,1)+.01;
        case 3,cc.YfL(1,1)=cc.YfL(1,1)+.01;
        case 4,cc.YtL(1,1)=cc.YtL(1,1)+.01;
        case 5,cc.YseriesL(1,1)=cc.YseriesL(1,1)+.01;
        case 6,cc.from_current_base_A(1)=cc.from_current_base_A(1)*1.01;
        case 7,cc.to_current_base_A(1)=cc.to_current_base_A(1)*1.01;
        case 8,cc.retained_full_rows([1 2])=cc.retained_full_rows([2 1]);
        case 9,cc.branch_keys{1}='wrong_conductor_key';
        case 10,cc.branch_parent_row(1)=cc.branch_parent_row(1)+1;
    end
    got='';try,compact_ac_solve(cc,opt);catch err,got=err.identifier;end
    assert(strcmp(got,'compactAC:EditedOperator'),'independent:MissingOperatorGuard','Mutation %s produced %s',names{j},got);
    checks(end+1)=struct('test',names{j},'passed',true,'error',0);
end
cc=c;cc.bus(1,3)=cc.bus(1,3)+1;
got='';try,compact_ac_solve(cc,opt);catch err,got=err.identifier;end
assert(strcmp(got,'compactAC:EditedView'));checks(end+1)=struct('test','edited_compact_bus_view','passed',true,'error',0);
cc=c;cc.gen(1,2)=cc.gen(1,2)+1;
got='';try,compact_ac_solve(cc,opt);catch err,got=err.identifier;end
assert(strcmp(got,'compactAC:EditedView'));checks(end+1)=struct('test','edited_compact_gen_view','passed',true,'error',0);
mm=m;mm.bus(e,3)=5;cc=compact_ac_build(mm);
assert(size(cc.bus,1)==149&&isequal(cc.promoted_bus_ids,eid));
checks(end+1)=struct('test','nonzero_eliminated_load_promotes_only_its_bus','passed',true,'error',0);
mm=m;gg=m.gen(110,:);gg(1)=eid;gg(2:3)=0;gg(4)=100;gg(5)=-100;gg(8)=1;gg(9)=100;gg(10)=0;
mm.gen(end+1,:)=gg;mm.bus(e,2)=2;cc=compact_ac_build(mm);
assert(size(cc.bus,1)==149&&isequal(cc.promoted_bus_ids,eid));
checks(end+1)=struct('test','new_PV_generator_promotes_only_its_bus','passed',true,'error',0);
mm=m;mm.dcline(1,1)=eid;cc=compact_ac_build(mm);
assert(size(cc.bus,1)==149&&isequal(cc.promoted_bus_ids,eid));
checks(end+1)=struct('test','new_DC_terminal_promotes_only_its_bus','passed',true,'error',0);
mm=m;mm.bus(e,6)=mm.bus(e,6)+10;cc=compact_ac_build(mm);
assert(size(cc.bus,1)==148&&isempty(cc.promoted_bus_ids)&&norm(cc.Yred-c.Yred,inf)>1e-8);
checks(end+1)=struct('test','fixed_shunt_remains_eliminable_but_changes_operator','passed',true,'error',0);
mm=m;incident=mm.branch(:,1)==eid|mm.branch(:,2)==eid;mm.branch(incident,11)=0;mm.bus(e,6)=-10;
got='';try,compact_ac_build(mm);catch err,got=err.identifier;end
assert(strcmp(got,'compactAC:UnanchoredInterior'));
checks(end+1)=struct('test','isolated_shunted_interior_rejected','passed',true,'error',0);
small=struct('version','2','baseMVA',100,'bus',[1 3 0 0 0 0 1 1 0 345 1 1.1 .9;2 1 0 0 0 100 1 1 0 345 1 1.1 .9], ...
    'gen',[1 0 0 100 -100 1 100 1 100 0 zeros(1,11)],'branch',[1 2 0 1 0 100 0 0 0 0 1 -360 360]);
got='';try,compact_ac_build(small,1);catch err,got=err.identifier;end
assert(strcmp(got,'compactAC:SingularInterior'));
checks(end+1)=struct('test','anchored_resonant_singular_interior_rejected','passed',true,'error',0);
small.bus(2,6)=0;small.dcline=zeros(0,23);cc=compact_ac_build(small,1);
assert(size(cc.bus,1)==1&&numel(cc.operator_fingerprint)==64&&numel(cc.source_fingerprint)==64);
checks(end+1)=struct('test','empty_converter_and_promotion_arrays_hash','passed',true,'error',0);
fprintf('INDEPENDENT_GUARDS_PASS %d\n',numel(checks));
mi=ext2int(m,opt);
pairs=struct('qlim',{},'compact_success',{},'full_success',{},'voltage_error_pu',{},'PG_error_MW',{},'QG_error_MVAr',{},'branch_power_error_MVA',{},'current_error_A',{},'compact_outer_iterations',{});
for mode=[0 1 2]
    op=mpoption(opt,'pf.enforce_q_lims',mode);
    [rr,aa,fr]=compact_ac_solve(c,op);[dr,ds]=runpf(m,op);
    assert(rr.success&&ds&&aa.AC_equation_gate);
    vf=fr.bus(:,8).*exp(1i*deg2rad(fr.bus(:,9)));vd=dr.bus(:,8).*exp(1i*deg2rad(dr.bus(:,9)));
    ev=max(abs(vf-vd));ep=max(abs(fr.gen(:,2)-dr.gen(:,2)));eq=max(abs(fr.gen(:,3)-dr.gen(:,3)));
    eb=max(abs(fr.branch(:,14:17)-dr.branch(:,14:17)),[],'all');
    [ok,f]=ismember(m.branch(:,1),m.bus(:,1));assert(all(ok));[ok,t]=ismember(m.branch(:,2),m.bus(:,1));assert(all(ok));
    ia=1000*abs(complex(dr.branch(:,14),dr.branch(:,15)))./(sqrt(3)*m.bus(f,10).*dr.bus(f,8));
    ib=1000*abs(complex(dr.branch(:,16),dr.branch(:,17)))./(sqrt(3)*m.bus(t,10).*dr.bus(t,8));
    ei=max(abs(rr.recovered_line_current_A(:,1:2)-[ia ib]),[],'all');
    assert(ev<1e-7&&max([ep eq eb])<1e-4&&ei<1e-4);
    assert(isequal(rr.initial_control.generator_bus,mi.gen(:,1))&&isequal(rr.initial_control.generator_PG,mi.gen(:,2)) ...
       &&isequal(rr.initial_control.generator_QG,mi.gen(:,3))&&isequal(rr.initial_control.generator_VG,mi.gen(:,6)) ...
       &&rr.initial_control.converted_generator_count==size(mi.gen,1));
    pairs(end+1)=struct('qlim',mode,'compact_success',logical(rr.success),'full_success',logical(ds), ...
        'voltage_error_pu',ev,'PG_error_MW',ep,'QG_error_MVAr',eq,'branch_power_error_MVA',eb, ...
        'current_error_A',ei,'compact_outer_iterations',aa.reactive_control_outer_iterations);
    checks(end+1)=struct('test',sprintf('paired_8508_full_compact_qlim%d',mode),'passed',true,'error',max([ev ep eq eb ei]));
    fprintf('PAIRED_QLIM%d PASS V%.3g I%.3g outer%d\n',mode,ev,ei,aa.reactive_control_outer_iterations);
end
report=struct('passed',all([checks.passed]),'tests',numel(checks),'checks',checks,'paired_control_cases',pairs,'exported_fingerprints',fingerprints, ...
    'network_phase_shift_preserved',true,'full_converted_generator_setup_matches',true, ...
    'MATLAB_version',version,'scope','Independent kernel mutations and one existing profile under three Q-limit modes; not annual operating qualification');
fid=fopen('output/nygrid_2025_compact_ac/independent/kernel_guard_results.json','w');assert(fid>=0);
fprintf(fid,'%s\n',jsonencode(report,'PrettyPrint',true));fclose(fid);
"""


def main(skip_mode2=False):
    OUT.mkdir(parents=True,exist_ok=True)
    code=sorted(CORE.glob('*.m'))
    baseline=ROOT/'output/nygrid_2025_acpf_profile_audit/acpf/representative_h8508.mat'
    before=[record(p) for p in code+[baseline]]
    matlab=shutil.which('matlab') or r'C:\Program Files\MATLAB\R2026a\bin\matlab.exe'
    program=MATLAB.replace('for mode=[0 1 2]','for mode=[0 1]') if skip_mode2 else MATLAB
    if skip_mode2:program=program.replace('under three Q-limit modes','under Q-limit modes 0 and 1')
    result=subprocess.run([matlab,'-batch',program],cwd=ROOT,capture_output=True,text=True,timeout=240,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    print(result.stdout)
    if result.returncode:
        print(result.stderr);raise RuntimeError(f'MATLAB fixture failed: exit {result.returncode}')
    assert before==[record(p) for p in code+[baseline]],'Kernel/reference changed during fixtures'
    raw_path=OUT/'kernel_guard_results.json';raw=json.loads(raw_path.read_text())
    assert raw['passed']
    review=dict(passed=True,created_utc=datetime.now(timezone.utc).isoformat(),
        scope='Independent compact-kernel source inspection, source/operator mutation guards and paired detailed-control checks',
        independent_tests=raw['tests'],paired_Q_limit_modes=[0,1] if skip_mode2 else [0,1,2],extra_retained_nodes_on_baseline=0,
        five_saved_operator_fingerprints_match_current_byte_stream=True,
        source_guard_rejects_R_X_B_phase_tap_shunt_status_mutation=True,
        derived_operator_guard_rejects_matrices_lift_currents_mapping_and_key_mutation=True,
        only_new_load_generator_or_converter_port_is_promoted=True,
        fixed_shunt_does_not_require_retained_unknown=True,
        unanchored_shunted_and_anchored_singular_interiors_rejected=True,
        MATPOWER_converted_generator_setup_and_Q_control_results_match=True,
        paired_results=raw['paired_control_cases'],
        limitations=['The retained 148 buses are the requested interface, not a proof of global minimum network order.',
            'Exact reduction preserves existing operating-limit violations, synthetic parameters and unresolved cable classifications.',
            'Any status, temperature-resistance, fixed shunt, phase/tap or specified device/control change requires a fresh valid reduction.',
            'This is a PF-only model and recovery contract; OPF support and security qualification are not established.'],
        resolved_findings=['Added connectivity guard for invertible but unanchored shunted interiors.',
            'Added immutable operator fingerprint beyond the detailed-input fingerprint.',
            'Empty numerical arrays retain shape hashes and no longer trigger Java overload errors.'],
        dependencies=before+[record(Path(__file__)),record(raw_path),record(OUT/'kron_feasibility_review.json')]
            +[record(p) for p in sorted((OUT.parent/'models').glob('compact_ac_h*.mat'))])
    if skip_mode2:
        historical_path=OUT/'kernel_guard_results_before_performance.json'
        historical=json.loads(historical_path.read_text())
        mode2=next(x for x in historical['paired_control_cases'] if x['qlim']==2)
        assert mode2['compact_success'] and mode2['full_success']
        diff_path=OUT/'performance_source_diff_review.json';diff=json.loads(diff_path.read_text())
        assert diff['passed'] and diff['historical_sources_reconstructed_and_matched_prior_review_hashes']
        review['historical_mode2_comparison']=dict(evidence_stage='before_performance_only_change;not_rerun',**mode2)
        review['performance_only_change_preserves_solver_math_and_fingerprint_byte_stream']=True
        review['dependencies'].extend([record(historical_path),record(diff_path)])
    (OUT/'compact_core_review.json').write_text(json.dumps(review,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':True,'tests':raw['tests'],'current_paired_modes':[0,1] if skip_mode2 else [0,1,2],
        'historical_mode2_retained':skip_mode2,'saved_operator_fingerprints_matched':len(raw['exported_fingerprints'])},indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--skip-mode2',action='store_true');main(parser.parse_args().skip_mode2)
