import {SCHEMA,validateDocument,mergeDocuments,exportJSON,exportCSV,createDemoDocument,ACTIVATION_STAGES} from './data.js';
import {filterSessions,aggregate,calendarInterval,groupUsage,comparisonMetrics,distributions,distribution,metricValue,priceCost,validatePrices,costCoverage,usageEconomics,periodComparison,benchmarkGroups,benchmarkArmDistributions,evidenceGaps,independentlyAccepted} from './analytics.js';
import {escape as e,count,human,status,sourceTag,empty,section,metric,pairPlots,tokenTrend,costTrend,toolGraph,valueLabel} from './charts.js';

const PAGES = {
  overview:['Command Center','What has been observed, and what remains unproven.'],
  sessions:['Session Explorer','Inspect each recorded execution without losing missing evidence.'],
  tokens:['Token Intelligence','Usage grouped by provider and calendar period.'],
  tools:['Tool Intelligence','Observed tool-category associations, not inferred causal dependencies.'],
  benchmarks:['Benchmark Lab','Compare contract-consistent attempts and their qualification gates.'],
  activation:['Activation & Evidence','Was the skill made available, delivered, invoked and actually verified?'],
  evidence:['Efficiency Evidence','Separate observed resource differences from attributable savings.'],
  settings:['Sources & Privacy','Your selected files stay on this computer; collection is off.']
};
const EMPTY={schema:SCHEMA,sources:[],sessions:[],comparisons:[],limitations:[]};
const captureKeys=['discovery','delivery','invocation','tools','context','qualification'];
const $=id=>document.getElementById(id);
const safe=v=>e(v??'');
const metricKnown=(s,k)=>metricValue(s,k);
const number=n=>typeof n==='number'?count(n):'Unavailable';
const clock=v=>v?new Intl.DateTimeFormat(undefined,{dateStyle:'medium',timeStyle:'short',timeZone:state.zone}).format(new Date(v)):'Undated';
const label=(s)=>s.title||[s.task,s.arm].filter(Boolean).join(' · ')||'Recorded attempt';
const button=(text,action,id='',style='')=>'<button type="button" class="'+style+'" data-action="'+safe(action)+'" '+(id?'data-id="'+safe(id)+'"':'')+'>'+safe(text)+'</button>';
const cell=v=>'<td>'+safe(v)+'</td>';
const table=(heads,rows,style='')=>'<div class="table-wrap" tabindex="0" role="region" aria-label="'+safe(heads.join(', '))+' data table"><table'+(style?' class="'+safe(style)+'"':'')+'><thead><tr>'+heads.map(h=>'<th scope="col">'+safe(h)+'</th>').join('')+'</tr></thead><tbody>'+rows.join('')+'</tbody></table></div>';
const percent=(v)=>typeof v==='number'?(v*100).toFixed(1)+'%':'Unavailable';
const uncertain=(s)=>s.kind==='control'?'Model-free control':s.kind==='demo'?'Synthetic data':s.qualification?.qualified?'Eligible run; pair not established':'Exploratory / unqualified';
const notice=(msg,error=false)=>{const el=$('notice');el.textContent=msg;el.className=error?'message error':'message';};
const state={historical:EMPTY,imported:EMPTY,demo:validateDocument(createDemoDocument(),{trusted:false}),page:'overview',dataset:'demo',filters:{period:'all',agent:'',provider:'',model:'',project:''},zone:Intl.DateTimeFormat().resolvedOptions().timeZone||'UTC',granularity:'day',costDimension:'calendar',compareBucket:'',search:'',selectedTool:'',pageNo:0,pageSize:15,theme:'dark',capture:Object.fromEntries(captureKeys.map(k=>[k,false])),price:null,selectedSession:null,importing:false,retain:false,staticMode:false,includeControls:false,status:'',sort:'source',available:'',arm:'',kind:'',task:'',pairPage:0,activationId:'',benchmarkSearch:'',benchmarkDifficulty:'',benchmarkEligibility:'',benchmarkId:'',matrixPage:0,distributionPage:0,acceptedOnly:false,readiness:null};
const current=()=>state[state.dataset]||EMPTY;
const filtered=()=>{
  const f=state.filters;const span=calendarInterval({period:f.period,from:$('from-date').value||null,to:$('to-date').value||null,timeZone:state.zone});
  const kinds=new Set(current().sessions.map(s=>s.kind));const preferred=kinds.has('native')||kinds.has('session')?['native','session']:kinds.has('control')?['control']:['demo'];
  const eligible=current().sessions.filter(s=>state.kind?s.kind===state.kind:preferred.includes(s.kind));
  return filterSessions(eligible,{...span,agent:f.agent,provider:f.provider,model:f.model,project:f.project,search:state.search,status:state.status,available:state.available,arm:state.arm});
};
const iconPaths={overview:'M3 11 12 3l9 8M5 10v11h5v-7h4v7h5V10',sessions:'M5 3h14v18H5zM8 7h8M8 11h8M8 15h5',tokens:'M4 20V10h4v10m4 0V4h4v16m4 0V7',tools:'M12 4v6m-7 8 5-5m4 0 5 5M12 2a2 2 0 1 0 0 4 2 2 0 0 0 0-4ZM3 17a2 2 0 1 0 0 4 2 2 0 0 0 0-4Zm18 0a2 2 0 1 0 0 4 2 2 0 0 0 0-4Z',benchmarks:'M3 4h18v16H3zM3 10h18M9 4v16M15 4v16',activation:'M12 3 3 7v6c0 5 9 8 9 8s9-3 9-8V7l-9-4Zm-4 9 3 3 5-6',evidence:'M4 20h16M6 16V9m6 7V4m6 12v-5',settings:'M4 6h16M4 12h16M4 18h16M8 3v6m8 0v6m-6 0v6'};
const icon=key=>'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="'+iconPaths[key]+'"/></svg>';
function navigation(){
  $('navigation').innerHTML=Object.entries(PAGES).map(([id,[name]])=>'<a href="#'+id+'" class="nav-link" '+(id===state.page?'aria-current="page"':'')+'>'+icon(id)+safe(name)+'</a>').join('');
}
function toolbar(){
  const visible=state.page!=='settings';
  $('filters').hidden=!visible;
  const sessions=current().sessions;
  for(const [key,field] of [['agent','agent'],['provider','provider'],['model','model'],['project','project']]){
    const el=$(key);const selected=state.filters[key]||'';
    const opts=[...new Set(sessions.map(s=>s[field]).filter(Boolean))].sort();
    el.innerHTML='<option value="">All '+key+'s</option>'+opts.map(v=>'<option value="'+safe(v)+'">'+safe(v)+'</option>').join('');
    el.value=opts.includes(selected)?selected:'';
    state.filters[key]=el.value;
  }
  $('period').value=state.filters.period;
  $('custom-range').hidden=state.filters.period!=='custom';
  $('page-title').textContent=PAGES[state.page][0];$('page-description').textContent=PAGES[state.page][1];
  $('breadcrumb').textContent='WORKSPACE / '+state.page.toUpperCase().replace('_',' ');
  $('source-summary').textContent=current().sources.length+' sources · '+current().sessions.length+' attempts/sessions · '+current().comparisons.length+' comparison records · no background capture';
  $('capture-status').textContent='Capture off';
  if(!state.includeControls)$('dataset').querySelector('option[value=controls]')?.remove();
  if(state.includeControls&&!$('dataset').querySelector('option[value=controls]')){const option=document.createElement('option');option.value='controls';option.textContent='Model-free controls';$('dataset').append(option);}
  $('dataset').value=state.dataset;
  $('page-actions').innerHTML=state.page==='sessions'||state.page==='benchmarks'||state.page==='evidence'?button('Export CSV','exportCSV','','button'):button('Export JSON','exportJSON','','button');
  navigation();
}
function metricsView(rows){
  const a=aggregate(rows);
  const defs=[['Recorded attempts',a.session_count,'Excludes '+a.unattempted+' unattempted'],['Input tokens',a.input_tokens,'Provider input; cached already included'],['Output tokens',a.output_tokens,'Provider-reported when available'],['Observed tool calls',a.tool_calls_observed,'Public event coverage only']];
  return '<div class="metric-strip">'+defs.map(([name,v,note])=>metric(name,typeof v==='number'?number(v):number(v.value),note,typeof v==='object'&&v?'Coverage '+v.known+'/'+v.total+' attempts':'' )).join('')+'</div>';
}
function evidenceNotes(rows){
  const a=aggregate(rows);
  return '<div class="evidence-summary">'+[
    ['Independent correctness',a.verified_success.value===null?'Unavailable':percent(a.verified_success.value),a.verified_success.known+' accepted-or-rejected observations / '+a.verified_success.total+' attempted'],
    ['Known input usage',a.input_tokens.known+' / '+a.input_tokens.total,'Unknown input tokens remain unknown, never zero'],
    ['Eligible runs',String(rows.filter(s=>s.qualification?.qualified).length),'Run eligibility alone cannot establish a qualified comparison'],
    ['Undated attempts',String(rows.filter(s=>s.status!=='unattempted'&&!s.started_at).length),'Excluded from date-bucket plots, retained in all-time totals']
  ].map(([name,val,note])=>'<div class="evidence-row"><div class="row-head"><strong>'+safe(name)+'</strong>'+safe(val)+'</div><small>'+safe(note)+'</small></div>').join('')+'</div>';
}
const money=(value,currency)=>typeof value==='number'?currency+' '+new Intl.NumberFormat(undefined,{minimumFractionDigits:6,maximumFractionDigits:6}).format(value):'Unavailable';
function costDetail(cost){
  const amounts=cost.currencies.map(row=>money(row.value,row.currency)+' ('+row.covered+' observations'+(row.limited?', '+row.limited+' limited confidence':'')+')');
  const rates=cost.currencies.flatMap(row=>row.rates.map(rate=>rate.version+' · '+rate.provider+'/'+rate.model+' · '+rate.source+' · '+rate.effective_from+' to '+(rate.effective_to||'open-ended')+' · '+rate.currency+'/million: uncached '+rate.uncached_input_per_million+', cached '+rate.cached_input_per_million+', output '+rate.output_per_million+' · '+rate.observations+' observations'));
  return '<span class="cell-note">'+safe(cost.label)+' · Confidence: '+safe(cost.confidence)+'</span><span class="cost-amount">'+safe(amounts.join('; ')||'Unavailable')+'</span><span class="cell-note">'+(cost.complete?'Complete recorded scenario coverage':'Partial / unavailable recorded scenario coverage')+' · '+cost.covered+'/'+cost.total+' priced · '+cost.missing+' missing</span>'+(rates.length?'<details><summary>Rate provenance</summary><ul>'+rates.map(rate=>'<li>'+safe(rate)+'</li>').join('')+'</ul></details>':'')+(cost.reasons.length?'<ul class="note">'+cost.reasons.map(row=>'<li>'+safe(row.count+' × '+row.reason)+'</li>').join('')+'</ul>':'')+'<span class="cell-note">'+safe(cost.assumption_basis)+'</span>';
}
function costSummary(rows){
  const cost=costCoverage(rows,state.price);
  return section('Cost coverage','<div class="comparison-plots"><div class="measure-plot">'+costDetail(cost)+'</div><div class="measure-plot"><h3 class="plot-title">Estimates, not invoices</h3><p class="note">These are subtotals of selected recorded observations. Missing records, human effort, subscriptions, taxes and provider billing adjustments are not inferred. Different currencies remain separate; no conversion or attributable savings is assumed.</p>'+button('Configure pricing','goto','settings','quiet-button')+'</div></div>','','Coverage describes imported observations, not complete account expenditure. Synthetic/control records and unattempted arms are excluded.');
}
function economicsView(rows){
  const dimension=state.costDimension;
  const range=calendarInterval({period:state.filters.period,from:$('from-date').value||null,to:$('to-date').value||null,timeZone:state.zone});
  const report=usageEconomics(rows,state.price,{dimension,granularity:state.granularity,timeZone:state.zone,...range});
  const metricCell=(row,key)=>{const m=row.usage[key];return '<td>'+safe(number(m.value))+'<span class="cell-note">'+m.known+'/'+m.total+' observed</span></td>';};
  const groups=report.groups;
  const selection=groups.some(row=>row.key===state.compareBucket)?state.compareBucket:groups.at(-1)?.key;
  const comparison=dimension==='calendar'&&selection?periodComparison(groups,selection,state.granularity,report.unallocated.length):null;
  const toolbar='<div class="toolbar"><label for="cost-dimension">Cost breakdown</label><select id="cost-dimension">'+[['calendar','Calendar'],['model','Model'],['provider','Provider'],['project','Project']].map(([value,title])=>'<option value="'+value+'" '+(dimension===value?'selected':'')+'>'+title+'</option>').join('')+'</select><label for="cost-granularity">Calendar interval</label><select id="cost-granularity" '+(dimension==='calendar'?'':'disabled')+'> '+[['day','Day'],['week','Week'],['month','Month']].map(([value,title])=>'<option value="'+value+'" '+(state.granularity===value?'selected':'')+'>'+title+'</option>').join('')+'</select><span>'+safe(state.zone)+'</span></div>';
  const currencies=[...new Set(groups.flatMap(row=>row.cost.currencies.map(cost=>cost.currency)))];
  const plots=dimension==='calendar'?currencies.map(currency=>costTrend(groups,currency)).join(''):'';
  const grid=groups.length?table(['Period / group','Sessions','Input','Cached input','Uncached input','Output','Recorded tool calls','Legacy configured cost scenario / coverage'],groups.map(row=>'<tr data-cost-group="'+safe(row.key)+'">'+'<td>'+safe(row.key)+(row.period_clipped?'<span class="cell-note">Partial selected period</span>':'')+'</td><td>'+row.usage.session_count+'<details><summary>Inspect sessions</summary>'+row.ids.slice(0,5).map(id=>button(label(current().sessions.find(s=>s.id===id)||{}),'session',id,'session-link')).join('')+(row.ids.length>5?'<p class="note">First 5 shown; all observations remain in Session Explorer.</p>':'')+'</details></td>'+['input_tokens','cached_input_tokens','uncached_input_tokens','output_tokens','tool_calls_observed'].map(key=>metricCell(row,key)).join('')+'<td>'+costDetail(row.cost)+'</td></tr>')):empty('No allocatable observations','Choose a source with dated usage and a complete session span, or choose Model / Provider / Project to inspect sessions without calendar allocation.');
  const gaps=report.unallocated.length?'<details open><summary>'+report.unallocated.length+' unallocated sessions</summary><p class="note">No token or cost total from these sessions is assigned to calendar buckets. Period differences are unavailable while allocation is incomplete.</p>'+table(['Session','Why not allocated'],report.unallocated.map(row=>'<tr><td>'+button(label(current().sessions.find(s=>s.id===row.id)||{}),'session',row.id,'session-link')+'</td>'+cell(row.reason)+'</tr>'))+'</details>':'';
  const delta=value=>value===null?'Unavailable':(value>0?'+':'')+number(value);
  const compare=comparison?'<div class="toolbar"><label for="compare-period">Compare recorded periods</label><select id="compare-period">'+groups.map(row=>'<option value="'+safe(row.key)+'" '+(row.key===selection?'selected':'')+'>'+safe(row.key)+'</option>').join('')+'</select><span>Previous: '+safe(comparison.previousKey)+'</span></div>'+table(['Recorded metric','Previous','Selected','Change'],[...Object.entries(comparison.metrics).map(([key,row])=>'<tr>'+cell(human(key))+cell(number(row.previous))+cell(number(row.current))+cell(delta(row.delta))+'</tr>'),'<tr>'+cell('Legacy configured cost scenario')+cell('Complete same-currency coverage required')+cell(comparison.cost.assumption_basis+' Confidence: '+comparison.cost.confidence)+cell(comparison.cost.delta===null?'Unavailable':money(comparison.cost.delta,comparison.cost.currency))+'</tr>'])+'<p class="note">'+safe(comparison.note)+' Missing calendar periods are unknown, not zero. Deltas require complete counter/cost coverage and unclipped calendar ranges in both recorded groups.</p>':'';
  return section('Usage and cost intelligence',toolbar+'<p class="note">'+report.allocated+'/'+report.total+' selected observations allocated. Each session is assigned wholly only when its recorded span fits in the bucket. Crossing spans and unknown times remain unallocated; no daily prorating occurs. Week starts Monday. Global date filters select session start times, not within-session events.</p>'+plots+'<p id="cost-selection" class="chart-selection" aria-live="polite">Select a cost bar for exact coverage; the numeric table includes all groups. Charts show at most the last 90 groups per currency.</p>'+grid+gaps+compare,'','User-supplied effective-dated prices × recorded usage. Partial amounts are explicitly covered subtotals, never total account spend.');
}
function overview(rows){
  const a=aggregate(rows);const ids=new Set(rows.map(r=>r.id));const comps=current().comparisons.filter(p=>ids.has(p.baseline_id)&&ids.has(p.treatment_id));
  const qualified=comps.filter(c=>c.qualified===true&&c.kind==='native').length;
  const strip='<div class="metric-strip">'+metric('Recorded attempts',number(a.session_count),a.unattempted+' arm unattempted · not counted')+metric('Input tokens',number(a.input_tokens.value),'Observed '+a.input_tokens.known+'/'+a.input_tokens.total,'Cached already included')+metric('Cached input',number(a.cached_input_tokens.value),'Observed '+a.cached_input_tokens.known+'/'+a.cached_input_tokens.total,'Subset of input')+metric('Output tokens',number(a.output_tokens.value),'Observed '+a.output_tokens.known+'/'+a.output_tokens.total,'Provider usage where supplied')+'</div>';
  return strip+'<div class="summary-line"><span>Tool calls <strong>'+number(a.tool_calls_observed.value)+'</strong> · coverage '+a.tool_calls_observed.known+'/'+a.tool_calls_observed.total+'</span><span>Independent completion <strong>'+percent(a.verified_success.value)+'</strong> · '+a.verified_success.known+'/'+a.verified_success.total+' observed</span><span><strong>'+qualified+' / '+comps.length+' qualified comparisons</strong></span></div>'+
    '<div class="work-grid"><div>'+section('Tokens and time, together',comps.length?pairView(comps[0],current().sessions,true):empty('No paired evidence','Import matched contract-consistent receipts. Ordinary usage does not establish savings.'),button('Benchmark Lab','goto','benchmarks','quiet-button'))+'</div><aside>'+section('Evidence coverage',evidenceNotes(rows),'','A lower token count is only one outcome.')+'</aside></div>'+
    section('Individual observations',sessionTable(rows.slice(0,8)),button('All sessions','goto','sessions','quiet-button'))+
    section('Current-session usage','<p class="note">Unavailable. Observatory cannot see this conversation or live Codex/ChatGPT usage. Select an authorized, sanitized usage export to add actual provider measurements.</p>')+costSummary(rows)+economicsView(rows);
}
function sessionTable(rows){
  if(!rows.length)return empty('No matching observations','Try another source, a different date range, or a different search.');
  return table(['Observation','Arm','Source','Input','Wall time','Verification','Evidence'],rows.map(s=>'<tr><td>'+button(label(s),'session',s.id,'session-link')+'<small class="muted">'+safe(s.task||s.project||'')+'</small></td>'+cell(s.arm||'—')+'<td>'+sourceTag(s.kind)+'</td>'+cell(valueLabel(metricKnown(s,'input_tokens')))+cell(valueLabel(metricKnown(s,'wall_ms'),'wall_ms'))+'<td>'+status(s.acceptance?.accepted===true?(s.acceptance?.independent===true?'Passed':'Reported pass'):s.status==='unattempted'?'Unattempted':s.acceptance?.accepted===false?(s.acceptance?.independent===true?'Failed':'Reported fail'):'Unknown',s.status==='unattempted'?'unattempted':s.acceptance?.accepted===true?'accepted':s.acceptance?.accepted===false?'failed':'unknown')+'</td>'+cell(uncertain(s))+'</tr>'));
}
function sessionsView(rows){
  let sorted=[...rows];const key=state.sort;
  if(key==='title')sorted.sort((a,b)=>label(a).localeCompare(label(b)));
  if(key==='date')sorted.sort((a,b)=>(Date.parse(b.started_at)||0)-(Date.parse(a.started_at)||0));
  if(['input_tokens','wall_ms'].includes(key))sorted.sort((a,b)=>(metricKnown(b,key)??-1)-(metricKnown(a,key)??-1));
  const pages=Math.max(1,Math.ceil(sorted.length/state.pageSize));if(state.pageNo>=pages)state.pageNo=0;
  const select=(id,values,selected)=>'<select id="'+id+'">'+values.map(([v,t])=>'<option value="'+safe(v)+'" '+(v===selected?'selected':'')+'>'+safe(t)+'</option>').join('')+'</select>';
  return metricsView(rows)+section('Session directory','<div class="toolbar"><label for="search">Search</label><input id="search" type="search" placeholder="Task, project, model or session" value="'+safe(state.search)+'"><label>Evidence kind '+select('kind-filter',[['','Automatic separation'],['native','Reported native observations'],['session','Imported observations'],['control','Model-free controls'],['demo','Synthetic demo']],state.kind)+'</label><label>Status '+select('status-filter',[['','All'],['accepted','Accepted'],['failed','Failed'],['incomplete','Incomplete'],['timed_out','Timed out'],['unattempted','Unattempted']],state.status)+'</label><label>Arm '+select('arm-filter',[['','All'],['A','A baseline'],['B','B skill'],['C','C runtime'],['D','D parallel']],state.arm)+'</label><label>Has metric '+select('available-filter',[['','Any coverage'],['input_tokens','Input tokens'],['wall_ms','Wall time'],['tool_calls_observed','Tool events'],['human_review_ms','Human review time']],state.available)+'</label><label>Sort '+select('sort-session',[['source','Source order'],['title','Title'],['date','Newest dated'],['input_tokens','Most input'],['wall_ms','Longest wall']],state.sort)+'</label></div>'+sessionTable(sorted.slice(state.pageNo*state.pageSize,(state.pageNo+1)*state.pageSize))+'<div class="pagination"><span>'+rows.length+' observations · Page '+(state.pageNo+1)+' of '+pages+'</span><div><button type="button" class="quiet-button" data-action="previous" '+(state.pageNo===0?'disabled':'')+'>Previous</button><button type="button" class="quiet-button" data-action="next" '+(state.pageNo>=pages-1?'disabled':'')+'>Next</button></div></div>','','Unattempted arms remain visible. Sort and filters never discard failed attempts from an exported source.');
}
function tokensView(rows){
  const grouped=groupUsage(rows,state.granularity,state.zone);const a=aggregate(rows);
  const dist=field=>table([human(field),'Known / total','Observed input total','Median input','Range','Outliers'],distributions(rows,field,'input_tokens').map(x=>'<tr>'+cell(x.key)+cell(x.count+'/'+x.total)+cell(x.count?number(x.values.reduce((sum,n)=>sum+n,0)):'Unavailable')+cell(number(x.median))+cell(x.min===null?'Unavailable':number(x.min)+' – '+number(x.max))+cell(x.outliers.length)+'</tr>'));
  const buckets=grouped.buckets;let cumulativeInput=null;const cumulative=buckets.map(x=>{if(x.input_tokens.value!==null)cumulativeInput=(cumulativeInput??0)+x.input_tokens.value;return cumulativeInput;});const spread=distribution(rows.map(s=>metricKnown(s,'input_tokens')));const outliers=rows.filter(s=>spread.outliers.includes(metricKnown(s,'input_tokens')));
  return metricsView(rows)+costSummary(rows)+economicsView(rows)+section('Session-start token cohorts by '+state.granularity,'<div class="toolbar"><label>Group by <select id="granularity"><option value="day">Day</option><option value="week">Week</option><option value="month">Month</option></select></label><span class="muted">'+safe(state.zone)+' · '+grouped.undated+' undated, not plotted</span></div>'+(buckets.length?tokenTrend(buckets)+'<p id="bucket-selection" class="chart-selection" aria-live="polite">Select a bar for exact values. The complete numeric table follows.</p>'+table(['Calendar bucket','Attempts','Input','Cached','Uncached','Output','Cumulative observed input'],buckets.map((x,i)=>'<tr>'+cell(x.key)+cell(x.session_count)+cell(number(x.input_tokens.value))+cell(number(x.cached_input_tokens.value))+cell(number(x.uncached_input_tokens.value))+cell(number(x.output_tokens.value))+cell(number(cumulative[i]))+'</tr>')):empty('No dated records','Totals are still available. Historical receipts without timestamps cannot be assigned to calendar buckets.')),'','Cohort totals are assigned to the session start date, not actual within-session daily consumption. Allocation-aware usage and costs follow below. Buckets follow '+state.zone+'. Date filters use local calendar days and an exclusive next-day boundary.')+
    '<div class="split">'+section('Usage by model',dist('model'))+section('Usage by provider',dist('provider'))+'</div><div class="split">'+section('Usage by project',dist('project'))+section('Usage by task',dist('task'))+'</div>'+
    section('Session input outliers',outliers.length?sessionTable(outliers.slice(0,15)):empty('No input outliers identified','A descriptive interquartile-range rule requires at least four observed values. It is not a correctness or efficiency judgment.'),'','Showing up to 15 observations beyond 1.5 × IQR; exact source records remain exportable. Unknown values are excluded. Cumulative input counts only observed counters, with coverage above.')+section('Cache fraction', '<p class="note">'+percent(a.cache_fraction.value)+' in '+a.cache_fraction.known+'/'+a.cache_fraction.total+' attempts with both provider counters. Cached input is a subset of total input. Uncached = input − cached only when both are known. Bytes and characters are never tokens.</p>');
}
function categorized(rows){
  const categories=new Map();
  for(const s of rows)for(const event of s.events||[]){
    const key=String(event.category||'uncategorized');const c=categories.get(key)||{key,calls:0,failures:0,sessions:new Set(),duration:0,knownDuration:0};c.calls++;c.sessions.add(s.id);if(event.success===false)c.failures++;if(typeof event.duration_ms==='number'){c.duration+=event.duration_ms;c.knownDuration++};categories.set(key,c);
  }
  return [...categories.values()].sort((a,b)=>b.calls-a.calls).map(x=>({...x,sessions:x.sessions.size}));
}
function toolsView(rows){
  const tools=categorized(rows);const selected=tools.find(x=>x.key===state.selectedTool);
  return section('Observed tool relationships',tools.length?toolGraph(tools,state.selectedTool):empty('No tool events','Select a receipt containing supported public tool events.'),'','Edges represent observed session associations, never causal dependencies.')+
  (selected?section('Selected category', '<h3>'+safe(human(selected.key))+'</h3><p class="note">'+selected.calls+' calls across '+selected.sessions+' sessions, '+selected.failures+' recorded failures, '+selected.knownDuration+' events with duration data.</p>'):'')+
  section('Accessible category table',tools.length?table(['Category','Calls','Sessions','Failures','Timed events'],tools.map(x=>'<tr><td>'+button(human(x.key),'tool',x.key,'session-link')+'</td>'+cell(x.calls)+cell(x.sessions)+cell(x.failures)+cell(x.knownDuration)+'</tr>')):empty('No observations yet','Import an event-enabled receipt to see tool categories.'),'','Tool timing events are not task wall time.');
}
function pairView(pair, all, compact=false){
  const c=comparisonMetrics(pair,all);const qualified=c.attributable;
  const keys=['input_tokens','cached_input_tokens','uncached_input_tokens','output_tokens','agent_ms','wall_ms','initialization_ms','preparation_ms','verification_ms','checkpoint_ms','tool_calls_observed','potential_redundant_unchanged_rereads','agent_retries','tool_retries','benchmark_reruns','context_bytes','automated_edit_observed_sum_ms','human_review_ms','human_edit_ms','human_interventions','delegation_ms'];
  const signed=(n,k)=>n===null?'Unavailable':(n>0?'+':n<0?'−':'')+valueLabel(Math.abs(n),k);
  const metricRows=keys.map(k=>{const m=c.metrics[k]||{baseline:metricKnown(c.baseline,k),treatment:metricKnown(c.treatment,k),delta:null};return '<tr>'+cell(human(k))+'<td class="number">'+safe(valueLabel(m.baseline,k))+'</td><td class="number">'+safe(valueLabel(m.treatment,k))+'</td><td class="number">'+safe(signed(m.delta,k))+'</td><td class="event-label">'+safe(m.baseline_source||'Unavailable')+' / '+safe(m.treatment_source||'Unavailable')+'</td></tr>';});
  const costs=[c.baseline,c.treatment].map(row=>priceCost(row,state.price));
  const costDelta=costs.every(row=>row.value!==null)&&costs[0].currency===costs[1].currency?(costs[1].value>costs[0].value?'+':'')+money(costs[1].value-costs[0].value,costs[0].currency):'Unavailable';
  metricRows.push('<tr>'+cell('Legacy configured cost scenario')+cell(money(costs[0].value,costs[0].currency))+cell(money(costs[1].value,costs[1].currency))+cell(costDelta)+cell(costs.map(cost=>[cost.source,'Confidence: '+(cost.confidence||'unknown'),cost.reason].filter(Boolean).join(' · ')).join(' / '))+'</tr>');
  const allMetrics='<p class="note">Model costs are estimates from configured rates, not invoices or attributable TuckBit savings. Missing time and human effort are not priced.</p><p class="scroll-hint">Scroll the table horizontally for all values and provenance.</p><div class="table-wrap" tabindex="0" role="region" aria-label="Paired token, latency and effort measurements"><table class="pair-metrics"><caption>Baseline and treatment values, with signed observed differences. Unknown observations are not zero.</caption><thead><tr><th scope="col">Metric</th><th scope="col">Baseline A</th><th scope="col">Treatment '+safe(c.treatment.arm||'T')+'</th><th scope="col">Observed Δ (T − A)</th><th scope="col">A / treatment provenance</th></tr></thead><tbody>'+metricRows.join('')+'</tbody></table></div>';
  const qrows=[c.baseline,c.treatment].map(s=>'<tr>'+cell(s.arm)+'<td>'+safe(s.acceptance?.independent===true?(s.acceptance.all_passed?'Passed':'Failed'):'Unknown / caller-reported')+' '+safe(s.acceptance?.performed??'?')+'/'+safe(s.acceptance?.required??'?')+'</td><td>'+safe(s.activation?.find(a=>a.stage==='delivery_verified')?.state||'unknown')+'</td><td>'+safe(s.activation?.find(a=>a.stage==='invocation')?.state||'unknown')+'</td><td>'+safe(s.policy?.qualified===true?'Verified':s.policy?.qualified===false?'Incomplete':'Unknown')+' · '+safe(s.policy?.unclassified??'?')+' unclassified</td></tr>');
  return '<article class="benchmark-record"><div class="section-header"><div><h3>'+safe(c.baseline.task||'Baseline')+' · A versus '+safe(c.treatment.arm||'treatment')+'</h3><p>'+safe(c.label)+'</p></div>'+status(qualified?'Evaluator-qualified':c.qualified?'Contract-qualified / uncorroborated':c.simulated?'Synthetic / control':'Unqualified',qualified?'verified':'warning')+'</div>'+pairPlots(c)+
    '<div class="qualification-note"><strong>'+(qualified?'Qualified matched observations; one result is not a general effect.':c.qualified?'Contract-consistent pair; independent grading and provider corroboration are unavailable.':c.simulated?'Simulation / model-free evidence, excluded from real savings.':'Observed differences are not attributable savings.')+'</strong>Sample size: '+safe(c.sample_size??'unknown')+'. '+safe((c.reasons||[]).join(' · ')||'No additional reason codes')+'.</div>'+
    (compact?'<details><summary>Inspect all numeric observations</summary>'+allMetrics+'</details>':allMetrics+table(['Arm','Independent acceptance','Full skill delivery','Invocation','Policy coverage'],qrows))+
    '<div class="flow-links">'+button('Inspect baseline','session',c.baseline.id,'text-button')+button('Inspect treatment','session',c.treatment.id,'text-button')+button('Activation & evidence','activationAttempt',c.treatment.id,'text-button')+'</div>'+
    (!compact?'<details><summary>Evidence gaps, matching and source identities</summary>'+gapsView(pair)+'<p class="note">Evaluator: '+safe(pair.evaluator||'Unavailable')+' · Matched identity: '+safe(pair.matched_identity===true?'yes':pair.matched_identity===false?'no':'unknown')+'. Caching conditions and human effort are unknown unless explicitly measured. Preparation is nested in initialization; checkpoint is nested in verification. Shared batch setup is never summed per arm. Public-event duration sums are not client or wall time.</p><dl class="key-value"><dt>Bundle</dt><dd class="mono">'+safe(pair.bundle_sha256||c.baseline.bundle_sha256||'Unavailable')+'</dd><dt>Source</dt><dd class="mono">'+safe(c.baseline.identity?.source||'Unavailable')+'</dd><dt>Baseline receipt</dt><dd class="mono">'+safe(c.baseline.receipt_sha256||c.baseline.id)+'</dd><dt>Treatment receipt</dt><dd class="mono">'+safe(c.treatment.receipt_sha256||c.treatment.id)+'</dd></dl><ul class="gaps">'+[...(pair.limitations||[]),...(c.reasons||[])].map(x=>'<li>'+safe(x)+'</li>').join('')+'</ul></details>':'')+'</article>';
}
function benchmarkPager(label,page,pages,previous,next){
  return '<div class="pagination"><span>'+safe(label)+' · Page '+(page+1)+' of '+pages+'</span><div><button class="quiet-button" data-action="'+previous+'" '+(!page?'disabled':'')+'>Previous</button><button class="quiet-button" data-action="'+next+'" '+(page>=pages-1?'disabled':'')+'>Next</button></div></div>';
}
function benchmarksView(rows){
  const tasks=[...new Set(rows.map(s=>s.task).filter(Boolean))].sort();
  const query=state.benchmarkSearch.toLocaleLowerCase();
  const groups=benchmarkGroups(rows,current().comparisons).filter(group=>(!state.task||group.task===state.task)&&(!state.benchmarkDifficulty||group.complexity===state.benchmarkDifficulty)&&(!state.benchmarkEligibility||(state.benchmarkEligibility==='qualified'?group.qualified>0:group.qualified===0))&&(!query||group.rows.some(row=>[row.task,row.domain,row.complexity,row.provider,row.model,row.bundle_sha256,row.identity?.source,row.identity?.model].some(value=>String(value||'').toLocaleLowerCase().includes(query)))));
  const selected=groups.find(group=>group.id===state.benchmarkId);
  const chosen=selected?selected.rows:groups.flatMap(group=>group.rows);const allowed=new Set(chosen.map(row=>row.id));
  const pairs=current().comparisons.filter(pair=>allowed.has(pair.baseline_id)&&allowed.has(pair.treatment_id));
  const matrixPages=Math.max(1,Math.ceil(groups.length/15));state.matrixPage=Math.min(state.matrixPage,matrixPages-1);
  const attemptPages=Math.max(1,Math.ceil(chosen.length/15));const pairPages=Math.max(1,Math.ceil(pairs.length/5));state.pageNo=Math.min(state.pageNo,attemptPages-1);state.pairPage=Math.min(state.pairPage,pairPages-1);
  const chooser='<div class="toolbar benchmark-filters"><label>Search tasks or identities<input id="benchmark-search" name="benchmark-search" type="search" autocomplete="off" value="'+safe(state.benchmarkSearch)+'" placeholder="Task, model or source hash…"></label><label>Task <select id="task-filter"><option value="">All tasks</option>'+tasks.map(t=>'<option '+(t===state.task?'selected':'')+' value="'+safe(t)+'">'+safe(t)+'</option>').join('')+'</select></label><label>Difficulty<select id="benchmark-difficulty"><option value="">All difficulties</option>'+['small','medium','complex'].map(value=>'<option value="'+value+'" '+(state.benchmarkDifficulty===value?'selected':'')+'>'+human(value)+'</option>').join('')+'</select></label><label>Comparison eligibility<select id="benchmark-eligibility"><option value="">All decisions</option><option value="qualified" '+(state.benchmarkEligibility==='qualified'?'selected':'')+'>Contract-qualified pair present</option><option value="unqualified" '+(state.benchmarkEligibility==='unqualified'?'selected':'')+'>No qualified pair</option></select></label></div>';
  const matrix=groups.slice(state.matrixPage*15,state.matrixPage*15+15).map(group=>'<tr><td>'+button(group.task,'benchmarkGroup',group.id,'session-link')+'<span class="cell-note">'+safe(group.domain)+' · '+safe(group.complexity)+'</span></td><td>'+safe(group.provider||'Unavailable')+' / '+safe(group.model||'Unavailable')+'<details><summary>Model/effort identity</summary><span class="cell-note mono">'+safe(group.rows[0].identity?.model||'Unavailable')+'</span></details></td>'+cell(group.arms.join(' / '))+cell(group.accepted+'/'+group.attempted+' accepted; '+group.unattempted+' unattempted')+cell(group.qualified+'/'+group.pairs.length+' contract-qualified pairs')+'<td><details><summary>Inspect bundle / source</summary><span class="cell-note mono">Bundle: '+safe(group.rows[0].bundle_sha256||'Unavailable')+'</span><span class="cell-note mono">Source: '+safe(group.rows[0].identity?.source||'Unavailable')+'</span></details></td></tr>');
  const orderRows=chosen.slice(state.pageNo*15,state.pageNo*15+15).map(row=>'<tr><td>'+button(row.arm||'No arm','session',row.id,'session-link')+'</td>'+cell(row.trial??'Unavailable')+cell(row.experiment?.benchmark_rerun??'Unavailable')+cell(row.experiment?.order_index===undefined?'Unavailable':row.experiment.order_index+1)+cell(row.experiment?.block_order||'Unavailable')+cell(row.status)+'<td class="mono">'+safe(row.identity?.treatment||'Unavailable')+'</td></tr>');
  return section('Task matrix',chooser+'<p role="status" aria-live="polite">'+groups.length+' task/source/model strata · '+chosen.length+' visible observations'+(selected?' · Selected '+safe(selected.task):'')+'</p>'+(matrix.length?table(['Task / domain / difficulty','Provider / model / effort identity','Arms','Correctness denominator','Original pair decisions','Bundle / source identity'],matrix):empty('No matching tasks','Clear search, difficulty or eligibility filters.'))+benchmarkPager(groups.length+' strata',state.matrixPage,matrixPages,'matrixPrevious','matrixNext')+(selected?button('Show all matching strata','benchmarkGroupClear','','quiet-button'):''),'','A stratum keeps task, source/grader, acceptance requirements, model/effort, environment and bundle together. Missing identities stay separate. Select a task row to inspect original observations.')+
    section('A/B/C attempts',sessionTable(chosen.slice(state.pageNo*15,state.pageNo*15+15))+table(['Inspect arm','Trial','Rerun','Execution position (1-based)','Planned block order','Outcome','Treatment identity / version'],orderRows)+benchmarkPager(chosen.length+' observations',state.pageNo,attemptPages,'benchmarkPrevious','benchmarkNext'),'','Display order is not execution order. Failed, interrupted and unattempted arms remain visible; unknown order is never inferred.')+
    section('Matched comparison evidence',pairs.length?pairs.slice(state.pairPage*5,state.pairPage*5+5).map(pair=>pairView(pair,current().sessions)).join('')+benchmarkPager(pairs.length+' comparisons',state.pairPage,pairPages,'pairPrevious','pairNext'):empty('No matched comparisons','Some strata have no counterpart. Observations remain visible; the frontend never constructs an eligible pair.'),'','The original trusted evaluator owns qualification. Search never promotes a decision.')+benchmarkDistributions(chosen)+readinessView();
}
function benchmarkDistributions(rows){
  const groups=benchmarkArmDistributions(rows,{acceptedOnly:state.acceptedOnly,prices:state.price});
  const pages=Math.max(1,Math.ceil(groups.length/15));state.distributionPage=Math.min(state.distributionPage,pages-1);
  const metrics=['input_tokens','cached_input_tokens','uncached_input_tokens','output_tokens','wall_ms','agent_ms','preparation_ms','verification_ms','tool_calls_observed','agent_retries','tool_retries','human_review_ms','human_edit_ms'];
  const values=groups.slice(state.distributionPage*15,state.distributionPage*15+15).map(group=>{
    const summary=metrics.map(key=>{const d=group.metrics[key];return '<tr>'+cell(human(key))+cell(d.count+'/'+group.selected)+cell(valueLabel(d.median,key))+cell(d.min===null?'Unavailable':valueLabel(d.min,key)+' – '+valueLabel(d.max,key))+cell(d.values.map(value=>valueLabel(value,key)).join('; ')||'Unavailable')+'</tr>';});
    if(!group.costs.length)summary.push('<tr>'+cell('Legacy configured cost scenario')+cell('0/'+group.selected)+cell('Unavailable')+cell('Unavailable')+cell('No supported effective pricing for the selected observations')+'</tr>');
    for(const cost of group.costs)summary.push('<tr>'+cell('Legacy configured cost scenario ('+cost.currency+')')+cell(cost.count+'/'+group.selected)+cell(money(cost.median,cost.currency))+cell(money(cost.min,cost.currency)+' – '+money(cost.max,cost.currency))+cell(cost.values.map(value=>money(value,cost.currency)).join('; '))+'</tr>');
    const order=group.order.map(row=>'trial '+(row.trial??'?')+': position '+(row.position===null?'?':row.position+1)+' / '+(row.block||'?')).join('; ');
    return '<tr><td>'+safe(group.task)+' · '+safe(group.arm)+'<span class="cell-note">'+safe(group.provider||'Unavailable')+' / '+safe(group.model||'Unavailable')+'</span><span class="cell-note mono">Treatment: '+safe(group.treatment||'Unavailable')+'</span></td>'+cell(group.accepted+'/'+group.attempted+' accepted; '+group.failed+' rejected; '+group.interrupted+' interrupted; '+group.unattempted+' unattempted')+cell(valueLabel(group.metrics.input_tokens.median,'input_tokens')+' ('+group.metrics.input_tokens.count+'/'+group.selected+' known)')+cell(valueLabel(group.metrics.wall_ms.median,'wall_ms')+' ('+group.metrics.wall_ms.count+'/'+group.selected+' known)')+'<td>'+safe(group.trials.length+' distinct recorded trials')+'<span class="cell-note">'+safe(order||'Execution order unavailable')+'</span></td><td><details><summary>Inspect '+group.selected+' selected observations</summary>'+table(['Metric','Known / selected','Median','Observed range','Individual values'],summary)+costDetail(group.cost_coverage)+'<p class="note">Costs are estimates only; unpriced attempts remain missing. Preparation/verification may be nested in other timing fields. No time-to-money conversion or total ownership cost is calculated.</p></details></td></tr>';
  });
  return section('Task and arm distributions','<label><input id="benchmark-accepted" type="checkbox" '+(state.acceptedOnly?'checked':'')+'> Independently accepted observations only</label>'+table(['Task / arm / stratum','Outcomes (all observations)','Median input','Median wall','Repetition and order evidence','Resource distributions'],values)+benchmarkPager(groups.length+' arm strata',state.distributionPage,pages,'distributionPrevious','distributionNext'),'','Groups preserve task/model/effort, source/grader, acceptance and treatment identities. Failed attempts stay in denominators when accepted-only is selected. Medians and ranges are descriptive; small samples and unbalanced order cannot establish significance, repeatability or attributable savings.');
}
function gapsView(pair){
  return '<p class="note">These evidence limitations explain what is known; they do not replace or strengthen the original evaluator decision. Unknown evidence is not verified absence.</p>'+table(['Evidence requirement','Evidence state','What is missing / observed','How future evidence could resolve it'],evidenceGaps(pair,current().sessions,state.price).map(gap=>'<tr>'+cell(human(gap.code))+cell(human(gap.state))+cell(gap.meaning)+cell(gap.resolve)+'</tr>'),'wrap-table evidence-gaps');
}
function readinessView(){
  const metadata=state.readiness;
  if(!metadata)return section('Workload acceptance readiness',empty('Readiness metadata unavailable','Use the local adapter or packaged metadata. Missing controls never imply native readiness.'));
  return section('Workload acceptance readiness',table(['Workload','Structural / model-free validation','Executable controls','Native eligible / observed','Correctness / efficiency qualified','Remaining gate'],metadata.candidates.map(row=>'<tr>'+cell(row.id)+cell(row.structural)+cell(row.controls)+cell('No / No')+cell('Not established / No')+cell(row.gap)+'</tr>'),'wrap-table readiness-table')+'<details><summary>Control provenance and fingerprints</summary><p class="note">'+safe(metadata.scope)+'</p><dl class="key-value"><dt>Control version</dt><dd>'+safe(metadata.version)+'</dd><dt>Control implementation</dt><dd class="mono">'+safe(metadata.implementation_sha256)+'</dd><dt>Source</dt><dd class="mono">'+safe(metadata.source_revision)+'</dd><dt>Original grader</dt><dd class="mono">'+safe(metadata.grader_sha256)+'</dd><dt>Environment</dt><dd>'+safe(metadata.environment)+'</dd></dl></details>','','Controls exercise the existing safe evaluator. They are not native model observations, historical regrades or authorization to execute arbitrary model code.');
}
function activationTimeline(s){
  return '<ol class="activation-timeline">'+ACTIVATION_STAGES.map(stage=>{const r=s.activation?.find(a=>a.stage===stage)||{state:'unknown'};return '<li data-state="'+safe(r.state)+'"><strong>'+safe(human(stage))+'</strong>'+status(human(r.state),r.state)+'</li>';}).join('')+'</ol>';
}
function activationDetails(s){
 const stages=ACTIVATION_STAGES.map(stage=>{const r=s.activation?.find(a=>a.stage===stage)||{state:'unknown'};return '<tr>'+cell(human(stage))+'<td>'+status(human(r.state),r.state)+'</td><td class="event-label">'+safe(r.note||'No supported observation')+'</td><td class="event-label">'+safe(r.provenance||'Unavailable')+'</td>'+cell(r.events?.length||'No public event')+'</tr>';});
 const events=ACTIVATION_STAGES.flatMap(stage=>(s.activation?.find(item=>item.stage===stage)?.events||[]).map(event=>({...event,stage}))).slice(0,80);
 return '<p class="note">Installation: Unknown. Availability and offered-runtime evidence do not prove a persistent installation. Attempt '+safe(s.id)+' · Arm '+safe(s.arm||'Unavailable')+' · Policy coverage: '+safe(s.policy?.classified_commands??'?')+'/'+safe(s.policy?.observed_commands??'?')+' · Treatment version/hash: <span class="mono">'+safe(s.identity?.treatment||'Unavailable')+'</span></p>'+activationTimeline(s)+table(['Stage','Evidence state','Meaning / limitation','Provenance','Events'],stages)+'<p class="note">A complete file read proves delivery only. It does not expose hidden reasoning, establish semantic adherence, or imply an invocation.</p>'+table(['Stage / event','Order / timestamp','Source version / hash','Content hash','Delivery complete','Provenance'],events.map(ev=>'<tr>'+cell(human(ev.stage)+' / '+ev.id)+cell((ev.order??'Unknown')+' / '+(ev.timestamp||'Unavailable'))+'<td class="mono">'+safe(ev.source_sha256||'Unavailable')+'</td><td class="mono">'+safe(ev.content_sha256||'Unavailable')+'</td>'+cell(ev.delivery_complete===true?'Verified':ev.delivery_complete===false?'Explicitly incomplete':'Unknown')+cell(ev.provenance||'Unavailable')+'</tr>'))+'<p class="note">First 80 stage/event links shown; the same event may support several stages. Export JSON preserves the full bounded evidence. Unknown timestamps remain unavailable.</p>';
}

