"""Materialize current numerical kernels in the latest-only runtime namespace.

This authoring utility is not a packaged model entrypoint. Original source
files are read only. Formula-preserving renames and the three data/path
adaptations are recorded individually for independent review.
"""
from pathlib import Path
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = Path(__file__).parent / 'runtime'
KERNELS = RUNTIME / 'kernels'
OUT = ROOT / 'output/nygrid_2025_latest_handoff/build'

SOURCES = {
    'ac_loss_apply_budget': 'scripts/nygrid_2025_ac_loss_revision/core',
    'ac_loss_budget': 'scripts/nygrid_2025_ac_loss_revision/core',
    'ac_loss_coupled_context': 'scripts/nygrid_2025_ac_loss_revision/core',
    'ac_loss_coupled_equations': 'scripts/nygrid_2025_ac_loss_revision/core',
    'ac_loss_coupled_solve': 'scripts/nygrid_2025_ac_loss_revision/core',
    'ac_loss_finalize': 'scripts/nygrid_2025_ac_loss_revision/core',
    'compact_ac_build': 'scripts/nygrid_2025_compact_ac/core',
    'compact_ac_operator_fingerprint': 'scripts/nygrid_2025_compact_ac/core',
    'compact_ac_source_fingerprint': 'scripts/nygrid_2025_compact_ac/core',
    'audit_ac_solution': 'scripts/nygrid_2025_ac_system/ac_validation',
    'ac_terminal_current_audit': 'scripts/nygrid_2025_ac_system/thermal',
    'ac_conductor_resistance': 'scripts/nygrid_2025_ac_system/thermal',
    'ac_conductor_heat': 'scripts/nygrid_2025_ac_system/thermal',
    'ac_dlr_apply_resistance': 'scripts/nygrid_2025_ac_system/thermal',
    'ac_dlr_current_audit': 'scripts/nygrid_2025_ac_system/thermal',
    'ac_dlr_limits': 'scripts/nygrid_2025_ac_system/thermal',
    'dlr_heat_balance': 'System Matpower Format/NY_Lite',
    'nygrid_rx_thermal_candidates': 'scripts/nygrid_2025_conductor_inference',
    'screen_nygrid_2025_rx_thermal': 'scripts/nygrid_2025_conductor_inference',
}
NAMES = {name: 'nylatest_' + name.removeprefix('ac_loss_').removeprefix('ac_')
         for name in SOURCES}
NAMES.update({
    'ac_loss_prepare_policy': 'nylatest_prepare_policy',
    'compact_ac_build': 'nylatest_compact_build',
    'compact_ac_operator_fingerprint': 'nylatest_operator_fingerprint',
    'compact_ac_source_fingerprint': 'nylatest_source_fingerprint',
    'audit_ac_solution': 'nylatest_audit_ac_solution',
    'nygrid_rx_thermal_candidates': 'nylatest_thermal_candidates',
    'screen_nygrid_2025_rx_thermal': 'screen_nygrid_latest_dlr',
    'run_nygrid_2025_loss_consistent_acpf': 'run_nygrid_latest_acpf',
})


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    KERNELS.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    records = []
    pattern = re.compile(r'\b(' + '|'.join(map(re.escape, sorted(NAMES, key=len, reverse=True))) + r')\b')
    for name, folder in SOURCES.items():
        source = ROOT / folder / (name + '.m')
        original = source.read_text(encoding='utf-8-sig')
        code = original
        adaptations = []
        if name == 'ac_loss_coupled_solve':
            start = code.index("root=fileparts(")
            end = code.index('started=tic;', start)
            code = code[:start] + code[end:]
            adaptations.append('Remove historical addpath setup; latest setup owns the complete kernel path.')
        elif name == 'compact_ac_build':
            start = code.index('root=fileparts(')
            end = code.index('ids=double(m.bus(:,1))', start)
            code = (code[:start] + "if nargin<2||isempty(anchor_ids)\n"
                    "    anchor_ids=double(m.userdata.latest_runtime.retained_bus_ids(:));assert(numel(anchor_ids)==148);\n"
                    "end\n" + code[end:])
            adaptations.append('Replace historical retained-bus CSV read with the frozen current retained IDs carried by the loaded case.')
        elif name == 'nygrid_rx_thermal_candidates':
            start = code.index('root=fileparts(')
            end = code.index('assert(isequal(sort(double(conflicts.branch_row))', start)
            code = (code[:start] + "data=nylatest_data();\n"
                    "reg=data.thermal.branch_registry;conductors=data.thermal.conductors;\n"
                    "geometry=data.thermal.geometry;conflicts=data.thermal.cable_conflicts;\n" + code[end:])
            adaptations.append('Replace four historical CSV reads with identical current tables in the consolidated bundle.')
        code = pattern.sub(lambda match: NAMES[match.group()], code)
        if name == 'screen_nygrid_2025_rx_thermal':
            code = code.replace('%SCREEN_NYGRID_2025_RX_THERMAL', '%SCREEN_NYGRID_LATEST_DLR')
        target = (RUNTIME if name == 'screen_nygrid_2025_rx_thermal' else KERNELS) / (NAMES[name] + '.m')
        target.write_text(code, encoding='utf-8', newline='\n')
        records.append(dict(source=source.relative_to(ROOT).as_posix(), source_sha256=sha(source),
            target=target.relative_to(ROOT).as_posix(), target_sha256=sha(target),
            function_renames=NAMES, data_and_path_adaptations=adaptations,
            numerical_equations_modified=False))
    receipt = dict(passed=True, scope='Current default coupled-PF/compact/audit/RX-thermal kernels only',
        original_files_modified=False, historical_model_loaders_copied=False,
        legacy_loss_solvers_or_OPF_entrypoints_copied=False, records=records)
    (OUT / 'kernel_copy_receipt.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(copied_files=len(records), numerical_equations_modified=False)))


if __name__ == '__main__':
    main()
