/* Actual built HTML/JS behavior through DOM events. LinkeDOM provides no
 * browser layout or native hit testing; explicit geometry/IDL stubs below
 * are disclosed in the receipt. Real-browser visual QA is a separate check. */
'use strict';
const fs=require('fs'),path=require('path'),vm=require('vm'),assert=require('assert'),crypto=require('crypto');
const root=path.resolve(__dirname,'../..'),out=path.join(root,'output/nygrid_2025_latest_map');
const library=path.join(root,'tmp/nygrid_2025_slim_map_test/node_modules/linkedom');
const {parseHTML}=require(library);
const htmlFile=path.join(out,'network_map.html'),html=fs.readFileSync(htmlFile,'utf8');
const {window}=parseHTML(html),document=window.document;
const data=JSON.parse(document.getElementById('network-data').textContent),annual=data.annual,geo=data.geography,defs=data.interfaces;
const checks=[],errors=[],networkRequests=[],consoleMessages=[];
const sha=value=>crypto.createHash('sha256').update(value).digest('hex');
const fileRecord=file=>({path:path.relative(root,file).replaceAll('\\','/'),bytes:fs.statSync(file).size,sha256:sha(fs.readFileSync(file))});
const inputFiles=[htmlFile,path.join(__dirname,'map.js'),path.join(__dirname,'map.css'),path.join(__dirname,'map_template.html'),
    path.join(out,'annual_data.json'),path.join(out,'geography_data.json'),path.join(out,'interface_definitions.json'),
    path.join(root,'output/nygrid_2025_acpf_profile_audit/alignment/interface_operator_terms.csv')];
const oldFiles=[path.join(root,'scripts/nygrid_2025_slim/test_interactive_map.cjs'),
    path.join(root,'output/nygrid_2025_slim/interactive/network_map.html')].filter(fs.existsSync);
const inputsBefore=inputFiles.map(fileRecord),oldBefore=oldFiles.map(fileRecord);
let canvasWidth=1024,canvasHeight=720,clock=1000,resizeCallback=null,captureCount=0,releaseCount=0;
const $=id=>document.getElementById(id),svg=$('map'),wrap=$('map-wrap'),tooltip=$('tooltip'),detail=$('detail');
Object.defineProperty(wrap,'clientWidth',{get:()=>canvasWidth});Object.defineProperty(wrap,'clientHeight',{get:()=>canvasHeight});
wrap.getBoundingClientRect=()=>({left:0,top:0,width:canvasWidth,height:canvasHeight,right:canvasWidth,bottom:canvasHeight});
Object.defineProperty(tooltip,'offsetWidth',{get:()=>260});Object.defineProperty(tooltip,'offsetHeight',{get:()=>100});
// Supply ordinary select.value and checkbox.checked state, absent from this
// pinned DOM implementation; these adapters do not alter application code.
Object.defineProperty(window.HTMLSelectElement.prototype,'value',{configurable:true,
    get(){return this.querySelector('option[selected]')?.value??this.querySelector('option')?.value??'';},
    set(value){for(const option of this.querySelectorAll('option')){
        if(option.value===String(value))option.setAttribute('selected','');else option.removeAttribute('selected');}}});
const checkedState=new WeakMap();
Object.defineProperty(window.HTMLInputElement.prototype,'checked',{configurable:true,
    get(){return checkedState.has(this)?checkedState.get(this):this.hasAttribute('checked');},
    set(value){checkedState.set(this,Boolean(value));}});
const capturedPointers=new Set();
svg.setPointerCapture=id=>{captureCount++;capturedPointers.add(id);};
svg.hasPointerCapture=id=>capturedPointers.has(id);
svg.releasePointerCapture=id=>{releaseCount++;capturedPointers.delete(id);};
const ResizeObserver=class{constructor(callback){resizeCallback=callback;}observe(){}};
const blocked=name=>function(...args){networkRequests.push({api:name,args:args.map(String)});throw Error('Unexpected runtime network API: '+name);};
const networkStubs=Object.fromEntries(['fetch','XMLHttpRequest','WebSocket','EventSource','Worker','SharedWorker'].map(name=>[name,blocked(name)]));
Object.assign(window,networkStubs);
const context=vm.createContext({window,document,Map,Set,Array,Object,Number,String,Math,JSON,Date,Intl,
    performance:{now:()=>clock},ResizeObserver,requestAnimationFrame:fn=>{fn();return 1;},...networkStubs,
    console:{log:(...args)=>consoleMessages.push(args.join(' ')),warn:(...args)=>consoleMessages.push(args.join(' ')),error:(...args)=>errors.push(args.join(' '))}});
