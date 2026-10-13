"""Source-gated treatment of Cornell's added Gilboa--Buchanan equivalent.

This is an evidence/recommendation builder. It writes no production model,
reads no interface-observation or model-scoring table, and does not run PF.
"""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,re,subprocess
import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'output/nygrid_2025_ac_loss_revision/impedance'
SOURCES=OUT/'sources'
PIN='47698b6c7823ae7b1bc6935e5601d5b64b8f918e'


def record(p):
    with p.open('rb') as f:h=hashlib.file_digest(f,'sha256').hexdigest()
    return dict(path=p.relative_to(ROOT).as_posix(),sha256=h)


def pair_rows(branch,a=38,b=77):
    return np.flatnonzero(((branch[:,0]==a)&(branch[:,1]==b))|((branch[:,0]==b)&(branch[:,1]==a)))


def chain_Y(branch):
    ids=list(dict.fromkeys(map(int,branch[:,:2].flatten())));index={b:i for i,b in enumerate(ids)}
    Y=np.zeros((len(ids),len(ids)),complex)
    for r in branch:
        a,b=index[int(r[0])],index[int(r[1])];z=r[2]+1j*r[3];assert abs(z)>0
        assert r[4]==0 and r[8] in [0,1] and r[9]==0 and r[10]==1
        y=1/z;Y[a,a]+=y;Y[b,b]+=y;Y[a,b]-=y;Y[b,a]-=y
    return Y,ids


