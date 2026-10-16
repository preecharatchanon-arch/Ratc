'use strict';

const $ = (selector, root = document) => root.querySelector(selector);
const withToken = path => path;
const km = meters => `${((Number(meters) || 0) / 1000).toFixed(1)} km`;
const formatClock = value => {
  if (!Number.isFinite(Number(value))) return '—';
  const seconds = Math.max(0, Math.round(Number(value)));
  return `${String(Math.floor(seconds / 3600) % 24).padStart(2, '0')}:${String(Math.floor((seconds % 3600) / 60)).padStart(2, '0')}`;
};

const COLORS = ['#0f8075','#2f6fec','#b87813','#9b55c4','#d05b43','#1687a7','#688c32','#ce4775','#5e6d80','#00a08a'];
const ROUTE_PROFILES = new WeakMap();
const PLAYBACK_SECONDS_AT_1X = 120;

let map;
let routeLayer;
let stopLayer;
let truckLayer;
let routes = [];
let routeVersion = null;
let routeState = {};
let activeSolver = null;
let markers = new Map();
let playing = false;
let progress = 0;
let lastFrame = 0;
let speed = 1;
let simStart = 0;
let simEnd = 60;
let loadInFlight = false;
let connectionStatus = 'connecting';
let connectionDetail = '';
let pollTimer = null;

async function api(url, {timeoutMs = 15000} = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, {signal: controller.signal});
    const text = await response.text();
    let data;
    try { data = text ? JSON.parse(text) : {}; } catch { data = {detail: text}; }
    if (!response.ok) throw new Error(requestErrorMessage(data,response.status));
    return data;
  } catch (error) {
    if (controller.signal.aborted) throw new Error(`FleetRoute did not respond within ${Math.ceil(timeoutMs / 1000)} seconds.`);
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

function renderConnection() {
  const button = $('#connectionBtn');
  const notice = $('#connectionNotice');
  const online = connectionStatus === 'online';
  button.classList.toggle('connecting', connectionStatus === 'connecting');
  button.classList.toggle('offline', connectionStatus === 'offline');
  button.textContent = online ? 'ONLINE' : connectionStatus === 'connecting' ? 'CONNECTING' : 'OFFLINE';
  notice.classList.toggle('hidden', connectionStatus !== 'offline');
  if (connectionStatus === 'offline') {
    $('#connectionNoticeTitle').textContent = 'Could not reach FleetRoute';
    $('#connectionNoticeDetail').textContent = connectionDetail || 'Choose Retry. The last loaded plan remains visible.';
  }
}

function setConnection(status, detail = '') {
  connectionStatus = status;
  connectionDetail = detail;
  renderConnection();
}

function simulationPlanStatus() {
  const hasRoute = routes.length > 0 && !!routeVersion?.id;
  const source = String(routeState.solution_source || routeVersion?.payload?.solution_source || '');
  const stateVersion = Number(routeState.route_version || 0);
  const displayedVersion = Number(routeVersion?.id || 0);
  const generationMismatch = hasRoute && (!stateVersion || stateVersion !== displayedVersion);
  const stale = hasRoute && (routeState.stale !== false || generationMismatch);
  const completed = !!(routeState.optimization_completed || routeState.optimization_checked_at || source === 'cpp_optimizer');
  if (stale) return {phase:'stale', badge:'UPDATE NEEDED', completed:false, title:'Plan no longer matches current inputs', detail:'This playback is historical until dispatch publishes an updated fleet plan.'};
  if (activeSolver && hasRoute) return {phase:'running', badge:'OPTIMIZING', completed:false, title:'Replaying the published initial plan', detail:'Dashed routes remain visible while the optimizer searches for a better validated result.'};
  if (!hasRoute) return {phase:'empty', badge:'NO PLAN', completed:false, title:'No fleet plan to simulate', detail:'Create and publish a route from the control center first.'};
  if (!completed) return {phase:'prepared', badge:'INITIAL PLAN', completed:false, title:'Replaying the constraint-valid initial plan', detail:'The optimizer has not yet published a completed result.'};
  if (source === 'cpp_optimizer') return {phase:'optimized', badge:'OPTIMIZED', completed:true, title:'Validated optimized fleet plan', detail:'The optimizer completed and FleetRoute independently validated this published result.'};
  return {phase:'reviewed', badge:'READY', completed:true, title:'Validated fleet plan', detail:'Optimization completed; the feasible existing plan was retained.'};
}

function renderPlanStatus() {
  const status = simulationPlanStatus();
  const card = $('#simulationPlanState');
  if (!card) return;
  card.className = `simulation-plan-state ${status.phase}`;
  $('i', card).textContent = status.completed ? '✓' : status.phase === 'running' ? '◆' : status.phase === 'prepared' ? '△' : status.phase === 'stale' ? '!' : '◇';
  $('b', card).textContent = status.title;
  $('small', card).textContent = status.detail;
  $('span', card).textContent = status.badge;
  document.body.dataset.planPhase = status.phase;
}

function updateSimulationMeta() {
  const status = simulationPlanStatus();
  const workItems = routes.reduce((sum, route) => sum + (route.stops || []).reduce((subtotal, stop) => subtotal + (stop.orders?.length || 0), 0), 0);
  const distance = routes.reduce((sum, route) => sum + (Number(route.distance_m) || 0), 0);
  $('#simMeta').textContent = routes.length
    ? `${routes.length} ${routes.length === 1 ? 'truck' : 'trucks'} · ${workItems} work items · ${km(distance)} · ${formatClock(simStart)}–${formatClock(simEnd)} · ${status.badge}`
    : status.detail;
}

function init() {
  map = L.map('simMap').setView([20, 0], 2);
  const fallback = 'data:image/svg+xml;charset=UTF-8,' + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256"><rect width="256" height="256" fill="#eaf0f4"/><path d="M0 64H256M0 128H256M0 192H256M64 0V256M128 0V256M192 0V256" stroke="#d5dee6" fill="none"/></svg>');
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {maxNativeZoom:19,maxZoom:20,referrerPolicy:'strict-origin', attribution:'&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap contributors</a>', errorTileUrl:fallback}).addTo(map);
  routeLayer = L.layerGroup().addTo(map);
  stopLayer = L.layerGroup().addTo(map);
  truckLayer = L.layerGroup().addTo(map);
  $('#backLink').href = withToken('/');
  bind();
  load(false);
  pollTimer = setInterval(() => load(true), 15000);
  requestAnimationFrame(frame);
}

