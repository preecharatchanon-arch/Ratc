'use strict';

const $ = (q, root=document) => root.querySelector(q);
const $$ = (q, root=document) => [...root.querySelectorAll(q)];
// Authentication is cookie-based after the launch URL is verified server-side.
// Never persist or re-append the access token in browser storage or shareable URLs.
const withToken = path => path;

let STATE = null;
let currentView = 'command';
let LANG = 'en';
const SAVED_APPLICATION_MODE = storageRead('localStorage','fleetroute_judge_mode');
let JUDGE_MODE = SAVED_APPLICATION_MODE === null ? true : SAVED_APPLICATION_MODE === 'true';
let searchResults = [];
let pendingPlace = null;
let pendingAccess = null;
let selectedPlaceId = null;
let DISTANCE_RISK_RESOLVE = null;
let mapAddMode = false;
let closurePickMode = false;
let pendingClosureEdge = null;
let selectedJobId = null;
let selectedJobLog = '';
let convergenceData = null;
let convergenceChart = null;
let workerChart = null;
let routeChart = null;
let LIVE_OPTIMIZER_JOB_ID = null;
let LIVE_OPTIMIZER_MINIMIZED = false;
const LIVE_OPTIMIZER_DISMISSED = new Set();
let commandMap = null;
let commandRouteLayer = null;
let commandStopLayer = null;
let routeHaloLayer = null;
let routeStopLayer = null;
let COMMAND_MAP_KEY = '';
let roadStyle = 'class';
let roadGeojson = null;
const MAP_THEMES = [
  {key:'navigation',label:'Navigation',icon:'⌖',provider:'osm',description:'Street-first GPS view'},
  {key:'terrain',label:'Terrain',icon:'△',provider:'topo',description:'Topography and relief'},
  {key:'clean',label:'Clean',icon:'◫',provider:'osm',description:'Quiet background for route overlays'},
  {key:'night',label:'Night',icon:'◐',provider:'osm',description:'Low-glare dark operations view'}
];
const LEGACY_MAP_THEME = {operations:'clean',street:'navigation',contrast:'clean'};
const SAVED_MAP_THEME_RAW = storageRead('localStorage','fleetroute_map_theme','navigation');
const SAVED_MAP_THEME = LEGACY_MAP_THEME[SAVED_MAP_THEME_RAW]||SAVED_MAP_THEME_RAW;
let mapThemeIndex = Math.max(0, MAP_THEMES.findIndex(theme=>theme.key===SAVED_MAP_THEME));
if(mapThemeIndex<0)mapThemeIndex=0;
let selectedCandidate = null;
let selectedCandidateAccess = null;
let mapPickRole = 'customer';
let PENDING_CLUSTER_METHOD = null;
let RUSH_ROWS = [];
let CONSOLE_OPEN = false;
let CONSOLE_FOLLOW = true;
let CONSOLE_WRAP = true;
let CONNECTION_ONLINE = false;
let CONNECTION_FAILURES = 0;
let DEV_RUNTIME = null;
let DEV_FILE_KEY = null;
let DEV_FILE_TEXT = '';
let DEV_FILE_OFFSET = 0;
let DEV_FILE_COMPLETE = true;
const NOTIFIED_JOBS = readNotificationIds('fleetroute_notified_jobs');
const NOTIFIED_BASELINES = readNotificationIds('fleetroute_notified_baselines');

const I18N = {

  en: {
    systemOnline:'System online',navCommand:'Command Center',navPlan:'Plan destinations',navRoads:'Roads & incidents',navClustering:'Clustering Lab',navOptimize:'Optimizer',navAnalytics:'Convergence Lab',navDispatch:'Dispatch Center',navActivity:'Evidence & Logs',navDeveloper:'Data & Runtime',openSimulation:'Open Truck Simulation',openDriver:'Open Driver App',idle:'Idle',optimize:'Optimize',commandKicker:'INTELLIGENT FLEET OPERATIONS',commandTitle:'Turn real destinations into auditable truck operations',commandDesc:'Set a depot, add real work points, validate road access, optimize routes, and publish driver-ready plans from one control center.',tryDemo:'Try the complete demo',buildRealPlan:'Build a real-place plan',currentReadiness:'Current readiness',workflowKicker:'GUIDED WORKFLOW',workflowTitle:'From plan to operating trucks',continuePlan:'Continue',latestRun:'Latest run',evidenceGallery:'Notebook figures and evidence',viewAll:'View all',planTitle:'Search real places, then confirm a round-trip road access segment',planDesc:'Choose the real destination. FleetRoute highlights the nearest usable road segment and saves the matched road location only after outbound-and-return access is proven.',loadDemo:'Load demo',continueRoadSetup:'Next: Road setup',searchRealPlace:'Search a place, business, school, hotel, or address',search:'Search',searching:'Searching…',addFromMap:'Add from map',roadSnapRequired:'A drivable road is required',randomNearDepot:'Random work points near depot',replaceCustomers:'Replace current work points',importCsv:'Import CSV',currentPlan:'Current plan',clear:'Clear',fitPlan:'Fit all stops',mapStyle:'Map style',clickRoadLocation:'Click the real location; road access will be validated',depot:'Depot',customer:'Work point',roadAccess:'Road access',roadsTitle:'Choose a regional road source, then prepare the directed operating graph',roadsDesc:'FleetRoute verifies the selected regional road data, extracts the active operating area, and builds a directed round-trip graph with named road segments.',buildRoadNetwork:'Build and validate network',osmSetup:'Road-source setup',networkType:'Network type',networkMargin:'Coverage margin',snapLimit:'Maximum road-access distance',networkScope:'Network scope',saveSettings:'Save settings',showRoadLayer:'Show road layer',roadGraphPreview:'Road-network preview',roadClass:'Road class',speed:'Speed',oneWay:'One-way',stopRoadAccess:'Road access for every place',editStops:'Edit stops',closureCommand:'Road-closure command',selectClosedRoad:'Select a closed road segment',closureHelp:'Press the button and click the road line. FleetRoute highlights the exact segment before a report is submitted—it is not a node report.',clusterTitle:'Validated clustering that cannot silently break the solve',clusterDesc:'Each method is independently checked for work-point coverage, cluster IDs, capacity, and overload. Failures are explained and safely fall back unless strict mode is enabled.',benchmarkAll:'Benchmark every method',chooseClusterMethod:'Choose starting route grouping',strictMode:'Strict clustering',strictModeHelp:'Stop the run when clustering fails instead of falling back',saveClusterPolicy:'Save clustering policy',clusterPreview:'Latest cluster partition',methodScorecard:'Runtime, proxy cost, balance, and feasibility scorecard',downloadZip:'Download ZIP',optimizeTitle:'Validate first → publish initial plan → improve with routing',optimizeDesc:'FleetRoute independently validates a capacity-, road-, and time-feasible route, publishes it immediately, then lets routing search for a better route in the background.',optimizeNow:'Optimize routes',fullPipeline:'Run the complete pipeline',pipelineStatus:'Processing status',openDetailedLog:'Open detailed log',rerunCurrentGraph:'Rerun on current graph',operatingSettings:'Basic route settings',save:'Save',trucks:'Maximum trucks',capacity:'Capacity per truck',objective:'Optimize for',clustering:'Clustering',advancedResearchSettings:'Advanced solver settings',parallelInstances:'Maximum parallel workers',hardLimit:'Maximum runtime (seconds)',stageLimit:'Per-stage time (s)',enforceTW:'Enforce time windows',allowMultiTrip:'Allow multi-trip',generateEvidence:'Build convergence report',analyticsTitle:'See how the optimizer improved the route over time',analyticsDesc:'Review best-so-far objective, late-run detail, worker comparison, search temperature, acceptance, and stagnation from the recorded optimization trace.',downloadConvergence:'Download Convergence Report',convergenceCurve:'Primary convergence curve',fullRun:'Full run',lateZoom:'Late zoom',convergenceChecks:'Log integrity checks',workerComparison:'Worker comparison',notebookFigures:'Optimization analysis figures',dispatchTitle:'Every truck route, driver app, and offline HTML package',dispatchDesc:'Inspect all routes, open driver operations, run the moving-truck simulation, or export standalone HTML route sheets.',truckSimulation:'Truck Simulation',allTruckHtml:'All-truck HTML package',fleetMap:'Fleet route map',showAll:'Show all',routeWorkload:'Route workload',downloadEvidence:'Download run evidence',evidenceDesc:'Input, dataset, clustering, solver output, convergence, route JSON, and analysis figures.',downloadRunZip:'Download Run Evidence ZIP',developerTitle:'Inspect routing inputs, command contract, and returned evidence',developerDesc:'Inspect materialized inputs, SHA-256 identities, routing command details, process streams, and evidence files from the same runtime.',developerContract:'Pre-routing input contract checks',developerCommand:'Routing command and input handoff',developerFiles:'Files used by FleetRoute and the routing engine',developerSelectFile:'Select a file to inspect',developerLoadMore:'Load next chunk',developerSettings:'Effective backend settings',activityTitle:'Readable visual logs first; raw console when needed',activityDesc:'Every job includes a visual timeline, runtime, artifacts, warnings, and separately inspectable process streams for technical review.',refresh:'Refresh',optimizationRuns:'Run history',selectRun:'Select a run',showRawLog:'Open process console',routeVersions:'Route versions',auditTimeline:'Activity timeline',placeName:'Place name',address:'Address',demand:'Demand',serviceMinutes:'Service (minutes)',earliest:'Earliest',latest:'Latest',technicalRoadEvidence:'Technical road-access evidence',cancel:'Cancel',setDepot:'Set as depot',addCustomer:'Add work point',saveChanges:'Save changes',confirmClosedRoad:'Confirm the closed road segment',reporter:'Reporter',blockBothDirections:'Block both directions',closureNote:'Details',technicalEdgeIdentity:'Technical OSM edge identity',sendClosureReport:'Submit road-segment report',noData:'No data yet',loading:'Processing',success:'Success',failed:'Failed',randomHint:'Set work-point count, demand profile, and maximum available fleet',scenarioKicker:'SCENARIO GENERATOR',scenarioTitle:'Generate work points on reachable roads',customerCount:'Work-point count',targetUtilization:'Fleet utilization',scenarioRadius:'Work-point radius',scenarioSeed:'Seed',demandRange:'Demand range',serviceRange:'Service time (minutes)',generateScenario:'Generate scenario',presetCity:'City',presetMetro:'Metro',presetRegion:'Regional',fixedAreaTitle:'Area fixed around the depot',fixedAreaDesc:'Work points inside this area are added instantly without rebuilding the graph',prepareFixedArea:'Prepare operating area'
  }
};
const tr = key => I18N[LANG]?.[key] || I18N.en[key] || key;

const ROUTE_COLORS = ['#0F8075','#2F6FEC','#C68A20','#7C3AED','#16805B','#C9443A','#0E7490','#475569','#BE123C','#4F46E5'];

Object.assign(I18N.en,{
  rushMode:'Rush mode from CSV',rushTitle:'CSV → roads → solver → published routes in one run',chooseRushCsv:'Choose CSV file',rushCsvHelp:'Requires name, lat, lon, and demand. Include one role=depot row or use the current depot.',rushClustering:'Warm start',useCurrentDepot:'Use current depot when CSV has no depot',runRush:'Start rush workflow',pickDepotMap:'Pick depot from map',pickDepotMapHelp:'Click the real place, then validate its road access',addFromMapHelp:'FleetRoute attaches it to a reachable road',testSelectedCluster:'Test selected method',solverProfile:'Routing policy',advancedSolverHelp:'These controls generate the real routing command and feed input.txt through stdin.',extraSolverFlags:'Extra validated solver flags',extraSolverHelp:'Only flags recognized by the routing engine are accepted. Shell operators and managed output paths are rejected.',commandPreview:'Exact command to run',validateCommand:'Validate command',showRawLog:'Open process console'
});


Object.assign(I18N.en,{
  importCsvHelp:'Validate every row after the graph is prepared',mapAccessTitle:'Destination and road-access map',lastMeterAccess:'Last-meter access',reachableRoadSegment:'Reachable road segment',accessInspectorTitle:'Confirm before adding a stop',accessInspectorDesc:'You choose the place; FleetRoute manages graph nodes and edges internally.',noPlaceSelected:'No place selected',noPlaceSelectedHelp:'Choose a search result or pick from the map to inspect verified road access.',roadSegment:'Road segment',lastMeterDistance:'Last-meter distance',roundTripDepot:'Round trip to depot',direction:'Direction',technicalOsmEvidence:'Technical OSM evidence',prepareAreaPrompt:'Prepare or expand the operating graph to validate this stop',prepareAreaPromptHelp:'After a depot is selected, FleetRoute extracts local regional roads and expands the area to include the selected place.',prepareAroundDepot:'Prepare roads around depot',downloadVerify:'Download and verify',checkStatus:'Check status',deleteFile:'Delete file',operatingGraphTitle:'Active operating-road graph',notPrepared:'Not prepared',operatingGraphDesc:'FleetRoute does not load roads in the selected operating region into RAM. It extracts the depot area, caches the graph on local SSD, and keeps spatial indexes in RAM.',presetCityHelp:'6 km · fast',presetMetroHelp:'12 km · broader',presetRegionHelp:'25 km · heavier'
});


Object.assign(I18N.en,{
  presetStandard:'Standard operations',presetQuick:'Quick test',presetStress:'Stress test',scenarioAdvanced:'Custom demand, service & reproducibility',demandSetup:'Demand setup',serviceSetup:'Service setup',automaticRecommended:'Automatic (recommended)',customRange:'Custom range',timeWindowSetup:'Time windows',openDayRecommended:'Open day (recommended)',broadShift:'Broad shift 07:00–22:00',staggeredBenchmark:'Staggered benchmark windows',scenarioReady:'Ready to generate',scenarioStress:'Stress scenario',scenarioBlocked:'Fix settings first',stopsPerTruck:'Stops per truck',estimatedWorkload:'Estimated workload',recommendedTrucks:'Recommended trucks',autoDemandRange:'Automatic demand range',fleetSizing:'Fleet sizing',fleetSizingAuto:'Automatic (recommended)',currentFleet:'Keep current fleet',targetStops:'Target stops per truck',optimizeClustering:'Background clustering',noClusterFast:'None · fast and stable',scenarioRunMode:'Routing mode',fastCertifiedRoute:'Fast validated route (recommended)',backgroundCppImprove:'Publish first, then improve with routing',createStopsOnly:'Create stops only',createAndRoute:'Create stops + run optimizer',scenarioFlowTitle:'1. Create stops → 2. Publish a validated initial route → 3. Run the optimizer automatically',scenarioFlowHelp:'Always uses the saved Optimizer settings and exposes stdout, stderr/cerr, and convergence from the real run.'
});

Object.assign(I18N.en,{
  clusterDesc:'Coverage, cluster IDs, and capacity are checked first. The optimizer then checks roads, visit order, time windows, and trip limits; an unsafe warm start falls back inside the same solve.',
  strictModeHelp:'Stop when the selected method fails assignment validation. The native route gate always falls back safely.',
  demandProfile:'Demand profile',demandLight:'Light',demandStandard:'Standard',demandHeavy:'Heavy',
  routeStart:'Fleet departure time',routeStartHelp:'The route clock starts here and continues across waiting, service, travel, and depot returns.',
  maxTrips:'Maximum trips per truck',maxTripsHelp:'Load resets at the depot; the route clock does not.',
  judgeMode:'Judge mode',fullMode:'Full mode'
});

/* v3 language layer: natural application wording without hiding exact terms. */

Object.assign(I18N.en,{
  navOperations:'Operations',navAnalysis:'Advanced analysis',navCommand:'System overview',
  navPlan:'Work points & depot',navRoads:'Roads & incidents',navClustering:'Clustering',
  navOptimize:'Route optimization',navAnalytics:'Convergence',navDispatch:'Current fleet plan',
  navActivity:'Evidence & logs',navDeveloper:'System data',openSimulation:'Planned-route simulation',openDriver:'Open driver manifest',
  commandKicker:'REAL-ROAD FLEET OPERATIONS',commandTitle:'Plan real-road routes that are ready for field operations',
  commandDesc:'Coordinate multi-vehicle collection and distribution under capacity, time-window, multi-trip, and road-closure constraints, then hand the plan directly to drivers.',
  tryDemo:'Open example scenario',buildRealPlan:'Start planning work points',currentReadiness:'System readiness',
  workflowKicker:'NEXT STEPS',workflowTitle:'Next steps for this plan',continuePlan:'Open plan',latestRun:'Recent activity',
  evidenceGallery:'Analysis and evidence',viewAll:'View all',mapRoute:'Route',mapWorkPoint:'Work point',mapDepot:'Depot',
  planTitle:'Define the depot and work points, then validate real road access',
  planDesc:'Choose locations from search or the map. FleetRoute binds each one to the directed road graph and verifies depot round-trip reachability before saving.',
  pickDepotMap:'Choose depot from map',pickDepotMapHelp:'Click the real place, then validate its road access',
  addFromMap:'Add work point from map',randomNearDepot:'Generate a scenario',replaceCustomers:'Replace current work points',currentPlan:'Current work-point plan',fitPlan:'Fit all work points',
  mapAccessTitle:'Work points and validated road access',clickRoadLocation:'Click the real location; FleetRoute will find road access with verified depot round-trip reachability',
  customer:'Work point',stopRoadAccess:'Road access for every work point',editStops:'Edit work points',addCustomer:'Add work point',
  setDepot:'Set as depot',
  roadsTitle:'Prepare the road network for this operating area',
  roadsDesc:'Build a directed graph from real roads, including direction, speed, access points, and approved closures.',
  operatingGraphTitle:'Directed road graph',operatingGraphDesc:'Extract the area around the depot and reuse it for later routing runs.',
  clusterTitle:'Clustering for optimizer warm starts',
  clusterDesc:'Compare Road Savings, Network K-medoids, Sweep, and Sparse Spectral using coverage, capacity, overload, runtime, and input SHA-256.',
  chooseClusterMethod:'Choose starting route grouping',
  optimizeTitle:'Prepare an initial plan, then let the optimizer search for a better route',
  optimizeDesc:'Follow clustering, initial-plan construction, optimizer search, validation, convergence, and logs in one workspace.',
  optimizeNow:'Start optimizer',fullPipeline:'Prepare → search → validate → apply',
  dispatchTitle:'Fleet plan, driver manifests, and field incidents',
  dispatchDesc:'Review each route and work-point sequence, open the Driver App, replay planned movement, or export standalone HTML manifests.',
  truckSimulation:'Planned-route simulation',allTruckHtml:'Export all driver manifests',fleetMap:'All fleet routes',showAll:'Show all trucks',
  rushTitle:'CSV → validate work points → prepare roads → run the optimizer',
  rushMode:'Import plan from CSV',
  rushCsvHelp:'Requires name, lat, lon, and demand, plus one role=depot row or the current depot.',
  fastCertifiedRoute:'Prepare a constraint-valid initial plan',backgroundCppImprove:'Prepare an initial plan, then continue with the optimizer',
  createStopsOnly:'Create work points only',createAndRoute:'Create work points + run the optimizer',
  randomHint:'Set the work-point count, demand profile, and maximum available trucks',scenarioTitle:'Create work points on roads with verified depot round-trip access',customerCount:'Work-point count',scenarioRadius:'Work-point radius',
  fixedAreaTitle:'Operating area around the depot',fixedAreaDesc:'Add work points inside the prepared area without rebuilding the directed graph.',
  addFromMapHelp:'Bind the point to a road with verified depot round-trip access',importCsvHelp:'Validate every row against the directed graph before saving',
  prepareAreaPrompt:'Prepare or expand the directed graph to validate this work point',prepareAreaPromptHelp:'FleetRoute extracts roads from the selected regional OSM source and expands the operating area to include the selected location.',
  roundTripDepot:'Depot round trip',prepareAroundDepot:'Prepare roads around the depot',
  scenarioFlowTitle:'Create work points → validate roads → prepare an initial plan → run the optimizer',
  scenarioFlowHelp:'The initial plan appears as a dashed route. Ready status appears after the optimizer and result checks finish.',
  operatingSettings:'Basic route settings',objective:'Optimize for',clustering:'Warm-start clustering',parallelInstances:'Maximum parallel workers',
  routeStart:'Fleet departure time',routeStartHelp:'The route clock starts here and continues across waiting, service, travel, and depot returns.',
  maxTripsHelp:'Used only when multi-trip is enabled. Load resets at the depot; time does not.',
  presetCityHelp:'6 km · compact',presetMetroHelp:'12 km · broader',presetRegionHelp:'25 km · heavier',
  judgeMode:'Operations view',fullMode:'Show analysis'
});

// Keep operator-facing promises consistent with pending imports and job states.
Object.assign(I18N.en,{
  planDesc:'Choose the depot and work points from search, the map, or CSV. Pending imports are checked against the road network before routing.',
  importCsvHelp:'Import rows now; road access is checked before routing',
  rushCsvHelp:'Required: name, lat, lon. Demand defaults to 0. Include one role=depot row or use the current depot.',
  scenarioFlowHelp:'Create work points only stops after generation. Create work points + run the optimizer continues through route validation.',
  analyticsTitle:'Review search improvement and solver evidence',
  analyticsDesc:'Inspect best-so-far cost, worker progress, temperature, acceptance, and stagnation. Build figures from saved telemetry without rerunning the optimizer.',
  developerTitle:'Inspect inputs, execution settings, and output files',
  activityTitle:'Review run history, warnings, and saved evidence',
  activityDesc:'Choose a run to inspect its status, timeline, and process logs. Completed route evidence remains available after a failed or cancelled rerun.'
});

const CLUSTER_METHODS = [
  {id:'auto',icon:'A',title:'Auto validated',en:'Road Savings → K-medoids → Sweep → None',badge:'recommended'},
  {id:'road_savings',icon:'S',title:'Road Savings',en:'Road-cost Clarke–Wright; strong warm-start default',badge:'paper'},
  {id:'network_kmedoids',icon:'K',title:'Network K-medoids',en:'Road-matrix medoids and load repair',badge:'road'},
  {id:'sweep',icon:'W',title:'Sweep',en:'Fast angular geographic partition',badge:'fast'},
  {id:'road_spectral_sparse',icon:'Σ',title:'Sparse Road Spectral',en:'Sparse road-spectral research method',badge:'research'},
  {id:'none',icon:'—',title:'No clustering',en:'Let the solver start from Savings directly',badge:'safe'}
];
const PIPELINE_STAGES = [
  ['Operating graph','Reuse the validated graph already held in memory'],
  ['Exact input','Apply approved closures and materialize input.txt'],
  ['Initial plan','Construct and independently validate a feasible starting plan'],
  ['Routing engine','Check the prepared solver cache; rebuild only if the source or compiler changed'],
  ['Clustering','Run only the selected optional warm start'],
  ['Improvement search','Stream the real routing process while keeping the initial plan safe'],
  ['Validate & apply','Apply a valid optimized result, or retain the initial plan without calling routing complete']
];
const VIEW_TITLES = {
  command:['OPERATIONS','Fleet Overview'],plan:['OPERATIONS','Work Points & Depot'],roads:['OPERATIONS','Road Network & Incidents'],clustering:['ANALYSIS','Clustering'],optimize:['OPERATIONS','Route Optimization'],analytics:['ANALYSIS','Convergence'],dispatch:['OPERATIONS','Current Fleet Plan'],developer:['SYSTEM','Data & Runtime'],activity:['EVIDENCE','Run History']
};

let planMap, roadsMap, routesMap, regionMap;
let PLAN_RENDER_KEY='';
let PLAN_LIST_RENDER_KEY='';
let PLAN_FIT_KEY='';
let PLAN_REGION_FIT_KEY='';
let ROADS_REGION_FIT_KEY='';
let ROAD_RENDER_KEY='';
let ROAD_ACCESS_TABLE_KEY='';
let ROUTE_RENDER_KEY='';
let ROAD_GEOJSON_REV=0;
let ROAD_VIEWPORT_KEY='';
let ROAD_NETWORK_ID='';
let ROAD_LOAD_TIMER=null;
let ROAD_REQUEST_SEQ=0;
let ROAD_REQUEST_CONTROLLER=null;
let MAP_RESIZE_OBSERVERS=[];
const DIALOG_RETURN_FOCUS=new WeakMap();
let planMarkers, planAccessLines, planPreviewLayer, planOperatingLayer, roadLayer, roadPlaceLayer, roadOperatingLayer, closureLayer, closurePreviewLayer, routeLayer;
let baseLayers = [];
let MAP_STYLE_MENU_TRIGGER=null;
let REGION_CATALOG=null, REGION_MAP_LAYER=null, REGION_LIBRARY=[], REGION_FORCE_OPEN=false, REGION_COLLAPSE_ON_READY=false, REGION_SEARCH_ACTIVE=-1, REGION_MAP_SCOPE=null, REGION_SEARCH_IDS=new Set(), DELEGATED_UI_BOUND=false;
let STATE_REQUEST_SEQ=0, STATE_APPLIED_SEQ=0;


async function api(path, options={}){
  const timeoutMs=Number(options.timeoutMs)||20000;
  const controller=new AbortController();
  const callerSignal=options.signal;
  const relayAbort=()=>controller.abort(callerSignal?.reason);
  if(callerSignal?.aborted)relayAbort();else if(callerSignal)callerSignal.addEventListener('abort',relayAbort,{once:true});
  const timer=setTimeout(()=>controller.abort(new DOMException('Request timeout','TimeoutError')),timeoutMs);
  const headers = {'Content-Type':'application/json', ...(options.headers||{})};
  const requestOptions={...options,headers,signal:controller.signal};delete requestOptions.timeoutMs;
  try{
    const response = await fetch(path,requestOptions);
    const type=response.headers.get('content-type')||'';
    const body=type.includes('application/json')?await response.json():await response.text();
    if(!response.ok) throw new Error(requestErrorMessage(body,response.status));
    return body;
  }catch(error){
    if(controller.signal.aborted&&!callerSignal?.aborted)throw new Error(`FleetRoute did not respond within ${Math.ceil(timeoutMs/1000)} seconds.`);
    throw error;
  }finally{
    clearTimeout(timer);if(callerSignal)callerSignal.removeEventListener('abort',relayAbort);
  }
}
function revealDialog(modal,focusSelector){
  if(!modal)return;
  if(modal.classList.contains('hidden'))DIALOG_RETURN_FOCUS.set(modal,document.activeElement);
  modal.classList.remove('hidden');
  document.body.classList.add('dialog-open');
  requestAnimationFrame(()=>$(focusSelector,modal)?.focus());
}
function dismissDialog(modal){
  if(!modal)return;
  modal.classList.add('hidden');
  if(!$$('.modal-backdrop,.lightbox').some(item=>!item.classList.contains('hidden')))document.body.classList.remove('dialog-open');
  const previous=DIALOG_RETURN_FOCUS.get(modal);DIALOG_RETURN_FOCUS.delete(modal);
  if(previous&&document.contains(previous)&&typeof previous.focus==='function')previous.focus();
}
function setConnectionState(online,detail=''){
  CONNECTION_ONLINE=!!online;
  if(online)CONNECTION_FAILURES=0;else CONNECTION_FAILURES+=1;
  const banner=$('#connectionBanner'),pulse=$('.project-card .pulse'),label=$('#systemConnectionText');
  $('#appShell')?.classList.toggle('connection-lost',!online);
  if(banner)banner.classList.toggle('hidden',online);
  if(pulse){pulse.classList.toggle('connecting',!online);pulse.classList.toggle('offline',!online&&CONNECTION_FAILURES>0);}
  if(label)label.textContent=online?(LANG==='th'?'':'System connected'):(LANG==='th'?'':'Reconnecting');
  if(!online){
    const title=$('#connectionBannerTitle'),body=$('#connectionBannerDetail');
    if(title)title.textContent=LANG==='th'?' FleetRoute  — ':'FleetRoute is unavailable — retrying';
    if(body)body.textContent=detail||(LANG==='th'?'  “”  Colab runtime ':'The last known screen is preserved. Retry when the Colab runtime is ready.');
    if(!STATE){const status=$('#projectStatus'),meta=$('#projectMeta');if(status)status.textContent=LANG==='th'?' Runtime ':'Runtime not connected';if(meta)meta.textContent=detail||'Waiting for FleetRoute';}
  }
}
function esc(value=''){return String(value).replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));}
function logTone(line=''){
  const text=String(line),lower=text.toLowerCase();
  const receipt=/\[(clusterwarmstartreceipt|solverconfig|savingswarmstart|budgetfillportfolio|earlylnsreceipt)\]/i.test(text);
  if(receipt&&/(accepted=false|hard_feasible=false|rejected=true)/i.test(text))return'log-receipt log-warning';
  if(receipt&&/(accepted=true|hard_feasible=true)/i.test(text))return'log-receipt log-success';
  if(/\b(fatal|error|failure|failed|exception|traceback|launch_failed|state=failed)\b/i.test(text)||lower.includes('violates the process evidence contract'))return'log-error';
  if(/\b(warn(?:ing)?|timeout|cancelled|fallback|rejected|skipped|stagnat(?:ion|ed)|no improvement)\b/i.test(text))return'log-warning';
  if(/\b(succeeded|success|passed|published|complete(?:d)?|ready)\b/i.test(text)||/(accepted=true|hard_feasible=true|state=succeeded)/i.test(text))return'log-success';
  if(receipt)return'log-receipt';
  if(/\[(solverlive|fleetrouteprogress|fleetrouteprocess|earlylns|solverconfig)\]/i.test(text))return'log-telemetry';
  if(/^\s*(?:={3,}|-{3,}|[A-Z][A-Z0-9 _/·.:-]{4,})\s*$/.test(text))return'log-section';
  return'';
}
function friendlyLogLine(line=''){
  let value=String(line||'');
  const tags=[
    [/\[PhaseEngine(?:-[^\]]+)?\]/gi,'[Search]'],
    [/\[EliteEvolution\]/gi,'[Refinement]'],
    [/\[SavingsWarmStart\]/gi,'[Initial route]'],
    [/\[ClusterWarmStartReceipt\]/gi,'[Warm start]'],
    [/\[SolverConfig\]/gi,'[Optimizer]'],
    [/\[SolverLive\]/gi,'[Optimizer]'],
    [/\[FleetRouteProgress\]/gi,'[Progress]'],
    [/\[FleetRouteProcess\]/gi,'[Process]'],
    [/\[EarlyLNS[^\]]*\]/gi,'[Search]'],
    [/\[BudgetFillPortfolio\]/gi,'[Search]'],
  ];
  for(const [pattern,label] of tags)value=value.replace(pattern,label);
  value=value
    .replace(/Current\/E36/gi,'routing optimizer')
    .replace(/V3\.1/gi,'FleetRoute')
    .replace(/Early[-_ ]?LNS/gi,'search')
    .replace(/phase[-_ ]engine/gi,'adaptive search')
    .replace(/phase[-_ ]specialized/gi,'adaptive')
    // Keep internal telemetry generation suffixes out of the operator console.
    // Raw evidence files remain byte-for-byte unchanged on disk.
    .replace(/\[([^\]\r\n]*?)-V\d+(?:\.\d+)?\]/gi,'[$1]')
    .replace(/\b(Staged portfolio layout\s*:\s*)v\d+(?:\.\d+)?\b/gi,'$1production')
    .replace(/\bC\+\+ optimizer\b/gi,'optimizer');
  return value;
}
function logMarkup(text='',placeholder=''){
  const source=String(text||placeholder||'');
  return source.split(/\r?\n/).map(raw=>{const line=friendlyLogLine(raw);return`<span class="log-row ${logTone(raw)}">${line?esc(line):'&nbsp;'}</span>`;}).join('');
}
function renderLogInto(element,text,placeholder=''){if(element)element.innerHTML=logMarkup(text,placeholder);}
function normalizeCandidate(place){
  const lat=Number(place?.lat),lon=Number(place?.lon);
  if(!Number.isFinite(lat)||!Number.isFinite(lon)||lat<-90||lat>90||lon<-180||lon>180){
    throw new Error(LANG==='th'?' ':'The selected place has invalid coordinates. Choose the search result again.');
  }
  return {...place,lat,lon,name:String(place?.name||'Selected place'),address:String(place?.address||place?.display_name||'')};
}
function num(v,d=0){const n=Number(v);return Number.isFinite(n)?n.toLocaleString(undefined,{minimumFractionDigits:d,maximumFractionDigits:d}):'—';}
function km(m){return Number.isFinite(+m)?`${num(+m/1000,1)} km`:'—';}
function mins(s){return Number.isFinite(+s)?`${num(+s/60,0)} min`:'—';}
function rel(date){if(!date)return'—';const ms=Date.now()-new Date(date).getTime(),s=Math.max(0,ms/1000);if(s<60)return`${Math.floor(s)}s`;if(s<3600)return`${Math.floor(s/60)}m`;if(s<86400)return`${Math.floor(s/3600)}h`;return new Date(date).toLocaleDateString(LANG==='th'?'th-TH':'en-GB');}
function timeToSeconds(v){if(!v)return 0;const[h,m]=v.split(':').map(Number);return h*3600+m*60;}
function secondsToTime(v){v=Math.max(0,Number(v)||0);return`${String(Math.floor(v/3600)%24).padStart(2,'0')}:${String(Math.floor(v%3600/60)).padStart(2,'0')}`;}
function toast(title,detail='',error=false){const el=$('#toast');el.classList.toggle('error',error);el.setAttribute('role',error?'alert':'status');el.setAttribute('aria-live',error?'assertive':'polite');$('strong',el).textContent=title;$('span',el).textContent=detail;el.classList.add('show');clearTimeout(window.__toast);window.__toast=setTimeout(()=>el.classList.remove('show'),error?6000:3800);}
function motionBehavior(){return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches?'auto':'smooth';}
function setMenuOpen(open){
  const shell=$('#appShell'),button=$('#mobileMenuBtn');if(!shell||!button)return;
  shell.classList.toggle('menu-open',!!open);button.setAttribute('aria-expanded',String(!!open));
  button.setAttribute('aria-label',open?(LANG==='th'?'':'Close navigation'):(LANG==='th'?'':'Open navigation'));
}
function loading(show,title=tr('loading'),detail=''){const el=$('#loadingOverlay');el.classList.toggle('hidden',!show);$('#loadingTitle').textContent=title;$('#loadingDetail').textContent=detail;}
function latestRoutes(){return STATE?.latest_routes?.payload?.routes || [];}
function latestVersion(){return STATE?.latest_routes?.id || null;}
function latestJob(){return (STATE?.jobs||[])[0]||null;}
function activeSolverJob(){return (STATE?.jobs||[]).find(job=>['solve','network-and-solve'].includes(job.kind)&&['queued','running'].includes(job.status))||null;}
function routeOperationalState(){
  const routeState=STATE?.route_state||{},workflow=STATE?.workflow||{},routes=latestRoutes();
  const hasRoute=routes.length>0&&!!(routeState.route_version||latestVersion());
  const stale=hasRoute&&routeState.stale!==false;
  const solverJob=activeSolverJob();
  const source=String(routeState.solution_source||STATE?.latest_routes?.payload?.solution_source||'');
  const completed=!!(routeState.optimization_completed||routeState.optimization_checked_at||source==='cpp_optimizer'||workflow.completed?.optimization_completed);
  const outcome=String(routeState.optimization_outcome||workflow.optimization_outcome||'not_started');
  if(stale)return{phase:'stale',icon:'!',badge:'UPDATE NEEDED',hasRoute,completed:false,title:LANG==='th'?'':'This plan needs an update',detail:LANG==='th'?'  ':'Work points, roads, or fleet settings have changed.'};
  if(solverJob&&hasRoute)return{phase:'running',icon:'◆',badge:'OPTIMIZING',hasRoute,completed:false,savedPlanCompleted:completed,title:LANG==='th'?'':'Optimizing routes',detail:LANG==='th'?`Route v${latestVersion()} · `:`Route v${latestVersion()} · the saved plan remains visible during search.`};
  if(solverJob)return{phase:'running',icon:'◆',badge:'PREPARING',hasRoute:false,completed:false,title:LANG==='th'?'':'Preparing the initial plan',detail:LANG==='th'?'':'Checking the road graph and constraints.'};
  if(!hasRoute)return{phase:'empty',icon:'◇',badge:'NOT STARTED',hasRoute:false,completed:false,title:LANG==='th'?'':'No fleet plan yet',detail:LANG==='th'?'':'Start with a depot and work points.'};
  if(!completed)return{phase:'prepared',icon:'△',badge:'INITIAL PLAN',hasRoute:true,completed:false,title:LANG==='th'?'':'Initial plan ready for review',detail:LANG==='th'?`Route v${latestVersion()} ·  Optimizer`:`Route v${latestVersion()} · next: optimizer.`};
  if(source==='cpp_optimizer'||outcome==='improved_route_published')return{phase:'optimized',icon:'✓',badge:'OPTIMIZED',hasRoute:true,completed:true,title:LANG==='th'?'':'Fleet plan ready',detail:LANG==='th'?`Route v${latestVersion()} ·  Optimizer `:`Route v${latestVersion()} · optimizer result validated.`};
  return{phase:'reviewed',icon:'✓',badge:'READY',hasRoute:true,completed:true,title:LANG==='th'?'':'Fleet plan ready',detail:LANG==='th'?`Route v${latestVersion()} · Optimizer `:`Route v${latestVersion()} · optimizer review selected this plan.`};
}
function cards(items){return items.map(([label,value,detail,state=''])=>`<div class="metric-card ${state}"><span>${esc(label)}</span><strong>${esc(value)}</strong><small>${esc(detail||'')}</small></div>`).join('');}
function artifactUrl(url){return url ? withToken(url) : '#';}


function renderView(view=currentView){
  const renderers={command:renderCommand,plan:renderPlan,roads:renderRoads,clustering:renderClustering,optimize:renderOptimize,dispatch:renderDispatch,developer:renderDeveloper,activity:renderActivity};
  const renderer=renderers[view];if(renderer)renderer();
}
function renderAll(){if(!STATE)return;renderTop();renderView(currentView);renderRegionSetup();applyMapTheme(false);renderLiveOptimizerDock();} 


function browsedRegion(){return STATE?.osm_browse?.region||STATE?.osm_source?.region||null;}
function activeRegion(){return STATE?.osm_source?.region||null;}
function activeSourceOperational(){const c=STATE?.osm_source_coverage||{},hasPlan=(STATE?.places||[]).length>0;return !!STATE?.osm_source?.ready&&(!hasPlan||(c.known===true&&c.covers_all===true));}
function sourceCoverageMismatch(){const c=STATE?.osm_source_coverage||{};return !!STATE?.osm_source?.ready&&c.known===true&&c.covers_all===false;}
function sourceCoverageUnverified(){const c=STATE?.osm_source_coverage||{};return !!STATE?.osm_source?.ready&&(STATE?.places||[]).length>0&&c.known!==true;}
function openMatchingRegion(message='The active road source does not cover the current depot and work points.'){
  REGION_FORCE_OPEN=true;activate('command');renderRegionSetup();
  toast('Choose a matching road region',message,true);
}
async function openMatchingRegionForDepot(depot,message='The selected depot is outside the active road source.'){
  REGION_FORCE_OPEN=true;activate('command');renderRegionSetup();
  const activeName=STATE?.osm_source?.region?.name||'the active road source';
  try{
    const recommendation=await api(`/api/osm/recommend?lat=${encodeURIComponent(depot.lat)}&lon=${encodeURIComponent(depot.lon)}`,{timeoutMs:22000});
    const country=recommendation?.country||null,target=recommendation?.recommended_region||country;
    if(target?.id){
      // If a country is split into downloadable subregions, zoom into that
      // country first so the automatically selected extract is actually visible.
      if(country?.id&&target.id!==country.id&&regionFeature(country.id)){
        REGION_MAP_SCOPE=country.id;drawRegionCatalog();updateRegionMapBack();
      }
      REGION_SEARCH_IDS=new Set([country?.id,target.id].filter(Boolean));
      const selected=await chooseOperatingRegion(target.id,{fit:true,collapseIfReady:false,announce:false});
      if(selected){
        const input=$('#regionSearch');if(input)input.value=country?.name||target.name||'';
        if(REGION_MAP_LAYER)REGION_MAP_LAYER.setStyle(regionMapStyle);
        const detected=country?.name||target.name||'the matching region';
        const extract=target.name||target.id;
        showResult({
          type:'warn',
          title:'Depot is outside the active road source',
          message:`${message} FleetRoute detected ${detected} and preselected ${extract} in Road-source setup. Nothing has been downloaded or activated yet.`,
          details:[['Current source',activeName],['Detected country / region',detected],['Suggested road extract',extract],['Next step',selected.ready?'Use the verified cached source':'Download & verify the selected source']],
          primary:'Continue to road-source setup'
        });
        setTimeout(()=>$('#regionSourceDrawer')?.scrollIntoView({behavior:motionBehavior(),block:'start'}),80);
        return recommendation;
      }
    }
    showResult({type:'warn',title:'Depot is outside the active road source',message:`${message} FleetRoute could not prove a matching downloadable extract from the current boundary catalog. Choose the depot's region in Road-source setup.`});
  }catch(error){
    showResult({type:'warn',title:'Depot is outside the active road source',message:`${message} Open Road-source setup and choose a region that contains the depot. (${friendlyError(error.message)})`});
  }
  toast('Choose a matching road region','The depot is saved, but road preparation is blocked until a matching regional source is selected.',true);
  return null;
}
function closeDistanceRisk(confirmed=false){
  const modal=$('#distanceRiskModal');if(!modal)return;
  const resolve=DISTANCE_RISK_RESOLVE;DISTANCE_RISK_RESOLVE=null;dismissDialog(modal);
  if(resolve)resolve(!!confirmed);
}
function confirmDistanceRisk(actionLabel='continue'){
  const d=STATE?.plan_distance_check||{};if(!d.available||!d.warning)return Promise.resolve(true);
  // Never stack confirmations. A second request while this modal is open is a
  // duplicate action and should not silently get a separate approval path.
  if(DISTANCE_RISK_RESOLVE)return Promise.resolve(false);
  const farthest=d.farthest?.name||'a work point',farKm=(Number(d.farthest_m||0)/1000).toFixed(1),thresholdKm=(Number(d.warning_threshold_m||0)/1000).toFixed(1);
  const count=Number(d.far_count||0),severity=d.severe?'Unusually large operating span':'Large operating span';
  $('#distanceRiskHeadline').textContent=severity;
  $('#distanceRiskMessage').textContent=`${count} work point${count===1?' is':'s are'} farther than ${thresholdKm} km straight-line from the depot.`;
  $('#distanceRiskFacts').innerHTML=`<div><span>Farthest work point</span><b>${esc(farthest)}</b></div><div><span>Straight-line distance</span><b>${esc(farKm)} km</b></div><div><span>Warning threshold</span><b>${esc(thresholdKm)} km</b></div><div><span>Requested action</span><b>${esc(actionLabel)}</b></div>`;
  $('#distanceRiskContinue').textContent=`Continue to ${actionLabel}`;
  return new Promise(resolve=>{
    DISTANCE_RISK_RESOLVE=resolve;
    revealDialog($('#distanceRiskModal'),'#distanceRiskContinue');
  });
}
function readiness(){
  const p=STATE.places||[],d=p.some(x=>x.role==='depot'),c=p.filter(x=>x.role==='customer').length>0;
  const source=activeSourceOperational();
  const n=!!STATE.network?.access_ready&&!STATE.network_stale?.stale;
  const access=p.length>0&&p.every(x=>!!x.access_verified);
  const route=routeOperationalState(),r=route.hasRoute,opt=route.completed&&!STATE.route_state?.stale;
  return{source,d,c,n,access,r,opt,score:[source,d&&c,n&&access,r,opt].filter(Boolean).length/5*100};
}
function renderCommand(){
  const ready=readiness(),places=STATE.places||[],customers=places.filter(p=>p.role==='customer'),routes=latestRoutes(),job=latestJob(),source=STATE.osm_source||{},routeStatus=routeOperationalState();
  const readinessPct=clampPercent(ready.score);$('#heroReadiness').textContent=percentText(readinessPct);$('#heroReadinessBar').style.width=`${readinessPct}%`;
  $('#commandMetrics').innerHTML=cards([
    [LANG==='th'?'':'Work points',num(customers.length),places.length?`${places.filter(p=>p.access_verified).length}/${places.length} ${LANG==='th'?'':'ready on the road graph'}`:(LANG==='th'?'':'No plan'),customers.length?'good':'warn'],
    ['Directed graph',STATE.network&&!STATE.network_stale?.stale?num(STATE.network.nodes):'—',STATE.network&&!STATE.network_stale?.stale?`${num(STATE.network.edges)} directed edges`:(ready.source?('Ready to prepare from regional data'):sourceCoverageMismatch()?'Active source does not cover this plan':(LANG==='th'?'':'Road data not installed')),STATE.network&&!STATE.network_stale?.stale?'good':'warn'],
    [LANG==='th'?'':'Fleet-plan state',routeStatus.badge,latestVersion()?`Route v${latestVersion()} · ${routeStatus.title}`:routeStatus.detail,routeStatus.phase==='optimized'||routeStatus.phase==='reviewed'?'good':routeStatus.phase==='stale'?'bad':'warn'],
    [LANG==='th'?'':'Active trucks',num(routes.length),routes.length?`${routes.reduce((sum,route)=>sum+(route.stops||[]).filter(stop=>stop.kind!=='depot').length,0)} ${LANG==='th'?'':'scheduled stops'}`:(LANG==='th'?'':'Awaiting fleet plan'),routes.length?'good':''],
    [LANG==='th'?'':'Road incidents',num((STATE.closures||[]).filter(item=>item.status==='approved').length),`${num((STATE.closures||[]).filter(item=>item.status==='pending').length)} ${LANG==='th'?'':'pending review'}`,(STATE.closures||[]).some(item=>item.status==='pending')?'warn':'good']
  ]);
  const wf=STATE.workflow||{},wc=wf.completed||{},next=wf.next_action||{};
  const steps=[
    [!!wc.source,'source',LANG==='th'?'':'regional road data',source.ready?(LANG==='th'?'':'Installed and verified'):('Choose and verify region'),'roads'],
    [!!wc.depot&&!!wc.customers,'places',LANG==='th'?'':'Depot and work points',`${customers.length} ${LANG==='th'?'':'work points'}`,'plan'],
    [!!wc.graph&&!!wc.access,'network',LANG==='th'?'Directed Graph  Road access':'Directed graph and road access',wc.graph?(LANG==='th'?` · ${num(STATE.network?.nodes)} nodes`:`Ready · ${num(STATE.network?.nodes)} nodes`):(LANG==='th'?'':'Prepared when routing starts'),'roads'],
    [!!wc.route_prepared,'route',LANG==='th'?'':'Initial plan',wc.route_prepared?`Route v${wf.route_version||latestVersion()||'—'} · ${LANG==='th'?'':'ready for review'}`:(LANG==='th'?'':'Awaiting preparation'),'optimize'],
    [!!wc.optimization_current,'solver',LANG==='th'?' Optimizer':'Optimized result',wc.optimization_current?(LANG==='th'?'':'Ready for use'):(wc.route_prepared?(LANG==='th'?' Optimizer':'Awaiting optimizer result'):(job?.message||next.label||'Waiting')),'optimize']
  ];
  const firstOpen=steps.findIndex(x=>!x[0]);
  $('#workflowSteps').innerHTML=steps.map(([done,key,title,detail,view],i)=>`<div class="workflow-step ${done?'done':i===firstOpen?'active':''}"><i>${done?'✓':i+1}</i><div><b>${esc(title)}</b><small>${esc(detail)}</small></div><button data-go="${view}" data-workflow-step="${key}">${done?(LANG==='th'?'':'View'):(LANG==='th'?'':'Open')} →</button></div>`).join('');
  if(job){$('#latestRunStatus').className=`status-chip ${job.status}`;$('#latestRunStatus').textContent=localizeStatus(job.status);$('#latestRunCard').classList.remove('empty-state');$('#latestRunCard').innerHTML=`<div class="run-number">#${job.id}</div><b>${esc(localizeJobKind(job.kind))}</b><p>${esc(friendlyError(job.message))}</p><div class="run-progress"><i style="width:${jobProgress(job)}%"></i></div><small>${rel(job.created_at)} · ${esc(localizeStatus(job.status))}</small>`;}else{$('#latestRunStatus').className='status-chip idle';$('#latestRunStatus').textContent=LANG==='th'?'':'Idle';$('#latestRunCard').classList.add('empty-state');$('#latestRunCard').innerHTML=LANG==='th'?' ':'Define a depot and work points, or open the example scenario.';}
  const gallery=(STATE.artifact_gallery||[]).slice(0,7);$('#commandArtifacts').innerHTML=gallery.length?gallery.map(a=>`<div class="artifact-thumb" data-image="${artifactUrl(a.url)}" data-caption="${esc(a.name)}"><img src="${artifactUrl(a.url)}"><b>${esc(a.name)}</b></div>`).join(''):`<div class="empty-state">${tr('noData')}</div>`;
  renderRouteLifecycle(routeStatus,wc);
  renderCommandMap(routeStatus);
  bindDynamicNavigation();bindImages();
}

function renderRouteLifecycle(status,completed){
  const buttons=$$('#routeLifecycle [data-stage]');
  const stageDone={plan:!!completed.depot&&!!completed.customers,graph:!!completed.graph&&!!completed.access,prepared:!!completed.route_prepared,optimized:!!completed.optimization_current,dispatch:!!completed.optimization_current};
  const firstOpen=['plan','graph','prepared','optimized','dispatch'].find(stage=>!stageDone[stage]);
  buttons.forEach(button=>{const stage=button.dataset.stage;button.classList.toggle('done',!!stageDone[stage]);button.classList.toggle('active',stage===firstOpen||(stage==='prepared'&&status.phase==='prepared')||(stage==='optimized'&&['running','optimized','reviewed'].includes(status.phase)&&!stageDone.dispatch));button.classList.toggle('prepared',stage==='prepared');});
  $('#lifecycleHeadline').textContent=status.title;$('#lifecycleDetail').textContent=status.detail;
  const card=$('#commandRouteState');card.className=`command-route-state ${status.phase}`;$('strong',card).textContent=status.title;$('small',card).textContent=status.detail;
  $('#commandMapClock').textContent=new Intl.DateTimeFormat(LANG==='th'?'th-TH':'en-GB',{hour:'2-digit',minute:'2-digit'}).format(new Date());
}

function renderCommandMap(status){
  if(!commandMap||!commandRouteLayer||!commandStopLayer)return;
  const routes=latestRoutes(),places=STATE.places||[];
  const key=JSON.stringify([latestVersion(),status.phase,routes.map(route=>[route.truck_id,route.geometry?.length,route.stops?.length]),places.map(place=>[place.id,place.lat,place.lon,place.role])]);
  if(key===COMMAND_MAP_KEY)return;COMMAND_MAP_KEY=key;commandRouteLayer.clearLayers();commandStopLayer.clearLayers();
  const bounds=[];
  if(routes.length){
    const initial=['prepared','running'].includes(status.phase),stale=status.phase==='stale';
    // Halos first, then colored route strokes: overlapping routes stay legible.
    routes.forEach((route,i)=>{if(!route.geometry?.length)return;const outline={color:stale?'#f7f2f0':'#fff',weight:7.5,opacity:.9,lineCap:'round',lineJoin:'round',interactive:false,pane:'route-halo'};if(initial)outline.dashArray='10 7';L.polyline(route.geometry,outline).addTo(commandRouteLayer);});
    routes.forEach((route,i)=>{const color=stale?'#9a655e':ROUTE_COLORS[i%ROUTE_COLORS.length],lineStyle={color,weight:4.2,opacity:initial ? .82 : .94,lineCap:'round',lineJoin:'round',interactive:false,pane:'route-main'};if(initial)lineStyle.dashArray='10 7';if(route.geometry?.length){L.polyline(route.geometry,lineStyle).addTo(commandRouteLayer);bounds.push(...route.geometry);}for(const stop of route.stops||[]){const depot=stop.kind==='depot';L.circleMarker([+stop.lat,+stop.lon],{radius:depot?6.2:4,color:'#fff',weight:depot?2.4:1.8,fillColor:depot?'#0b3145':color,fillOpacity:1,interactive:false,pane:'fleet-stops'}).addTo(commandStopLayer);}});
  }else{
    places.forEach(place=>{if(!Number.isFinite(+place.lat)||!Number.isFinite(+place.lon))return;const depot=place.role==='depot';bounds.push([+place.lat,+place.lon]);L.circleMarker([+place.lat,+place.lon],{radius:depot?6:4,color:'#fff',weight:depot?2.2:1.7,fillColor:depot?'#0b6d65':'#ef8c2f',fillOpacity:1,interactive:false}).addTo(commandStopLayer);});
  }
  requestAnimationFrame(()=>{commandMap.invalidateSize({pan:false});if(bounds.length>1)commandMap.fitBounds(bounds,{padding:[32,32],animate:false,maxZoom:14});else if(bounds.length===1)commandMap.setView(bounds[0],13,{animate:false});});
}

function placeMarkerIcon(place,index=0){
  const depot=place.role==='depot';
  const verified=!!place.access_verified;
  const label=depot?'D':String(index+1);
  return L.divIcon({
    className:'fleet-map-icon-wrap',
    html:`<span class="fleet-map-icon ${depot?'depot':'customer'} ${verified?'verified':'pending'}"><i>${depot?'⌂':label}</i></span>`,
    iconSize:[depot?38:32,depot?38:32],
    iconAnchor:[depot?19:16,depot?19:16],
    popupAnchor:[0,depot?-21:-18],
    tooltipAnchor:[0,depot?-20:-18],
  });
}
function accessMarkerIcon(valid=true){
  return L.divIcon({
    className:'fleet-map-icon-wrap',
    html:`<span class="fleet-access-icon ${valid?'valid':'invalid'}"></span>`,
    iconSize:[16,16],iconAnchor:[8,8],popupAnchor:[0,-10],
  });
}
function previewMarkerIcon(role='customer'){
  const depot=role==='depot';
  return L.divIcon({
    className:'fleet-map-icon-wrap',
    html:`<span class="fleet-preview-icon ${depot?'depot':''}">${depot?'D':'+'}</span>`,
    iconSize:[40,40],iconAnchor:[20,20],popupAnchor:[0,-22],
  });
}


function regionBoundsForOperationalContext(){
  if(!REGION_CATALOG)return null;
  const region=(activeSourceOperational()?activeRegion():browsedRegion())||activeRegion();
  if(!region?.id)return null;
  const feature=regionFeature(region.id);if(!feature?.geometry)return null;
  try{const bounds=L.geoJSON(feature).getBounds();return bounds.isValid()?{id:region.id,bounds}:null;}catch{return null;}
}
function fitPlanRegionContext(force=false){
  if(!planMap||selectedCandidate||(STATE?.places||[]).length)return false;
  const context=regionBoundsForOperationalContext();if(!context)return false;
  if(!force&&PLAN_REGION_FIT_KEY===context.id)return true;
  PLAN_REGION_FIT_KEY=context.id;
  requestAnimationFrame(()=>{planMap.invalidateSize({pan:false});planMap.fitBounds(context.bounds,{padding:[34,34],maxZoom:7,animate:false});});
  return true;
}
function fitRoadsRegionContext(force=false){
  if(!roadsMap||STATE?.network||((STATE?.places||[]).length>0))return false;
  const context=regionBoundsForOperationalContext();if(!context)return false;
  if(!force&&ROADS_REGION_FIT_KEY===context.id)return true;
  ROADS_REGION_FIT_KEY=context.id;
  requestAnimationFrame(()=>{roadsMap.invalidateSize({pan:false});roadsMap.fitBounds(context.bounds,{padding:[34,34],maxZoom:7,animate:false});});
  return true;
}

function renderPlan(){
  const places=STATE.places||[],customers=places.filter(p=>p.role==='customer'),depot=places.find(p=>p.role==='depot');
  renderOperatingArea(planOperatingLayer,depot);
  const sourceReady=activeSourceOperational(),graphReady=!!STATE.network?.access_ready&&!STATE.network_stale?.stale;
  const depotVerified=!!depot?.access_verified,customersVerified=customers.length>0&&customers.every(p=>!!p.access_verified);
  const allVerified=depotVerified&&customersVerified;
  $('#planSummary').textContent=`${depot?1:0} depot · ${customers.length} ${LANG==='th'?'':'work points'} · demand ${num(customers.reduce((s,p)=>s+(+p.demand||0),0),1)}`;
  const stateCard=(id,ok,title,detail)=>{const el=$(id);if(!el)return;el.classList.toggle('pass',!!ok);el.classList.toggle('warn',!ok);$('i',el).textContent=ok?'✓':$('i',el).textContent.replace('✓','')||'•';$('small',el).textContent=detail;};
  stateCard('#planSourceState',sourceReady,'Regional road source',sourceReady?`${STATE.osm_source.size_human||''} · verified`:(sourceCoverageUnverified()?'Boundary check required':'Open Roads & incidents'));
  stateCard('#planDepotState',!!depot,'Depot',depot?depot.name:'Choose a real depot');
  stateCard('#planNetworkState',graphReady,'Operating graph',graphReady?`${num(STATE.network.nodes)} nodes · ${num(STATE.network.edges)} edges`:(depot?'Prepare roads around depot':'Waiting for depot'));
  stateCard('#planAccessState',allVerified,LANG==='th'?'Road access ':'Validated road access',allVerified?`Depot + ${customers.length} ${LANG==='th'?'':'work points reachable'}`:`${places.filter(p=>!p.access_verified).length} ${LANG==='th'?'':'locations pending'}`);
  const planListKey=places.map(p=>[p.id,p.role,p.name,p.address,+p.lat,+p.lon,!!p.access_verified,p.access_road,+p.access_distance_m].join(':')).join('|');
  if(planListKey!==PLAN_LIST_RENDER_KEY){
    PLAN_LIST_RENDER_KEY=planListKey;let customerCardIndex=0;
    $('#planList').innerHTML=places.length?places.map(p=>{
      const idx=p.role==='customer'?customerCardIndex++:-1,verified=!!p.access_verified;
      return `<div class="place-card ${p.role} ${verified?'verified':'pending'}"><div class="place-icon">${p.role==='depot'?'D':String(idx+1).padStart(2,'0')}</div><div class="place-card-copy"><div class="place-title-row"><b>${esc(p.name)}</b><span class="mini-status ${verified?'pass':'warn'}">${verified?'reachable':'pending'}</span></div><p>${esc(p.address||`${Number(p.lat).toFixed(5)}, ${Number(p.lon).toFixed(5)}`)}</p><div class="place-access-line"><i></i><span>${verified?`${esc(p.access_road||'Road')} · ${num(p.access_distance_m,0)} m`:(LANG==='th'?'':'Requires road validation')}</span></div></div><div class="place-actions"><button type="button" data-ui-action="focus-place" data-place-id="${p.id}" title="Map" aria-label="Show ${esc(p.name)} on map">⌖</button><button type="button" data-ui-action="edit-place" data-place-id="${p.id}" title="Edit" aria-label="Edit ${esc(p.name)}">✎</button><button type="button" data-ui-action="delete-place" data-place-id="${p.id}" title="Remove" aria-label="Remove ${esc(p.name)}">×</button></div></div>`;
    }).join(''):`<div class="empty-state"><b>${LANG==='th'?'':'Start by choosing a depot'}</b><p>${LANG==='th'?' operating graph ':'Then prepare the operating graph before adding work points from the map.'}</p></div>`;
  }
  const renderKey=places.map(p=>[p.id,p.role,+p.lat,+p.lon,!!p.access_verified,+p.access_lat,+p.access_lon,p.name,p.access_road,+p.access_distance_m].join(':')).join('|');
  const fitKey=places.map(p=>[p.id,+p.lat,+p.lon].join(':')).join('|');
  if(renderKey!==PLAN_RENDER_KEY){
    PLAN_RENDER_KEY=renderKey;planMarkers.clearLayers();planAccessLines.clearLayers();
    const bounds=[];let customerIndex=0;
    places.forEach(p=>{
      const index=p.role==='customer'?customerIndex++:0;
      const marker=L.marker([+p.lat,+p.lon],{icon:placeMarkerIcon(p,index),keyboard:true,riseOnHover:true});
      marker.bindTooltip(`<div class="place-map-tooltip"><b>${esc(p.name)}</b><span>${p.role==='depot'?'Depot':'Work point'} · ${p.access_verified?'road access verified':'access pending'}</span></div>`,{direction:'top',offset:[0,-10],className:'fleet-map-tooltip'});
      marker.bindPopup(`<div class="fleet-popup"><span>${p.role==='depot'?'DEPOT':'WORK POINT'}</span><b>${esc(p.name)}</b><small>${p.access_verified?`${esc(p.access_road)} · ${num(p.access_distance_m,0)} m`:(LANG==='th'?'':'Road access pending')}</small></div>`);
      marker.addTo(planMarkers);bounds.push([+p.lat,+p.lon]);
      if(p.access_verified&&p.access_lat!=null&&p.access_lon!=null){
        const accessLine=[[+p.lat,+p.lon],[+p.access_lat,+p.access_lon]];
        L.polyline(accessLine,{pane:'access',color:'#fff',weight:4.4,opacity:.92,interactive:false}).addTo(planAccessLines);
        L.polyline(accessLine,{pane:'access',color:'#c68a20',weight:2,dashArray:'5 5',opacity:.9,interactive:false}).addTo(planAccessLines);
        L.marker([+p.access_lat,+p.access_lon],{icon:accessMarkerIcon(true),interactive:false,pane:'fleet-stops'}).addTo(planAccessLines);
        bounds.push([+p.access_lat,+p.access_lon]);
      }
    });
    if(bounds.length&&currentView==='plan'&&!selectedCandidate&&fitKey!==PLAN_FIT_KEY){
      PLAN_FIT_KEY=fitKey;
      requestAnimationFrame(()=>{planMap.invalidateSize({pan:false});planMap.fitBounds(bounds,{padding:[42,42],maxZoom:16,animate:false});});
    }
  }
  if(!places.length)fitPlanRegionContext(false);
  renderAccessInspector();
  renderGuidedNext();
}

function openScenarioBuilder(){
  activate('plan');$('#scenarioBuilder')?.classList.remove('hidden');updateScenarioSummary();
  setTimeout(()=>$('#scenarioBuilder')?.scrollIntoView({behavior:'smooth',block:'center'}),80);
}
function focusDepotSearch(){activate('plan');setTimeout(()=>{$('#searchQuery')?.focus();$('#searchQuery')?.scrollIntoView({behavior:'smooth',block:'center'});},80);}
function guidedStepsState(){
  const wf=STATE?.workflow||{},c=wf.completed||{},places=STATE?.places||[],depot=places.find(p=>p.role==='depot'),customers=places.filter(p=>p.role==='customer');
  return {source:!!c.source,depot,customers,graph:!!c.graph,access:!!c.access,route:!!c.route,optimizationCurrent:!!c.optimization_current,next:wf.next_action||{}};
}
function focusWorkPointEntry(){
  activate('plan');
  setTimeout(()=>{
    const tools=$('.quick-tools-v2')||$('#importCsvBtn')?.closest('.quick-tools');
    const rail=tools||$('.search-rail-v2');
    rail?.scrollIntoView({behavior:'smooth',block:'center'});
    if(tools){tools.classList.remove('workflow-focus-pulse');void tools.offsetWidth;tools.classList.add('workflow-focus-pulse');setTimeout(()=>tools.classList.remove('workflow-focus-pulse'),1800);}
    toast('Add or import work points','Search a place, pick from the map, generate a scenario, or import CSV.');
  },100);
}
function runWorkflowAction(action){
  const key=action?.key||'';
  if(key==='install_roads'){activate('roads');return;}
  if(key==='choose_depot'){focusDepotSearch();return;}
  if(key==='add_customers'){focusWorkPointEntry();return;}
  if(key==='optimize_auto_repair'||key==='optimize'||key==='reoptimize_settings'){activate('optimize');setTimeout(()=>startOptimize(null),80);return;}
  if(key==='dispatch'){activate('dispatch');return;}
  activate(action?.view||'command');
}
function renderGuidedNext(){
  const card=$('#guidedNextCard');if(!card||!STATE)return;const s=guidedStepsState(),job=activeJob(),wf=STATE.workflow||{},action=s.next||{};
  const pills=[['source',s.source],['depot',!!s.depot],['roads',s.graph&&s.access],['orders',!!s.customers.length],['route',s.route&&s.optimizationCurrent]];
  const first=pills.findIndex(item=>!item[1]);
  $('#guidedStepPills').innerHTML=pills.map(([key,done],i)=>`<span class="${done?'done':i===first?'active':''}">${({source:'Regional roads',depot:'Depot',roads:LANG==='th'?'Directed graph':'Directed graph',orders:LANG==='th'?'':'Work points',route:LANG==='th'?'':'Fleet plan'})[key]}</span>`).join('');
  const title=$('#guidedNextTitle'),detail=$('#guidedNextDetail'),primary=$('#guidedPrimaryBtn'),secondary=$('#guidedSecondaryBtn');
  secondary.classList.add('hidden');secondary.onclick=null;primary.disabled=!!job;
  if(job){title.textContent=LANG==='th'?'':'The selected workflow is running';detail.textContent=`Job #${job.id} · ${job.message}`;primary.innerHTML=`<span>${LANG==='th'?'':'View job status'}</span><b>→</b>`;primary.onclick=()=>activate('activity');return;}
  title.textContent=action.label||(LANG==='th'?'':'Review next action');
  if(action.key==='optimize_auto_repair'){detail.textContent=LANG==='th'?'Optimize  directed graph   input.txt  routing ':'Optimize will build or expand the directed graph, validate the depot and every work point, then hand input.txt to routing in the same job.';}
  else if(wf.graph_reusable){detail.textContent=LANG==='th'?` ${wf.graph_id||''}   reuse `:`Graph ${wf.graph_id||''} is still valid and will be reused without rebuilding.`;}
  else if(action.key==='reoptimize_settings'){detail.textContent=LANG==='th'?'  Optimizer  ':'The current fleet plan is retained, but optimizer settings changed. Run it again to apply the latest configuration.';}
  else{detail.textContent=action.reason||'';}
  const labels={install_roads:LANG==='th'?'':'Install road data',choose_depot:LANG==='th'?'':'Choose depot',add_customers:LANG==='th'?'':'Add or import work points',optimize_auto_repair:LANG==='th'?' Optimize':'Prepare graph and optimize',optimize:LANG==='th'?' Optimizer':'Start optimizer',continue_optimization:LANG==='th'?' Optimizer ':'Run optimizer to completion',reoptimize_settings:LANG==='th'?'':'Run with latest settings',dispatch:LANG==='th'?'':'Open current fleet plan'};
  primary.innerHTML=`<span>${esc(labels[action.key]||action.label||'Continue')}</span><b>→</b>`;primary.onclick=()=>runWorkflowAction(action);
  if(action.key==='choose_depot'){secondary.textContent=LANG==='th'?'':'Pick on map';secondary.classList.remove('hidden');secondary.onclick=()=>{$('#mapDepotBtn')?.click();};}
}

window.showSearchResult=i=>{const x=searchResults[i];if(!x)return;selectCandidate({...x,address:x.display_name},'auto');};
window.selectSearchResult=i=>{const x=searchResults[i];if(!x)return;selectCandidate({...x,address:x.display_name},'auto');};
window.prepareSearchResult=async(i,role)=>{const x=searchResults[i];if(!x)return;await selectCandidate({...x,address:x.display_name},role);};

async function selectCandidate(place,preferredRole='auto'){
  try{place=normalizeCandidate(place);}catch(error){showResult({type:'error',title:LANG==='th'?'':'Could not select place',message:error.message});return;}
  selectedCandidate={...place,preferredRole};selectedCandidateAccess=null;
  planPreviewLayer.clearLayers();
  L.marker([place.lat,place.lon],{icon:previewMarkerIcon(preferredRole==='depot'?'depot':'customer'),keyboard:false}).addTo(planPreviewLayer);
  planMap.setView([place.lat,place.lon],16);renderAccessInspector(true);
  const depot=(STATE.places||[]).find(p=>p.role==='depot');
  if(!STATE.network?.access_ready||STATE.network_stale?.stale){
    renderAccessInspector();return;
  }
  try{
    const access=await api('/api/access/preview',{method:'POST',body:JSON.stringify({lat:place.lat,lon:place.lon})});
    selectedCandidateAccess=access;
    if(access.geometry?.length){L.polyline(access.geometry,{pane:'route-halo',color:'#fff',weight:11,opacity:.9,interactive:false}).addTo(planPreviewLayer);L.polyline(access.geometry,{pane:'route-main',color:access.valid?'#0f8075':'#c9443a',weight:7,opacity:.9}).addTo(planPreviewLayer);}
    if(access.snap_lat!=null){L.polyline([[place.lat,place.lon],[access.snap_lat,access.snap_lon]],{color:'#c68a20',weight:2,dashArray:'5 5'}).addTo(planPreviewLayer);L.marker([access.snap_lat,access.snap_lon],{icon:accessMarkerIcon(!!access.valid),interactive:false}).addTo(planPreviewLayer);}
  }catch(e){selectedCandidateAccess={valid:false,status:'error',warning:friendlyError(e.message),technical_error:String(e.message||'')};}
  renderAccessInspector();
}



function clearAccessInspector(){selectedCandidate=null;selectedCandidateAccess=null;planPreviewLayer.clearLayers();renderAccessInspector();}

function renderAccessInspector(waiting=false){
  const empty=$('#accessInspectorEmpty'),content=$('#accessInspectorContent'),prepare=$('#inspectorPrepareArea');if(!empty||!content||!prepare)return;
  if(!selectedCandidate){empty.classList.remove('hidden');content.classList.add('hidden');prepare.classList.add('hidden');return;}
  empty.classList.add('hidden');content.classList.remove('hidden');
  $('#inspectorPlaceName').textContent=selectedCandidate.name||'Selected destination';$('#inspectorAddress').textContent=selectedCandidate.address||selectedCandidate.display_name||'';
  const depot=(STATE.places||[]).find(p=>p.role==='depot'),graphReady=!!STATE.network?.access_ready&&!STATE.network_stale?.stale;
  const access=selectedCandidateAccess;
  const needsPrepare=!access?.valid && !!depot && !!STATE.osm_source?.ready;
  const status=$('#inspectorStatus');status.className='access-verdict '+(waiting?'waiting':access?.valid?'valid':needsPrepare?'needs-graph':'invalid');
  $('i',status).textContent=waiting?'…':access?.valid?'✓':needsPrepare?'↻':'!';
  $('b',status).textContent=waiting?(LANG==='th'?'':'Checking road access'):access?.valid?(LANG==='th'?' — road segment – Depot ':'Accepted — this segment supports depot round trips'):needsPrepare?(LANG==='th'?' Operating Graph':'Prepare or expand the operating graph'):(depot?(LANG==='th'?'':'This destination is not accepted'):(LANG==='th'?' Depot ':'Choose a depot first'));
  $('small',status).textContent=waiting?'Regional offline road engine':access?.warning||access?.message||(access?.valid?'Validated on the same round-trip road network as the depot':(depot?'The selected regional road source can validate this place locally.':'The first selected place becomes the depot.'));
  $('#inspectorRoad').textContent=access?.road_name||'—';$('#inspectorClass').textContent=access?.highway||'—';$('#inspectorDistance').textContent=access?.snap_distance_m!=null?`${num(access.snap_distance_m,0)} m / ${num(access.max_snap_m||STATE.fleet?.snap_max_m||350,0)} m`:'—';$('#inspectorReachability').textContent=access?.round_trip_reachable?(LANG==='th'?' · –':'Pass · outbound and return'):access?.valid===false?(LANG==='th'?'':'Not accepted'):'Waiting';$('#inspectorDirection').textContent=access?.direction_text||'—';$('#inspectorTechnical').textContent=JSON.stringify(access||{status:'operating graph required'},null,2);
  const guidance=$('#inspectorGuidance');guidance.innerHTML=access?.valid?`<b>${LANG==='th'?'':'The real destination and road access are stored separately'}</b><p>${LANG==='th'?'Driver   Solver  node – Depot':'Drivers see the real destination; the solver uses the verified round-trip access node.'}</p>`:needsPrepare?`<b>${LANG==='th'?'':'Prepare roads from the verified regional source'}</b><p>${LANG==='th'?'  segment ':'FleetRoute expands the local operating area, then highlights a usable segment before the customer can be saved.'}</p>`:access?.warning?`<b>${LANG==='th'?'':'Destination is too far from an accepted road'}</b><p>${esc(access.warning)}</p>`:'';
  prepare.classList.toggle('hidden',!needsPrepare);
  const prepareBtn=$('#prepareAreaInlineBtn');if(prepareBtn){prepareBtn.textContent=graphReady?(LANG==='th'?'':'Expand graph to this place and recheck'):(LANG==='th'?' Operating Graph ':'Prepare operating graph and validate');}
  $('#previewSetDepotBtn').disabled=false;
  $('#previewAddCustomerBtn').disabled=!access?.valid;
  $('#previewAddCustomerBtn').title=access?.valid?'':(LANG==='th'?' road-access check ':'Road-access validation is required');
  $('#inspectorRoleHint').textContent=selectedCandidate.preferredRole==='depot'?'DEPOT CANDIDATE':selectedCandidate.preferredRole==='customer'?'WORK-POINT CANDIDATE':depot?'WORK-POINT CANDIDATE':'DEPOT CANDIDATE';
  $('#previewSetDepotBtn').classList.toggle('hidden',selectedCandidate.preferredRole==='customer');
  $('#previewAddCustomerBtn').classList.toggle('hidden',selectedCandidate.preferredRole==='depot');
}


async function saveDepotCandidate(candidate){
  let place;
  try{place=normalizeCandidate(candidate);}
  catch(error){showResult({type:'error',title:LANG==='th'?' Depot ':'Could not set depot',message:error.message});return;}
  const existing=(STATE.places||[]).find(item=>item.role==='depot');
  if(existing&&!confirm(LANG==='th'?` Depot  “${existing.name}”  “${place.name}”?`:`Replace depot “${existing.name}” with “${place.name}”?`))return;
  try{
    await api('/api/places',{method:'POST',body:JSON.stringify({
      role:'depot',name:place.name,address:place.address,lat:place.lat,lon:place.lon,
      demand:0,service_s:0,earliest_s:0,latest_s:86400,external_id:place.external_id||'',
      access:selectedCandidateAccess?.valid?selectedCandidateAccess:null,allow_pending:true
    })});
    clearAccessInspector();clearSearchUI();await refresh(true);
    if(sourceCoverageMismatch()){await openMatchingRegionForDepot(place,'The depot was saved, but it is outside the current verified road extract.');return;}
    const sourceReady=activeSourceOperational();
    showResult({
      type:'success',
      title:LANG==='th'?' Depot ':'Depot selected',
      message:sourceReady
        ? (LANG==='th'?' ':'FleetRoute validates the depot inside the work-point workflow. No separate graph run is required.')
        : (LANG==='th'?' regional road source ':'Next, prepare the regional road source.'),
      primary:sourceReady?(LANG==='th'?' 20 ':'Create a standard 20-stop plan'):(LANG==='th'?'':'Choose the operating road region'),
      secondary:sourceReady?(LANG==='th'?'':'Adjust plan options'):'',
      onPrimary:()=>{
        if(!sourceReady){REGION_FORCE_OPEN=true;activate('command');renderRegionSetup();return;}
        applyScenarioPreset('standard');generateScenario(true);
      },
      onSecondary:openScenarioBuilder,
    });
  }catch(error){showResult({type:'error',title:LANG==='th'?' Depot ':'Could not set depot',message:friendlyError(error.message)});}
}

window.quickSetDepotFromSearch=async i=>{const place=searchResults[i];if(place)await saveDepotCandidate(place);};

function openPlaceModal(place,access,role='customer',edit=false){pendingPlace={...place,role};pendingAccess=access||null;selectedPlaceId=edit?place.id:null;$('#modalName').value=place.name||'';$('#modalAddress').value=place.address||place.display_name||'';$('#modalDemand').value=edit?place.demand||0:10;$('#modalService').value=edit?Math.round((place.service_s||0)/60):10;$('#modalEarliest').value=secondsToTime(edit?place.earliest_s:8*3600);$('#modalLatest').value=secondsToTime(edit?place.latest_s:18*3600);$('#saveDepotBtn').classList.toggle('hidden',edit);$('#saveCustomerBtn').classList.toggle('hidden',edit);$('#updatePlaceBtn').classList.toggle('hidden',!edit);$('#accessPreviewCard').innerHTML=access?`<div class="access-road-title"><i>⌁</i><div><b>${esc(access.road_name)} · ${esc(access.highway)}</b><small>${num(access.snap_distance_m,0)} m from destination · ${esc(access.direction_text)}</small></div></div>`:`<div class="access-road-title"><i>○</i><div><b>${LANG==='th'?' OSM':'Pending road-network validation'}</b><small>${LANG==='th'?'':'CSV locations are validated when the network is built'}</small></div></div>`;$('#accessTechnical').textContent=JSON.stringify(access||{status:'pending'},null,2);revealDialog($('#placeModal'),'#modalName');}
function closePlaceModal(){dismissDialog($('#placeModal'));pendingPlace=null;pendingAccess=null;selectedPlaceId=null;}
async function saveNewPlace(role){
  if(!pendingPlace)return;
  let normalized;try{normalized=normalizeCandidate(pendingPlace);}catch(error){showResult({type:'error',title:LANG==='th'?'':'Could not save place',message:error.message});return;}
  const body={role,name:$('#modalName').value.trim()||normalized.name,address:$('#modalAddress').value.trim(),lat:normalized.lat,lon:normalized.lon,demand:+$('#modalDemand').value||0,service_s:(+$('#modalService').value||0)*60,earliest_s:timeToSeconds($('#modalEarliest').value),latest_s:timeToSeconds($('#modalLatest').value),external_id:normalized.external_id||'',access:pendingAccess,allow_pending:role==='depot'};
  try{await api('/api/places',{method:'POST',body:JSON.stringify(body)});closePlaceModal();clearAccessInspector();toast(role==='depot'?tr('setDepot'):tr('addCustomer'),body.name);await refresh(true);if(sourceCoverageMismatch()){if(role==='depot')await openMatchingRegionForDepot(body,'The depot was saved, but it is outside the current verified road extract.');else openMatchingRegion('A work point is outside the active verified road extract.');}else if(role==='depot'){if(activeSourceOperational()){$('#scenarioBuilder')?.classList.remove('hidden');updateScenarioSummary();}else{REGION_FORCE_OPEN=true;activate('command');renderRegionSetup();}}}
  catch(e){showResult({type:'error',title:LANG==='th'?'':'Could not save place',message:friendlyError(e.message)});}
}
window.editPlace=id=>{const p=(STATE.places||[]).find(x=>+x.id===+id);if(!p)return;openPlaceModal(p,p.access_verified?{valid:true,road_name:p.access_road,snap_distance_m:p.access_distance_m,snap_lat:p.access_lat,snap_lon:p.access_lon,access_osm_node:p.access_osm_node}:null,p.role,true);};
async function updatePlaceFromModal(){if(!selectedPlaceId)return;const body={name:$('#modalName').value.trim(),address:$('#modalAddress').value.trim(),demand:+$('#modalDemand').value||0,service_s:(+$('#modalService').value||0)*60,earliest_s:timeToSeconds($('#modalEarliest').value),latest_s:timeToSeconds($('#modalLatest').value)};try{await api(`/api/places/${selectedPlaceId}`,{method:'PATCH',body:JSON.stringify(body)});closePlaceModal();toast(tr('saveChanges'),body.name);await refresh(true);}catch(e){toast('Update failed',e.message,true);}}
window.deletePlace=async id=>{if(!confirm(LANG==='th'?'?':'Remove this place from the plan?'))return;try{await api(`/api/places/${id}`,{method:'DELETE'});await refresh(true);}catch(e){toast('Delete failed',e.message,true);}};
window.focusPlace=id=>{const p=(STATE.places||[]).find(x=>+x.id===+id);if(p){activate('plan');planMap.setView([p.lat,p.lon],17);}};

async function clearPlan(){if(!confirm(LANG==='th'?'?':'Clear the depot and all work points?'))return;await api('/api/places',{method:'DELETE'});await refresh(true);}
async function loadDemo(aroundDepot=false){
  if(!aroundDepot){$('#scenarioBuilder')?.classList.remove('hidden');updateScenarioSummary();return;}
  return generateScenario();
}
let SCENARIO_PREVIEW_TIMER = null;
let SCENARIO_CONTRACT = null;

function scenarioPayload(){
  return {
    count:+$('#scenarioCount').value||20,
    radius_m:+$('#scenarioRadius').value||4200,
    seed:$('#scenarioSeed').value.trim()===''?777:Number($('#scenarioSeed').value),
    replace_customers:$('#scenarioReplace').checked,
    demand_mode:$('#scenarioDemandMode')?.value||'auto',
    demand_profile:$('#scenarioDemandProfile')?.value||'standard',
    demand_min:+$('#scenarioDemandMin').value||1,
    demand_max:+$('#scenarioDemandMax').value||1,
    service_mode:$('#scenarioServiceMode')?.value||'auto',
    service_min:+$('#scenarioServiceMin').value||1,
    service_max:+$('#scenarioServiceMax').value||1,
    time_window_mode:$('#scenarioTimeWindow')?.value||'open',
    trucks:+$('#trucks').value||4,
    capacity:+$('#capacity').value||100,
  };
}
function updateScenarioAdvancedVisibility(){
  $('#scenarioDemandCustom')?.classList.toggle('hidden',($('#scenarioDemandMode')?.value||'auto')!=='custom');
  $('#scenarioServiceCustom')?.classList.toggle('hidden',($('#scenarioServiceMode')?.value||'auto')!=='custom');
}
function applyScenarioPreset(name){
  const presets={
    quick:{count:12,profile:'light',radius:2500,tw:'open'},
    standard:{count:20,profile:'standard',radius:4200,tw:'open'},
    stress:{count:100,profile:'heavy',radius:7000,tw:'open'},
  };
  const p=presets[name]||presets.standard;
  $('#scenarioCount').value=p.count;
  $('#scenarioDemandProfile').value=p.profile;
  $('#scenarioRadius').value=String(p.radius);
  $('#scenarioTimeWindow').value=p.tw;
  $('#scenarioDemandMode').value='auto';
  $('#scenarioServiceMode').value='auto';
  $$('.scenario-preset').forEach(b=>b.classList.toggle('active',b.dataset.scenarioPreset===name));
  updateScenarioAdvancedVisibility();updateScenarioSummary();
}
async function refreshScenarioPreview(){
  const el=$('#scenarioSummary'),button=$('#generateScenarioBtn'),only=$('#generateOnlyBtn');if(!el)return null;
  const body=scenarioPayload();
  el.className='scenario-summary loading';el.innerHTML=LANG==='th'?'…':'Checking feasibility…';
  try{
    const c=await api('/api/scenario/preview',{method:'POST',body:JSON.stringify(body)});SCENARIO_CONTRACT=c;
    const status=c.ok?(c.warnings?.length?'stress':'ready'):'blocked';
    const title=status==='ready'?tr('scenarioReady'):status==='stress'?tr('scenarioStress'):tr('scenarioBlocked');
    const notes=[...(c.errors||[]),...(c.warnings||[])];
    el.className=`scenario-summary ${status}`;
    el.innerHTML=`<div class="scenario-contract-head"><b>${esc(title)}</b><span>${LANG==='th'?'':'up to'} ${num(c.maximum_trucks,0)} ${LANG==='th'?'':'trucks'}</span></div>
      <div class="scenario-contract-grid">
        <div><span>${LANG==='th'?'':'Maximum available'}</span><b>${num(c.maximum_trucks,0)}</b></div>
        <div><span>${LANG==='th'?'':'Expected active'}</span><b>${num(c.expected_active_trucks,0)}</b></div>
        <div><span>${tr('autoDemandRange')}</span><b>${num(c.resolved_demand_min,0)}–${num(c.resolved_demand_max,0)}</b></div>
        <div><span>${LANG==='th'?'Demand ':'Expected total demand'}</span><b>${num(c.expected_total_demand,0)}</b></div>
        <div><span>${LANG==='th'?'':'Stops per active truck'}</span><b>${num(c.stops_per_active_truck,1)}</b></div>
      </div><p class="scenario-semantics">${LANG==='th'?' ':'Unused vehicles remain empty. Maximum fleet size is not a target route count.'}</p>${notes.length?`<ul>${notes.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`:''}`;
    if(button)button.disabled=!c.ok;if(only)only.disabled=!c.ok;
    return c;
  }catch(e){SCENARIO_CONTRACT=null;el.className='scenario-summary blocked';el.textContent=e.message;if(button)button.disabled=true;if(only)only.disabled=true;return null;}
}
function updateScenarioSummary(){
  updateScenarioAdvancedVisibility();clearTimeout(SCENARIO_PREVIEW_TIMER);SCENARIO_PREVIEW_TIMER=setTimeout(refreshScenarioPreview,220);
}
async function generateScenario(autoOptimize=true){
  try{
    const depot=(STATE.places||[]).find(p=>p.role==='depot');
    if(!depot){activate('plan');toast(LANG==='th'?' Depot ':'Choose a depot first',LANG==='th'?' Depot ':'Search a place or use depot-pick mode.',true);return;}
    if(!activeSourceOperational()){if(sourceCoverageMismatch())openMatchingRegion();else{REGION_FORCE_OPEN=true;activate('command');renderRegionSetup();toast('Regional road source required','Choose and verify a region that covers this depot.',true);}return;}
    if(!await confirmDistanceRisk(autoOptimize?'create work points and route them':'create these work points'))return;
    await saveSettings(false);
    const body=scenarioPayload();body.auto_optimize=!!autoOptimize;body.run_optimizer=!!autoOptimize;
    const contract=await refreshScenarioPreview();
    if(!contract?.ok){showResult({type:'error',title:tr('scenarioBlocked'),message:(contract?.errors||[]).join(' · ')||'Invalid scenario'});return;}
    const r=await api('/api/scenario',{method:'POST',body:JSON.stringify(body)});
    selectedJobId=r.job_id;resetJobLogs(r.job_id);$('#scenarioBuilder').classList.add('hidden');
    const action=autoOptimize?(LANG==='th'?'  Optimizer':'Preparing an initial plan, then running the optimizer'):(LANG==='th'?'':'Creating road-validated work points');
    toast(action,`Job #${r.job_id} · ${body.count} ${LANG==='th'?'':'work points'}`);
    await refresh(true,false);activate('plan');subscribeToActiveJob();
  }catch(e){showResult({type:'error',title:LANG==='th'?'':'Could not start scenario',message:e.message});}
}

async function importCsv(file){
  // Keep original values/units for the server's atomic validation. Numeric
  // coercion here used to turn blank coordinates and invalid demand into zero,
  // and discarded service_s / earliest_s / latest_s entirely.
  const rows=parseCsvRows(await file.text());
  loading(true,LANG==='th'?' CSV':'Importing CSV',`${rows.length} rows · one atomic database commit`);
  try{
    const result=await api('/api/plan/import',{method:'POST',body:JSON.stringify({rows,replace:false,use_current_depot:true})});
    await refresh(true);toast(LANG==='th'?' — Optimize ':'CSV imported',`${result.customer_count??rows.length} customers · atomic import`);if(sourceCoverageMismatch()){openMatchingRegion('The imported depot/work points are not fully covered by the active road extract. The CSV is saved, but road preparation is blocked until you use a matching region.');}else if(!activeSourceOperational()){REGION_FORCE_OPEN=true;activate('command');renderRegionSetup();toast('Road region required','Choose a verified region that covers the imported plan.',true);}else{activate('optimize');}
  }finally{loading(false);}
}
function parseCsvLine(line){return parseCsvRecords(line)[0]||[];}
function parseCsvRecords(text){
  const records=[];let row=[],cell='',quoted=false,closed=false;
  const finishCell=()=>{row.push(cell);cell='';closed=false;};
  const finishRow=()=>{finishCell();if(row.some(value=>value.trim()!==''))records.push(row);row=[];};
  text=String(text).replace(/^\uFEFF/,'');
  for(let i=0;i<text.length;i++){
    const ch=text[i];
    if(quoted){
      if(ch==='"'){if(text[i+1]==='"'){cell+='"';i++;}else{quoted=false;closed=true;}}
      else cell+=ch;
      continue;
    }
    if(ch===','){finishCell();continue;}
    if(ch==='\n'||ch==='\r'){if(ch==='\r'&&text[i+1]==='\n')i++;finishRow();continue;}
    if(closed){if(ch===' '||ch==='\t')continue;throw new Error('CSV has unexpected text after a closing quote');}
    if(ch==='"'){if(cell.trim()!=='')throw new Error('CSV has a quote inside an unquoted field');cell='';quoted=true;}
    else cell+=ch;
  }
  if(quoted)throw new Error('CSV has an unclosed quoted field');
  if(cell!==''||row.length||closed)finishRow();
  return records;
}
function parseClock(v){if(!v)return 0;if(/^\d+(\.\d+)?$/.test(v))return +v;return timeToSeconds(v);}


function tickRoadDownloadUI(job=null){
  const downloadJob=job||((STATE?.jobs||[]).find(j=>j.kind==='osm-source-download'&&['queued','running'].includes(j.status)));
  if(!downloadJob)return;
  const badge=$('#osmSourceBadge');if(badge){badge.className='status-chip running';badge.textContent=LANG==='th'?'':'Downloading';}
  const button=$('#downloadRegionBtn');if(button){button.disabled=true;button.textContent=LANG==='th'?'…':'Downloading…';}
  const prog=$('#osmSourceProgress');if(prog)prog.classList.remove('hidden');
  const ind=jobIndeterminate(downloadJob),pct=jobProgress(downloadJob);
  const bar=$('#osmSourceProgressBar');if(bar){bar.style.width=`${ind?34:pct}%`;bar.parentElement?.classList.toggle('indeterminate',ind);}
  const percent=$('#osmSourceProgressPercent');if(percent)percent.textContent=progressLabel(downloadJob);
  const text=$('#osmSourceProgressText');if(text)text.textContent=`${localizeStage(currentStageLabel(downloadJob))} · ${LANG==='th'?'':'elapsed'} ${humanDuration(jobElapsed(downloadJob))}`;
}

function renderRoads(){
  const n=STATE.network,source=STATE.osm_source||{},coverage=STATE.osm_source_coverage||{},distance=STATE.plan_distance_check||{},places=STATE.places||[],closures=STATE.closures||[],pending=closures.filter(c=>c.status==='pending'),approved=closures.filter(c=>c.status==='approved');
  let verifiedAccessCount=0;for(const p of places){if(p.access_verified)verifiedAccessCount+=1;}
  const pendingAccessCount=places.length-verifiedAccessCount;
  const networkIdentity=n?String(n.cache_key||n.built_at||`${n.nodes||0}:${n.edges||0}`):'';
  const graphUsable=!!n&&!STATE.network_stale?.stale;
  const nextRoadNetworkId=graphUsable?networkIdentity:'';
  // Invalidate the road canvas only on a real graph-readiness/identity transition.
  // The old `!graphUsable || ...` condition reset the whole Leaflet cache on
  // every heartbeat while a graph was absent/stale, needlessly rebuilding up to
  // hundreds of stop markers before graph preparation.
  if(nextRoadNetworkId!==ROAD_NETWORK_ID){
    if(ROAD_REQUEST_CONTROLLER){ROAD_REQUEST_SEQ+=1;ROAD_REQUEST_CONTROLLER.abort();ROAD_REQUEST_CONTROLLER=null;}
    roadGeojson=null;ROAD_VIEWPORT_KEY='';ROAD_RENDER_KEY='';
    ROAD_NETWORK_ID=nextRoadNetworkId;
  }
  const downloadJob=(STATE.jobs||[]).find(j=>j.kind==='osm-source-download'&&['queued','running'].includes(j.status));
  const sourceOk=activeSourceOperational(),sourceMismatch=sourceCoverageMismatch();
  $('#osmSourceBadge').className=`status-chip ${sourceOk?'succeeded':source.ready&&sourceMismatch?'warn':downloadJob?'running':'idle'}`;$('#osmSourceBadge').textContent=sourceOk?'Active & verified':source.ready&&sourceMismatch?'Outside plan':downloadJob?'Downloading':'No active source';
  $('#osmSourceTitle').textContent=source.region?`${source.region.name} · active road source`:'Choose an operating region';
  $('#osmSourceMeta').textContent=sourceOk?`${source.size_human||''} · covers the current plan · checksum ${String(source.verified_md5||'').slice(0,10)}…`:sourceMismatch?`Verified file is intact, but ${coverage.outside_count||1} current plan point${coverage.outside_count===1?' is':'s are'} outside this extract. Choose a matching region before graph preparation.`:(source.ready?'Verified local source; geographic coverage is unavailable, so FleetRoute will keep this source until you explicitly change it.':'Choose/download a region in System overview, then explicitly use it for this plan.');
  $('#osmStoragePath').textContent=source.path||source.data_dir||'—';
  $('#downloadRegionBtn').disabled=!!downloadJob||sourceOk;$('#downloadRegionBtn').textContent=sourceOk?'Active source verified':downloadJob?'Downloading…':sourceMismatch?'Choose matching region':'Choose road region';$('#deleteOsmSourceBtn').classList.toggle('hidden',!source.ready);
  const prog=$('#osmSourceProgress');prog.classList.toggle('hidden',!downloadJob);if(downloadJob){const live=liveOf(downloadJob),pct=jobProgress(downloadJob),ind=jobIndeterminate(downloadJob);$('#osmSourceProgressBar').style.width=`${ind?34:pct}%`;$('#osmSourceProgressBar').parentElement?.classList.toggle('indeterminate',ind);$('#osmSourceProgressPercent').textContent=progressLabel(downloadJob);$('#osmSourceProgressText').textContent=`${localizeStage(currentStageLabel(downloadJob))} · ${LANG==='th'?'':'elapsed'} ${humanDuration(jobElapsed(downloadJob))}`; }
  const depot=places.find(p=>p.role==='depot'),graphOk=!!n&&!STATE.network_stale?.stale,accessOk=graphOk&&places.length&&places.every(p=>!!p.access_verified);
  const steps=[[sourceOk,'1',source.region?.name||'Regional source',sourceOk?source.size_human:(sourceMismatch?'Outside current plan':'Choose/activate region')],[!!depot,'2','Depot anchor',depot?.name||'Choose depot'],[graphOk,'3','Operating graph',graphOk?`${num(n.nodes)} nodes`:'Prepare/expand'],[accessOk,'4','Access contract',accessOk?'Every stop reachable':`${pendingAccessCount} pending`]];
  $('#osmSetupSteps').innerHTML=steps.map(([ok,no,title,detail])=>`<div class="osm-step ${ok?'pass':'pending'}"><i>${ok?'✓':no}</i><div><b>${esc(title)}</b><small>${esc(detail)}</small></div></div>`).join('<span class="osm-step-arrow">→</span>');
  const farthestKm=distance.available?(Number(distance.farthest_m||0)/1000):0;
  $('#roadMetrics').innerHTML=cards([
    ['Active road source',sourceOk?source.size_human:'—',sourceOk?(source.region?.name||'Verified source'):sourceMismatch?'Does not cover current plan':'Not operational',sourceOk?'good':'warn'],
    [LANG==='th'?'Road nodes':'Road nodes',n?num(n.nodes):'—',n?.cache_hit?'Loaded from regional cache':'Directed round-trip network',graphOk?'good':'warn'],
    [LANG==='th'?'Directed edges':'Directed edges',n?num(n.edges):'—',n?.network_type||'drive',graphOk?'good':''],
    [LANG==='th'?'Validated access':'Validated access',`${verifiedAccessCount}/${places.length}`,accessOk?'All destinations reachable':`${pendingAccessCount} need preparation`,accessOk?'good':places.length?'warn':''],
    ['Customer spread',distance.available?`${farthestKm.toFixed(1)} km`:'—',distance.warning?`${distance.far_count} unusually distant from depot`:distance.available?'Farthest straight-line distance':'Add depot and work points',distance.warning?'warn':distance.available?'good':'']
  ]);
  $('#networkReadyChip').className=`status-chip ${accessOk?'succeeded':graphOk?'warn':'idle'}`;$('#networkReadyChip').textContent=accessOk?(LANG==='th'?'':'Ready'):graphOk?(LANG==='th'?'':'Needs review'):(LANG==='th'?'':'Not prepared');
  const checks=[[sourceOk,'Regional road source covers plan',sourceOk?(source.path||source.region?.name||'Verified'):sourceMismatch?`${coverage.outside_count||1} point(s) outside active extract`:'No operational source'],[!!depot,LANG==='th'?' Depot':'Depot selected',depot?.name||'Missing'],[!distance.warning,'Customer distance sanity',distance.warning?`${distance.far_count} beyond ${(Number(distance.warning_threshold_m||0)/1000).toFixed(0)} km · farthest ${farthestKm.toFixed(1)} km`:distance.available?`Farthest ${farthestKm.toFixed(1)} km from depot`:'Waiting for plan'],[graphOk,LANG==='th'?'– Depot':'Round-trip graph',graphOk?`${num(n.nodes)} nodes · ${n.cache_hit?'cache hit':'fresh extract'}`:(LANG==='th'?'':'Not prepared')],[accessOk,LANG==='th'?'':'Every stop reachable',accessOk?'Validated':`${pendingAccessCount} pending`]];
  $('#networkChecklist').innerHTML=checks.map(([ok,title,detail])=>`<div class="network-check ${ok?'pass':'warn'}"><i>${ok?'✓':'!'}</i><div><b>${esc(title)}</b><small>${esc(detail)}</small></div></div>`).join('');
  const accessTableKey=places.map(p=>[p.id,p.role,p.name,+p.lat,+p.lon,p.access_road,p.access_highway,p.access_direction,+p.access_distance_m,!!p.access_verified].join(':')).join('|');
  if(accessTableKey!==ROAD_ACCESS_TABLE_KEY){
    ROAD_ACCESS_TABLE_KEY=accessTableKey;
    $('#accessTable').innerHTML=places.length?`<table class="data-table access-contract-table"><thead><tr><th>Stop</th><th>Destination</th><th>Reachable road segment</th><th>Last meter</th><th>Contract</th></tr></thead><tbody>${places.map(p=>`<tr><td><span class="role-badge ${p.role}">${p.role==='depot'?'depot':'work point'}</span></td><td><b>${esc(p.name)}</b><br><small>${Number(p.lat).toFixed(5)}, ${Number(p.lon).toFixed(5)}</small></td><td><b>${esc(p.access_road||'Pending')}</b><br><small>${esc(p.access_highway||'')} ${p.access_direction?`· ${esc(p.access_direction)}`:''}</small></td><td>${p.access_distance_m==null?'—':num(p.access_distance_m,0)+' m'}</td><td><span class="status-chip ${p.access_verified?'pass':'warn'}">${p.access_verified?'round-trip ready':'prepare graph'}</span></td></tr>`).join('')}</tbody></table>`:`<div class="empty-state">${tr('noData')}</div>`;
  }
  if(!places.length&&!graphUsable)fitRoadsRegionContext(false);
  renderClosures();renderRoadMap();
}
async function downloadRegionSource(){
  if(activeJob()){toast('A job is already running',activeJob().message,true);return;}
  REGION_FORCE_OPEN=true;activate('command');renderRegionSetup();
  toast(sourceCoverageMismatch()?'Choose a matching road region':'Choose the road region for this plan',sourceCoverageMismatch()?'The current verified source does not cover every depot/work point. Browsing another region will not replace it until you explicitly use that source.':'Browse, download, and explicitly activate a verified Geofabrik extract.');
}
async function refreshOsmStatus(){await refresh(false);toast('Road-source status refreshed',activeSourceOperational()?`${STATE.osm_source?.region?.name||'Region'} covers the current plan`:sourceCoverageMismatch()?'Verified source does not cover the current plan':'No active verified source');}
async function deleteRegionSource(){if(!confirm('Delete the selected cached road source and invalidate the active operating graph?'))return;try{await api('/api/osm/source',{method:'DELETE'});roadGeojson=null;REGION_FORCE_OPEN=true;await refresh(true);renderRegionSetup();toast('Regional road source removed');}catch(e){toast('Delete failed',e.message,true);}}

function roadColor(feature){const p=feature.properties||{};if(roadStyle==='oneway')return p.oneway?'#d94d41':'#8a9aa6';if(roadStyle==='speed'){const s=+p.speed_kph||35;return s>=70?'#2867d8':s>=50?'#0f8b7d':s>=30?'#d18d24':'#cf5147';}const h=String(p.highway||'');if(/motorway|trunk/.test(h))return'#245fca';if(/primary/.test(h))return'#0b8175';if(/secondary/.test(h))return'#36a596';if(/tertiary/.test(h))return'#c98a24';if(/service/.test(h))return'#8b6eb3';return'#738592';}
function roadWeight(feature){const h=String(feature.properties?.highway||''),zoom=roadsMap?.getZoom?.()||13,boost=zoom>=16?.45:zoom>=14?.2:0;if(/motorway|trunk/.test(h))return 4.25+boost;if(/primary/.test(h))return 3.55+boost;if(/secondary/.test(h))return 2.8+boost;if(/tertiary/.test(h))return 2.2+boost;if(/service/.test(h))return 1.35+boost;return 1.55+boost;}
function roadLegendHtml(){
  const truncated=!!roadGeojson?.truncated,rendered=num(roadGeojson?.rendered_edges||0),total=num(roadGeojson?.total_edges||0),closures=STATE?.closures||[],approved=closures.filter(c=>c.status==='approved').length,pending=closures.filter(c=>c.status==='pending').length;
  const meta=truncated?`<span class="road-density-note">Visible detail · ${rendered}/${total} edges</span>`:`<span class="road-density-note">${rendered} visible edges</span>`;
  const incidents=`${approved?`<span class="road-incident-key"><i class="road-swatch closure-approved"></i><b>${approved} closed</b></span>`:''}${pending?`<span class="road-incident-key"><i class="road-swatch closure-pending"></i><b>${pending} pending</b></span>`:''}`;
  if(roadStyle==='speed')return `<span class="legend-title">SPEED</span><span><i class="road-swatch speed-fast"></i><b>70+ km/h</b></span><span><i class="road-swatch speed-mid"></i><b>50–69</b></span><span><i class="road-swatch speed-city"></i><b>30–49</b></span><span><i class="road-swatch speed-slow"></i><b>&lt;30</b></span>${incidents}${meta}`;
  if(roadStyle==='oneway')return `<span class="legend-title">DIRECTION</span><span><i class="road-swatch one-way"></i><b>One-way edge</b></span><span><i class="road-swatch two-way"></i><b>Two-way record</b></span>${incidents}${meta}`;
  return `<span class="legend-title">ROAD CLASS</span><span><i class="road-swatch motorway"></i><b>Motorway / trunk</b></span><span><i class="road-swatch primary"></i><b>Primary</b></span><span><i class="road-swatch secondary"></i><b>Secondary</b></span><span><i class="road-swatch local"></i><b>Local</b></span>${incidents}${meta}`;
}

function closeClosureModal(){dismissDialog($('#closureModal'));pendingClosureEdge=null;closurePreviewLayer.clearLayers();}

async function runClusterBenchmark(){if(!STATE.network?.access_ready){toast(LANG==='th'?' OSM ':'Road network required',LANG==='th'?' OSM  ':'Build and validate the road network first',true);activate('roads');return;}if(!confirm(LANG==='th'?'Benchmark   spectral ?':'The full benchmark can take several minutes, especially spectral methods. Continue?'))return;try{await saveSettings(false);const root=$('#clustering').value==='auto'?'road_savings':$('#clustering').value==='none'?'road_savings':$('#clustering').value;const r=await api('/api/clustering/benchmark',{method:'POST',body:JSON.stringify({root_mode:root})});toast(LANG==='th'?' Clustering Benchmark ':'Clustering benchmark queued',`Job #${r.job_id}`);selectedJobId=r.job_id;activate('activity');await refresh(true);}catch(e){toast('Benchmark failed',e.message,true);}}

function renderOptimizeBase(){
  const customers=(STATE.places||[]).filter(p=>p.role==='customer'),solverJobs=(STATE.jobs||[]).filter(j=>['solve','network-and-solve'].includes(j.kind)),job=solverJobs.find(j=>['queued','running'].includes(j.status))||solverJobs[0]||activeJob()||latestJob(),pf=STATE.preflight||{},checks=pf.checks||[],routeStatus=routeOperationalState();
  $('#optimizeMetrics').innerHTML=cards([
    [LANG==='th'?'':'Work points',num(customers.length),`Demand ${num(customers.reduce((s,p)=>s+(+p.demand||0),0),1)}`,customers.length?'good':'warn'],
    ['Directed graph',STATE.network&&!STATE.network_stale?.stale?'READY':'NOT READY',STATE.network?`${num(STATE.network.nodes)} nodes · ${num(STATE.network.edges)} directed edges`:'Prepare from the selected regional road source',STATE.network&&!STATE.network_stale?.stale?'good':'warn'],
    ['Road access',`${(STATE.places||[]).filter(p=>p.access_verified).length}/${(STATE.places||[]).length}`,pf.invalid_places?.length?`${pf.invalid_places.length} pending`:(LANG==='th'?'–':'Depot round trips validated'),pf.invalid_places?.length?'warn':'good'],
    [LANG==='th'?'':'Routing state',routeStatus.badge,latestVersion()?`Route v${latestVersion()} · ${latestRoutes().length} ${LANG==='th'?'':'trucks'}`:routeStatus.detail,routeStatus.completed?'good':routeStatus.phase==='stale'?'bad':'warn']
  ]);
  const contract=STATE.latest_scenario_contract||{},fleet=STATE.fleet||{};
  const maximumTrucks=Number(fleet.trucks||contract.maximum_trucks||contract.trucks||0),capacity=Number(fleet.capacity||contract.capacity||0);
  const totalDemand=customers.reduce((sum,p)=>sum+(Number(p.demand)||0),0);
  const capacityLowerBound=capacity>0?Math.ceil(totalDemand/capacity):0;
  const publishedActive=latestRoutes().length||0;
  const required=Number(contract.required_trucks_by_capacity||capacityLowerBound||0);
  const usedUtil=required&&capacity?totalDemand/(required*capacity)*100:null;
  $('#resolvedFleetContract').innerHTML=`<div class="resolved-fleet-title"><div><span class="section-kicker">${LANG==='th'?' Fleet ':'ACTIVE FLEET CONTRACT'}</span><b>${maximumTrucks||'—'} ${LANG==='th'?'':'maximum available'} · ${capacity||'—'} ${LANG==='th'?'':'capacity each'}</b></div><span class="status-chip ${customers.length?'pass':'idle'}">${customers.length?(LANG==='th'?'K  ':'K IS A CEILING'):(LANG==='th'?'':'NO PLAN')}</span></div><div class="resolved-fleet-grid"><div><span>${LANG==='th'?'':'Work points'}</span><b>${num(customers.length)}</b></div><div><span>${LANG==='th'?' Capacity':'Minimum trucks by load'}</span><b>${num(required)}</b></div><div><span>${LANG==='th'?'':'Current active trucks'}</span><b>${publishedActive||'—'}</b></div><div><span>${LANG==='th'?'Load ':'Load at minimum fleet'}</span><b>${usedUtil==null?'—':percentText(usedUtil)}</b></div></div><p>${LANG==='th'?'  Solver  Objective ':'Truck count is a maximum availability limit. Unneeded vehicles remain empty; the solver chooses the active fleet under the selected objective and constraints.'}</p><button type="button" class="text-button" id="editFleetContractBtn">${LANG==='th'?' Demand':'Edit work points and demand model'} →</button>`;
  $('#editFleetContractBtn').onclick=openScenarioBuilder;
  const hardMissing=checks.filter(x=>!x.ok&&['source','depot','customers'].includes(x.id));
  const repairMissing=checks.filter(x=>!x.ok&&['network','access'].includes(x.id));
  const canStart=hardMissing.length===0;
  const preflightTitle=canStart?(repairMissing.length?(LANG==='th'?' Solver · ':'Ready · road graph will auto-repair'):(LANG==='th'?' Solver':'Ready to start the solver')):(LANG==='th'?'':'Complete the required items first');
  const preflightBadge=canStart?(repairMissing.length?'AUTO REPAIR':'READY'):`${hardMissing.length} BLOCKING`;
  $('#optimizerPreflight').innerHTML=`<div class="preflight-title"><div><span class="section-kicker">PRE-RUN CONTRACT</span><b>${preflightTitle}</b></div><span class="status-chip ${canStart?'pass':'warn'}">${preflightBadge}</span></div><div class="preflight-grid">${checks.map((c,i)=>{const repair=!c.ok&&['network','access'].includes(c.id);return`<button class="preflight-check ${c.ok?'pass':repair?'repair':'pending'}" data-preflight-action="${c.id}"><i>${c.ok?'✓':repair?'↻':i+1}</i><span><b>${esc(c.label)}</b><small>${c.ok?(LANG==='th'?'':'Validated'):repair?(LANG==='th'?'Solver /':'FleetRoute will build/expand this automatically'):(LANG==='th'?'':'Required before start')}</small></span><em>→</em></button>`;}).join('')}</div>`;
  $$('[data-preflight-action]').forEach(b=>b.onclick=()=>{const id=b.dataset.preflightAction;if(id==='source'||id==='network'||id==='access')activate('roads');else activate('plan');});
  const optimizeDisabled=!canStart||!!activeJob();$('#optimizeNowBtn').classList.toggle('disabled',optimizeDisabled);$('#optimizeNowBtn').disabled=optimizeDisabled;
  const st=stageOf(job),stageDefs=job?stagesForJob(job):stagesForJob({kind:'solve'});$('#jobStatusChip').className=`status-chip ${job?.status||'idle'}`;$('#jobStatusChip').textContent=job?.status||'Idle';$('#pipeline').innerHTML=stageDefs.map((x,i)=>{const n=i+1,done=job?.status==='succeeded'||n<st,running=job?.status==='running'&&n===st,failed=['failed','cancelled'].includes(job?.status)&&n===st;return`<div class="pipeline-stage ${done?'done':running?'running':failed?'failed':''}"><i>${done?'✓':failed?'!':running?'▶':n}</i><div><b>${esc(x[0])}</b><small>${esc(x[1])}</small></div><span class="status-chip ${done?'pass':running?'running':failed?'failed':'idle'}">${done?'done':running?'running':failed?'stopped':'waiting'}</span></div>`;}).join('');
  renderOptimizeTrace(job);
  return job;
}



function developerFile(key){return (DEV_RUNTIME?.files||[]).find(file=>file.key===key)||null;}
function shortHash(value){return value?`${String(value).slice(0,12)}…`:'—';}
function renderDeveloper(){
  const metrics=$('#devMetrics');if(!metrics)return;
  if(!DEV_RUNTIME){metrics.innerHTML=cards([[LANG==='th'?'Runtime inspector':'Runtime inspector','—',LANG==='th'?'':'Loading runtime data','warn']]);return;}
  const files=DEV_RUNTIME.files||[],existing=files.filter(f=>f.exists),contract=DEV_RUNTIME.contract||{},prov=DEV_RUNTIME.solver_provenance||{};
  const input=developerFile('input'),stderr=developerFile('solver_stderr'),inv=DEV_RUNTIME.last_invocation,attempts=inv?.attempts||[];
  metrics.innerHTML=cards([
    [LANG==='th'?'Input contract':'Input contract',contract.ok?'PASS':'FAIL',contract.ok?(LANG==='th'?' dataset ':'Structure matches dataset'):(contract.error||'Mismatch'),contract.ok?'good':'warn'],
    ['Optimizer provenance','FleetRoute Optimizer',prov.source_matches_declared?`SHA-256 ${shortHash(prov.active_solver_source_sha256)}`:(LANG==='th'?'Source hash  receipt':'Source hash differs from receipt'),prov.source_matches_declared?'good':'warn'],
    [LANG==='th'?'Runtime artifacts':'Runtime artifacts',`${existing.length}/${files.length}`,LANG==='th'?'':'files currently present',existing.length?'good':'warn'],
    ['stdin bytes',input?.exists?humanBytes(input.bytes):'—',input?.sha256?`SHA-256 ${shortHash(input.sha256)}`:(LANG==='th'?' materialize':'Not materialized'),input?.exists?'good':'warn'],
    ['routing cerr / stderr',stderr?.exists?humanBytes(stderr.bytes):'—',stderr?.exists?(LANG==='th'?' stdout ':'Separated from stdout'):(LANG==='th'?'':'No solver run yet'),stderr?.exists&&stderr.bytes>0?'warn':'good'],
    [LANG==='th'?'Solver attempts':'Solver attempts',attempts.length?num(attempts.length):'—',inv?.job_id?`Job #${inv.job_id}`:(LANG==='th'?' command preview ':'Current command preview')]
  ]);
  const checks=contract.checks||[];
  $('#devContractBadge').className=`status-chip ${contract.ok?'pass':'failed'}`;$('#devContractBadge').textContent=contract.ok?'PASS':'FAIL';
  $('#devContractChecks').innerHTML=checks.length?checks.map(c=>`<div class="developer-check ${c.ok?'pass':'fail'}"><i>${c.ok?'✓':'!'}</i><div><b>${esc(c.id||c.label||'check')}</b><small>${esc(c.detail||'')}</small></div></div>`).join(''):`<div class="empty-state">${esc(contract.error||tr('noData'))}</div>`;
  const lastAttempt=attempts.length?attempts[attempts.length-1]:null;
  const commandText=lastAttempt?.display||DEV_RUNTIME.command?.display||'—';$('#devCommand').textContent=commandText;
  const stdin=inv?.stdin||{};const meta=[inv?.job_id?`Job #${inv.job_id}`:(LANG==='th'?'Current settings preview':'Current settings preview'),inv?.cwd||DEV_RUNTIME.runtime_dir,stdin.bytes!=null?`${humanBytes(stdin.bytes)} stdin`:null,stdin.sha256?`SHA-256 ${stdin.sha256}`:null].filter(Boolean);
  $('#devCommandMeta').innerHTML=meta.map(x=>`<span>${esc(x)}</span>`).join('');$('#devSettings').textContent=JSON.stringify(DEV_RUNTIME.effective_settings||{},null,2);
  const groups=new Map();for(const file of files){if(!groups.has(file.group))groups.set(file.group,[]);groups.get(file.group).push(file);}
  $('#devFileList').innerHTML=[...groups.entries()].map(([group,items])=>`<div class="developer-file-group"><h3>${esc(group)}</h3>${items.map(file=>`<button type="button" class="developer-file ${DEV_FILE_KEY===file.key?'active':''} ${file.exists?'exists':'missing'}" data-dev-file="${esc(file.key)}"><i>${file.exists?'●':'○'}</i><span><b>${esc(file.label)}</b><small>${esc(file.description)}</small></span><em>${file.exists?humanBytes(file.bytes):'missing'}</em><code>${file.sha256?shortHash(file.sha256):''}</code></button>`).join('')}</div>`).join('');
  $$('[data-dev-file]').forEach(btn=>btn.onclick=()=>selectDeveloperFile(btn.dataset.devFile,true));
  const semantics=DEV_RUNTIME.stream_semantics||{};$('#devStreamSemantics').innerHTML=Object.entries(semantics).map(([name,meaning])=>`<div><b>${esc(name)}</b><span>${esc(meaning)}</span></div>`).join('');
}
async function loadActivityRuntime(showToast=false){
  try{DEV_RUNTIME=await api('/api/developer/runtime');if(currentView==='activity'){const j=(STATE?.jobs||[]).find(x=>+x.id===+selectedJobId);if(j)renderJob(j);}if(showToast)toast(LANG==='th'?' Runtime ':'Runtime evidence refreshed');}
  catch(e){if(showToast)toast(LANG==='th'?' Runtime ':'Runtime evidence failed',e.message,true);}
}
async function loadDeveloper(showToast=false){
  try{
    DEV_RUNTIME=await api('/api/developer/runtime');renderDeveloper();
    const preferred=DEV_FILE_KEY&&developerFile(DEV_FILE_KEY)?.exists?DEV_FILE_KEY:(developerFile('dataset_summary')?.exists?'dataset_summary':developerFile('input')?.exists?'input':null);
    if(preferred)await selectDeveloperFile(preferred,true);else{$('#devFilePreview').textContent=LANG==='th'?' runtime file —  input  Solver ':'No runtime file yet — materialize an input or optimize routes first.';}
    if(showToast)toast(LANG==='th'?' Runtime ':'Runtime refreshed',DEV_RUNTIME.runtime_dir||'');
  }catch(e){toast(LANG==='th'?' Runtime ':'Runtime load failed',e.message,true);}
}
async function selectDeveloperFile(key,reset=true){
  const file=developerFile(key);if(!file)return;
  DEV_FILE_KEY=key;if(reset){DEV_FILE_TEXT='';DEV_FILE_OFFSET=0;DEV_FILE_COMPLETE=false;}
  $('#devSelectedFile').textContent=file.label;$('#devFileMeta').textContent=[file.group,file.exists?humanBytes(file.bytes):'missing',file.sha256?`SHA-256 ${file.sha256}`:''].filter(Boolean).join(' · ');
  $('#devDownload').classList.toggle('hidden',!file.exists||!file.download_url);if(file.download_url)$('#devDownload').href=artifactUrl(file.download_url);
  if(!file.exists){DEV_FILE_TEXT='';DEV_FILE_COMPLETE=true;$('#devFilePreview').textContent=LANG==='th'?'':'This file has not been created yet.';$('#devLoadMoreBtn').classList.add('hidden');renderDeveloper();return;}
  try{
    const part=await api(`/api/developer/files/${encodeURIComponent(key)}?offset=${DEV_FILE_OFFSET}&limit=${512*1024}`);
    DEV_FILE_TEXT+=part.text||'';DEV_FILE_OFFSET=part.next_offset||DEV_FILE_OFFSET;DEV_FILE_COMPLETE=!!part.complete;$('#devFilePreview').textContent=DEV_FILE_TEXT||'(empty file)';$('#devLoadMoreBtn').classList.toggle('hidden',DEV_FILE_COMPLETE);renderDeveloper();
  }catch(e){$('#devFilePreview').textContent=`Read failed: ${e.message}`;toast('File preview',e.message,true);}
}

function shortSha(value){return value?String(value).slice(0,12):'—';}
function renderReceipt(element,state,icon,title,detail,tags=[]){if(!element)return;element.className=`analysis-receipt ${state||'neutral'}`;element.innerHTML=`<i>${esc(icon||'i')}</i><div><b>${esc(title||'')}</b><small>${esc(detail||'')}</small>${tags.length?`<div class="receipt-tags">${tags.filter(([,v])=>v!=null&&v!=='').map(([k,v])=>`<span>${esc(k)} ${esc(v)}</span>`).join('')}</div>`:''}</div>`;}
async function loadConvergence(){try{convergenceData=await api('/api/analytics/convergence');renderAnalytics();}catch(e){toast('Convergence',e.message,true);}}
async function buildConvergenceReport(){
  try{
    const r=await api('/api/analytics/convergence/build',{method:'POST',body:'{}'});
    selectedJobId=r.job_id;resetJobLogs(r.job_id);
    toast(LANG==='th'?' Convergence':'Building convergence report',`Job #${r.job_id} · verified raw telemetry`);
    await refresh(true,true);renderAnalytics();subscribeToActiveJob();
  }catch(e){showResult({type:'error',title:LANG==='th'?'':'Could not build convergence report',message:e.message});}
}
function renderAnalytics(zoom=false){
  const d=convergenceData||STATE?.convergence_summary||{},receipt=d.source_receipt||{};
  const buildJob=(STATE?.jobs||[]).find(j=>j.kind==='convergence-analysis'&&['queued','running'].includes(j.status));
  const anyActive=(STATE?.jobs||[]).find(j=>['queued','running'].includes(j.status));
  const buildBtn=$('#buildConvergenceBtn');
  buildBtn.disabled=!d.available||!!anyActive;
  $('span',buildBtn).textContent=buildJob?(LANG==='th'?'…':'Building figures…'):(d.report_current?(LANG==='th'?'':'Rebuild figures'):(LANG==='th'?' Convergence':'Build convergence figures'));
  $('b',buildBtn).textContent=buildJob?'…':'↻';
  $('#analyticsMetrics').innerHTML=cards([
    [LANG==='th'?' Log rows':'Log rows',d.rows!=null?num(d.rows):'—',d.duration_s!=null?`${num(d.duration_s,1)} seconds`:'No convergence file',d.available?'good':'warn'],
    [LANG==='th'?'Objective ':'Initial objective',d.initial_best!=null?num(d.initial_best,2):'—','First best-so-far'],
    [LANG==='th'?'Objective ':'Final objective',d.final_best!=null?num(d.final_best,2):'—',d.improvement_pct!=null?`${num(d.improvement_pct,2)}% improvement`:'—',d.available?'good':''],
    [LANG==='th'?'Global-best improvements':'Global-best improvements',d.improvement_count!=null?num(d.improvement_count):'—',d.global_source==='global_best_obj'?'Process-wide monotone trace':'Legacy log normalized to monotone best-so-far',d.available?'good':'warn']
  ]);
  let receiptState='neutral',receiptIcon='◇',receiptTitle=LANG==='th'?' telemetry':'No telemetry yet',receiptDetail=LANG==='th'?' Optimizer  convergence.csv':'Run the optimizer once to create convergence.csv.';
  if(buildJob){receiptState='running';receiptIcon='↻';receiptTitle=LANG==='th'?' raw telemetry  hash ':'Building from hash-verified raw telemetry';receiptDetail=buildJob.message||'Reconstructing exact routing search streams.';}
  else if(d.available&&d.input_current===false){receiptState='stale';receiptIcon='↺';receiptTitle=LANG==='th'?' Solver  — ':'Last completed solver evidence preserved — current input differs';receiptDetail=LANG==='th'?'  Fleet ':'These files and figures remain downloadable and auditable, but are not presented as results for the current plan, fleet, graph, or closures.';}
  else if(d.report_current){receiptState='current';receiptIcon='✓';receiptTitle=LANG==='th'?' Solver run ':'Figures match the latest solver run';receiptDetail=receipt.invocation_verified?(LANG==='th'?'SHA-256  convergence.csv  solver_invocation.json  SourceManifest':'convergence.csv matches both solver_invocation.json and the report SourceManifest by SHA-256.'):(LANG==='th'?' raw file  invocation ':'Figures match the raw file; the invocation predates verified convergence receipts.');}
  else if(d.available){receiptState='stale';receiptIcon='!';receiptTitle=d.report_stale?(LANG==='th'?' — Raw telemetry ':'Historical figures hidden — raw telemetry is newer'):(LANG==='th'?'Raw telemetry ':'Raw telemetry is ready');receiptDetail=d.report_stale?(LANG==='th'?' “”  run ':'Press “Rebuild figures” so an older report is never mixed with the current run.'):(LANG==='th'?'  Solver ':'Build the figures here; the solver does not need to run again.');}
  renderReceipt($('#convergenceReceipt'),receiptState,receiptIcon,receiptTitle,receiptDetail,[['JOB',receipt.solver_job_id!=null?`#${receipt.solver_job_id}`:null],['ROWS',d.rows!=null?num(d.rows):null],['SHA',shortSha(receipt.sha256)],['INSTANCES',receipt.instances],['BUDGET',receipt.hard_time_limit_s!=null?`${receipt.hard_time_limit_s}s`:null],['PATIENCE',receipt.no_improve_stop_s!=null?`${receipt.no_improve_stop_s}s`:null]]);
  const checks=d.checks||[];$('#convergenceChecks').innerHTML=checks.length?checks.map(c=>`<div class="check-item ${c.status}"><i>${c.status==='pass'?'✓':c.status==='warn'?'!':'×'}</i><div><b>${esc(c.title)}</b><small>${esc(c.detail)}</small></div></div>`).join(''):`<div class="empty-state">${tr('noData')}</div>`;
  setDownloadLink($('#convergenceZipBtn'),d.report_zip?artifactUrl(d.report_zip):null);
  const figs=d.figures||[];let emptyFigures=LANG==='th'?' convergence.csv  Solver':'No solver convergence.csv is available yet.';if(d.available)emptyFigures=d.report_stale?(LANG==='th'?' raw telemetry   “”':'The old report is hidden because it does not match current telemetry. Press “Rebuild figures”.'):(LANG==='th'?'Raw telemetry   “ Convergence” ':'Raw telemetry is ready. Press “Build convergence figures” above.');$('#convergenceFigures').innerHTML=figs.length?figs.map(f=>figureCard(f)).join(''):`<div class="empty-state">${emptyFigures}</div>`;bindImages();
  const points=d.points||[];$('#noConvergence').classList.toggle('hidden',points.length>0);if(!points.length){$('#noConvergence').textContent=LANG==='th'?' convergence.csv  Solver':'No solver convergence.csv is available yet.';if(convergenceChart){convergenceChart.destroy();convergenceChart=null;}}else{drawConvergence(zoom);}
  drawWorkers(d.workers||[]);
}
function drawConvergence(zoom=false){
  let pts=(convergenceData?.points||[]).filter(p=>Number.isFinite(+p.time_s)&&Number.isFinite(+p.best));
  if(zoom&&pts.length){const maxT=Math.max(...pts.map(p=>+p.time_s));const threshold=maxT*.65;const first=Math.max(0,pts.findIndex(p=>+p.time_s>=threshold)-1);pts=pts.slice(first<0?0:first);}
  const ctx=$('#convergenceChart');if(convergenceChart)convergenceChart.destroy();
  const values=pts.map(p=>+p.best),times=pts.map(p=>+p.time_s);
  convergenceChart=new Chart(ctx,{type:'line',data:{datasets:[{label:'Global best-so-far',data:pts.map(p=>({x:+p.time_s,y:+p.best})),borderColor:'#0f8075',backgroundColor:'rgba(15,128,117,.08)',borderWidth:2.6,pointRadius:0,pointHoverRadius:4,stepped:'after',fill:true,tension:0}]},options:{responsive:true,maintainAspectRatio:false,animation:false,interaction:{mode:'nearest',intersect:false},plugins:{legend:{position:'bottom',labels:{usePointStyle:true,boxWidth:7}},tooltip:{callbacks:{title:items=>items.length?`${Number(items[0].parsed.x).toFixed(2)} s`:'',label:item=>`Global best: ${num(item.parsed.y,3)}`}}},scales:{x:{type:'linear',min:zoom&&times.length?Math.min(...times):undefined,max:times.length?Math.max(...times):undefined,title:{display:true,text:'Process elapsed time (s)'},grid:{color:'#edf1f4'}},y:{suggestedMin:values.length?Math.min(...values)*.995:undefined,suggestedMax:values.length?Math.max(...values)*1.005:undefined,title:{display:true,text:'Best objective so far'},grid:{color:'#edf1f4'}}}}});
  $('#chartFullBtn').classList.toggle('active',!zoom);$('#chartZoomBtn').classList.toggle('active',zoom);
}

function drawWorkers(workers){
  if(workerChart) workerChart.destroy();
  workerChart=new Chart($('#workerChart'),{
    type:'bar',
    data:{
      labels:workers.map(w=>w.worker),
      datasets:[
        {label:'Best objective',data:workers.map(w=>w.best),backgroundColor:'#2f6fec',borderRadius:7},
        {label:'Improvement %',data:workers.map(w=>w.improvement_pct),backgroundColor:'#0f8075',borderRadius:7,yAxisID:'y1'}
      ]
    },
    options:{
      responsive:true,
      maintainAspectRatio:false,
      plugins:{legend:{position:'bottom'}},
      scales:{
        x:{grid:{display:false}},
        y:{beginAtZero:false},
        y1:{position:'right',grid:{display:false},title:{display:true,text:'Improvement %'}}
      }
    }
  });
}
function figureCard(f){const detail=f.description||'',url=artifactUrl(f.url);return`<div class="figure-card" role="button" tabindex="0" data-image="${esc(url)}" data-caption="${esc(f.name)}"><img src="${esc(url)}" alt="${esc(f.name)}" loading="lazy"><div><b>${esc(f.name)}</b><small>${detail?esc(detail):(LANG==='th'?'':'Click to enlarge')}</small></div></div>`;}

function renderDispatch(){
  const routes=latestRoutes(),version=latestVersion(),totalDistance=routes.reduce((s,r)=>s+(+r.distance_m||0),0),orders=routes.reduce((s,r)=>s+r.stops.reduce((a,x)=>a+(x.orders?.length||0),0),0),source=STATE.latest_routes?.payload?.solution_source||'unknown',status=routeOperationalState();
  const initialPlan=status.phase==='prepared'||(status.phase==='running'&&status.hasRoute&&!status.savedPlanCompleted);
  const sourceLabel=status.phase==='reviewed'?(LANG==='th'?' routing ':'Initial plan retained after routing review'):source==='cpp_optimizer'?(LANG==='th'?' Optimizer':'Optimized result'):source==='deterministic_baseline'?(LANG==='th'?'':'Validated initial plan'):source;
  const stateCard=$('#dispatchPlanState');stateCard.className=`dispatch-plan-state ${status.phase}`;stateCard.innerHTML=`<div><b>${esc(status.title)}</b><small>${esc(status.detail)}</small></div><span>${esc(status.badge)}</span>`;
  $('#dispatchMetrics').innerHTML=cards([
    [LANG==='th'?'Route version':'Route version',version?`v${version}`:'—',`${sourceLabel} · ${STATE.latest_routes?.created_at?rel(STATE.latest_routes.created_at):(LANG==='th'?'':'No plan yet')}`,status.completed?'good':version?'warn':''],
    [LANG==='th'?'':'Active trucks',num(routes.length),`${orders} ${LANG==='th'?'':'work items'}`,routes.length?'good':''],
    [LANG==='th'?'':'Planned distance',km(totalDistance),initialPlan?(LANG==='th'?' ·  Optimizer':'Initial plan · awaiting optimizer'):(LANG==='th'?'':'Road-network route')],
    [LANG==='th'?'':'Applied closures',num(STATE.latest_routes?.payload?.approved_closure_count||0),LANG==='th'?' edge ':'Edges removed before routing']
  ]);
  const routeRenderKey=JSON.stringify([status.phase,routes.map(r=>[r.truck_id,r.distance_m,r.geometry?.length,r.stops?.length,version])]);
  if(routeRenderKey!==ROUTE_RENDER_KEY){
    ROUTE_RENDER_KEY=routeRenderKey;routeHaloLayer?.clearLayers();routeLayer.clearLayers();routeStopLayer?.clearLayers();const all=[];
    // Draw every halo first so later routes cannot erase the visual separation of earlier ones.
    routes.forEach((r,i)=>{if(!r.geometry?.length)return;const halo={pane:'route-halo',color:'#fff',weight:initialPlan?8:9,opacity:.9,lineCap:'round',lineJoin:'round',interactive:false};if(initialPlan)halo.dashArray='11 8';L.polyline(r.geometry,halo).addTo(routeHaloLayer);});
    routes.forEach((r,i)=>{const color=ROUTE_COLORS[i%ROUTE_COLORS.length],lineStyle={pane:'route-main',color,weight:initialPlan?4.6:5.4,opacity:initialPlan?.78:.94,interactive:true,lineCap:'round',lineJoin:'round'};if(initialPlan)lineStyle.dashArray='11 8';if(r.geometry?.length){const line=L.polyline(r.geometry,lineStyle).bindTooltip(`<div class="route-map-tooltip"><b>Truck ${r.truck_id}</b><span>${km(r.distance_m)} · ${(r.stops||[]).filter(s=>s.kind!=='depot').length} work points</span></div>`,{sticky:true,direction:'top',className:'fleet-map-tooltip'}).bindPopup(`<div class="fleet-popup route-popup"><span>TRUCK ${r.truck_id}</span><b>${km(r.distance_m)}</b><small>${esc(status.title)}</small></div>`).addTo(routeLayer);line.on('mouseover',()=>line.setStyle({weight:initialPlan?6.1:6.8,opacity:1}));line.on('mouseout',()=>line.setStyle(lineStyle));all.push(...r.geometry);}let customerIndex=0;(r.stops||[]).forEach(s=>{const depot=s.kind==='depot';const icon=routeStopIcon(i,depot?0:(s.sequence||++customerIndex),depot);L.marker([+s.lat,+s.lon],{icon,keyboard:false,pane:'fleet-stops',riseOnHover:true}).bindTooltip(depot?`Depot · Truck ${r.truck_id}`:`Truck ${r.truck_id} · Stop ${s.sequence}`,{direction:'top',offset:[0,-8],className:'fleet-map-tooltip'}).addTo(routeStopLayer);});});
    if(currentView==='dispatch'&&all.length)requestAnimationFrame(()=>routesMap.fitBounds(all,{padding:[48,48],animate:false,maxZoom:16}));
  }
  const routeLegend=$('#dispatchRouteLegend');if(routeLegend)routeLegend.innerHTML=routes.length?`<div class="dispatch-route-legend-title"><span>TRUCK ROUTES</span><b>${routes.length} active</b></div><div class="dispatch-route-legend-scroll">${routes.map((r,i)=>`<button type="button" data-ui-action="focus-truck" data-truck-id="${r.truck_id}"><i style="--route-color:${ROUTE_COLORS[i%ROUTE_COLORS.length]}"></i><span><b>Truck ${r.truck_id}</b><small>${km(r.distance_m)} · ${(r.stops||[]).filter(s=>s.kind!=='depot').length} stops</small></span></button>`).join('')}</div>`:`<div class="dispatch-route-legend-empty">Routes appear here after an initial plan is published.</div>`;
  $('#routeCards').innerHTML=routes.length?routes.map((r,i)=>routeCard(r,i,status)).join(''):`<div class="surface empty-state">${LANG==='th'?'  Optimizer ':'No fleet plan yet. Start the optimizer to prepare and complete routing.'}</div>`;
  if(routeChart)routeChart.destroy();routeChart=new Chart($('#routeChart'),{type:'bar',data:{labels:routes.map(r=>`Truck ${r.truck_id}`),datasets:[{label:'Distance (km)',data:routes.map(r=>r.distance_m/1000),backgroundColor:'#0f8075',borderRadius:7},{label:LANG==='th'?'':'Work items',data:routes.map(r=>r.stops.reduce((s,x)=>s+(x.orders?.length||0),0)),backgroundColor:'#2f6fec',borderRadius:7}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'bottom'}},scales:{x:{grid:{display:false}},y:{beginAtZero:true}}}});
  $('#simulationBtn').href=withToken('/simulation');$('#driverPackageBtn').href=withToken('/api/export/driver-package');
}
function routeCard(r,i,status=routeOperationalState()){const color=ROUTE_COLORS[i%ROUTE_COLORS.length],orders=r.stops.reduce((s,x)=>s+(x.orders?.length||0),0),load=r.stops.reduce((s,x)=>s+(+x.demand||0),0),initial=status.phase==='prepared'||(status.phase==='running'&&status.hasRoute&&!status.savedPlanCompleted),sourceText=status.phase==='optimized'?'OPTIMIZED':status.phase==='reviewed'?'READY':initial?'INITIAL PLAN':status.badge,cardClass=initial?'prepared-route':status.completed?'optimized-route':'';return`<article class="route-card ${cardClass}" style="--route-color:${color}" data-ui-action="focus-truck" data-truck-id="${r.truck_id}" role="button" tabindex="0"><div class="route-card-head"><div class="route-card-identity"><i aria-hidden="true"></i><div><h3>Truck ${r.truck_id}</h3><p>${orders} ${LANG==='th'?'':'work items'} · ${routeSequenceLabel(status)}</p></div></div><span class="status-chip ${status.completed?'pass':'warn'}">${sourceText}</span></div><div class="route-spark">${routeSvg(r,color)}</div><div class="route-stats"><div class="route-stat"><span>Distance</span><b>${km(r.distance_m)}</b></div><div class="route-stat"><span>Travel</span><b>${mins(r.travel_time_s)}</b></div><div class="route-stat"><span>Load</span><b>${num(load,1)}</b></div></div><div class="stop-chain">${r.stops.map(s=>`<span class="stop-chip ${s.kind}" style="--route-color:${color}">${s.sequence}</span>`).join('')}</div><div class="route-actions"><a href="${withToken(`/driver/${r.truck_id}`)}" target="_blank" rel="noopener" data-ui-action="route-link">Driver App</a><button data-ui-action="copy-driver-link" data-truck-id="${r.truck_id}">${LANG==='th'?'':'Copy link'}</button><button data-ui-action="save-route-svg" data-truck-id="${r.truck_id}">SVG</button></div></article>`;}
function routeSvg(route,color){const pts=route.geometry||[];if(pts.length<2)return'<svg viewBox="0 0 400 130"><text x="200" y="68" text-anchor="middle" fill="#8795a3">No geometry</text></svg>';const xs=pts.map(p=>p[1]),ys=pts.map(p=>p[0]),minx=Math.min(...xs),maxx=Math.max(...xs),miny=Math.min(...ys),maxy=Math.max(...ys),w=Math.max(maxx-minx,1e-9),h=Math.max(maxy-miny,1e-9),P=14;const mapped=pts.map(p=>[P+(p[1]-minx)/w*(400-2*P),P+(maxy-p[0])/h*(130-2*P)]);return`<svg viewBox="0 0 400 130" xmlns="http://www.w3.org/2000/svg"><path d="M${mapped.map(p=>p.join(',')).join(' L')}" fill="none" stroke="${color}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><circle cx="${mapped[0][0]}" cy="${mapped[0][1]}" r="6" fill="#0b1f3a" stroke="#fff" stroke-width="2"/>${route.stops.slice(1,-1).map(s=>{const nearest=mapped[Math.min(mapped.length-1,Math.round(s.sequence/(Math.max(1,route.stops.length-1))*(mapped.length-1)))];return`<circle cx="${nearest[0]}" cy="${nearest[1]}" r="3.5" fill="${color}" stroke="#fff" stroke-width="1.5"/>`;}).join('')}</svg>`;}
window.focusTruck=id=>{const r=latestRoutes().find(x=>+x.truck_id===+id);if(r?.geometry?.length){activate('dispatch');routesMap.fitBounds(r.geometry,{padding:[50,50]});}};
window.copyDriverLink=async id=>{const url=new URL(withToken(`/driver/${id}`),location.origin).href;try{await navigator.clipboard.writeText(url);toast('Driver link copied',`Truck ${id}`);}catch{prompt('Copy driver link',url);}};
window.saveRouteSvg=id=>{const r=latestRoutes().find(x=>+x.truck_id===+id);if(!r)return;const svg=routeSvg(r,ROUTE_COLORS[latestRoutes().indexOf(r)%ROUTE_COLORS.length]);const blob=new Blob([svg],{type:'image/svg+xml'}),a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=`truck_${id}_route.svg`;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);};

function routeSequenceLabel(status){
  if(status.phase==='stale')return 'historical sequence — update required';
  if(status.phase==='prepared')return 'initial sequence awaiting optimization';
  if(status.phase==='running')return 'saved sequence — optimization in progress';
  return status.completed?'validated work-point sequence':'sequence awaiting validation';
}
function lastMatch(text,re,fallback='—'){const m=[...text.matchAll(re)];return m.length?m.at(-1)[1]:fallback;}

function bindDynamicNavigation(){$$('[data-go]').forEach(b=>b.onclick=()=>{if(b.dataset.workflowStep==='places'){focusWorkPointEntry();return;}activate(b.dataset.go);});}
function bindImages(){$$('[data-image]').forEach(el=>{const open=()=>{$('#lightboxImage').src=el.dataset.image;$('#lightboxCaption').textContent=el.dataset.caption||'';revealDialog($('#imageLightbox'),'#closeLightbox');};el.onclick=open;el.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();open();}};});}
function toggleMapTheme(trigger){openMapStyleMenu(trigger||MAP_STYLE_MENU_TRIGGER||$('#toggleSatelliteBtn'));}
function handleGlobalOptimize(){
  if(!STATE){setConnectionState(false,LANG==='th'?' Runtime ':'Wait for the runtime connection before optimizing.');return;}
  const blocking=(STATE.preflight?.checks||[]).filter(check=>!check.ok&&['source','depot','customers'].includes(check.id));
  if(blocking.length){activate('optimize');toast(LANG==='th'?'':'Plan needs attention',blocking.map(x=>x.label).join(' · '));return;}
  startOptimize(null);
}

function bind(){
  $$('.nav-item').forEach(b=>b.addEventListener('click',()=>activate(b.dataset.view)));bindDynamicNavigation();
  $('#judgeModeBtn').onclick=()=>setJudgeMode(!JUDGE_MODE);
  $('#mobileMenuBtn').onclick=()=>setMenuOpen(!$('#appShell').classList.contains('menu-open'));
  $('.main-shell').addEventListener('click',e=>{if(window.innerWidth<=900&&$('#appShell').classList.contains('menu-open')&&!e.target.closest('#mobileMenuBtn'))setMenuOpen(false);});
  $('#globalOptimizeBtn').onclick=handleGlobalOptimize;$('#heroDemoBtn').onclick=()=>loadDemo(false);$('#planDemoBtn').onclick=()=>loadDemo(false);$('#randomizeBtn').onclick=()=>{$('#scenarioBuilder').classList.toggle('hidden');updateScenarioSummary();};
  $('#searchBtn').onclick=searchPlaces;$('#searchQuery').addEventListener('keydown',e=>{if(e.key==='Enter')searchPlaces();});
  $('#mapAddBtn').onclick=()=>{const depot=(STATE.places||[]).find(p=>p.role==='depot');if(!depot){toast(LANG==='th'?' Depot ':'Choose a depot first',LANG==='th'?' Depot':'Search a place and set it as the depot.',true);return;}if(!activeSourceOperational()){if(sourceCoverageMismatch())openMatchingRegion();else{REGION_FORCE_OPEN=true;activate('command');renderRegionSetup();toast(LANG==='th'?' regional road source ':'Choose and verify an operating-region road source first',LANG==='th'?'':'This is a one-time setup.',true);}return;}mapAddMode=true;updateMapMode();toast(LANG==='th'?'':'Destination pick mode',LANG==='th'?' ':'Click the destination; FleetRoute can expand the operating graph when needed.');};
  $('#cancelMapMode').onclick=()=>{mapAddMode=false;updateMapMode();};
  $('#cancelAccessPreviewBtn').onclick=clearAccessInspector;
  $('#previewSetDepotBtn').onclick=()=>{if(selectedCandidate)saveDepotCandidate(selectedCandidate);};
  $('#previewAddCustomerBtn').onclick=()=>{if(selectedCandidate&&selectedCandidateAccess?.valid)openPlaceModal(selectedCandidate,selectedCandidateAccess,'customer');};
  $('#prepareAreaInlineBtn').onclick=prepareSelectedCandidate;
  $('#closeScenarioBtn').onclick=()=>$('#scenarioBuilder').classList.add('hidden');$('#generateScenarioBtn').onclick=()=>generateScenario(true);$('#generateOnlyBtn').onclick=()=>generateScenario(false);
  $$('.scenario-preset').forEach(btn=>btn.onclick=()=>applyScenarioPreset(btn.dataset.scenarioPreset));
  ['scenarioCount','scenarioDemandProfile','scenarioRadius','scenarioSeed','scenarioDemandMode','scenarioDemandMin','scenarioDemandMax','scenarioServiceMode','scenarioServiceMin','scenarioServiceMax','scenarioTimeWindow','trucks','capacity'].forEach(id=>{$('#'+id)?.addEventListener('input',updateScenarioSummary);$('#'+id)?.addEventListener('change',updateScenarioSummary);});
  $$('#operatingPresets button').forEach(btn=>btn.onclick=()=>{$('#operatingRadius').value=btn.dataset.radius;syncOperatingPreset();});
  $('#fitPlanBtn').onclick=()=>{const p=STATE.places||[];if(p.length)planMap.fitBounds(p.map(x=>[x.lat,x.lon]),{padding:[48,48],maxZoom:16});};
  for(const id of ['toggleSatelliteBtn','roadMapStyleBtn','dispatchMapStyleBtn']){$('#'+id).onclick=event=>{event.stopPropagation();openMapStyleMenu(event.currentTarget);};}
  document.addEventListener('pointerdown',event=>{const menu=$('#fleetMapStyleMenu');if(!menu||menu.classList.contains('hidden'))return;if(menu.contains(event.target)||MAP_STYLE_MENU_TRIGGER?.contains(event.target))return;closeMapStyleMenu();});
  document.addEventListener('keydown',event=>{if(event.key==='Escape')closeMapStyleMenu();});
  window.addEventListener('resize',closeMapStyleMenu,{passive:true});
  $('#fitRoadsBtn').onclick=()=>{const b=roadGeojson?.bounds,p=STATE.places||[];if(b&&[b.south,b.west,b.north,b.east].every(Number.isFinite))roadsMap.fitBounds([[b.south,b.west],[b.north,b.east]],{padding:[34,34],maxZoom:16});else if(p.length)roadsMap.fitBounds(p.map(x=>[+x.lat,+x.lon]),{padding:[48,48],maxZoom:16});};
  $('#importCsvBtn').onclick=()=>$('#csvInput').click();$('#clearPlanBtn').onclick=clearPlan;$('#csvInput').onchange=async e=>{if(e.target.files?.[0])try{await importCsv(e.target.files[0]);}catch(x){toast('CSV',x.message,true);}finally{e.target.value='';}};
  $('#planToRoadsBtn').onclick=()=>activate('roads');
  $('#saveRoadSettingsBtn').onclick=()=>saveSettings(true).catch(()=>{});$('#buildNetworkBtn').onclick=buildNetwork;
  $('#downloadRegionBtn').onclick=downloadRegionSource;$('#refreshOsmStatusBtn').onclick=refreshOsmStatus;$('#deleteOsmSourceBtn').onclick=deleteRegionSource;
  $('#showNetworkLayerBtn').onclick=async()=>{await loadRoadLayer(true);toast(LANG==='th'?'':'Road layer loaded',roadGeojson?.truncated?'Layer was simplified for browser performance':'');};
  $$('[data-road-style]').forEach(b=>b.onclick=()=>{roadStyle=b.dataset.roadStyle;$$('[data-road-style]').forEach(x=>x.classList.toggle('active',x===b));ROAD_RENDER_KEY='';renderRoadMap();});
  $('#selectClosureEdgeBtn').onclick=async()=>{if(!STATE.network?.access_ready){toast(LANG==='th'?'':'No road graph',LANG==='th'?' Operating Graph ':'Prepare the operating graph first',true);return;}closurePickMode=!closurePickMode;roadsMap.getContainer().style.cursor=closurePickMode?'crosshair':'';ROAD_RENDER_KEY='';await loadRoadLayer(!roadGeojson);renderRoadMap();$('#selectClosureEdgeBtn').classList.toggle('active',closurePickMode);toast(closurePickMode?(LANG==='th'?'':'Road-segment selection'):(LANG==='th'?'':'Road selection cancelled'),closurePickMode?(LANG==='th'?'':'Click the actual road line on the map'):'');};
  $('#saveClusterPolicyBtn').onclick=saveClusterPolicy;$('#runClusterBenchmarkBtn').onclick=runClusterBenchmark;
  $('#optimizeNowBtn').onclick=()=>startOptimize(null);$('#rerunCurrentGraphBtn').onclick=()=>startOptimize(false);$('#saveSolverSettingsBtn').onclick=()=>saveSettings(true).catch(()=>{});$('#viewCurrentLogBtn').onclick=()=>{const j=activeJob()||latestJob();if(j){selectedJobId=j.id;activate('activity');selectJob(j.id);}else toast('No run yet');};
  $('#chartFullBtn').onclick=()=>renderAnalytics(false);$('#chartZoomBtn').onclick=()=>renderAnalytics(true);$('#buildConvergenceBtn').onclick=buildConvergenceReport;
  $('#showAllRoutesBtn').onclick=()=>{const all=latestRoutes().flatMap(r=>r.geometry||[]);if(all.length)routesMap.fitBounds(all,{padding:[35,35]});};
  $('#refreshBtn').onclick=()=>refresh(false);$('#toggleRawLogBtn').onclick=async()=>{const pre=$('#jobLog'),switcher=$('#logSourceSwitch'),notice=$('#logSourceNotice');const opening=pre.classList.contains('hidden');pre.classList.toggle('hidden');switcher.classList.toggle('hidden',!opening);notice.classList.toggle('hidden',!opening);$('#toggleRawLogBtn').textContent=opening?(LANG==='th'?' Console':'Hide console'):(LANG==='th'?' Console':'Show console');if(opening&&selectedJobId){await fetchJobLogChunk(selectedJobId,false,JOB_LOG_SOURCE);renderOpenConsole();}};$('#logSourceRawBtn').onclick=()=>selectLogSource('raw');$('#logSourceStdoutBtn').onclick=()=>selectLogSource('stdout');$('#logSourceStderrBtn').onclick=()=>selectLogSource('stderr');$('#logSourceAuditBtn').onclick=()=>selectLogSource('audit');
  $$('[data-close-modal]').forEach(b=>b.onclick=closePlaceModal);$('#placeModal').onclick=e=>{if(e.target.id==='placeModal')closePlaceModal();};$('#saveDepotBtn').onclick=()=>saveNewPlace('depot');$('#saveCustomerBtn').onclick=()=>saveNewPlace('customer');$('#updatePlaceBtn').onclick=updatePlaceFromModal;
  $('#distanceRiskCancel').onclick=()=>closeDistanceRisk(false);$('#distanceRiskClose').onclick=()=>closeDistanceRisk(false);$('#distanceRiskContinue').onclick=()=>closeDistanceRisk(true);$('#distanceRiskModal').onclick=e=>{if(e.target.id==='distanceRiskModal')closeDistanceRisk(false);};
  $$('[data-close-closure]').forEach(b=>b.onclick=closeClosureModal);$('#closureModal').onclick=e=>{if(e.target.id==='closureModal')closeClosureModal();};$('#submitClosureBtn').onclick=submitClosure;
  $('#closeLightbox').onclick=()=>dismissDialog($('#imageLightbox'));$('#imageLightbox').onclick=e=>{if(e.target.id==='imageLightbox')dismissDialog($('#imageLightbox'));};
}


// =============================================================================
// REALTIME RUNTIME OVERRIDES — measured progress, streamed logs, fast maps
// =============================================================================
let ROUTE_CACHE = null;
let ROUTE_CACHE_ID = null;
let JOB_STREAM = null;
let JOB_STREAM_ID = null;
let JOB_LOG_OFFSETS = {raw:new Map(),stdout:new Map(),stderr:new Map(),audit:new Map()};
let JOB_LOG_TEXT = {raw:new Map(),stdout:new Map(),stderr:new Map(),audit:new Map()};
let JOB_LOG_TRUNCATED = {raw:new Map(),stdout:new Map(),stderr:new Map(),audit:new Map()};
const JOB_LOG_FETCHING = new Map();
const LIVE_LOG_BUFFER_LIMIT = 2 * 1024 * 1024;
let LAST_CONSOLE_RENDER_KEY = '';
let JOB_LOG_SOURCE = 'audit';
let PENDING_CANDIDATE_JOB = null;
let LAST_STATE_REFRESH = 0;

function clampPercent(value){
  const n=Number(value);
  return Number.isFinite(n)?Math.round(Math.max(0,Math.min(100,n))*10)/10:0;
}
function percentText(value){const n=clampPercent(value);return `${n.toLocaleString(undefined,{maximumFractionDigits:1})}%`;}
function humanBytes(value){let n=Number(value);if(!Number.isFinite(n)||n<0)return'—';for(const unit of ['B','KB','MB','GB','TB']){if(n<1024||unit==='TB')return`${n.toLocaleString(undefined,{maximumFractionDigits:1})} ${unit}`;n/=1024;}return'—';}
function humanDuration(value){const s=Math.max(0,Number(value)||0);if(s<60)return`${num(s,1)} s`;if(s<3600)return`${Math.floor(s/60)}m ${Math.round(s%60)}s`;return`${Math.floor(s/3600)}h ${Math.floor((s%3600)/60)}m`;}
function liveOf(job){return job?.result?.live||{};}
function jobElapsed(job){
  const live=liveOf(job),fromLive=Number(live.job_elapsed_s);
  if(Number.isFinite(fromLive)&&['succeeded','failed','cancelled'].includes(job?.status))return fromLive;
  if(!job?.started_at)return 0;
  const end=job.finished_at?new Date(job.finished_at).getTime():Date.now();
  return Math.max(0,(end-new Date(job.started_at).getTime())/1000);
}
function measuredPhase(job){
  const live=liveOf(job),phase=Number(live.phase_progress);
  return live.progress_kind==='measured'&&Number.isFinite(phase)?clampPercent(phase):null;
}
function stageElapsed(job){
  const live=liveOf(job);let value=Math.max(0,Number(live.stage_elapsed_s)||0);
  if(job?.status==='running'&&job?.heartbeat_at){value+=Math.max(0,(Date.now()-new Date(job.heartbeat_at).getTime())/1000);}
  return value;
}
function blockingJob(){return (STATE?.jobs||[]).find(j=>['queued','running'].includes(j.status)&&j.kind!=='evidence')||null;}
function stageOf(job){return Math.max(0,Number(job?.stage_index)||Number(job?.result?.live?.stage_index)||0);}
function currentStageLabel(job){const live=liveOf(job),terminal=['failed','cancelled','succeeded'].includes(job?.status);if(terminal){if(job?.stage_label)return job.stage_label;if(job?.status==='failed')return 'Stopped with error';if(job?.status==='cancelled')return 'Cancelled';return 'Complete';}return live.phase_label||job?.stage_label||live.message||'Working';}
function jobProgress(job){
  if(!job)return 0;
  if(job.status==='succeeded')return 100;
  const count=Math.max(1,Number(job.stage_count)||Number(liveOf(job).stage_count)||1);
  const index=Math.max(0,Number(job.stage_index)||Number(liveOf(job).stage_index)||0);
  const measured=measuredPhase(job);
  const completed=Math.max(0,index-1);
  // Reporters persist an absolute overall percentage alongside any measured
  // phase percentage. Prefer that absolute value so a new measured phase never
  // makes the bar jump backwards (for example 62% -> 40%).
  if(measured!=null){
    const absolute=Number(liveOf(job).progress ?? job.progress);
    if(Number.isFinite(absolute))return clampPercent(absolute);
    return clampPercent((completed+measured/100)/count*100);
  }
  const absolute=Number(job.progress);
  if(Number.isFinite(absolute)&&absolute>0)return clampPercent(absolute);
  return clampPercent(completed/count*100);
}
function jobIndeterminate(job){
  if(job?.status!=='running')return false;
  const live=liveOf(job);
  return live.progress_kind!=='measured';
}
function progressLabel(job){
  if(job?.status==='failed')return LANG==='th'?'':'Stopped with error';
  if(job?.status==='cancelled')return LANG==='th'?'':'Cancelled';
  if(job?.status==='succeeded')return LANG==='th'?'':'Complete';
  const live=liveOf(job),phase=measuredPhase(job),elapsed=jobElapsed(job);
  if(phase!=null){
    const isBytes=Number(live.total)>0&&(!live.unit||live.unit==='bytes');
    const measuredCount=Number(live.total)>0&&live.unit&&live.unit!=='bytes'?`${num(live.done,0)} / ${num(live.total,0)} ${esc(live.unit)}`:'';
    const bytes=isBytes?`${humanBytes(live.done)} / ${humanBytes(live.total)}`:'';
    const rate=Number(live.rate_bps)>0?`${humanBytes(live.rate_bps)}/s`:'';
    const eta=Number.isFinite(Number(live.eta_s))&&Number(live.eta_s)>=0?`${LANG==='th'?'':'ETA'} ${humanDuration(live.eta_s)}`:'';
    const metric=live.phase_metric==='time_budget_used'?(LANG==='th'?' time budget':'time budget used'):'';
    return [percentText(phase),metric,measuredCount,bytes,rate,eta,`${LANG==='th'?'':'stage'} ${humanDuration(stageElapsed(job))}`].filter(Boolean).join(' · ');
  }
  const index=Math.max(1,stageOf(job)),count=Math.max(1,Number(job?.stage_count)||Number(live.stage_count)||1);
  return `${LANG==='th'?'':'Stage'} ${index}/${count} · ${LANG==='th'?'':'stage'} ${humanDuration(stageElapsed(job))} · ${LANG==='th'?'':'total'} ${humanDuration(elapsed)}`;
}

function baseStagesForJob(job){
  const sets={
    'osm-source-download':[['Source metadata',' checksum'],['Download',' road extract  streaming'],['Integrity',' checksum '],['Ready','']],
    'network-build':[['Local source',' road extract  local SSD'],['Road graph','Extract, filter  directed graph'],['Road access','–'],['Ready',' graph  spatial index  RAM']],
    'network-expand':[['Local source',' road extract  local SSD'],['Road graph',' directed graph'],['Road access',''],['Ready',' spatial index ']],
    'solve':[['Operating graph',' RAM  GraphML '],['Solver input',' input.txt'],['Initial plan',' capacity   time windows'],['routing engine',' binary  compile '],['Clustering',''],['Improve',' output  routing '],['Validate & apply',' ']],
    'network-and-solve':[['Operating graph',''],['Solver input',' input '],['Initial plan',''],['routing engine',' binary'],['Clustering',' warm start'],['Improve',''],['Validate & apply',' routing ']],
    'scenario-route':[['Contract',' Fleet  Demand'],['Graph',' RAM'],['Work points','–'],['Initial plan',''],['routing handoff',' Optimizer ']],
    'clustering-benchmark':[['Operating graph',''],['Benchmark input',' input'],['All methods',' clustering method'],['Figures',' scorecard ']],
    'convergence-analysis':[['Source receipt',' SHA-256  convergence.csv'],['Publication figures',' telemetry ']],
    'evidence':[['Convergence',' log '],['Driver HTML',' all-truck'],['Evidence ZIP','']]
  };
  return sets[job?.kind]||Array.from({length:Math.max(1,Number(job?.stage_count)||1)},(_,i)=>[`Stage ${i+1}`,'']);
}

async function refresh(silent=true,forceRoutes=false){
  const requestSeq=++STATE_REQUEST_SEQ;
  try{
    const includeRoutes=forceRoutes||!STATE||!ROUTE_CACHE;
    const next=await api(`/api/state?include_routes=${includeRoutes?'true':'false'}`);
    if(requestSeq!==STATE_REQUEST_SEQ)return true;
    if(next.latest_routes?.id){ROUTE_CACHE=next.latest_routes;ROUTE_CACHE_ID=next.latest_routes.id;}
    const summaryId=next.latest_route_summary?.id||null;
    if(summaryId&&summaryId!==ROUTE_CACHE_ID){
      const latest=await api('/api/routes/latest');
      if(requestSeq!==STATE_REQUEST_SEQ)return true;
      if(latest?.id){ROUTE_CACHE=latest;ROUTE_CACHE_ID=latest.id;}
    }
    if(requestSeq!==STATE_REQUEST_SEQ)return true;
    next.latest_routes=ROUTE_CACHE;
    STATE=next;
    STATE_APPLIED_SEQ=requestSeq;
    LAST_STATE_REFRESH=Date.now();
    setConnectionState(true);
    applySettings();renderAll();subscribeToActiveJob();
    return true;
  }catch(e){
    // An older request is not allowed to mark the application offline after a
    // newer refresh has already started/succeeded.
    if(requestSeq!==STATE_REQUEST_SEQ)return true;
    setConnectionState(false,e.message);if(!silent)toast(LANG==='th'?'':'Refresh failed',e.message,true);return false;
  }
}



function resetJobLogs(jobId){
  for(const source of ['raw','stdout','stderr','audit']){
    JOB_LOG_OFFSETS[source].set(jobId,0);
    JOB_LOG_TEXT[source].set(jobId,'');
    JOB_LOG_TRUNCATED[source].set(jobId,false);
  }
  SOLVER_LIVE_PARSE_CACHE.delete(Number(jobId));
  LAST_CONSOLE_RENDER_KEY='';
}
function logText(jobId,source=JOB_LOG_SOURCE){return JOB_LOG_TEXT[source].get(jobId)||'';}
function appendLiveLog(jobId,source,text){
  if(!text)return;
  let next=(JOB_LOG_TEXT[source].get(jobId)||'')+text;
  if(next.length>LIVE_LOG_BUFFER_LIMIT){
    next=next.slice(-LIVE_LOG_BUFFER_LIMIT);
    JOB_LOG_TRUNCATED[source].set(jobId,true);
  }
  JOB_LOG_TEXT[source].set(jobId,next);
}
function tailLog(text,maxLines=10){
  if(!text)return'';
  let cursor=text.length,count=0;
  while(cursor>0&&count<maxLines+4){
    cursor=text.lastIndexOf('\n',cursor-1);
    if(cursor<0){cursor=0;break;}
    count+=1;
  }
  return text.slice(cursor).split(/\r?\n/).filter(Boolean).slice(-maxLines).join('\n');
}
function tickLiveLogTail(jobId){
  if(+selectedJobId!==+jobId)return;
  const raw=logText(jobId,'raw');
  const meta=$('#jobRawTailMeta'),pre=$('#jobRawTailText');
  if(meta)meta.textContent=raw?`${num(raw.length)} chars${JOB_LOG_TRUNCATED.raw.get(jobId)?' · tail buffer':''}`:'waiting for process output';
  if(pre&&raw)renderLogInto(pre,tailLog(raw,10));
}

async function fetchJobLogChunk(jobId,reset=false,source='raw'){
  source=['raw','stdout','stderr','audit'].includes(source)?source:'raw';
  const key=`${source}:${jobId}`;
  if(reset){
    JOB_LOG_OFFSETS[source].set(jobId,0);
    JOB_LOG_TEXT[source].set(jobId,'');
    JOB_LOG_TRUNCATED[source].set(jobId,false);
    LAST_CONSOLE_RENDER_KEY='';
  }
  if(JOB_LOG_FETCHING.has(key))return JOB_LOG_FETCHING.get(key);
  const task=(async()=>{
    const offset=JOB_LOG_OFFSETS[source].get(jobId)||0;
    try{
      const tailQuery=reset?`&tail_bytes=${LIVE_LOG_BUFFER_LIMIT}&limit=${LIVE_LOG_BUFFER_LIMIT}`:'';
      const chunk=await api(`/api/jobs/${jobId}/log-chunk?source=${source}&offset=${offset}${tailQuery}`);
      appendLiveLog(jobId,source,chunk.text||'');
      if(chunk.truncated_start)JOB_LOG_TRUNCATED[source].set(jobId,true);
      JOB_LOG_OFFSETS[source].set(jobId,chunk.next_offset??offset);
      if(source==='raw')tickLiveLogTail(jobId);
      if(+selectedJobId===+jobId&&JOB_LOG_SOURCE===source)renderOpenConsole();
      return chunk;
    }catch(e){console.warn('log chunk',source,e);return null;}
    finally{JOB_LOG_FETCHING.delete(key);}
  })();
  JOB_LOG_FETCHING.set(key,task);
  return task;
}

async function selectLogSource(source){
  JOB_LOG_SOURCE=['raw','stdout','stderr','audit'].includes(source)?source:'audit';
  CONSOLE_FOLLOW=true;
  if(selectedJobId&&!logText(selectedJobId,JOB_LOG_SOURCE))await fetchJobLogChunk(selectedJobId,true,JOB_LOG_SOURCE);
  renderOpenConsole();
}
function shouldStreamJobLogs(jobId){
  return +selectedJobId===+jobId&&(currentView==='activity'||CONSOLE_OPEN);
}
let JOB_STREAM_LAST_UPDATE=0;
const JOB_TERMINAL_PENDING=new Map(),JOB_TERMINAL_BUSY=new Set(),JOB_TERMINAL_DONE=new Set();
function jobPollingRequired(){
  // Cloudflare explicitly excludes SSE support from Quick Tunnels.
  return typeof EventSource==='undefined'||/(^|\.)trycloudflare\.com$/i.test(location.hostname);
}
async function handleJobSnapshot(snapshot){
  const id=Number(snapshot.id),terminal=['succeeded','failed','cancelled'].includes(snapshot.status);
  if(JOB_TERMINAL_DONE.has(id)||(!terminal&&JOB_TERMINAL_PENDING.has(id)))return;
  if(terminal){
    JOB_TERMINAL_PENDING.set(id,snapshot);
    if(JOB_TERMINAL_BUSY.has(id))return;
    JOB_TERMINAL_BUSY.add(id);
  }
  try{
    setConnectionState(true);mergeJobSnapshot(snapshot);
    if(shouldStreamJobLogs(snapshot.id)){await fetchJobLogChunk(snapshot.id,false,'raw');if(JOB_LOG_SOURCE!=='raw')await fetchJobLogChunk(snapshot.id,false,JOB_LOG_SOURCE);}
    if(currentView==='optimize'&&['solve','network-and-solve'].includes(snapshot.kind)){await Promise.all([fetchJobLogChunk(snapshot.id,false,'stderr'),fetchJobLogChunk(snapshot.id,false,'stdout')]);const liveJob=(STATE.jobs||[]).find(x=>+x.id===+snapshot.id)||snapshot;renderOptimizeTrace(liveJob);}
    if(terminal){
      if(JOB_STREAM&&+JOB_STREAM_ID===id){JOB_STREAM.close();JOB_STREAM=null;JOB_STREAM_ID=null;}
      if(['solve','network-and-solve'].includes(snapshot.kind))await Promise.all([fetchJobLogChunk(snapshot.id,true,'stderr'),fetchJobLogChunk(snapshot.id,true,'stdout')]);
      if(shouldStreamJobLogs(snapshot.id)){await fetchJobLogChunk(snapshot.id,true,'raw');if(JOB_LOG_SOURCE!=='raw')await fetchJobLogChunk(snapshot.id,true,JOB_LOG_SOURCE);}
      const candidateJob=PENDING_CANDIDATE_JOB&&+PENDING_CANDIDATE_JOB.jobId===+snapshot.id?PENDING_CANDIDATE_JOB:null;
      if(!await refresh(true,true))throw new Error('Final results have not refreshed yet; reconnecting.');
      if(snapshot.kind==='convergence-analysis'&&currentView==='analytics')await loadConvergence();
      const finished=(STATE.jobs||[]).find(x=>+x.id===+snapshot.id)||snapshot;
      const childId=Number(finished.result?.next_job_id||finished.result?.optimizer_job_id||0);
      if(childId){
        selectedJobId=childId;resetJobLogs(childId);
        if(currentView==='activity'||currentView==='optimize'){toast(LANG==='th'?' routing Solver ':'Handed off to the optimizer',`Job #${childId}`);}
        subscribeToActiveJob();
      }
      if(candidateJob&&snapshot.status==='succeeded'&&selectedCandidate){PENDING_CANDIDATE_JOB=null;await selectCandidate(selectedCandidate,selectedCandidate.preferredRole||'customer');}
      JOB_TERMINAL_PENDING.delete(id);JOB_TERMINAL_DONE.add(id);
      if(JOB_TERMINAL_DONE.size>200)JOB_TERMINAL_DONE.delete(JOB_TERMINAL_DONE.values().next().value);
    }
  }finally{if(terminal)JOB_TERMINAL_BUSY.delete(id);}
}
function subscribeToActiveJob(){
  const job=activeJob();
  if(!job||jobPollingRequired()){if(JOB_STREAM)JOB_STREAM.close();JOB_STREAM=null;JOB_STREAM_ID=null;return;}
  if(+JOB_STREAM_ID===+job.id&&JOB_STREAM)return;
  if(JOB_STREAM)JOB_STREAM.close();
  JOB_STREAM_ID=job.id;JOB_STREAM_LAST_UPDATE=Date.now();
  const stream=new EventSource(withToken(`/api/jobs/${job.id}/stream`));JOB_STREAM=stream;
  stream.addEventListener('snapshot',async event=>{
    if(JOB_STREAM!==stream)return;
    try{const snapshot=JSON.parse(event.data);JOB_STREAM_LAST_UPDATE=Date.now();await handleJobSnapshot(snapshot);}
    catch(error){setConnectionState(false,error.message);}
  });
  stream.addEventListener('job-event',async()=>{
    if(JOB_STREAM!==stream)return;
    try{if(shouldStreamJobLogs(job.id)){await fetchJobLogChunk(job.id,false,'raw');if(JOB_LOG_SOURCE!=='raw')await fetchJobLogChunk(job.id,false,JOB_LOG_SOURCE);}}
    catch(error){setConnectionState(false,error.message);}
  });
  stream.onerror=()=>{stream.close();if(JOB_STREAM!==stream)return;JOB_STREAM=null;JOB_STREAM_ID=null;setTimeout(()=>refresh(true,false),1200);};
}

function observeMapSize(map,containerId){
  const element=document.getElementById(containerId);if(!element||typeof ResizeObserver==='undefined')return;
  let frame=0;const observer=new ResizeObserver(()=>{cancelAnimationFrame(frame);frame=requestAnimationFrame(()=>map.invalidateSize({pan:false,animate:false}));});
  observer.observe(element);MAP_RESIZE_OBSERVERS.push(observer);
}
const MAP_FALLBACK_TILE='data:image/svg+xml;charset=UTF-8,'+encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256"><rect width="256" height="256" fill="#eaf0f4"/><path d="M0 0H256V256H0Z M0 64H256M0 128H256M0 192H256M64 0V256M128 0V256M192 0V256" fill="none" stroke="#d5dee6" stroke-width="1"/><circle cx="128" cy="128" r="3" fill="#8093a3"/></svg>`);
function keylessOsmTiles(options={}){
  return L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{
    maxZoom:19,attribution:'© OpenStreetMap contributors',updateWhenZooming:false,keepBuffer:3,
    errorTileUrl:MAP_FALLBACK_TILE,
    ...options
  });
}
function keylessTerrainTiles(options={}){
  // World Topographic Map is a cached Web-Mercator tile service. If one
  // topographic tile fails, replace that tile with the matching OSM street
  // tile rather than the old diagnostic grid, so Terrain always remains a map.
  const layer=L.tileLayer('https://services.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}',{
    maxNativeZoom:19,maxZoom:19,
    attribution:'Tiles © Esri — Sources: Esri, TomTom, Garmin, FAO, NOAA, USGS, © OpenStreetMap contributors, GIS User Community',
    updateWhenZooming:false,keepBuffer:3,errorTileUrl:MAP_FALLBACK_TILE,
    ...options
  });
  layer.on('tileerror',event=>{
    const tile=event?.tile,coords=event?.coords;if(!tile||!coords||tile.dataset?.fleetOsmFallback==='1')return;
    tile.dataset.fleetOsmFallback='1';
    tile.src=`https://tile.openstreetmap.org/${coords.z}/${coords.x}/${coords.y}.png`;
  });
  return layer;
}
function mapTheme(){return MAP_THEMES[mapThemeIndex]||MAP_THEMES[0];}
function buildBasemapLayer(theme){
  const layer=theme?.provider==='topo'?keylessTerrainTiles():keylessOsmTiles();
  layer.__fleetThemeKey=theme?.key||'navigation';
  return layer;
}
function syncMapBasemap(map,theme){
  if(!map)return;
  const current=map.__fleetBaseLayer;
  if(current?.__fleetThemeKey===theme.key)return;
  const next=buildBasemapLayer(theme);
  next.addTo(map);
  if(current&&map.hasLayer(current))map.removeLayer(current);
  map.__fleetBaseLayer=next;
}
function updateMapStyleControls(theme){
  for(const id of ['#planMapStyleLabel','#roadMapStyleLabel','#dispatchMapStyleLabel']){const el=$(id);if(el)el.textContent=theme.label;}
  for(const id of ['#toggleSatelliteBtn','#roadMapStyleBtn','#dispatchMapStyleBtn']){
    const el=$(id);if(!el)continue;el.dataset.theme=theme.key;el.setAttribute('aria-label',`Choose map style · ${theme.label}`);el.title=`Map style · ${theme.label}`;
    const glyph=$('.map-style-glyph',el)||$('span[aria-hidden="true"]',el);if(glyph)glyph.textContent=theme.icon;
  }
}
function applyMapTheme(persist=true){
  const theme=mapTheme(),classes=MAP_THEMES.map(item=>`fleet-map-theme-${item.key}`).concat(['fleet-map-theme-operations','fleet-map-theme-street','fleet-map-theme-contrast']);
  for(const map of [planMap,roadsMap,routesMap,commandMap]){
    const el=map?.getContainer?.();if(!el)continue;el.classList.remove(...classes);el.classList.add(`fleet-map-theme-${theme.key}`);syncMapBasemap(map,theme);
  }
  document.body.dataset.mapTheme=theme.key;
  if(persist)storageWrite('localStorage','fleetroute_map_theme',theme.key);
  updateMapStyleControls(theme);
  const menu=$('#fleetMapStyleMenu');if(menu&&!menu.classList.contains('hidden'))renderMapStyleMenu();
}
function setMapTheme(key,persist=true){
  const index=MAP_THEMES.findIndex(theme=>theme.key===key);if(index<0)return;
  mapThemeIndex=index;applyMapTheme(persist);closeMapStyleMenu();
}
function cycleMapTheme(){mapThemeIndex=(mapThemeIndex+1)%MAP_THEMES.length;applyMapTheme(true);}
function ensureMapStyleMenu(){
  let menu=$('#fleetMapStyleMenu');if(menu)return menu;
  menu=document.createElement('div');menu.id='fleetMapStyleMenu';menu.className='map-style-menu hidden';menu.setAttribute('role','menu');menu.setAttribute('aria-label','Choose map style');
  menu.addEventListener('click',event=>{const option=event.target.closest('[data-map-theme-choice]');if(option)setMapTheme(option.dataset.mapThemeChoice,true);});
  document.body.appendChild(menu);return menu;
}
function renderMapStyleMenu(){
  const menu=ensureMapStyleMenu(),active=mapTheme().key;
  menu.innerHTML=`<div class="map-style-menu-head"><div><span>BASEMAP</span><b>Choose map style</b></div><small>Route and road evidence stay unchanged</small></div><div class="map-style-options">${MAP_THEMES.map(theme=>`<button type="button" role="menuitemradio" aria-checked="${theme.key===active?'true':'false'}" class="map-style-option ${theme.key===active?'active':''}" data-map-theme-choice="${theme.key}"><i class="map-style-preview preview-${theme.key}"><span>${theme.icon}</span></i><span class="map-style-option-copy"><b>${esc(theme.label)}</b><small>${esc(theme.description)}</small></span><em>${theme.provider==='topo'?'TOPO':'OSM'}</em>${theme.key===active?'<strong>✓</strong>':''}</button>`).join('')}</div><div class="map-style-menu-foot">Navigation/Clean/Night use OpenStreetMap. Terrain uses Esri World Topographic Map with per-tile OSM fallback.</div>`;
}
function openMapStyleMenu(trigger){
  const menu=ensureMapStyleMenu();MAP_STYLE_MENU_TRIGGER=trigger;renderMapStyleMenu();menu.classList.remove('hidden');
  const rect=trigger.getBoundingClientRect(),width=Math.min(340,window.innerWidth-24);menu.style.width=`${width}px`;
  const desiredLeft=Math.min(Math.max(12,rect.right-width),window.innerWidth-width-12);menu.style.left=`${desiredLeft}px`;
  const menuHeight=Math.min(420,menu.scrollHeight||360),below=window.innerHeight-rect.bottom;
  if(below>=Math.min(menuHeight,360)){menu.style.top=`${Math.min(window.innerHeight-menuHeight-12,rect.bottom+8)}px`;menu.style.bottom='auto';}
  else{menu.style.top='auto';menu.style.bottom=`${Math.max(12,window.innerHeight-rect.top+8)}px`;}
  trigger.setAttribute('aria-expanded','true');
}
function closeMapStyleMenu(){
  const menu=$('#fleetMapStyleMenu');if(menu)menu.classList.add('hidden');if(MAP_STYLE_MENU_TRIGGER)MAP_STYLE_MENU_TRIGGER.setAttribute('aria-expanded','false');MAP_STYLE_MENU_TRIGGER=null;
}
function setupMapPanes(map){
  if(!map)return;
  for(const [name,z] of [['operating-area',405],['route-halo',410],['road-network',420],['route-main',430],['closure',440],['access',450],['fleet-stops',460]]){
    const pane=map.getPane(name)||map.createPane(name);pane.style.zIndex=String(z);pane.style.pointerEvents=name==='route-halo'?'none':'';
  }
}
function addMetricScale(map){
  if(!map||map.__fleetScale)return;map.__fleetScale=L.control.scale({imperial:false,maxWidth:110,position:'bottomright'}).addTo(map);
}
function routeStopIcon(routeIndex,sequence,depot=false){
  const color=ROUTE_COLORS[routeIndex%ROUTE_COLORS.length];
  return L.divIcon({className:'fleet-map-icon-wrap',html:depot?`<span class="route-stop-icon depot" style="--route-color:${color}"><i>⌂</i></span>`:`<span class="route-stop-icon" style="--route-color:${color}"><i>${Math.max(1,Number(sequence)||1)}</i></span>`,iconSize:[depot?36:28,depot?36:28],iconAnchor:[depot?18:14,depot?18:14],popupAnchor:[0,depot?-21:-17]});
}
function renderOperatingArea(layer,depot){
  if(!layer)return;layer.clearLayers();
  const radius=Math.max(0,+STATE?.fleet?.operating_radius_m||0);if(!depot||!radius||!Number.isFinite(+depot.lat)||!Number.isFinite(+depot.lon))return;
  L.circle([+depot.lat,+depot.lon],{pane:'operating-area',radius,color:'#0f8075',weight:1.6,opacity:.72,dashArray:'8 7',fillColor:'#31a993',fillOpacity:.045,interactive:false}).addTo(layer);
}
function initMaps(){
  baseLayers=[];
  planMap=L.map('planMap',{zoomControl:false,preferCanvas:true,zoomAnimation:true,markerZoomAnimation:true}).setView([20,0],2);
  syncMapBasemap(planMap,mapTheme());L.control.zoom({position:'bottomright'}).addTo(planMap);setupMapPanes(planMap);addMetricScale(planMap);
  roadsMap=L.map('roadsMap',{zoomControl:false,preferCanvas:true,zoomAnimation:true,markerZoomAnimation:true}).setView([20,0],2);
  syncMapBasemap(roadsMap,mapTheme());L.control.zoom({position:'bottomright'}).addTo(roadsMap);setupMapPanes(roadsMap);addMetricScale(roadsMap);
  routesMap=L.map('routesMap',{zoomControl:false,preferCanvas:true,zoomAnimation:true,markerZoomAnimation:true}).setView([20,0],2);
  syncMapBasemap(routesMap,mapTheme());L.control.zoom({position:'bottomright'}).addTo(routesMap);setupMapPanes(routesMap);addMetricScale(routesMap);
  // Attribution stays visible even on the Fleet Overview map. Both supported
  // providers require visible attribution, so presentation mode must not hide it.
  commandMap=L.map('commandMap',{zoomControl:false,attributionControl:true,preferCanvas:true,zoomAnimation:true,markerZoomAnimation:true,scrollWheelZoom:false}).setView([20,0],2);
  syncMapBasemap(commandMap,mapTheme());setupMapPanes(commandMap);
  planOperatingLayer=L.layerGroup().addTo(planMap);planMarkers=L.layerGroup().addTo(planMap);planAccessLines=L.layerGroup().addTo(planMap);planPreviewLayer=L.layerGroup().addTo(planMap);
  roadOperatingLayer=L.layerGroup().addTo(roadsMap);roadLayer=L.layerGroup().addTo(roadsMap);roadPlaceLayer=L.layerGroup().addTo(roadsMap);closureLayer=L.layerGroup().addTo(roadsMap);closurePreviewLayer=L.layerGroup().addTo(roadsMap);
  routeHaloLayer=L.layerGroup().addTo(routesMap);routeLayer=L.layerGroup().addTo(routesMap);routeStopLayer=L.layerGroup().addTo(routesMap);
  commandRouteLayer=L.layerGroup().addTo(commandMap);commandStopLayer=L.layerGroup().addTo(commandMap);
  planMap.on('click',e=>{if(mapAddMode)previewMapPlace(e.latlng);});
  roadsMap.on('click',e=>{if(closurePickMode)previewClosureEdge(e.latlng);});
  roadsMap.on('moveend zoomend',()=>{
    if(currentView!=='roads'||!roadGeojson)return;
    clearTimeout(ROAD_LOAD_TIMER);ROAD_LOAD_TIMER=setTimeout(()=>loadRoadLayer(true),260);
  });
  observeMapSize(planMap,'planMap');observeMapSize(roadsMap,'roadsMap');observeMapSize(routesMap,'routesMap');observeMapSize(commandMap,'commandMap');
  applyMapTheme(false);
}


async function buildNetwork(){
  if(!activeSourceOperational()){if(sourceCoverageMismatch())openMatchingRegion();else{REGION_FORCE_OPEN=true;activate('command');renderRegionSetup();toast('Regional road source is missing','Choose and verify a region that covers the current plan.',true);}return;}
  if(!(STATE.places||[]).some(p=>p.role==='depot')){toast(LANG==='th'?' Depot ':'Choose a depot first','',true);activate('plan');return;}
  if(!await confirmDistanceRisk('prepare this operating graph'))return;
  try{
    await saveSettings(false);
    const result=await api('/api/network/build',{method:'POST',body:'{}'});
    selectedJobId=result.job_id;resetJobLogs(result.job_id);
    toast(LANG==='th'?'':'Operating graph queued',`Job #${result.job_id}`);
    await refresh(true,false);activate('activity');subscribeToActiveJob();
  }catch(e){toast(LANG==='th'?'':'Could not queue graph build',friendlyError(e.message),true);}
}

async function prepareSelectedCandidate(){
  if(!selectedCandidate)return;
  if(!activeSourceOperational()){if(sourceCoverageMismatch())openMatchingRegion();else{REGION_FORCE_OPEN=true;activate('command');renderRegionSetup();toast('Regional road source',LANG==='th'?'':'Choose and verify a region first',true);}return;}
  if(!(STATE.places||[]).some(p=>p.role==='depot')){toast(LANG==='th'?' Depot ':'Choose a depot first','',true);return;}
  try{
    await saveSettings(false);
    const result=await api('/api/access/prepare',{method:'POST',body:JSON.stringify({lat:selectedCandidate.lat,lon:selectedCandidate.lon,max_snap_m:+$('#snapMax').value||350})});
    PENDING_CANDIDATE_JOB={jobId:result.job_id,candidate:{...selectedCandidate}};selectedJobId=result.job_id;
    toast(LANG==='th'?' Operating Graph':'Expanding operating graph',`Job #${result.job_id}`);
    await refresh(true,false);activate('plan');subscribeToActiveJob();
  }catch(e){toast(LANG==='th'?'':'Could not queue graph expansion',friendlyError(e.message),true);}
}

async function loadRoadLayer(force=false){
  if(!roadsMap||!STATE?.network||STATE.network_stale?.stale)return null;
  const b=roadsMap.getBounds(),zoom=roadsMap.getZoom();
  const key=[b.getSouth(),b.getWest(),b.getNorth(),b.getEast()].map(v=>v.toFixed(4)).join(':')+`:${zoom}`;
  if(roadGeojson&&!force)return roadGeojson;
  if(force&&key===ROAD_VIEWPORT_KEY)return roadGeojson;
  const requestSeq=++ROAD_REQUEST_SEQ;
  if(ROAD_REQUEST_CONTROLLER)ROAD_REQUEST_CONTROLLER.abort();
  const controller=new AbortController();ROAD_REQUEST_CONTROLLER=controller;
  const btn=$('#showNetworkLayerBtn'),old=btn?.textContent;
  if(btn){btn.disabled=true;btn.textContent=LANG==='th'?'…':'Loading visible roads…';}
  try{
    const maxEdges=zoom<12?700:zoom<14?1400:zoom<16?2400:3600;
    const query=new URLSearchParams({south:b.getSouth().toFixed(7),west:b.getWest().toFixed(7),north:b.getNorth().toFixed(7),east:b.getEast().toFixed(7),max_edges:String(maxEdges)});
    const next=await api(`/api/network/viewport?${query}`,{signal:controller.signal});
    if(requestSeq!==ROAD_REQUEST_SEQ||controller.signal.aborted)return null;
    ROAD_VIEWPORT_KEY=key;ROAD_GEOJSON_REV+=1;next._clientRevision=ROAD_GEOJSON_REV;roadGeojson=next;ROAD_RENDER_KEY='';renderRoadMap();return roadGeojson;
  }catch(e){
    if(controller.signal.aborted||e?.name==='AbortError')return null;
    toast(LANG==='th'?'':'Road layer failed',e.message,true);return null;
  }
  finally{
    if(requestSeq===ROAD_REQUEST_SEQ){ROAD_REQUEST_CONTROLLER=null;if(btn){btn.disabled=false;btn.textContent=old||tr('showRoadLayer');}}
  }
}

function openClosureEdge(edge){
  pendingClosureEdge=edge;closurePickMode=false;roadsMap.getContainer().style.cursor='';$('#selectClosureEdgeBtn')?.classList.remove('active');ROAD_RENDER_KEY='';closurePreviewLayer.clearLayers();renderRoadMap();
  if(edge.geometry?.length){
    const geometry=edge.geometry.map(p=>[+p[0],+p[1]]);
    L.polyline(geometry,{pane:'closure',color:'#fff',weight:14,opacity:.92,lineCap:'round',interactive:false}).addTo(closurePreviewLayer);L.polyline(geometry,{pane:'closure',color:'#c9443a',weight:9,opacity:.98,lineCap:'round',interactive:false}).addTo(closurePreviewLayer);
    if(edge.snap_lat!=null&&edge.snap_lon!=null)L.marker([+edge.snap_lat,+edge.snap_lon],{icon:accessMarkerIcon(false),interactive:false}).addTo(closurePreviewLayer);
    requestAnimationFrame(()=>roadsMap.fitBounds(geometry,{padding:[70,70],maxZoom:18,animate:false}));
  }
  $('#closureSegmentPreview').innerHTML=`<h3>${esc(edge.road_name||(LANG==='th'?'':'Unnamed road'))}</h3><p>${esc(edge.highway||'road')} · ${esc(edge.direction_text||'directed edge')} · ${num(edge.snap_distance_m||0,0)} m</p>`;
  $('#closureTechnical').textContent=JSON.stringify(edge,null,2);revealDialog($('#closureModal'),'#closureReporter');
}
function renderRoadMap(){
  if(!roadsMap||!STATE)return;
  const places=STATE.places||[],closures=STATE.closures||[];
  const signature=JSON.stringify({
    road:roadGeojson?roadGeojson._clientRevision||[roadGeojson.rendered_edges,roadGeojson.bounds]:null,
    places:places.map(p=>[p.id,p.role,+p.lat,+p.lon,!!p.access_verified,+p.access_lat,+p.access_lon]),
    closures:closures.map(c=>[c.id,c.status,c.applied_revision,c.road_name]),
    pick:closurePickMode,style:roadStyle,operatingRadius:+STATE?.fleet?.operating_radius_m||0,zoom:Math.round((roadsMap.getZoom?.()||0)*2)/2,
  });
  if(signature===ROAD_RENDER_KEY)return;
  ROAD_RENDER_KEY=signature;renderOperatingArea(roadOperatingLayer,places.find(p=>p.role==='depot'));roadLayer.clearLayers();roadPlaceLayer.clearLayers();closureLayer.clearLayers();
  const legend=$('#roadMapLegend');if(legend)legend.innerHTML=roadLegendHtml();
  const density=$('#roadMapDensity');if(density){const dense=!!roadGeojson?.truncated;density.classList.toggle('hidden',!dense);density.innerHTML=dense?`<i></i><span>Viewport simplified for browser performance · zoom in for more local roads</span>`:'';}
  if(roadGeojson){
    L.geoJSON(roadGeojson,{pane:'road-network',interactive:closurePickMode,style:f=>{const weight=roadWeight(f);return{color:roadColor(f),weight:closurePickMode?Math.max(5.5,weight+2.3):weight,opacity:closurePickMode ? .88 : (roadStyle==='class' ? .78 : .84),lineCap:'round',lineJoin:'round'};},onEachFeature:(f,l)=>{
      const p=f.properties||{},name=p.name||(LANG==='th'?'':'Unnamed road'),direction=p.oneway?'one-way':'two-way',speed=Math.round(+p.speed_kph||35);
      l.bindTooltip(`<div class="road-tooltip"><b>${esc(name)}</b><span>${esc(p.highway||'road')} · ${speed} km/h · ${direction}</span></div>`,{sticky:true,direction:'top',className:'fleet-map-tooltip'});
      const base=()=>({color:roadColor(f),weight:closurePickMode?Math.max(5.5,roadWeight(f)+2.3):roadWeight(f),opacity:closurePickMode ? .88 : (roadStyle==='class' ? .78 : .84)});
      l.on('mouseover',()=>{l.setStyle({...base(),weight:Math.max(base().weight+1.6,4.2),opacity:1});l.bringToFront();});
      l.on('mouseout',()=>l.setStyle(base()));
      if(!closurePickMode)return;
      l.on('click',ev=>{
        L.DomEvent.stopPropagation(ev);
        const latlngs=(f.geometry?.coordinates||[]).map(point=>[+point[1],+point[0]]);
        openClosureEdge({...p,road_name:name,direction_text:p.oneway?'one-way':'two-way road record',geometry:latlngs,snap_lat:ev.latlng.lat,snap_lon:ev.latlng.lng,snap_distance_m:0});
      });
    }}).addTo(roadLayer);
  }
  let customerIndex=0;
  places.forEach(p=>{
    const index=p.role==='customer'?customerIndex++:0;
    L.marker([+p.lat,+p.lon],{icon:placeMarkerIcon(p,index),keyboard:true,riseOnHover:true,pane:'fleet-stops'})
      .bindTooltip(`<div class="place-map-tooltip"><b>${esc(p.name)}</b><span>${p.role==='depot'?'Depot':'Work point'} · ${p.access_verified?'road access verified':'access pending'}</span></div>`,{direction:'top',offset:[0,-10],className:'fleet-map-tooltip'})
      .bindPopup(`<div class="fleet-popup"><span>${p.role==='depot'?'DEPOT':'WORK POINT'}</span><b>${esc(p.name)}</b><small>${esc(p.access_road||(LANG==='th'?'':'Access pending'))}</small></div>`)
      .addTo(roadPlaceLayer);
    if(p.access_verified&&p.access_lat!=null&&p.access_lon!=null){
      L.polyline([[+p.lat,+p.lon],[+p.access_lat,+p.access_lon]],{pane:'access',color:'#fff',weight:4,opacity:.88,interactive:false}).addTo(roadPlaceLayer);
      L.polyline([[+p.lat,+p.lon],[+p.access_lat,+p.access_lon]],{pane:'access',color:'#c68a20',weight:1.8,dashArray:'4 5',opacity:.9,interactive:false}).addTo(roadPlaceLayer);
      L.marker([+p.access_lat,+p.access_lon],{icon:accessMarkerIcon(true),interactive:false,pane:'fleet-stops'}).addTo(roadPlaceLayer);
    }
  });
  closures.forEach(c=>{
    if(!c.geometry?.length)return;
    const color=c.status==='approved'?'#c9443a':c.status==='pending'?'#c68a20':'#8795a3',geometry=c.geometry.map(p=>[+p[0],+p[1]]),approved=c.status==='approved';
    L.polyline(geometry,{pane:'closure',color:'#fff',weight:approved?11:9,opacity:.88,lineCap:'round',interactive:false}).addTo(closureLayer);
    const line=L.polyline(geometry,{pane:'closure',color,weight:approved?7:5.5,opacity:.96,lineCap:'round',dashArray:c.status==='pending'?'9 6':null})
      .bindPopup(`<div class="fleet-popup danger-popup"><span>${esc(localizeClosureStatus(c.status))}</span><b>${esc(c.road_name||'Road segment')}</b><small>${esc(c.note||'')}</small></div>`)
      .addTo(closureLayer);
    line.on('mouseover',()=>line.setStyle({weight:approved?8.5:7,opacity:1}));line.on('mouseout',()=>line.setStyle({weight:approved?7:5.5,opacity:.96}));
  });
}

async function previewClosureEdge(latlng){
  closurePickMode=false;roadsMap.getContainer().style.cursor='wait';
  try{const edge=await api('/api/road-edge/preview',{method:'POST',body:JSON.stringify({lat:latlng.lat,lon:latlng.lng})});openClosureEdge(edge);}
  catch(e){roadsMap.getContainer().style.cursor='';toast(LANG==='th'?'':'Could not select road',e.message,true);}
}

async function startOptimize(rebuild=null){
  const running=blockingJob();if(running){toast(LANG==='th'?'':'An operational job is already running',running.message,true);return;}
  const pf=STATE.preflight||{},missing=(pf.checks||[]).filter(x=>!x.ok);
  const hardMissing=missing.filter(x=>['source','depot','customers'].includes(x.id));
  const repairMissing=missing.filter(x=>['network','access'].includes(x.id));
  if(hardMissing.length){const first=hardMissing[0];toast(LANG==='th'?' Solver ':'Solver cannot start yet',hardMissing.map(x=>x.label).join(' · '),true);if(first.id==='source'){REGION_FORCE_OPEN=true;activate('command');renderRegionSetup();}else if(first.id==='customers'){focusWorkPointEntry();showResult({type:'warn',title:'Add at least one work point',message:'A depot by itself cannot create a delivery route. Search a destination, add one from the map, generate a scenario, or import CSV, then optimize again.',primary:'Go to work-point tools',onPrimary:focusWorkPointEntry});}else activate('plan');return;}
  try{
    await saveSettings(false);
    const autoRepair=repairMissing.length>0;
    if(autoRepair&&!await confirmDistanceRisk('prepare roads and optimize this plan'))return;
    const res=await api('/api/solve',{method:'POST',body:JSON.stringify({rebuild_network:rebuild===true||autoRepair,reason:autoRepair?'Verified optimization · automatic graph repair':'Verified route optimization'})});
    selectedJobId=res.job_id;resetJobLogs(res.job_id);
    toast(LANG==='th'?'':'Optimization queued',autoRepair?`Job #${res.job_id} · ${LANG==='th'?'/':'road graph will auto-repair'}`:`Job #${res.job_id}`);
    await refresh(true,false);activate('optimize');subscribeToActiveJob();
  }catch(e){toast(LANG==='th'?' Solver ':'Could not start solver',e.message,true);}
}

function localizeStatus(status){const th={queued:'',running:'',succeeded:'',failed:'',cancelled:''};return LANG==='th'?(th[status]||status):status;}
function localizeStage(label){if(LANG!=='th')return label||'—';const map={'Reachable demo customers':'','Scenario contract':'','Fixed operating area':'','Verified customers':'','Operating graph ready':'','Preparing local operating graph':'','Destination road access':'','Road graph':'Directed road graph','Customers':'','Work points':'','Depot':'','Initial plan':'','routing engine':'routing engine','Clustering':'Clustering','Solver':'Optimizer','Improve':'','Validate & apply':'','Dispatch':' Driver App','Evidence':''};return map[label]||String(label||'—').replace('complete','').replace('waiting','').replace('running','').replace('stopped','');}

function friendlyError(message){const m=String(message||'');if(/road-cost preparation exceeded the .*preparation limit/i.test(m))return LANG==='th'?'':'Directed road-cost preparation exceeded its separate hang limit. The configured optimization budget had not started yet; inspect stderr for BackendPrep progress.';if(/did not exit within the configured limit \(.*search budget.*shutdown grace\)/i.test(m))return LANG==='th'?'':'The C++ optimizer reached the governed search limit but did not exit within its shutdown grace. The current fleet plan was preserved; inspect the process timing and final stderr lines.';if(m.includes('values for')&&m.includes('columns'))return LANG==='th'?' — ':'Internal demo schema mismatch — generate again';if(m.includes('hard-feasible')||m.includes('hard constraint'))return LANG==='th'?'Solver   Time windows,  ':'No route satisfied every hard constraint. Check time windows, service workload, and stops per truck.';if(/outside (?:the )?active .*road source|outside this extract|outside the active regional road source/i.test(m))return 'The current road-data region does not cover one or more plan locations. Choose the matching region in Road-source setup before preparing roads.';if(/no usable driving edges|no strongly connected driving component|no usable round-trip drivable component/i.test(m))return 'No usable round-trip driving network was found around the selected operating area. Move the depot closer to mapped drivable roads, increase the operating area if appropriate, or verify that the selected road-data region is correct.';if(/nearest round-trip drivable road is/i.test(m))return m+' Move the location closer to a mapped drivable road or increase the road-access limit only when that last-meter distance is operationally acceptable.';if(/choose a depot first/i.test(m))return 'Choose a depot before adding or validating work points.';if(/invalid latitude\/longitude/i.test(m))return "Invalid coordinates. Use decimal degrees in 'lat, lon' order, for example 13.7563, 100.5018.";return m;}
function runtimeArtifact(key){return (DEV_RUNTIME?.files||[]).find(f=>f.key===key)||null;}
function jobSolverRelation(job){
  const r=job?.result||{};
  const solverJob=Number(r.optimizer_job_id||r.next_job_id||0);
  const invocationJob=Number(DEV_RUNTIME?.last_invocation?.job_id||0);
  if(['solve','network-and-solve'].includes(job?.kind))return {hasProcess:true,jobId:Number(job.id),note:''};
  if(solverJob)return {hasProcess:false,jobId:solverJob,note:LANG==='th'?`  Optimizer  Job #${solverJob}`:`The initial plan is ready; the optimizer runs in Job #${solverJob}.`};
  if(job?.kind==='scenario-route')return {hasProcess:false,jobId:0,note:LANG==='th'?'  Job  Optimizer  stdout/stderr ':'Preparing the initial plan. The linked optimizer job and its stdout/stderr will appear automatically.'};
  if(job?.kind==='scenario-generate')return {hasProcess:false,jobId:0,note:LANG==='th'?' “”  Optimizer':'“Create work points only” was selected, so no optimizer process is expected.'};
  return {hasProcess:invocationJob===Number(job?.id),jobId:invocationJob,note:''};
}
function renderJobArtifacts(job){
  const relation=jobSolverRelation(job);
  const keys=['input','dataset','dataset_summary','solver_invocation','solver_stdout','solver_stderr','convergence','run_summary'];
  const executionKeys=new Set(['solver_invocation','solver_stdout','solver_stderr','convergence','run_summary']);
  const invocationJob=Number(DEV_RUNTIME?.last_invocation?.job_id||0);
  const selectedJob=Number(job?.id||0);
  const expectedSolverJob=Number(relation.jobId||0);
  const rows=keys.map(key=>{
    const f=runtimeArtifact(key);if(!f)return'';
    const state=f.exists?'exists':'missing';
    let ownership='';
    if(executionKeys.has(key)&&f.exists&&invocationJob){
      if(invocationJob===selectedJob)ownership=LANG==='th'?` Job #${invocationJob}`:`Produced by Job #${invocationJob}`;
      else if(expectedSolverJob&&invocationJob===expectedSolverJob)ownership=LANG==='th'?` Solver Job #${invocationJob} `:`Produced by handed-off Solver Job #${invocationJob}`;
      else ownership=LANG==='th'?` Runtime  Job #${invocationJob} —  Job #${selectedJob}`:`Latest runtime snapshot from Job #${invocationJob} — not evidence produced by Job #${selectedJob}`;
    }else if(!executionKeys.has(key)&&f.exists){
      ownership=LANG==='th'?'Snapshot  solver input/data':'Current solver input/data snapshot';
    }
    const detail=[f.description||'',ownership].filter(Boolean).join(' · ');
    return `<button class="job-artifact-row ${state}" data-job-artifact="${esc(key)}"><span><b>${esc(f.label)}</b><small>${esc(detail)}</small></span><em>${f.exists?humanBytes(f.bytes):'missing'}</em><code>${f.sha256?shortHash(f.sha256):''}</code></button>`;
  }).join('');
  const solverNote=relation.note||((relation.hasProcess&&relation.jobId)?(LANG==='th'?`Process streams  Job #${relation.jobId}  STDOUT  STDERR/CERR`:`Job #${relation.jobId} process streams are captured separately as STDOUT and STDERR/CERR.`):'');
  const snapshotNote=LANG==='th'?'Process Console  Job   Runtime  snapshot  Job ':'The Process Console is the preserved history for the selected job; runtime files are latest mutable snapshots and show their owning job explicitly.';
  return `<section class="job-evidence-files"><div class="job-evidence-head"><div><b>${LANG==='th'?' Runtime':'Runtime evidence files'}</b><small>${esc([solverNote,snapshotNote].filter(Boolean).join(' · '))}</small></div><button type="button" class="text-button" id="activityRuntimeRefreshBtn">${LANG==='th'?'':'Refresh files'}</button></div><div class="job-artifact-grid">${rows||`<div class="empty-state">${tr('noData')}</div>`}</div></section>`;
}
function renderActivity(){
  const openBtn=$('#openConsoleBtn');if(openBtn)openBtn.textContent=CONSOLE_OPEN?(LANG==='th'?'Console ':'Console open'):(LANG==='th'?' Process Console':'Open process console');
  const jobs=STATE.jobs||[];if(!selectedJobId&&jobs.length)selectedJobId=jobs[0].id;
  $('#jobsList').innerHTML=jobs.length?jobs.map(j=>{const pct=jobProgress(j),ind=jobIndeterminate(j);return`<div class="job-card ${+j.id===+selectedJobId?'selected':''}" data-job-card="${j.id}" data-ui-action="select-job" data-job-id="${j.id}" role="button" tabindex="0"><div class="job-card-top"><div><h4>#${j.id} · ${esc(localizeJobKind(jobLabel(j)))}</h4><p data-job-card-stage="${j.id}">${esc(currentStageLabel(j))} · ${rel(j.created_at)}</p></div><span class="status-chip ${j.status}">${localizeStatus(j.status)}</span></div><div class="job-progress ${ind?'indeterminate':''}" data-job-progress-wrap="${j.id}"><i data-job-progress-bar="${j.id}" style="width:${ind?'34':pct}%"></i></div><div class="job-progress-meta"><span>${esc(friendlyError(j.message))}</span><b data-job-progress-label="${j.id}">${progressLabel(j)}</b></div></div>`;}).join(''):`<div class="empty-state">${tr('noData')}</div>`;
  const job=jobs.find(j=>+j.id===+selectedJobId);if(job){renderJob(job);if(!DEV_RUNTIME)loadActivityRuntime(false);}
  $('#versionList').innerHTML=(STATE.route_versions||[]).length?STATE.route_versions.map(v=>`<div class="version-row"><div><b>Route version ${v.id}</b><p>${v.route_count} trucks · ${v.customer_count} visits · job #${v.source_job_id||'—'}</p></div><span class="version-badge">${rel(v.created_at)}</span></div>`).join(''):`<div class="empty-state">${tr('noData')}</div>`;
  $('#eventsList').innerHTML=(STATE.events||[]).length?STATE.events.map(e=>`<div class="audit-row"><div><b>${esc(auditActionLabel(e.action))}</b><p>${esc(auditEventSummary(e))}</p></div><span class="version-badge">${rel(e.ts)}</span></div>`).join(''):`<div class="empty-state">${tr('noData')}</div>`;
}
function auditActionLabel(action){const th={'place.added':'','place.updated':'','place.removed':'','plan.cleared':'','network.offline.started':'','network.offline.completed':'','instance.materialized':' input.txt','closure.reported':'','closure.decision':'','closure.reopened':'','route.published':'','settings.updated':'','rush.csv.imported':' CSV ','plan.csv.imported':' CSV','rush.workflow.queued':' Rush mode  Optimizer','demo.generated':'','demo.workflow.queued':' Optimizer','clustering.single.ready':'Clustering '};const en={'place.added':'Place added','place.updated':'Place updated','place.removed':'Place removed','plan.cleared':'Plan cleared','network.offline.started':'Road-graph preparation started','network.offline.completed':'Road graph ready','instance.materialized':'Solver input regenerated','closure.reported':'Road closure reported','closure.decision':'Road report decided','closure.reopened':'Road edge restored','route.published':'Fleet-plan version updated','settings.updated':'Settings saved','rush.csv.imported':'Rush CSV imported','plan.csv.imported':'Plan CSV imported','rush.workflow.queued':'Rush workflow handed to optimizer','demo.generated':'Verified demo generated','demo.workflow.queued':'Demo handed to optimizer','clustering.single.ready':'Clustering validated'};return (LANG==='th'?th:en)[action]||String(action||'event').replaceAll('.',' · ');}
function auditEventSummary(e){const d=e.details||{},parts=[];if(d.name)parts.push(d.name);if(d.role)parts.push(LANG==='th'?` ${d.role}`:`role ${d.role}`);if(d.road_name)parts.push(d.road_name);if(d.status)parts.push(LANG==='th'?` ${d.status}`:`status ${d.status}`);if(d.revision||d.applied_revision)parts.push(`revision ${d.revision||d.applied_revision}`);if(d.job_id)parts.push(`Job #${d.job_id}`);if(d.solve_job_id)parts.push(`Optimizer #${d.solve_job_id}`);if(d.route_version)parts.push(`Route v${d.route_version}`);if(d.nodes!=null)parts.push(`${d.nodes} nodes`);if(d.edges!=null)parts.push(`${d.edges} edges`);if(d.customer_count!=null)parts.push(`${d.customer_count} ${LANG==='th'?'':'work points'}`);if(d.removed_edge_count!=null)parts.push(`${d.removed_edge_count} ${LANG==='th'?'edge ':'edges removed'}`);return `${e.actor||'system'} · ${parts.join(' · ')|| (LANG==='th'?'':'Event recorded')}`;}

window.selectJob=async id=>{selectedJobId=id;renderActivity();await Promise.all([loadJobLog(id,true),loadActivityRuntime(false)]);};
async function loadJobLog(id,silent=false){try{await fetchJobLogChunk(id,true,'audit');if(JOB_LOG_SOURCE!=='audit')await fetchJobLogChunk(id,true,JOB_LOG_SOURCE);const j=(STATE.jobs||[]).find(x=>+x.id===+id);if(j)renderJob(j);if(!silent)toast('Log loaded',`Job #${id}`);}catch(e){toast('Log failed',e.message,true);}}
function solverTimingPanel(j){
  if(!j||!['solve','network-and-solve'].includes(j.kind))return '';
  const result=j.result||{},timing=result.process_timing||{},validation=result.candidate_validation||{};
  const finite=v=>Number.isFinite(Number(v))&&Number(v)>=0,fmt=v=>finite(v)?humanDuration(Number(v)):null;
  const process=finite(result.solver_process_runtime_s)?Number(result.solver_process_runtime_s):finite(timing.process_elapsed_s)?Number(timing.process_elapsed_s):null;
  const prep=finite(result.solver_preparation_runtime_s)?Number(result.solver_preparation_runtime_s):finite(timing.preparation_elapsed_s)?Number(timing.preparation_elapsed_s):null;
  const search=finite(result.solver_search_runtime_s)?Number(result.solver_search_runtime_s):finite(timing.governed_elapsed_s)?Number(timing.governed_elapsed_s):null;
  const cert=finite(result.solver_validation_runtime_s)?Number(result.solver_validation_runtime_s):finite(validation.validation_runtime_s)?Number(validation.validation_runtime_s):null;
  if(process==null&&prep==null&&search==null&&cert==null)return '';
  const items=[
    ['Road-cost prep',prep],['Governed search',search],['Independent validation',cert],['Native process',process]
  ].map(([label,value])=>`<span><small>${label}</small><b>${value==null?'—':fmt(value)}</b></span>`).join('');
  let note='';
  if(String(timing.status||'')==='timeout'){
    const phase=String(timing.phase||'process'),where=phase==='native_preparation'?'road-cost preparation':phase==='governed_search'?'governed search / shutdown':'native process';
    const limit=finite(timing.timeout_s)?` after ${fmt(timing.timeout_s)}`:'';
    note=`<p><b>Watchdog receipt:</b> stopped during ${esc(where)}${limit}. Preparation and search use separate clocks.</p>`;
  }else if(cert!=null){
    note=`<p>Final validation reuses the objective-specific road-path context; it is measured separately from C++ search.</p>`;
  }
  return `<div class="solver-timing-panel"><div>${items}</div>${note}</div>`;
}
function renderJob(j){
  const pct=jobProgress(j),duration=jobElapsed(j),stages=stagesForJob(j),index=stageOf(j),result=j.result||{},network=result.network||{};
  const terminal=['succeeded','failed','cancelled'].includes(j.status);
  const heartbeatAge=j.heartbeat_at?Math.max(0,(Date.now()-new Date(j.heartbeat_at).getTime())/1000):null;
  const streamHealthy=!terminal&&(heartbeatAge==null||heartbeatAge<8);
  const raw=logText(j.id,'raw');
  const tail=tailLog(raw,10);
  $('#selectedJobTitle').textContent=`${LANG==='th'?'':'Job'} #${j.id} · ${localizeJobKind(jobLabel(j))}`;
  $('#selectedJobMeta').textContent=`${localizeStatus(j.status)} · ${duration==null?'not started':num(duration,1)+' s'} · ${progressLabel(j)} · ${j.message}`;
  const metrics=`<div class="log-hero"><div class="log-stat"><span>${jobIndeterminate(j)?(LANG==='th'?'':'Status'):'Progress'}</span><b id="jobProgressMetric">${progressLabel(j)}</b></div><div class="log-stat"><span>${LANG==='th'?'':'Last stage'}</span><b id="jobLastStageMetric">${esc(localizeStage(currentStageLabel(j)))}</b></div><div class="log-stat"><span>${LANG==='th'?'':'Road nodes'}</span><b>${num(network.nodes)}</b></div><div class="log-stat"><span>${LANG==='th'?'':'Job elapsed'}</span><b id="jobElapsedMetric">${num(duration,1)+'s'}</b></div></div>`;
  const timingByStage=new Map((result.performance?.stage_timings||[]).map(t=>[Number(t.index),Number(t.elapsed_s)||0]));
  const timeline=`<div class="log-timeline">${stages.map((x,i)=>{const n=i+1;let state='waiting';if(j.status==='succeeded')state='done';else if(n<index)state='done';else if(n===index&&j.status==='running')state='running';else if(n===index&&['failed','cancelled'].includes(j.status))state='failed';else if(terminal&&n>index)state='skipped';const label=LANG==='th'?({done:'',running:'',failed:'',skipped:'',waiting:''})[state]:({done:'complete',running:'running',failed:'stopped',skipped:'not run',waiting:'waiting'})[state];const stored=timingByStage.get(n);const shown=stored!=null?humanDuration(stored):(n===index&&j.status==='running'?humanDuration(stageElapsed(j)):'');return`<div class="log-event ${state}"><i>${state==='done'?'✓':state==='failed'?'!':state==='running'?'▶':state==='skipped'?'–':n}</i><div><h5>${esc(localizeStage(x[0]))} · ${label}</h5><p>${esc(x[1])}<span data-job-stage-time="${n}">${shown?` · ${shown}`:''}</span></p></div></div>`;}).join('')}</div>`;
  const health=terminal
    ? `<div id="jobStreamHealth" class="stream-health finished"><i></i><div><b id="jobHeartbeatTitle">${LANG==='th'?' · Backend ':'This job is finished · backend remains online'}</b><small id="jobHeartbeatDetail">${LANG==='th'?' heartbeat ':'No further heartbeat is expected for a terminal job.'}</small></div></div>`
    : `<div id="jobStreamHealth" class="stream-health ${streamHealthy?'healthy':'delayed'}"><i></i><div><b id="jobHeartbeatTitle">${streamHealthy?(LANG==='th'?'Backend ':'Backend heartbeat is live'):(LANG==='th'?' heartbeat ':'Backend heartbeat is delayed')}</b><small id="jobHeartbeatDetail">${heartbeatAge==null?'No heartbeat timestamp':`${LANG==='th'?'':'Last update'} ${num(heartbeatAge,1)} s · ${LANG==='th'?'':'elapsed'} ${num(duration,1)} s · raw ${num(result.live?.raw_log_offset||0)} B`}</small></div></div>`;
  const emptyRaw=terminal
    ? (LANG==='th'?' child process  Raw Console —  Audit Trace ':'No child process started for this job. Open Audit Trace to see the failed prerequisite.')
    : (LANG==='th'?'Raw output  child process ':'Raw output will appear when the child process writes it.');
  const liveTail=`<div class="live-log-tail"><div><b>${LANG==='th'?' Raw Console':'Raw-console tail'}</b><span id="jobRawTailMeta">${raw?num(raw.length)+' chars':terminal?(LANG==='th'?' process output':'no process output'):'waiting for process output'}</span></div><pre id="jobRawTailText">${logMarkup(tail||emptyRaw)}</pre></div>`;
  const action=['failed','cancelled'].includes(j.status)?`<div class="actionable-error"><b>${result.cancelled?(LANG==='th'?'':'Cancelled'):(LANG==='th'?'':'Job stopped with the actual error')}</b><p>${esc(friendlyError(j.message))}</p></div>`:'';
  const cancel=['queued','running'].includes(j.status)?`<button class="cancel-live-job" data-ui-action="cancel-job" data-job-id="${j.id}">${LANG==='th'?'':'Cancel job'}</button>`:'';
  $('#visualLog').innerHTML=`${metrics}<div class="live-stage-banner ${jobIndeterminate(j)?'indeterminate':''}"><span id="jobStageLabel">${esc(currentStageLabel(j))}</span><b id="jobStageProgress">${progressLabel(j)}</b>${cancel}</div>${solverTimingPanel(j)}${health}${timeline}${liveTail}${renderJobArtifacts(j)}${action}`;
  $('#activityRuntimeRefreshBtn')?.addEventListener('click',()=>loadActivityRuntime(true));
  $$('[data-job-artifact]').forEach(btn=>btn.addEventListener('click',()=>{activate('developer');selectDeveloperFile(btn.dataset.jobArtifact,true);}));
  renderOpenConsole();bindDynamicNavigation();
}

function tickLiveJobUI(job=null){
  if(!STATE)return;
  const j=job||((STATE.jobs||[]).find(x=>+x.id===+selectedJobId));
  if(!j)return;
  const duration=jobElapsed(j),label=progressLabel(j),stage=currentStageLabel(j);
  if(+selectedJobId===+j.id){
    const meta=$('#selectedJobMeta');if(meta)meta.textContent=`${localizeStatus(j.status)} · ${num(duration,1)} s · ${label} · ${j.message}`;
    const elapsed=$('#jobElapsedMetric');if(elapsed)elapsed.textContent=`${num(duration,1)}s`;
    const progress=$('#jobProgressMetric');if(progress)progress.textContent=label;
    const stageProgress=$('#jobStageProgress');if(stageProgress)stageProgress.textContent=label;
    const stageLabel=$('#jobStageLabel');if(stageLabel)stageLabel.textContent=stage;
    const lastStage=$('#jobLastStageMetric');if(lastStage)lastStage.textContent=localizeStage(stage);
    const stageTime=document.querySelector(`[data-job-stage-time="${stageOf(j)}"]`);if(stageTime&&j.status==='running')stageTime.textContent=` · ${humanDuration(stageElapsed(j))}`;
    const health=$('#jobStreamHealth'),detail=$('#jobHeartbeatDetail'),title=$('#jobHeartbeatTitle');
    const terminal=['succeeded','failed','cancelled'].includes(j.status);
    const age=j.heartbeat_at?Math.max(0,(Date.now()-new Date(j.heartbeat_at).getTime())/1000):null;
    if(health&&!terminal){const healthy=age==null||age<8;health.classList.toggle('healthy',healthy);health.classList.toggle('delayed',!healthy);}
    if(title&&!terminal)title.textContent=(age==null||age<8)?(LANG==='th'?'Backend ':'Backend heartbeat is live'):(LANG==='th'?' heartbeat ':'Backend heartbeat is delayed');
    if(detail&&!terminal)detail.textContent=age==null?'No heartbeat timestamp':`${LANG==='th'?'':'Last update'} ${num(age,1)} s · ${LANG==='th'?'':'elapsed'} ${num(duration,1)} s · raw ${num(j.result?.live?.raw_log_offset||0)} B`;
  }
  const cardStage=document.querySelector(`[data-job-card-stage="${j.id}"]`);if(cardStage)cardStage.textContent=`${stage} · ${rel(j.created_at)}`;
  const cardLabel=document.querySelector(`[data-job-progress-label="${j.id}"]`);if(cardLabel)cardLabel.textContent=label;
  const wrap=document.querySelector(`[data-job-progress-wrap="${j.id}"]`),bar=document.querySelector(`[data-job-progress-bar="${j.id}"]`);
  const ind=jobIndeterminate(j);if(wrap)wrap.classList.toggle('indeterminate',ind);if(bar)bar.style.width=`${ind?34:jobProgress(j)}%`;
}

window.cancelJob=async id=>{if(!confirm(LANG==='th'?'?':'Cancel this job?'))return;try{await api(`/api/jobs/${id}/cancel`,{method:'POST',body:'{}'});toast(LANG==='th'?'':'Cancellation requested',`Job #${id}`);}catch(e){toast('Cancel failed',e.message,true);}};

let ACTIVE_POLL_BUSY=false;
async function pollActiveJobFallback(){
  if(ACTIVE_POLL_BUSY)return;
  const job=activeJob();
  const pending=JOB_TERMINAL_PENDING.values().next().value;
  if(!job&&!pending)return;
  if(!pending&&!jobPollingRequired()&&JOB_STREAM&&+JOB_STREAM_ID===+job.id&&JOB_STREAM.readyState===EventSource.OPEN&&Date.now()-JOB_STREAM_LAST_UPDATE<8000)return;
  ACTIVE_POLL_BUSY=true;
  try{
    // Retain terminal work across a failed refresh even after activeJob() clears.
    if(pending)await handleJobSnapshot(pending);
    if(job)await handleJobSnapshot(await api(`/api/jobs/${job.id}`,{timeoutMs:10000}));
  }catch(error){setConnectionState(false,error.message);}
  finally{ACTIVE_POLL_BUSY=false;}
}


// =============================================================================
// v1.5 MAP-ACCURATE FAST OVERRIDES
// =============================================================================

function renderTop(){
  const routes=latestRoutes(),job=activeJob(),places=STATE.places||[],pf=STATE.preflight||{},ctx=STATE.operational_context||{},routeStatus=routeOperationalState(),wf=STATE.workflow||{};
  const connectionLabel=$('#systemConnectionText'),pulse=$('.project-card .pulse');if(connectionLabel)connectionLabel.textContent=LANG==='th'?'':'System connected';if(pulse){pulse.classList.remove('connecting','offline');}
  $('#navPlanBadge').textContent=places.filter(p=>p.role==='customer').length;
  $('#navRouteBadge').textContent=routes.length;
  $('#navRoadBadge').textContent=ctx.graph?.ready?'✓':STATE.osm_source?.ready?'•':'!';
  $('#projectStatus').textContent=job?(LANG==='th'?` · ${localizeJobKind(job.kind)}`:`Running · ${localizeJobKind(job.kind)}`):routeStatus.title;
  $('#projectMeta').textContent=ctx.graph?.ready?`${ctx.graph.id||'graph'} · ${num(ctx.graph.nodes)} nodes · ${ctx.depot?.name||'no depot'} · ${LANG==='th'?(wf.graph_reusable?'':''):(wf.graph_reusable?'reusable':'ready')}`:(STATE.osm_source?.ready?(LANG==='th'?' · ':'Road data ready · graph prepares when needed'):(LANG==='th'?'':'regional road data is not installed'));
  const top=$('#topJobIndicator');top.className=`live-job compact ${job?.status||routeStatus.phase}`;top.setAttribute('aria-busy',String(!!job&&['queued','running'].includes(job.status)));$('span',top).textContent=job?(job.stage_label||friendlyError(job.message)):(routeStatus.completed?(LANG==='th'?'':'Fleet plan ready'):routeStatus.phase==='prepared'?(LANG==='th'?'':'Initial plan ready'):(pf.ready?(LANG==='th'?' Optimizer':'Ready for optimizer'):tr('idle')));
  const globalButton=$('#globalOptimizeBtn');if(globalButton){globalButton.disabled=!!job;globalButton.title=job?(LANG==='th'?'':'A workflow is already running'):'';}
  $('#driverQuickLink').href=withToken(routes.length?`/driver/${routes[0].truck_id}`:'/driver/0');
  const setContract=(id,text,good=false,bad=false)=>{const el=$(id);if(!el)return;el.textContent=text;el.classList.toggle('contract-ready',good);el.classList.toggle('contract-stale',bad);};
  const setStepState=(id,state)=>{const step=$(id)?.closest('.contract-step');if(!step)return;step.classList.remove('complete','active','waiting','stale');step.classList.add(state);};
  const planComplete=!!ctx.depot&&ctx.plan?.customer_count>0&&ctx.plan?.verified_count===ctx.plan?.customer_count,graphComplete=!!ctx.graph?.ready;
  setContract('#contractGraph',graphComplete?`${ctx.graph.id||'active'} · ${num(ctx.graph.nodes)} nodes`:(LANG==='th'?'':'Not prepared'),graphComplete,!graphComplete);
  setContract('#contractDepot',ctx.depot?.name||(LANG==='th'?'':'Depot not selected'),!!ctx.depot,!ctx.depot);
  setContract('#contractOrders',`${num(ctx.plan?.verified_count||0)}/${num(ctx.plan?.customer_count||0)} ${LANG==='th'?'':'work points ready'}`,planComplete,ctx.plan?.customer_count>ctx.plan?.verified_count);
  setContract('#contractClosures',`${num(ctx.closures?.active||0)} ${LANG==='th'?' · ': 'active · '}${num(ctx.closures?.pending||0)} ${LANG==='th'?'':'pending'}`,ctx.closures?.pending===0,ctx.closures?.pending>0);
  setContract('#contractCluster',`Clustering: ${PENDING_CLUSTER_METHOD||ctx.solver?.clustering||'auto'}`,true,false);
  const routeText=routeStatus.phase==='running'?(routeStatus.hasRoute?(LANG==='th'?'':'Optimizing routes'):(LANG==='th'?'':'Preparing plan')):routeStatus.phase==='prepared'?(LANG==='th'?'':'Initial plan ready'):routeStatus.completed?(LANG==='th'?'':'Fleet plan ready'):routeStatus.phase==='stale'?(LANG==='th'?'':'Update required'):(LANG==='th'?'':'No fleet plan');
  setContract('#contractRoutes',routeText,routeStatus.completed,routeStatus.phase==='stale');
  const dispatchText=routeStatus.completed?(LANG==='th'?'Driver App ':'Driver App ready'):routeStatus.phase==='prepared'||(routeStatus.phase==='running'&&routeStatus.hasRoute)?(LANG==='th'?'':'Initial plan available for review'):routeStatus.phase==='stale'?(LANG==='th'?'':'Waiting for an updated plan'):(LANG==='th'?'':'Awaiting fleet plan');
  setContract('#contractDispatch',dispatchText,routeStatus.completed,routeStatus.phase==='stale');
  const phaseText=routeStatus.completed?(LANG==='th'?'':'Fleet plan ready'):routeStatus.phase==='running'?(LANG==='th'?'Optimizer ':'Optimizer running'):routeStatus.phase==='prepared'?(LANG==='th'?'':'Initial plan ready for review'):routeStatus.phase==='stale'?(LANG==='th'?' · ':'Inputs changed · update required'):(graphComplete?(LANG==='th'?'':'Road graph ready'):(LANG==='th'?'':'Prepare the plan'));
  $('#contractPhase').textContent=phaseText;
  setStepState('#contractDepot',planComplete?'complete':'active');
  setStepState('#contractGraph',graphComplete?'complete':planComplete?'active':'waiting');
  setStepState('#contractRoutes',routeStatus.completed?'complete':['prepared','running'].includes(routeStatus.phase)?'active':routeStatus.phase==='stale'?'stale':graphComplete?'active':'waiting');
  setStepState('#contractDispatch',routeStatus.completed?'complete':routeStatus.phase==='stale'?'stale':'waiting');
}


async function searchPlaces(){
  const q=$('#searchQuery').value.trim();if(q.length<3){toast(LANG==='th'?'':'Place search',LANG==='th'?' 3 ':"Enter at least 3 characters, or decimal coordinates as 'lat, lon'.",true);return;}
  $('#searchLoading').classList.remove('hidden');$('#searchResults').innerHTML='';
  try{
    const r=await api(`/api/geocode?q=${encodeURIComponent(q)}&limit=7`,{timeoutMs:18000});searchResults=r.results||[];
    $('#searchResults').innerHTML=searchResults.length?searchResults.map((x,i)=>`<article class="search-result search-result-v2"><button class="search-result-main" data-ui-action="show-search-result" data-search-index="${i}"><div class="search-result-pin">${i+1}</div><div><b>${esc(x.name)}</b><p>${esc(x.display_name)}</p><span>${esc(x.type||x.category||'place')}</span></div><i>⌖</i></button><div class="search-result-actions"><button class="primary-result" data-ui-action="use-search-depot" data-search-index="${i}">${LANG==='th'?' Depot ':'Use as depot & continue'}</button><button data-ui-action="show-search-result" data-search-index="${i}">${LANG==='th'?'':'Map'}</button><button data-ui-action="prepare-search-customer" data-search-index="${i}">${LANG==='th'?'+ ':'+ Work point'}</button></div></article>`).join(''):`<div class="empty-state">${LANG==='th'?' ':'No results. Add a city or country to the query.'}</div>`;
  }catch(e){toast(LANG==='th'?'':'Search failed',e.message,true);}finally{$('#searchLoading').classList.add('hidden');}
}
function clearSearchUI(){searchResults=[];$('#searchQuery').value='';$('#searchResults').innerHTML='';$('#clearSearchBtn').classList.add('hidden');clearAccessInspector();$('#searchQuery').focus();}
async function previewMapPlace(latlng){mapAddMode=false;updateMapMode();const role=mapPickRole||'customer';await selectCandidate({name:role==='depot'?(LANG==='th'?'Depot ':'Map depot'):(LANG==='th'?'':'Map work point'),address:`${latlng.lat.toFixed(6)}, ${latlng.lng.toFixed(6)}`,lat:latlng.lat,lon:latlng.lng},role);}
function updateMapMode(){const n=$('#mapModeNotice');n.classList.toggle('hidden',!mapAddMode);planMap.getContainer().style.cursor=mapAddMode?'crosshair':'';if(mapAddMode&&n){n.textContent=mapPickRole==='depot'?(LANG==='th'?' Depot ':'Click the real depot location'):(LANG==='th'?'':'Click the real work-point location');}}

async function startCompleteDemo(){
  if(activeJob()){toast(LANG==='th'?'':'A job is already running',activeJob().message,true);return;}
  if(!STATE.osm_source?.ready){showResult({type:'warn',title:'Operating-region road source required',message:'The complete demo uses real roads. Prepare a regional road source first, then run the demo again.',primary:'Open Roads & incidents',onPrimary:()=>activate('roads')});return;}
  try{const r=await api('/api/workflows/demo',{method:'POST',body:JSON.stringify({count:12,clustering:'none'})});selectedJobId=r.job_id;resetJobLogs(r.job_id);toast(LANG==='th'?'':'Complete demo started',`Job #${r.job_id}`);activate('plan');await refresh(true);subscribeToActiveJob();}catch(e){showResult({type:'error',title:LANG==='th'?'':'Could not start demo',message:e.message});}
}

function parseCsvRows(text){
  const records=parseCsvRecords(text);
  if(records.length<2)throw new Error('CSV has no data rows');
  const headers=records[0].map(value=>value.trim().toLowerCase());
  if(headers.some(value=>!value))throw new Error('CSV has an empty column name');
  if(new Set(headers).size!==headers.length)throw new Error('CSV has duplicate column names');
  for(const required of ['name','lat','lon'])if(!headers.includes(required))throw new Error(`Missing required column: ${required}`);
  return records.slice(1).map((values,index)=>{
    if(values.length!==headers.length)throw new Error(`CSV record ${index+2}: expected ${headers.length} fields, received ${values.length}`);
    return Object.fromEntries(headers.map((header,i)=>[header,values[i].trim()]));
  });
}
function openRushModal(){RUSH_ROWS=[];$('#rushCsvInput').value='';$('#rushCsvMeta').textContent=I18N[LANG].rushCsvHelp;$('#rushValidation').className='rush-validation';$('#rushValidation').textContent='';$('#runRushBtn').disabled=true;revealDialog($('#rushModal'),'#rushCsvInput');}
function closeRushModal(){dismissDialog($('#rushModal'));}
async function inspectRushFile(file){try{const rows=parseCsvRows(await file.text());RUSH_ROWS=rows;const depots=rows.filter(r=>(r.role||'customer').toLowerCase()==='depot').length,customers=rows.length-depots;const hasCurrent=!!(STATE.places||[]).find(p=>p.role==='depot');const valid=depots===1||(depots===0&&hasCurrent&&$('#rushUseDepot').checked);$('#rushCsvMeta').textContent=`${file.name} · ${rows.length} rows · ${customers} work points · ${depots} depot rows`;$('#rushValidation').className=`rush-validation ${valid?'good':'bad'}`;$('#rushValidation').textContent=valid?(LANG==='th'?' —   directed graph  Optimizer':'File ready — FleetRoute will validate work points, prepare the directed graph, and run the optimizer'):(LANG==='th'?'CSV  Depot  Depot ':'CSV has no depot and there is no current depot');$('#runRushBtn').disabled=!valid;}catch(e){RUSH_ROWS=[];$('#rushValidation').className='rush-validation bad';$('#rushValidation').textContent=e.message;$('#runRushBtn').disabled=true;}}
async function runRushWorkflow(){if(!RUSH_ROWS.length)return;try{const payload={rows:RUSH_ROWS,clustering:$('#rushClustering').value,replace:true,use_current_depot:$('#rushUseDepot').checked,fleet:{trucks:+$('#rushTrucks').value||4,capacity:+$('#rushCapacity').value||100},solver:{profile:'auto_dynamic',run_convergence_analysis:false}};const r=await api('/api/workflows/rush',{method:'POST',body:JSON.stringify(payload)});closeRushModal();selectedJobId=r.job_id;resetJobLogs(r.job_id);toast(LANG==='th'?'':'Rush workflow started',`${RUSH_ROWS.length} CSV rows · Job #${r.job_id}`);activate('activity');await refresh(true);subscribeToActiveJob();}catch(e){showResult({type:'error',title:LANG==='th'?'':'Rush workflow stopped',message:e.message});}}

function renderClustering(){
  const selected=PENDING_CLUSTER_METHOD||STATE.solver?.clustering||'auto',latest=STATE.latest_clustering,bench=STATE.clustering_benchmark||{};
  const latestCurrent=!!latest&&!latest.stale&&latest.current!==false,native=latestCurrent?latest?.native_warm_start:null,benchCurrent=!!bench.available&&!bench.stale&&bench.current!==false;$('#clustering').value=selected;
  $('#clusterMethodCards').innerHTML=CLUSTER_METHODS.map(m=>`<button type="button" class="method-card ${selected===m.id?'selected':''}" aria-pressed="${selected===m.id}" data-cluster-method="${m.id}"><i>${m.icon}</i><span><b>${m.title}</b><small>${esc(LANG==='th'?m.th:m.en)}</small></span><em>${m.badge}</em></button>`).join('');
  const val=latestCurrent?latest?.validation:null,latestReceipt=latest?.source_receipt||{},benchReceipt=bench?.source_receipt||{};
  const nativeLabel=native?.accepted===true?(LANG==='th'?'':'ACCEPTED'):native?.accepted===false?(LANG==='th'?'fallback ':'SAFE FALLBACK'):(val?.valid?(LANG==='th'?' Solver':'PENDING SOLVER'):'—');
  const nativeDetail=native?.accepted===true?(LANG==='th'?'  Time windows  trip  routing':'Native roads, order, time-window, and trip gate passed'):native?.accepted===false?(LANG==='th'?'routing  cluster  Greedy/Savings ':'routing rejected the cluster ordering and used Greedy/Savings in the same run'):(LANG==='th'?' cluster  route':'A cluster-only test cannot validate route order');
  $('#clusterMetrics').innerHTML=cards([
    [LANG==='th'?'':'Selected method',selected,PENDING_CLUSTER_METHOD?(LANG==='th'?'':'Unsaved selection'):(latest?.stale?(LANG==='th'?' — ':'Historical result hidden — retest'):(latest?.effective_method?`effective: ${latest.effective_method}`:'Not tested'))],
    [LANG==='th'?' Assignment':'Assignment validation',val?(val.valid?'PASS':'FAIL'):'—',val?`${val.assignment_count}/${val.customer_count} assignments · coverage + capacity`:(LANG==='th'?'':'Test the selected method'),val?.valid?'good':val?'bad':''],
    [LANG==='th'?'Clusters ':'Used clusters',val?num(val.used_clusters):'—',val?`${val.used_clusters}/${val.target_clusters??val.used_clusters} target · max fleet ${val.maximum_available_trucks??'—'}`:'No assignment'],
    [LANG==='th'?'Native route gate':'Native route gate',nativeLabel,nativeDetail,native?.accepted===true?'good':native?.accepted===false?'warn':''],
  ]);
  $('#clusterValidationChip').className=`status-chip ${latest?.stale?'warn':native?.accepted===false?'warn':val?.valid?'pass':latest?.warning?'warn':'idle'}`;$('#clusterValidationChip').textContent=latest?.stale?'STALE INPUT':native?.accepted===false?'SAFE FALLBACK':val?.valid?'ASSIGNMENT VALID':latest?.warning?'REJECTED':'NO RESULT';
  renderReceipt($('#clusterInputReceipt'),latest?.stale?'stale':latestCurrent?'current':'neutral',latest?.stale?'!':latestCurrent?'✓':'◇',latest?.stale?(LANG==='th'?' partition  input ':'Historical partition hidden'):latestCurrent?(LANG==='th'?'Partition  input ':'Partition matches the current input'):(LANG==='th'?' source receipt':'No source receipt yet'),latest?.stale?(LANG==='th'?'  Fleet    ':'Work points, plan, fleet, capacity, graph, or road incidents changed. Test the method again.'):(LANG==='th'?' Parallel instances  clustering;  Fleet    partition':'Parallel instances do not alter clustering; work points, fleet, capacity, graph, and road incidents do.'),[['WORK POINTS',latestReceipt.customer_count],['CLUSTERS',latestReceipt.active_cluster_count],['MAX FLEET',latestReceipt.maximum_available_trucks],['CAPACITY',latestReceipt.capacity],['INPUT SHA',shortSha(latestReceipt.input_sha256)]]);
  const safety=$('#clusterSafetyBanner');
  if(safety){const state=latest?.stale?'rejected':native?.accepted===true?'accepted':native?.accepted===false?'fallback':val?.valid?'pending':latest?.warning?'rejected':'pending';safety.className=`cluster-safety-banner ${state}`;safety.innerHTML=`<i>${state==='accepted'?'✓':state==='fallback'?'↺':state==='rejected'?'!':'2'}</i><div><b>${esc(latest?.stale?(LANG==='th'?' input ':'Result belongs to an older input'):state==='accepted'?(LANG==='th'?'Route warm start  native gate':'Native route gate accepted the warm start'):state==='fallback'?(LANG==='th'?'Cluster ':'Cluster ordering rejected safely'):state==='rejected'?(LANG==='th'?'Assignment ':'Assignment rejected'):(LANG==='th'?' 2 ':'Two-stage safety check'))}</b><small>${esc(latest?.stale?(latest.stale_reason||'Retest clustering for the current source'):state==='fallback'?nativeDetail:state==='accepted'?nativeDetail:state==='rejected'?(latest?.warning||'Coverage or capacity validation failed'):(LANG==='th'?'1) Coverage + capacity  clustering · 2) Roads + order + TW + trips  Solver ':'1) Coverage + capacity here · 2) Roads + order + TW + trips when the solver runs'))}</small></div></div>`;}
  const preview=latestCurrent?latest?.preview:null;$('#clusterPreview').innerHTML=preview?`<img src="${artifactUrl(preview)}" data-image="${artifactUrl(preview)}" data-caption="Selected clustering" alt="Validated clustering partition">`:`<div>${latest?.stale?(LANG==='th'?' input  ':'The old-input image is hidden. Test the selected method again.'):(LANG==='th'?' “”':'Select a card, then press “Test selected method”.')}</div>`;
  $('#clusterAttempts').innerHTML=(latest?.attempts||[]).map(a=>`<div class="attempt-item"><div><b>${esc(a.method)}</b><small>${esc(a.error||'Coverage, IDs, and capacity assignment checks passed')}</small></div><span class="status-chip ${a.status==='passed'?'pass':'failed'}">${a.status}</span></div>`).join('')+(latest?.warning?`<div class="attempt-item"><div><b>Safe fallback</b><small>${esc(latest.warning)}</small></div><span class="status-chip warn">warning</span></div>`:'');
  renderReceipt($('#clusterBenchmarkReceipt'),bench?.stale?'stale':benchCurrent?'current':'neutral',bench?.stale?'!':benchCurrent?'✓':'◇',bench?.stale?(LANG==='th'?'Benchmark  input ':'Historical benchmark hidden from the current input'):benchCurrent?(LANG==='th'?'Benchmark  instance ':'Benchmark matches the current instance'):(LANG==='th'?' Benchmark instance ':'This instance has not been benchmarked'),bench?.stale?(LANG==='th'?' Benchmark ':'Run the benchmark again to rebuild the table and figures for the current work points.'):(LANG==='th'?'Backend  exact input/dataset SHA-256 ':'The backend records exact input/dataset SHA-256 before every method runs.'),[['JOB',benchReceipt.job_id!=null?`#${benchReceipt.job_id}`:null],['WORK POINTS',benchReceipt.customer_count],['ORDERS',benchReceipt.customer_order_count],['MAX FLEET',benchReceipt.maximum_available_trucks],['CAPACITY',benchReceipt.capacity],['INPUT SHA',shortSha(benchReceipt.input_sha256)]]);
  if(benchCurrent){const cols=[['label','method'],['effective_mode','effective mode'],['hard_assignment_feasible','assignment feasible'],['total_s','runtime s'],['nn_route_proxy_total_cost','route proxy cost'],['load_std','load std'],['total_overload','overload']];$('#clusterBenchmarkTable').innerHTML=`<table class="data-table"><thead><tr>${cols.map(([,label])=>`<th>${esc(label)}</th>`).join('')}</tr></thead><tbody>${bench.methods.map(m=>`<tr>${cols.map(([key])=>`<td>${key==='hard_assignment_feasible'?`<span class="status-chip ${m[key]?'pass':'fail'}">${m[key]?'yes':'no'}</span>`:typeof m[key]==='number'?num(m[key],key==='total_s'?4:2):esc(m[key]??'—')}</td>`).join('')}</tr>`).join('')}</tbody></table>`;$('#clusterFigureGallery').innerHTML=(bench.figures||[]).map(f=>figureCard(f)).join('');}else{$('#clusterBenchmarkTable').innerHTML=`<div class="empty-state">${bench?.stale?(LANG==='th'?' input ':'Scores and figures from an older input are never presented as current.'):(LANG==='th'?'Benchmark  ':'The full benchmark is a separate analysis. Run it only when you need a comparison.')}</div>`;$('#clusterFigureGallery').innerHTML='';}setDownloadLink($('#clusterBenchmarkDownload'),bench.archive?artifactUrl(bench.archive):null);
  bindImages();$$('[data-cluster-method]').forEach(b=>b.onclick=()=>{PENDING_CLUSTER_METHOD=b.dataset.clusterMethod;$('#clustering').value=PENDING_CLUSTER_METHOD;renderClustering();});
}
async function saveClusterPolicy(){try{await saveSettings(false);PENDING_CLUSTER_METHOD=null;toast(LANG==='th'?' Clustering ':'Clustering method saved',$('#clustering').value);await refresh(true);}catch(e){toast(LANG==='th'?'':'Save failed',e.message,true);}}
async function runSelectedClustering(){const method=PENDING_CLUSTER_METHOD||$('#clustering').value;if(['auto','none'].includes(method)){showResult({type:'warn',title:LANG==='th'?'':'Choose a concrete method',message:LANG==='th'?'Auto  None   clustering algorithm ':'Auto and None are policies, not concrete algorithms for a single-method test.'});return;}if(!STATE.preflight?.ready){toast(LANG==='th'?'':'Plan is not ready',LANG==='th'?' directed graph  road access ':'A current directed graph and road-validated work points are required',true);return;}try{PENDING_CLUSTER_METHOD=method;await saveSettings(false);const r=await api('/api/clustering/test',{method:'POST',body:JSON.stringify({method})});selectedJobId=r.job_id;resetJobLogs(r.job_id);toast(LANG==='th'?' Clustering':'Clustering test started',`${method} · Job #${r.job_id}`);activate('activity');await refresh(true);subscribeToActiveJob();}catch(e){showResult({type:'error',title:LANG==='th'?' Clustering ':'Clustering test failed',message:e.message});}}

function renderClosures(){const cs=STATE.closures||[];$('#closureList').innerHTML=cs.length?cs.map(c=>{const applied=c.application_status||c.status;const lifecycle=`<div class="closure-state-line"><span>${LANG==='th'?'':'Report'} ✓</span><span>${LANG==='th'?'':'Graph'} ${applied==='applied'?'✓':'—'}</span><span>input.txt ${c.applied_revision?`r${c.applied_revision}`:'—'}</span><span>${LANG==='th'?'':'Routes'} ${c.route_version_after?`v${c.route_version_after}`:c.reroute_deferred?(LANG==='th'?'':'queued'):'—'}</span></div>`;return`<div class="incident-item ${c.status}"><div style="display:flex;justify-content:space-between;gap:8px"><div><h4>${esc(c.road_name||'Unnamed road')}</h4><p>${esc(c.highway)} · ${c.block_reverse?(LANG==='th'?'':'both directions'):(LANG==='th'?'':'one direction')} · ${rel(c.reported_at)}</p></div><span class="status-chip ${c.status}">${localizeClosureStatus(c.status,applied)}</span></div><p><b>${esc(c.reporter)}:</b> ${esc(c.note||'—')}</p>${lifecycle}${c.reroute_message?`<p class="helper">${esc(c.reroute_message)}</p>`:''}<div class="incident-actions">${c.status==='pending'?`<button class="approve" data-ui-action="closure-decision" data-closure-id="${c.id}" data-approve="true">${LANG==='th'?' →  input → ':'Approve → update input → reroute'}</button><button class="reject" data-ui-action="closure-decision" data-closure-id="${c.id}" data-approve="false">${LANG==='th'?'':'Reject'}</button>`:c.status==='approved'?`<button class="reject" data-ui-action="closure-reopen" data-closure-id="${c.id}">${LANG==='th'?' →  edge → ':'Road reopened → restore edge → reroute'}</button>`:''}</div></div>`;}).join(''):`<div class="empty-state">${LANG==='th'?'':'No road-closure reports yet.'}</div>`;}
function localizeClosureStatus(status,applied){if(LANG!=='th')return applied==='applied'?'APPLIED':status.toUpperCase();return applied==='applied'?'':status==='pending'?'':status==='rejected'?'':status==='expired'?'':status;}
async function submitClosure(){if(!pendingClosureEdge)return;try{const body={lat:pendingClosureEdge.snap_lat,lon:pendingClosureEdge.snap_lon,reporter:$('#closureReporter').value.trim()||'dispatcher',note:$('#closureNote').value.trim(),block_reverse:$('#closureBothDirections').checked,edge:pendingClosureEdge};const r=await api('/api/closures',{method:'POST',body:JSON.stringify(body)});closeClosureModal();await refresh(true);showResult({type:'warn',title:LANG==='th'?'':'Report reached dispatch',message:LANG==='th'?'  Dispatcher   reroute ':'The report is stored immediately, but the edge is not removed until dispatch approval to prevent unsafe reroutes from an incorrect report.',details:[[LANG==='th'?'':'Road',r.road_name],[LANG==='th'?'':'Status',LANG==='th'?'':'Pending approval'],['OSM edge',`${r.osm_u} → ${r.osm_v} · ${r.osm_key}`]],primary:'OK'});}catch(e){showResult({type:'error',title:LANG==='th'?'':'Report failed',message:e.message});}}
window.decideClosure=async(id,approve)=>{if(approve&&!confirm(LANG==='th'?':  edge   input.txt  ?':'Confirm: apply this edge closure, regenerate input.txt, and reroute?'))return;try{const r=await api(`/api/closures/${id}/decision`,{method:'POST',body:JSON.stringify({approve,actor:'dispatcher',rerun:approve})});await refresh(true);showResult({type:approve?(r.input_updated?'success':'warn'):'success',title:approve?(LANG==='th'?'':'Closure applied to the system'):(LANG==='th'?'':'Report rejected'),message:approve?(r.reroute_deferred?(LANG==='th'?'edge  ':'The edge is applied now; rerouting will start automatically after the active job.'):(LANG==='th'?' edge   input.txt   reroute ':'FleetRoute removed the approved edge, regenerated input.txt, and queued a reroute.')):'',details:approve?[['input.txt',r.input_updated?(LANG==='th'?'':'regenerated'):(r.input_message||'pending')],[LANG==='th'?'Revision':'Revision',r.applied_revision],['Reroute',r.reroute_job_id?`Job #${r.reroute_job_id}`:(r.reroute_deferred?(LANG==='th'?'':'deferred automatically'):'—')]]:[],primary:'OK'});}catch(e){showResult({type:'error',title:LANG==='th'?'':'Decision failed',message:e.message});}};
window.reopenClosure=async id=>{if(!confirm(LANG==='th'?'  edge ?':'Confirm the road reopened, restore the edge, and reroute?'))return;try{const r=await api(`/api/closures/${id}/reopen?actor=dispatcher&rerun=true`,{method:'POST',body:'{}'});await refresh(true);showResult({type:'success',title:LANG==='th'?'':'Road restored to the graph',message:r.reroute_deferred?(LANG==='th'?'':'Rerouting will start after the active job.'):(LANG==='th'?' input ':'Input regenerated and reroute queued.'),details:[['Revision',r.applied_revision],['Reroute',r.reroute_job_id?`Job #${r.reroute_job_id}`:'deferred']]});}catch(e){showResult({type:'error',title:LANG==='th'?'':'Reopen failed',message:e.message});}};

async function validateSolverCommand(){
  try{
    const cfg=collectSettings();
    const r=await api('/api/solver/command-preview',{method:'POST',body:JSON.stringify(cfg)}),p=r.dynamic_policy||{};
    $('#solverCommandPreview').textContent=r.display;
    showResult({type:'success',title:'Command validated',message:`Routing command validated; the plan is passed to the optimizer without shell execution.`,details:[
      ['Customer policy',`${p.customer_count??'—'} → ${p.tier_label||'automatic'}`],
      ['Search strategy',p.phase_engine?'Adaptive multi-stage search':'Native adaptive search'],
      ['Workers',`${p.requested_instances??'—'} requested · ${p.effective_instances??'—'} effective · cap ${p.instance_cap??'—'}`],
      ['Stage slice',`${p.stage_time_s??'—'} s`],
      ['Stall guard',`${p.no_improve_stop_s??'—'} s`],
      ['Budget scope',p.budget_scope||'solve'],
      ['Research overrides',String(p.advanced_override_count??0)]
    ]});
  }catch(e){
    $('#solverCommandPreview').textContent=e.message;
    showResult({type:'error',title:'Command rejected',message:e.message});
  }
}

function showResult({type='success',title='Completed',message='',details=[],primary='OK',secondary='',onPrimary=null,onSecondary=null}={}){const modal=$('#resultModal'),icon=$('#resultIcon');icon.className=`result-icon ${type==='error'?'error':type==='warn'?'warn':''}`;icon.textContent=type==='error'?'!':type==='warn'?'i':'✓';$('#resultKicker').textContent=type==='error'?'ACTION REQUIRED':type==='warn'?'IMPORTANT':'ACTION COMPLETED';$('#resultTitle').textContent=title;$('#resultMessage').textContent=message||'';$('#resultDetails').innerHTML=(details||[]).map(([k,v])=>`<div><span>${esc(k)}</span><b>${esc(v)}</b></div>`).join('');const p=$('#resultPrimaryBtn'),s=$('#resultSecondaryBtn');p.textContent=primary||'OK';s.textContent=secondary||'';s.classList.toggle('hidden',!secondary);p.onclick=()=>{dismissDialog(modal);if(onPrimary)onPrimary();};s.onclick=()=>{dismissDialog(modal);if(onSecondary)onSecondary();};revealDialog(modal,'#resultPrimaryBtn');}
function notifyTerminalJob(job){
  if(!job||!['succeeded','failed','cancelled'].includes(job.status)||NOTIFIED_JOBS.has(job.id))return;
  NOTIFIED_JOBS.add(job.id);storageWrite('sessionStorage','fleetroute_notified_jobs',JSON.stringify([...NOTIFIED_JOBS].slice(-100)));
  const success=job.status==='succeeded',kind=job.kind,result=job.result||{};
  let title=success?(LANG==='th'?'':'Important step completed'):(LANG==='th'?' — ':'Job stopped — review required');
  let message=friendlyError(job.message);
  let details=[['Job',`#${job.id}`],[LANG==='th'?'':'Type',localizeJobKind(kind)]];
  let primary='OK',secondary='',onPrimary=null,onSecondary=null;
  if(success&&['network-build','network-expand'].includes(kind)){
    const customerCount=(STATE?.places||[]).filter(p=>p.role==='customer').length;
    title=LANG==='th'?'':'Road graph ready';
    message=customerCount?(LANG==='th'?`Directed Graph  Road access  ${customerCount}   Optimizer`:`The directed graph and road access for ${customerCount} work points are ready. Continue to the optimizer.`):(LANG==='th'?' ':'The graph is ready. Add or import work points next.');
    primary=customerCount?(LANG==='th'?' Optimizer':'Open Optimizer'):(LANG==='th'?'/':'Add/import work points');onPrimary=()=>activate(customerCount?'optimize':'plan');
    secondary=LANG==='th'?'':'Inspect road graph';onSecondary=()=>activate('roads');
  }else if(success&&kind==='clustering-test'){
    title=LANG==='th'?'Clustering ':'Clustering validated';message=result.clustering?.effective_method||job.message;
    primary=LANG==='th'?' Clustering Lab':'Open Clustering Lab';onPrimary=()=>activate('clustering');
  }else if(success&&kind==='convergence-analysis'){
    title=LANG==='th'?' Convergence  Log ':'Convergence figures rebuilt from the latest log';
    message=LANG==='th'?'Source receipt  figures  convergence.csv ':'The source receipt verifies that these figures were built directly from the current convergence.csv.';
    primary=LANG==='th'?' Convergence Lab':'Open Convergence Lab';onPrimary=()=>activate('analytics');
  }else if(success&&['solve','network-and-solve'].includes(kind)){
    const retained=result.optimizer_improved===false;
    title=LANG==='th'?'':'Fleet plan ready';
    message=retained?(LANG==='th'?`Route v${latestVersion()||result.route_version||'—'}  `:`Route v${latestVersion()||result.route_version||'—'} passed review and remains the best plan from this run.`):(LANG==='th'?`Route v${latestVersion()||result.route_version||'—'}  Optimizer  Driver App`:`Route v${latestVersion()||result.route_version||'—'} is the improved optimizer result and is ready in the Driver App.`);
    primary=LANG==='th'?'':'Open current fleet plan';onPrimary=()=>activate('dispatch');
    secondary=LANG==='th'?' Clustering / Convergence':'Clustering / convergence';onSecondary=()=>activate('clustering');
  }else if(success&&['scenario-generate','scenario-route'].includes(kind)){
    const currentRouteStatus=routeOperationalState();
    title=kind==='scenario-route'?(currentRouteStatus.completed?(LANG==='th'?'':'Work points created and routing complete'):(LANG==='th'?'':'Work points and initial plan prepared')):(LANG==='th'?'':'Road-verified work points are ready');
    const scenario=result.scenario||{};
    message=LANG==='th'?` ${scenario.customer_count??'—'}  · Demand  ${scenario.total_demand??'—'} ·  ${scenario.required_trucks_by_capacity??'—'}  ${scenario.maximum_trucks??'—'} `:`Created ${scenario.customer_count??'—'} stops · total demand ${scenario.total_demand??'—'} · about ${scenario.required_trucks_by_capacity??'—'} active of ${scenario.maximum_trucks??'—'} available trucks.`;
    details.push([LANG==='th'?'':'Work points',String(scenario.customer_count??'—')],[LANG==='th'?'':'Maximum available trucks',String(scenario.maximum_trucks??'—')],[LANG==='th'?' Capacity':'Minimum trucks by load',String(scenario.required_trucks_by_capacity??scenario.estimated_active_trucks??'—')],[LANG==='th'?'Demand ':'Total demand',String(scenario.total_demand??'—')],[LANG==='th'?'':'Load at minimum fleet',`${scenario.used_fleet_utilization_pct??'—'}%`]);
    primary=kind==='scenario-route'?(currentRouteStatus.completed?(LANG==='th'?'':'Open fleet plan'):(LANG==='th'?' Optimizer':'Monitor optimizer')):(LANG==='th'?'':'Open plan');onPrimary=()=>activate(kind==='scenario-route'?(currentRouteStatus.completed?'dispatch':'optimize'):'plan');
    if(kind==='scenario-route'){secondary=LANG==='th'?'':'Developer tests';onSecondary=()=>activate('clustering');}
  }else if(success&&kind==='complete-demo'){
    title=LANG==='th'?'':'Example scenario prepared';message=result.next_job_id?`${LANG==='th'?' Optimizer':'Handed off to the optimizer'} · Job #${result.next_job_id}`:job.message;
    primary=LANG==='th'?'':'Open plan';onPrimary=()=>activate('plan');secondary=LANG==='th'?'':'View job';onSecondary=()=>activate('activity');
  }else if(success&&kind==='rush'){
    title=LANG==='th'?' CSV ':'CSV plan validated and handed off';message=result.next_job_id?`${LANG==='th'?' Optimizer':'Handed off to the optimizer'} · Job #${result.next_job_id}`:job.message;
    details.push([LANG==='th'?'':'Work points',String(result.import?.customer_count??'—')],[LANG==='th'?'Clustering':'Clustering',String(result.clustering||'—')]);
    primary=LANG==='th'?'':'Open plan';onPrimary=()=>activate('plan');secondary=LANG==='th'?'':'View job';onSecondary=()=>activate('activity');
  }else if(success&&kind==='osm-source-download'){
    title=LANG==='th'?'':'Regional road data installed';message=LANG==='th'?' Depot   directed graph  Optimizer ':'Next, choose a depot and add work points. FleetRoute will prepare the directed graph and hand the plan to the optimizer.';
    primary=LANG==='th'?' Depot':'Choose depot';onPrimary=focusDepotSearch;
  }
  if(!success&&String(job.message||'').toLowerCase().includes('depot')&&String(job.message||'').toLowerCase().includes('road access')){
    title=LANG==='th'?'Depot  — ':'Depot road-access record needs repair';
    message=LANG==='th'?' Optimizer  Optimize / Depot + ':'Open Optimizer and run Optimize. FleetRoute will build/expand the graph and revalidate the depot plus every stop in the same job.';
    primary=LANG==='th'?' Optimizer · ':'Open Optimizer · auto repair';onPrimary=()=>activate('optimize');
  }
  showResult({type:success?'success':job.status==='cancelled'?'warn':'error',title,message,details,primary,secondary,onPrimary,onSecondary});
}

function setConsoleOpen(open){CONSOLE_OPEN=!!open;const drawer=$('#consoleDrawer');drawer.classList.toggle('hidden',!CONSOLE_OPEN);drawer.setAttribute('aria-hidden',String(!CONSOLE_OPEN));$('#openConsoleBtn').textContent=CONSOLE_OPEN?(LANG==='th'?'Console ':'Console open'):(LANG==='th'?' Process Console':'Open process console');if(CONSOLE_OPEN){CONSOLE_FOLLOW=true;if(selectedJobId)fetchJobLogChunk(selectedJobId,false,JOB_LOG_SOURCE).then(renderOpenConsole);}}
function updateConsoleControls(){
  const follow=$('#followConsoleBtn'),wrap=$('#wrapConsoleBtn');
  if(follow){follow.classList.toggle('active',CONSOLE_FOLLOW);follow.setAttribute('aria-pressed',String(CONSOLE_FOLLOW));follow.textContent=CONSOLE_FOLLOW?(LANG==='th'?' Log':'Following'):(LANG==='th'?' Log':'Follow');}
  if(wrap){wrap.classList.toggle('active',CONSOLE_WRAP);wrap.setAttribute('aria-pressed',String(CONSOLE_WRAP));wrap.textContent=CONSOLE_WRAP?(LANG==='th'?'':'Wrap'):(LANG==='th'?'':'No wrap');}
}
function setConsoleFollow(follow,scroll=true){CONSOLE_FOLLOW=!!follow;updateConsoleControls();const pre=$('#jobLog');if(scroll&&CONSOLE_FOLLOW&&pre)pre.scrollTop=pre.scrollHeight;}
function setConsoleWrap(wrap){CONSOLE_WRAP=!!wrap;const pre=$('#jobLog');if(pre)pre.classList.toggle('nowrap',!CONSOLE_WRAP);updateConsoleControls();}
function renderOpenConsole(){
  const pre=$('#jobLog');if(!pre||!selectedJobId||!CONSOLE_OPEN)return;
  const text=logText(selectedJobId,JOB_LOG_SOURCE);selectedJobLog=text;
  const selected=(STATE.jobs||[]).find(j=>+j.id===+selectedJobId),terminal=selected&&['succeeded','failed','cancelled'].includes(selected.status);
  const empty={
    raw:terminal?(LANG==='th'?' Combined Raw stream':'This job has no combined raw stream.'):(LANG==='th'?' process stream':'Waiting for process output…'),
    stdout:terminal?(LANG==='th'?' Solver Result  stdout':'The solver produced no stdout result for this job.'):(LANG==='th'?'Solver Result  native process ':'The solver result appears when the native process finishes.'),
    stderr:terminal?(LANG==='th'?' native diagnostics':'This job produced no native diagnostics.'):(LANG==='th'?' native diagnostics':'Waiting for native diagnostics…'),
    audit:terminal?(LANG==='th'?' Activity trace':'This job has no activity trace.'):(LANG==='th'?' Activity trace…':'Waiting for the activity trace…')
  };
  const renderKey=`${selectedJobId}:${JOB_LOG_SOURCE}:${JOB_LOG_OFFSETS[JOB_LOG_SOURCE].get(selectedJobId)||0}:${JOB_LOG_TRUNCATED[JOB_LOG_SOURCE].get(selectedJobId)?1:0}`;
  if(renderKey!==LAST_CONSOLE_RENDER_KEY){renderLogInto(pre,text,empty[JOB_LOG_SOURCE]||empty.raw);LAST_CONSOLE_RENDER_KEY=renderKey;}
  for(const source of ['raw','stdout','stderr','audit'])$(`#logSource${source[0].toUpperCase()+source.slice(1)}Btn`)?.classList.toggle('active',JOB_LOG_SOURCE===source);
  const notices={
    raw:LANG==='th'?'COMBINED RAW  stdout/stderr  backend reader   command/stdin/exit boundaries;   stream ':'COMBINED RAW interleaves stdout and stderr in backend reader-arrival order with command/stdin/exit boundaries; cross-stream order is not authoritative.',
    stdout:LANG==='th'?'SOLVER RESULT  stdout  route parser  ':'SOLVER RESULT is the separate decoded stdout used by the final native route parser.',
    stderr:LANG==='th'?'DIAGNOSTICS  stderr/cerr  telemetry, warning  native diagnostics':'DIAGNOSTICS is the separate decoded stderr/cerr stream for telemetry, warnings, and native diagnostics.',
    audit:LANG==='th'?'ACTIVITY  stage, heartbeat, command, exit code  error  FleetRoute ':'ACTIVITY is the user-readable FleetRoute trace of stages, heartbeats, commands, exit codes, and errors.'
  };
  const notice=$('#logSourceNotice');if(notice){const clipped=JOB_LOG_TRUNCATED[JOB_LOG_SOURCE].get(selectedJobId)?(LANG==='th'?' ·  2 MiB  UI   Runtime Evidence':' · showing the latest 2 MiB for UI performance; the full file remains in Runtime Evidence'):'';notice.textContent=notices[JOB_LOG_SOURCE]+clipped;}
  pre.classList.toggle('nowrap',!CONSOLE_WRAP);updateConsoleControls();if(CONSOLE_FOLLOW)pre.scrollTop=pre.scrollHeight;
}

function activeJob(){const jobs=(STATE?.jobs||[]).filter(j=>['queued','running'].includes(j.status));const rank={solve:0,'network-and-solve':0,'complete-demo':0,'rush':0,'scenario-generate':0,'scenario-route':0,'network-build':1,'network-expand':1,'osm-source-download':2,'clustering-test':3,'clustering-benchmark':4,'convergence-analysis':5,evidence:6};return jobs.sort((a,b)=>(rank[a.kind]??9)-(rank[b.kind]??9)||b.id-a.id)[0]||null;}
function jobLabel(j){const labels={'osm-source-download':'Regional road source','network-build':LANG==='th'?' Operating Graph':'Prepare operating graph','network-expand':LANG==='th'?' Operating Graph':'Expand operating graph','network-and-solve':LANG==='th'?' Optimizer':'Prepare graph + optimize','solve':LANG==='th'?'Route optimization':'Route optimization','complete-demo':LANG==='th'?'':'Complete example scenario','rush':LANG==='th'?' CSV':'CSV plan import','scenario-generate':LANG==='th'?'':'Generate road-valid work points','scenario-route':LANG==='th'?' Optimizer':'Create work points + optimize','clustering-test':LANG==='th'?' Clustering ':'Selected clustering test','clustering-benchmark':LANG==='th'?'Benchmark Clustering ':'Clustering benchmark','convergence-analysis':LANG==='th'?' Convergence':'Build convergence figures','evidence':LANG==='th'?'':'Post-run evidence'};return labels[j?.kind]||j?.kind||'Job';}


function tickTopJobUI(job){
  if(!job)return;
  const status=$('#projectStatus');if(status)status.textContent=job.message||currentStageLabel(job);
  const top=$('#topJobIndicator');if(top){top.className=`live-job compact ${job.status||''}`;top.setAttribute('aria-busy',String(['queued','running'].includes(job.status)));const text=$('span',top);if(text)text.textContent=job.message||currentStageLabel(job);}
}

function mergeJobSnapshot(job){
  if(!STATE||!job)return;const jobs=STATE.jobs||[];const i=jobs.findIndex(x=>+x.id===+job.id);
  const previous=i>=0?jobs[i]:null;
  const structural=!previous||previous.status!==job.status||previous.stage_key!==job.stage_key||Number(previous.stage_index)!==Number(job.stage_index)||Number(previous.stage_count)!==Number(job.stage_count);
  const merged={...(i>=0?jobs[i]:{}),...job,_clientSnapshotAt:Date.now()};
  if(i>=0)jobs[i]=merged;else jobs.unshift(merged);
  job=merged;
  const baselineVersion=job.result?.baseline?.published_route_version;
  if(baselineVersion&&!NOTIFIED_BASELINES.has(job.id)){
    NOTIFIED_BASELINES.add(job.id);storageWrite('sessionStorage','fleetroute_notified_baselines',JSON.stringify([...NOTIFIED_BASELINES].slice(-100)));
    toast(LANG==='th'?'':'Initial plan ready for review',LANG==='th'?`Route v${baselineVersion}  Optimizer `:`Route v${baselineVersion} appears as a dashed route while the optimizer runs.`);
    refresh(true,true);
  }
  if(structural)renderTop();else tickTopJobUI(job);
  if(currentView==='activity'){if(structural)renderActivity();else tickLiveJobUI(job);}
  else if(currentView==='developer'&&['succeeded','failed','cancelled'].includes(job.status))loadDeveloper(false);
  else if(currentView==='optimize'){if(structural)renderOptimize();else renderOptimizeTrace(job);}
  else if(currentView==='analytics')renderAnalytics();
  else if(currentView==='command'&&structural)renderCommand();
  else if(currentView==='roads'&&job.kind==='osm-source-download'&&!['succeeded','failed','cancelled'].includes(job.status))tickRoadDownloadUI(job);
  renderLiveOptimizerDock(job);
  if(['succeeded','failed','cancelled'].includes(job.status))notifyTerminalJob(job);
}


function updateJudgeModeButton(){const button=$('#judgeModeBtn');if(!button)return;button.setAttribute('aria-pressed',String(!JUDGE_MODE));button.textContent=JUDGE_MODE?(LANG==='th'?'':'Show analysis'):(LANG==='th'?'':'Back to operations');button.title=JUDGE_MODE?(LANG==='th'?' Clustering, Convergence,  ':'Show Clustering, Convergence, evidence, and system data'):(LANG==='th'?'––':'Return to the planning, routing, and driver workflow');}
function setJudgeMode(enabled){JUDGE_MODE=!!enabled;storageWrite('localStorage','fleetroute_judge_mode',String(JUDGE_MODE));document.body.classList.toggle('judge-mode',JUDGE_MODE);const panel=$('#advancedSolverPanel');if(panel&&JUDGE_MODE)panel.open=false;updateJudgeModeButton();if(JUDGE_MODE&&['clustering','analytics','developer','activity'].includes(currentView))activate('command');}
function setLanguage(){LANG='en';document.documentElement.lang='en';$$('[data-i18n]').forEach(el=>{const key=el.dataset.i18n;if(I18N.en?.[key])el.textContent=I18N.en[key];});if($('#searchQuery'))$('#searchQuery').placeholder="Search a place or coordinates: 13.7563, 100.5018";updateJudgeModeButton();setMenuOpen($('#appShell')?.classList.contains('menu-open'));activate(currentView,false);if(STATE)renderAll();}
function activate(view,scroll=true){
  const previousView=currentView;currentView=view;
  if(previousView==='roads'&&view!=='roads'&&ROAD_REQUEST_CONTROLLER){ROAD_REQUEST_SEQ+=1;ROAD_REQUEST_CONTROLLER.abort();ROAD_REQUEST_CONTROLLER=null;}
  $$('.view').forEach(v=>v.classList.toggle('active',v.id===`view-${view}`));$$('.nav-item').forEach(b=>{const selected=b.dataset.view===view;b.classList.toggle('active',selected);if(selected)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current');});
  const th={command:['',''],plan:['',''],roads:['',''],clustering:['','Clustering'],optimize:['','Optimizer'],analytics:['','Convergence'],dispatch:['',''],developer:['','Data & Runtime Inspector'],activity:['','']};
  const en={command:['OPERATIONS','System overview'],plan:['MAP-FIRST PLANNING','Depot & work points'],roads:['ROAD NETWORK','Roads & incidents'],clustering:['ANALYSIS','Clustering'],optimize:['ROUTE OPTIMIZATION','Optimizer'],analytics:['SEARCH EVIDENCE','Convergence'],dispatch:['OPERATIONS','Current fleet plan'],developer:['SYSTEM DATA','Data & Runtime Inspector'],activity:['AUDIT','Evidence & logs']};
  const title=(LANG==='th'?th:en)[view]||['',''];$('#breadcrumbKicker').textContent=title[0];$('#breadcrumbTitle').textContent=title[1];setMenuOpen(false);
  if(STATE&&view!=='analytics')renderView(view);
  setTimeout(()=>{if(view==='command')commandMap?.invalidateSize({pan:false,animate:false});if(view==='plan')planMap.invalidateSize({pan:false,animate:false});if(view==='roads'){roadsMap.invalidateSize({pan:false,animate:false});renderRoadMap();}if(view==='dispatch')routesMap.invalidateSize({pan:false,animate:false});},80);
  if(view==='analytics')loadConvergence();if(view==='developer')loadDeveloper(false);if(view==='activity'&&latestJob()){selectedJobId=selectedJobId||latestJob().id;loadJobLog(selectedJobId,true);}if(scroll)window.scrollTo({top:0,behavior:motionBehavior()});
}
function stagesForJob(job){const th=LANG==='th';const sets={
  'osm-source-download':[[th?'':'Source metadata',th?' checksum':'Resolve immutable source + checksum'],[th?' + ':'Download + integrity',th?' PBF + hash':'Stream the regional PBF while hashing'],[th?'':'Checksum',th?'':'Confirm the streamed checksum'],[th?'':'Ready',th?'':'Road source ready']],
  'network-build':[[th?'':'Local source',th?' PBF  SSD  Colab':'Prepare the regional road extract on Colab SSD'],[th?'':'Road graph',th?'':'Extract and build directed roads'],[th?'':'Road access',th?' Depot ':'Validate every depot round trip'],[th?'':'Ready',th?' RAM':'Keep graph and indexes in RAM']],
  'network-expand':[[th?'':'Local source',th?'':'Prepare road data'],[th?'':'Expand road graph',th?'':'Expand the operating area'],[th?'':'Validate work points',th?'':'Validate existing and new places'],[th?'':'Ready',th?'':'Updated graph ready']],
  'solve':[[th?'':'Operating graph',th?' RAM':'Reuse current in-memory graph'],[th?' Solver':'Solver input',th?' closure  input.txt':'Apply closures and write input.txt'],[th?'':'Initial feasible plan',th?' feasibility ':'Build and validate feasibility before search'],[th?'routing engine':'routing engine',th?' binary ':'Verify binary and exact command'],[th?'Clustering':'Clustering',th?' warm start ':'Run the selected warm start only'],[th?'':'Route improvement',th?' output  validation':'Stream native output while protecting the current plan'],[th?'':'Validate & apply',th?'':'Apply an improvement or retain the initial plan with evidence']],
  'network-and-solve':[[th?'':'Prepare graph',th?'':'Build or load operating area'],[th?' Solver':'Solver input',th?' input  closure ':'Materialize current closure-aware input'],[th?'':'Initial feasible plan',th?'  Optimizer ':'Prepare a feasible plan without claiming optimizer completion'],[th?'routing engine':'routing engine',th?' binary':'Verify binary'],[th?'Clustering':'Clustering',th?' warm start':'Validate warm start'],[th?'':'Search',th?'':'Search for a better route'],[th?'':'Validate & apply',th?' Driver App':'Apply the validated fleet plan to Driver App']],
  'complete-demo':[['Regional roads',th?'':'Check one-time road source'],[th?'':'Example scenario',th?' Depot  ':'Prepare depot, graph, and reachable work points'],[th?'routing Optimization':'routing optimization',th?' Solver ':'Hand off to solver without another click']],
  'rush':[['Regional roads',th?'':'Check the local road source'],[th?' CSV':'CSV plan',th?' Depot ':'Validate depot and every work-point row'],[th?'':'Automatic preparation',th?'':'Build or reuse the graph and validate all stops'],[th?' Solver':'Solver handoff',th?' Optimizer ':'Run the optimizer and validate the result automatically']],
  'scenario-generate':[[th?'':'Scenario contract',th?' Depot  ':'Check depot, road source, and fleet capacity'],[th?'':'Operating area',th?' cache ':'Load cache or prepare the graph once'],[th?'':'Verified work points',th?'– Depot ':'Sample only round-trip reachable road nodes']],
  'clustering-test':[[th?'':'Current instance',th?' input ':'Materialize the current graph and work points'],[th?'':'Selected method',th?' routing  assignment':'Run routing and validate assignments'],[th?'':'Validated partition',th?'':'Save result and preview']],
  'clustering-benchmark':[[th?'':'Operating graph',th?'':'Check road graph'],[th?' Benchmark':'Benchmark input',th?' input':'Materialize input'],[th?'':'All methods',th?' clustering ':'Run all clustering methods'],[th?'':'Figures',th?' scorecard ':'Create scorecard and figures']],
  'convergence-analysis':[[th?'Source receipt':'Source receipt',th?' SHA-256  convergence.csv':'Verify convergence.csv SHA-256'],[th?'':'Publication figures',th?' telemetry ':'Build figures from exact telemetry']],
  'evidence':[[th?'Convergence':'Convergence',th?' log ':'Analyze logs and figures'],[th?'':'Driver HTML',th?' Driver  all-truck':'Build driver pages'],[th?'':'Evidence ZIP',th?'':'Package run evidence']]};return sets[job?.kind]||Array.from({length:Math.max(1,Number(job?.stage_count)||1)},(_,i)=>[th?` ${i+1}`:`Stage ${i+1}`,'']);}
function localizeJobKind(kind){const th={'solve':'Route optimization','network-and-solve':' Optimizer','network-build':'','network-expand':'','osm-source-download':'Regional road source','complete-demo':'','rush':' CSV','scenario-generate':'','scenario-route':' Optimizer','clustering-test':' Clustering ','clustering-benchmark':'Benchmark Clustering','convergence-analysis':' Convergence','evidence':'','stream-test':' Log'};return LANG==='th'?(th[kind]||kind):({'solve':'Route optimization','network-and-solve':'Prepare graph + optimizer','network-build':'Prepare operating graph','network-expand':'Expand operating graph','osm-source-download':'Regional road source','complete-demo':'Complete example scenario','rush':'CSV plan import','scenario-generate':'Generate road-valid work points','scenario-route':'Create work points + optimize','clustering-test':'Selected clustering test','clustering-benchmark':'Clustering benchmark','convergence-analysis':'Build convergence figures','evidence':'Post-run evidence','stream-test':'Log stream test'}[kind]||kind);}

// =============================================================================
// OPTIMIZER STATE CONTRACT + AUTOMATIC BENCHMARK CONTROLS
// =============================================================================
let OPTIMIZER_DRAFT=null;
let OPTIMIZER_DIRTY=false;
let OPTIMIZER_EDIT_SEQ=0;
let OPTIMIZER_SAVE_TIMER=null;
let OPTIMIZER_SAVE_PROMISE=null;
let OPTIMIZER_SERVER_REV='0:0';
let ADVANCED_RENDER_KEY='';
const OPTIMIZER_TRACE_FETCHED=new Set();
const SOLVER_LIVE_PARSE_CACHE=new Map();
const OPTIMIZER_DRAFT_KEY='fleetroute_optimizer_draft_v390';
const OPTIMIZER_CONTROL_IDS=['trucks','capacity','instances','hardTime','objective','clustering','seed','routeStartTime','useTW','multiTrip','maxTrips','runConvergence','extraSolverArgs'];

function cloneJson(value){return JSON.parse(JSON.stringify(value??{}));}
function settingsRevisionToken(){const r=STATE?.settings_revision||{};return `${Number(r.fleet||0)}:${Number(r.solver||0)}`;}
function makeOptimizerDraftFromState(){return {fleet:{trucks:Number(STATE?.fleet?.trucks??4),capacity:Number(STATE?.fleet?.capacity??100)},solver:{...cloneJson(STATE?.solver||{}),advanced:cloneJson(STATE?.solver?.advanced||{})}};}
function syncOptimizerDraftFromState(force=false){
  if(!STATE)return;
  const rev=settingsRevisionToken();
  if(!OPTIMIZER_DRAFT){
    let restored=null;
    try{const raw=JSON.parse(localStorage.getItem(OPTIMIZER_DRAFT_KEY)||'null');if(raw&&raw.serverRev===rev&&Date.now()-Number(raw.savedAt||0)<3600000)restored=raw.draft;}catch{}
    OPTIMIZER_DRAFT=restored||makeOptimizerDraftFromState();OPTIMIZER_DIRTY=!!restored;OPTIMIZER_SERVER_REV=rev;
    return;
  }
  if(force||(!OPTIMIZER_DIRTY&&rev!==OPTIMIZER_SERVER_REV)){OPTIMIZER_DRAFT=makeOptimizerDraftFromState();OPTIMIZER_SERVER_REV=rev;ADVANCED_RENDER_KEY='';}
}
function setDraftState(kind,message=''){
  const el=$('#optimizerSaveState');if(!el)return;el.className=`draft-state ${kind}`;
  const labels={saved:LANG==='th'?'':'Saved',dirty:LANG==='th'?'':'Unsaved changes',saving:LANG==='th'?'…':'Saving…',error:LANG==='th'?'':'Save failed'};
  el.textContent=message||labels[kind]||kind;
}
function persistLocalDraft(){try{localStorage.setItem(OPTIMIZER_DRAFT_KEY,JSON.stringify({serverRev:OPTIMIZER_SERVER_REV,savedAt:Date.now(),draft:OPTIMIZER_DRAFT}));}catch{}}
function markOptimizerDirty(){OPTIMIZER_DIRTY=true;OPTIMIZER_EDIT_SEQ++;persistLocalDraft();setDraftState('dirty');clearTimeout(OPTIMIZER_SAVE_TIMER);OPTIMIZER_SAVE_TIMER=setTimeout(()=>saveOptimizerDraft(false,false).catch(()=>{}),700);}
function validNumberFrom(id,current){const el=$('#'+id);if(!el||el.value.trim()===''||!el.checkValidity())return current;const n=Number(el.value);return Number.isFinite(n)?n:current;}
function secondsToClockInput(value){const seconds=Math.max(0,Math.min(86399,Number(value)||0)),hours=Math.floor(seconds/3600),minutes=Math.floor((seconds%3600)/60);return `${String(hours).padStart(2,'0')}:${String(minutes).padStart(2,'0')}`;}
function clockInputToSeconds(value,current=28800){const match=/^(\d{2}):(\d{2})$/.exec(String(value||''));if(!match)return current;const hours=Number(match[1]),minutes=Number(match[2]);return hours<24&&minutes<60?hours*3600+minutes*60:current;}
function updateMultiTripControl(){const enabled=!!$('#multiTrip')?.checked,input=$('#maxTrips'),field=$('#maxTripsField');if(input)input.disabled=!enabled;if(field){field.classList.toggle('inactive',!enabled);field.setAttribute('aria-disabled',String(!enabled));}}
function syncOperatingPreset(){const value=Number($('#operatingRadius')?.value);$$('#operatingPresets button').forEach(btn=>btn.classList.toggle('active',Number(btn.dataset.radius)===value));}
function captureOptimizerDraft(){
  syncOptimizerDraftFromState();if(!OPTIMIZER_DRAFT)return;
  const d=OPTIMIZER_DRAFT;
  d.fleet.trucks=validNumberFrom('trucks',d.fleet.trucks);d.fleet.capacity=validNumberFrom('capacity',d.fleet.capacity);
  d.solver.seed=validNumberFrom('seed',d.solver.seed??777);d.solver.instances=validNumberFrom('instances',d.solver.instances??2);
  d.solver.hard_time_limit_s=validNumberFrom('hardTime',d.solver.hard_time_limit_s??30);
  d.solver.objective_mode=$('#objective')?.value||d.solver.objective_mode||'distance';
  d.solver.clustering=$('#clustering')?.value||d.solver.clustering||'none';
  d.solver.use_time_window=!!$('#useTW')?.checked;d.solver.allow_multi_trip=!!$('#multiTrip')?.checked;
  d.solver.route_start_time_s=clockInputToSeconds($('#routeStartTime')?.value,d.solver.route_start_time_s??28800);
  d.solver.max_trips_per_truck=validNumberFrom('maxTrips',d.solver.max_trips_per_truck??3);
  d.solver.run_convergence_analysis=!!$('#runConvergence')?.checked;
  d.solver.profile='auto_dynamic';
  d.solver.extra_args=$('#extraSolverArgs')?.value??d.solver.extra_args??'';
}
function collectSettings(){
  syncOptimizerDraftFromState();captureOptimizerDraft();
  const f=STATE?.fleet||{},d=OPTIMIZER_DRAFT||makeOptimizerDraftFromState(),s=d.solver||{};
  return {fleet:{...f,...d.fleet,network_type:$('#networkType')?.value||f.network_type||'drive',network_margin_m:validNumberFrom('networkMargin',f.network_margin_m??1200),snap_max_m:validNumberFrom('snapMax',f.snap_max_m??350),operating_radius_m:validNumberFrom('operatingRadius',f.operating_radius_m??8000),network_scope:'regional_offline'},solver:{...s,clustering:PENDING_CLUSTER_METHOD||s.clustering||'none',clustering_strict:$('#clusterStrict')?.checked??!!s.clustering_strict,advanced:cloneJson(s.advanced||{})}};
}
function optimizerDraftValidationError(){
  const labels={trucks:'Maximum trucks',capacity:'Capacity per truck',seed:'Random seed',instances:'Parallel workers',hardTime:'Maximum runtime',maxTrips:'Maximum trips per truck'};
  let message='';
  const requiredNumeric=['trucks','capacity','seed','instances','hardTime',...($('#multiTrip')?.checked?['maxTrips']:[])];
  for(const id of requiredNumeric){
    const el=$('#'+id);if(!el)continue;
    const invalid=el.value.trim()===''||!el.checkValidity()||!Number.isFinite(Number(el.value));
    el.setAttribute('aria-invalid',String(invalid));
    if(invalid&&!message){
      const range=el.min&&el.max?` between ${el.min} and ${el.max}`:el.min?` of at least ${el.min}`:'';
      message=`${labels[id]}: enter a valid ${el.step==='any'?'number':'whole number'}${range}.`;
    }
  }
  const departure=$('#routeStartTime');
  if(departure){const invalid=!departure.value||!departure.checkValidity();departure.setAttribute('aria-invalid',String(invalid));if(invalid&&!message)message='Fleet departure time: enter a time between 00:00 and 23:59.';}
  const help=$('#optimizerValidationMessage');if(help){help.textContent=message;help.classList.toggle('hidden',!message);}
  return message;
}
async function saveOptimizerDraft(showToast=false,refreshAfter=false){
  syncOptimizerDraftFromState();if(OPTIMIZER_SAVE_PROMISE)return OPTIMIZER_SAVE_PROMISE;
  const validationError=optimizerDraftValidationError();
  if(validationError){setDraftState('dirty','Check highlighted fields');if(showToast){toast('Settings not saved',validationError,true);$('#view-optimize [aria-invalid="true"]')?.focus();}throw new Error(validationError);}
  captureOptimizerDraft();const seq=OPTIMIZER_EDIT_SEQ;setDraftState('saving');
  const payload=collectSettings();
  OPTIMIZER_SAVE_PROMISE=(async()=>{try{
    const r=await api('/api/settings',{method:'POST',body:JSON.stringify(payload)});
    if(STATE){STATE.fleet=r.fleet;STATE.solver=r.solver;STATE.settings_revision=r.revision||STATE.settings_revision;}
    OPTIMIZER_SERVER_REV=`${Number(r.revision?.fleet||0)}:${Number(r.revision?.solver||0)}`;
    if(seq===OPTIMIZER_EDIT_SEQ){OPTIMIZER_DRAFT={fleet:{trucks:r.fleet.trucks,capacity:r.fleet.capacity},solver:cloneJson(r.solver)};OPTIMIZER_DIRTY=false;storageRemove('localStorage',OPTIMIZER_DRAFT_KEY);setDraftState('saved');}
    else{OPTIMIZER_DIRTY=true;persistLocalDraft();setDraftState('dirty');setTimeout(()=>saveOptimizerDraft(false,false).catch(()=>{}),100);}
    if(showToast)toast(LANG==='th'?'':'Settings saved',r.changed?`${(r.changed.fleet||[]).length+(r.changed.solver||[]).length} fields changed`:'');
    if(refreshAfter)await refresh(true,false);
    return r;
  }catch(e){setDraftState('error',LANG==='th'?'':'Save failed');if(showToast)toast(LANG==='th'?'':'Save failed',e.message,true);throw e;}finally{OPTIMIZER_SAVE_PROMISE=null;}})();
  return OPTIMIZER_SAVE_PROMISE;
}
async function saveSettings(showToast=true){
  clearTimeout(OPTIMIZER_SAVE_TIMER);
  if(OPTIMIZER_SAVE_PROMISE){try{await OPTIMIZER_SAVE_PROMISE;}catch{}}
  // Post once more after any in-flight autosave so Optimize always launches
  // with the newest visible values, including road controls not in the draft.
  return saveOptimizerDraft(showToast,showToast);
}

function applySettings(){
  if(!STATE)return;syncOptimizerDraftFromState();const f=STATE.fleet||{},d=OPTIMIZER_DRAFT||makeOptimizerDraftFromState(),s=d.solver||{};
  const set=(id,v)=>{const el=$(id);if(el&&document.activeElement!==el&&v!==undefined&&v!==null)el.value=v;};
  // Road/network fields remain backend-authoritative.
  set('#networkType',f.network_type);set('#networkMargin',f.network_margin_m);set('#snapMax',f.snap_max_m);set('#operatingRadius',f.operating_radius_m||8000);set('#networkScope','regional_offline');syncOperatingPreset();
  // Optimizer fields come from the durable draft, never directly from an SSE refresh.
  set('#trucks',d.fleet.trucks);set('#capacity',d.fleet.capacity);set('#seed',s.seed);set('#instances',s.instances);set('#hardTime',s.hard_time_limit_s);set('#objective',s.objective_mode);set('#routeStartTime',secondsToClockInput(s.route_start_time_s??28800));set('#maxTrips',s.max_trips_per_truck??3);if(!PENDING_CLUSTER_METHOD)set('#clustering',s.clustering);set('#extraSolverArgs',s.extra_args||'');
  if($('#useTW')&&document.activeElement!==$('#useTW'))$('#useTW').checked=s.use_time_window!==false;
  if($('#multiTrip')&&document.activeElement!==$('#multiTrip'))$('#multiTrip').checked=!!s.allow_multi_trip;
  updateMultiTripControl();
  if($('#clusterStrict')&&document.activeElement!==$('#clusterStrict'))$('#clusterStrict').checked=!!s.clustering_strict;
  if($('#runConvergence')&&document.activeElement!==$('#runConvergence'))$('#runConvergence').checked=s.run_convergence_analysis===true;
  if($('#rushTrucks')&&document.activeElement!==$('#rushTrucks'))$('#rushTrucks').value=d.fleet.trucks||4;if($('#rushCapacity')&&document.activeElement!==$('#rushCapacity'))$('#rushCapacity').value=d.fleet.capacity||100;
  setDraftState(OPTIMIZER_DIRTY?'dirty':'saved');
  renderOptimizerAutoPolicy();
}
function optimizerPolicyPreview(){
  const tiers=STATE?.solver_advanced_schema?.tiers||[],count=(STATE?.places||[]).filter(p=>p.role==='customer').length,selectionCount=Math.max(1,count),tier=tiers.find(x=>selectionCount<=Number(x.customers))||tiers.at(-1)||{customers:10,stage_time_s:4,base_no_improve_s:10,instance_cap:6,optimizer_generation:'FleetRoute Optimizer',phase_engine:true,budget_scope:'solve'};
  const runtime=Math.max(5,Number(OPTIMIZER_DRAFT?.solver?.hard_time_limit_s??STATE?.solver?.hard_time_limit_s??30)),requested=Math.max(1,Number(OPTIMIZER_DRAFT?.solver?.instances??STATE?.solver?.instances??2)),cap=Math.max(1,Number(tier.instance_cap||6)),effective=Math.min(requested,cap),patience=Math.min(Number(tier.base_no_improve_s||10),Math.max(5,Math.floor((runtime+1)/2))),advanced=OPTIMIZER_DRAFT?.solver?.advanced||{};
  return {count,tier,runtime,requested,effective,cap,patience,overrides:Object.keys(advanced).length};
}
function renderOptimizerAutoPolicy(){
  const root=$('#optimizerAutoPolicy');if(!root||!STATE)return;const p=optimizerPolicyPreview(),tiers=STATE?.solver_advanced_schema?.tiers||[],upper=Number(p.tier.customers)===450,above=p.count>Number(p.tier.customers),countLabel=p.count===0?'No work points yet':`${p.count} work point${p.count===1?'':'s'}`,selectionHelp=p.count===0?'Starting size-band preview; it updates as work points are added.':above?'Above 450 work points; using the upper operational guardrail band while the optimizer adapts its search internally.':`Smallest operational size band that covers this plan${upper?' · upper guardrail band':''}.`;
  root.innerHTML=`<div class="auto-policy-head"><div><span class="section-kicker">ADAPTIVE ROUTING POLICY</span><b>${countLabel} → ${esc(p.tier.label||`≤ ${p.tier.customers} work points`)}</b><small>${selectionHelp}</small></div><span class="auto-policy-badge">AUTO${upper?' · UPPER':''}</span></div><div class="auto-policy-stats"><span><small>Search strategy</small><b>Adaptive multi-stage search</b></span><span><small>Planning slice</small><b>${p.tier.stage_time_s}s</b></span><span><small>Stall guard</small><b>${p.patience}s</b></span><span><small>Parallel workers</small><b>${p.effective} effective</b></span><span><small>Runtime ceiling</small><b>${p.runtime}s user-set</b></span></div><div class="tier-rail" aria-label="Operational work-point size bands">${tiers.map(t=>`<span class="tier-node ${Number(t.customers)===Number(p.tier.customers)?'active':''} ${Number(t.customers)===450?'heavy':''}" ${Number(t.customers)===Number(p.tier.customers)?'aria-current="true"':''} title="${esc(t.label||`≤ ${t.customers} work points`)} · adaptive routing policy">${t.customers}</span>`).join('')}</div><div class="auto-policy-foot">FleetRoute automatically scales runtime guardrails to the live plan while the optimizer adapts its search internally. Visible solve controls define the fleet, departure time, runtime, parallel-worker ceiling, objective, and route rules. Instance request ${p.requested}, capped at ${p.cap}. Stall guard = min(${p.tier.base_no_improve_s}s size-band allowance, max(5s, half-up 50% of runtime)). ${p.overrides?p.overrides+' expert override'+(p.overrides===1?'':'s')+' active.':'Production defaults are active.'}</div>`;
  const help=$('#instancesPolicyHelp');if(help)help.textContent=p.requested>p.cap?`Requested ${p.requested}; this problem size currently caps parallel workers at ${p.cap}.`:`Effective parallel workers: ${p.effective}.`;
}
function advancedProfileDefault(key){const p=optimizerPolicyPreview();return STATE?.solver_advanced_schema?.tier_defaults?.[String(p.tier.customers)]?.[key];}
function advancedValueLabel(v){if(v===true)return'ON';if(v===false)return'OFF';return v==null?'auto/native':String(v);}
function updateAdvancedCount(){const schema=STATE?.solver_advanced_schema||{},el=$('#advancedOverrideCount');if(!el)return;if(!schema.enabled){el.textContent='No overrides';return;}const n=Object.keys(OPTIMIZER_DRAFT?.solver?.advanced||{}).length,total=Number(schema.count||0);el.textContent=n?`${n} ${n===1?'override':'overrides'} active`:'No overrides';}
function renderAdvancedSolverControls(force=false){
  const schema=STATE?.solver_advanced_schema||{};
  ['#researchAdvancedToolbar','#advancedSolverFields','#researchRawFlagsPanel'].forEach(sel=>$(sel)?.classList.toggle('hidden',!schema.enabled));
  const root=$('#advancedSolverFields');if(!root||!STATE){updateAdvancedCount();return;}syncOptimizerDraftFromState();
  if(!schema.enabled){OPTIMIZER_DRAFT.solver.advanced={};updateAdvancedCount();return;}
  if(!force&&document.activeElement&&root.contains(document.activeElement))return;
  const fields=schema.fields||[],overrides=OPTIMIZER_DRAFT?.solver?.advanced||{},q=($('#advancedSolverSearch')?.value||'').trim().toLowerCase(),onlyOverrides=!!$('#advancedOverridesOnly')?.checked;
  const key=JSON.stringify([settingsRevisionToken(),optimizerPolicyPreview().tier.customers,overrides,q,onlyOverrides,LANG]);if(!force&&key===ADVANCED_RENDER_KEY){updateAdvancedCount();return;}ADVANCED_RENDER_KEY=key;
  const visible=fields.filter(f=>(!onlyOverrides||Object.prototype.hasOwnProperty.call(overrides,f.key))&&(!q||`${f.label} ${f.flag} ${f.category} ${f.description}`.toLowerCase().includes(q)));
  const cats=[];for(const f of visible){let g=cats.find(x=>x.name===f.category);if(!g){g={name:f.category,fields:[]};cats.push(g);}g.fields.push(f);}
  root.innerHTML=cats.length?cats.map((g,gi)=>`<details class="advanced-group" ${(q||gi===0)?'open':''}><summary><div><span class="section-kicker">${esc(g.name.toUpperCase())}</span><b>${esc(g.name)}</b></div><span>${g.fields.length} controls</span></summary><div class="advanced-control-grid">${g.fields.map(f=>{const has=Object.prototype.hasOwnProperty.call(overrides,f.key),v=has?overrides[f.key]:null,def=advancedProfileDefault(f.key),hint=def!==undefined?`Auto · ${advancedValueLabel(def)}`:'Auto / native default';if(f.type==='bool')return`<label class="advanced-control ${has?'overridden':''}"><span><b>${esc(f.label)}</b><code>${esc(f.flag)}</code></span><select data-advanced-key="${esc(f.key)}" data-advanced-type="bool"><option value="" ${!has?'selected':''}>${esc(hint)}</option><option value="true" ${v===true?'selected':''}>Enabled override</option><option value="false" ${v===false?'selected':''}>Disabled override</option></select><small>${esc(f.description)}</small></label>`;return`<label class="advanced-control ${has?'overridden':''}"><span><b>${esc(f.label)}</b><code>${esc(f.flag)}</code></span><input data-advanced-key="${esc(f.key)}" data-advanced-type="${esc(f.type)}" type="number" ${f.min!=null?`min="${f.min}"`:''} ${f.max!=null?`max="${f.max}"`:''} step="${f.step??(f.type==='int'?1:'any')}" value="${has?esc(v):''}" placeholder="${esc(hint)}"><small>${esc(f.description)}</small></label>`;}).join('')}</div></details>`).join(''):`<div class="empty-state">${LANG==='th'?' setting ':'No advanced setting matches this search.'}</div>`;
  updateAdvancedCount();
}
function optimizerAdvancedInput(target){
  const key=target.dataset.advancedKey;if(!key)return;syncOptimizerDraftFromState();const advanced=OPTIMIZER_DRAFT.solver.advanced||(OPTIMIZER_DRAFT.solver.advanced={});
  if(target.value===''){delete advanced[key];}
  else if(target.dataset.advancedType==='bool')advanced[key]=target.value==='true';
  else{if(!target.checkValidity())return;const n=Number(target.value);if(!Number.isFinite(n))return;advanced[key]=target.dataset.advancedType==='int'?Math.trunc(n):n;}
  updateAdvancedCount();renderOptimizerAutoPolicy();markOptimizerDirty();
}
function bindOptimizerSettings(){
  for(const id of OPTIMIZER_CONTROL_IDS){const el=$('#'+id);if(!el)continue;const evt=(el.tagName==='SELECT'||el.type==='checkbox')?'change':'input';el.addEventListener(evt,()=>{if(id==='clustering')PENDING_CLUSTER_METHOD=null;if(id==='multiTrip')updateMultiTripControl();captureOptimizerDraft();renderOptimizerAutoPolicy();markOptimizerDirty();});}
  $('#advancedSolverPanel')?.addEventListener('input',e=>{if(e.target?.dataset?.advancedKey)optimizerAdvancedInput(e.target);});
  $('#advancedSolverPanel')?.addEventListener('change',e=>{if(e.target?.dataset?.advancedKey)optimizerAdvancedInput(e.target);});
  $('#advancedSolverSearch')?.addEventListener('input',()=>{ADVANCED_RENDER_KEY='';renderAdvancedSolverControls(true);});
  $('#advancedOverridesOnly')?.addEventListener('change',()=>{ADVANCED_RENDER_KEY='';renderAdvancedSolverControls(true);});
  $('#resetAdvancedSolverBtn')?.addEventListener('click',()=>{syncOptimizerDraftFromState();OPTIMIZER_DRAFT.solver.advanced={};ADVANCED_RENDER_KEY='';renderAdvancedSolverControls(true);renderOptimizerAutoPolicy();markOptimizerDirty();});
}

async function ensureOptimizerTraceStreams(job){
  if(!job||!['solve','network-and-solve'].includes(job.kind))return;
  const key=Number(job.id);if(!key)return;
  const terminal=['succeeded','failed','cancelled'].includes(job.status);
  const needErr=!logText(key,'stderr'),needOut=!logText(key,'stdout');
  // A terminal fetch is mandatory once per solver job even if a live tail is
  // already present. This closes the race where the last stdout/cerr bytes land
  // between the final SSE snapshot and the page repaint.
  if(terminal){
    if(OPTIMIZER_TRACE_FETCHED.has(key))return;
    OPTIMIZER_TRACE_FETCHED.add(key);
    await Promise.all([
      fetchJobLogChunk(key,true,'stderr'),
      fetchJobLogChunk(key,true,'stdout'),
    ]);
  }else if(needErr||needOut){
    await Promise.all([
      needErr?fetchJobLogChunk(key,true,'stderr'):null,
      needOut?fetchJobLogChunk(key,true,'stdout'):null,
    ]);
  }
  const fresh=(STATE?.jobs||[]).find(x=>+x.id===key)||job;if(currentView==='optimize')renderOptimizeTrace(fresh);
}
function renderOptimizationStateBanner(){
  const status=routeOperationalState(),banner=$('#optimizationStateBanner');if(!banner)return;
  const source=String(STATE.route_state?.solution_source||STATE.latest_routes?.payload?.solution_source||'');
  const sourceLabel=status.phase==='reviewed'?(LANG==='th'?'':'INITIAL PLAN RETAINED'):source==='cpp_optimizer'?(LANG==='th'?' Optimizer':'OPTIMIZED RESULT'):source==='deterministic_baseline'?(LANG==='th'?' Deterministic':'DETERMINISTIC INITIAL PLAN'):(LANG==='th'?'':'NO ROUTE SOURCE');
  banner.className=`optimization-state-banner ${status.phase}`;
  $('.optimization-state-icon',banner).textContent=status.icon;
  $('#optimizationStateTitle').textContent=status.title;
  $('#optimizationStateDetail').textContent=status.detail;
  const active=activeSolverJob();
  const facts=[
    latestVersion()?`ROUTE v${latestVersion()}`:(LANG==='th'?' Route version':'NO ROUTE VERSION'),
    sourceLabel,
    active?`JOB #${active.id} · ${localizeStatus(active.status)}`:(status.completed?(LANG==='th'?'OPTIMIZER ':'OPTIMIZER COMPLETE'):('NEXT · OPTIMIZER')),
  ];
  $('#optimizationStateFacts').innerHTML=facts.map(value=>`<span>${esc(value)}</span>`).join('');
}
function renderOptimize(){
  const job=renderOptimizeBase();syncOptimizerDraftFromState();applySettings();renderAdvancedSolverControls(false);
  renderOptimizationStateBanner();
  if(job)ensureOptimizerTraceStreams(job);
  const wf=STATE?.workflow;if(wf?.next_action&&$('#optimizerPreflight')){const c=wf.completed||{},reuse=c.graph&&c.access;$('#optimizerPreflight').insertAdjacentHTML('beforeend',`<div class="workflow-next ${reuse?'ready':''}"><div><span class="section-kicker">NEXT ACTION · DATABASE STATE</span><b>${esc(wf.next_action.label||'')}</b><small>${reuse?(LANG==='th'?` ${wf.graph_id||''}  —  Prepare Graph `:`Graph ${wf.graph_id||''} is valid and will be reused; no repeated graph build is required.`):(wf.next_action.automatic?(LANG==='th'?' Optimize':'Repairable preparation will run automatically when you press Optimize.'):'')}</small></div><span class="status-chip ${reuse?'pass':wf.next_action.automatic?'running':'idle'}">${reuse?'REUSE':wf.next_action.automatic?'AUTO':'NEXT'}</span></div>`);}
}
function optimizerTelemetry(job,stderrText=''){
  const structured=job?.result?.optimizer_live||{};
  // Do not poison the stderr parse cache with an empty floating-dock read.
  // The structured heartbeat is authoritative once present; stderr fallback is
  // only for the short initialization window before the first structured event.
  const fallback=stderrText?cachedSolverLive(job?.id,stderrText):{};
  const merged={...fallback};
  for(const [key,value] of Object.entries(structured)){if(value!==null&&value!==undefined)merged[key]=value;}
  return merged;
}
function validatedCurvePoints(telemetry){
  return (Array.isArray(telemetry?.curve)?telemetry.curve:[]).map(point=>({time_s:Number(point?.time_s),best:Number(point?.best),event:String(point?.event||'')})).filter(point=>Number.isFinite(point.time_s)&&point.time_s>=0&&Number.isFinite(point.best)&&point.best>0).sort((a,b)=>a.time_s-b.time_s);
}
function renderValidatedBestCurve(svg,telemetry,elapsed=0,compact=false){
  if(!svg)return;
  const points=validatedCurvePoints(telemetry),width=compact?340:520,height=compact?106:148,padL=compact?10:14,padR=compact?10:14,padT=compact?10:14,padB=compact?18:23;
  if(!points.length){
    const prep=telemetry?.backend_prep||{},done=Number(prep.sources_done),total=Number(prep.sources_total);
    const emptyText=Number.isFinite(total)&&total>0?`Preparing directed road costs${Number.isFinite(done)?` · ${Math.max(0,done)}/${total}`:''}…`:'Waiting for the first feasible route…';
    svg.setAttribute('viewBox',`0 0 ${width} ${height}`);svg.innerHTML=`<text class="live-curve-empty" x="${width/2}" y="${height/2}" text-anchor="middle">${esc(emptyText)}</text>`;return;
  }

  // The compact floating monitor keeps the true construction start in its
  // numeric receipt, but once search begins it may zoom the Y-domain to the
  // best validated warm-start + subsequent search incumbents. A very expensive
  // raw greedy seed can otherwise flatten every meaningful late improvement.
  // No objective is altered or synthesized; the omitted early vertical span is
  // explicitly marked as an off-scale validated start.
  const warmEvent=/^(external_validated_start|cluster_validated_start|greedy_validated_start|compact_fill_validated_improvement|savings_validated_improvement)$/;
  let plotFrom=0,zoomedConstructionStart=false;
  if(compact&&points.length>=3){
    const firstSearch=points.findIndex((p,i)=>i>0&&!warmEvent.test(p.event));
    if(firstSearch>0){
      // If search improves immediately after the raw construction seed, zoom
      // from that first search incumbent rather than requiring a second warm point.
      const candidateFrom=firstSearch>1?firstSearch-1:firstSearch,tail=points.slice(candidateFrom),tailVals=tail.map(p=>p.best),tailMin=Math.min(...tailVals),tailMax=Math.max(...tailVals),tailSpan=Math.max(1e-9,tailMax-tailMin),earlyGap=points[0].best-tailMax;
      if(candidateFrom>0&&earlyGap>Math.max(tailSpan*2.5,Math.abs(tailMax)*.08)){plotFrom=candidateFrom;zoomedConstructionStart=true;}
    }
  }
  const plotted=points.slice(plotFrom),now=Math.max(Number(elapsed)||0,points[points.length-1].time_s,.25),values=plotted.map(p=>p.best),rawMin=Math.min(...values),rawMax=Math.max(...values);let lo=rawMin,hi=rawMax;
  if(Math.abs(hi-lo)<=Math.max(1e-9,Math.abs(hi)*1e-9)){const margin=Math.max(1,Math.abs(hi)*.005);lo-=margin;hi+=margin;}else{const margin=(hi-lo)*.08;lo-=margin;hi+=margin;}
  const innerW=width-padL-padR,innerH=height-padT-padB,x=t=>padL+Math.max(0,Math.min(1,t/now))*innerW,y=v=>padT+(hi-v)/(hi-lo)*innerH;
  let path=`M ${x(plotted[0].time_s).toFixed(2)} ${y(plotted[0].best).toFixed(2)}`;
  for(let i=1;i<plotted.length;i++){path+=` H ${x(plotted[i].time_s).toFixed(2)} V ${y(plotted[i].best).toFixed(2)}`;}
  path+=` H ${x(now).toFixed(2)}`;
  const firstX=x(plotted[0].time_s).toFixed(2),lastX=x(now).toFixed(2),baseline=(height-padB).toFixed(2),area=`M ${firstX} ${baseline} L ${firstX} ${y(plotted[0].best).toFixed(2)}${path.slice(path.indexOf(' H '))} L ${lastX} ${baseline} Z`;
  const grid=[.25,.5,.75].map(fr=>{const gy=(padT+innerH*fr).toFixed(2);return`<line class="live-curve-grid" x1="${padL}" y1="${gy}" x2="${width-padR}" y2="${gy}"/>`;}).join('');
  const last=points[points.length-1],dot=`<circle class="live-curve-dot" cx="${x(last.time_s).toFixed(2)}" cy="${y(last.best).toFixed(2)}" r="${compact?3.2:3.6}"/>`;
  const offscale=zoomedConstructionStart?`<path class="live-curve-start-drop" d="M ${x(points[0].time_s).toFixed(2)} ${padT+2} H ${x(plotted[0].time_s).toFixed(2)} V ${y(plotted[0].best).toFixed(2)}"/><text class="live-curve-start-label" x="${padL+2}" y="${padT+8}">initial plan ${num(points[0].best,2)} ↘ · focused scale</text>`:'';
  const labels=compact?`<text class="live-curve-label" x="${padL}" y="${height-5}">0s</text><text class="live-curve-label" x="${width-padR}" y="${height-5}" text-anchor="end">${now.toFixed(now<10?1:0)}s</text>`:`<text class="live-curve-best" x="${padL}" y="10">${num(rawMax,2)}</text><text class="live-curve-best" x="${padL}" y="${height-padB+15}">${num(rawMin,2)}</text><text class="live-curve-label" x="${width-padR}" y="${height-6}" text-anchor="end">${now.toFixed(now<10?1:0)} s</text>`;
  svg.setAttribute('viewBox',`0 0 ${width} ${height}`);svg.innerHTML=`${grid}<line class="live-curve-axis" x1="${padL}" y1="${height-padB}" x2="${width-padR}" y2="${height-padB}"/>${offscale}<path class="live-curve-area" d="${area}"/><path class="live-curve-line" d="${path}"/>${dot}${labels}`;
}
function optimizerCurveMetaText(telemetry,elapsed){
  const points=validatedCurvePoints(telemetry),count=Number(telemetry?.improvement_events)||points.length,last=Number(telemetry?.last_improvement_time_s),age=Number.isFinite(last)?Math.max(0,(Number(elapsed)||0)-last):null;
  const sampled=telemetry?.curve_decimated?' · display thinned, no synthetic points':'';
  if(!count||!points.length){
    const prep=telemetry?.backend_prep||{},done=Number(prep.sources_done),total=Number(prep.sources_total),prepElapsed=Number(prep.elapsed_s);
    if(Number.isFinite(total)&&total>0){const progress=Number.isFinite(done)?` · ${Math.max(0,done)}/${total} sources`:'';return `Preparing directed road costs${progress}${Number.isFinite(prepElapsed)?` · ${prepElapsed.toFixed(1)}s`:''}`;}
    return 'Waiting for the first feasible route';
  }
  const start=points[0].best,best=points[points.length-1].best,gain=start-best,gainPct=start>0?Math.max(0,gain/start*100):0;
  const progress=gain>Math.max(1e-9,Math.abs(start)*1e-12)?` · start ${num(start,2)} → ${num(best,2)} (−${gainPct.toFixed(gainPct<1?2:1)}%)`:` · start ${num(start,2)}`;
  return `${count} best update${count===1?'':'s'}${progress}${age==null?'':` · last change ${age.toFixed(1)}s ago`}${sampled}`;
}
function optimizerLiveClocks(job,live,processLive){
  const clientAge=processLive&&job?._clientSnapshotAt?Math.max(0,(Date.now()-job._clientSnapshotAt)/1000):0,age=Math.min(clientAge,1.5),result=job?.result||{},timing=result.process_timing||{};
  const governedRaw=live?.governed_elapsed_s??result.solver_search_runtime_s??timing.governed_elapsed_s;
  const explicitBudgetStarted=live?.budget_started??timing.budget_started;
  const searchFallback=live?.elapsed_s??live?.stage_elapsed_s??result.solver_search_runtime_s??0;
  const budgetStarted=explicitBudgetStarted===true||(explicitBudgetStarted==null&&Number(governedRaw??searchFallback)>0);
  const processBase=Number(live?.process_elapsed_s??result.solver_process_runtime_s??timing.process_elapsed_s??result.solver_runtime_s??live?.job_elapsed_s??0);
  const searchBase=Number(governedRaw??(budgetStarted?searchFallback:0)??0);
  return {
    processElapsed:Math.max(0,processBase)+(processLive?age:0),
    searchElapsed:Math.max(0,searchBase)+(processLive&&budgetStarted?age:0),
    budgetStarted,
  };
}
function bindLiveOptimizerDock(){
  const min=$('#liveOptimizerDockMinimize'),close=$('#liveOptimizerDockClose'),open=$('#liveOptimizerDockOpen');
  if(min)min.onclick=()=>{LIVE_OPTIMIZER_MINIMIZED=!LIVE_OPTIMIZER_MINIMIZED;renderLiveOptimizerDock();};
  if(close)close.onclick=()=>{if(LIVE_OPTIMIZER_JOB_ID!=null)LIVE_OPTIMIZER_DISMISSED.add(Number(LIVE_OPTIMIZER_JOB_ID));renderLiveOptimizerDock();};
  if(open)open.onclick=()=>activate('optimize');
}
function renderLiveOptimizerDock(preferredJob=null){
  const root=$('#liveOptimizerDock');if(!root||!STATE)return;
  const solverJobs=(STATE.jobs||[]).filter(j=>['solve','network-and-solve'].includes(j.kind));
  const liveJob=preferredJob&&['solve','network-and-solve'].includes(preferredJob.kind)&&preferredJob.result?.live?.process_alive?preferredJob:solverJobs.find(j=>j.result?.live?.process_alive&&['queued','running'].includes(j.status));
  if(liveJob&&Number(liveJob.id)!==Number(LIVE_OPTIMIZER_JOB_ID)){LIVE_OPTIMIZER_JOB_ID=Number(liveJob.id);LIVE_OPTIMIZER_MINIMIZED=false;}
  let job=liveJob||solverJobs.find(j=>Number(j.id)===Number(LIVE_OPTIMIZER_JOB_ID));
  if(!job||LIVE_OPTIMIZER_JOB_ID==null||LIVE_OPTIMIZER_DISMISSED.has(Number(LIVE_OPTIMIZER_JOB_ID))){root.classList.add('hidden');return;}
  const live=job.result?.live||{},processLive=!!live.process_alive,terminal=['succeeded','failed','cancelled'].includes(job.status);if(!processLive&&!terminal){root.classList.add('hidden');return;}
  const clocks=optimizerLiveClocks(job,live,processLive),telemetry=optimizerTelemetry(job,''),best=Number(telemetry.global_best),phase=solverPhaseLabel(telemetry.phase),title=$('#liveOptimizerDockTitle'),bestEl=$('#liveOptimizerDockBest'),phaseEl=$('#liveOptimizerDockPhase'),meta=$('#liveOptimizerDockMeta');
  root.classList.remove('hidden','terminal','failed');root.classList.toggle('minimized',LIVE_OPTIMIZER_MINIMIZED);if(terminal)root.classList.add('terminal');if(job.status==='failed')root.classList.add('failed');
  if(title)title.textContent=processLive?(!clocks.budgetStarted?'Preparing directed travel costs':'Searching for a better route'):job.status==='succeeded'?'Optimization complete':job.status==='cancelled'?'Optimization cancelled':'Optimization stopped';
  if(bestEl)bestEl.textContent=Number.isFinite(best)&&best>0?num(best,2):'—';if(phaseEl)phaseEl.textContent=processLive?phase:localizeStatus(job.status);if(meta)meta.textContent=optimizerCurveMetaText(telemetry,clocks.searchElapsed);renderValidatedBestCurve($('#liveOptimizerDockCurve'),telemetry,clocks.searchElapsed,true);
  const min=$('#liveOptimizerDockMinimize');if(min){min.textContent=LIVE_OPTIMIZER_MINIMIZED?'＋':'−';min.title=LIVE_OPTIMIZER_MINIMIZED?'Expand':'Minimize';min.setAttribute('aria-label',LIVE_OPTIMIZER_MINIMIZED?'Expand live optimizer monitor':'Minimize live optimizer monitor');}
}

function parseSolverLive(text){
  const lines=String(text||'').split(/\r?\n/);
  let native=null,wrapper=null,structured=null;
  for(let i=lines.length-1;i>=0;i--){
    const line=lines[i],isNative=line.includes('[SolverLive]'),isWrapper=line.includes('[FleetRouteProgress]')||line.includes('[FleetRouteProcess]'),isPhase=/\[(PhaseEngine-E32|EliteEvolution|SavingsWarmStart|ClusterWarmStartReceipt|SolverConfig)\]/.test(line);if(!isNative&&!isWrapper&&!isPhase)continue;
    const data={};for(const match of line.matchAll(/([a-z_]+)=([^\s]+)/gi)){const raw=match[2],numeric=Number(raw);data[match[1]]=Number.isFinite(numeric)?numeric:raw;}
    if(isNative&&!native)native=data;
    if(isWrapper&&!wrapper)wrapper=data;
    if(isPhase&&!structured){
      if(line.includes('[EliteEvolution]'))data.phase='solution-refinement';
      else if(line.includes('[SavingsWarmStart]'))data.phase='initial-route-construction';
      else if(line.includes('[ClusterWarmStartReceipt]'))data.phase='validated-warm-start';
      else if(line.includes('[SolverConfig]'))data.phase='optimizer-initialization';
      else if(/transition_to_final_mode/i.test(line))data.phase='final-refinement';
      else if(/\bEND\b/.test(line))data.phase='search-complete';
      else data.phase='adaptive-search';
      if(data.global_best==null&&Number.isFinite(Number(data.best)))data.global_best=Number(data.best);
      if(data.global_best==null&&Number.isFinite(Number(data.obj)))data.global_best=Number(data.obj);
      if(data.elapsed_s==null&&Number.isFinite(Number(data.elapsed)))data.elapsed_s=Number(data.elapsed);
      structured=data;
    }
    if(native&&wrapper&&structured)break;
  }
  const merged={...(wrapper||{}),...(structured||{}),...(native||{})};
  if(!merged.phase&&wrapper)merged.phase=String(wrapper.event||'native-process').toLowerCase();
  return merged;
}
function cachedSolverLive(jobId,text){
  const key=Number(jobId),offset=Number(JOB_LOG_OFFSETS.stderr.get(key)||0),length=String(text||'').length;
  const cached=SOLVER_LIVE_PARSE_CACHE.get(key);
  if(cached&&cached.offset===offset&&cached.length===length)return cached.value;
  const value=parseSolverLive(text);
  SOLVER_LIVE_PARSE_CACHE.set(key,{offset,length,value});
  if(SOLVER_LIVE_PARSE_CACHE.size>24){const first=SOLVER_LIVE_PARSE_CACHE.keys().next().value;SOLVER_LIVE_PARSE_CACHE.delete(first);}
  return value;
}
function solverPhaseLabel(phase){const value=String(phase||'').replaceAll('_',' ').trim();return value?value.replace(/\b\w/g,c=>c.toUpperCase()):(LANG==='th'?'':'Searching');}
function renderOptimizeTrace(job){
  const root=$('#optimizerLiveTrace');if(!root)return;const chip=$('.status-chip',root),runSummary=$('.optimizer-run-summary',root),metrics=$('.optimizer-trace-metrics',root),errPre=$('.optimizer-stderr-text',root),outPre=$('.optimizer-stdout-text',root),note=$('.optimizer-trace-note',root),title=$('#optimizerTraceTitle'),summary=$('#optimizerTraceSummary'),detail=$('#optimizerTraceDetail'),icon=$('#optimizerTraceIcon'),budgetTrack=$('#optimizerBudgetTrack'),budgetBar=$('#optimizerBudgetBar'),budgetLabel=$('#optimizerBudgetLabel');
  runSummary.className='optimizer-run-summary';
  if(!job){const status=routeOperationalState();chip.className=`status-chip ${status.completed?'pass':status.phase==='prepared'?'warn':'idle'}`;chip.textContent=status.completed?'COMPLETE':status.phase==='prepared'?'PREPARED':'READY';metrics.innerHTML='';title.textContent=status.completed?(LANG==='th'?'':'Latest routing run completed'):status.phase==='prepared'?(LANG==='th'?'':'Initial plan ready for the next step'):(LANG==='th'?' Optimizer':'Ready to optimize routes');summary.textContent=status.detail;detail.textContent=LANG==='th'?' Optimizer ':'Start optimization to search for and validate a better route.';icon.textContent=status.icon;budgetTrack.classList.add('hidden');renderValidatedBestCurve($('#optimizerLiveCurve'),{},0,false);const cm=$('#optimizerCurveMeta');if(cm)cm.textContent='Waiting for the first feasible incumbent';renderLogInto(errPre,'The routing engine has not launched yet.');renderLogInto(outPre,'The routing report will be created for the next optimization job.');$('#optimizerStderrBytes').textContent='0 B';$('#optimizerStdoutBytes').textContent='0 B';$('#optimizerStreamSummary').textContent='0 B captured';return;}
  const live=job.result?.live||{},tx=job.result?.transaction||{},isSolver=['solve','network-and-solve'].includes(job.kind),processLive=!!live.process_alive,terminal=['succeeded','failed','cancelled'].includes(job.status);
  const clocks=optimizerLiveClocks(job,live,processLive),processElapsed=clocks.processElapsed,searchElapsed=clocks.searchElapsed,budgetStarted=clocks.budgetStarted,budget=Number(live.budget_s||OPTIMIZER_DRAFT?.solver?.hard_time_limit_s||STATE?.solver?.hard_time_limit_s||0),budgetPct=budget>0&&isSolver&&budgetStarted?Math.min(100,searchElapsed/budget*100):null;
  const err=isSolver?logText(job.id,'stderr'):'',out=isSolver?logText(job.id,'stdout'):'',telemetry=optimizerTelemetry(job,err),phase=solverPhaseLabel(telemetry.phase);const errTail=tailLog(err,18),outTail=tailLog(out,18);
  const failed=job.status==='failed',cancelled=job.status==='cancelled',improved=job.result?.optimizer_improved!==false,routeVersion=job.result?.route_version||latestVersion(),routeCount=job.result?.route_count;
  chip.className=`status-chip ${processLive?'running':job.status==='succeeded'?'pass':failed?'failed':cancelled?'warn':'idle'}`;chip.textContent=processLive?(isSolver&&!budgetStarted?'PREPARING':'SEARCHING'):String(job.status||'WAITING').toUpperCase();
  if(processLive){if(tx.protected_route_version)runSummary.classList.add('protected');const visibleVersion=tx.protected_route_version||routeVersion,isPrep=isSolver&&!budgetStarted;title.textContent=isPrep?(LANG==='th'?'':'Preparing directed road costs'):(LANG==='th'?'Optimizer ':'Optimizer is searching for a better route');summary.textContent=telemetry.phase?(LANG==='th'?` ${phase} · global best ${telemetry.global_best>0?num(telemetry.global_best,2):''}`:`${phase} · global best ${telemetry.global_best>0?num(telemetry.global_best,2):'initializing'}`):(job.message||currentStageLabel(job));detail.textContent=isPrep?(LANG==='th'?` ${processElapsed.toFixed(1)}s · ${budget}s `:`${processElapsed.toFixed(1)}s process elapsed · ${budget?`${budget}s search budget starts after preparation`:'search begins after preparation'}`):(LANG==='th'?` ${searchElapsed.toFixed(1)}s${budget?`  ${budget}s`:''}${visibleVersion?` · Route v${visibleVersion} `:''}`:`${searchElapsed.toFixed(1)}s${budget?` of ${budget}s search budget`:''}${visibleVersion?` · route v${visibleVersion} remains visible during search`:''}`);icon.textContent='◆';}
  else if(job.status==='succeeded'){title.textContent=improved?(LANG==='th'?' · ':'Routing complete · improved result applied'):(LANG==='th'?' · ':'Routing complete · initial plan selected');summary.textContent=routeVersion?(LANG==='th'?`Route v${routeVersion} ${routeCount!=null?` ·  ${routeCount} `:''}`:`Route v${routeVersion} passed validation${routeCount!=null?` · ${routeCount} active trucks`:''}`):(job.message||'Completed');detail.textContent=improved?(LANG==='th'?'Optimizer ':'The optimizer selected an improved result and validation passed.'):(LANG==='th'?'Optimizer   Objective ':'The optimizer completed its checks; the initial plan was selected because the objective did not improve.');icon.textContent='✓';}
  else if(failed||cancelled){const preserved=!!(tx.route_preserved||tx.evidence_preserved),kept=tx.retained_route_version||tx.protected_route_version||routeVersion,currentStatus=routeOperationalState();if(preserved)runSummary.classList.add('protected');title.textContent=cancelled?(LANG==='th'?' Optimizer ':'Optimizer cancelled'):(LANG==='th'?'Optimizer ':'Optimizer stopped — review required');summary.textContent=preserved&&kept?(currentStatus.completed?(LANG==='th'?`Route v${kept} `:`Route v${kept} remains ready.`):(LANG==='th'?`Route v${kept} `:`Route v${kept} remains an initial plan.`)):friendlyError(job.message);detail.textContent=preserved?(LANG==='th'?'':'This attempt did not change the current fleet plan.'):(LANG==='th'?'':'See Evidence & logs for details.');icon.textContent=preserved?'↺':'!';}
  else{title.textContent=LANG==='th'?'':'Preparing inputs and an initial plan';summary.textContent=job.message||currentStageLabel(job);detail.textContent=LANG==='th'?' Directed Graph  Solver input':'Checking the directed graph and preparing solver input.';icon.textContent='…';}
  const bestValue=telemetry.global_best>0?num(telemetry.global_best,2):'—',remainingValue=telemetry.remaining_s>=0?`${num(telemetry.remaining_s,1)}s`:(budgetPct==null?'—':`${num(Math.max(0,budget-searchElapsed),1)}s`);
  metrics.innerHTML=`<span><small>Job</small><b>#${job.id}</b></span><span><small>Stage</small><b>${esc(job.stage_label||'—')}</b></span><span><small>${processLive?'Phase':'Status'}</small><b>${esc(processLive?phase:localizeStatus(job.status))}</b></span><span><small>Elapsed</small><b>${processElapsed?`${processElapsed.toFixed(1)}s`:'—'}</b></span><span><small>${processLive?'Global best':'Route'}</small><b>${processLive?bestValue:(routeVersion?`v${routeVersion}`:'—')}</b></span><span><small>${processLive?'Remaining':'Active trucks'}</small><b>${processLive?remainingValue:(routeCount??'—')}</b></span>`;
  renderValidatedBestCurve($('#optimizerLiveCurve'),telemetry,searchElapsed,false);const curveMeta=$('#optimizerCurveMeta');if(curveMeta)curveMeta.textContent=optimizerCurveMetaText(telemetry,searchElapsed);
  budgetTrack.classList.toggle('hidden',budgetPct==null||terminal||!isSolver);if(budgetPct!=null){budgetBar.style.width=`${budgetPct}%`;budgetLabel.textContent=`${budgetPct.toFixed(1)}% · ${searchElapsed.toFixed(1)} / ${budget}s search`;}
  if(errTail)renderLogInto(errPre,errTail);else if(isSolver&&processLive)renderLogInto(errPre,'routing process is alive; waiting for the next cerr/stderr telemetry line…');else if(isSolver&&terminal)renderLogInto(errPre,'ERROR: No stderr/cerr captured for this solver job. Open Evidence & Logs — this violates the process evidence contract.');else renderLogInto(errPre,'Pipeline has not reached routing yet.');
  if(outTail)renderLogInto(outPre,outTail);else if(isSolver&&processLive)renderLogInto(outPre,'stdout is intentionally quiet during search. Final route/report will appear here when routing exits.');else if(isSolver&&terminal)renderLogInto(outPre,'ERROR: No stdout captured after solver exit. Open Evidence & Logs — final solver output should exist.');else renderLogInto(outPre,'No routing output yet.');
  const errBytes=Number(JOB_LOG_OFFSETS.stderr.get(job.id)||0),outBytes=Number(JOB_LOG_OFFSETS.stdout.get(job.id)||0),eb=$('#optimizerStderrBytes'),ob=$('#optimizerStdoutBytes');if(eb)eb.textContent=humanBytes(errBytes);if(ob)ob.textContent=humanBytes(outBytes);$('#optimizerStreamSummary').textContent=`${humanBytes(errBytes+outBytes)} captured`;
  note.textContent=terminal&&isSolver?'Process finished: final tails were fetched after exit. Full separate files remain in Evidence & Logs / Data & Runtime.':'The two streams remain independent; Combined Raw uses backend reader-arrival order and does not claim authoritative cross-stream timing.';
}

function handleDelegatedUiAction(event){
  const target=event.target.closest?.('[data-ui-action]');
  if(!target)return false;
  const action=target.dataset.uiAction;
  const intValue=(name)=>{const value=Number.parseInt(target.dataset[name]||'',10);return Number.isFinite(value)?value:null;};
  if(action==='route-link'){return true;}
  if(action==='focus-place'){const id=intValue('placeId');if(id!=null)focusPlace(id);return true;}
  if(action==='edit-place'){const id=intValue('placeId');if(id!=null)editPlace(id);return true;}
  if(action==='delete-place'){const id=intValue('placeId');if(id!=null)deletePlace(id);return true;}
  if(action==='focus-truck'){const id=intValue('truckId');if(id!=null)focusTruck(id);return true;}
  if(action==='copy-driver-link'){const id=intValue('truckId');if(id!=null)copyDriverLink(id);return true;}
  if(action==='save-route-svg'){const id=intValue('truckId');if(id!=null)saveRouteSvg(id);return true;}
  if(action==='select-job'){const id=intValue('jobId');if(id!=null)selectJob(id);return true;}
  if(action==='cancel-job'){const id=intValue('jobId');if(id!=null)cancelJob(id);return true;}
  if(action==='show-search-result'){const index=intValue('searchIndex');if(index!=null)showSearchResult(index);return true;}
  if(action==='use-search-depot'){const index=intValue('searchIndex');if(index!=null)quickSetDepotFromSearch(index);return true;}
  if(action==='prepare-search-customer'){const index=intValue('searchIndex');if(index!=null)prepareSearchResult(index,'customer');return true;}
  if(action==='closure-decision'){const id=intValue('closureId');if(id!=null)decideClosure(id,target.dataset.approve==='true');return true;}
  if(action==='closure-reopen'){const id=intValue('closureId');if(id!=null)reopenClosure(id);return true;}
  if(action==='quick-region'){const id=target.dataset.regionId;if(id)chooseOperatingRegion(id,{fit:true});return true;}
  return false;
}
function bindDelegatedUiActions(){
  if(DELEGATED_UI_BOUND)return;
  DELEGATED_UI_BOUND=true;
  document.addEventListener('click',event=>{handleDelegatedUiAction(event);});
  document.addEventListener('keydown',event=>{
    if(event.key!=='Enter'&&event.key!==' ')return;
    // Nested links/buttons keep their native keyboard activation. Only the
    // non-native card itself needs Enter/Space synthesized as a click action.
    if(event.target.closest?.('button,a,input,select,textarea,summary'))return;
    const target=event.target.closest?.('[data-ui-action][role="button"]');
    if(!target||target.tagName==='BUTTON'||target.tagName==='A')return;
    event.preventDefault();
    handleDelegatedUiAction(event);
  });
}

function bindV14(){
  bindDelegatedUiActions();
  $('#heroDemoBtn').onclick=startCompleteDemo;$('#planDemoBtn').onclick=startCompleteDemo;$('#rushModeBtn').onclick=openRushModal;
  $('#retryConnectionBtn').onclick=()=>refresh(false,true);
  $('#searchQuery').addEventListener('input',e=>$('#clearSearchBtn').classList.toggle('hidden',!e.target.value));$('#clearSearchBtn').onclick=clearSearchUI;
  $('#mapDepotBtn').onclick=()=>{mapPickRole='depot';mapAddMode=true;updateMapMode();toast(LANG==='th'?' Depot':'Depot pick mode',LANG==='th'?'':'Click the real location on the map');};
  $('#mapAddBtn').onclick=()=>{mapPickRole='customer';const depot=(STATE.places||[]).find(p=>p.role==='depot');if(!depot){toast(LANG==='th'?' Depot ':'Choose a depot first',LANG==='th'?' “ Depot ” ':'Use “Pick depot from map” or a search result.',true);return;}mapAddMode=true;updateMapMode();toast(LANG==='th'?'':'Work-point pick mode',LANG==='th'?'':'Click the real location on the map');};
  $('#testSelectedClusterBtn').onclick=runSelectedClustering;$('#saveClusterPolicyBtn').onclick=saveClusterPolicy;
  $('#validateSolverCommandBtn').onclick=validateSolverCommand;
  $('#openConsoleBtn').onclick=()=>setConsoleOpen(true);$('#closeConsoleBtn').onclick=()=>setConsoleOpen(false);
  $('#followConsoleBtn').onclick=()=>setConsoleFollow(!CONSOLE_FOLLOW);
  $('#wrapConsoleBtn').onclick=()=>setConsoleWrap(!CONSOLE_WRAP);
  $('#jobLog').addEventListener('scroll',()=>{const pre=$('#jobLog'),nearBottom=pre.scrollHeight-pre.scrollTop-pre.clientHeight<28;if(nearBottom!==CONSOLE_FOLLOW)setConsoleFollow(nearBottom,false);},{passive:true});
  $('#copyConsoleBtn').onclick=async()=>{const text=logText(selectedJobId,JOB_LOG_SOURCE);if(!text.trim()){toast(LANG==='th'?'':'Nothing to copy',LANG==='th'?' stream  job ':'Choose another stream or wait for the job to start.');return;}try{await navigator.clipboard.writeText(text);toast(LANG==='th'?' Console ':'Console copied');}catch{prompt('Copy console',text);}};
  $('#logSourceRawBtn').onclick=()=>selectLogSource('raw');$('#logSourceStdoutBtn').onclick=()=>selectLogSource('stdout');$('#logSourceStderrBtn').onclick=()=>selectLogSource('stderr');$('#logSourceAuditBtn').onclick=()=>selectLogSource('audit');
  $('#devRefreshBtn').onclick=()=>loadDeveloper(true);$('#devLoadMoreBtn').onclick=()=>DEV_FILE_KEY&&selectDeveloperFile(DEV_FILE_KEY,false);
  $('#devCopyCommandBtn').onclick=async()=>{const text=$('#devCommand').textContent||'';try{await navigator.clipboard.writeText(text);toast(LANG==='th'?'':'Command copied');}catch{prompt('Copy command',text);}};
  $('#devCopyFileBtn').onclick=async()=>{try{await navigator.clipboard.writeText(DEV_FILE_TEXT||'');toast(LANG==='th'?'':'File content copied');}catch{prompt('Copy file',DEV_FILE_TEXT||'');}};
  $$('[data-close-rush]').forEach(b=>b.onclick=closeRushModal);$('#rushModal').onclick=e=>{if(e.target.id==='rushModal')closeRushModal();};$('#rushCsvInput').onchange=e=>{if(e.target.files?.[0])inspectRushFile(e.target.files[0]);};$('#rushUseDepot').onchange=()=>{if($('#rushCsvInput').files?.[0])inspectRushFile($('#rushCsvInput').files[0]);};$('#runRushBtn').onclick=runRushWorkflow;
  $('#resultModal').onclick=e=>{if(e.target.id==='resultModal')dismissDialog($('#resultModal'));};
  document.addEventListener('keydown',e=>{
    const dialog=$$('.modal-backdrop,.lightbox').find(item=>!item.classList.contains('hidden'));
    if(e.key==='Tab'&&dialog){const focusable=$$('button:not([disabled]),a[href],input:not([disabled]),select:not([disabled]),textarea:not([disabled]),summary,[tabindex]:not([tabindex="-1"])',dialog).filter(item=>item.offsetParent!==null);if(focusable.length){const first=focusable[0],last=focusable.at(-1);if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}}return;}
    if(e.key!=='Escape')return;if($('#appShell').classList.contains('menu-open')){setMenuOpen(false);$('#mobileMenuBtn').focus();return;}if(CONSOLE_OPEN){setConsoleOpen(false);return;}if(!$('#distanceRiskModal').classList.contains('hidden')){closeDistanceRisk(false);return;}if(!$('#resultModal').classList.contains('hidden')){dismissDialog($('#resultModal'));return;}if(!$('#rushModal').classList.contains('hidden')){closeRushModal();return;}if(!$('#closureModal').classList.contains('hidden')){closeClosureModal();return;}if(!$('#placeModal').classList.contains('hidden')){closePlaceModal();return;}if(!$('#imageLightbox').classList.contains('hidden'))dismissDialog($('#imageLightbox'));
  });
}


function regionProps(feature){return feature?.properties||{};}
function regionFeature(id){return (REGION_CATALOG?.features||[]).find(f=>regionProps(f).id===id)||null;}
function regionLabel(feature){const p=regionProps(feature);return p.name||p.id||'Unknown region';}
function regionParentLabel(feature){const p=regionProps(feature);const parent=regionFeature(p.parent);return parent?regionLabel(parent):(p.parent||'Geofabrik');}
function regionIso(feature){return (regionProps(feature).iso2||[]).join(' / ');}
function allRegionChildren(regionId){
  return (REGION_CATALOG?.features||[]).filter(f=>regionProps(f).parent===regionId).sort((a,b)=>regionLabel(a).localeCompare(regionLabel(b)));
}
function regionDescendants(regionId,{downloadableOnly=false}={}){
  const out=[],queue=[...allRegionChildren(regionId)],seen=new Set();
  while(queue.length){
    const feature=queue.shift(),id=regionProps(feature).id;if(!id||seen.has(id))continue;seen.add(id);
    if(!downloadableOnly||regionProps(feature).pbf_url)out.push(feature);
    queue.push(...allRegionChildren(id));
  }
  return out;
}
function nearestDownloadableDescendants(regionId){
  const found=[],queue=[...allRegionChildren(regionId)],seen=new Set();
  while(queue.length){
    const feature=queue.shift(),id=regionProps(feature).id;if(!id||seen.has(id))continue;seen.add(id);
    if(regionProps(feature).pbf_url){found.push(feature);continue;}
    queue.push(...allRegionChildren(id));
  }
  return found.sort((a,b)=>regionLabel(a).localeCompare(regionLabel(b)));
}
function nearestGeometryDescendants(regionId){
  const found=[],queue=[...allRegionChildren(regionId)],seen=new Set();
  while(queue.length){
    const feature=queue.shift(),id=regionProps(feature).id;if(!id||seen.has(id))continue;seen.add(id);
    if(feature.geometry){found.push(feature);continue;}
    queue.push(...allRegionChildren(id));
  }
  return found.sort((a,b)=>regionLabel(a).localeCompare(regionLabel(b)));
}
function regionAncestry(feature){
  const labels=[],seen=new Set();let current=feature;
  while(current){const p=regionProps(current);if(!p.id||seen.has(p.id))break;seen.add(p.id);labels.unshift(regionLabel(current));current=p.parent?regionFeature(p.parent):null;}
  return labels;
}
function worldRegionFeatures(){
  const all=REGION_CATALOG?.features||[];
  if(REGION_MAP_SCOPE){
    const children=nearestGeometryDescendants(REGION_MAP_SCOPE);
    if(children.length)return children;
  }
  const countries=all.filter(f=>f.geometry&&(regionProps(f).iso2||[]).length);
  return countries.length?countries:all.filter(f=>f.geometry&&!regionProps(f).parent);
}
function normalizeRegionText(value){return String(value||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/[^a-z0-9]+/g,' ').trim();}
function updateRegionMapBack(){
  const back=$('#regionMapBack');if(!back)return;
  if(!REGION_MAP_SCOPE){back.classList.add('hidden');return;}
  const current=regionFeature(REGION_MAP_SCOPE),parent=current?regionFeature(regionProps(current).parent):null;
  back.classList.remove('hidden');
  back.textContent=`← ${parent?regionLabel(parent):'World'} · ${current?regionLabel(current):REGION_MAP_SCOPE}`;
}
function enterRegionScope(regionId){
  const children=nearestGeometryDescendants(regionId);
  if(!children.length)return false;
  REGION_MAP_SCOPE=regionId;drawRegionCatalog();updateRegionMapBack();fitRegionFeature(regionId);
  return true;
}
function leaveRegionScope(){
  if(!REGION_MAP_SCOPE)return;
  const current=regionFeature(REGION_MAP_SCOPE),parent=current?regionFeature(regionProps(current).parent):null;
  if(parent&&nearestGeometryDescendants(regionProps(parent).id).length){
    REGION_MAP_SCOPE=regionProps(parent).id;drawRegionCatalog();updateRegionMapBack();fitRegionFeature(REGION_MAP_SCOPE);return;
  }
  REGION_MAP_SCOPE=null;drawRegionCatalog();updateRegionMapBack();regionMap?.setView([18,5],2,{animate:motionBehavior()==='smooth'});
}
function regionMapStyle(feature){
  const id=regionProps(feature).id;
  const browsed=browsedRegion()?.id===id;
  const active=STATE?.osm_source?.ready&&activeRegion()?.id===id;
  const searched=REGION_SEARCH_IDS.has(id);
  const cached=REGION_LIBRARY.some(item=>item.ready&&item.id===id);
  if(browsed)return {color:'#087b70',weight:3.2,opacity:1,fillColor:'#28ad9a',fillOpacity:.31};
  if(active)return {color:'#0b5363',weight:2.45,opacity:1,fillColor:'#4b9ba1',fillOpacity:.18,dashArray:'8 4'};
  if(searched)return {color:'#246aa5',weight:2.35,opacity:.98,fillColor:'#67b7df',fillOpacity:.22};
  if(cached)return {color:'#168f81',weight:1.65,opacity:.9,fillColor:'#69c5b7',fillOpacity:.16,dashArray:'6 4'};
  return {color:'#678e94',weight:.82,opacity:.62,fillColor:'#94b8b7',fillOpacity:.07};
}
function positionRegionHover(ev,feature){
  const card=$('#regionHoverCard'),stage=$('.region-map-stage');if(!card||!stage)return;
  const box=stage.getBoundingClientRect(),oe=ev?.originalEvent;let x=oe?.clientX-box.left+14,y=oe?.clientY-box.top+14;
  if(!Number.isFinite(x)){x=18;y=18;}
  x=Math.min(Math.max(10,x),Math.max(10,box.width-270));y=Math.min(Math.max(10,y),Math.max(10,box.height-85));
  card.style.left=`${x}px`;card.style.top=`${y}px`;card.classList.remove('hidden');
  const p=regionProps(feature),children=nearestDownloadableDescendants(p.id),cached=REGION_LIBRARY.some(item=>item.ready&&item.id===p.id);
  const availability=cached?'Verified locally':p.pbf_url?'Direct download':children.length?`${children.length} downloadable subregions`:'Catalog region';
  $('b',card).textContent=regionLabel(feature);$('small',card).textContent=[regionIso(feature),availability,'Click to select'].filter(Boolean).join(' · ');
}
function hideRegionHover(){const card=$('#regionHoverCard');if(card)card.classList.add('hidden');}
function regionFeatureKind(feature){
  const p=regionProps(feature);
  if(p.pbf_url&&p.parent)return 'EXTRACT';
  if((p.iso2||[]).length)return p.pbf_url?'COUNTRY':'COUNTRY · SUBREGIONS';
  return p.pbf_url?'REGION':'PARENT REGION';
}
function renderRegionDiscovery(){
  const quick=$('#regionQuickAccess'),summary=$('#regionCatalogSummary');
  if(!REGION_CATALOG){if(summary)$('span',summary).textContent='Regional catalog unavailable';return;}
  const all=REGION_CATALOG.features||[],downloadable=all.filter(f=>regionProps(f).pbf_url),countries=all.filter(f=>(regionProps(f).iso2||[]).length&&f.geometry),audit=REGION_CATALOG.audit||{},rejected=Number(audit.rejected_pbf_urls||0);
  if(summary){
    summary.classList.remove('loading');summary.classList.toggle('offline',!all.length||rejected>0);
    $('span',summary).textContent=rejected?`${countries.length} countries · ${downloadable.length} extracts · ${rejected} source link${rejected===1?'':'s'} rejected`:`${countries.length} countries · ${downloadable.length} downloadable extracts`;
    summary.title=rejected?'The live catalog contains road-source links that failed FleetRoute security validation. Refresh the catalog or review the source audit before downloading.':'Every exposed road-source URL passed FleetRoute catalog validation.';
  }
  if(!quick)return;
  const preferred=['TH','SG','JP','AU','GB','DE','FR','US'];
  const chosen=[];
  for(const code of preferred){
    const feature=countries.find(f=>(regionProps(f).iso2||[]).map(x=>String(x).toUpperCase()).includes(code));
    if(feature&&!chosen.some(x=>regionProps(x).id===regionProps(feature).id))chosen.push(feature);
  }
  if(chosen.length<6){for(const feature of countries.slice().sort((a,b)=>regionLabel(a).localeCompare(regionLabel(b)))){if(chosen.length>=8)break;if(!chosen.some(x=>regionProps(x).id===regionProps(feature).id))chosen.push(feature);}}
  quick.innerHTML=chosen.map(f=>{const p=regionProps(f),cached=REGION_LIBRARY.some(item=>item.ready&&item.id===p.id),selected=browsedRegion()?.id===p.id;const active=STATE?.osm_source?.ready&&activeRegion()?.id===p.id;return `<button type="button" class="region-quick-chip ${cached?'cached':''} ${active?'active-source':''} ${selected?'selected':''}" aria-pressed="${selected?'true':'false'}" data-ui-action="quick-region" data-region-id="${esc(p.id)}"><span>${esc(regionIso(f)||regionLabel(f).slice(0,2).toUpperCase())}</span><b>${esc(regionLabel(f))}</b>${active?'<em title="Active road source">ACTIVE</em>':cached?'<i title="Verified locally"></i>':''}</button>`;}).join('');
}
function drawRegionCatalog(){
  if(!regionMap||!REGION_CATALOG)return;
  if(REGION_MAP_LAYER){REGION_MAP_LAYER.remove();REGION_MAP_LAYER=null;}
  REGION_MAP_LAYER=L.geoJSON({type:'FeatureCollection',features:worldRegionFeatures()},{
    style:regionMapStyle,
    onEachFeature:(feature,layer)=>{
      layer.on({
        mouseover:e=>{layer.setStyle({color:'#0c8c7f',weight:1.8,fillColor:'#26aa98',fillOpacity:.22});layer.bringToFront();positionRegionHover(e,feature);},
        mousemove:e=>positionRegionHover(e,feature),
        mouseout:()=>{REGION_MAP_LAYER?.resetStyle(layer);hideRegionHover();},
        click:async()=>{const p=regionProps(feature),id=p.id,children=nearestDownloadableDescendants(id);if(!p.pbf_url&&children.length){enterRegionScope(id);toast('Choose a smaller extract',`${regionLabel(feature)} is provided through ${children.length} downloadable subregions.`);return;}await chooseOperatingRegion(id,{fit:true});enterRegionScope(id);},
      });
    }
  }).addTo(regionMap);
  populateRegionFallback();
  renderRegionDiscovery();
}
function populateRegionFallback(){
  const select=$('#regionFallbackSelect');if(!select||!REGION_CATALOG)return;
  const options=(REGION_CATALOG.features||[]).filter(f=>regionProps(f).pbf_url).slice().sort((a,b)=>regionLabel(a).localeCompare(regionLabel(b)));
  select.innerHTML='<option value="">Choose an extract…</option>'+options.map(f=>`<option value="${esc(regionProps(f).id)}">${esc(regionLabel(f))}${regionParentLabel(f)?` — ${esc(regionParentLabel(f))}`:''}</option>`).join('');
}
function directRegionChildren(regionId){
  return allRegionChildren(regionId).filter(f=>regionProps(f).pbf_url);
}
function renderRegionChildren(regionId){
  const wrap=$('#regionChildrenWrap'),grid=$('#regionChildren');if(!wrap||!grid)return;
  let children=allRegionChildren(regionId);
  if(!children.length)children=nearestDownloadableDescendants(regionId);
  wrap.classList.toggle('hidden',!children.length);
  grid.innerHTML=children.slice(0,80).map(f=>{const p=regionProps(f),nested=!p.pbf_url&&nearestDownloadableDescendants(p.id).length;return `<button type="button" class="region-child ${nested?'drilldown':''}" data-region-child="${esc(p.id)}"><b>${esc(regionLabel(f))}</b><small>${esc(regionIso(f)||p.id)} · ${p.pbf_url?'download':`${nearestDownloadableDescendants(p.id).length} extracts →`}</small></button>`;}).join('');
  $$('[data-region-child]',grid).forEach(btn=>btn.onclick=()=>chooseOperatingRegion(btn.dataset.regionChild,{fit:true}));
}
function libraryEntry(id){return REGION_LIBRARY.find(item=>item.id===id)||null;}
function renderRegionLibrary(){
  const boxes=[$('#regionLibrary'),$('#regionLibraryQuick')].filter(Boolean);if(!boxes.length)return;
  const ready=REGION_LIBRARY.filter(item=>item.ready);
  const html=ready.length?ready.map(item=>`<div class="region-library-item"><div><b>${esc(item.name)}</b><small>${esc(item.size_human||'Cached road source')} · checksum ${esc(String(item.verified_md5||'').slice(0,8))}…</small></div><button type="button" data-library-region="${esc(item.id)}">Use</button></div>`).join(''):'<div class="region-library-empty">No verified regional source is available locally yet.</div>';
  boxes.forEach(box=>{box.innerHTML=html;});
  $('#regionLibraryQuickWrap')?.classList.toggle('hidden',!ready.length);
  $$('[data-library-region]').forEach(btn=>btn.onclick=()=>chooseOperatingRegion(btn.dataset.libraryRegion,{fit:true,collapseIfReady:true}));
  renderRegionDiscovery();
  if(REGION_MAP_LAYER)REGION_MAP_LAYER.setStyle(regionMapStyle);
}
async function loadRegionLibrary(){
  try{const data=await api('/api/osm/library',{timeoutMs:12000});REGION_LIBRARY=data.items||[];renderRegionLibrary();}catch{REGION_LIBRARY=[];renderRegionLibrary();}
}
function fitRegionFeature(regionId){
  const feature=regionFeature(regionId);if(!feature?.geometry||!regionMap)return;
  try{const layer=L.geoJSON(feature);const bounds=layer.getBounds();if(bounds.isValid())regionMap.fitBounds(bounds,{padding:[28,28],maxZoom:6,animate:motionBehavior()==='smooth'});}catch{}
}
async function chooseOperatingRegion(regionId,{fit=true,collapseIfReady=false,announce=true}={}){
  if(!regionId)return null;
  const feature=regionFeature(regionId);const name=feature?regionLabel(feature):regionId;
  if(feature&&!regionProps(feature).pbf_url){const children=nearestDownloadableDescendants(regionId);if(children.length){enterRegionScope(regionId);if(announce)toast('Choose a smaller extract',`${name} has no single country-level road download; choose one of ${children.length} downloadable extracts below it.`);return null;}if(announce)toast('No downloadable road extract',`${name} is present in the catalog but no downloadable Geofabrik road extract exists below it.`,true);return null;}
  try{
    $('#selectedRegionStatus').className='status-chip running';$('#selectedRegionStatus').textContent='Selecting';
    const status=await api('/api/osm/region',{method:'POST',body:JSON.stringify({region_id:regionId}),timeoutMs:25000});
    // Apply the successful browser target immediately so map/Quick Access state
    // cannot visually disappear while the subsequent full-state refresh runs.
    if(STATE)STATE.osm_browse=status;
    REGION_SEARCH_IDS=new Set([regionId]);
    if(fit)fitRegionFeature(regionId);
    if(REGION_MAP_LAYER)REGION_MAP_LAYER.setStyle(regionMapStyle);
    REGION_FORCE_OPEN=!collapseIfReady;
    await Promise.all([loadRegionLibrary(),refresh(true,false)]);
    renderRegionSourceDrawer(STATE?.osm_browse||status);
    drawRegionCatalog();
    const activeSame=STATE?.osm_source?.ready&&activeRegion()?.id===regionId;
    if(announce)toast(activeSame?'Active road source':'Region selected',activeSame?`${name} is already backing the operating graph.`:`${name} · ${status.ready?'verified locally; choose Use to activate':'not downloaded yet'}`);
    fitPlanRegionContext(true);fitRoadsRegionContext(true);
    return STATE?.osm_browse||status;
  }catch(e){if(announce)toast('Region selection failed',e.message,true);return null;}
}
function renderRegionSourceDrawer(target=STATE?.osm_browse||{}){
  const region=target.region||null,empty=$('#regionDrawerEmpty'),content=$('#regionDrawerContent');if(!empty||!content)return;
  empty.classList.toggle('hidden',!!region);content.classList.toggle('hidden',!region);if(!region)return;
  const active=STATE?.osm_source||{},activeRegionValue=active.region||null;
  const activeSame=!!active.ready&&activeRegionValue?.id===region.id;
  $('#selectedRegionName').textContent=region.name||region.id;const selectedFeature=regionFeature(region.id),trail=selectedFeature?regionAncestry(selectedFeature).join(' › '):region.parent;$('#selectedRegionMeta').textContent=[(region.iso2||[]).join(' / '),trail,region.id].filter(Boolean).join(' · ');
  const chip=$('#selectedRegionStatus');chip.className=`status-chip ${activeSame?'succeeded':target.ready?'pass':'idle'}`;chip.textContent=activeSame?'Active roads':target.ready?'Verified cache':'Not cached';
  const activeNotice=$('#activeRegionNotice');
  const doneButton=$('#regionSetupDoneBtn');
  if(doneButton){const canDone=activeSourceOperational();doneButton.classList.toggle('hidden',!canDone);doneButton.disabled=!canDone;doneButton.textContent=canDone?`Done · keep ${activeRegionValue?.name||activeRegionValue?.id||'active source'}`:'Done';}
  if(activeNotice){
    activeNotice.classList.toggle('warning',!!active.ready&&!activeSourceOperational());
    activeNotice.innerHTML=active.ready
      ? `<span>ACTIVE ROAD SOURCE</span><b>${esc(activeRegionValue?.name||activeRegionValue?.id||'Verified source')}</b><small>${activeSourceOperational()?'Backing the current operating graph':`Does not cover the current depot/plan · choose a matching source before road preparation`}</small>`
      : `<span>ACTIVE ROAD SOURCE</span><b>None yet</b><small>Download a region, then use it for the current plan.</small>`;
  }
  $('#recommendedSourceName').textContent=activeSame?'Current active road source':target.ready?'Verified local source':`${region.name} · Geofabrik road extract`;
  $('#recommendedSourceMeta').textContent=target.ready?`${target.size_human||''} · checksum ${String(target.verified_md5||'').slice(0,10)}…`:'Official OpenStreetMap extract · checksum verified before use';
  const button=$('#useRecommendedSourceBtn');const downloading=!!activeSourceDownload();button.disabled=downloading||activeSame;button.textContent=activeSame?'Active source':downloading?'Downloading…':target.ready?'Use verified source':'Download & verify';
  renderRegionChildren(region.id);renderRegionLibrary();
}
function activeSourceDownload(){return (STATE?.jobs||[]).find(j=>j.kind==='osm-source-download'&&['queued','running'].includes(j.status));}
function renderRegionSetup(){
  const setup=$('#regionSetup');if(!setup)return;
  const source=STATE?.osm_source||{},ready=activeSourceOperational(),region=source.region||null;
  if(source.ready&&!ready)REGION_FORCE_OPEN=true;
  if(ready&&REGION_COLLAPSE_ON_READY){REGION_FORCE_OPEN=false;REGION_COLLAPSE_ON_READY=false;}
  setup.classList.toggle('complete',ready&&!REGION_FORCE_OPEN);
  document.body.classList.toggle('region-onboarding-active',!ready||REGION_FORCE_OPEN);
  if(region){$('#collapsedRegionName').textContent=region.name||region.id;$('#collapsedRegionMeta').textContent=`Verified regional road source · ${source.size_human||''}`;}
  renderRegionSourceDrawer(STATE?.osm_browse||{});
  if(REGION_MAP_LAYER)REGION_MAP_LAYER.setStyle(regionMapStyle);
  setTimeout(()=>regionMap?.invalidateSize({pan:false,animate:false}),60);
}
function regionSearchMatches(query){
  const q=String(query||'').trim().toLowerCase();if(!q||!REGION_CATALOG)return[];
  return (REGION_CATALOG.features||[]).map(f=>{
    const p=regionProps(f),name=String(p.name||''),id=String(p.id||''),iso=(p.iso2||[]).join(' '),parent=String(p.parent||'');
    const hay=`${name} ${id} ${iso} ${parent}`.toLowerCase();let score=0;if(name.toLowerCase()===q||id===q||iso.toLowerCase()===q)score=100;else if(name.toLowerCase().startsWith(q))score=80;else if(hay.includes(q))score=50;return {f,score};
  }).filter(x=>x.score).sort((a,b)=>b.score-a.score||regionLabel(a.f).localeCompare(regionLabel(b.f))).slice(0,10).map(x=>x.f);
}
function renderRegionSearch(){
  const input=$('#regionSearch'),box=$('#regionSearchResults');if(!input||!box)return;const matches=regionSearchMatches(input.value);REGION_SEARCH_ACTIVE=-1;
  REGION_SEARCH_IDS=new Set(matches.map(f=>regionProps(f).id));if(REGION_MAP_LAYER)REGION_MAP_LAYER.setStyle(regionMapStyle);
  box.classList.toggle('hidden',!matches.length);input.setAttribute('aria-expanded',String(!!matches.length));input.removeAttribute('aria-activedescendant');
  box.innerHTML=matches.map((f,index)=>{const p=regionProps(f),cached=REGION_LIBRARY.some(item=>item.ready&&item.id===p.id),selected=browsedRegion()?.id===p.id;return `<button type="button" role="option" aria-selected="${selected?'true':'false'}" id="region-result-${index}" class="region-search-item ${cached?'cached':''} ${selected?'selected':''}" data-region-result="${esc(p.id)}"><div><b>${esc(regionLabel(f))}</b><small>${esc([regionParentLabel(f),p.id].filter(Boolean).join(' · '))}</small></div><span class="region-result-badges"><em>${esc(regionIso(f)||regionFeatureKind(f))}</em><small>${esc(selected?'SELECTED':cached?'VERIFIED':regionFeatureKind(f))}</small></span></button>`;}).join('');
  $$('[data-region-result]',box).forEach(btn=>btn.onclick=()=>{input.value=btn.querySelector('b')?.textContent||'';box.classList.add('hidden');input.setAttribute('aria-expanded','false');input.removeAttribute('aria-activedescendant');REGION_SEARCH_IDS=new Set([btn.dataset.regionResult]);if(REGION_MAP_LAYER)REGION_MAP_LAYER.setStyle(regionMapStyle);chooseOperatingRegion(btn.dataset.regionResult,{fit:true});});
}
function moveRegionSearchSelection(delta){
  const input=$('#regionSearch'),box=$('#regionSearchResults'),items=$$('[data-region-result]',box);if(!input||!items.length)return false;
  REGION_SEARCH_ACTIVE=(REGION_SEARCH_ACTIVE+delta+items.length)%items.length;
  items.forEach((item,index)=>{const active=index===REGION_SEARCH_ACTIVE;item.classList.toggle('active',active);item.setAttribute('aria-selected',String(active));if(active){input.setAttribute('aria-activedescendant',item.id);item.scrollIntoView({block:'nearest'});}});
  return true;
}
async function resolveRegionSearch(query){
  const direct=regionSearchMatches(query);if(direct.length){await chooseOperatingRegion(regionProps(direct[0]).id,{fit:true});return true;}
  const q=String(query||'').trim();if(q.length<3)return false;
  try{
    const geo=await api(`/api/geocode?q=${encodeURIComponent(q)}&limit=3`,{timeoutMs:18000});
    const hit=(geo.results||[]).find(item=>item.country_code);if(!hit)return false;
    const code=String(hit.country_code||'').toUpperCase();
    const country=(REGION_CATALOG?.features||[]).find(f=>(regionProps(f).iso2||[]).map(x=>String(x).toUpperCase()).includes(code));
    if(!country)return false;
    let best=country;
    const children=regionDescendants(regionProps(country).id);
    const stateKey=normalizeRegionText(hit.state);
    if(stateKey&&children.length){
      const exact=children.find(f=>normalizeRegionText(regionLabel(f))===stateKey);
      const fuzzy=children.find(f=>normalizeRegionText(regionLabel(f)).includes(stateKey)||stateKey.includes(normalizeRegionText(regionLabel(f))));
      best=exact||fuzzy||country;
    }
    $('#regionSearch').value=hit.name||hit.state||hit.country||regionLabel(best);
    if(!regionProps(best).pbf_url&&nearestDownloadableDescendants(regionProps(best).id).length){enterRegionScope(regionProps(best).id);toast('Location resolved',`${hit.display_name||q} → choose a downloadable extract below ${regionLabel(best)}`);return true;}
    await chooseOperatingRegion(regionProps(best).id,{fit:true});
    if(best===country)enterRegionScope(regionProps(country).id);
    toast('Location resolved',`${hit.display_name||q} → ${regionLabel(best)}`);
    return true;
  }catch(e){toast('Region search unavailable',e.message,true);return false;}
}
async function downloadSelectedRegion(){
  const target=STATE?.osm_browse||{},region=target.region||null;
  if(!region){toast('Choose a region first','Move across the map or use search.',true);return;}
  const activeSame=STATE?.osm_source?.ready&&activeRegion()?.id===region.id;
  if(activeSame){REGION_FORCE_OPEN=false;renderRegionSetup();return;}
  if(target.ready){
    try{
      const status=await api('/api/osm/activate',{method:'POST',body:JSON.stringify({region_id:region.id}),timeoutMs:25000});
      if(STATE)STATE.osm_source=status;
      REGION_COLLAPSE_ON_READY=true;await refresh(true,true);renderRegionSetup();toast('Road source activated',`${region.name} now backs the operating graph.`);
    }catch(e){toast('Cannot use this road source',e.message,true);}
    return;
  }
  REGION_COLLAPSE_ON_READY=true;
  try{const r=await api('/api/osm/download',{method:'POST',body:JSON.stringify({force:false})});selectedJobId=r.job_id;resetJobLogs(r.job_id);toast('Downloading regional road source',`Job #${r.job_id} · checksum is verified during transfer`);activate('activity');await refresh(true,false);subscribeToActiveJob();}
  catch(e){toast('Road-source download failed',e.message,true);}
}
async function initRegionSetup(){
  if(!$('#regionMap'))return;
  regionMap=L.map('regionMap',{zoomControl:false,preferCanvas:true,worldCopyJump:true,minZoom:1,maxZoom:8,zoomSnap:.5}).setView([18,5],2);
  keylessOsmTiles({maxZoom:8}).addTo(regionMap);L.control.zoom({position:'bottomright'}).addTo(regionMap);observeMapSize(regionMap,'regionMap');
  $('#regionSearch').addEventListener('input',renderRegionSearch);
  $('#regionSearch').addEventListener('keydown',async e=>{
    const input=$('#regionSearch'),box=$('#regionSearchResults');
    if(e.key==='ArrowDown'||e.key==='ArrowUp'){e.preventDefault();moveRegionSearchSelection(e.key==='ArrowDown'?1:-1);return;}
    if(e.key==='Escape'){box.classList.add('hidden');input.setAttribute('aria-expanded','false');input.removeAttribute('aria-activedescendant');REGION_SEARCH_ACTIVE=-1;REGION_SEARCH_IDS=new Set();if(REGION_MAP_LAYER)REGION_MAP_LAYER.setStyle(regionMapStyle);return;}
    if(e.key==='Enter'){e.preventDefault();const items=$$('[data-region-result]',box),chosen=items[REGION_SEARCH_ACTIVE]||items[0];if(chosen)chosen.click();else if(!(await resolveRegionSearch(input.value)))toast('No operating region found','Try a country, state, province, city, or Geofabrik extract.',true);}
  });
  $('#regionFallbackBtn').onclick=()=>{REGION_FORCE_OPEN=true;renderRegionSetup();$('#regionSourceDrawer').scrollIntoView({behavior:motionBehavior(),block:'start'});setTimeout(()=>$('#regionFallbackSelect')?.focus(),250);};
  $('#regionMapBack').onclick=leaveRegionScope;
  $('#regionFallbackUseBtn').onclick=()=>{const id=$('#regionFallbackSelect').value;if(id)chooseOperatingRegion(id,{fit:true});};
  $('#useRecommendedSourceBtn').onclick=downloadSelectedRegion;
  $('#changeRegionBtn').onclick=()=>{REGION_FORCE_OPEN=true;renderRegionSetup();setTimeout(()=>{$('#regionSearch')?.focus();regionMap?.invalidateSize();},80);};
  $('#regionSetupDoneBtn').onclick=()=>{if(!activeSourceOperational())return;REGION_FORCE_OPEN=false;REGION_SEARCH_IDS=new Set();hideRegionHover();renderRegionSetup();};
  document.addEventListener('click',e=>{if(!e.target.closest('.region-search-wrap')){const box=$('#regionSearchResults'),input=$('#regionSearch');box?.classList.add('hidden');input?.setAttribute('aria-expanded','false');input?.removeAttribute('aria-activedescendant');REGION_SEARCH_ACTIVE=-1;}});
  // Local verified sources are operationally useful even when the live catalog is slow or offline.
  // Render Library state first; load the remote map catalog independently afterward.
  const catalogStatus=$('#regionCatalogStatus');
  await loadRegionLibrary();
  renderRegionSetup();
  if(catalogStatus){catalogStatus.className='region-catalog-status';$('span',catalogStatus).textContent='Loading selectable region boundaries…';}
  try{
    REGION_CATALOG=await api('/api/osm/catalog?geometry=true',{timeoutMs:20000});
    drawRegionCatalog();
    fitPlanRegionContext(true);fitRoadsRegionContext(true);
    $('#regionSetup').classList.remove('catalog-error');
    catalogStatus?.classList.add('hidden');
  }
  catch(e){
    $('#regionSetup').classList.add('catalog-error');
    if(catalogStatus){catalogStatus.className='region-catalog-status error';$('span',catalogStatus).textContent='Live boundaries unavailable · verified local cache remains ready';}
    toast('Map catalog unavailable','Your verified local cache is still available. Browse cached sources or retry the live map catalog when the connection returns.',true);
    try{REGION_CATALOG=await api('/api/osm/catalog?geometry=false',{timeoutMs:10000});populateRegionFallback();}catch{}
  }
  renderRegionSetup();
}
function bootFleetRoute(){
  setLanguage('en');
  setJudgeMode(JUDGE_MODE);
  const missing=[];if(typeof L==='undefined')missing.push('map runtime');if(typeof Chart==='undefined')missing.push('chart runtime');
  if(missing.length){
    setConnectionState(false,`Missing local UI component: ${missing.join(', ')}`);
    const title=$('#connectionBannerTitle'),detail=$('#connectionBannerDetail');if(title)title.textContent='FleetRoute UI files did not load';if(detail)detail.textContent='Reload this page. If it repeats, rerun notebook cells 1 and 2.';
    $('#globalOptimizeBtn').disabled=true;return;
  }
  initMaps();bind();bindV14();bindOptimizerSettings();bindLiveOptimizerDock();initRegionSetup();refresh(true,true);
  setInterval(()=>{if(!activeJob()&&Date.now()-LAST_STATE_REFRESH>12000)refresh(true,false);},5000);
  setInterval(pollActiveJobFallback,1500);
  // One view-aware UI heartbeat replaces multiple permanent 500 ms timers.
  // SSE remains the primary live transport; this only refreshes visible dynamic
  // panels and therefore stays cheap while the operator is idle.
  setInterval(()=>{
    if(!STATE)return;
    const job=activeJob();
    if(currentView==='activity'&&selectedJobId){
      const selected=(STATE.jobs||[]).find(x=>+x.id===+selectedJobId);
      if(selected&&['queued','running'].includes(selected.status))tickLiveJobUI(selected);
    }
    if(currentView==='optimize'&&job)renderOptimizeTrace(job);
    renderLiveOptimizerDock(job);
    if(currentView==='roads'){
      const roadJob=(STATE.jobs||[]).find(j=>j.kind==='osm-source-download'&&['queued','running'].includes(j.status));
      if(roadJob)tickRoadDownloadUI(roadJob);
    }
  },750);
}
bootFleetRoute();
