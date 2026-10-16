(()=>{
'use strict';
const data=JSON.parse(document.getElementById('network-data').textContent);
const geo=data.geography,annual=data.annual,defs=data.interfaces;
const ns='http://www.w3.org/2000/svg',svg=document.getElementById('map'),wrap=document.getElementById('map-wrap');
const detail=document.getElementById('detail'),tooltip=document.getElementById('tooltip');
const nodes=new Map(geo.nodes.map(n=>[Number(n.id),n])),parents=new Map(geo.parents.map(p=>[Number(p.id),p]));
const zones=new Map(defs.zones.map((z,i)=>[z.id,{...z,index:i}]));
const zoneColors={A:'#a65e39',B:'#897b26',C:'#43835b',D:'#3b8394',E:'#557eb4',F:'#8063aa',G:'#a3608f',H:'#b96c64',I:'#b68b42',J:'#bb5361',K:'#527fa4'};
const categoryColors={overhead:'#758994',cable:'#3d789f',transformer:'#997740',composite:'#a0a1aa',par:'#997740',equivalent:'#8b7db0',inactiveRecord:'#bd8990',coupling:'#8b7db0',transfer:'#16837a'};
let h=8507,view='ny',mode='retained',units='model',selection=null,box=[0,0,100,100],lastNetworkKey='',drag=null,ignoreClickUntil=0,drawQueued=false;
let edgeElements=[],nodeElements=[],busLabels=[];
const zoneElements=[],interfaceElements=[];
const $=id=>document.getElementById(id);
function el(tag,attrs,parent){const node=document.createElementNS(ns,tag);for(const [k,v]of Object.entries(attrs||{}))node.setAttribute(k,String(v));if(parent)parent.append(node);return node;}
function esc(value){return String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function finite(v){return v!==null&&v!==undefined&&Number.isFinite(Number(v));}
function power(v){return finite(v)?Number(v)/(units==='public'?Number(annual.gamma||defs.gamma):1):null;}
function fmt(v){if(!finite(v))return '—';return Number(v).toLocaleString('en-US',{maximumFractionDigits:Math.abs(v)<100?1:0});}
function unit(){return units==='public'?'Public scale MW':'Model MW';}
function flow(i){return power(annual.interfaceFlowsModelMW[h]?.[i]);}
function hour(){return annual.hours[h];}
function state(){return hour().state??hour().stateId??geo.states[Number(hour().stateIndex)-1]?.id;}
function sourceQualified(){return Boolean(hour().sourceQualified??hour().source_qualified);}
function qualified(){return Boolean(hour().qualified??hour().lossQualified);}
function timestamp(){return hour().timestamp??hour().timestampUtc??hour().timestamp_utc;}
function present(item){const p=item.presenceByState;if(!p)return true;if(Array.isArray(p))return typeof p[0]==='boolean'||typeof p[0]==='number'?Boolean(p[geo.states.findIndex(s=>s.id===state())]):p.includes(state());return Boolean(p[state()]);}
function record(parent){if(Array.isArray(parent.stateRecords))return parent.stateRecords.find(s=>(s.stateId??s.id)===state());return parent.stateRecords?.[state()];}
function currentNodes(){return geo.nodes.filter(n=>present(n)&&n.xy&&(mode==='detailed'||n.retained));}
function refreshBusOptions(){const select=$('bus-select'),chosen=select.value;select.replaceChildren();const blank=document.createElement('option');blank.value='';blank.textContent='Find bus…';select.append(blank);for(const n of geo.nodes.filter(n=>present(n)&&!/numerical/i.test(n.role)).sort((a,b)=>String(a.name).localeCompare(String(b.name)))){const option=document.createElement('option');option.value=String(n.id);option.textContent=`${n.name} · #${n.id} · ${n.kv} kV${n.xy?'':' · unlocated'}`;select.append(option);}select.value=chosen&&nodes.has(Number(chosen))&&present(nodes.get(Number(chosen)))?chosen:'';}
function width(){return Math.max(wrap.clientWidth,1);}function height(){return Math.max(wrap.clientHeight,1);}function scale(){return box[2]/width();}
function screen(xy){return [(xy[0]-box[0])/box[2]*width(),(xy[1]-box[1])/box[3]*height()];}
function pixel(px,py){return [box[0]+px*box[2]/width(),box[1]+py*box[3]/height()];}
function color(n){return zoneColors[n.zone]||'#8698a3';}
function activeState(){return geo.states.find(s=>s.id===state())||{};}
function fit(){
  let bounds=geo.viewBounds?.[view];
  if(!bounds){const wanted=geo.nodes.filter(n=>n.xy&&present(n)&&(view==='fullNPCC'||(view==='downstate'?Number(n.id)>140||'GHIJK'.includes(n.zone):zones.has(n.zone))));bounds=[Math.min(...wanted.map(n=>n.xy[0])),Math.min(...wanted.map(n=>n.xy[1])),Math.max(...wanted.map(n=>n.xy[0])),Math.max(...wanted.map(n=>n.xy[1]))];}
  const cx=(bounds[0]+bounds[2])/2,cy=(bounds[1]+bounds[3])/2;let w=Math.max(bounds[2]-bounds[0],20)*1.24,hh=Math.max(bounds[3]-bounds[1],20)*1.24;
  if(w/hh<width()/height())w=hh*width()/height();else hh=w*height()/width();box=[cx-w/2,cy-hh/2,w,hh];draw();
}
function changeView(next){view=next;document.querySelectorAll('[data-view]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.view===view)));fit();}
function zoom(factor,rx=.5,ry=.5){const w=box[2]*factor,hh=box[3]*factor;if(w<.6||w>6500)return;box=[box[0]+(box[2]-w)*rx,box[1]+(box[3]-hh)*ry,w,hh];hideTip();draw();}
function queueDraw(){if(drawQueued)return;drawQueued=true;requestAnimationFrame(()=>{drawQueued=false;draw();});}
function hideTip(){tooltip.style.display='none';}
function tip(text,event){tooltip.innerHTML=text;tooltip.style.display='block';const r=wrap.getBoundingClientRect();let x=(event?.clientX??r.left+10)-r.left+12,y=(event?.clientY??r.top+35)-r.top+12;x=Math.max(6,Math.min(x,width()-tooltip.offsetWidth-7));y=Math.max(6,Math.min(y,height()-tooltip.offsetHeight-7));tooltip.style.left=x+'px';tooltip.style.top=y+'px';}
function activate(node,fn){node.addEventListener('click',event=>{if(performance.now()<ignoreClickUntil)return;event.stopPropagation();fn();});node.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();fn();}});}
function bindTip(node,text){node.addEventListener('pointerenter',e=>tip(typeof text==='function'?text():text,e));node.addEventListener('pointerleave',hideTip);node.addEventListener('focus',()=>tip(typeof text==='function'?text():text));node.addEventListener('blur',hideTip);}
const definitions=el('defs',{},svg);
el('path',{d:'M0,-3 L7,0 L0,3 Z',fill:'#b45309'},el('marker',{id:'flow-arrow',viewBox:'0 -4 8 8',refX:7,refY:0,markerWidth:7,markerHeight:7,orient:'auto',markerUnits:'strokeWidth'},definitions));
el('path',{d:'M0,-3 L7,0 L0,3 Z',fill:'#16837a'},el('marker',{id:'transfer-arrow',viewBox:'0 -4 8 8',refX:7,refY:0,markerWidth:6,markerHeight:6,orient:'auto',markerUnits:'strokeWidth'},definitions));
const basemap=el('g',{'data-layer':'basemap'},svg);
for(const layer of geo.basemap)el('path',{d:layer.path,class:layer.kind+' cartography','fill-rule':'evenodd'},basemap);
const edgesLayer=el('g',{'data-layer':'network'},svg),interfacesLayer=el('g',{'data-layer':'interfaces'},svg),nodesLayer=el('g',{'data-layer':'buses'},svg);
const busLabelsLayer=el('g',{'data-layer':'bus-labels'},svg),zonesLayer=el('g',{'data-layer':'zones'},svg),flowLabelsLayer=el('g',{'data-layer':'flow-labels'},svg);
function members(def){return def.members_by_state?.[state()]||[];}
function memberParents(){return selection?.type==='interface'?new Set(members(defs.interfaces[selection.index]).map(m=>Number(m.parent_id))):new Set();}
function lineGeometry(a,b,lane=0){const dx=b[0]-a[0],dy=b[1]-a[1],len=Math.hypot(dx,dy),s=scale();if(len<1e-6)return `M${a[0]},${a[1]} C${a[0]+18*s},${a[1]-24*s} ${a[0]+36*s},${a[1]+24*s} ${a[0]},${a[1]}`;const bend=lane*6*s;return `M${a[0]},${a[1]} Q${(a[0]+b[0])/2-dy/len*bend},${(a[1]+b[1])/2+dx/len*bend} ${b[0]},${b[1]}`;}
function buildNetwork(){
  const key=state()+'|'+mode+'|'+$('show-inactive').checked+'|'+$('show-controls').checked;if(key===lastNetworkKey)return;lastNetworkKey=key;
  edgesLayer.replaceChildren();nodesLayer.replaceChildren();busLabelsLayer.replaceChildren();edgeElements=[];nodeElements=[];busLabels=[];refreshBusOptions();
  let items=[];
  if(mode==='retained')items=(geo.couplings||[]).filter(p=>present(p)).map(p=>({...p,type:'coupling',category:'coupling'}));
  else items=geo.parents.filter(p=>record(p)&&($('show-inactive').checked||record(p).active)).map(p=>({...p,type:'parent'}));
  if($('show-controls').checked)items=items.concat(geo.transfers.filter(p=>present(p)).map(p=>({...p,type:'transfer',category:'transfer'})));
  const groups=new Map();for(const item of items){const key=[...([item.a,item.b].map(Number))].sort((a,b)=>a-b).join(':');if(!groups.has(key))groups.set(key,[]);groups.get(key).push(item);}
  for(const list of groups.values())for(let k=0;k<list.length;k++){
    const item=list[k],a=nodes.get(Number(item.a)),b=nodes.get(Number(item.b));if(!a?.xy||!b?.xy)continue;
    const group=el('g',{'data-type':item.type,'data-edge-id':item.id??item.key,'data-parent-id':item.type==='parent'?item.id:''},edgesLayer);
    const line=el('path',{class:'edge-line',stroke:categoryColors[item.category]||'#86949d','stroke-dasharray':item.type==='coupling'?'2 5':item.type==='transfer'?'7 3':record(item)?.active===false?'6 4':''},group);
    const hit=el('path',{class:'edge-hit',role:'button',tabindex:0,'aria-label':`${item.type==='coupling'?'AC coupling':item.type==='transfer'?'Prescribed transfer':'Parent corridor'} ${a.name} to ${b.name}`},group);
    edgeElements.push({group,line,hit,item,a,b,lane:k-(list.length-1)/2});activate(hit,()=>selectEdge(item));
    bindTip(hit,()=>`<b>${esc(item.type==='coupling'?'Retained AC coupling':item.type==='transfer'?'Prescribed transfer':item.key||'Parent '+item.id)}</b><br>${esc(a.name)} ↔ ${esc(b.name)}<br>${esc(item.classification||item.category)}`);
  }
  for(const n of currentNodes()){
    const group=el('g',{class:'bus-group','data-bus-id':n.id,'data-retained':Boolean(n.retained),role:'button',tabindex:0,'aria-label':`${n.name}, bus ${n.id}, ${n.kv} kV, ${n.zone}`},nodesLayer);
    const hit=el('circle',{class:'bus-hit',cx:n.xy[0],cy:n.xy[1]},group);
    const mark=el(n.retained&&Number(n.id)>140?'rect':'circle',{class:'bus-mark',fill:color(n)},group);
    nodeElements.push({group,hit,mark,n});activate(group,()=>selectBus(n.id));bindTip(group,()=>`<b>${esc(n.name)} · #${n.id}</b><br>${fmt(n.kv)} kV · ${esc(n.zone)}<br>${esc(n.coordinateBasis||n.role||'Model geography')}`);
    const text=el('text',{class:'bus-label','data-bus-label':n.id},busLabelsLayer);text.textContent=n.name;busLabels.push({text,n});
  }
}
function zoneXY(id){const anchor=(geo.zoneLabels||[]).find(z=>z.id===id||z.zone===id);return anchor?.xy||defs.zones.find(z=>z.id===id)?.anchor_xy;}
for(const z of defs.zones){const leader=el('path',{fill:'none',stroke:zoneColors[z.id],'stroke-width':.7,'stroke-opacity':.6,'vector-effect':'non-scaling-stroke',class:'zone-leader'},zonesLayer);const group=el('g',{class:'zone-label',role:'button',tabindex:0,'data-zone':z.id,'aria-label':`Zone ${z.id}, ${z.display_name}`},zonesLayer);const rect=el('rect',{},group),text=el('text',{fill:zoneColors[z.id]},group);text.textContent=`${z.id} · ${z.display_name}`;zoneElements.push({group,rect,text,leader,z});activate(group,()=>selectZone(z.id));bindTip(group,()=>`<b>Zone ${z.id} · ${esc(z.display_name)}</b><br>Model accounting group<br>Select for hourly load, loss and net native generation`);}
for(let i=0;i<defs.interfaces.length;i++){
  const def=defs.interfaces[i],line=el('path',{class:'interface-line','data-interface-arrow':def.id},interfacesLayer);
  const group=el('g',{class:'flow-label',role:'button',tabindex:0,'data-interface':def.id,'aria-label':def.name},flowLabelsLayer);
  const rect=el('rect',{rx:4},group),name=el('text',{},group),value=el('text',{class:'flow-number'},group);name.textContent=def.name;
  interfaceElements.push({group,rect,name,value,line,def,index:i});activate(group,()=>selectInterface(i));bindTip(group,()=>`<b>${esc(def.name)}</b><br>${fmt(flow(i))} ${unit()}<br>${members(def).length} signed parent records · model diagnostic cut`);
}
function direction(i){const v=flow(i);return !finite(v)?'unavailable':v<0?'reverse':v>0?'positive':'zero';}
function setHour(index){if(!Number.isInteger(Number(index))||Number(index)<1||Number(index)>annual.hours.length){syncControls();return;}h=Number(index)-1;if(selection?.type==='bus'&&!present(nodes.get(selection.id)))selection=null;hideTip();syncControls();updateStatus();updateFlows();renderDetail();draw();}
function syncControls(){$('hour-index').value=String(h+1);$('hour-slider').value=String(h+1);$('datetime').value=timestamp().slice(0,16);$('prev-hour').disabled=h===0;$('next-hour').disabled=h===annual.hours.length-1;}
function updateStatus(){
  const success=qualified(),source=sourceQualified();$('hour-status').className=success?'qualified':'failed';
  $('hour-status').textContent=success?'AC equations and loss balance passed · operating limits '+((hour().operatingQualified??hour().operating_qualified)?'passed':'failed'):source?'No qualified AC flow · '+(hour().status||'solver rejected this hour'):'Source-excluded hour · AC flows unavailable';
  const s=activeState();$('topology-status').textContent=`${state().replaceAll('_',' ')} · ${s.detailedBusCount} detailed buses · ${s.runtimeBranchCount} branch rows`;
  $('power-note').textContent=units==='model'?'Synthetic electrical power base':'Aggregate model power ÷ γ; no current rescaling';
  document.querySelectorAll('.unit-label').forEach(x=>x.textContent=unit());
}
function updateFlows(){
  const list=$('flow-list');list.replaceChildren();defs.interfaces.forEach((def,i)=>{const row=document.createElement('button');row.className='flow-row'+(selection?.type==='interface'&&selection.index===i?' selected':'');row.dataset.flowId=def.id;row.dataset.flowValue=finite(flow(i))?String(flow(i)):'';row.dataset.direction=direction(i);row.innerHTML=`<span>${esc(def.name)}</span><span class="value">${fmt(flow(i))}</span><span class="direction">${direction(i)==='positive'?'→':direction(i)==='reverse'?'←':direction(i)==='zero'?'·':'—'}</span>`;row.setAttribute('aria-label',`${def.name}: ${fmt(flow(i))} ${unit()}, ${direction(i)} direction`);row.onclick=()=>selectInterface(i);list.append(row);});drawChart();
}
function drawChart(){
  const chart=$('flow-chart');chart.replaceChildren();const idx=selection?.type==='interface'?selection.index:4,first=Math.max(0,h-12),last=Math.min(annual.hours.length-1,h+12);
  const values=Array.from({length:last-first+1},(_,j)=>power(annual.interfaceFlowsModelMW[first+j]?.[idx])),valid=values.filter(finite),w=280,hh=66;
  chart.setAttribute('viewBox',`0 0 ${w} ${hh}`);if(!valid.length){$('chart-caption').textContent='No qualified flow in this 25-hour window.';return;}
  let lo=Math.min(...valid,0),hi=Math.max(...valid,0);if(hi-lo<1){lo-=.5;hi+=.5;}const x=j=>7+j/Math.max(values.length-1,1)*(w-14),y=v=>6+(hi-v)/(hi-lo)*(hh-12);
  el('line',{x1:7,y1:y(0),x2:w-7,y2:y(0),stroke:'#dae2e5','stroke-width':1},chart);
  let path='',open=false;values.forEach((v,j)=>{if(!finite(v)){open=false;return;}path+=(open?'L':'M')+x(j)+','+y(v);open=true;});el('path',{d:path,fill:'none',stroke:'#a36b2d','stroke-width':1.8},chart);
  el('line',{x1:x(h-first),x2:x(h-first),y1:3,y2:hh-3,stroke:'#77909d','stroke-dasharray':'2 3'},chart);
  $('chart-caption').textContent=`${defs.interfaces[idx].name} · nearby 25 hours · gaps are unavailable flows`;
}
function clearSelection(){selection=null;$('bus-select').value='';hideTip();renderDetail();updateFlows();draw();}
function selectBus(id){const n=nodes.get(Number(id));if(!n||!present(n))return;if(!n.retained){mode='detailed';$('network-mode').value=mode;}selection={type:'bus',id:Number(id)};$('bus-select').value=String(id);hideTip();renderDetail();updateFlows();draw();}
function selectZone(id){selection={type:'zone',id};$('bus-select').value='';hideTip();renderDetail();updateFlows();draw();}
function selectInterface(index){selection={type:'interface',index};$('bus-select').value='';mode='detailed';$('network-mode').value=mode;hideTip();renderDetail();updateFlows();draw();}
function selectEdge(item){selection={type:item.type,id:item.id??item.key,item};$('bus-select').value='';hideTip();renderDetail();updateFlows();draw();}
function badges(items){return '<div class="badges">'+items.map(s=>`<span class="badge">${esc(s)}</span>`).join('')+'</div>';}
function pairs(rows){return '<dl class="pairs">'+rows.map(([a,b])=>`<dt>${esc(a)}</dt><dd>${esc(b)}</dd>`).join('')+'</dl>';}
function busName(id){const n=nodes.get(Number(id));return n?`${n.name} #${n.id}`:`#${id}`;}
function renderDetail(){
  if(!selection){detail.innerHTML='<h3>Inspect the current model</h3><p>Select an interface label to highlight its member corridors, a zone to inspect its hourly balance, or a bus for its geographic and electrical identity.</p><p>Colored markers show accounting-zone membership. Added retained ports are squares; other geographic buses are circles.</p>';return;}
  if(selection.type==='zone'){
    const z=zones.get(selection.id),index=z.index,series=annual.zoneSeriesModelMW,rows=[['Gross boundary target',series.gross?.[h]?.[index]],['Delivered load',series.served?.[h]?.[index]],['Assigned AC loss',series.loss?.[h]?.[index]],['Net native generation',series.generation?.[h]?.[index]]];
    detail.innerHTML=`<h3>Zone ${z.id} · ${esc(z.display_name)}</h3>${badges(['Model accounting zone',unit()])}${pairs(rows.map(([name,value])=>[name,fmt(power(value))+' MW']))}<p>Gross load and native generation are supplied source inputs. Delivered load and assigned loss require a qualified AC solution. HQ and other external equivalents are excluded from native generation.</p><p>The label is derived from model bus locations; it does not trace an official zone boundary.</p>`;return;
  }
  if(selection.type==='interface'){
    const def=defs.interfaces[selection.index],list=members(def);detail.innerHTML=`<h3>${esc(def.name)}</h3>${badges([unit(),direction(selection.index)==='reverse'?'Reverse total':direction(selection.index)==='positive'?'Positive total':direction(selection.index)==='zero'?'Zero total':'Flow unavailable'])}${pairs([['Signed interface flow',fmt(flow(selection.index))+' MW'],['Positive orientation',(def.source_zones||[]).join(', ')+' → '+(def.target_zones||[]).join(', ')],['Signed members',String(list.length)]])}<p>Sum of each frozen member coefficient times its original corridor from-terminal P. A negative aggregate reverses the arrow. Physical NYISO meter membership is unverified.</p><div class="member-list">${list.map(m=>`<button data-parent-member="${m.parent_id}">${m.coefficient>0?'+':'−'} parent ${m.parent_id} · ${esc(busName(m.from_bus))} → ${esc(busName(m.to_bus))}</button>`).join('')}</div>`;
    detail.querySelectorAll('[data-parent-member]').forEach(b=>b.onclick=()=>{const p=parents.get(Number(b.dataset.parentMember));if(p)selectEdge({...p,type:'parent'});});return;
  }
  if(selection.type==='bus'){
    const n=nodes.get(selection.id);detail.innerHTML=`<h3>${esc(n.name)}</h3>${badges(['Bus '+n.id,fmt(n.kv)+' kV',n.zone,n.retained?'Retained':'Detailed passive port'])}${pairs([['Coordinate basis',n.coordinateBasis||n.role||'Not located'],['Location quality',n.quality||'Declared model geography'],['Retained AC axis',n.retained?'Yes':'No']])}<p>${n.xy?n.displayAnchorOf?'Display anchor colocated with bus '+n.displayAnchorOf+'; no independent physical coordinate is claimed.':'A station/model point; geographic connections are not surveyed routes.':'No geographic point is assigned to this aggregate or numerical bus.'}</p><p>Coordinate source: ${esc(n.source||'Current geographic register')}</p>`;return;
  }
  const item=selection.item,a=nodes.get(Number(item.a)),b=nodes.get(Number(item.b));
  if(selection.type==='coupling'){detail.innerHTML=`<h3>Retained AC coupling</h3>${badges(['Mathematical admittance',state().replaceAll('_',' ')])}<p>${esc(a.name)} ↔ ${esc(b.name)}</p><p>This coupling represents the passive network eliminated between retained voltages. It is not an individual conductor, and no line flow or ampacity is assigned to the displayed edge. Its topology comes from the current dated AC reduction.</p>`;return;}
  if(selection.type==='transfer'){
    const row=Number(item.row??item.id)-1,v=power(annual.fixedTransferFlowsModelMW?.[h]?.[row]);detail.innerHTML=`<h3>${esc(item.name||item.key||'Prescribed transfer')}</h3>${badges(['Transfer record '+(row+1),unit()])}${pairs([['Model from bus',busName(item.a)],['Model to bus',busName(item.b)],['Prescribed P',fmt(v)+' MW']])}<p>The sign follows the modeled from-to direction. These six records include external transfers and two ideal PAR-flow equivalents. Model endpoints do not assert literal asset terminals.</p>`;return;
  }
  const r=record(item);detail.innerHTML=`<h3>Parent ${item.id} · ${esc(item.key||'corridor')}</h3>${badges([item.displayClassification||item.classification||item.category,r?.active?'Active':r?'Inactive':'Absent in this state'])}${pairs([['From',busName(item.a)],['To',busName(item.b)],['Total R',finite(r?.rPu)?Number(r.rPu).toPrecision(7)+' pu':'—'],['Total X',finite(r?.xPu)?Number(r.xPu).toPrecision(7)+' pu':'—'],['Total B',finite(r?.bPu)?Number(r.bPu).toPrecision(7)+' pu':'—'],['Numerical sections',String(r?.runtimeRows?.length??0)],['Synthetic conductor eligibility',r?.thermalEligible?'Eligible in this state':'Excluded']])}${item.knownCableEvidenceConflict?'<p>Documented cable-evidence conflict: excluded from the overhead conductor screen. '+esc(item.cableEvidence||'')+'</p>':''}<p>R/X/B totals sum the original numerical sections. Bus shunts and reactors are separate; these totals are not a fitted single pi equivalent. Conductor eligibility describes the declared R/X realization and is separate from facility ratings and operating qualification.</p>`;
}
function draw(){
  buildNetwork();svg.setAttribute('viewBox',box.join(' '));const s=scale(),highlight=memberParents();
  for(const e of edgeElements){const path=lineGeometry(e.a.xy,e.b.xy,e.lane);e.line.setAttribute('d',path);e.hit.setAttribute('d',path);
    let focus=!selection||selection.type==='bus'&&(Number(e.item.a)===selection.id||Number(e.item.b)===selection.id)||selection.type==='zone'&&(e.a.zone===selection.id||e.b.zone===selection.id)||selection.type==='interface'&&e.item.type==='parent'&&highlight.has(Number(e.item.id))||selection.item&&selection.type===e.item.type&&(selection.item.id??selection.item.key)===(e.item.id??e.item.key);
    e.line.style.opacity=focus?'1':'.20';e.line.setAttribute('stroke-width',focus&&selection?2.8:e.item.type==='coupling'?1:1.15);
    if(e.item.type==='transfer'){const v=annual.fixedTransferFlowsModelMW?.[h]?.[Number(e.item.row??e.item.id)-1];if(finite(v)&&v!==0){e.line.setAttribute('d',Number(v)<0?lineGeometry(e.b.xy,e.a.xy,-e.lane):path);e.line.setAttribute('marker-end','url(#transfer-arrow)');}else e.line.removeAttribute('marker-end');}
  }
  for(const e of nodeElements){const selected=selection?.type==='bus'&&selection.id===Number(e.n.id),r=(selected?6:e.n.retained?3.4:2.2)*s;e.hit.setAttribute('r',Math.max(9*s,r));e.mark.setAttribute('fill',selected?'#143d53':color(e.n));if(e.mark.tagName.toLowerCase()==='rect'){e.mark.setAttribute('x',e.n.xy[0]-r);e.mark.setAttribute('y',e.n.xy[1]-r);e.mark.setAttribute('width',2*r);e.mark.setAttribute('height',2*r);}else{e.mark.setAttribute('cx',e.n.xy[0]);e.mark.setAttribute('cy',e.n.xy[1]);e.mark.setAttribute('r',r);}e.group.style.opacity=selection?.type==='zone'&&e.n.zone!==selection.id?'.28':'1';}
  const occupied=[];
  function place(xy,w,hh,seed=0){const p=screen(xy);if(p[0]<-35||p[1]<-35||p[0]>width()+35||p[1]>height()+35)return null;const offsets=[[0,0],[0,-25],[0,25],[35,0],[-35,0]];for(let radius=50;radius<=220;radius+=25)for(let angle=0;angle<8;angle++)offsets.push([radius*Math.cos(angle*Math.PI/4),radius*Math.sin(angle*Math.PI/4)]);for(let j=0;j<offsets.length;j++){const o=offsets[(j+seed)%offsets.length];let x=Math.max(8,Math.min(p[0]-w/2+o[0],width()-w-8)),y=Math.max(53,Math.min(p[1]-hh/2+o[1],height()-hh-54));if(!occupied.some(b=>x<b[0]+b[2]+4&&x+w+4>b[0]&&y<b[1]+b[3]+4&&y+hh+4>b[1])){occupied.push([x,y,w,hh]);return [x,y];}}return null;}
  let visibleFlows=0;
  for(const e of interfaceElements){const orientation=e.def.positive_orientation||{},from=orientation.source_xy,to=orientation.target_xy,anchor=orientation.label_anchor_xy;const enabled=$('show-interfaces').checked,xy=anchor||from&&to&&[(from[0]+to[0])/2,(from[1]+to[1])/2];const v=flow(e.index);
    e.line.style.display=enabled&&from&&to&&finite(v)&&v!==0?'':'none';if(from&&to&&finite(v)&&v!==0){e.line.setAttribute('d',lineGeometry(v<0?to:from,v<0?from:to,0));e.line.setAttribute('marker-end','url(#flow-arrow)');e.line.dataset.direction=direction(e.index);}
    const w=Math.max(118,e.def.name.length*6+15),hh=37,pos=enabled&&xy?place(xy,w,hh,e.index%3):null;e.group.style.display=pos?'':'none';if(!pos)continue;visibleFlows++;const p=pixel(pos[0],pos[1]);e.group.setAttribute('transform',`translate(${p[0]} ${p[1]}) scale(${s})`);e.rect.setAttribute('width',w);e.rect.setAttribute('height',hh);e.name.setAttribute('x',7);e.name.setAttribute('y',13);e.value.setAttribute('x',7);e.value.setAttribute('y',29);e.value.textContent=`${fmt(v)} MW ${direction(e.index)==='reverse'?'←':direction(e.index)==='positive'?'→':''}`;e.group.dataset.flowValue=finite(v)?String(v):'';e.group.dataset.direction=direction(e.index);e.group.setAttribute('aria-label',`${e.def.name}, ${fmt(v)} ${unit()}, ${direction(e.index)} direction`);}
  let visibleZones=0;
  for(const e of zoneElements){const compact=width()<450,xy=zoneXY(e.z.id),w=compact?24:e.z.display_name.length*6+30,hh=19,pos=$('show-zones').checked&&xy?place(xy,w,hh):null;e.text.textContent=compact?e.z.id:`${e.z.id} · ${e.z.display_name}`;e.group.style.display=pos?'':'none';e.leader.style.display='none';if(!pos)continue;visibleZones++;const p=pixel(pos[0],pos[1]);e.group.setAttribute('transform',`translate(${p[0]} ${p[1]}) scale(${s})`);e.rect.setAttribute('width',w);e.rect.setAttribute('height',hh);e.text.setAttribute('x',0);e.text.setAttribute('y',14);const anchor=screen(xy),label=[pos[0]+w/2,pos[1]+hh/2];if(Math.hypot(anchor[0]-label[0],anchor[1]-label[1])>28){const end=pixel(label[0],label[1]);e.leader.setAttribute('d',`M${xy[0]},${xy[1]} L${end[0]},${end[1]}`);e.leader.style.display='';}}
  let labelCount=0;const labelMode=$('bus-labels').value;
  for(const e of busLabels){const show=labelMode!=='none'&&(labelMode==='all'||e.n.retained&&Number(e.n.id)>140||selection?.type==='bus'&&selection.id===Number(e.n.id)),p=screen(e.n.xy);let ok=show&&p[0]>=0&&p[1]>=0&&p[0]<=width()&&p[1]<=height();const r=[p[0]+7,p[1]-14,e.n.name.length*5.7,15];if(ok&&labelMode==='all'&&occupied.some(b=>r[0]<b[0]+b[2]&&r[0]+r[2]>b[0]&&r[1]<b[1]+b[3]&&r[1]+r[3]>b[1]))ok=false;e.text.style.display=ok?'':'none';if(ok){occupied.push(r);labelCount++;e.text.setAttribute('x',e.n.xy[0]+7*s);e.text.setAttribute('y',e.n.xy[1]-6*s);e.text.style.fontSize=11*s+'px';e.text.style.strokeWidth=3*s+'px';}}
  const mappedNodes=currentNodes().length;$('map-caption').textContent=`${mode==='retained'?'Retained AC topology · mathematical couplings':'Detailed original parent corridors'} · ${mappedNodes} geographic bus markers · ${visibleZones} zone labels · ${visibleFlows} interface labels · unlocated proxies 78, 79, 82 remain in the model`;
  svg.dataset.ready='true';svg.dataset.hour=String(h+1);svg.dataset.state=state();svg.dataset.mode=mode;svg.dataset.view=view;svg.dataset.geographicBusCount=String(mappedNodes);svg.dataset.interfaceLabelCount=String(visibleFlows);svg.dataset.zoneLabelCount=String(visibleZones);svg.dataset.busLabelCount=String(labelCount);svg.dataset.qualified=String(qualified());svg.dataset.units=units;
}
document.querySelectorAll('[data-view]').forEach(b=>b.onclick=()=>changeView(b.dataset.view));
$('zoom-in').onclick=()=>zoom(.78);$('zoom-out').onclick=()=>zoom(1/.78);$('fit-view').onclick=fit;$('clear-selection').onclick=clearSelection;
$('network-mode').onchange=()=>{mode=$('network-mode').value;hideTip();draw();renderDetail();};
for(const id of ['show-zones','show-interfaces','show-controls','show-inactive','bus-labels'])$(id).onchange=()=>{hideTip();draw();};
$('power-units').onchange=()=>{units=$('power-units').value;updateStatus();updateFlows();renderDetail();draw();};
$('hour-slider').oninput=()=>setHour($('hour-slider').value);$('hour-index').onchange=()=>setHour($('hour-index').value);
$('hour-index').oninput=()=>{const value=$('hour-index').value;if(value!==''&&Number.isInteger(Number(value))&&Number(value)>=1&&Number(value)<=annual.hours.length)setHour(value);};
$('prev-hour').onclick=()=>setHour(h);$('next-hour').onclick=()=>setHour(h+2);
$('datetime').min=(annual.hours[0].timestamp??annual.hours[0].timestamp_utc).slice(0,16);$('datetime').max=(annual.hours.at(-1).timestamp??annual.hours.at(-1).timestamp_utc).slice(0,16);
const timestampIndex=new Map(annual.hours.map((r,i)=>[(r.timestamp??r.timestampUtc??r.timestamp_utc).slice(0,16),i+1]));$('datetime').onchange=()=>{const i=timestampIndex.get($('datetime').value);if(i)setHour(i);else syncControls();};
$('datetime').oninput=()=>{const i=timestampIndex.get($('datetime').value);if(i)setHour(i);};
$('bus-select').onchange=()=>{$('bus-select').value?selectBus(Number($('bus-select').value)):clearSelection();};
refreshBusOptions();
for(const z of defs.zones){const button=document.createElement('button');button.className='zone-button';button.dataset.zoneButton=z.id;button.innerHTML=`<span class="zone-dot" style="background:${zoneColors[z.id]}"></span><span>${z.id} · ${esc(z.display_name)}</span>`;button.onclick=()=>selectZone(z.id);$('zone-list').append(button);}
svg.addEventListener('wheel',event=>{event.preventDefault();const r=wrap.getBoundingClientRect();zoom(Math.exp(Math.sign(event.deltaY)*.14),(event.clientX-r.left)/width(),(event.clientY-r.top)/height());},{passive:false});
svg.addEventListener('pointerdown',event=>{if(event.button!==0||event.target.closest?.('.bus-group,.flow-label,.zone-label,.edge-hit'))return;drag={id:event.pointerId,x:event.clientX,y:event.clientY,box:box.slice(),distance:0};svg.setPointerCapture(event.pointerId);});
svg.addEventListener('pointermove',event=>{if(!drag||event.pointerId!==drag.id)return;const dx=event.clientX-drag.x,dy=event.clientY-drag.y;drag.distance=Math.hypot(dx,dy);if(drag.distance>4){svg.classList.add('dragging');box=[drag.box[0]-dx*drag.box[2]/width(),drag.box[1]-dy*drag.box[3]/height(),drag.box[2],drag.box[3]];hideTip();queueDraw();}});
function endDrag(event){if(!drag||event.pointerId!==drag.id)return;if(drag.distance>4)ignoreClickUntil=performance.now()+120;drag=null;svg.classList.remove('dragging');if(svg.hasPointerCapture?.(event.pointerId))svg.releasePointerCapture(event.pointerId);}
svg.addEventListener('pointerup',endDrag);svg.addEventListener('pointercancel',endDrag);
svg.addEventListener('click',event=>{if(performance.now()<ignoreClickUntil)return;if(event.target===svg||event.target.classList.contains('cartography'))clearSelection();});
svg.addEventListener('keydown',event=>{if(event.key==='Escape'){clearSelection();return;}if(event.target!==svg)return;if(['+','=','-','Home','ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key))event.preventDefault();if(event.key==='+'||event.key==='=')zoom(.8);if(event.key==='-')zoom(1.25);if(event.key==='Home')fit();const d=.08;if(event.key==='ArrowLeft')box[0]-=box[2]*d;if(event.key==='ArrowRight')box[0]+=box[2]*d;if(event.key==='ArrowUp')box[1]-=box[3]*d;if(event.key==='ArrowDown')box[1]+=box[3]*d;if(event.key.startsWith('Arrow'))draw();});
new ResizeObserver(()=>{const center=[box[0]+box[2]/2,box[1]+box[3]/2],hh=box[2]*height()/width();box=[center[0]-box[2]/2,center[1]-hh/2,box[2],hh];draw();}).observe(wrap);
$('source-commit').textContent=String(data.sourceModelCommit||annual.sourceModelCommit||'39402c2').slice(0,7);
syncControls();updateStatus();renderDetail();updateFlows();fit();
})();