const scripts=[...document.querySelectorAll('script')].filter(node=>node.getAttribute('type')!=='application/json');
function check(name,fn){
    try{fn();checks.push({name,passed:true});console.log('PASS '+name);}
    catch(error){checks.push({name,passed:false,error:String(error.message).slice(0,1800)});console.error('FAIL '+name+': '+String(error.message).slice(0,600));}
}
function event(target,type,props={}){
    assert(target,'Missing event target');const e=new window.Event(type,{bubbles:true,cancelable:true});
    for(const [key,value]of Object.entries(props))Object.defineProperty(e,key,{value});target.dispatchEvent(e);return e;
}
function click(target){if(typeof target==='string')target=document.querySelector(target);assert(target,'Missing click target');event(target,'click');}
function choose(id,value){$(id).value=String(value);event($(id),'change');}
function toggle(id,value){$(id).checked=value;event($(id),'change');}
function setHour(value){choose('hour-index',value);}
function currentBox(){return svg.getAttribute('viewBox').trim().split(/\s+/).map(Number);}
function base(hour=8508){clock+=500;setHour(hour);choose('network-mode','retained');choose('power-units','model');
    toggle('show-zones',true);toggle('show-interfaces',true);toggle('show-controls',true);toggle('show-inactive',false);
    choose('bus-labels','added');click('#clear-selection');click('[data-view="ny"]');}
function close(actual,expected,tolerance=1e-8){assert(Math.abs(actual-expected)<=tolerance,`${actual} != ${expected}`);}
function nodesById(){return new Map(geo.nodes.map(n=>[Number(n.id),n]));}
function pairValues(){const answer={};for(const dt of detail.querySelectorAll('dt'))answer[dt.textContent]=dt.nextElementSibling.textContent;return answer;}
function powerTextMatches(text,expected){
    if(expected===null){assert(text.includes('—'),'Unavailable value rendered numerically: '+text);return;}
    const number=Number.parseFloat(text.replaceAll(',','').replaceAll('−','-'));
    assert(Number.isFinite(number),'Missing displayed numeric value: '+text);
    close(number,expected,Math.abs(expected)<100?.05000001:.50000001);
}
function visible(nodes){return [...nodes].filter(node=>node.style.display!=='none');}
function csvRow(line){let quote=false,value='',row=[];for(let i=0;i<line.length;i++){
    const c=line[i];if(c==='"'){if(quote&&line[i+1]==='"'){value+='"';i++;}else quote=!quote;}
    else if(c===','&&!quote){row.push(value);value='';}else value+=c;}row.push(value);return row;}
