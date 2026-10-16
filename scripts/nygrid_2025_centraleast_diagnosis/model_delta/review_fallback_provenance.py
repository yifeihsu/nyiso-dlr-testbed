"""Document actual, unchanged fallback behavior for the tested corridors."""
from pathlib import Path
from datetime import datetime,timezone
import json
import numpy as np
import pandas as pd
from review_bridge_outputs import ROOT,BASE,record


def main():
    source=ROOT/'output/nygrid_2025_ac_system/branches'
    inputs=[source/'branch_assignments.csv',source/'explicit_R_X_replacements.csv',source/'thermal_segments.csv']
    a=pd.read_csv(inputs[0]).set_index('branch_row');r=pd.read_csv(inputs[1]).set_index('branch_row');s=pd.read_csv(inputs[2]).set_index('branch_row')
    rows=[]
    for p in [224,41]:
        aa,rr,ss=a.loc[p],r.loc[p],s.loc[p]
        assert not isinstance(ss,pd.DataFrame)
        inferred=float(aa.original_x_pu/aa.applied_x_pu*aa.route_length_m)
        assert abs(inferred-rr.raw_X_implied_length_m)<1e-8
        assert inferred<aa.length_min_m
        expected=float(np.clip(aa.preferred_length_m,aa.length_min_m,aa.length_max_m))
        assert abs(expected-aa.route_length_m)<1e-8
        assert abs(aa.preferred_length_m-1.25*aa.geographic_chord_m)<1e-8
        assert not bool(aa.installed_conductor_or_route_identified) and not bool(aa.asbuilt_identity_qualified)
        rows.append(dict(branch_row=p,branch_key=aa.branch_key,from_name=aa.from_name,to_name=aa.to_name,
            source_R_pu=aa.original_r_pu,source_X_pu=aa.original_x_pu,AC_R_pu=aa.applied_r_pu,AC_X_pu=aa.applied_x_pu,
            source_X_implied_length_m=inferred,geographic_chord_m=aa.geographic_chord_m,
            declared_length_min_m=aa.length_min_m,declared_length_max_m=aa.length_max_m,
            preferred_1p25_chord_m=aa.preferred_length_m,chosen_length_m=aa.route_length_m,
            nearest_lower_boundary_not_selected_m=aa.length_min_m,
            X_if_nearest_lower_boundary_had_been_selected_pu=aa.applied_x_pu*aa.length_min_m/aa.route_length_m,
            chosen_X_over_original_X=aa.applied_x_pu/aa.original_x_pu,
            exact_inverse_candidates=int(aa.exact_inverse_candidates),catalog_id=ss.catalog_id,circuits=ss.circuits,bundle_count=ss.bundle_count,
            phase_GMD_m=ss.gmd_m,bundle_spacing_m=ss.bundle_spacing_m,conductor_reference_temperature_C=ss.reference_temperature_c,
            actual_algorithm='If exact inverse fails and original-X-implied length is outside interval, choose preferred1.25chord, then clip to interval.',
            installed_asset_or_route_identified=False,as_built_impedance_qualified=False))
    rows=[{k:(v.item() if isinstance(v,np.generic) else v) for k,v in r.items()} for r in rows]
    output=BASE/'model_delta/fallback_design_provenance.csv';pd.DataFrame(rows).to_csv(output,index=False)
    paths=inputs+[Path(__file__),Path(__file__).with_name('review_bridge_outputs.py'),
                  ROOT/'scripts/nygrid_2025_ac_system/branches/line_equivalents.py',
                  ROOT/'scripts/nygrid_2025_ac_system/branches/build_assignments.py']
    report=dict(passed=True,created_utc=datetime.now(timezone.utc).isoformat(),scope='Read-only algorithm/source provenance for rows224 and41',
        actual_preferred_length_behavior_independently_reconstructed=True,
        fallback_docstring_nearest_boundary_description_matches_actual_behavior=False,
        baseline_code_or_parameter_change_made=False,any_actual_route_or_impedance_claim=False,
        lower_public_WAPE_not_evidence_of_physical_parameter_truth=True,rows=rows,
        dependencies=[record(p) for p in paths],outputs=[record(output)])
    (BASE/'model_delta/fallback_provenance_review.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ['dependencies','outputs']},indent=2))


if __name__=='__main__':main()
