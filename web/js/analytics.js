import {METRIC_KEYS} from './data.js';

const observed = (session, key) => {
  const value = session.metrics?.[key]?.value;
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : null;
};
export const metricValue = observed;
export function filterSessions(sessions, filters = {}) {
  const {from, to, agent, provider, model, project, search, status, kind, arm, available} = filters;
  const fromTime = from ? Date.parse(from) : null;
  const toTime = to ? Date.parse(to) : null;
  if ((from && !Number.isFinite(fromTime)) || (to && !Number.isFinite(toTime)) || (fromTime !== null && toTime !== null && fromTime >= toTime)) throw new Error('Invalid [from, to) interval');
  const query = (search || '').toLocaleLowerCase();
  return sessions.filter(session => {
    const at = session.started_at ? Date.parse(session.started_at) : null;
    if ((fromTime !== null || toTime !== null) && (at === null || !Number.isFinite(at) || (fromTime !== null && at < fromTime) || (toTime !== null && at >= toTime))) return false;
    for (const [key, value] of Object.entries({agent, provider, model, project, status, kind, arm})) {
      if (value && value !== 'all' && session[key] !== value) return false;
    }
    if (available && observed(session, available) === null) return false;
    return !query || ['id', 'title', 'agent', 'provider', 'model', 'project', 'task', 'domain', 'complexity'].some(key => String(session[key] || '').toLocaleLowerCase().includes(query));
  });
}
export function aggregate(sessions) {
  const unattempted = sessions.filter(item => item.status === 'unattempted').length;
  sessions = sessions.filter(item => item.status !== 'unattempted');
  const output = {session_count: sessions.length, unattempted, dated: sessions.filter(item => item.started_at).length};
  for (const key of METRIC_KEYS) {
    const values = sessions.map(session => observed(session, key)).filter(value => value !== null);
    output[key] = {value: values.length ? values.reduce((sum, value) => sum + value, 0) : null, known: values.length, total: sessions.length, coverage: sessions.length ? values.length / sessions.length : null, source: 'sum of recorded metric observations'};
  }
  const accepted = sessions.filter(session => session.acceptance?.independent === true && (session.acceptance?.accepted === false || (session.acceptance?.accepted === true && session.acceptance.all_passed === true && Number.isInteger(session.acceptance.required) && session.acceptance.required > 0 && session.acceptance.performed === session.acceptance.required)));
  const passed = accepted.filter(session => session.acceptance.accepted).length;
  output.verified_success = {value: accepted.length ? passed / accepted.length : null, passed, known: accepted.length, total: sessions.length, coverage: sessions.length ? accepted.length / sessions.length : null, source: 'independent acceptance observations'};
  // Cache fraction uses only sessions with both counters, avoiding incompatible partial denominators.
  const cacheRows = sessions.filter(session => observed(session, 'input_tokens') !== null && observed(session, 'cached_input_tokens') !== null);
  const input = cacheRows.reduce((sum, session) => sum + observed(session, 'input_tokens'), 0);
  const cached = cacheRows.reduce((sum, session) => sum + observed(session, 'cached_input_tokens'), 0);
  output.cache_fraction = {value: input > 0 ? cached / input : null, known: cacheRows.length, total: sessions.length, source: 'cached / input in sessions with both provider counters'};
  return output;
}
const formatters = new Map();
function calendarParts(timestamp, timeZone) {
  if (!formatters.has(timeZone)) formatters.set(timeZone, new Intl.DateTimeFormat('en-CA', {timeZone, year: 'numeric', month: '2-digit', day: '2-digit'}));
  return Object.fromEntries(formatters.get(timeZone).formatToParts(new Date(timestamp)).filter(part => ['year', 'month', 'day'].includes(part.type)).map(part => [part.type, part.value]));
}
function dateLabel(value) {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value) || !Number.isFinite(Date.parse(`${value}T00:00:00Z`)) || new Date(`${value}T00:00:00Z`).toISOString().slice(0, 10) !== value) throw new Error('Invalid calendar date');
  return value;
}
function addCalendarDays(label, days) {
  const date = new Date(`${label}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}
function localDayStart(label, timeZone) {
  const center = Date.parse(`${dateLabel(label)}T00:00:00Z`);
  let low = center - 36 * 3600000;
  let high = center + 36 * 3600000;
  // Search the first instant in the local calendar day; this also handles a midnight DST gap.
  while (low < high) {
    const middle = Math.floor((low + high) / 2);
    const {year, month, day} = calendarParts(middle, timeZone);
    if (`${year}-${month}-${day}` < label) low = middle + 1;
    else high = middle;
  }
  const {year, month, day} = calendarParts(low, timeZone);
  if (`${year}-${month}-${day}` !== label) throw new Error('Calendar date does not exist in this timezone');
  return new Date(low).toISOString();
}
export function calendarInterval({period = 'all', from = null, to = null, timeZone = 'UTC', now = new Date()} = {}) {
  new Intl.DateTimeFormat('en', {timeZone});
  if (!['all', 'today', '7d', '30d', 'custom'].includes(period)) throw new Error('Unsupported period');
  if (period === 'all') return {from: null, to: null};
  if (period === 'custom') {
    const first = from ? localDayStart(dateLabel(from), timeZone) : null;
    const last = to ? localDayStart(addCalendarDays(dateLabel(to), 1), timeZone) : null;
    if (first && last && Date.parse(first) >= Date.parse(last)) throw new Error('Invalid custom calendar range');
    return {from: first, to: last};
  }
  const instant = new Date(now);
  if (!Number.isFinite(instant.getTime())) throw new Error('Invalid current timestamp');
  const {year, month, day} = calendarParts(instant, timeZone);
  const today = `${year}-${month}-${day}`;
  const offset = period === 'today' ? 0 : period === '7d' ? -6 : -29;
  return {from: localDayStart(addCalendarDays(today, offset), timeZone), to: localDayStart(addCalendarDays(today, 1), timeZone)};
}
function calendarKey(timestamp, granularity, timeZone) {
  const {year, month, day} = calendarParts(timestamp, timeZone);
  let key = `${year}-${month}-${day}`;
  if (granularity === 'month') key = `${year}-${month}`;
  if (granularity === 'week') {
    // This is calendar arithmetic on date labels, not a UTC interpretation of the observation.
    const date = new Date(Date.UTC(Number(year), Number(month) - 1, Number(day)));
    date.setUTCDate(date.getUTCDate() - ((date.getUTCDay() + 6) % 7));
    key = date.toISOString().slice(0, 10);
  }
  return key;
}
export function groupUsage(sessions, granularity = 'day', timeZone = 'UTC') {
  if (!['day', 'week', 'month'].includes(granularity)) throw new Error('Unsupported calendar grouping');
  new Intl.DateTimeFormat('en', {timeZone});
  const buckets = new Map();
  let undated = 0;
  for (const session of sessions) {
    if (!session.started_at || !Number.isFinite(Date.parse(session.started_at))) { undated++; continue; }
    const key = calendarKey(session.started_at, granularity, timeZone);
    if (!buckets.has(key)) buckets.set(key, []);
    buckets.get(key).push(session);
  }
  return {granularity, timeZone, undated, total: sessions.length, buckets: [...buckets.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([key, rows]) => ({key, ...aggregate(rows)}))};
}
export function comparisonMetrics(comparison, sessions) {
  const byID = new Map(sessions.map(session => [session.id, session]));
  const baseline = byID.get(comparison.baseline_id);
  const treatment = byID.get(comparison.treatment_id);
  if (!baseline || !treatment) throw new Error('Comparison refers to an unavailable session');
  const simulated = [baseline, treatment].some(session => ['control', 'demo'].includes(session.kind)) || ['control', 'demo'].includes(comparison.kind);
  const attributable = comparison.qualified === true && !simulated && [baseline, treatment].every(row => row.acceptance?.independent === true);
  const metrics = {};
  for (const key of METRIC_KEYS) {
    const a = observed(baseline, key);
    const b = observed(treatment, key);
    metrics[key] = {baseline: a, treatment: b, delta: a !== null && b !== null ? b - a : null, percent: a !== null && a !== 0 && b !== null ? (b - a) / a * 100 : null, baseline_source: baseline.metrics[key]?.source ?? null, treatment_source: treatment.metrics[key]?.source ?? null, attributable};
  }
  return {baseline, treatment, metrics, qualified: comparison.qualified === true, attributable, simulated, label: simulated ? 'Simulation / model-free control — not measured native savings' : attributable ? 'Evaluator-qualified observed difference' : 'Exploratory observed difference — not attributable savings', reasons: comparison.reasons || [], sample_size: comparison.sample_size ?? null};
}
export function distribution(values) {
  const ordered = values.filter(value => typeof value === 'number' && Number.isFinite(value)).sort((a, b) => a - b);
  if (!ordered.length) return {count: 0, median: null, min: null, max: null, values: [], outliers: []};
  const median = data => data.length % 2 ? data[(data.length - 1) / 2] : (data[data.length / 2 - 1] + data[data.length / 2]) / 2;
  const mid = Math.floor(ordered.length / 2);
  const q1 = ordered.length > 3 ? median(ordered.slice(0, mid)) : null;
  const q3 = ordered.length > 3 ? median(ordered.slice(Math.ceil(ordered.length / 2))) : null;
  const iqr = q1 === null ? null : q3 - q1;
  return {count: ordered.length, median: median(ordered), min: ordered[0], max: ordered.at(-1), values: ordered, outliers: iqr === null ? [] : ordered.filter(value => value < q1 - 1.5 * iqr || value > q3 + 1.5 * iqr)};
}
export function distributions(sessions, field = 'model', metric = 'input_tokens') {
  if (!['model', 'provider', 'project', 'task', 'domain', 'arm'].includes(field) || !METRIC_KEYS.includes(metric)) throw new Error('Unsupported distribution');
  const groups = new Map();
  for (const session of sessions) {
    const key = session[field] || 'Unknown';
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(session);
  }
  return [...groups.entries()].map(([key, rows]) => ({key, total: rows.length, ...distribution(rows.map(session => observed(session, metric)))})).sort((a, b) => (b.median ?? -1) - (a.median ?? -1));
}
const scenarioLabel = 'Legacy configured cost scenario';
const scenarioBasis = 'Three configured rates × legacy uncached input (total minus cache reads), cached input and output. Cache writes are not verified by absent counters; no separate write charge is modeled. Codex client counters, when used, may include estimates or replay. Actual API-equivalent billing remains incomplete: billing mode, cache-write applicability and required source counters are unresolved. Subscription charges and quota usage are unavailable. Not an invoice, real API charge, complete billing or savings.';
export function priceCost(session, configuration) {
  const unavailable = reason => ({value: null, currency: null, status: 'unavailable', reason, source: null});
  if (!configuration || configuration.schema !== 'tuckbit.prices/1' || typeof configuration.version !== 'string' || !configuration.version || !Array.isArray(configuration.rates)) return unavailable('Validated versioned pricing is not configured');
  try { validatePrices(configuration); } catch { return unavailable('Pricing components, dates or evidence are incomplete'); }
  if (!session.started_at) return unavailable('Session timestamp unavailable for effective pricing');
  const matches = configuration.rates.filter(rate => rate.provider === session.provider && rate.model === session.model && typeof rate.currency === 'string' && /^[A-Z]{3}$/.test(rate.currency) && Number.isFinite(Date.parse(rate.effective_from)) && Date.parse(rate.effective_from) <= Date.parse(session.started_at) && (!rate.effective_to || (Number.isFinite(Date.parse(rate.effective_to)) && Date.parse(session.started_at) < Date.parse(rate.effective_to))));
  if (matches.length !== 1) return unavailable('No unique effective price matches this provider/model/date');
  const rate = matches[0];
  const span = sessionSpan(session);
  const clientCounters = session.metrics?.input_tokens?.source === 'codex_client_cumulative';
  if ((rate.effective_to && (span === null || Date.parse(session.started_at) + span >= Date.parse(rate.effective_to))) || configuration.rates.some(other => other !== rate && other.provider === session.provider && other.model === session.model && Date.parse(other.effective_from) > Date.parse(session.started_at) && (span === null || Date.parse(other.effective_from) <= Date.parse(session.started_at)+span))) return unavailable('Session span may cross the price validity boundary; per-response pricing is unavailable');
  if (typeof rate.source !== 'string' || !rate.source || !['uncached_input_per_million', 'cached_input_per_million', 'output_per_million'].every(key => typeof rate[key] === 'number' && Number.isFinite(rate[key]) && rate[key] >= 0)) return unavailable('Pricing components or evidence are incomplete');
  const totalInput = observed(session, 'input_tokens');
  const cachedInput = observed(session, 'cached_input_tokens');
  const uncachedInput = observed(session, 'uncached_input_tokens');
  if (totalInput === null || cachedInput === null || uncachedInput === null || cachedInput + uncachedInput !== totalInput) return unavailable('Validated total/cached/uncached input usage is unavailable');
  const counters = ['uncached_input_tokens', 'cached_input_tokens', 'output_tokens'].map(key => observed(session, key));
  if (counters.some(value => value === null || !Number.isSafeInteger(value)) || !Number.isSafeInteger(totalInput)) return unavailable('Complete cached/uncached/output usage is unavailable');
  if (['control', 'demo'].includes(session.kind)) return unavailable('Synthetic/control usage is excluded from actual cost estimates');
  const writes = Object.entries(session.metrics || {}).filter(([key]) => /cache.*(?:write|creation)/i.test(key));
  if (writes.some(([, metric]) => metric?.value !== 0 || metric?.status !== 'observed')) return {...unavailable('Legacy configured cost scenario incompatible with explicit cache-write observations; billing mode and cache-write pricing are unresolved. Subscription charges and quota usage are unavailable.'), status: 'incomplete'};
  const value = (uncachedInput * rate.uncached_input_per_million + cachedInput * rate.cached_input_per_million + counters[2] * rate.output_per_million) / 1_000_000;
  if (!Number.isFinite(value)) return unavailable('Configured scenario exceeds numeric range');
  return {value, rate: {...rate, version: configuration.version}, currency: rate.currency, status: 'scenario', label: scenarioLabel, confidence: clientCounters ? 'limited' : 'configured', reason: scenarioBasis, source: `${configuration.version}: ${rate.source}`};
}

function validRateDate(value) {
  return typeof value === 'string' && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?(?:Z|\+00:00)$/.test(value) && Number.isFinite(Date.parse(value)) && new Date(value).toISOString().slice(0,10) === value.slice(0,10);
}
export function validatePrices(value){
 const fail=()=>{throw new Error('Invalid price configuration');};
 const text=v=>typeof v==='string'&&v.trim()&&v.length<=512&&!/[\u0000-\u001f]/.test(v);
 if(!value||value.schema!=='tuckbit.prices/1'||!text(value.version)||!Array.isArray(value.rates)||value.rates.length>200||Object.keys(value).some(k=>!['schema','version','rates'].includes(k)))fail();
 const keys=['provider','model','currency','effective_from','effective_to','uncached_input_per_million','cached_input_per_million','output_per_million','source'];
 for(const rate of value.rates){if(!rate||Object.keys(rate).some(k=>!keys.includes(k))||!['provider','model','currency','source','effective_from'].every(k=>text(rate[k]))||!/^[A-Z]{3}$/.test(rate.currency)||!validRateDate(rate.effective_from))fail();if(rate.effective_to!==null&&rate.effective_to!==undefined&&(!text(rate.effective_to)||!validRateDate(rate.effective_to)||Date.parse(rate.effective_to)<=Date.parse(rate.effective_from)))fail();for(const k of ['uncached_input_per_million','cached_input_per_million','output_per_million'])if(typeof rate[k]!=='number'||!Number.isFinite(rate[k])||rate[k]<0)fail();}
 return value;
}

// A Codex span explicitly marked unknown cannot fall back to an unrelated wall-time metric.
function sessionSpan(session) {
  return session.metrics?.session_elapsed_ms ? observed(session, 'session_elapsed_ms') : observed(session, 'wall_ms');
}
function uniqueSessions(sessions) {
  const unique = new Map();
  for (const session of sessions) {
    const prior = unique.get(session.id);
    if (prior && prior !== session && JSON.stringify(prior) !== JSON.stringify(session)) throw new Error('Conflicting session identity');
    unique.set(session.id, session);
  }
  return [...unique.values()];
}
export function costCoverage(sessions, configuration) {
  const rows = uniqueSessions(sessions).filter(row => !['control','demo'].includes(row.kind) && row.status !== 'unattempted');
  const currencies = new Map(), reasons = new Map();
  let priced = 0;
  for (const row of rows) {
    const cost = priceCost(row, configuration);
    if (cost.value === null) { reasons.set(cost.reason, (reasons.get(cost.reason) || 0)+1); continue; }
    priced++;
    const group = currencies.get(cost.currency) || {currency:cost.currency,value:0,covered:0,limited:0,rates:new Map()};
    group.value += cost.value; group.covered++; if (cost.confidence === 'limited') group.limited++;
    const identity = JSON.stringify(cost.rate);
    const rate = group.rates.get(identity) || {...cost.rate,observations:0};rate.observations++;
    group.rates.set(identity,rate);currencies.set(cost.currency,group);
  }
  const amounts = [...currencies.values()].map(group=>({...group,rates:[...group.rates.values()]}));
  if (amounts.some(group=>!Number.isFinite(group.value))) throw new Error('Cost aggregate exceeds numeric range');
  return {label:scenarioLabel,assumption_basis:scenarioBasis,confidence:!priced?'unknown':amounts.some(group=>group.limited)?'limited':'configured',total:rows.length,covered:priced,missing:rows.length-priced,complete:rows.length>0 && priced===rows.length,
    currencies:amounts,reasons:[...reasons].map(([reason,count])=>({reason,count})),
    excluded:uniqueSessions(sessions).length-rows.length};
}
export function usageEconomics(sessions, configuration, {dimension='calendar',granularity='day',timeZone='UTC',from=null,to=null}={}) {
  if (!['calendar','model','provider','project'].includes(dimension)) throw new Error('Invalid breakdown');
  if (!['day','week','month'].includes(granularity)) throw new Error('Unsupported calendar grouping');
  new Intl.DateTimeFormat('en',{timeZone});
  const rows=uniqueSessions(sessions).filter(row=>!['control','demo'].includes(row.kind) && row.status!=='unattempted');
  const groups=new Map(), unallocated=[];
  for (const row of rows) {
    let key;
    if (dimension==='calendar') {
      const span=sessionSpan(row), start=Date.parse(row.started_at);
      let reason=null;
      if (!Number.isFinite(start)) reason='Session timestamp unavailable';
      else if (span===null || !Number.isFinite(start+span) || !Number.isFinite(new Date(start+span).getTime())) reason='Complete session span unavailable';
      else if (calendarKey(start,granularity,timeZone)!==calendarKey(start+span,granularity,timeZone)) reason='Session spans calendar buckets; timestamped usage allocation unavailable';
      if (reason) {unallocated.push({id:row.id,reason});continue;}
      key=calendarKey(start,granularity,timeZone);
    } else key=dimension==='model'?[row.provider||'Unavailable provider',row.model||'Unavailable model'].join(' / '):row[dimension] || 'Unavailable';
    if (!groups.has(key))groups.set(key,[]);
    groups.get(key).push(row);
  }
  return {dimension,granularity,timeZone,total:rows.length,allocated:rows.length-unallocated.length,unallocated,
    groups:[...groups].sort(([a],[b])=>a.localeCompare(b)).map(([key,items])=>({key,usage:aggregate(items),cost:costCoverage(items,configuration),ids:items.map(row=>row.id),source_ids:[...new Set(items.map(row=>row.source_id))],period_clipped:dimension==='calendar' && clippedBucket(key,granularity,timeZone,from,to)}))};
}
function clippedBucket(key,granularity,timeZone,from,to) {
  const first=granularity==='month'?key+'-01':key;
  let next=addCalendarDays(first,granularity==='week'?7:1);
  if(granularity==='month') {const date=new Date(first+'T00:00:00Z');date.setUTCMonth(date.getUTCMonth()+1);next=date.toISOString().slice(0,10);}
  const start=Date.parse(localDayStart(first,timeZone)),end=Date.parse(localDayStart(next,timeZone));
  return !!((from && Date.parse(from)>start) || (to && Date.parse(to)<end));
}
function precedingKey(key,granularity) {
  if (granularity==='month') {const date=new Date(key+'-01T00:00:00Z');date.setUTCMonth(date.getUTCMonth()-1);return date.toISOString().slice(0,7);}
  return addCalendarDays(key,granularity==='week'?-7:-1);
}
export function periodComparison(groups,key,granularity='day',unallocated=0) {
  if (!['day','week','month'].includes(granularity)) throw new Error('Unsupported calendar grouping');
  const current=groups.find(row=>row.key===key), previousKey=precedingKey(key,granularity);
  const previous=groups.find(row=>row.key===previousKey);
  const metrics={};
  for (const name of ['input_tokens','cached_input_tokens','uncached_input_tokens','output_tokens','tool_calls_observed']) {
    const a=previous?.usage[name],b=current?.usage[name];
    const complete=unallocated===0 && !current?.period_clipped && !previous?.period_clipped && !!a && !!b && a.known===a.total && b.known===b.total;
    metrics[name]={previous:a?.value??null,current:b?.value??null,delta:complete?b.value-a.value:null};
  }
  const a=previous?.cost,b=current?.cost;
  const comparable=unallocated===0 && !current?.period_clipped && !previous?.period_clipped && !!a?.complete && !!b?.complete && a.currencies.length===1 && b.currencies.length===1 && a.currencies[0].currency===b.currencies[0].currency;
  return {key,previousKey,metrics,cost:{label:scenarioLabel,assumption_basis:scenarioBasis,confidence:!comparable?'unknown':a.confidence==='limited'||b.confidence==='limited'?'limited':'configured',delta:comparable?b.currencies[0].value-a.currencies[0].value:null,currency:comparable?b.currencies[0].currency:null},
    note:'Descriptive recorded observations only. Calendar/source coverage does not establish complete account expenditure or a controlled TuckBit effect.'};
}

export function independentlyAccepted(row) {
  const a = row.acceptance;
  return row.status !== 'unattempted' && a?.independent === true && a.accepted === true && a.all_passed === true && Number.isInteger(a.required) && a.required > 0 && a.performed === a.required;
}

// Identity hashes bind model/effort, grader/task, environment, permissions and source.
export function benchmarkStratum(row) {
  const identity = Object.fromEntries(Object.entries(row.identity || {}).filter(([key]) => key !== 'treatment').sort(([a], [b]) => a.localeCompare(b)));
  const complete = ['client','configuration','dependencies','environment','model','permissions','runtime','source','task'].every(key => identity[key]) && Number.isInteger(row.acceptance?.required) && row.acceptance.required > 0;
  return JSON.stringify([row.kind, row.task, row.complexity, row.provider, row.model, row.bundle_sha256 ?? null, row.stratum_sha256 ?? null, identity, row.acceptance?.required ?? null,
    complete ? null : row.id]);
}

export function benchmarkGroups(sessions, comparisons = []) {
  const groups = new Map();
  for (const row of uniqueSessions(sessions)) {
    if (!row.task) continue;
    const key = benchmarkStratum(row);
    if (!groups.has(key)) groups.set(key, {key, id: row.id, task: row.task, domain: row.domain, complexity: row.complexity, provider: row.provider, model: row.model, rows: [], pairs: []});
    groups.get(key).rows.push(row);
  }
  const membership = new Map([...groups.values()].flatMap(group => group.rows.map(row => [row.id, group.key])));
  for (const pair of comparisons) {
    const key = membership.get(pair.baseline_id);
    if (key !== undefined && membership.get(pair.treatment_id) === key) groups.get(key).pairs.push(pair);
  }
  for (const group of groups.values()) {
    group.qualified = group.pairs.filter(pair => pair.qualified === true).length;
    group.attempted = group.rows.filter(row => row.status !== 'unattempted').length;
    group.accepted = group.rows.filter(independentlyAccepted).length;
    group.unattempted = group.rows.length - group.attempted;
    group.arms = [...new Set(group.rows.map(row => row.arm || 'Unknown'))].sort();
  }
  return [...groups.values()].sort((a, b) => a.task.localeCompare(b.task) || a.key.localeCompare(b.key));
}

export function benchmarkArmDistributions(sessions, {acceptedOnly = false, prices = null} = {}) {
  return benchmarkGroups(sessions).flatMap(group => [...new Set(group.rows.map(row => JSON.stringify([row.arm || 'Unknown', row.identity?.treatment || row.id])))].map(treatment => {
    const rows = group.rows.filter(row => JSON.stringify([row.arm || 'Unknown', row.identity?.treatment || row.id]) === treatment);
    const arm = rows[0].arm || 'Unknown';
    const attempted = rows.filter(row => row.status !== 'unattempted');
    const accepted = attempted.filter(independentlyAccepted);
    const selected = acceptedOnly ? accepted : attempted;
    const metrics = Object.fromEntries(METRIC_KEYS.map(key => [key, distribution(selected.map(row => observed(row, key)))]));
    const currencies = new Map();
    for (const row of selected) {
      const cost = priceCost(row, prices);
      if (cost.value === null) continue;
      if (!currencies.has(cost.currency)) currencies.set(cost.currency, []);
      currencies.get(cost.currency).push(cost.value);
    }
    return {stratum: group.key, id: group.id, task: group.task, model: group.model, provider: group.provider, arm, treatment: rows[0].identity?.treatment ?? null, total: rows.length, attempted: attempted.length,
      accepted: accepted.length, failed: attempted.filter(row => row.acceptance?.independent === true && row.acceptance.accepted === false).length,
      interrupted: attempted.filter(row => row.status === 'interrupted').length, unattempted: rows.length - attempted.length,
      selected: selected.length, metrics, cost_coverage: costCoverage(selected, prices), costs: [...currencies].map(([currency, values]) => ({currency, ...distribution(values)})),
      trials: [...new Set(attempted.map(row => row.trial).filter(Number.isInteger))],
      order: attempted.map(row => ({id: row.id, trial: row.trial ?? null, position: row.experiment?.order_index ?? null, block: row.experiment?.block_order ?? null})),
      limitation: 'Descriptive observations only. Repeats, order balance and independent matched pairs are required before repeatability or attribution can be assessed; no significance is inferred.'};
  }));
}

export function evidenceGaps(pair, sessions, prices = null) {
  const byID = new Map(sessions.map(row => [row.id, row]));
  const rows = [byID.get(pair.baseline_id), byID.get(pair.treatment_id)].filter(Boolean);
  const gaps = [];
  const add = (code, state, meaning, resolve) => gaps.push({code, state, meaning, resolve});
  for (const reason of pair.reasons || []) add(reason, 'evaluator', `Original evaluator: ${reason.replaceAll('_', ' ')}.`, 'Inspect the original decision below. Collect new, matched evidence in a separately authorized future experiment; historical decisions stay unchanged.');
  if (rows.length !== 2) add('missing_attempt', 'unknown', 'One comparison attempt is unavailable.', 'Select both original attempt receipts.');
  if (rows.length === 2 && benchmarkStratum(rows[0]) !== benchmarkStratum(rows[1])) add('stratum_mismatch', 'observed', 'Task, model/effort, acceptance, source, bundle or environment differs, or its identity is unknown.', 'Use the same source, grader, acceptance requirements and runtime identity in future matched attempts. These observations remain separate.');
  if (pair.baseline_id === pair.treatment_id) add('distinct_attempts', 'observed', 'The same attempt cannot be its own comparison.', 'Provide distinct baseline and treatment receipts.');
  for (const row of rows) {
    const who = `Arm ${row.arm || '?'} (${row.id.slice(0, 12)})`;
    if (!independentlyAccepted(row)) add('acceptance', row.acceptance?.independent === true && row.acceptance.accepted === false ? 'verified_failure' : 'unknown', `${who}: independent correctness acceptance is failed, incomplete or unavailable.`, 'A future attempt needs all required independent checks to pass; failed attempts remain in denominators.');
    if (row.status === 'unattempted' || row.status === 'interrupted') add(row.status, 'observed', `${who}: ${row.status}.`, 'A separate authorized future run can provide an outcome. Do not fill in the missing run.');
    if (row.policy?.qualified !== true) add('policy_coverage', row.policy?.qualified === false ? 'incomplete' : 'unknown', `${who}: policy classified ${row.policy?.classified_commands ?? '?'} of ${row.policy?.observed_commands ?? '?'} commands.`, 'Classify every observed command with a supported policy observer and preserve coverage in the new receipt.');
    if (row.arm !== 'A') for (const [stage, meaning, resolve] of [
      ['delivery_verified', 'Full instruction delivery', 'Record complete canonical instruction bytes and their hash; offering or starting a read is insufficient.'],
      ['invocation', 'Public invocation', 'Use a supported public invocation event. A complete read alone cannot prove invocation.'],
      ['behavioral', 'Independent application evidence', 'Use independently reviewed task behavior; do not infer semantic adherence or hidden reasoning from a read.']
    ]) {
      const observation = row.activation?.find(item => item.stage === stage);
      if (observation?.state !== 'verified' && observation?.state !== 'not_applicable') add(stage, observation?.state || 'unknown', `${who}: ${meaning} is ${observation?.state?.replaceAll('_', ' ') || 'unknown'}.`, resolve);
    }
    const missing = ['input_tokens','cached_input_tokens','uncached_input_tokens','output_tokens','wall_ms','preparation_ms','verification_ms','human_review_ms','human_edit_ms'].filter(key => observed(row, key) === null);
    if (missing.length) add('missing_metrics', 'unknown', `${who}: unavailable ${missing.map(key => key.replaceAll('_', ' ')).join(', ')}.`, 'Record provider counters, wall time and separate preparation, verification and human effort. Do not treat missing values as zero or add nested timings twice.');
    const cost = priceCost(row, prices);
    if (cost.value === null) add('pricing', 'unknown', `${who}: ${cost.reason}.`, 'Configure a documented effective price for the observed provider/model/date; inference estimates still exclude enterprise labor and other overhead.');
    if (row.experiment?.order_index === undefined || row.experiment?.order_index === null) add('execution_order', 'unknown', `${who}: execution position unavailable.`, 'Record trial schedule and position before future execution; do not reconstruct them from display order.');
  }
  if (!pair.repeatable_efficacy) add('repetition', 'insufficient', `This pair has ${pair.sample_size ?? 'unknown'} reported matched observation(s); repeatability is not established.`, 'A separately approved repeated matched study needs distinct trial identities and recorded execution order. No confidence interval or significance is inferred here.');
  return gaps;
}
