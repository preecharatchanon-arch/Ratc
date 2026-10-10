const $=(selector,root=document)=>root.querySelector(selector);
const $$=(selector,root=document)=>[...root.querySelectorAll(selector)];
const truckId=Number(location.pathname.split('/').filter(Boolean).pop());
const withToken=path=>path;
const tr=(_legacy,en)=>en;
const esc=value=>String(value??'').replace(/[&<>'"]/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
const formatKm=meters=>`${((Number(meters)||0)/1000).toFixed(1)} km`;
const formatMinutes=seconds=>`${Math.max(0,Math.round((Number(seconds)||0)/60))} min`;
const formatNumber=value=>new Intl.NumberFormat('en-US',{maximumFractionDigits:1}).format(Number(value)||0);
const formatClock=value=>{if(value==null||!Number.isFinite(Number(value)))return'—';const seconds=Math.max(0,Math.round(Number(value))),hours=Math.floor(seconds/3600)%24,minutes=Math.floor((seconds%3600)/60);return`${String(hours).padStart(2,'0')}:${String(minutes).padStart(2,'0')}`;};

let LANG='en';
let latestVersion=null;
let route=null;
let routeState={};
let optimizerJob=null;
let map=null;
let routeLayer=null;
let stopLayer=null;
let selectedRoadLayer=null;
let selectableRoadLayer=null;
let selectedEdge=null;
let reportMode=false;
let currentTileLayer=null;
let currentMapStyle='street';
let pollTimer=null;
let roadReloadTimer=null;
let roadsRequestSerial=0;
let latestRouteRequestInFlight=false;
let reportReturnFocus=null;

function currentPlanStatus(){
  const hasRoute=!!route&&!!latestVersion?.id;
  const source=String(routeState.solution_source||latestVersion?.payload?.solution_source||'');
  const stateVersion=Number(routeState.route_version||0);
  const displayedVersion=Number(latestVersion?.id||0);
  const generationMismatch=hasRoute&&(!stateVersion||stateVersion!==displayedVersion);
  const stale=hasRoute&&(routeState.stale!==false||generationMismatch);
  const completed=!!(routeState.optimization_completed||routeState.optimization_checked_at||source==='cpp_optimizer');
  if(stale)return{phase:'stale',icon:'!',badge:'UPDATE NEEDED',completed:false,title:'Plan no longer matches dispatch inputs',detail:'Work points, roads, or operating settings changed. Wait for an updated plan before navigation.'};
  if(optimizerJob&&hasRoute)return{phase:'running',icon:'◆',badge:'OPTIMIZING',completed:false,title:'Optimizer is improving this plan',detail:`Route v${latestVersion.id} remains the published initial plan while search continues.`};
  if(!hasRoute)return{phase:'empty',icon:'◇',badge:'NO ASSIGNMENT',completed:false,title:'No manifest is assigned to this truck',detail:'Check the truck number or contact dispatch.'};
  if(!completed)return{phase:'prepared',icon:'△',badge:'INITIAL PLAN',completed:false,title:'Constraint-valid initial plan',detail:'This published sequence is available while the optimizer has not yet produced a completed result.'};
  if(source==='cpp_optimizer')return{phase:'optimized',icon:'✓',badge:'OPTIMIZED',completed:true,title:'Validated fleet plan ready',detail:'The optimizer completed and FleetRoute independently validated the published result.'};
  return{phase:'reviewed',icon:'✓',badge:'READY',completed:true,title:'Validated fleet plan ready',detail:'Optimization completed; the existing feasible plan was retained because no better valid result was published.'};
}
function renderPlanState(){
  const status=currentPlanStatus(),element=$('#driverPlanState');if(!element)return;
  element.className=`driver-plan-state ${status.phase}`;
  $('.plan-state-icon',element).textContent=status.icon;
  $('b',element).textContent=status.title;
  $('p',element).textContent=status.detail;
  $('em',element).textContent=status.badge;
  document.body.dataset.planPhase=status.phase;
  const mapTitle=$('#mapPlanStateTitle');if(mapTitle)mapTitle.textContent=status.completed?tr('','Fleet plan ready'):status.phase==='prepared'||status.phase==='running'?tr('','Initial plan'):tr('','Current fleet plan');
}

function navigationAvailable(){return !!route&&currentPlanStatus().phase!=='stale';}

const DRIVER_FALLBACK_TILE='data:image/svg+xml;charset=UTF-8,'+encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256"><rect width="256" height="256" fill="#eaf0f4"/><path d="M0 64H256M0 128H256M0 192H256M64 0V256M128 0V256M192 0V256" stroke="#d5dee6" fill="none"/></svg>`);
const TILE_STYLES={
  street:{url:'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',options:{maxZoom:20,attribution:'&copy; OpenStreetMap contributors',errorTileUrl:DRIVER_FALLBACK_TILE}},
  night:{url:'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',options:{maxZoom:20,attribution:'&copy; OpenStreetMap contributors',errorTileUrl:DRIVER_FALLBACK_TILE}},
  terrain:{url:'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',options:{maxZoom:20,attribution:'&copy; OpenStreetMap contributors',errorTileUrl:DRIVER_FALLBACK_TILE}},
  technical:{url:'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',options:{maxZoom:20,attribution:'&copy; OpenStreetMap contributors',errorTileUrl:DRIVER_FALLBACK_TILE}},
};

async function api(path,options={}){
  const timeoutMs=Number(options.timeoutMs)||15000;
  const controller=new AbortController();
  const callerSignal=options.signal;
  const relayAbort=()=>controller.abort(callerSignal?.reason);
  if(callerSignal?.aborted)relayAbort();else if(callerSignal)callerSignal.addEventListener('abort',relayAbort,{once:true});
  const timer=setTimeout(()=>controller.abort(new DOMException('Request timeout','TimeoutError')),timeoutMs);
  const headers={'Content-Type':'application/json',...(options.headers||{})};
  const requestOptions={...options,headers,signal:controller.signal};delete requestOptions.timeoutMs;
  try{
    const response=await fetch(path,requestOptions);
    const text=await response.text();
    let data;
    try{data=text?JSON.parse(text):{};}catch{data={detail:text};}
    if(!response.ok)throw new Error(requestErrorMessage(data,response.status));
    return data;
  }catch(error){
    if(controller.signal.aborted&&!callerSignal?.aborted)throw new Error(tr(`FleetRoute  ${Math.ceil(timeoutMs/1000)} `,`FleetRoute did not respond within ${Math.ceil(timeoutMs/1000)} seconds.`));
    throw error;
  }finally{
    clearTimeout(timer);if(callerSignal)callerSignal.removeEventListener('abort',relayAbort);
  }
}

function toast(message,bad=false){
  const element=$('#toast');
  element.textContent=message;
  element.style.background=bad?'#9e3028':'#071b2d';
  element.classList.add('show');
  clearTimeout(window.__fleetToast);
  window.__fleetToast=setTimeout(()=>element.classList.remove('show'),2400);
}

function setConnected(connected,detail=''){
  const badge=$('#connectionBadge');
  badge.classList.remove('connecting');
  badge.classList.toggle('offline',!connected);
  $('span',badge).textContent=connected?tr('','Online'):tr('','Offline');
  const notice=$('#routeUpdate');
  if(!connected){
    notice.dataset.kind='connection';notice.classList.add('offline');notice.classList.remove('hidden');
    notice.innerHTML=`<b>${tr(' Dispatcher','Dispatch connection lost')}</b> · ${esc(detail||tr(' Offline  ','Tap Offline to retry. The last route remains visible.'))}`;
  }else if(notice.dataset.kind==='connection'){
    notice.classList.add('hidden');notice.classList.remove('offline');delete notice.dataset.kind;
  }
}

function applyLanguage(){LANG='en';document.documentElement.lang='en';$$('[data-en]').forEach(element=>{element.textContent=element.dataset.en||element.textContent;});renderPlanState();}

function initMap(){
  map=L.map('driverMap',{zoomControl:true,preferCanvas:true,attributionControl:true}).setView([7.8842,98.3891],12);
  routeLayer=L.layerGroup().addTo(map);
  stopLayer=L.layerGroup().addTo(map);
  selectedRoadLayer=L.layerGroup().addTo(map);
  setMapStyle('street');
  map.on('click',async event=>{
    if(!reportMode)return;
    await selectRoadByMapPoint(event.latlng.lat,event.latlng.lng);
  });
  map.on('moveend',()=>{
    if(!reportMode)return;
    clearTimeout(roadReloadTimer);
    roadReloadTimer=setTimeout(()=>loadVisibleRoads(true),220);
  });
  const mapElement=document.getElementById('driverMap');
  if(mapElement&&typeof ResizeObserver!=='undefined'){
    let frame=0;
    const observer=new ResizeObserver(()=>{cancelAnimationFrame(frame);frame=requestAnimationFrame(()=>map.invalidateSize({pan:false,animate:false}));});
    observer.observe(mapElement);
    window.__fleetDriverMapObserver=observer;
  }
}

function setMapStyle(style){
  const selected=TILE_STYLES[style]||TILE_STYLES.street;
  if(currentTileLayer)map.removeLayer(currentTileLayer);
  currentTileLayer=L.tileLayer(selected.url,selected.options).addTo(map);
  currentTileLayer.bringToBack();
  currentMapStyle=style;
  $$('[data-map-style]').forEach(button=>button.classList.toggle('active',button.dataset.mapStyle===style));
  document.body.dataset.mapStyle=style;
}

function stopName(stop,index){
  if(stop.orders?.length)return stop.orders.map(order=>order.name).join(' + ');
  if(index===0)return tr('','Start depot');
  return tr('','Return depot');
}

function allOrders(){
  return route?.stops?.reduce((total,stop)=>total+(stop.orders?.length||0),0)||0;
}

function routeLoad(){
  return route?.stops?.reduce((total,stop)=>total+(stop.kind==='customer'?(Number(stop.demand)||0):0),0)||0;
}

function routeBounds(){
  const coordinates=route?.geometry?.length?route.geometry:(route?.stops||[]).map(stop=>[stop.lat,stop.lon]);
  return coordinates.length?L.latLngBounds(coordinates):null;
}

function fitRoute(){
  const bounds=routeBounds();
  if(bounds?.isValid())map.fitBounds(bounds,{padding:[45,45],maxZoom:16});
}

function markerIcon(index,depot){
  return L.divIcon({
    className:'',
    html:`<span class="stop-marker ${depot?'depot':''}">${depot?'D':index}</span>`,
    iconSize:[30,30],
    iconAnchor:[15,15],
    tooltipAnchor:[0,-16],
  });
}

function drawCompleteRoute(fit=true){
  routeLayer.clearLayers();
  stopLayer.clearLayers();
  if(!route)return;
  const status=currentPlanStatus(),initial=!status.completed&&['prepared','running'].includes(status.phase);
  if(route.geometry?.length){
    L.polyline(route.geometry,{color:'#06131f',weight:10,opacity:.28,lineCap:'round',lineJoin:'round'}).addTo(routeLayer);
    L.polyline(route.geometry,{color:initial?'#d4942d':'#17a99c',weight:6,opacity:.98,dashArray:initial?'13 9':undefined,lineCap:'round',lineJoin:'round'}).addTo(routeLayer);
    if(!initial)L.polyline(route.geometry,{color:'#d8fffa',weight:1.5,opacity:.82,dashArray:'2 10',lineCap:'round'}).addTo(routeLayer);
  }
  route.stops.forEach((stop,index)=>{
    const depot=stop.kind==='depot';
    const marker=L.marker([stop.lat,stop.lon],{icon:markerIcon(index,depot),keyboard:true});
    marker.bindTooltip(`<div class="selected-road-popup"><b>${index}. ${esc(stopName(stop,index))}</b><br>${depot?esc(tr('Depot','Depot')):`${stop.orders?.length||0} ${esc(tr('','work items'))}`}</div>`,{direction:'top',offset:[0,-7]});
    marker.on('click',()=>{
      const timeline=$(`[data-stop-sequence="${stop.sequence}"]`);
      if(timeline)timeline.scrollIntoView({behavior:'smooth',block:'center'});
    });
    marker.addTo(stopLayer);
  });
  if(fit)fitRoute();
}

function renderRouteSummary(){
  $('#driverTitle').textContent=`Truck ${truckId}`;
  $('#versionBadge').textContent=latestVersion?.id?`PLAN v${latestVersion.id}`:'PLAN —';
  if(!route){
    $('#driverMeta').textContent='No current manifest is assigned to this truck.';
    $('#stopCount').textContent='—';
    $('#routeDistance').textContent='—';
    $('#routeTime').textContent='—';
    $('#routeLoad').textContent='—';
    $('#routeOrders').textContent='No assignment';
    $('#mapRouteMeta').textContent=latestVersion?.id?`Fleet plan v${latestVersion.id} · truck not assigned`:'No fleet plan';
    renderPlanState();
    return;
  }
  const customerStops=route.stops.filter(stop=>stop.kind==='customer').length;
  const trips=Math.max(1,Number(route.trip_count)||1);
  $('#driverMeta').textContent=`${customerStops} work stops · ${allOrders()} work items · ${trips} ${trips===1?'trip':'trips'} · ${formatKm(route.distance_m)}`;
  $('#stopCount').textContent=customerStops;
  $('#routeDistance').textContent=formatKm(route.distance_m);
  $('#routeTime').textContent=route.finish_time_s!=null?`${formatClock(route.route_start_time_s)}–${formatClock(route.finish_time_s)}`:formatMinutes(route.travel_time_s);
  $('#routeLoad').textContent=formatNumber(routeLoad());
  $('#routeOrders').textContent=`${allOrders()} work items`;
  $('#mapRouteMeta').textContent=`Truck ${truckId} · plan v${latestVersion?.id||'—'} · ${customerStops} stops`;
  renderPlanState();
}
function mapsToStop(stop){
  const params=new URLSearchParams({api:'1',destination:`${stop.lat},${stop.lon}`,travelmode:'driving',dir_action:'navigate'});
  return`https://www.google.com/maps/dir/?${params}`;
}

function routeUrl(stops){
  if(stops.length<2)return null;
  const params=new URLSearchParams({
    api:'1',
    origin:`${stops[0].lat},${stops[0].lon}`,
    destination:`${stops[stops.length-1].lat},${stops[stops.length-1].lon}`,
    travelmode:'driving',
    dir_action:'navigate',
  });
  if(stops.length>2)params.set('waypoints',stops.slice(1,-1).map(stop=>`${stop.lat},${stop.lon}`).join('|'));
  return`https://www.google.com/maps/dir/?${params}`;
}

function splitRouteStops(stops,maxWaypoints=9){
  const maxLocations=maxWaypoints+2;
  const parts=[];
  let start=0;
  while(start<stops.length-1){
    const end=Math.min(stops.length,start+maxLocations);
    parts.push(stops.slice(start,end));
    start=end-1;
  }
  return parts;
}

function routeTripGroups(stops){
  if(!stops?.length)return[];
  const groups=[];
  let current=[stops[0]];
  for(let index=1;index<stops.length;index++){
    const stop=stops[index];current.push(stop);
    if(stop.kind==='depot'&&current.length>1){groups.push(current);if(index<stops.length-1)current=[stop];}
  }
  if(current.length>1&&groups.at(-1)?.at(-1)!==current.at(-1))groups.push(current);
  return groups;
}

function renderGoogleNavigation(){
  const button=$('#openFullGoogleBtn');
  const hint=$('#googleRouteHint');
  const partsElement=$('#googleParts');
  partsElement.classList.add('hidden');
  partsElement.innerHTML='';
  button.onclick=null;
  if(!route?.stops?.length){button.disabled=true;hint.textContent='Available after this truck receives a route';return;}
  if(!navigationAvailable()){
    button.disabled=true;
    hint.textContent='Disabled until dispatch publishes an updated plan';
    return;
  }
  const trips=routeTripGroups(route.stops);
  const parts=trips.flatMap((trip,tripIndex)=>splitRouteStops(trip,9).map((stops,partIndex)=>({stops,trip:tripIndex+1,part:partIndex+1})));
  if(parts.length===1){
    const url=routeUrl(parts[0].stops);
    button.disabled=!url;
    button.onclick=url?()=>window.open(url,'_blank','noopener'):null;
    hint.textContent=`Trip 1 · ${parts[0].stops.length} locations`;
    return;
  }
  button.disabled=parts.length===0;
  button.onclick=()=>{
    partsElement.classList.toggle('hidden');
    if(!partsElement.classList.contains('hidden'))partsElement.scrollIntoView({behavior:'smooth',block:'nearest'});
  };
  hint.textContent=`${trips.length} ${trips.length===1?'trip':'trips'} · ${parts.length} navigation links`;
  partsElement.innerHTML=`<b>Depot returns remain separate trips. Each link preserves the FleetRoute stop order.</b>`+parts.map(item=>`<a target="_blank" rel="noopener" href="${routeUrl(item.stops)}">Trip ${item.trip}${parts.filter(x=>x.trip===item.trip).length>1?` · part ${item.part}`:''} · stops ${item.stops[0].sequence}→${item.stops.at(-1).sequence}</a>`).join('');
}
function renderTimeline(){
  const container=$('#routeTimeline');
  if(!route){container.innerHTML='<div class="empty-route">No manifest assigned to this truck.</div>';return;}
  const done=completedStops();
  const canNavigate=navigationAvailable();
  container.innerHTML=route.stops.map((stop,index)=>{
    const depot=stop.kind==='depot';
    const orderTags=(stop.orders||[]).slice(0,5).map(order=>`<span>${esc(order.name)}</span>`).join('');
    const more=(stop.orders?.length||0)>5?`<span>+${stop.orders.length-5}</span>`:'';
    const detail=depot?'Depot':`${stop.orders?.length||0} work items · demand ${formatNumber(stop.demand)} · service ${formatMinutes(stop.service_s)}`;
    const status=['depot','on_time','waiting','late','not_enforced'].includes(stop.time_window_status)?stop.time_window_status:'unknown';
    const planned=index===0?`Depart ${formatClock(stop.departure_s)}`:depot?`Return ${formatClock(stop.arrival_s)}`:`ETA ${formatClock(stop.arrival_s)} · service ${formatClock(stop.service_start_s)}`;
    const window=depot?'':status==='not_enforced'?'Time window not enforced':`Window ${formatClock(stop.earliest_s??stop.earliest)}–${formatClock(stop.latest_s??stop.latest)}`;
    const wait=Number(stop.waiting_s)>0?`wait ${formatMinutes(stop.waiting_s)}`:'';
    const schedule=`<div class="schedule-chips"><span class="planned-time">${esc(planned)}</span><span class="trip-chip">Trip ${Number(stop.trip_number)||1}</span>${window?`<span class="window-chip ${status}">${esc(window)}</span>`:''}${wait?`<span class="wait-chip">${esc(wait)}</span>`:''}</div>`;
    const tripBreak=depot&&index>0&&index<route.stops.length-1?'trip-return':'';
    const navigation=canNavigate?`<a class="stop-nav-link" target="_blank" rel="noopener" href="${mapsToStop(stop)}">Open map</a>`:`<span class="stop-nav-link disabled" aria-disabled="true">Await update</span>`;
    return`<article class="timeline-stop ${depot?'depot':''} ${tripBreak} ${done.has(Number(stop.sequence))?'completed':''}" data-stop-sequence="${stop.sequence}">
      <span class="timeline-number">${depot?'D':index}</span>
      <span class="timeline-rail"><i></i></span>
      <div class="timeline-content"><h3>${esc(stopName(stop,index))}</h3><p>${esc(detail)}</p>${schedule}${orderTags||more?`<div class="order-tags">${orderTags}${more}</div>`:''}</div>
      ${navigation}
    </article>`;
  }).join('');
}
const PROGRESS_MEMORY=new Map();
function progressKey(){return`fleetroute_optional_progress_v${latestVersion?.id||0}_truck_${truckId}`;}
function completedStops(){
  const key=progressKey();
  if(PROGRESS_MEMORY.has(key))return new Set(PROGRESS_MEMORY.get(key));
  try{const saved=JSON.parse(storageRead('localStorage',key,'[]'));return new Set(Array.isArray(saved)?saved.map(Number).filter(Number.isFinite):[]);}catch{return new Set();}
}
function saveCompletedStops(set){
  const key=progressKey(),values=[...set];
  PROGRESS_MEMORY.set(key,values);
  if(!storageWrite('localStorage',key,JSON.stringify(values)))toast('Progress is saved for this tab only. Browser storage is unavailable; refreshing will reset these marks.',true);
}
function resetCompletedStops(){
  PROGRESS_MEMORY.set(progressKey(),[]);
  if(!storageRemove('localStorage',progressKey()))toast('Progress was reset in this tab, but the stored copy could not be cleared.',true);
  renderOptionalProgress();
}
function nextIncomplete(){
  if(!route)return null;
  const done=completedStops();
  return route.stops.find((stop,index)=>index>0&&index<route.stops.length-1&&!done.has(Number(stop.sequence)))||route.stops.find((stop,index)=>index===route.stops.length-1&&!done.has(Number(stop.sequence)))||null;
}

function renderOptionalProgress(){
  if(!route){
    $('#progressFill').style.width='0%';
    $('#progressText').textContent='0 / 0';
    $('#nextIndex').textContent='—';
    $('#nextName').textContent='No route assigned';
    $('#nextDetail').textContent='Contact dispatch or check the truck number.';
    $('#nextStopBtn').disabled=true;$('#nextStopBtn').onclick=null;
    $('#markNextDoneBtn').disabled=true;
    return;
  }
  const trackable=route.stops.filter((_,index)=>index>0);
  const done=completedStops();
  const validDone=trackable.filter(stop=>done.has(Number(stop.sequence))).length;
  const pct=trackable.length?Math.min(100,Math.round(validDone/trackable.length*100)):0;
  $('#progressFill').style.width=`${pct}%`;
  $('#progressText').textContent=`${validDone} / ${trackable.length} · ${pct}%`;
  const next=nextIncomplete();
  const canNavigate=navigationAvailable();
  if(next){
    const index=route.stops.indexOf(next);
    $('#nextIndex').textContent=index;
    $('#nextName').textContent=stopName(next,index);
    if(next.kind==='depot')$('#nextDetail').textContent=`Return to depot · ${formatClock(next.arrival_s)}`;
    else{
      const status=String(next.time_window_status||'');
      const window=status==='not_enforced'?'':` · window ${formatClock(next.earliest_s??next.earliest)}–${formatClock(next.latest_s??next.latest)}`;
      $('#nextDetail').textContent=`ETA ${formatClock(next.arrival_s)}${window} · ${next.orders?.length||0} work items`;
    }
    $('#nextStopBtn').disabled=!canNavigate;
    $('#nextStopBtn').onclick=canNavigate?()=>window.open(mapsToStop(next),'_blank','noopener'):null;
    $('#markNextDoneBtn').disabled=!canNavigate;
  }else{
    $('#nextIndex').textContent='✓';
    $('#nextName').textContent='All route checkpoints completed';
    $('#nextDetail').textContent='Every trackable stop is marked complete on this device.';
    $('#nextStopBtn').disabled=true;$('#nextStopBtn').onclick=null;
    $('#markNextDoneBtn').disabled=true;
  }
  renderTimeline();
}
function closureGeometryFromFeature(feature){
  return(feature.geometry?.coordinates||[]).map(([lon,lat])=>[lat,lon]);
}

function edgeFromFeature(feature,latlng){
  const properties=feature.properties||{};
  return{
    road_name:properties.name||tr('','Unnamed road'),
    highway:properties.highway||'road',
    osm_u:properties.osm_u,
    osm_v:properties.osm_v,
    osm_key:properties.osm_key,
    direction_text:properties.oneway?'one-way':'two-way road record',
    geometry:closureGeometryFromFeature(feature),
    snap_lat:latlng.lat,
    snap_lon:latlng.lng,
    snap_distance_m:0,
  };
}

function roadStyle(feature){
  const highway=String(feature.properties?.highway||'');
  const major=['motorway','trunk','primary','secondary'].includes(highway);
  return{color:major?'#f6c86b':'#e8f5f3',weight:major?4:3,opacity:.7,lineCap:'round'};
}

async function loadVisibleRoads(silent=false){
  const loading=$('#roadLoading');
  const requestId=++roadsRequestSerial;
  loading.classList.remove('hidden');
  try{
    const bounds=map.getBounds();
    const params=new URLSearchParams({
      south:bounds.getSouth().toFixed(7),west:bounds.getWest().toFixed(7),
      north:bounds.getNorth().toFixed(7),east:bounds.getEast().toFixed(7),max_edges:'2200',
    });
    const geojson=await api(`/api/network/viewport?${params}`);
    if(requestId!==roadsRequestSerial||!reportMode)return;
    if(selectableRoadLayer)map.removeLayer(selectableRoadLayer);
    selectableRoadLayer=L.geoJSON(geojson,{
      style:roadStyle,
      onEachFeature:(feature,layer)=>{
        layer.on({
          mouseover:()=>layer.setStyle({color:'#ffffff',weight:7,opacity:.98}),
          mouseout:()=>{if(!selectedEdge||feature.properties?.osm_u!==selectedEdge.osm_u||feature.properties?.osm_v!==selectedEdge.osm_v)layer.setStyle(roadStyle(feature));},
          click:event=>{L.DomEvent.stopPropagation(event);selectEdge(edgeFromFeature(feature,event.latlng));},
        });
        layer.bindTooltip(feature.properties?.name||feature.properties?.highway||tr('','Road'),{sticky:true});
      },
    }).addTo(map);
    selectableRoadLayer.bringToFront();
    if(!silent)toast(tr(` ${geojson.rendered_edges||0} `,`Ready: ${geojson.rendered_edges||0} road segments`));
  }catch(error){
    if(requestId===roadsRequestSerial)toast(error.message,true);
  }finally{if(requestId===roadsRequestSerial)loading.classList.add('hidden');}
}

async function selectRoadByMapPoint(lat,lon){
  try{
    const edge=await api('/api/road-edge/preview',{method:'POST',body:JSON.stringify({lat,lon})});
    selectEdge(edge);
  }catch(error){toast(error.message,true);}
}

function selectEdge(edge){
  selectedEdge=edge;
  selectedRoadLayer.clearLayers();
  if(edge.geometry?.length){
    L.polyline(edge.geometry,{color:'#fff',weight:13,opacity:.95,lineCap:'round'}).addTo(selectedRoadLayer);
    L.polyline(edge.geometry,{color:'#d4473d',weight:8,opacity:1,lineCap:'round'}).addTo(selectedRoadLayer);
  }
  $('#selectedRoadName').textContent=edge.road_name||tr('','Unnamed road');
  $('#selectedRoadMeta').textContent=`${edge.highway||'road'} · ${edge.direction_text||''}${Number(edge.snap_distance_m)>0?` · ${Math.round(edge.snap_distance_m)} m`:''}`;
  $('#edgeReadyBadge').className='edge-state ready';
  $('#edgeReadyBadge').textContent=tr('','READY');
  $('#submitClosureBtn').disabled=false;
  $('#edgeEvidence').textContent=JSON.stringify({
    edge:{u:edge.osm_u,v:edge.osm_v,key:edge.osm_key},
    direction:edge.direction_text,
    road_name:edge.road_name,
    highway:edge.highway,
    geometry_points:edge.geometry?.length||0,
  },null,2);
  toast(tr(' road segment ','Road segment selected'));
}

async function beginReport(){
  if(!route){toast(tr('','No route available'),true);return;}
  reportReturnFocus=document.activeElement;
  reportMode=true;
  selectedEdge=null;
  selectedRoadLayer.clearLayers();
  $('#reportSheet').classList.remove('hidden');
  $('#closureHint').classList.remove('hidden');
  $('#reporter').value=`Truck ${truckId}`;
  $('#selectedRoadName').textContent=tr('','No road selected');
  $('#selectedRoadMeta').textContent=tr('','Tap a highlighted road line on the map');
  $('#edgeReadyBadge').className='edge-state waiting';
  $('#edgeReadyBadge').textContent=tr('','WAITING');
  $('#submitClosureBtn').disabled=true;
  $('#edgeEvidence').textContent='No segment selected';
  document.body.classList.add('report-mode');
  setTimeout(()=>map.invalidateSize(),20);
  await loadVisibleRoads(false);
  $('#cancelReportBtn').focus();
}

function closeReport(){
  reportMode=false;
  roadsRequestSerial+=1;
  clearTimeout(roadReloadTimer);
  selectedEdge=null;
  $('#reportSheet').classList.add('hidden');
  document.body.classList.remove('report-mode');
  $('#closureHint').classList.add('hidden');
  selectedRoadLayer.clearLayers();
  if(selectableRoadLayer){map.removeLayer(selectableRoadLayer);selectableRoadLayer=null;}
  if(reportReturnFocus?.isConnected)reportReturnFocus.focus();
  reportReturnFocus=null;
}

async function submitClosure(){
  if(!selectedEdge)return;
  const button=$('#submitClosureBtn');
  const original=button.textContent;
  button.disabled=true;
  button.textContent=tr('…','Sending…');
  try{
    const response=await api('/api/closures',{method:'POST',body:JSON.stringify({
      lat:selectedEdge.snap_lat,
      lon:selectedEdge.snap_lon,
      reporter:$('#reporter').value.trim()||`Truck ${truckId}`,
      source_truck_id:truckId,
      note:$('#closureNote').value.trim(),
      block_reverse:$('#blockReverse').checked,
      edge:selectedEdge,
    })});
    closeReport();
    $('#closureNote').value='';
    toast(tr(
      ' ·  Dispatcher  · ',
      'Report sent · awaiting dispatch approval · route unchanged'
    ));
    await loadReports(true);
  }catch(error){
    toast(error.message,true);
    button.disabled=false;
  }finally{button.textContent=original;}
}

async function loadLatestRoute(silent=false){
  if(latestRouteRequestInFlight)return;
  latestRouteRequestInFlight=true;
  const previousVersion=Number(latestVersion?.id||0);
  const previousRouteAssigned=!!route;
  try{
    // Use one state snapshot so the displayed route version and route_state are
    // observed together. Publication commits both records transactionally.
    const state=await api('/api/state?include_routes=true',{timeoutMs:20000});
    const incoming=state?.latest_routes?.id?state.latest_routes:null;
    latestVersion=incoming;
    routeState=state?.route_state||{stale:true,reason:'No route has been published'};
    optimizerJob=(state?.jobs||[]).find(job=>['solve','network-and-solve'].includes(job.kind)&&['queued','running'].includes(job.status))||null;
    route=(incoming?.payload?.routes||[]).find(item=>Number(item.truck_id)===truckId)||null;

    const newVersion=Number(latestVersion?.id||0);
    const generationChanged=previousVersion!==newVersion;
    const assignmentChanged=previousRouteAssigned!==!!route;
    setConnected(true);
    renderRouteSummary();
    renderGoogleNavigation();
    renderOptionalProgress();
    drawCompleteRoute(generationChanged||assignmentChanged||!silent);
    const reportButton=$('#reportBtn');if(reportButton)reportButton.disabled=!route;

    const notice=$('#routeUpdate');
    if(notice&&route&&currentPlanStatus().phase==='stale'){
      notice.dataset.kind='route';notice.classList.remove('hidden','offline');
      notice.innerHTML=`<b>Updated plan required</b> · ${esc(routeState.reason||'Dispatch inputs changed. Navigation stays disabled until a matching plan is published.')}`;
    }else if(notice?.dataset.kind==='route'){
      notice.classList.add('hidden');notice.classList.remove('offline');delete notice.dataset.kind;
    }
    if(!silent&&previousVersion&&newVersion&&previousVersion!==newVersion){
      toast(`Fleet plan updated to v${newVersion}`);
    }
    requestAnimationFrame(()=>map?.invalidateSize?.({pan:false,animate:false}));
  }catch(error){
    setConnected(false,error.message);
    if(!silent)toast(error.message,true);
  }finally{
    latestRouteRequestInFlight=false;
  }
}

async function loadReports(silent=false){
  try{
    const response=await api('/api/closures');
    const needle=`truck ${truckId}`.toLowerCase();
    const reports=(response.closures||[]).filter(item=>Number(item.source_truck_id)===truckId||(item.source_truck_id==null&&String(item.reporter||'').toLowerCase().includes(needle)));
    $('#closureHistory').innerHTML=reports.length?reports.slice(0,12).map(item=>{
      const state=item.status==='pending'
        ?tr(' Dispatcher  · ','Awaiting dispatch approval · route unchanged')
        :item.status==='approved'
          ?(item.route_version_after
            ?tr(` input revision ${item.applied_revision||0} ·  v${item.route_version_after}`,`Applied to input revision ${item.applied_revision||0} · fleet plan v${item.route_version_after} created`)
            :item.reroute_deferred
              ?tr(` edge  · `,`Edge blocked · reroute waiting in queue`)
              :tr(` edge  · `,`Edge blocked · reroute in progress`))
          :item.status==='rejected'
            ?tr('Dispatcher  · ','Report rejected · graph unchanged')
            :tr(' · edge ','Road reopened · edge restored');
      const direction=item.block_reverse?tr('','Both directions'):tr('','Selected direction');
      return `<article class="report-card ${esc(item.status)}"><h3>${esc(item.road_name||tr('','Unnamed road'))}</h3><p>${esc(item.note||'—')}</p><p><b>${esc(direction)}</b><br>${esc(state)}</p><footer><span>${esc(item.status)}</span><span>${new Date(item.reported_at).toLocaleString('en-US')}</span></footer></article>`;
    }).join(''):`<div style="grid-column:1/-1;padding:20px;text-align:center;color:#65778a;font-size:9px">${tr('','No reports from this truck yet.')}</div>`;
    if(!silent)toast(tr('','Reports refreshed'));
  }catch(error){if(!silent)toast(error.message,true);}
}

function bind(){
  $('#dispatcherLink').href=withToken('/');
  $('#connectionBadge').addEventListener('click',()=>loadLatestRoute(false));
  $$('[data-map-style]').forEach(button=>button.addEventListener('click',()=>setMapStyle(button.dataset.mapStyle)));
  $('#fitRouteBtn').addEventListener('click',fitRoute);
  $('#printRouteBtn').addEventListener('click',()=>window.print());
  $('#reportBtn').addEventListener('click',beginReport);
  $('#cancelReportBtn').addEventListener('click',closeReport);
  $('#reportBackdrop').setAttribute('aria-hidden','true');
  $('#reselectRoadBtn').addEventListener('click',()=>{selectedEdge=null;selectedRoadLayer.clearLayers();$('#submitClosureBtn').disabled=true;$('#selectedRoadName').textContent='No road selected';$('#selectedRoadMeta').textContent='Tap a highlighted road line on the map';$('#edgeReadyBadge').className='edge-state waiting';$('#edgeReadyBadge').textContent='WAITING';$('#edgeEvidence').textContent='No segment selected';});
  $('#submitClosureBtn').addEventListener('click',submitClosure);
  $('#refreshReportsBtn').addEventListener('click',()=>loadReports(false));
  $('#markNextDoneBtn').addEventListener('click',()=>{
    const next=nextIncomplete();
    if(!next)return;
    const done=completedStops();done.add(Number(next.sequence));saveCompletedStops(done);renderOptionalProgress();
  });
  $('#resetProgressBtn').addEventListener('click',resetCompletedStops);
  window.addEventListener('online',()=>loadLatestRoute(false));
  window.addEventListener('offline',()=>setConnected(false));
  document.addEventListener('keydown',event=>{if(event.key==='Escape'&&reportMode){event.preventDefault();closeReport();}});
}

function bootDriver(){
  if(typeof L==='undefined'){
    setConnected(false,tr(' ','The local map component did not load. Reload this page.'));
    $('#connectionBadge').addEventListener('click',()=>location.reload());
    return;
  }
  initMap();bind();applyLanguage();
  loadLatestRoute(false).then(()=>loadReports(true));
  pollTimer=setInterval(()=>loadLatestRoute(true),10000);
}
bootDriver();
