"""Deterministic, source-only F84/Dover parameter evidence register.

This is a transcription/provenance compiler, not an impedance estimator or fitter.
Use --verify to check archived bytes, text anchors, and existing register outputs.
"""
import argparse
import csv
import hashlib
import io
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'output/nygrid_2025_line_parameters'
SOURCES = OUT / 'sources/projects'

# Values are per circuit unless a segment is explicitly identified.
RECORDS = []
def add(asset, field, value, unit, filename, page, printed, kind, note, anchor=''):
    RECORDS.append(dict(asset_key=asset, field=field, value=value, unit=unit,
        filename=filename, pdf_page_1based=page, printed_page=printed,
        evidence_class=kind, qualification=note, text_anchor=anchor))

F84 = 'CV:PV_CV_F84'
Y17 = 'DOVER:CV_DOVER_Y17'
LM = 'DOVER:DOVER_LM_398'
EM = 'CV_EMCP_Rev2_VolI_2017.pdf'
STAR = 'NYISO_2022Q2_STAR.pdf'
SA = 'NYTransco_SA2510_2023.pdf'
CT = 'CT_398_Petition1216_Filing_2016.pdf'
APP = 'CV_EMCP_AppS_EngineeringDrawings_20170825.pdf'

add(F84,'length',14.6,'mi',EM,8,'5','primary_project_design','Whole Pleasant Valley-Cricket Valley new line; approximate route length.','14.6 miles')
add(F84,'nominal_voltage',345,'kV',EM,8,'5','primary_project_design','Same voltage as the modeled circuit.','345 kV')
add(F84,'conductor','Mallard 795 ACSS','',EM,12,'9','primary_project_design','Applies to new F84 and separately to NY reconductoring; not the short plant loop ACSR conductor.','bundled')
add(F84,'subconductors_per_phase',2,'count','CV_EMF_SmithRd_2014.pdf',1,'EMF input table','primary_project_study_input','F84 twin bundle explicitly specified in project EMF inputs and independently depicted by AppS p12.','1.14')
add(F84,'bundle_spacing',18,'in',APP,12,'Standard idler insulator assembly','primary_project_drawing','Clamp spacing shown in project drawing; that hardware sheet is labeled conceptual. Independently corroborated by the 2014 project EMF input table.','18')
add(F84,'conductor_diameter',1.14,'in','CV_EMF_SmithRd_2014.pdf',1,'EMF input table','primary_project_study_input','Mallard row inputs; local Smith Road coordinates are NOT a route-average geometry.','1.14')
for field,value,temp in [('summer_normal_current',2214,95),('winter_normal_current',2695,95),('summer_15min_emergency_current',3717,180),('winter_15min_emergency_current',3979,180)]:
    add(F84,field,value,'A',EM,12,'9','primary_project_design',f'Conductor rating at {temp} C; circuit ampacity, not per subconductor; not a verified current terminal-limited facility rating.',str(value))
add(F84,'summer_normal_apparent_power',1323,'MVA',EM,12,'9','primary_project_design','Published value; matches sqrt(3)*345kV*2214A to rounding.','1323')
add(F84,'normal_rating_conductor_temperature',95,'degC',EM,12,'9','primary_project_design','Temperature associated with both seasonal normal ampacities.','95')
add(F84,'15min_emergency_conductor_temperature',180,'degC',EM,12,'9','primary_project_design','Maximum operating temperature and 15-minute emergency rating temperature.','180')
add(F84,'energized_date','2019-07-28','date','CV_InServiceNotice_20190729.pdf',1,'1','primary_owner_in_service_notice','New relative to frozen model does not imply built after calendar 2019. This notice establishes energization, not an as-built R/X/B measurement.','July 28, 2019')
add(F84,'right_phase_center_offset',15.5,'ft',APP,2,'2013-195-T sheet 21 rev 2','primary_project_drawing','Dimension reads 15 feet 6 inches from pole to right-side bundle center.','')
add(F84,'top_to_bottom_right_phase_arm_separation',31,'ft',APP,2,'2013-195-T sheet 21 rev 2','primary_project_drawing','Relative conductor heights require equal V-string drop assumption.','')
add(F84,'shield_to_top_phase_arm_separation',7,'ft',APP,2,'2013-195-T sheet 21 rev 2','primary_project_drawing','Source geometry dimension; not height above ground.','')
add(F84,'shield_to_middle_phase_arm_separation',24,'ft',APP,2,'2013-195-T sheet 21 rev 2','primary_project_drawing','Source geometry dimension; not height above ground.','')
coords = [[15.5,0.0],[15.5,31.0],[-15.5,14.0]]
gmd = math.prod(math.dist(coords[i],coords[j]) for i,j in [(0,1),(1,2),(2,0)])**(1/3)
add(F84,'representative_phase_centers',json.dumps(coords),'ft',APP,2,'2013-195-T sheet 21 rev 2','geometry_inference','A lower right; B upper right; C middle left. Assumes mirrored 15.5-ft left offset and equal V-string drops. Typical structure only; do not label as-built route average.','')
add(F84,'representative_GMD',gmd*0.3048,'m',APP,2,'2013-195-T sheet 21 rev 2','geometry_inference','Cube root of three pairwise distances from explicitly qualified representative phase centers; route variation and mutual coupling remain uncertain.','')