const csv=fs.readFileSync(inputFiles.at(-1),'utf8').trim().split(/\r?\n/),header=csvRow(csv.shift());
const frozenTerms=csv.map(line=>Object.fromEntries(csvRow(line).map((value,index)=>[header[index],value])));
check('built page embeds exactly the frozen annual, geography and interface JSON',()=>{
    assert.strictEqual(scripts.length,1);
    for(const [key,name]of [['annual','annual_data.json'],['geography','geography_data.json'],['interfaces','interface_definitions.json']]){
        assert.strictEqual(sha(JSON.stringify(data[key])),sha(JSON.stringify(JSON.parse(fs.readFileSync(path.join(out,name),'utf8')))),name);
    }
    assert.strictEqual(annual.hours.length,8760);assert.strictEqual(annual.interfaceNames.length,7);assert.strictEqual(annual.zoneNames.length,11);
    assert.strictEqual(annual.hours.filter(h=>h.qualified).length,8170);assert.strictEqual(annual.hours.filter(h=>h.operatingQualified).length,0);
});
let started=false;
check('actual inline application initializes without substitution',()=>{
    vm.runInContext(scripts[0].textContent,context,{timeout:20000});started=true;assert.strictEqual(svg.dataset.ready,'true');
});
if(started){
check('initial hour8508 has145 geographic markers,7 flow labels and11 zone labels',()=>{
    assert.strictEqual(svg.dataset.hour,'8508');assert.strictEqual(svg.dataset.state,'post_dover');assert.strictEqual(svg.dataset.mode,'retained');
    assert.strictEqual(svg.querySelectorAll('.bus-group').length,145);assert.strictEqual(svg.dataset.geographicBusCount,'145');
    assert.strictEqual(svg.dataset.interfaceLabelCount,'7');assert.strictEqual(svg.dataset.zoneLabelCount,'11');
    assert.strictEqual(document.querySelectorAll('.flow-row').length,7);assert.strictEqual(document.querySelectorAll('.zone-button').length,11);
    assert.strictEqual(svg.querySelectorAll('rect.bus-mark').length,8);assert($('hour-status').textContent.includes('operating limits failed'));
});
check('four dated state boundaries preserve148axis and update188/189 detailed markers',()=>{
    base();
    const cases=[[1,'pre_may',188],[3359,'pre_may',188],[3360,'may21',188],[3575,'may21',188],
        [3576,'may30',188],[8471,'may30',188],[8472,'post_dover',189],[8760,'post_dover',189]];
    for(const [hour,state,count]of cases){setHour(hour);choose('network-mode','detailed');
        assert.strictEqual(svg.dataset.state,state);assert.strictEqual(svg.querySelectorAll('.bus-group').length,count);
        assert.strictEqual(Number(svg.dataset.geographicBusCount),count);choose('network-mode','retained');
        assert.strictEqual(svg.querySelectorAll('.bus-group').length,145);assert.strictEqual(geo.nodes.filter(n=>n.retained).length,148);
    }
});
check('each interface selection lists and highlights the exact frozen signed parent members in every state',()=>{
    const lookup=nodesById();
    for(const [hour,state]of [[523,'pre_may'],[3360,'may21'],[4000,'may30'],[8508,'post_dover']]){
        base(hour);let total=0;
        for(const def of defs.interfaces){click(`.flow-row[data-flow-id="${def.id}"]`);assert.strictEqual(svg.dataset.mode,'detailed');
            const expected=frozenTerms.filter(term=>term.state===state&&term.interface===def.name);total+=expected.length;
            const buttons=[...detail.querySelectorAll('[data-parent-member]')];assert.strictEqual(buttons.length,expected.length);
            const expectedById=new Map(expected.map(term=>[Number(term.original_branch_row),Number(term.coefficient)]));
            assert.deepStrictEqual(buttons.map(b=>Number(b.dataset.parentMember)).sort((a,b)=>a-b),[...expectedById.keys()].sort((a,b)=>a-b));
            for(const button of buttons)assert(button.textContent.startsWith(expectedById.get(Number(button.dataset.parentMember))>0?'+':'−'));
            const drawn=[...svg.querySelectorAll('[data-type="parent"]')];
            const highlighted=drawn.filter(g=>g.querySelector('.edge-line').style.opacity==='1').map(g=>Number(g.dataset.parentId)).sort((a,b)=>a-b);
            const visibleExpected=expected.filter(term=>lookup.get(Number(term.original_from_bus))?.xy&&lookup.get(Number(term.original_to_bus))?.xy).map(term=>Number(term.original_branch_row)).sort((a,b)=>a-b);
            assert.deepStrictEqual(highlighted,visibleExpected);assert.strictEqual(svg.querySelectorAll('[data-type="coupling"]').length,0);
        }
        assert.strictEqual(total,34);
    }
});
check('zone selection displays the correct11zone source/results values and highlights correct buses',()=>{
    base();const lookup=nodesById();
    for(let i=0;i<defs.zones.length;i++){
        const z=defs.zones[i];click(`[data-zone-button="${z.id}"]`);assert(detail.textContent.includes('Zone '+z.id));
        const pairs=pairValues();
        for(const [label,key]of [['Gross boundary target','gross'],['Delivered load','served'],['Assigned AC loss','loss'],['Net native generation','generation']]){
            powerTextMatches(pairs[label],annual.zoneSeriesModelMW[key][8507][i]);
        }
        for(const node of svg.querySelectorAll('.bus-group'))assert.strictEqual(node.style.opacity,lookup.get(Number(node.dataset.busId)).zone===z.id?'1':'.28');
    }
});
check('model/public power switch preserves exact unrounded DOM flow values',()=>{
    base();const gamma=annual.metadata.gamma;assert.strictEqual(Number(defs.gamma),gamma);
    for(const units of ['model','public','model']){
        choose('power-units',units);assert.strictEqual(svg.dataset.units,units);
        for(let j=0;j<7;j++){
            const expected=annual.interfaceFlowsModelMW[8507][j]/(units==='public'?gamma:1),id=defs.interfaces[j].id;
            assert.strictEqual(Number(document.querySelector(`.flow-row[data-flow-id="${id}"]`).dataset.flowValue),expected);
            assert.strictEqual(Number(svg.querySelector(`.flow-label[data-interface="${id}"]`).dataset.flowValue),expected);
        }
    }
});
check('negative Moses total reverses arrow endpoints and remains reversed after public conversion',()=>{
    base();const index=annual.interfaceNames.indexOf('MOSES SOUTH'),def=defs.interfaces[index];assert(annual.interfaceFlowsModelMW[8507][index]<0);
    for(const units of ['model','public']){choose('power-units',units);
        const line=svg.querySelector(`[data-interface-arrow="${def.id}"]`);assert.notStrictEqual(line.style.display,'none');
        assert.strictEqual(line.dataset.direction,'reverse');assert.strictEqual(line.getAttribute('marker-end'),'url(#flow-arrow)');
        const values=line.getAttribute('d').match(/[+-]?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?/ig).map(Number);
        close(values[0],def.positive_orientation.target_xy[0]);close(values[1],def.positive_orientation.target_xy[1]);
        close(values.at(-2),def.positive_orientation.source_xy[0]);close(values.at(-1),def.positive_orientation.source_xy[1]);
        assert.strictEqual(document.querySelector(`.flow-row[data-flow-id="${def.id}"]`).dataset.direction,'reverse');
    }
});
check('failed2349 and excluded154 expose no computed interface values or arrows',()=>{
    for(const hour of [2349,154]){base(hour);assert.strictEqual(svg.dataset.qualified,'false');
        for(const row of document.querySelectorAll('.flow-row')){assert.strictEqual(row.dataset.flowValue,'');assert.strictEqual(row.dataset.direction,'unavailable');}
        for(const label of svg.querySelectorAll('.flow-label')){assert.strictEqual(label.dataset.flowValue,'');assert(label.textContent.includes('—'));}
        for(const line of svg.querySelectorAll('[data-interface-arrow]'))assert.strictEqual(line.style.display,'none');
        assert($('hour-status').textContent.includes(hour===154?'Source-excluded':'No qualified AC flow'));
    }
});
check('failed hour retains only known zone inputs; excluded hour blanks all zone quantities',()=>{
    for(const hour of [2349,154]){base(hour);click('[data-zone-button="A"]');const pairs=pairValues();
        for(const [label,key]of [['Gross boundary target','gross'],['Delivered load','served'],['Assigned AC loss','loss'],['Net native generation','generation']]){
            powerTextMatches(pairs[label],annual.zoneSeriesModelMW[key][hour-1][0]);
        }
        assert(pairs['Delivered load'].includes('—')&&pairs['Assigned AC loss'].includes('—'));
        if(hour===2349)assert(!pairs['Gross boundary target'].includes('—')&&!pairs['Net native generation'].includes('—'));
        else assert(Object.values(pairs).every(text=>text.includes('—')));
    }
});
check('nearby flow chart breaks its path at unavailable hours instead of interpolating',()=>{
    base(2349);const index=4,first=2348-12,last=2348+12;let runs=0,inRun=false;
    for(const row of annual.interfaceFlowsModelMW.slice(first,last+1)){const finite=row[index]!==null;if(finite&&!inRun)runs++;inRun=finite;}
    assert(runs>1);const path=$('flow-chart').querySelector('path');assert(path);assert.strictEqual((path.getAttribute('d').match(/M/g)||[]).length,runs);
});
check('prescribed control popup and source masks follow six input records without inventing unlocated links',()=>{
    base();const lookup=nodesById();
    const expected=geo.transfers.filter(t=>lookup.get(Number(t.a))?.xy&&lookup.get(Number(t.b))?.xy);
    assert.strictEqual(svg.querySelectorAll('[data-type="transfer"]').length,expected.length);assert.strictEqual(geo.transfers.length,6);
    for(const group of svg.querySelectorAll('[data-type="transfer"]')){click(group.querySelector('.edge-hit'));const pairs=pairValues();
        const t=geo.transfers.find(t=>String(t.id??t.key)===group.dataset.edgeId),row=Number(t.row??t.id)-1;
        powerTextMatches(pairs['Prescribed P'],annual.fixedTransferFlowsModelMW[8507][row]);assert(detail.textContent.includes('ideal PAR'));
    }
    base(154);for(const group of svg.querySelectorAll('[data-type="transfer"]'))assert.strictEqual(group.querySelector('.edge-line').getAttribute('marker-end'),null);
    toggle('show-controls',false);assert.strictEqual(svg.querySelectorAll('[data-type="transfer"]').length,0);
});
check('datetime, index and slider navigation honor UTC year limits and reject invalid hours',()=>{
    base();choose('datetime',annual.hours[0].timestamp.slice(0,16));assert.strictEqual(svg.dataset.hour,'1');assert.strictEqual($('prev-hour').disabled,true);
    click('#prev-hour');assert.strictEqual(svg.dataset.hour,'1');click('#next-hour');assert.strictEqual(svg.dataset.hour,'2');
    choose('datetime',annual.hours.at(-1).timestamp.slice(0,16));assert.strictEqual(svg.dataset.hour,'8760');assert.strictEqual($('next-hour').disabled,true);
    click('#next-hour');assert.strictEqual(svg.dataset.hour,'8760');click('#prev-hour');assert.strictEqual(svg.dataset.hour,'8759');
    for(const invalid of [0,8761,1.5]){setHour(invalid);assert.strictEqual(svg.dataset.hour,'8759');assert.strictEqual($('hour-index').value,'8759');}
    choose('datetime','2026-01-01T05:00');assert.strictEqual(svg.dataset.hour,'8759');
    $('hour-slider').value='8508';event($('hour-slider'),'input');assert.strictEqual(svg.dataset.hour,'8508');
    assert.strictEqual($('datetime').value,annual.hours[8507].timestamp.slice(0,16));
});
check('hour-index input events immediately navigate valid hours without applying partial or invalid edits',()=>{
    base();$('hour-index').value='4000';event($('hour-index'),'input');assert.strictEqual(svg.dataset.hour,'4000');
    assert.strictEqual(svg.dataset.state,'may30');assert.strictEqual($('hour-slider').value,'4000');
    assert.strictEqual($('datetime').value,annual.hours[3999].timestamp.slice(0,16));
    for(const invalid of ['', '4000.5', '0', '8761']){$('hour-index').value=invalid;event($('hour-index'),'input');assert.strictEqual(svg.dataset.hour,'4000');}
    $('hour-index').value='8508';event($('hour-index'),'input');assert.strictEqual(svg.dataset.hour,'8508');assert.strictEqual(svg.dataset.state,'post_dover');
});
check('UTC datetime input events navigate the exact cutover and ignore incomplete or unmatched dates',()=>{
    base();
    for(const [hour,state]of [[8471,'may30'],[8472,'post_dover'],[154,'pre_may']]){
        $('datetime').value=annual.hours[hour-1].timestamp.slice(0,16);event($('datetime'),'input');
        assert.strictEqual(svg.dataset.hour,String(hour));assert.strictEqual(svg.dataset.state,state);
        assert.strictEqual($('hour-index').value,String(hour));assert.strictEqual($('hour-slider').value,String(hour));
    }
    for(const partial of ['', '2025-12', '2027-01-01T00:00']){$('datetime').value=partial;event($('datetime'),'input');assert.strictEqual(svg.dataset.hour,'154');}
    assert.strictEqual(svg.dataset.qualified,'false');
    $('datetime').value=annual.hours[8507].timestamp.slice(0,16);event($('datetime'),'input');assert.strictEqual(svg.dataset.hour,'8508');
});
check('three unlocated proxies remain inspectable with no fabricated geographic markers',()=>{
    base();for(const id of [78,79,82]){const node=geo.nodes.find(n=>Number(n.id)===id);assert.strictEqual(node.xy,null);
        assert.strictEqual(svg.querySelector(`[data-bus-id="${id}"]`),null);choose('bus-select',id);
        assert(detail.textContent.includes('Bus '+id));assert(detail.textContent.includes('No geographic point is assigned'));
        assert($('bus-select').querySelector(`option[value="${id}"]`).textContent.includes('unlocated'));
    }
});
check('interactive bus, flow, zone and edge pointer targets never capture a background pan',()=>{
    const fixtures=[['.bus-group[data-bus-id="10858"] .bus-hit','Bus 10858'],
        ['.flow-label rect',defs.interfaces[0].name],['.zone-label[data-zone="A"] rect','Zone A'],
        ['[data-type="coupling"] .edge-hit','Retained AC coupling']];
    for(let i=0;i<fixtures.length;i++){
        base();const [selector,detailText]=fixtures[i],target=svg.querySelector(selector);assert(target);
        const before=currentBox(),captures=captureCount,pointerId=100+i;
        event(target,'pointerdown',{button:0,pointerId,clientX:300,clientY:220});
        event(svg,'pointermove',{pointerId,clientX:370,clientY:280});event(svg,'pointerup',{pointerId,clientX:370,clientY:280});
        assert.strictEqual(captureCount,captures);assert.strictEqual(svg.hasPointerCapture(pointerId),false);
        assert.deepStrictEqual(currentBox(),before);assert(!svg.classList.contains('dragging'));
        click(target);assert(detail.textContent.includes(detailText));
    }
});
check('regulated port21001 is offered only in its post-Dover dated topology',()=>{
    base(8471);assert.strictEqual($('bus-select').querySelector('option[value="21001"]'),null);
    assert.strictEqual(svg.querySelector('[data-bus-id="21001"]'),null);
    setHour(8472);assert($('bus-select').querySelector('option[value="21001"]'));
    assert.strictEqual(svg.querySelector('[data-bus-id="21001"]'),null,'Nonretained port must not enter the retained layer');
    setHour(8471);assert.strictEqual($('bus-select').querySelector('option[value="21001"]'),null);
});
check('selecting a nonretained port opens detailed mode and clears when that port becomes absent',()=>{
    base(8508);choose('bus-select',21001);assert.strictEqual(svg.dataset.mode,'detailed');assert.strictEqual($('network-mode').value,'detailed');
    assert(svg.querySelector('[data-bus-id="21001"]'));assert(detail.textContent.includes('Bus 21001'));
    assert(detail.textContent.includes('20003')&&detail.textContent.includes('no independent physical coordinate'));
    setHour(8471);assert.strictEqual($('bus-select').value,'');assert.strictEqual(svg.querySelector('[data-bus-id="21001"]'),null);
    assert(detail.textContent.includes('Inspect the current model'));assert.strictEqual(svg.dataset.geographicBusCount,'188');
    setHour(8472);assert($('bus-select').querySelector('option[value="21001"]'));assert.strictEqual($('bus-select').value,'');
    assert(detail.textContent.includes('Inspect the current model'));
});
check('latest parent224 data and mathematical retained couplings are distinguished in popups',()=>{
    base();const coupling=svg.querySelector('[data-type="coupling"] .edge-hit');assert(coupling);click(coupling);
    assert(detail.textContent.includes('not an individual conductor'));assert(detail.textContent.includes('no line flow or ampacity'));
    choose('network-mode','detailed');const parent=svg.querySelector('[data-parent-id="224"] .edge-hit');assert(parent);click(parent);
    const p=pairValues();close(Number.parseFloat(p['Total R']),.02,1e-12);close(Number.parseFloat(p['Total X']),.0147,1e-12);
    close(Number.parseFloat(p['Total B']),0,1e-12);assert.strictEqual(p['Synthetic conductor eligibility'],'Excluded');
});
check('zone, interface, inactive and bus-label toggles change only their intended layers',()=>{
    base();const markerCount=svg.querySelectorAll('.bus-group').length;
    toggle('show-zones',false);assert.strictEqual(svg.dataset.zoneLabelCount,'0');assert.strictEqual(svg.dataset.interfaceLabelCount,'7');
    toggle('show-interfaces',false);assert.strictEqual(svg.dataset.interfaceLabelCount,'0');for(const line of svg.querySelectorAll('[data-interface-arrow]'))assert.strictEqual(line.style.display,'none');
    assert.strictEqual(document.querySelectorAll('.flow-row').length,7);toggle('show-zones',true);toggle('show-interfaces',true);
    choose('bus-labels','none');assert.strictEqual(svg.dataset.busLabelCount,'0');choose('bus-labels','added');click('[data-view="downstate"]');assert(Number(svg.dataset.busLabelCount)>0);
    choose('bus-labels','all');assert(Number(svg.dataset.busLabelCount)>0);assert.strictEqual(svg.querySelectorAll('.bus-group').length,markerCount);
    choose('network-mode','detailed');const active=svg.querySelectorAll('[data-type="parent"]').length;toggle('show-inactive',true);
    assert(svg.querySelectorAll('[data-type="parent"]').length>active);toggle('show-inactive',false);assert.strictEqual(svg.querySelectorAll('[data-type="parent"]').length,active);
});
check('view presets, zoom buttons and wheel preserve geographic marker coordinates',()=>{
    base();click('[data-view="fullNPCC"]');const full=currentBox();click('[data-view="downstate"]');assert(currentBox()[2]<full[2]);
    const n=geo.nodes.find(n=>n.retained&&Number(n.id)>140&&n.xy),mark=svg.querySelector(`[data-bus-id="${n.id}"] .bus-mark`);
    const center=()=>[Number(mark.getAttribute('x'))+Number(mark.getAttribute('width'))/2,Number(mark.getAttribute('y'))+Number(mark.getAttribute('height'))/2];
    const before=center(),box=currentBox();click('#zoom-in');assert(currentBox()[2]<box[2]);close(center()[0],before[0]);close(center()[1],before[1]);
    const small=currentBox();const e=event(svg,'wheel',{deltaY:120,clientX:500,clientY:300});assert(e.defaultPrevented);assert(currentBox()[2]>small[2]);
    click('#fit-view');assert(currentBox().every(Number.isFinite));
});
check('keyboard activation, pan, zoom, Home and Escape operate the actual controls',()=>{
    base();const node=svg.querySelector('[data-bus-id="10858"]');assert(node);event(node,'keydown',{key:'Enter'});assert(detail.textContent.includes('Bus 10858'));
    const before=currentBox();event(svg,'keydown',{key:'+'});assert(currentBox()[2]<before[2]);const zoomed=currentBox();
    event(svg,'keydown',{key:'ArrowRight'});assert(currentBox()[0]>zoomed[0]);event(svg,'keydown',{key:'Home'});assert(currentBox()[2]>zoomed[2]);
    event(node,'keydown',{key:'Escape'});assert(detail.textContent.includes('Inspect the current model'));assert.strictEqual($('bus-select').value,'');
});
check('drag captures pointer, pans, suppresses accidental click and allows the next deliberate selection',()=>{
    base();const before=currentBox(),released=releaseCount;event(svg,'pointerdown',{button:0,pointerId:9,clientX:300,clientY:220});
    assert(svg.hasPointerCapture(9));
    event(svg,'pointermove',{pointerId:9,clientX:430,clientY:280});assert(svg.classList.contains('dragging'));
    event(svg,'pointerup',{pointerId:9,clientX:430,clientY:280});assert(captureCount>0);assert(currentBox()[0]!==before[0]);assert(!svg.classList.contains('dragging'));
    assert(!svg.hasPointerCapture(9));assert.strictEqual(releaseCount,released+1);
    click(svg.querySelector('[data-bus-id="10858"]'));assert(detail.textContent.includes('Inspect the current model'));
    clock+=200;click(svg.querySelector('[data-bus-id="10858"]'));assert(detail.textContent.includes('Bus 10858'));
    event(svg,'pointerdown',{button:0,pointerId:10,clientX:300,clientY:220});assert(svg.hasPointerCapture(10));
    event(svg,'pointercancel',{pointerId:10});assert(!svg.hasPointerCapture(10));assert.strictEqual(releaseCount,released+2);
});
check('tooltip is clamped to the stub viewport and clears on pointer leave',()=>{
    base();const node=svg.querySelector('[data-bus-id="10858"]');event(node,'pointerenter',{clientX:canvasWidth-1,clientY:canvasHeight-1});
    assert.strictEqual(tooltip.style.display,'block');assert(Number.parseFloat(tooltip.style.left)>=0&&Number.parseFloat(tooltip.style.top)>=0);
    assert(Number.parseFloat(tooltip.style.left)+260<=canvasWidth);assert(Number.parseFloat(tooltip.style.top)+100<=canvasHeight);
    event(node,'pointerleave');assert.strictEqual(tooltip.style.display,'none');
});
check('mobile-like resize stubs keep finite aspect-correct geometry and visible labels within viewport',()=>{
    base();canvasWidth=360;canvasHeight=540;assert(resizeCallback);resizeCallback();click('#fit-view');
    const b=currentBox();assert(b.every(Number.isFinite));close(b[2]/b[3],canvasWidth/canvasHeight,1e-10);
    assert.strictEqual(svg.querySelectorAll('.bus-group').length,145);
    const labels=visible(svg.querySelectorAll('.flow-label,.zone-label'));assert(labels.length>0);
    for(const label of labels){const xy=label.getAttribute('transform').match(/[+-]?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?/ig).map(Number),rect=label.querySelector('rect');
        const x=(xy[0]-b[0])/b[2]*canvasWidth,y=(xy[1]-b[1])/b[3]*canvasHeight;
        assert(x>=-1e-6&&y>=-1e-6);assert(x+Number(rect.getAttribute('width'))<=canvasWidth+1e-6);assert(y+Number(rect.getAttribute('height'))<=canvasHeight+1e-6);
    }
    const node=svg.querySelector('[data-bus-id="10858"]');event(node,'pointerenter',{clientX:359,clientY:539});
    assert(Number.parseFloat(tooltip.style.left)+260<=360);assert(Number.parseFloat(tooltip.style.top)+100<=540);
    canvasWidth=1024;canvasHeight=720;resizeCallback();
});
check('no external runtime assets, requests or console errors occurred',()=>{
    assert.deepStrictEqual(networkRequests,[]);assert.deepStrictEqual(errors,[]);
    assert.strictEqual(document.querySelectorAll('script[src],link[rel="stylesheet"],iframe,img,object,embed,audio,video,source').length,0);
    for(const image of document.querySelectorAll('image'))assert(!/^(?:https?:)?\/\//.test(image.getAttribute('href')||image.getAttribute('xlink:href')||''));
    assert(!/\b(fetch|XMLHttpRequest|WebSocket|EventSource|importScripts)\s*\(/.test(scripts[0].textContent));
    assert(!/@import|url\(\s*['"]?(?:https?:)?\/\//i.test(document.querySelector('style').textContent));
});
}
const inputsAfter=inputFiles.map(fileRecord),oldAfter=oldFiles.map(fileRecord);
check('all tested map inputs and previous map/test files remained unchanged',()=>{assert.deepStrictEqual(inputsAfter,inputsBefore);assert.deepStrictEqual(oldAfter,oldBefore);});
const receipt={passed:checks.every(c=>c.passed)&&errors.length===0,checks_run:checks.length,checks,
    method:'Actual built inline HTML/JavaScript executed with LinkeDOM DOM events and explicit viewport/IDL stubs; no application replacement or network server',
    final_ui_freeze_confirmed:process.argv.includes('--final'),browser_visual_verification:false,native_pointer_hit_testing:false,
    separate_browser_QA_expected:true,layout_stubs:{initial_width:1024,initial_height:720,mobile_width:360,mobile_height:540,tooltip_width:260,tooltip_height:100,
        select_value_IDL:true,checkbox_checked_IDL:true,requestAnimationFrame:'synchronous',ResizeObserver:'explicit callback'},
    network_requests:networkRequests,console_errors:errors,console_messages:consoleMessages,
    html_sha256:sha(html),test_code_sha256:sha(fs.readFileSync(__filename)),node_version:process.version,
    linkedom_version:require(path.join(library,'package.json')).version,input_files:inputsAfter,previous_artifacts_preserved:oldAfter,
    generated_utc:new Date().toISOString()};
fs.writeFileSync(path.join(out,'interaction_validation.json'),JSON.stringify(receipt,null,2)+'\n');
console.log(JSON.stringify({passed:receipt.passed,checks:checks.length,failed:checks.filter(c=>!c.passed).map(c=>c.name),
    final_ui_freeze_confirmed:receipt.final_ui_freeze_confirmed,browser_visual_verification:false},null,2));
if(!receipt.passed)process.exitCode=1;