def main():
    OUT.mkdir(parents=True,exist_ok=True);paths=[Path(__file__)];lineage=[]
    def mat(p,**kw):paths.append(p);return loadmat(p,simplify_cells=True,**kw)
    manifest_path=ROOT/'output/nygrid_2019/upstream_manifest.json';paths.append(manifest_path)
    manifest=json.loads(manifest_path.read_text());assert manifest['commit']==PIN
    for original,archived in [('modifyMPC.m','Cornell_NYgrid_modifyMPC.m'),('Data/npcc.mat','Cornell_NYgrid_original_npcc.mat'),('Data/npcc.csv','Cornell_NYgrid_original_npcc.csv')]:
        entry=next(e for e in manifest['files'] if e['path']==original);p=SOURCES/archived;paths.append(p)
        assert record(p)['sha256']==entry['sha256']
    text=(SOURCES/'Cornell_NYgrid_modifyMPC.m').read_text(encoding='utf-8')
    literal=np.fromstring(re.search(r'\bnewlineEG\s*=\s*\[([^\]]+)\]',text).group(1),sep=' ')
    sibling=np.fromstring(re.search(r'\bnewlineEG2\s*=\s*\[([^\]]+)\]',text).group(1),sep=' ')
    assert np.array_equal(literal[:5],[38,77,.02,.0147,0]) and np.array_equal(sibling[:5],[43,38,.02,.0427,0])
    raw=loadmat(SOURCES/'Cornell_NYgrid_original_npcc.mat',simplify_cells=True)['mpc']
    assert raw['bus'].shape[0]==140 and raw['branch'].shape[0]==227
    assert not len(pair_rows(raw['branch'])) and not len(pair_rows(raw['branch'],43,38))
    lineage.append(dict(stage='pinned_Cornell_original_NPCC',buses=140,branches=227,branch_38_77_present=False,branch_row=None,
                        source='Cornell_NYgrid_original_npcc.mat',interpretation='No such original NPCC branch'))
    historical_path=ROOT/'output/nygrid_2019_full_stage1/full_year.mat'
    historical=mat(historical_path,variable_names=['full_pre_hvdc_case','base_case','reduced_final_case'])
    for name in ['full_pre_hvdc_case','base_case','reduced_final_case']:
        m=historical[name];hits=pair_rows(m['branch']);assert len(hits)==1
        row=int(hits[0]);assert np.array_equal(m['branch'][row,:13],literal)
        lineage.append(dict(stage=name,buses=len(m['bus']),branches=len(m['branch']),branch_38_77_present=True,
                            branch_row=row+1,R_pu=float(m['branch'][row,2]),X_pu=float(m['branch'][row,3]),B_pu=float(m['branch'][row,4]),
                            source=historical_path.relative_to(ROOT).as_posix(),interpretation='Released added E-G aggregate, no circuit identifier'))
    full_path=ROOT/'output/nygrid_2025_line_parameters/overlays/engineering_nominal/full191_network_cases.mat'
    full=mat(full_path)
    for name in ['refined_2025_pre_may_case','refined_2025_may21_case','refined_2025_may30_case','refined_2025_case']:
        m=full[name];hits=pair_rows(m['branch']);assert np.array_equal(hits,[223]) and np.array_equal(m['branch'][223,:5],literal[:5])
        lineage.append(dict(stage=name,buses=len(m['bus']),branches=len(m['branch']),branch_38_77_present=True,branch_row=224,
                            R_pu=.02,X_pu=.0147,B_pu=0.,source=full_path.relative_to(ROOT).as_posix(),interpretation='Original released aggregate inherited without changing R/X/B'))
    post_path=ROOT/'output/nygrid_2025_dover_parameters/network/x_nominal.mat';post=mat(post_path)
    assert np.array_equal(post['full_case']['branch'][223,:5],literal[:5])
    legacy_path=OUT/'legacy_family_check.json';paths.append(legacy_path);legacy=json.loads(legacy_path.read_text())
    assert legacy['passed'] and legacy['all_38_77_pairs_absent']
    for r in legacy['cases']:
        paths.append(Path(r['case_file']))
        lineage.append(dict(stage=r['case_name'],buses=r['buses'],branches=r['branches'],branch_38_77_present=False,
                            branch_row=None,source=Path(r['case_file']).relative_to(ROOT).as_posix(),interpretation='Separate ENLITEN/S7 source family; current Cornell row224 does not originate here'))
    pd.DataFrame(lineage).to_csv(OUT/'branch224_lineage.csv',index=False)

    # Independent neighboring topology from the historical detailed source.
    src=full['source_case'];bus=src['bus'];br=src['branch'];names=np.asarray(src['bus_name']).astype(str)
    matches=np.flatnonzero(np.char.upper(names)=='GILBOA');assert len(matches)==1
    gilboa=int(bus[matches[0],0]);assert gilboa==1227
    bi={int(x):i for i,x in enumerate(bus[:,0])};active=np.flatnonzero(np.any(br[:,:2]==gilboa,axis=1)&(br[:,10]>0))
    assert np.array_equal(active+1,[1608,1635,2136])
    raw_inventory_path=ROOT/'output/nygrid_2025_acpf_profile_audit/structure/sources/perform_ny_branch_inventory.csv';paths.append(raw_inventory_path)
    inventory=pd.read_csv(raw_inventory_path).set_index('source_branch_row');adj=[]
    for j in active:
        r=br[j];f,t=map(int,r[:2]);inv=inventory.loc[j+1]
        assert np.max(abs(np.asarray([inv.source_r_pu,inv.source_x_pu,inv.source_b_pu])-r[2:5]))<1e-12
        adj.append(dict(snapshot_year=2019,source_branch_row=j+1,from_bus=f,to_bus=t,from_name=names[bi[f]],to_name=names[bi[t]],
                        nominal_kV=float(bus[bi[f],9]),R_pu=r[2],X_pu=r[3],B_pu=r[4],rateA_MVA=r[5],
                        source_device_key=inv.device_key,raw_circuit_id=str(inv.raw_circuit_id),
                        proves_direct_Gilboa_Buchanan_asset=False))
    pd.DataFrame(adj).to_csv(OUT/'historical_PERFORM_Gilboa_incident_circuits.csv',index=False)
    assert not any('BUCHANAN' in (r['from_name']+' '+r['to_name']).upper() for r in adj)
    zbase=345**2/100.;literalX=47*.371/zbase
    prior_path=ROOT/'output/nygrid_2025_ac_system/branches/branch_assignments.csv';paths.append(prior_path)
    assignment=pd.read_csv(prior_path).set_index('branch_row').loc[224]
    assert not assignment.asbuilt_identity_qualified and not assignment.installed_conductor_or_route_identified
    current=np.array([assignment.applied_r_pu,assignment.applied_x_pu,assignment.applied_b_pu])
    ledger=[
      dict(variant='released_equivalent_nominal',disposition='accepted_for_explicit_equivalent_study_only',R_pu=.02,X_pu=.0147,B_pu=0.,
           evidence='Exact pinned author-release tuple; X approximately follows paperEq10. R and B have no physical derivation.',
           physical_asset_qualified=False,thermal_conductor_qualified=False),
      dict(variant='paper_literal_X',disposition='arithmetic_sensitivity_only',R_pu=.02,X_pu=literalX,B_pu=0.,
           evidence='47miles times0.371ohm/mile divided by1190.25ohm, holding released R/B. Not a physical uncertainty interval.',
           physical_asset_qualified=False,thermal_conductor_qualified=False),
      dict(variant='lossless_equivalent',disposition='unresolved_R_sensitivity_only',R_pu=0.,X_pu=.0147,B_pu=0.,
           evidence='Zero-loss boundary case for unsupported aggregate R, preserving documented DC reactance. Not an installed-line estimate.',
           physical_asset_qualified=False,thermal_conductor_qualified=False),
      dict(variant='former_177p539km_single_OH',disposition='rejected_as_literal_asset_mapping_preserved_as_historical_model',R_pu=current[0],X_pu=current[1],B_pu=current[2],
           evidence='Geographic/default-conductor fallback applied to nonliteral network endpoints; no identified conductor or route.',
           physical_asset_qualified=False,thermal_conductor_qualified=False),
      dict(variant='former_X_only_hybrid',disposition='rejected_as_production_repair_diagnostic_only',R_pu=current[0],X_pu=.0147,B_pu=current[2],
           evidence='Mixes unrelated conductor-derived R/B with released aggregate X; no coherent source tuple or identified hardware.',
           physical_asset_qualified=False,thermal_conductor_qualified=False)]
    for r in ledger:r.update(baseMVA=100.,nominal_kV=345.,branch_row=224,from_bus=38,to_bus=77)
    pd.DataFrame(ledger).to_csv(OUT/'parameter_ledger.csv',index=False)
    # Candidate is checked as an exact passive series equivalent on unchanged
    # existing numerical sections, not as physical route segmentation.
    checks=[];proposed=[]
    for hour in [1,3360,3576,8472,8508]:
        p=ROOT/f'output/nygrid_2025_compact_ac/models/compact_ac_h{hour:04d}.mat';c=mat(p)['model'];m=c['detailed_mpc']
        parent=np.asarray(c['branch_parent_row'],int);use=np.flatnonzero(parent==224);old=np.asarray(m['branch']);new=old.copy()
        assert len(use)==2
        frac=old[use,3]/old[use,3].sum();new[use,2:5]=frac[:,None]*np.array([.02,.0147,0.])
        other=np.flatnonzero(parent!=224);assert np.array_equal(new[other],old[other])
        assert np.array_equal(new[:,[0,1,5,6,7,8,9,10,11,12]],old[:,[0,1,5,6,7,8,9,10,11,12]])
        assert np.max(abs(new[use,2:5].sum(axis=0)-[.02,.0147,0]))<1e-14
        Y,ids=chain_Y(new[use]);keep=[ids.index(38),ids.index(77)];elim=[i for i in range(len(ids)) if i not in keep]
        Ye=Y[np.ix_(keep,keep)]-Y[np.ix_(keep,elim)]@np.linalg.solve(Y[np.ix_(elim,elim)],Y[np.ix_(elim,keep)])
        target=np.array([[1,-1],[-1,1]])/(.02+1j*.0147);error=float(np.max(abs(Ye-target)));assert error<1e-12
        assert np.linalg.eigvalsh((Ye+Ye.conj().T)/2).min()>-1e-12
        for j in use:
            proposed.append(dict(hour_index=hour,runtime_branch_row=j+1,original_parent=224,from_bus=int(old[j,0]),to_bus=int(old[j,1]),
                old_R_pu=old[j,2],old_X_pu=old[j,3],old_B_pu=old[j,4],proposed_R_pu=new[j,2],proposed_X_pu=new[j,3],proposed_B_pu=new[j,4],
                R_X_B_only_change=True,all_other_branch_columns_unchanged=True))
        checks.append(dict(hour_index=hour,full_buses=len(m['bus']),full_branches=len(old),retained_buses=len(c['retained_bus_ids']),
            numerical_sections=len(use),topology_and_every_other_branch_unchanged=True,proposed_equivalent_passive=True,
            maximum_complex_Y_Schur_vs_single_released_equivalent_error_pu=error,
            actual_revised_model_built_by_this_script=False))
    pd.DataFrame(proposed).to_csv(OUT/'proposed_runtime_parameter_changes.csv',index=False)
    paper=SOURCES/'NYgrid_published_paper.pdf';paths.append(paper)
    visual=[]
    for name,pages,reason in [('NYgrid_paper_p7.png',[7],'Visually confirms added two-segment representation, Eq10,137/47mile assumptions and0.371reactance coefficient.'),
                              ('NYgrid_paper_p11.png',[11],'Visually confirms reference43 NYPA CommunicationbackboneOPGW expansion Sep18,2018; exact underlying document not recovered.'),
                              ('NYISO_stability_p6.png',[6],'Visually confirms historical TotalEast andUPNYConEd physical circuit names differ from the aggregate endpoint pair.'),
                              ('NYISO_stability_p8.png',[8],'Visually confirms Fraser-Gilboa, Gilboa-LeedsGL3 andGilboa-NewScotland contingency names.')]:
        p=SOURCES/name;assert p.is_file();paths.append(p);visual.append(dict(file=p.relative_to(ROOT).as_posix(),PDF_pages_one_based=pages,visually_checked=True,finding=reason))
    source_pdf=SOURCES/'NYISO_interface_stability_2004.pdf';paths.append(source_pdf)
    web_evidence=dict(retrieved_utc=datetime.now(timezone.utc).isoformat(),
        utility_property_inventory=dict(url='https://www.nypa.gov/-/media/nypa/documents/document-library/real-estate/2025/overview-of-all-nypa-holdings_12312024.pdf',
            source_asof='2024-12-31',retrieval_scope='Primary-source search-index text only; direct historical PDF endpoints returned404 and are not locally PDF-verified',
            entries=[dict(line='Gilboa-New Scotland',nominal_kV=345,ROW_miles=31),dict(line='Gilboa-Leeds',nominal_kV=345,ROW_miles=36),dict(line='Gilboa-Fraser',nominal_kV=345,ROW_miles=32)],
            limitation='ROW distances are not conductor impedance data or proof of a direct Gilboa-Buchanan circuit.'),
        live_author_source_url=f'https://raw.githubusercontent.com/AndersonEnergyLab-Cornell/NYgrid/{PIN}/modifyMPC.m',
        author_paper_url='https://sustainable-power-energy-research.media.uconn.edu/wp-content/uploads/sites/3441/2023/11/An-Open-Source-Representation-for-the-NYS-Electric-Grid-to-Support-Power-Grid-and-Market-Transition-Studies.pdf',
        NYISO_historical_download_url='https://www.nyiso.com/documents/20142/2964907/interface_stability_limit_analysis.pdf/2ed355de-8767-8cde-c397-eec7450439b8',
        exact_paper_reference43_public_document_recovered=False,direct_installed_pair_or_factory_R_X_B_source_found=False)
    (SOURCES/'primary_web_evidence.json').write_text(json.dumps(web_evidence,indent=2)+'\n')
    paths.extend([SOURCES/'primary_web_evidence.json',SOURCES/'source_download_receipt.json',SOURCES/'additional_download_attempts.json',
                  ROOT/'scripts/nygrid_2019_full/build_branch_register.py',ROOT/'scripts/nygrid_2019_full/audit_marcy_parameters.py',
                  ROOT/'scripts/nygrid_2025_ac_system/branches/line_equivalents.py',Path(__file__).with_name('audit_legacy_family.m')])
    recommendation=dict(passed=True,created_utc=datetime.now(timezone.utc).isoformat(),baseline_HEAD=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        branch_row=224,branch_key='PARENT:224',from_bus=38,to_bus=77,baseMVA=100,nominal_kV=345,
        classification='released_EG_network_equivalent_with_unresolved_physical_identity',
        source_family='Cornell_NYgrid_added_MarcySouth_representation_not_original_NPCC_or_S7_branch',
        accepted_scope='Source-reproducible passive network-equivalent baseline for a separately versioned synthetic AC study',
        accepted_variant='released_equivalent_nominal',accepted_R_X_B_pu=[.02,.0147,0.],
        physical_impedance_validated=False,installed_direct_line_identified=False,physical_route_identified=False,
        factory_or_utility_sequence_impedance_found=False,source_R_derivation_found=False,source_B_derivation_found=False,
        exact_source_code_tuple_verified=True,paper_X_approximation_reproduced=True,
        paper_literal_X_pu=literalX,released_X_minus_paper_literal_percent=100*(.0147/literalX-1),
        source_R_ohm=.02*zbase,source_X_ohm=.0147*zbase,
        rejection_of_177km_literal_OH_mapping='The model endpoints stand for an added aggregate route; no source-backed installed conductor, circuit or route supports converting their geographic chord into a literal single-line realization.',
        required_metadata_changes=['Classify parent224 and its numerical sections as a network equivalent.',
            'Exclude224 from IEEE738 conductor/R(T)/DLR claims and installed-conductor/route/equipment assertions.',
            'Retain original parent identity and interface membership; the case remains an inherited diagnostic interface model.',
            'If canonical axes are retained, use the existing two zero-injection numerical sections whose R/X sum to the accepted tuple and set their totalB tozero.',
            'Do not add/remove busGS/BS as part of this correction; no reactor was associated with224.',
            'Do not promote sourceRATEA0 or the former synthetic ampere envelope to a verified facility rating.'],
        parameter_sensitivity_scope=dict(X_arithmetic_interval_pu=[literalX,.0147],
            R_declared_sensitivity_points_pu=[0.,.02],B_nominal_pu=0.,
            interpretation='These points separate source arithmetic and unresolved aggregate-loss assumptions. They are not physical confidence bounds or measured operating limits.'),
        numerical_proposal_checks=checks,visual_source_page_checks=visual,
        limitations=['The source-backed result is the identity/classification and released model tuple, not validation of physical AC impedance.',
            'A lower NYISO WAPE does not determine physically correct R/X/B; no interface observations or score tables are read here.',
            'Historical PERFORM andNYISO documents establish context, not a complete2025 as-built topology certificate.',
            'NYPA indexed property records corroborate the named Gilboa connections, but fullPDF download/visual verification was unavailable for those specific historical URLs.',
            'The sibling43-38 aggregate is recorded as context only; this recommendation changes no other branch.',
            'Actual implementation requires an independent comparison against this proposal; this script has not changed or solved a production model.'],
        dependencies=[record(p) for p in dict.fromkeys(paths)],outputs=[record(OUT/n) for n in ['branch224_lineage.csv','historical_PERFORM_Gilboa_incident_circuits.csv','parameter_ledger.csv','proposed_runtime_parameter_changes.csv']])
    (OUT/'impedance_recommendation.json').write_text(json.dumps(recommendation,indent=2)+'\n')
    print(json.dumps({k:v for k,v in recommendation.items() if k not in ['dependencies','outputs','visual_source_page_checks','numerical_proposal_checks']},indent=2))


if __name__=='__main__':main()