function segmentMeters(a, b) {
  const rad = Math.PI / 180;
  const lat1 = Number(a[0]) * rad;
  const lat2 = Number(b[0]) * rad;
  const dlat = lat2 - lat1;
  const dlon = (Number(b[1]) - Number(a[1])) * rad;
  const x = Math.sin(dlat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dlon / 2) ** 2;
  return 6371008.8 * 2 * Math.atan2(Math.sqrt(x), Math.sqrt(Math.max(0, 1 - x)));
}

function pointKey(lat, lon) {
  return `${Number(lat).toFixed(5)},${Number(lon).toFixed(5)}`;
}

function routeProfile(route) {
  let profile = ROUTE_PROFILES.get(route);
  if (profile) return profile;
  const points = Array.isArray(route.geometry) ? route.geometry : [];
  const cumulative = [0];
  for (let index = 1; index < points.length; index += 1) {
    cumulative.push(cumulative.at(-1) + segmentMeters(points[index - 1], points[index]));
  }

  const coordinateIndex = new Map();
  points.forEach((point, index) => {
    const key = pointKey(point[0], point[1]);
    if (!coordinateIndex.has(key)) coordinateIndex.set(key, []);
    coordinateIndex.get(key).push(index);
  });

  let previous = 0;
  const stopIndices = (route.stops || []).map(stop => {
    const candidates = coordinateIndex.get(pointKey(stop.lat, stop.lon)) || [];
    const exact = candidates.find(index => index >= previous);
    if (exact != null) {
      previous = exact;
      return exact;
    }
    if (!points.length) return 0;
    let bestIndex = previous;
    let bestDistance = Infinity;
    for (let index = previous; index < points.length; index += 1) {
      const distance = segmentMeters([stop.lat, stop.lon], points[index]);
      if (distance < bestDistance) {
        bestDistance = distance;
        bestIndex = index;
      }
      if (bestDistance < 2 && index > bestIndex + 20) break;
    }
    previous = bestIndex;
    return bestIndex;
  });

  profile = {points, cumulative, stopIndices, total:cumulative.at(-1) || 0};
  ROUTE_PROFILES.set(route, profile);
  return profile;
}

