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
// Zone areas reach this far (km) from a zone's located buses; arrows are never drawn shorter than ARROW_MIN_PX on screen.
const zoneOrder='ABCDEFGHIJK',ZONE_REACH_KM=100,ARROW_MIN_PX=58;
let h=8507,view='ny',mode='retained',units='model',selection=null,hoverFlow=null,box=[0,0,100,100],lastNetworkKey='',drag=null,ignoreClickUntil=0,drawQueued=false,pressTarget=null;
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
el('path',{d:'M0,-3 L7,0 L0,3 Z',fill:'#16837a'},el('marker',{id:'transfer-arrow',viewBox:'0 -4 8 8',refX:7,refY:0,markerWidth:6,markerHeight:6,orient:'auto',markerUnits:'strokeWidth'},definitions));
const landClip=el('clipPath',{id:'land-clip'},definitions);
const basemap=el('g',{'data-layer':'basemap'},svg);let zoneAreasLayer=null;
for(const layer of geo.basemap){if(layer.kind==='land')el('path',{d:layer.path,'fill-rule':'evenodd'},landClip);else if(!zoneAreasLayer)zoneAreasLayer=el('g',{'data-layer':'zone-areas','clip-path':'url(#land-clip)','aria-hidden':'true'},basemap);el('path',{d:layer.path,class:layer.kind+' cartography','fill-rule':'evenodd'},basemap);}
zoneAreasLayer??=el('g',{'data-layer':'zone-areas','clip-path':'url(#land-clip)','aria-hidden':'true'},basemap);
const edgesLayer=el('g',{'data-layer':'network'},svg),interfacesLayer=el('g',{'data-layer':'interfaces'},svg),nodesLayer=el('g',{'data-layer':'buses'},svg);
const cutsLayer=el('g',{'clip-path':'url(#ny-mask)'},el('g',{'data-layer':'interface-cuts','clip-path':'url(#land-clip)'},interfacesLayer)),arrowsLayer=el('g',{'data-layer':'interface-arrows'},interfacesLayer);
const busLabelsLayer=el('g',{'data-layer':'bus-labels'},svg),zonesLayer=el('g',{'data-layer':'zones'},svg),flowLabelsLayer=el('g',{'data-layer':'flow-labels'},svg);
const pv20Group=el('g',{'data-boundary':'pv20',class:'boundary-label',role:'button',tabindex:0},flowLabelsLayer);
const pv20Rect=el('rect',{fill:'#edf8f5',stroke:'#16837a',rx:4},pv20Group),pv20Text=el('text',{fill:'#11695f'},pv20Group);
activate(pv20Group,()=>selectBus(49));
bindTip(pv20Group,()=>`<b>PV20 northern boundary proxy</b><br>Sand Bar meter assigned to Plattsburgh, Zone D.<br>South Hero net load and intervening losses are unresolved.<br>Positive = import into New York; ${unit()}.`);
function members(def){return def.members_by_state?.[state()]||[];}
function memberParents(){return selection?.type==='interface'?new Set(members(defs.interfaces[selection.index]).map(m=>Number(m.parent_id))):new Set();}
function lineGeometry(a,b,lane=0){const dx=b[0]-a[0],dy=b[1]-a[1],len=Math.hypot(dx,dy),s=scale();if(len<1e-6)return `M${a[0]},${a[1]} C${a[0]+18*s},${a[1]-24*s} ${a[0]+36*s},${a[1]+24*s} ${a[0]},${a[1]}`;const bend=lane*6*s;return `M${a[0]},${a[1]} Q${(a[0]+b[0])/2-dy/len*bend},${(a[1]+b[1])/2+dx/len*bend} ${b[0]},${b[1]}`;}
// Interface arrows keep the cut midpoint and direction; short cuts are lengthened symmetrically to stay legible.
function arrowSpan(a,b){const dx=b[0]-a[0],dy=b[1]-a[1],len=Math.hypot(dx,dy),min=ARROW_MIN_PX*scale();if(len<1e-9||len>=min)return [a,b];const mx=(a[0]+b[0])/2,my=(a[1]+b[1])/2,half=min/2;return [[mx-dx/len*half,my-dy/len*half],[mx+dx/len*half,my+dy/len*half]];}
function arrowShape(a,b,w){const s=scale(),[t,p]=arrowSpan(a,b),dx=p[0]-t[0],dy=p[1]-t[1],len=Math.hypot(dx,dy)||1,ux=dx/len,uy=dy/len,headLen=Math.min(Math.max(11,w*1.9)*s,len*.45),half=Math.max(6.5,w*1.3)*s,n=[p[0]-ux*headLen,p[1]-uy*headLen];return {tail:t,tip:p,neck:n,shaft:`M${t[0]},${t[1]} L${n[0]},${n[1]}`,head:`M${p[0]},${p[1]} L${n[0]-uy*half},${n[1]+ux*half} L${n[0]+uy*half},${n[1]-ux*half} Z`};}
// Width follows the square root of |flow| in model MW, so a unit switch never changes it.
const flowScaleMW=annual.interfaceFlowsModelMW.reduce((m,row)=>row.reduce((n,v)=>finite(v)?Math.max(n,Math.abs(v)):n,m),1);
function arrowWidth(i){const v=annual.interfaceFlowsModelMW[h]?.[i];return finite(v)?3+9*Math.sqrt(Math.min(Math.abs(v)/flowScaleMW,1)):0;}
function zoneRange(list){const ids=[...list].sort((a,b)=>zoneOrder.indexOf(a)-zoneOrder.indexOf(b)),runs=[];for(const id of ids){const last=runs.at(-1);if(last&&zoneOrder.indexOf(id)===zoneOrder.indexOf(last.at(-1))+1)last.push(id);else runs.push([id]);}return runs.map(r=>r.length>2?r[0]+'–'+r.at(-1):r.join(',')).join(',');}
function route(def){return zoneRange(def.source_zones||[])+' → '+zoneRange(def.target_zones||[]);}
// Schematic zone areas: nearest-bus (Voronoi) cells of every located model bus, limited to ZONE_REACH_KM and clipped to land and the New York display mask.
// Neighbouring-system buses bound the NY cells but are not drawn. These are not official NYISO zone boundaries.
function zoneTerritories(){
  const seeds=[],seen=new Set(),R=ZONE_REACH_KM,ring=48,areas=new Map(defs.zones.map(z=>[z.id,''])),borders=[];
  for(const n of geo.nodes){if(!n.xy)continue;const key=n.xy.map(v=>Number(v).toFixed(3)).join();if(seen.has(key))continue;seen.add(key);seeds.push({x:Number(n.xy[0]),y:Number(n.xy[1]),zone:n.zone});}
  seeds.forEach((s,i)=>{if(!zones.has(s.zone))return;let poly=Array.from({length:ring},(_,k)=>({x:s.x+R*Math.cos(k/ring*2*Math.PI),y:s.y+R*Math.sin(k/ring*2*Math.PI),tag:-1}));
    seeds.forEach((t,j)=>{const dx=t.x-s.x,dy=t.y-s.y;if(j===i||poly.length<3||dx*dx+dy*dy>=4*R*R)return;const mx=(s.x+t.x)/2,my=(s.y+t.y)/2,side=p=>(p.x-mx)*dx+(p.y-my)*dy,next=[];
      poly.forEach((E,k)=>{const S=poly[(k||poly.length)-1],fs=side(S),fe=side(E),cut=()=>({x:S.x+(E.x-S.x)*fs/(fs-fe),y:S.y+(E.y-S.y)*fs/(fs-fe)});if(fe<=0){if(fs>0)next.push({...cut(),tag:S.tag});next.push(E);}else if(fs<=0)next.push({...cut(),tag:j});});poly=next;});
    if(poly.length<3)return;const xy=p=>p.x.toFixed(2)+','+p.y.toFixed(2);areas.set(s.zone,areas.get(s.zone)+'M'+poly.map(xy).join('L')+'Z');
    poly.forEach((p,k)=>{const other=seeds[p.tag]?.zone;if(p.tag>i&&zones.has(other)&&other!==s.zone)borders.push({pair:[s.zone,other],d:'M'+xy(p)+'L'+xy(poly[(k+1)%poly.length])});});});
  return {areas,borders,seedCount:seeds.length};
}
const territory=zoneTerritories();
const zoneAreasClip=el('g',{'clip-path':'url(#ny-mask)'},zoneAreasLayer),zoneBorders=el('path',{class:'zone-borders',d:territory.borders.map(b=>b.d).join('')},zoneAreasClip);
const zoneAreas=new Map(defs.zones.map(z=>{const area=el('path',{class:'zone-area','data-zone-area':z.id,fill:zoneColors[z.id],stroke:zoneColors[z.id],d:territory.areas.get(z.id)||''},zoneAreasClip);return [z.id,area];}));
zoneAreasClip.append(zoneBorders);
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
for(const z of defs.zones){const leader=el('path',{fill:'none',stroke:zoneColors[z.id],'stroke-width':1,'stroke-opacity':.75,'vector-effect':'non-scaling-stroke',class:'zone-leader'},zonesLayer);const group=el('g',{class:'zone-label',role:'button',tabindex:0,'data-zone':z.id,'aria-label':`Zone ${z.id}, ${z.display_name}`},zonesLayer);const rect=el('rect',{rx:11},group);el('circle',{cx:11,cy:11,r:8.5,fill:zoneColors[z.id]},group);const letter=el('text',{class:'zone-letter',x:11,y:15},group),text=el('text',{class:'zone-name',x:24,y:15},group);letter.textContent=z.id;text.textContent=z.display_name;zoneElements.push({group,rect,text,leader,z});activate(group,()=>selectZone(z.id));bindTip(group,()=>`<b>Zone ${z.id} · ${esc(z.display_name)}</b><br>Model accounting group<br>Select for hourly load, loss and net native generation`);
  group.addEventListener('pointerenter',()=>zoneAreas.get(z.id).classList.add('hover'));group.addEventListener('pointerleave',()=>zoneAreas.get(z.id).classList.remove('hover'));}