for asset,length,scope in [(Y17,0.30,'Entire Cricket Valley-Dover short line, planned length.'),(LM,3.13,'NEW YORK PORTION ONLY: Dover-CT state line. Does not reach Long Mountain.')]:
    add(asset,'length_NY',length,'mi',STAR,30,'30','primary_operator_planning',scope+' 2022 planning table is not final survey.',str(length))
    add(asset,'conductor_NY','twin 795 kcmil ACSS Mallard','',SA,45,'8','primary_project_design','Dover terminal conductor family; agrees with NYISO 2-795 ACSS planning entries and prior NY398 reconductor.','Twin-bundled 795 kcmil ACSS Mallard')
    add(asset,'summer_thermal_rating_table',2220,'A',STAR,30,'30','primary_operator_planning','Table footnote4 explicitly defines ratings in amperes except where labeled otherwise. Planning value; not a current as-built operational limit.','2220')
    add(asset,'winter_thermal_rating_table',2700,'A',STAR,30,'30','primary_operator_planning','Table footnote4 explicitly defines ratings in amperes except where labeled otherwise. Planning value; not a current as-built operational limit.','2700')

add(LM,'length_CT',5.3,'mi',CT,5,'3','primary_project_design','NY/CT border to Long Mountain; stronger later CT filing than 2013 NY exhibit estimate 5.6 miles.','5.3 miles')
add(LM,'conductor_CT','2156 kcmil ACSS','',CT,5,'3','primary_project_design','Replacement for existing 2156 ACSR; NY EMCP identifies Bluebird transition near border.','2156 Aluminum Conductor Steel Supported')
add(LM,'subconductors_per_phase_CT',1,'count','CT_398_Interrogatories_20160316.pdf',3,'Q-CSC-002','primary_owner_interrogatory_response','Explicit single conductor per phase, 2156 kcmil.','single conductor per phase')
add(LM,'conductor_code_CT','Bluebird','',EM,12,'9','primary_adjacent_project_design','NY project explicitly describes transition from Mallard to Eversource-proposed single Bluebird at Tower L-76 immediately west of border. CT filing independently establishes 2156 ACSS, but does not state trade name.','single Bluebird')
add(LM,'construction_complete_by_CT','2019-06-18','date','CT_398_Completion_20190618.pdf',2,'Attachment p1','primary_owner_construction_status','Scanned document visually checked: Ruling1216 construction complete; restoration still scheduled. No exact energization date stated.','')
add(LM,'construction_and_restoration_complete_CT','2019-10-25','date','CT_398_Completion_20191120.pdf',1,'1','primary_owner_completion_notice','Owner states no material changes or other deviations. Distinct from electrical in-service date.','October 25, 2019')
add(LM,'combined_route_length',8.43,'mi',STAR,30,'30','cross_source_inference','3.13-mi NY planning segment + 5.3-mi CT project segment. Approximate heterogeneous line; no full-route as-built survey.','')
add(LM,'geometry_CT','horizontal phases; exact spacing unresolved','',CT,22,'Attachment B Sketch 1','primary_project_drawing','Depicts one replacement structure8039; not route-wide coordinates. Retain phase-spacing sensitivity, not a falsely exact measured GMD.','')
add('DOVER:PAR','installed_banks',2,'count',SA,44,'7','primary_project_design','Two active banks and one equivalent spare are specified; line-only impedance estimate must not silently absorb missing PAR impedance.','750 MVA')
add('DOVER:PAR','per_bank_nameplate_ratings','450/600/750','MVA',SA,44,'7','primary_project_design','Published cooling/nameplate sequence as written; no bank series R/X found in this public source.','450/600/750')
add('DOVER:PAR','phase_shift_range',40,'degree_plus_minus',SA,44,'7','primary_project_design','Maximum advance capability at750MVA separately stated32degrees; actual2025tapstateunknown.','40')
add('DOVER:PAR','series_impedance','unresolved','','NYTransco_SA2510_2023.pdf',44,'7','not_established','No public per-bank R/X established in reviewed SA2510. Do not infer zero impedance from a zero phase shift.','')


def serialize_csv(rows):
    buffer=io.StringIO(newline='')
    writer=csv.DictWriter(buffer, fieldnames=list(rows[0]), lineterminator='\n')
    writer.writeheader(); writer.writerows(rows)
    return buffer.getvalue().encode('utf-8')

def build():
    rows=[]
    for original in RECORDS:
        row=original.copy()
        asset=row['asset_key'];field=row['field']
        row['scope_key'] = ('F84' if asset==F84 else 'DOVER_NY_Y17' if asset==Y17 else 'DOVER_PAR' if asset=='DOVER:PAR' else 'CT_398' if field.endswith('_CT') else 'DOVER_NY_398' if field.endswith('_NY') or field.endswith('_table') else 'DOVER_COMBINED_398')
        path=SOURCES/row.pop('filename')
        receipt=json.loads(path.with_suffix(path.suffix+'.receipt.json').read_text(encoding='utf-8'))
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest==receipt['sha256'],path
        assert path.read_bytes().startswith(b'%PDF'),path
        anchor=row.pop('text_anchor')
        if anchor:
            assert anchor in path.with_suffix('.txt').read_text(encoding='utf-8'),(path,anchor)
        row.update(source_url=receipt['source_url'],local_path=str(path.relative_to(ROOT)).replace('\\','/'),sha256=digest)
        rows.append(row)
    return rows

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--verify',action='store_true');args=parser.parse_args()
    rows=build();content=serialize_csv(rows);path=OUT/'project_source_register.csv'
    if args.verify:
        assert path.read_bytes()==content,'Register differs from deterministic reproduction'
    else:
        path.write_bytes(content)
    print(json.dumps(dict(status='verified' if args.verify else 'written',rows=len(rows),sha256=hashlib.sha256(content).hexdigest(),representative_f84_gmd_m=gmd*0.3048),indent=2))

if __name__=='__main__':main()