function interpolateGeometry(profile, startIndex, endIndex, fraction) {
  const points = profile.points;
  if (!points.length) return [0, 0];
  startIndex = Math.max(0, Math.min(points.length - 1, Number(startIndex) || 0));
  endIndex = Math.max(startIndex, Math.min(points.length - 1, Number(endIndex) || startIndex));
  if (endIndex <= startIndex || fraction <= 0) return points[startIndex];
  if (fraction >= 1) return points[endIndex];
  const startDistance = profile.cumulative[startIndex] || 0;
  const endDistance = profile.cumulative[endIndex] || startDistance;
  const target = startDistance + (endDistance - startDistance) * fraction;
  let low = startIndex + 1;
  let high = endIndex;
  while (low < high) {
    const middle = Math.floor((low + high) / 2);
    if (profile.cumulative[middle] < target) low = middle + 1;
    else high = middle;
  }
  const index = Math.max(startIndex + 1, low);
  const before = index - 1;
  const span = Math.max(1e-9, profile.cumulative[index] - profile.cumulative[before]);
  const ratio = Math.max(0, Math.min(1, (target - profile.cumulative[before]) / span));
  const a = points[before];
  const b = points[index];
  return [a[0] + (b[0] - a[0]) * ratio, a[1] + (b[1] - a[1]) * ratio];
}

function routeStart(route) {
  const first = route.stops?.[0] || {};
  return Number.isFinite(Number(route.route_start_time_s)) ? Number(route.route_start_time_s)
    : Number.isFinite(Number(first.departure_s)) ? Number(first.departure_s) : 0;
}

function routeFinish(route) {
  const last = route.stops?.at(-1) || {};
  return Number.isFinite(Number(route.finish_time_s)) ? Number(route.finish_time_s)
    : Number.isFinite(Number(last.arrival_s)) ? Number(last.arrival_s)
    : routeStart(route) + Math.max(0, Number(route.travel_time_s) || 0);
}

function positionAtClock(route, clock) {
  const profile = routeProfile(route);
  const stops = route.stops || [];
  if (!profile.points.length) return [stops[0]?.lat || 0, stops[0]?.lon || 0];
  if (!stops.length) return profile.points[0];
  if (clock <= routeStart(route)) return profile.points[profile.stopIndices[0] || 0];

  for (let index = 0; index < stops.length - 1; index += 1) {
    const current = stops[index];
    const next = stops[index + 1];
    const depart = Number.isFinite(Number(current.departure_s)) ? Number(current.departure_s) : null;
    const arrive = Number.isFinite(Number(next.arrival_s)) ? Number(next.arrival_s) : null;
    if (depart == null || arrive == null || arrive < depart) continue;
    if (clock <= depart) return profile.points[profile.stopIndices[index] || 0];
    if (clock < arrive) {
      const fraction = arrive > depart ? (clock - depart) / (arrive - depart) : 1;
      return interpolateGeometry(profile, profile.stopIndices[index], profile.stopIndices[index + 1], fraction);
    }
  }
  return profile.points[profile.stopIndices.at(-1) ?? profile.points.length - 1];
}

function fleetClock() {
  return simStart + progress * Math.max(1, simEnd - simStart);
}

function routeProgress(route, clock) {
  const start = routeStart(route);
  const finish = Math.max(start + 1, routeFinish(route));
  return Math.max(0, Math.min(1, (clock - start) / (finish - start)));
}