function activationView(rows){
  if(!rows.length)return section('Activation inspector',empty('No activation observations','Import an explicitly selected supported evidence file or choose another dataset.'));
  const selected=rows.find(s=>s.id===state.activationId)||rows[0];state.activationId=selected.id;
  const chooser='<label for="activation-attempt">Inspect attempt</label><select id="activation-attempt">'+rows.map(s=>'<option value="'+safe(s.id)+'" '+(s.id===selected.id?'selected':'')+'>'+safe(label(s))+'</option>').join('')+'</select>';
  return section('Activation inspector','<p class="note">Not observed means no supported record; unknown means observation coverage cannot decide. Explicitly absent requires affirmative evidence. Baseline A has no TuckBit treatment.</p>'+chooser+'<article class="activation-record"><div class="section-header"><h3>'+button(label(selected),'session',selected.id,'session-link')+'</h3>'+sourceTag(selected.kind)+'</div>'+activationDetails(selected)+'<ul class="gaps">'+(selected.qualification?.reasons||[]).map(r=>'<li>'+safe(human(r))+'</li>').join('')+'</ul></article>','','Delivery, invocation and independently observed application are distinct.');
}
function evidenceView(rows){
  const allowed=new Set(rows.map(r=>r.id));
  const pairs=current().comparisons.filter(p=>allowed.has(p.baseline_id)&&allowed.has(p.treatment_id));
  const real=pairs.filter(p=>comparisonMetrics(p,rows).attributable);
  return '<div class="metric-strip">'+metric('Qualified pairs',number(real.length),'Independent grading required; contract validation alone is insufficient')+metric('Attributable tokens saved','Unavailable',real.length?'Per-pair signed differences below; no pooled causal total':'No independently observed matched comparison')+metric('Unqualified pairs',number(pairs.length-real.length),'Cannot support savings claims')+metric('Missing time evidence',number(rows.filter(r=>!r.started_at).length),'Undated sessions stay outside trends')+'</div>'+
  benchmarksView(rows);
}

