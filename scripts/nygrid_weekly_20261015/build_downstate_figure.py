"""Source-derived, editable two-panel topology excerpt; no electrical fitting."""
import csv, hashlib, json
from pathlib import Path
from collections import defaultdict

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/pdf/nygrid_weekly_2026-10-15/figures'
AUDIT=ROOT/'output/nygrid_weekly_20261015/evidence'
BASE=ROOT/'output/nygrid_2025_downstate/network/branch_register.csv'
GEO=ROOT/'output/nygrid_2025_moses_repair/delivery/map/geography_data.json'
BUS=ROOT/'output/nygrid_2025_downstate/network/bus_register.csv'
geo=json.loads(GEO.read_text()); nodes={n['id']:n for n in geo['nodes']}
with BUS.open(newline='',encoding='utf-8') as f:
    bus_register={int(r['model_bus']):r for r in csv.DictReader(f)}
base_bus={bid:r for bid,r in bus_register.items() if r['identity_role']=='original_parent'}
with BASE.open(newline='',encoding='utf-8') as f:
    base_branch=[r for r in csv.DictReader(f) if r['branch_key'].startswith('PARENT:') and int(r['parent_branch_row'])<=225]
assert set(base_bus)==set(range(1,141))
assert len(base_branch)==225 and {int(r['parent_branch_row']) for r in base_branch}==set(range(1,226))
assert all(int(r['from_bus']) in base_bus and int(r['to_bus']) in base_bus for r in base_branch)

# Display locations are schematic and hand separated for readability. The source
# lat/lon remains in CSV and is never represented as the display coordinates.
groups=[
('pv',[73],2.10,4.20),('ramapo',[76],.35,3.28),('buch',[77],1.40,3.18),('mill',[74],3.05,3.10),
('ceug',[78],1.70,2.13),('rava',[79],6.10,2.12),('northport',[80],5.45,2.75),('goethals',[81],.30,.00),('ak3',[82],3.60,1.34),
('ef',[10858],2.65,3.90),('wood',[10902],3.05,3.55),('laden',[10774],.85,3.60),
('cv',[20001],4.10,4.20),('dover',[20003,21001],5.10,4.15),('lm',[20002],6.10,3.62),('south',[35],6.10,4.20),
('un10547',[10547],2.60,2.81),('sprain',[10594,11502],3.05,2.47),('dun',[10593,11501],2.50,2.13),
('shore',[10560],4.35,2.78),('egc',[10589,11497],5.25,2.12),('gn',[10598],4.28,1.62),
('u61',[10561],4.70,1.21),('u67',[10567],5.25,1.02),('wh',[10588],5.75,.75),
('tap996',[10996],5.75,.30),('tap995',[10995],5.30,.10),('tap620',[10620],4.90,-.10),('valley',[10626],4.50,.08),
('e179',[10600],2.60,1.82),('bruc',[10595],3.00,1.65),('trem',[10596,11503],3.55,1.98),
('ast',[10557,11493],3.05,1.00),('nq',[10597],3.40,.62),('corona',[10601],3.82,.78),
('jamaica',[10628,11506],4.15,.38),('w49',[11136,11532],1.18,1.65),('e13',[10079],.70,1.04),
('leon',[11134],.62,.55),('farr',[11132],1.28,.39),('gow',[11129],1.80,.00),('rai',[11130,11529],2.18,.76),
('vernon',[20011],2.43,.39),('rccq',[20014],2.78,.72),('rccb',[20009],2.20,.00),('rccs',[20010],.75,-.13),
('green',[20007],2.75,-.13),('fox',[20008],1.20,-.28),('fk138',[20012],.72,-.48),('fk345',[20013],.15,-.48),('annex',[20005],1.70,1.04)
]
gby={g[0]:g for g in groups}; bus_to_group={bid:g[0] for g in groups for bid in g[1]}
original={i for i in bus_to_group if i<=140}
selected=set(bus_to_group)
active=[]
for edge in geo['parents']:
    state=next((s for s in edge['stateRecords'] if s['stateId']=='post_dover'),None)
    if edge['a'] in selected and edge['b'] in selected and state and state['active']:
        active.append(edge)
baseline=[]
for e in base_branch:
    a,b=int(e['from_bus']),int(e['to_bus'])
    # The current refinement marks superseded aggregate rows inactive. Ignore
    # those later statuses when reconstructing the pre-refinement parent view.
    if a in original and b in original:
        baseline.append(dict(id=int(e['parent_branch_row']),key=e['branch_key'],a=a,b=b,
            sourceRole='paper_derived_2019_structural_parent',classification=e['parameter_basis']))
assert len(baseline)==9
assert {tuple(sorted((e['a'],e['b']))) for e in baseline}=={
    (35,73),(73,74),(74,77),(74,78),(76,77),(78,79),(78,80),(78,81),(78,82)}