function recalculateSimulationWindow() {
  if (!routes.length) {
    simStart = 0;
    simEnd = 60;
    return;
  }
  simStart = Math.min(...routes.map(routeStart));
  simEnd = Math.max(...routes.map(routeFinish));
  if (!Number.isFinite(simStart)) simStart = 0;
  if (!Number.isFinite(simEnd) || simEnd <= simStart) simEnd = simStart + 60;
}

async function load(silent = false) {
  if (loadInFlight) return;
  loadInFlight = true;
  if (!silent) setConnection('connecting');
  const previousVersion = routeVersion?.id || null;
  const previousPhase = simulationPlanStatus().phase;
  try {
    const state = await api('/api/state');
    routeVersion = state.latest_routes || null;
    routeState = state.route_state || {};
    activeSolver = (state.jobs || []).find(job => ['solve','network-and-solve'].includes(job.kind) && ['queued','running'].includes(job.status)) || null;
    routes = routeVersion?.payload?.routes || [];
    recalculateSimulationWindow();
    $('#versionBadge').textContent = routeVersion ? `PLAN v${routeVersion.id}` : 'PLAN —';
    const newPhase = simulationPlanStatus().phase;
    renderPlanStatus();
    updateSimulationMeta();
    setConnection('online');
    if (!silent || previousVersion !== (routeVersion?.id || null) || previousPhase !== newPhase) render(!silent || previousVersion !== (routeVersion?.id || null));
    else updateUI();
  } catch (error) {
    setConnection('offline', error.message);
    if (!silent) toast(error.message);
  } finally {
    loadInFlight = false;
  }
}

function render(fit = true) {
  routeLayer.clearLayers();
  stopLayer.clearLayers();
  truckLayer.clearLayers();
  markers.clear();
  const bounds = [];
  const status = simulationPlanStatus();
  const initial = !status.completed && ['prepared','running'].includes(status.phase);
  routes.forEach((route, index) => {
    const color = COLORS[index % COLORS.length];
    const lineStyle = {color:initial ? '#d4942d' : color, weight:4, opacity:initial ? .76 : .8};
    if (initial) lineStyle.dashArray = '12 9';
    if (route.geometry?.length) {
      L.polyline(route.geometry, lineStyle).addTo(routeLayer);
      bounds.push(...route.geometry);
    }
    route.stops?.forEach(stop => L.circleMarker([stop.lat, stop.lon], {
      radius:stop.kind === 'depot' ? 6 : 3.5,
      color:'#fff', weight:1.5,
      fillColor:stop.kind === 'depot' ? '#07192d' : color,
      fillOpacity:1,
    }).addTo(stopLayer));
    const position = positionAtClock(route, fleetClock());
    const icon = L.divIcon({className:'', html:`<div class="truck-marker" style="background:${initial ? '#b97816' : color}">${route.truck_id}</div>`, iconSize:[31,31], iconAnchor:[15,15]});
    markers.set(route.truck_id, L.marker(position, {icon, zIndexOffset:500}).bindTooltip(`Truck ${route.truck_id}`).addTo(truckLayer));
  });
  if (fit && bounds.length) map.fitBounds(bounds, {padding:[30,30]});
  renderRoster();
  updateUI();
}

function renderRoster() {
  if (!routes.length) {
    $('#truckList').innerHTML = '<div class="simulation-empty">No fleet plan is available.</div>';
    return;
  }
  const status = simulationPlanStatus();
  const clock = fleetClock();
  $('#truckList').innerHTML = routes.map((route, index) => {
    const color = COLORS[index % COLORS.length];
    const workItems = (route.stops || []).reduce((sum, stop) => sum + (stop.orders?.length || 0), 0);
    const local = routeProgress(route, clock);
    const state = local <= 0 ? 'Not started' : local >= 1 ? 'Complete' : `${Math.round(local * 100)}%`;
    return `<article class="truck-row ${status.completed ? 'complete' : 'initial'}" data-id="${route.truck_id}" tabindex="0" role="button">
      <div class="truck-icon" style="background:${status.completed ? color : '#b97816'}">${route.truck_id}</div>
      <div><h3>Truck ${route.truck_id}</h3><p>${workItems} work items · ${km(route.distance_m)} · ${formatClock(routeStart(route))}–${formatClock(routeFinish(route))}</p></div>
      <span>${state}</span>
    </article>`;
  }).join('');
  document.querySelectorAll('.truck-row').forEach(row => {
    row.addEventListener('click', () => focusTruck(Number(row.dataset.id)));
    row.addEventListener('keydown', event => {
      if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); focusTruck(Number(row.dataset.id)); }
    });
  });
}