for(let i=0;i<defs.interfaces.length;i++){
  const def=defs.interfaces[i],sides=[new Set(def.source_zones||[]),new Set(def.target_zones||[])];
  const cutD=territory.borders.filter(b=>sides[0].has(b.pair[0])&&sides[1].has(b.pair[1])||sides[1].has(b.pair[0])&&sides[0].has(b.pair[1])).map(b=>b.d).join('');
  const cutCasing=el('path',{class:'interface-cut-casing','data-interface-cut':def.id,d:cutD},cutsLayer),cut=el('path',{class:'interface-cut',d:cutD},cutsLayer);
  const leader=el('path',{class:'flow-leader'},arrowsLayer),arrow=el('g',{class:'flow-arrow','data-flow-arrow':def.id},arrowsLayer);
  const casing=el('path',{class:'interface-casing'},arrow),casingHead=el('path',{class:'interface-casing-head'},arrow),line=el('path',{class:'interface-line','data-interface-arrow':def.id},arrow),head=el('path',{class:'interface-head'},arrow),pulse=el('path',{class:'interface-pulse'},arrow);
  const group=el('g',{class:'flow-label',role:'button',tabindex:0,'data-interface':def.id,'aria-label':def.name},flowLabelsLayer);
  const rect=el('rect',{rx:4},group),accent=el('rect',{class:'flow-accent',width:4},group),name=el('text',{},group),routeText=el('text',{class:'flow-route'},group),value=el('text',{class:'flow-number'},group);name.textContent=def.name;routeText.textContent=route(def);
  interfaceElements.push({group,rect,accent,name,routeText,value,line,casing,casingHead,head,pulse,arrow,cut,cutCasing,leader,def,index:i});
  const tipText=()=>`<b>${esc(def.name)}</b> · ${esc(route(def))}<br>${fmt(flow(i))} ${unit()}<br>${members(def).length} signed parent records · model diagnostic cut`;
  for(const target of [group,arrow]){activate(target,()=>selectInterface(i));bindTip(target,tipText);target.addEventListener('pointerenter',()=>{hoverFlow=i;queueDraw();});target.addEventListener('pointerleave',()=>{if(hoverFlow===i){hoverFlow=null;queueDraw();}});}
}
function direction(i){const v=flow(i);return !finite(v)?'unavailable':v<0?'reverse':v>0?'positive':'zero';}
function setHour(index){if(!Number.isInteger(Number(index))||Number(index)<1||Number(index)>annual.hours.length){syncControls();return;}h=Number(index)-1;if(selection?.type==='bus'&&!present(nodes.get(selection.id)))selection=null;hideTip();syncControls();updateStatus();updateFlows();renderDetail();draw();}
function syncControls(){$('hour-index').value=String(h+1);$('hour-slider').value=String(h+1);$('datetime').value=timestamp().slice(0,16);$('prev-hour').disabled=h===0;$('next-hour').disabled=h===annual.hours.length-1;}
function updateStatus(){
  const success=qualified(),source=sourceQualified();$('hour-status').className=success?'qualified':'failed';
  $('hour-status').textContent=success?'AC equations and loss balance passed · voltage and generator checks '+((hour().operatingQualified??hour().operating_qualified)?'passed':'failed'):source?'No qualified AC flow · '+(hour().status||'solver rejected this hour'):'Source-excluded hour · AC flows unavailable';
  const s=activeState();$('topology-status').textContent=`${state().replaceAll('_',' ')} · ${s.detailedBusCount} detailed buses · ${s.runtimeBranchCount} branch rows`;
  $('power-note').textContent=units==='model'?'Synthetic electrical power base':'Aggregate model power ÷ γ; no current rescaling';
  document.querySelectorAll('.unit-label').forEach(x=>x.textContent=unit());
}
function updateFlows(){
  renderNorthern();
  const list=$('flow-list');list.replaceChildren();defs.interfaces.forEach((def,i)=>{const row=document.createElement('button');row.className='flow-row'+(selection?.type==='interface'&&selection.index===i?' selected':'');row.dataset.flowId=def.id;row.dataset.flowValue=finite(flow(i))?String(flow(i)):'';row.dataset.direction=direction(i);row.style.setProperty('--magnitude',`${(Math.sqrt(Math.min(Math.abs(annual.interfaceFlowsModelMW[h]?.[i]??0)/flowScaleMW,1))*100).toFixed(1)}%`);row.innerHTML=`<span class="flow-name">${esc(def.name)}<small>${esc(route(def))}</small></span><span class="value">${fmt(flow(i))}</span><span class="direction">${direction(i)==='positive'?'→':direction(i)==='reverse'?'←':direction(i)==='zero'?'·':'—'}</span>`;row.setAttribute('aria-label',`${def.name}, zones ${route(def)}: ${fmt(flow(i))} ${unit()}, ${direction(i)} direction`);row.onclick=()=>selectInterface(i);row.onpointerenter=()=>{hoverFlow=i;draw();};row.onpointerleave=()=>{if(hoverFlow===i){hoverFlow=null;draw();}};list.append(row);});drawChart();
}
function renderNorthern(){
  const values=annual.northernInputsModelMW?.[h]||[null,null,null],names=annual.northernInputNames||[];
  $('northern-inputs').innerHTML=`<h3>North Country inputs · ${esc(unit())}</h3>${pairs(values.map((v,i)=>[names[i]||String(i),fmt(power(v))+' MW']))}<details><summary>PV20 source and scope</summary><p>Sand Bar PAR metering is represented at Plattsburgh in Zone D. Positive flow imports into New York; negative flow exports. South Hero net load and line losses are unresolved. Total New England interchange is preserved.</p><p>St. Lawrence matches reported monthly energy; its hourly output is reconstructed.</p></details>`;
  $('northern-inputs').dataset.pv20Value=finite(values[2])?String(power(values[2])):'';
}
function drawPV20(){
  const pn=nodes.get(49),pv=annual.northernInputsModelMW?.[h]?.[2],s=scale();
  const pointVisible=pn?.xy&&pn.xy[0]>=box[0]&&pn.xy[0]<=box[0]+box[2]&&pn.xy[1]>=box[1]&&pn.xy[1]<=box[1]+box[3];
  const visible=$('show-controls').checked&&pointVisible&&finite(pv);
  pv20Group.style.display=visible?'':'none';
  if(!visible)return;
  const label='PV20 proxy '+(pv<0?'export ':'import ')+fmt(Math.abs(power(pv)))+' MW';
  const labelWidth=(label.length*6.1+12)*s;
  const x=Math.max(box[0]+6*s,Math.min(pn.xy[0]+12*s,box[0]+box[2]-labelWidth-6*s));
  const y=Math.max(box[1]+6*s,Math.min(pn.xy[1]+20*s,box[1]+box[3]-26*s));
  pv20Text.textContent=label;pv20Text.setAttribute('x',x+6*s);pv20Text.setAttribute('y',y+14*s);
  pv20Text.style.fontSize=11*s+'px';pv20Rect.setAttribute('x',x);pv20Rect.setAttribute('y',y);
  pv20Rect.setAttribute('width',labelWidth);pv20Rect.setAttribute('height',20*s);
  pv20Rect.style.strokeWidth=s+'px';pv20Group.dataset.signedValue=String(power(pv));
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
    detail.innerHTML=`<h3>Zone ${z.id} · ${esc(z.display_name)}</h3>${badges(['Model accounting zone',unit()])}${pairs(rows.map(([name,value])=>[name,fmt(power(value))+' MW']))}<p>Gross load and native generation are supplied source inputs. Delivered load and assigned loss require a qualified AC solution. HQ and other external equivalents are excluded from native generation.</p><p>The shaded area and label are derived from model bus locations; they do not trace an official NYISO zone boundary.</p>`;return;
  }
  if(selection.type==='interface'){
    const def=defs.interfaces[selection.index],list=members(def);detail.innerHTML=`<h3>${esc(def.name)}</h3>${badges([unit(),direction(selection.index)==='reverse'?'Reverse total':direction(selection.index)==='positive'?'Positive total':direction(selection.index)==='zero'?'Zero total':'Flow unavailable'])}${pairs([['Signed interface flow',fmt(flow(selection.index))+' MW'],['Positive orientation',(def.source_zones||[]).join(', ')+' → '+(def.target_zones||[]).join(', ')],['Signed members',String(list.length)]])}<p>Sum of each frozen member coefficient times its original corridor from-terminal P. A negative aggregate reverses the arrow. The dashed map line marks where the schematic areas of zones ${esc(zoneRange(def.source_zones||[]))} meet zones ${esc(zoneRange(def.target_zones||[]))}. Physical NYISO meter membership is unverified.</p><div class="member-list">${list.map(m=>`<button data-parent-member="${m.parent_id}">${m.coefficient>0?'+':'−'} parent ${m.parent_id} · ${esc(busName(m.from_bus))} → ${esc(busName(m.to_bus))}</button>`).join('')}</div>`;
    if(def.name==='MOSES SOUTH')detail.insertAdjacentHTML('beforeend','<p><strong>Boundary source check:</strong> NYISO documents verify the seven physical members and the North Country boundary, including the separate PV20 tie. This model includes PV20 through Sand Bar metering at Plattsburgh. Exact meter equivalence, South Hero net load and intervening losses remain unresolved.</p>');
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
  if(item.compensationPlacement)detail.innerHTML+='<p>'+esc(item.compensationPlacement)+' Total fixed reactor rating: '+Number(r?.reactorNominalMVAr).toFixed(3)+' MVAr at 1 pu, over '+(r?.reactorBusIds?.length??0)+' modeled buses.</p>';
}
function draw(){
  drawPV20();
  buildNetwork();svg.setAttribute('viewBox',box.join(' '));const s=scale(),highlight=memberParents();
  for(const e of edgeElements){const path=lineGeometry(e.a.xy,e.b.xy,e.lane);e.line.setAttribute('d',path);e.hit.setAttribute('d',path);
    let focus=!selection||selection.type==='bus'&&(Number(e.item.a)===selection.id||Number(e.item.b)===selection.id)||selection.type==='zone'&&(e.a.zone===selection.id||e.b.zone===selection.id)||selection.type==='interface'&&e.item.type==='parent'&&highlight.has(Number(e.item.id))||selection.item&&selection.type===e.item.type&&(selection.item.id??selection.item.key)===(e.item.id??e.item.key);
    e.line.style.opacity=focus?'1':'.20';e.line.setAttribute('stroke-width',focus&&selection?2.8:e.item.type==='coupling'?1:1.15);
    if(e.item.type==='transfer'){const v=annual.fixedTransferFlowsModelMW?.[h]?.[Number(e.item.row??e.item.id)-1];if(finite(v)&&v!==0){e.line.setAttribute('d',Number(v)<0?lineGeometry(e.b.xy,e.a.xy,-e.lane):path);e.line.setAttribute('marker-end','url(#transfer-arrow)');}else e.line.removeAttribute('marker-end');}
  }
  for(const e of nodeElements){const selected=selection?.type==='bus'&&selection.id===Number(e.n.id),r=(selected?6:e.n.retained?3.4:2.2)*s;e.hit.setAttribute('r',Math.max(9*s,r));e.mark.setAttribute('fill',selected?'#143d53':color(e.n));if(e.mark.tagName.toLowerCase()==='rect'){e.mark.setAttribute('x',e.n.xy[0]-r);e.mark.setAttribute('y',e.n.xy[1]-r);e.mark.setAttribute('width',2*r);e.mark.setAttribute('height',2*r);}else{e.mark.setAttribute('cx',e.n.xy[0]);e.mark.setAttribute('cy',e.n.xy[1]);e.mark.setAttribute('r',r);}e.group.style.opacity=selection?.type==='zone'&&e.n.zone!==selection.id?'.28':'1';}
  const occupied=[],flowsOn=$('show-interfaces').checked,zonesOn=$('show-zones').checked,focusFlow=selection?.type==='interface'?selection.index:hoverFlow,bottomReserve=Math.max(54,(document.querySelector('.map-caption')?.offsetHeight||0)+18);
  function place(xy,w,hh,seed=0,preferred=[],maxRadius=Infinity){const p=screen(xy);if(p[0]<-35||p[1]<-35||p[0]>width()+35||p[1]>height()+35)return null;const offsets=[[0,0],[0,-25],[0,25],[35,0],[-35,0]];for(let radius=50;radius<=220;radius+=25)for(let angle=0;angle<8;angle++)offsets.push([radius*Math.cos(angle*Math.PI/4),radius*Math.sin(angle*Math.PI/4)]);const order=preferred.concat(offsets.map((_,j)=>offsets[(j+seed)%offsets.length]).filter(o=>Math.hypot(o[0],o[1])<=maxRadius));for(const o of order){let x=Math.max(8,Math.min(p[0]-w/2+o[0],width()-w-8)),y=Math.max(53,Math.min(p[1]-hh/2+o[1],height()-hh-bottomReserve));if(!occupied.some(b=>x<b[0]+b[2]+4&&x+w+4>b[0]&&y<b[1]+b[3]+4&&y+hh+4>b[1])){occupied.push([x,y,w,hh]);return [x,y];}}return null;}
  // Zone letter badges claim space beside their zone first, interface labels next, then badges grow to full names where room remains.
  function placeZone(e,maxRadius,compact){const xy=zoneXY(e.z.id);if(!zonesOn||!xy)return null;const w=compact?22:Math.round(e.z.display_name.length*7+34),hh=22,pos=place(xy,w,hh,0,[[w/2+9,0],[-w/2-9,0],[0,-hh/2-9],[0,hh/2+9]],maxRadius);if(!pos)return null;
    const p=pixel(pos[0],pos[1]);e.text.style.display=compact?'none':'';e.group.style.display='';e.group.setAttribute('transform',`translate(${p[0]} ${p[1]}) scale(${s})`);e.group.setAttribute('class','zone-label'+(selection?.type==='zone'&&selection.id===e.z.id?' active':''));e.rect.setAttribute('width',w);e.rect.setAttribute('height',hh);e.leader.style.display='none';
    const anchor=screen(xy),label=[Math.max(pos[0],Math.min(anchor[0],pos[0]+w)),Math.max(pos[1],Math.min(anchor[1],pos[1]+hh))];if(Math.hypot(anchor[0]-label[0],anchor[1]-label[1])>14){const end=pixel(label[0],label[1]);e.leader.setAttribute('d',`M${xy[0]},${xy[1]} L${end[0]},${end[1]}`);e.leader.style.display='';}return occupied.length-1;}
  const sides=focusFlow!=null?new Set([...(defs.interfaces[focusFlow].source_zones||[]),...(defs.interfaces[focusFlow].target_zones||[])]):null;zoneAreasLayer.style.display=zonesOn?'':'none';
  for(const [id,area]of zoneAreas){const active=selection?.type==='zone'&&selection.id===id,dim=selection?.type==='zone'?!active:Boolean(sides&&!sides.has(id));area.setAttribute('class','zone-area'+(active?' active':dim?' dim':'')+(area.classList?.contains('hover')?' hover':''));}
  for(const e of interfaceElements){const orientation=e.def.positive_orientation||{},from=orientation.source_xy,to=orientation.target_xy,enabled=flowsOn,v=flow(e.index),w=arrowWidth(e.index);
    e.line.style.display=enabled&&from&&to&&finite(v)&&v!==0?'':'none';e.arrow.style.display=e.line.style.display;e.shape=null;
    if(from&&to&&finite(v)&&v!==0){const shape=arrowShape(v<0?to:from,v<0?from:to,w);e.shape=shape;for(const part of [e.line,e.casing,e.pulse])part.setAttribute('d',shape.shaft);for(const part of [e.head,e.casingHead])part.setAttribute('d',shape.head);
      e.line.setAttribute('stroke-width',w);e.casing.setAttribute('stroke-width',w+4);e.pulse.setAttribute('stroke-width',Math.max(1.4,w*.32));e.line.dataset.direction=direction(e.index);}
    e.arrow.setAttribute('class','flow-arrow'+(focusFlow===e.index?' focus':focusFlow!=null?' dim':''));
    const cutShown=enabled&&focusFlow===e.index&&Boolean(e.cut.getAttribute('d'));e.cut.style.display=e.cutCasing.style.display=cutShown?'':'none';}
  // Reserve the drawn arrows so labels do not cover them.
  for(const e of interfaceElements)if(e.shape&&e.arrow.style.display!=='none'){const a=screen(e.shape.tail),b=screen(e.shape.tip),steps=Math.max(1,Math.ceil(Math.hypot(b[0]-a[0],b[1]-a[1])/14)),size=arrowWidth(e.index)+6;for(let k=0;k<=steps;k++)occupied.push([a[0]+(b[0]-a[0])*k/steps-size/2,a[1]+(b[1]-a[1])*k/steps-size/2,size,size]);}
  for(const e of zoneElements){e.group.style.display='none';e.leader.style.display='none';e.slot=placeZone(e,40,true);}
  let visibleFlows=0;
  for(const e of interfaceElements){const orientation=e.def.positive_orientation||{},from=orientation.source_xy,to=orientation.target_xy,anchor=orientation.label_anchor_xy,xy=anchor||from&&to&&[(from[0]+to[0])/2,(from[1]+to[1])/2],v=flow(e.index),aw=arrowWidth(e.index);
    const compact=width()<450,w=compact?Math.round(Math.max(84,e.def.name.length*6.2+18)):Math.round(Math.max(128,e.def.name.length*6.9+route(e.def).length*5.6+34)),hh=compact?32:38;let preferred=[];
    if(e.shape){const a=screen(e.shape.tail),b=screen(e.shape.tip),len=Math.hypot(b[0]-a[0],b[1]-a[1])||1,nx=-(b[1]-a[1])/len,ny=(b[0]-a[0])/len,d=Math.abs(nx)*w/2+Math.abs(ny)*hh/2+aw/2+8;preferred=[[nx*d,ny*d],[-nx*d,-ny*d]];}
    const pos=flowsOn&&xy?place(xy,w,hh,e.index%3,preferred):null;e.group.style.display=pos?'':'none';e.leader.style.display='none';if(!pos)continue;visibleFlows++;const p=pixel(pos[0],pos[1]);e.group.setAttribute('transform',`translate(${p[0]} ${p[1]}) scale(${s})`);e.group.setAttribute('class','flow-label'+(compact?' compact':'')+(focusFlow===e.index?' focus':''));
    e.rect.setAttribute('width',w);e.rect.setAttribute('height',hh);e.accent.setAttribute('height',hh);e.name.setAttribute('x',compact?9:11);e.name.setAttribute('y',compact?12:14);e.routeText.setAttribute('x',w-8);e.routeText.setAttribute('y',14);e.routeText.style.display=compact?'none':'';e.value.setAttribute('x',compact?9:11);e.value.setAttribute('y',compact?26:31);
    e.value.textContent=`${fmt(v)} MW ${direction(e.index)==='reverse'?'←':direction(e.index)==='positive'?'→':''}`;e.group.dataset.flowValue=finite(v)?String(v):'';e.group.dataset.direction=direction(e.index);e.group.setAttribute('aria-label',`${e.def.name}, zones ${route(e.def)}, ${fmt(v)} ${unit()}, ${direction(e.index)} direction`);
    const m=screen(xy),cx=Math.max(pos[0],Math.min(m[0],pos[0]+w)),cy=Math.max(pos[1],Math.min(m[1],pos[1]+hh));if(e.shape&&Math.hypot(cx-m[0],cy-m[1])>aw/2+14){const q=pixel(cx,cy);e.leader.setAttribute('d',`M${xy[0]},${xy[1]} L${q[0]},${q[1]}`);e.leader.style.display='';}}
  for(const e of zoneElements){if(e.slot==null||width()<450)continue;const badge=occupied[e.slot];occupied[e.slot]=[-1e9,-1e9,0,0];const slot=placeZone(e,40,false);if(slot==null)occupied[e.slot]=badge;else e.slot=slot;}
  for(const e of zoneElements)if(e.slot==null)e.slot=placeZone(e,Infinity,true);
  const visibleZones=zoneElements.filter(e=>e.slot!=null).length;
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
svg.addEventListener('pointerdown',event=>{pressTarget=event.target;if(event.button!==0||event.target.closest?.('.bus-group,.flow-label,.boundary-label,.flow-arrow,.zone-label,.edge-hit'))return;drag={id:event.pointerId,x:event.clientX,y:event.clientY,box:box.slice(),distance:0};svg.setPointerCapture(event.pointerId);});
svg.addEventListener('pointermove',event=>{if(!drag||event.pointerId!==drag.id)return;const dx=event.clientX-drag.x,dy=event.clientY-drag.y;drag.distance=Math.hypot(dx,dy);if(drag.distance>4){svg.classList.add('dragging');box=[drag.box[0]-dx*drag.box[2]/width(),drag.box[1]-dy*drag.box[3]/height(),drag.box[2],drag.box[3]];hideTip();queueDraw();}});
function endDrag(event){if(!drag||event.pointerId!==drag.id)return;if(drag.distance>4)ignoreClickUntil=performance.now()+120;drag=null;svg.classList.remove('dragging');if(svg.hasPointerCapture?.(event.pointerId))svg.releasePointerCapture(event.pointerId);}
svg.addEventListener('pointerup',endDrag);svg.addEventListener('pointercancel',endDrag);
// Pointer capture retargets a background click to the svg, so the pressed zone area is remembered from pointerdown.
svg.addEventListener('click',event=>{if(performance.now()<ignoreClickUntil)return;const area=event.target.closest?.('.zone-area')||(event.target===svg?pressTarget?.closest?.('.zone-area'):null);if(area){selectZone(area.dataset.zoneArea);return;}if(event.target===svg||event.target.classList.contains('cartography'))clearSelection();});
svg.addEventListener('keydown',event=>{if(event.key==='Escape'){clearSelection();return;}if(event.target!==svg)return;if(['+','=','-','Home','ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key))event.preventDefault();if(event.key==='+'||event.key==='=')zoom(.8);if(event.key==='-')zoom(1.25);if(event.key==='Home')fit();const d=.08;if(event.key==='ArrowLeft')box[0]-=box[2]*d;if(event.key==='ArrowRight')box[0]+=box[2]*d;if(event.key==='ArrowUp')box[1]-=box[3]*d;if(event.key==='ArrowDown')box[1]+=box[3]*d;if(event.key.startsWith('Arrow'))draw();});
new ResizeObserver(()=>{const center=[box[0]+box[2]/2,box[1]+box[3]/2],hh=box[2]*height()/width();box=[center[0]-box[2]/2,center[1]-hh/2,box[2],hh];draw();}).observe(wrap);
$('source-commit').textContent=String(annual.metadata.mosesRepairCandidateSha256).slice(0,12);
syncControls();updateStatus();renderDetail();updateFlows();fit();
})();