def rows(edges):
    out=[]
    for e in edges:
        a,b=e['a'],e['b']; ga,gb=bus_to_group[a],bus_to_group[b]
        out.append(dict(branch_key=e['key'],parent_record=e['id'],from_bus=a,to_bus=b,
            from_group=ga,to_group=gb,drawn_as_self_connection=ga==gb,
            source_role=e['sourceRole'],classification=e['classification'],
            line_style='original' if e['key'].startswith(('PARENT:','NPCC:')) else 'added'))
    return out

def writecsv(path,data):
    with path.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(data[0])); w.writeheader(); w.writerows(data)

node_rows=[]
for group,bids,x,y in groups:
    for bid in bids:
        n=nodes[bid]
        source_name=bus_register[bid]['model_name'] if bid in bus_register else n['name']
        node_rows.append(dict(bus_id=bid,name=source_name,group=group,base_kv=n['kv'],zone=n['zone'],
            present_baseline=bid in original,retained=n['retained'],role=n['role'],
            display_x_cm=x,display_y_cm=y,display_basis='schematic_manual_not_geographic',
            source_lon=n['lon'],source_lat=n['lat'],coordinate_basis=n['coordinateBasis'],coordinate_quality=n['quality']))
writecsv(OUT/'data/downstate_nodes.csv',node_rows)
writecsv(OUT/'data/downstate_original_edges.csv',rows(baseline))
writecsv(OUT/'data/downstate_current_edges.csv',rows(active))

tex=[r'% Source-derived connectivity. Generated by build_downstate_figure.py.',
r'% Display positions are schematic. CSVs preserve every represented bus and circuit key.',
r'\begingroup',r'\definecolor{dsAdded}{RGB}{140,24,48}',r'\definecolor{dsOld}{RGB}{113,118,122}',
r'\begin{tikzpicture}[x=1cm,y=1cm, every node/.style={font=\fontsize{7.1}{8}\selectfont},',
r' dsOriginal/.style={draw=dsOld,line width=.66pt},',r' dsAddedLine/.style={draw=dsAdded,line width=.55pt,opacity=.75},',
r' dsLabel/.style={fill=white,inner sep=.7pt,text=black,align=left}]',
r'\path[use as bounding box] (0,0) rectangle (14.4,5.4);',
r'\node[anchor=west,font=\small\bfseries] at (.10,5.19) {2019 structural counterpart};',
r'\node[anchor=west,font=\small\bfseries] at (7.37,5.19) {Current downstate detail};',
r'\node[anchor=west,text=dsOld,font=\fontsize{8}{9}\selectfont] at (.10,4.88) {Paper-derived NPCC parent; G--K excerpt};',
r'\node[anchor=west,text=dsAdded,font=\fontsize{8}{9}\selectfont] at (7.37,4.88) {Station detail + dated projects};',
r'\draw[gray!25,line width=.4pt] (7.16,.54)--(7.16,5.35);']

def coord(group,offset):
    g=gby[group];return f'({offset+.32+g[2]:.3f},{1.00+.75*g[3]:.3f})'

def draw_panel(edges,offset,after):
    represented=selected if after else original
    pairs=defaultdict(list)
    for e in edges:
        ga,gb=bus_to_group[e['a']],bus_to_group[e['b']]
        if ga!=gb:pairs[tuple(sorted((ga,gb)))].append(e)
    for (a,b),es in pairs.items():
        style='dsOriginal' if all(e['key'].startswith(('PARENT:','NPCC:')) for e in es) else 'dsAddedLine'
        keys=', '.join(e['key'] for e in es)
        tex.append('% '+keys)
        tex.append(f'\\draw[{style}] {coord(a,offset)} -- {coord(b,offset)};')
    for group,bids,x,y in groups:
        if not any(b in represented for b in bids):continue
        old=any(b<=140 for b in bids);retain=any(nodes[b]['retained'] for b in bids)
        color='dsOld' if old else 'dsAdded'
        radius='1.8pt' if (old or retain) else '1.25pt'
        tex.append(f'\\filldraw[draw={color},fill='+ (color if (old or retain) else 'white') +f',line width=.55pt] {coord(group,offset)} circle[radius={radius}];')
    return len(pairs)

base_pairs=draw_panel(baseline,0,False)
after_pairs=draw_panel(active,7.27,True)

def label(group,text,offset,dx,dy,anchor='west',color='black'):
    g=gby[group]; x=offset+.32+g[2]+dx;y=1+.75*g[3]+dy
    tex.append(f'\\node[dsLabel,anchor={anchor},text={color}] at ({x:.3f},{y:.3f}) {{{text}}};')