function focusTruck(id) {
  document.querySelectorAll('.truck-row').forEach(row => row.classList.toggle('active', Number(row.dataset.id) === id));
  const route = routes.find(item => Number(item.truck_id) === id);
  if (route?.geometry?.length) map.fitBounds(route.geometry, {padding:[45,45]});
}

function updateUI() {
  const clock = fleetClock();
  routes.forEach(route => markers.get(route.truck_id)?.setLatLng(positionAtClock(route, clock)));
  $('#timeSlider').value = Math.round(progress * 1000);
  $('#timeReadout').textContent = formatClock(clock);
  $('#heroMetrics').innerHTML = `<div class="metric"><span>TRUCKS</span><b>${routes.length}</b></div><div class="metric"><span>PLANNED TIME</span><b>${formatClock(clock)}</b></div><div class="metric"><span>PLAYBACK</span><b>${speed}×</b></div>`;
  if (Math.round(progress * 1000) % 10 === 0) renderRoster();
  $('#playBtn').disabled = routes.length === 0;
}

function frame(timestamp) {
  if (playing && routes.length) {
    if (lastFrame) {
      progress += ((timestamp - lastFrame) / 1000) * speed / PLAYBACK_SECONDS_AT_1X;
      if (progress >= 1) {
        progress = 1;
        playing = false;
        $('#playBtn').textContent = '▶';
      }
    }
    lastFrame = timestamp;
    updateUI();
  } else {
    lastFrame = timestamp;
  }
  requestAnimationFrame(frame);
}

function bind() {
  $('#connectionBtn').addEventListener('click', () => load(false));
  $('#retryBtn').addEventListener('click', () => load(false));
  $('#playBtn').addEventListener('click', () => {
    if (progress >= 1) progress = 0;
    playing = !playing;
    $('#playBtn').textContent = playing ? 'Ⅱ' : '▶';
  });
  $('#resetBtn').addEventListener('click', () => {
    progress = 0;
    playing = false;
    $('#playBtn').textContent = '▶';
    updateUI();
    renderRoster();
  });
  $('#timeSlider').addEventListener('input', event => {
    progress = Number(event.target.value) / 1000;
    updateUI();
    renderRoster();
  });
  $('#speedSelect').addEventListener('change', event => {
    speed = Number(event.target.value);
    updateUI();
  });
  $('#fitAllBtn').addEventListener('click', () => {
    const points = routes.flatMap(route => route.geometry || []);
    if (points.length) map.fitBounds(points, {padding:[30,30]});
  });
  window.addEventListener('online', () => load(false));
  window.addEventListener('offline', () => setConnection('offline', 'Network connection is unavailable. The last loaded plan remains visible.'));
}

function toast(message) {
  const element = $('#toast');
  element.textContent = message;
  element.classList.add('show');
  clearTimeout(window.__fleetSimulationToast);
  window.__fleetSimulationToast = setTimeout(() => element.classList.remove('show'), 2600);
}

function bootSimulation() {
  document.documentElement.lang = 'en';
  if (typeof L === 'undefined') {
    setConnection('offline', 'The local map component did not load. Reload this page.');
    $('#simMeta').textContent = 'Simulation cannot start until the local map component loads.';
    $('#connectionBtn').addEventListener('click', () => location.reload());
    $('#retryBtn').addEventListener('click', () => location.reload());
    return;
  }
  init();
}

bootSimulation();