function settingsView(){
  const doc=current();
  const captureLabels={discovery:'Skill discovery and availability',delivery:'Instruction delivery and complete-read evidence',invocation:'Public skill/tool invocation events',tools:'Tool categories, outcomes and timing',context:'Safe source/range identities',qualification:'Benchmark qualification metadata'};
  return section('Local data sources','<p class="note">Select an exported JSON file or a Codex rollout JSONL file you are authorized to inspect. No session folder is scanned, and current conversation usage is unavailable. Aggregate counters and independent acceptance are sanitized; the optional detail scopes below control additional evidence.</p>'+table(['Source / identity','Format','Trust','Imported'],doc.sources.map(r=>'<tr><td>'+safe(r.label||'Unnamed')+'<span class="cell-note mono">'+safe(r.sha256)+'</span></td>'+cell(r.format)+cell(r.trust)+cell(clock(r.imported_at))+'</tr>'))+'<div class="actions-row">'+button('Select JSON or Codex JSONL','import','','button primary')+button('Export JSON','exportJSON','','button')+button('Export session CSV','exportCSV','','button')+button('Export paired CSV','exportComparisonsCSV','','button')+button('Delete imported data','clear','','button danger')+'</div>')+
  section('Import a Codex session','<ol><li>Choose a single exported Codex rollout JSONL file (up to 4 MiB) from your own files using the selection button above. No directory access is requested.</li><li>The file is processed by the local server. Conversation text, tool arguments, commands, source, instructions and credentials are discarded; only supported counters and hashed identities reach the dashboard.</li><li>Open Sessions for usage and import diagnostics, Tokens for calendar history, and Tools for observed categories. Codex client counters may contain estimates or replay; elapsed session span includes idle time.</li><li>Identical imports are deduplicated. To refresh a changed session snapshot, export your current imports, delete imported data, then select the updated files. Conflicting snapshots never silently overwrite each other.</li></ol><p class="note">Supported records start with session_meta and may include turn_context, event_msg token_count and response_item tool calls. Forked/inherited histories and counter resets are rejected. Incremental-only usage, mixed models, acceptance, retries and activation remain unavailable when unsupported.</p>')+
  section('Evidence import preferences','<p class="note">Optional detail import is off by default. Turn on only the supported categories you want retained from future manually selected files. This is not a background recorder. Approved historical studies retain their original instrumentation consent.</p><div class="capture-options">'+captureKeys.map(key=>'<label><input type="checkbox" data-capture="'+key+'" '+(state.capture[key]?'checked':'')+'> '+safe(captureLabels[key])+'</label>').join('')+'</div><p class="note">Turning a category off omits its detailed evidence on the next import; aggregate usage fields remain explicitly sourced. Missing coverage is shown as unknown. Unavailable provider events cannot be enabled by a checkbox.</p>')+
  section('Retention and calendar','<div class="setting-row"><div><label for="retain-imports"><input id="retain-imports" type="checkbox" '+(state.retain?'checked':'')+'> Retain sanitized imports in this browser</label><p>Off by default. Retained data are not encrypted and can be read by someone using this browser profile. Turning retention off deletes the stored copy. Delete imported data clears both memory and storage.</p></div></div><p class="note">Restored or exported evaluator decisions are retained as reported, but become unverified until the original receipts are checked again. No requalification of historical observations occurs. Theme, timezone and these non-sensitive preferences are saved locally; price tables stay in memory.</p><div class="settings-fields"><label for="timezone">Calendar timezone (IANA)<input id="timezone" type="text" value="'+safe(state.zone)+'" placeholder="Europe/Nicosia"></label>'+button('Apply timezone','applyTimezone','','button')+'</div><p class="note">Date ranges use inclusive local start/end dates and an exclusive next-day instant. DST follows the selected timezone.</p>')+
  section('Historical controls','<label class="setting-row"><span>Show model-free research controls as a separate dataset</span><input id="include-controls" type="checkbox" '+(state.includeControls?'checked':'')+'></label><p class="note">Controls validate the harness. Their synthetic usage never enters native provider totals or measured savings.</p>')+
  section('Cost configuration (optional)','<p class="note">Legacy prices/1 computes only a legacy configured cost scenario using three manual rates and legacy uncached input (total minus cache reads). Absent cache writes are not verified zeros. Actual billing mode and cache-write applicability remain unresolved. Complete API-equivalent estimates are unavailable until documented source counters and a versioned mapping support them. Subscription charges and quota usage are unavailable. Pricing is manual and stays in this tab.</p><details><summary>Pricing JSON format</summary><pre class="price-example">'+safe(JSON.stringify({schema:'tuckbit.prices/1',version:'your-reviewed-table',rates:[{provider:'OpenAI',model:'exact-model-id',currency:'USD',effective_from:'2026-01-01T00:00:00Z',effective_to:null,uncached_input_per_million:0,cached_input_per_million:0,output_per_million:0,source:'Your documented rate reference (example zeros are not provider prices)'}]},null,2))+'</pre></details><label for="price-config">Paste versioned rate JSON</label><textarea id="price-config" rows="5" placeholder="No prices are assumed"></textarea><div class="actions-row">'+button('Apply local pricing','price','','button')+button('Clear pricing','clearprice','','quiet-button')+'</div><p class="note">'+safe(state.price?'Configured: '+state.price.version:'Pricing unavailable: no validated table configured.')+'</p>')+
  section('Local diagnostics and collection coverage','<dl class="key-value"><dt>Current-session usage</dt><dd>Unavailable — no authorized live provider source.</dd><dt>Capture</dt><dd>Disabled. Manual file selection only.</dd><dt>Sentry / replay</dt><dd>Disabled and not configured. No remote requests.</dd><dt>Storage mode</dt><dd>'+safe(state.retain?'Opt-in browser retention':'Memory-only imports')+'</dd><dt>Application mode</dt><dd>'+safe(state.staticMode?'Static export; imports require the local adapter server':'Local read-only adapters; supported receipt imports')+'</dd></dl><p class="note">Supported: explicitly selected Codex rollout JSONL, TuckBit sanitized V5/V5.1/V5.2 receipt lists, profiler traces, explicit Observatory session observations and normalized exports. Codex conversation content is discarded locally; other raw log formats are rejected. Commands, private source and credentials never enter exported observations. The server serves an allowlisted web directory, not arbitrary files.</p>');
}
function render(){
  const target=location.hash.slice(1).split('?')[0];if(target==='main'){$('main').focus();return;}const nextPage=PAGES[target]?target:'overview';
  if(nextPage!==state.page){state.status='';state.arm='';state.available='';state.kind='';state.search='';state.pageNo=0;}state.page=nextPage;
  toolbar();
  let rows;
  try{rows=filtered();}catch(error){notice(error.message,true);rows=[];}
  const kinds=new Set(rows.map(s=>s.kind));$('dataset-banner')?.remove();if(state.dataset==='demo'||state.dataset==='controls'||kinds.has('demo')||kinds.has('control')){const banner=document.createElement('p');banner.id='dataset-banner';banner.className='message demo';banner.textContent=state.dataset==='demo'?'Synthetic demo — illustrative values, never real performance evidence.':state.dataset==='controls'?'Model-free controls — instrumentation tests, never native savings.':'This selection contains synthetic/control data. Native comparisons stay separately qualified; do not pool these totals as provider usage.';$('view').before(banner);}
  let result='';
  try{
    switch(state.page){
      case 'sessions':result=sessionsView(rows);break;
      case 'tokens':result=tokensView(rows);break;
      case 'tools':result=toolsView(rows);break;
      case 'benchmarks':result=benchmarksView(rows);break;
      case 'activation':result=activationView(rows);break;
      case 'evidence':result=evidenceView(rows);break;
      case 'settings':result=settingsView();break;
      default:result=overview(rows);
    }
  }catch(error){result=empty('This view could not be rendered',String(error.message||error));}
  $('view').innerHTML=result;$('view').setAttribute('aria-busy','false');
  if($('granularity'))$('granularity').value=state.granularity;
}
function sessionDialog(id){
  const s=current().sessions.find(x=>x.id===id);if(!s)return;
  const metrics=Object.entries(s.metrics);const cost=priceCost(s,state.price);
  $('session-content').innerHTML='<div class="session-inspector">'+sourceTag(s.kind)+'<h2>'+safe(label(s))+'</h2><p class="note">ID: <span class="mono">'+safe(s.id)+'</span> · '+safe(clock(s.started_at))+'</p>'+
    '<div class="metric-strip">'+[['Input tokens','input_tokens'],['Cached input','cached_input_tokens'],['Output tokens','output_tokens'],['Wall time','wall_ms']].map(([name,key])=>metric(name,valueLabel(metricKnown(s,key),key),s.metrics[key]?.source||'No provider report')).join('')+'</div>'+
    section('Session configured cost scenario',costDetail(costCoverage([s],state.price))+'<p class="note">'+safe(cost.reason)+(cost.confidence?' · Confidence: '+safe(cost.confidence):'')+'</p>')+
    section('Acceptance and policy','<p class="note">Receipt contract consistency and source hashes do not authenticate provider activity. External provider corroboration is unavailable; grading below may be receipt-reported.</p><div class="evidence-summary"><div class="evidence-row">Independent: '+safe(String(s.acceptance?.independent??'Unknown'))+' · Accepted: '+safe(String(s.acceptance?.accepted??'Unknown'))+' · Checks: '+safe(String(s.acceptance?.performed??'?'))+'/'+safe(String(s.acceptance?.required??'?'))+'</div><div class="evidence-row">Policy classified: '+safe(String(s.policy?.classified_commands??'?'))+'/'+safe(String(s.policy?.observed_commands??'?'))+' · '+safe((s.qualification?.reasons||[]).join(', '))+'</div></div>')+
    section('Activation evidence',activationDetails(s))+
    section('All recorded metrics',table(['Metric','Value','Evidence'],metrics.map(([k,v])=>'<tr>'+cell(human(k))+cell(valueLabel(v.value,k))+cell((v.source||'Unavailable')+' · '+v.status)+'</tr>')))+
    section('Public tool event timeline','<p class="note">Showing the first '+Math.min(80,s.events?.length||0)+' of '+(s.events?.length||0)+' sanitized events. Export JSON for the full bounded sequence; timestamps remain unknown unless supplied.</p>'+table(['Order / time','Category','Outcome','Observed duration','Safe evidence identity'],(s.events||[]).slice(0,80).map(ev=>'<tr>'+cell(ev.order===undefined?'Unknown':ev.order)+'<td>'+safe(human(ev.category))+'</td>'+cell(ev.success===null||ev.success===undefined?'Unknown':ev.success?'Success':'Failed')+cell(valueLabel(ev.duration_ms,'duration_ms'))+'<td class="mono">'+safe(ev.evidence?.source||ev.operation||ev.id||'Unavailable')+'</td></tr>')))+
    section('Limits — what this observation cannot support',(s.limitations||[]).length?'<ul class="note limitations">'+s.limitations.map(item=>'<li>'+safe(item)+'</li>').join('')+'</ul>':'<p class="note">No specific limitations provided.</p>')+'</div>';
  $('session-dialog').showModal();
}
function savePreferences(){
 try{localStorage.setItem('tuckbit-observatory.preferences',JSON.stringify({theme:state.theme,zone:state.zone,capture:state.capture,retain:state.retain}));}catch{ /* Private browsing may disallow preference storage. */ }
}
function loadPreferences(){
 try{const p=JSON.parse(localStorage.getItem('tuckbit-observatory.preferences')||'null');if(!p)return;
  if(['dark','light'].includes(p.theme))state.theme=p.theme;
  if(typeof p.zone==='string'){new Intl.DateTimeFormat('en',{timeZone:p.zone});state.zone=p.zone;}
  if(p.capture&&captureKeys.every(k=>typeof p.capture[k]==='boolean'))state.capture=Object.fromEntries(captureKeys.map(k=>[k,p.capture[k]]));
  state.retain=p.retain===true;
 }catch{notice('Saved preferences were invalid; safe defaults are in use.',true);}
 document.documentElement.dataset.theme=state.theme;
}
function storeImport(value){
 return new Promise((resolve,reject)=>{const request=indexedDB.open('tuckbit-observatory',1);request.onupgradeneeded=()=>request.result.createObjectStore('workspace');request.onerror=()=>reject(new Error('Browser retention unavailable'));request.onsuccess=()=>{const db=request.result;const transaction=db.transaction('workspace',value===undefined?'readonly':'readwrite');const requestStore=value===undefined?transaction.objectStore('workspace').get('imports'):value===null?transaction.objectStore('workspace').delete('imports'):transaction.objectStore('workspace').put(value,'imports');let result;requestStore.onsuccess=()=>{result=requestStore.result;};transaction.oncomplete=()=>{db.close();resolve(result);};transaction.onerror=transaction.onabort=()=>{db.close();reject(new Error('Browser retention unavailable'));};};});
}
async function persistImports(){
 if(!state.retain)return;
 try{await storeImport(exportJSON(state.imported));}catch{state.retain=false;savePreferences();notice('Browser retention failed. Imports remain in this tab; export JSON to keep a copy.',true);}
}
function subsetDocument(doc,predicate){
 const sessions=doc.sessions.filter(predicate);const ids=new Set(sessions.map(r=>r.id));const sourceIDs=new Set(sessions.map(r=>r.source_id));
 return {...doc,sessions,sources:doc.sources.filter(s=>sourceIDs.has(s.id)),comparisons:doc.comparisons.filter(p=>ids.has(p.baseline_id)&&ids.has(p.treatment_id))};
}
async function loadHistorical(controls=false){
 let response;
 try{response=await fetch('/api/historical'+(controls?'?controls=1':''),{cache:'no-store'});if(!response.ok)throw new Error('adapter_unavailable');return validateDocument(await response.json(),{trusted:true});}
 catch{response=await fetch('data/historical.json',{cache:'no-store'});if(!response.ok)throw new Error('Historical sources unavailable');state.staticMode=true;return validateDocument(await response.json(),{trusted:false});}
}
function download(content,type,name){
  const link=document.createElement('a');const url=URL.createObjectURL(new Blob([content],{type}));
  link.href=url;link.download=name;document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
function importDiagnostic(error){
  const reasons={codex_counter_reset:'Cumulative counters decreased. Resumed/reset histories cannot be safely reconciled; choose one complete, non-reset session export.',codex_inconsistent_total:'Token components do not reconcile with the recorded total. Choose a complete supported export.',codex_cache_exceeds_input:'Cached input exceeds total input. Choose an unmodified supported export.',codex_multiple_sessions:'The file contains multiple session identities. Select one session per file.',codex_inherited_history_unsupported:'Forked or inherited history can contain shared usage. This adapter cannot safely attribute it.',codex_invalid_timestamp:'A session timestamp is invalid; select a supported UTC export.',codex_session_meta_required:'Codex JSONL must begin with session_meta. Other raw logs are unsupported.',duplicate_json_key:'The file contains duplicate JSON keys and was rejected.',size_limit:'The selected file or merged workspace exceeds 4 MiB. Use a smaller supported export.',
    invalid_json:'The file is not valid JSON or Codex JSONL. Select an Observatory JSON export or one Codex rollout .jsonl file.',invalid_number:'The file contains a non-finite number (NaN or Infinity), which is not valid JSON.',
    codex_malformed_line:'A line after session_meta is not valid JSON, so the export is truncated or edited. Select the original, complete export; do not remove lines from a cumulative history.',
    codex_line_limit:'The export is empty or has more than 100,000 records. Select a smaller single-session export.',codex_invalid_record:'A record is not a Codex rollout line with a payload object. Only unmodified rollout JSONL is supported.',
    codex_invalid_identity:'session_meta has no valid session UUID, so deduplication would be unsafe.',codex_timestamp_required:'session_meta has no UTC timestamp, so the session cannot be placed on the calendar.',
    codex_timestamp_before_session:'A record is timestamped before its session started. The history may be merged or edited; select one original export.',
    codex_invalid_usage:'A token report is malformed or has negative, fractional or oversized counters. These cannot be reconciled.',
    codex_call_identity_required:'A tool call has no call identity, so duplicate calls cannot be told apart.',codex_invalid_tool_name:'A tool call has a non-text name.',
    codex_conflicting_call:'The same call identity appears with different tools. The export is inconsistent and was not merged.',event_limit:'Too many events: at most 10,000 per session and 100,000 per file.',
    unsupported_schema:'This JSON shape is not a supported Observatory, receipt, trace or session format.',invalid_document:'The document failed validation. Check the documented format in Sources & Privacy.'};
  for(const [code,message] of Object.entries(reasons))if(error.message.endsWith(': '+code))return message+' (code '+code+')';
  if(error.message==='Conflicting session identity')return 'A different snapshot of this session is already imported. Export your current imports, delete imported data, then select the updated files.';
  if(error.message==='Selected file exceeds 4 MiB')return reasons.size_limit;
  const code=/: ([a-z_]+)$/.exec(error.message)?.[1];
  return 'The file could not be imported. Check the documented format, size and privacy rules in Sources & Privacy.'+(code?' (code '+code+')':'');
}
async function importFiles(files){
  if(!files.length)return;
  if(state.importing)return;
  if(state.staticMode){notice('Imports require the local adapter server so evidence preferences and privacy validation can be enforced. Start python3 scripts/dashboard_server.py.',true);$('file-input').value='';return;}
  state.importing=true;let countFiles=0,newSessions=0;
  notice('Validating selected files locally…');
  try{
    for(const file of files){
      state.importPosition=(countFiles+1)+' of '+files.length;
      if(file.size>4*1024*1024)throw new Error('Selected file exceeds 4 MiB');
      const raw=await file.text();
      const body=JSON.stringify({document_text:raw,capture:state.capture});
      let doc;
      if(state.staticMode){throw new Error('Static imports disabled; start the local adapter server');}else{
      const response=await fetch('/api/import',{method:'POST',headers:{'Content-Type':'application/json','X-Observatory-Import':'selected-file'},body});
      if(!response.ok){const x=await response.json().catch(()=>({error:'import_failed'}));throw new Error('Import rejected ('+response.status+'): '+x.error);}
      doc=validateDocument(await response.json(),{trusted:true});}
      const merged=mergeDocuments(state.imported,doc);
      newSessions+=merged.sessions.length-state.imported.sessions.length;state.imported=merged;
      countFiles++;
    }
    await persistImports();state.dataset='imported';state.task='';state.benchmarkId='';state.pageNo=0;notice(countFiles+' selected file(s) imported locally. '+newSessions+' new session(s); existing identical observations were deduplicated. No background capture was enabled.');render();
  }catch(error){await persistImports();state.dataset='imported';render();notice('Import stopped at file '+state.importPosition+'. '+(countFiles?countFiles+' earlier file(s) in this selection were accepted. ':'')+'Previously imported data is unchanged. '+importDiagnostic(error),true);}finally{state.importing=false;$('file-input').value='';}
}
function setup(){
  $('navigation').addEventListener('click',event=>{if(event.target.closest('a')){state.pageNo=0;state.search='';}});
  window.addEventListener('hashchange',render);
  $('dataset').addEventListener('change',event=>{state.dataset=event.target.value;state.task='';state.benchmarkSearch='';state.benchmarkDifficulty='';state.benchmarkEligibility='';state.benchmarkId='';state.matrixPage=0;state.distributionPage=0;state.pageNo=0;state.pairPage=0;state.kind='';state.status='';state.arm='';state.available='';state.search='';render();});
  $('period').addEventListener('change',event=>{state.filters.period=event.target.value;state.pageNo=0;render();});
  for(const k of ['agent','provider','model','project'])$(k).addEventListener('change',event=>{state.filters[k]=event.target.value;state.pageNo=0;render();});
  for(const k of ['from-date','to-date'])$(k).addEventListener('change',()=>{state.pageNo=0;render();});
  $('import-top').addEventListener('click',()=>$('file-input').click());
  $('file-input').addEventListener('change',event=>importFiles([...event.target.files]));
  $('refresh').addEventListener('click',async()=>{
    if(state.dataset==='historical'){
      try{state.historical=subsetDocument(await loadHistorical(),s=>s.kind!=='control'&&s.kind!=='demo');notice('Historical sources refreshed.');}
      catch(error){notice('Refresh failed: '+error.message,true);}
    }else notice('Local data refreshed. Retention is '+(state.retain?'enabled.':'off; imported data remain in this tab only.'));
    render();
  });
  $('theme-toggle').addEventListener('click',()=>{state.theme=state.theme==='dark'?'light':'dark';document.documentElement.dataset.theme=state.theme;updateTheme();});
  $('close-dialog').addEventListener('click',()=>$('session-dialog').close());
  $('session-dialog').addEventListener('click',event=>{if(event.target===$('session-dialog'))$('session-dialog').close();});
  $('view').addEventListener('input',event=>{if(event.target.id==='benchmark-search'){state.benchmarkSearch=event.target.value;state.matrixPage=0;state.pageNo=0;state.pairPage=0;state.distributionPage=0;const pos=event.target.selectionStart;render();const box=$('benchmark-search');box.focus();box.setSelectionRange(pos,pos);}if(event.target.id==='search'){state.search=event.target.value;state.pageNo=0;const pos=event.target.selectionStart;render();const box=$('search');if(box){box.focus();box.setSelectionRange(pos,pos);}}});
  $('view').addEventListener('change',async event=>{
    if(event.target.id==='benchmark-difficulty'||event.target.id==='benchmark-eligibility'){state[event.target.id==='benchmark-difficulty'?'benchmarkDifficulty':'benchmarkEligibility']=event.target.value;state.benchmarkId='';state.matrixPage=0;state.pageNo=0;state.pairPage=0;state.distributionPage=0;render();}
    if(event.target.id==='benchmark-accepted'){state.acceptedOnly=event.target.checked;render();}
    if(['granularity','cost-granularity'].includes(event.target.id)){state.granularity=event.target.value;state.compareBucket='';render();}
    if(event.target.id==='cost-dimension'){state.costDimension=event.target.value;state.compareBucket='';render();}
    if(event.target.id==='compare-period'){state.compareBucket=event.target.value;render();}
    if(['status-filter','available-filter','arm-filter','sort-session','kind-filter','task-filter','activation-attempt'].includes(event.target.id)){state[({'status-filter':'status','available-filter':'available','arm-filter':'arm','sort-session':'sort','kind-filter':'kind','task-filter':'task','activation-attempt':'activationId'})[event.target.id]]=event.target.value;state.pageNo=0;state.pairPage=0;state.matrixPage=0;state.distributionPage=0;state.benchmarkId='';render();}
    if(event.target.id==='retain-imports'){state.retain=event.target.checked;savePreferences();if(state.retain)await persistImports();else await storeImport(null).catch(()=>{});notice(state.retain?'Sanitized browser retention enabled.':'Retained browser copy deleted; current tab data remain.');}
    if(event.target.id==='include-controls'){state.includeControls=event.target.checked;if(state.includeControls){try{state.controls=subsetDocument(await loadHistorical(true),s=>s.kind==='control');state.dataset='controls';}catch{notice('Controls could not be loaded.',true);state.includeControls=false;}}else{state.controls=EMPTY;if(state.dataset==='controls')state.dataset='historical';}render();}
    if(event.target.dataset.capture){state.capture[event.target.dataset.capture]=event.target.checked;savePreferences();notice('Local import evidence preference updated; no background monitoring enabled.');}
  });
  const handleViewAction=async event=>{
    const costBucket=event.target.closest('[data-cost-bucket]');if(costBucket){$('cost-selection').textContent=costBucket.getAttribute('aria-label');return;}
    const bucket=event.target.closest('[data-bucket]');if(bucket){const row=groupUsage(filtered(),state.granularity,state.zone).buckets.find(r=>r.key===bucket.dataset.bucket);if(row&&$('bucket-selection'))$('bucket-selection').textContent=row.key+': '+number(row.input_tokens.value)+' input, '+number(row.cached_input_tokens.value)+' cached, '+number(row.output_tokens.value)+' output tokens. Known input in '+row.input_tokens.known+'/'+row.input_tokens.total+' attempts.';return;}
    const toolNode=event.target.closest('[data-tool]');if(toolNode){state.selectedTool=toolNode.dataset.tool;render();return;}
    const control=event.target.closest('[data-action]');if(!control)return;
    const {action,id}=control.dataset;
    switch(action){
      case 'goto':location.hash=id;break;
      case 'activationAttempt':state.activationId=id;location.hash='activation';break;
      case 'import':$('file-input').click();break;
      case 'session':sessionDialog(id);break;
      case 'tool':state.selectedTool=id;render();break;
      case 'benchmarkGroup':state.benchmarkId=id;state.pageNo=0;state.pairPage=0;state.distributionPage=0;render();$('view').querySelector('[data-action=benchmarkGroupClear]')?.focus();break;
      case 'benchmarkGroupClear':state.benchmarkId='';state.pageNo=0;state.pairPage=0;state.distributionPage=0;render();break;
      case 'matrixPrevious':state.matrixPage=Math.max(0,state.matrixPage-1);render();break;
      case 'matrixNext':state.matrixPage++;render();break;
      case 'distributionPrevious':state.distributionPage=Math.max(0,state.distributionPage-1);render();break;
      case 'distributionNext':state.distributionPage++;render();break;
      case 'benchmarkPrevious':state.pageNo=Math.max(0,state.pageNo-1);render();break;
      case 'benchmarkNext':state.pageNo++;render();break;
      case 'pairPrevious':state.pairPage=Math.max(0,state.pairPage-1);render();break;
      case 'pairNext':state.pairPage++;render();break;
      case 'previous':state.pageNo=Math.max(0,state.pageNo-1);render();break;
      case 'next':state.pageNo=Math.min(Math.max(0,Math.ceil(filtered().length/state.pageSize)-1),state.pageNo+1);render();break;
      case 'clear':state.imported=EMPTY;await storeImport(null).catch(()=>{});notice('Imported records deleted from memory and browser retention.');render();break;
      case 'applyTimezone':try{const zone=$('timezone').value.trim();new Intl.DateTimeFormat('en',{timeZone:zone});state.zone=zone;savePreferences();notice('Calendar timezone updated to '+zone+'.');render();}catch{notice('Timezone not recognized. Use an IANA name such as Europe/Nicosia or UTC.',true);}break;
      case 'price':try{state.price=validatePrices(JSON.parse($('price-config').value));notice('Local pricing configured. Legacy configured cost scenarios are not invoices or real API charges.');render();}catch{notice('Pricing rejected. Check the versioned schema, effective dates and numeric rates.',true);}break;
      case 'clearprice':state.price=null;notice('Local pricing cleared.');render();break;
      case 'exportComparisonsCSV':download(exportCSV(current(),{type:'comparisons'}),'text/csv','tuckbit-observatory-pairs.csv');break;
      case 'exportJSON':download(exportJSON(current()),'application/json','tuckbit-observatory.json');break;
      case 'exportCSV':download(exportCSV(current(),{type:state.page==='benchmarks'||state.page==='evidence'?'comparisons':'sessions'}),'text/csv','tuckbit-observatory.csv');break;
    }
  };
  $('view').addEventListener('click',handleViewAction);
  $('page-actions').addEventListener('click',handleViewAction);
  $('view').addEventListener('keydown',event=>{const node=event.target.closest('[data-tool]');if(node&&(event.key==='Enter'||event.key===' ')){event.preventDefault();state.selectedTool=node.dataset.tool;render();}});
}
function updateTheme(){
  $('theme-toggle').setAttribute('aria-label','Switch to '+(state.theme==='dark'?'light':'dark')+' theme');
  $('theme-toggle').innerHTML='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v3m0 14v3M2 12h3m14 0h3M5 5l2 2m10 10 2 2M5 19l2-2M17 7l2-2"/></svg>';savePreferences();
}
async function main(){
  loadPreferences();setup();updateTheme();$('view').setAttribute('aria-busy','true');
  notice('Public preview: synthetic demo only until you explicitly choose a local file. Historical private research is not bundled.');
  if(state.retain){try{const value=await storeImport();if(value){state.imported=validateDocument(value,{trusted:false});state.dataset='imported';notice('Retained sanitized imports restored. Prior decisions remain recorded but need receipt revalidation.');}}catch{notice('Retained imports could not be restored. Select the original receipt file again.',true);}}
  try{const response=await fetch('data/readiness.json',{cache:'no-store'});if(response.ok)state.readiness=await response.json();}catch{ /* Readiness stays explicitly unavailable. */ }
  render();
}
main();