base_labels=[('pv','Pleasant Valley',.00,.14,'south'),('ramapo','Ramapo',-.04,.15,'south west'),('buch','Buchanan',-.04,-.14,'north'),
('mill','Millwood',.12,.06,'west'),('ceug',r'CE UG\\(aggregate)',-.1,-.07,'north east'),
('rava','RAV A-3',.0,-.14,'north'),('northport','Northport',.0,.14,'south'),('goethals','Goethals',.0,-.14,'north west'),
('ak3','AK-3',.10,-.10,'north west'),('south','Southington',.0,.14,'south east')]
for g,t,dx,dy,a in base_labels:label(g,t,0,dx,dy,a)
after_labels=[('pv','Pleasant Vly',-.03,.13,'south'),('ramapo','Ramapo',-.06,-.12,'north west'),
('mill','Millwood',.10,.03,'west'),('ef','E. Fishkill',.12,.02,'west'),('wood','Wood St.',.12,.04,'west'),
('laden','Ladentown',-.06,.11,'south'),('cv','Cricket Vly',0,.13,'south'),('dover','Dover',0,.13,'south'),
('lm','Long Mtn.',.0,-.12,'north east'),
('sprain','Sprain Brook',-.05,.14,'south'),('dun','Dunwoodie',-.10,-.04,'north east'),
('egc',r'East Garden\\City',.10,-.04,'north west'),('northport','Northport',0,-.13,'north'),
('ast','E. Astoria',.11,.02,'west'),('rai','Rainey',-.12,.03,'east'),('gow','Gowanus',-.04,-.15,'north'),
('goethals','Goethals',-.05,.12,'south west')]
for g,t,dx,dy,a in after_labels:label(g,t,7.27,dx,dy,a)

tex += [r'\node[anchor=west,text=dsOld,font=\fontsize{7.5}{8.5}\selectfont] at (.13,.30) {\textbf{Schematic;} selected network excerpt.};',
r'\draw[dsOriginal] (7.54,.30)--(7.85,.30);',r'\node[anchor=west] at (7.91,.30) {original};',
r'\draw[dsAddedLine] (9.02,.30)--(9.33,.30);',r'\node[anchor=west,text=dsAdded] at (9.39,.30) {added detail};',
r'\node[anchor=east,text=dsOld,font=\fontsize{7.1}{8}\selectfont] at (14.25,.30) {parallel circuits merged};',
r'\end{tikzpicture}',r'\endgroup']
(OUT/'downstate_comparison.tex').write_text('\n'.join(line+'%' for line in tex)+'\n',encoding='utf-8')

def record(p):return dict(path=str(p.relative_to(ROOT)).replace('\\','/'),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
audit=dict(passed=True,source_derived_connectivity=True,baseline_bus_count=len(base_bus),baseline_branch_count=len(base_branch),
    baseline_definition='The 140 original_parent bus records and first 225 PARENT branch records in the paper-derived structural-parent registry. Current refinement statuses ignored for the pre-refinement structural view.',
    baseline_name_source='output/nygrid_2025_downstate/network/bus_register.csv:model_name',
    baseline_source_correction='Uses the paper-derived 225-row parent, not the separate ENLITEN 233-row NPCC.m source. The nine selected collapsed endpoint pairs are unchanged.',
    baseline_selected_endpoint_pairs_unchanged=True,
    source_files=[record(BASE),record(GEO),record(BUS)],
    baseline_selected_bus_ids=sorted(original),current_selected_bus_ids=sorted(selected),
    baseline_selected_branches=len(baseline),current_selected_active_parent_records=len(active),
    baseline_drawn_unique_pairs=base_pairs,current_drawn_unique_pairs=after_pairs,
    current_group_count=len(groups),co_located_voltage_and_regulated_ports_collapsed=True,
    current_self_connections_not_drawn=[e['key'] for e in active if bus_to_group[e['a']]==bus_to_group[e['b']]],
    all_selected_current_edges_active_in='post_dover',
    note='Connectivity excerpt, not complete G-K electrical network. Parallel circuit rows merged visually; all records and endpoint IDs retained in CSV. Voltage ports of same station share a display node. Includes 8 added retained ports. Original aggregate proxy nodes remain schematic.',
    geography_policy='Manual schematic positions only. Source coordinates exported for audit but not used as display coordinates.',
    electrical_policy='No impedances fabricated, inferred, plotted, or altered. Source parent endpoint adjacency only; no Yred coupling plotted.',
    qualifications=['Added relative to original model does not imply built after 2019.','Current source contains engineering equivalents and assumptions; diagram is not an installed-asset map.','Numerical section buses omitted.','Grey original nodes are preserved; inactive superseded aggregate branches omitted in current panel.'],
    outputs=[record(p) for p in [OUT/'downstate_comparison.tex',*sorted((OUT/'data').glob('downstate_*.csv'))]])
(AUDIT/'visual_downstate_source_audit.json').write_text(json.dumps(audit,indent=2)+'\n')
print(json.dumps({k:v for k,v in audit.items() if k.endswith('count') or k.endswith('records') or k.endswith('pairs') or k=='passed'},indent=2))
