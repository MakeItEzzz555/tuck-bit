import test from 'node:test';
import assert from 'node:assert/strict';
import {performance} from 'node:perf_hooks';
import {SCHEMA, validateDocument, mergeDocuments, createDemoDocument, exportJSON, exportCSV} from '../../web/js/data.js';
import {calendarInterval, aggregate, filterSessions, groupUsage, comparisonMetrics, priceCost, distribution, distributions} from '../../web/js/analytics.js';

const m = value => ({value, source: value === null ? null : 'provider event', status: value === null ? 'unknown' : 'observed'});
function fixture() {
  const doc = createDemoDocument();
  doc.sources[0].trust = 'repository';
  doc.sessions = doc.sessions.slice(0, 2).map((session, index) => ({...session, kind: 'native', arm: index ? 'B' : 'A', started_at: '2026-03-08T07:30:00.000Z', metrics: {...session.metrics, input_tokens: m(index ? 122935 : 152414), cached_input_tokens: m(index ? 95744 : 120064), uncached_input_tokens: m(index ? 27191 : 32350), output_tokens: m(index ? 233 : 282), wall_ms: m(index ? 23633 : 19590)}, acceptance: {accepted: true, required: 100, performed: 100, all_passed: true, provenance: 'independent_corpus_grader', independent: true}, qualification: {qualified: false, evaluator: 'existing evaluator', reasons: ['activation_unverified']}}));
  doc.comparisons = [{id: 'pair', baseline_id: doc.sessions[0].id, treatment_id: doc.sessions[1].id, kind: 'native', qualified: false, sample_size: 1, evaluator: 'existing evaluator', reasons: ['activation_unverified', 'policy_unverified']}];
  return doc;
}

test('gold totals reconcile with provider rows, never double-count cached input', () => {
  const result = aggregate(fixture().sessions);
  assert.equal(result.input_tokens.value, 275349);
  assert.equal(result.cached_input_tokens.value, 215808);
  assert.equal(result.uncached_input_tokens.value, 59541);
  assert.equal(result.output_tokens.value, 515);
  assert.equal(result.verified_success.value, 1);
});
test('unknown counters remain null and coverage partial; known zero stays zero', () => {
  const sessions = fixture().sessions;
  sessions[0].metrics.input_tokens = m(null);
  sessions[1].metrics.output_tokens = m(0);
  sessions[0].metrics.output_tokens = m(null);
  const totals = aggregate(sessions);
  assert.equal(totals.input_tokens.known, 1);
  assert.equal(totals.input_tokens.total, 2);
  assert.equal(totals.output_tokens.value, 0);
  assert.equal(totals.human_review_ms.value, null);
  assert.equal(aggregate([]).input_tokens.value, null);
});
test('strict cache validation and derived uncached counters', () => {
  let doc = fixture();
  doc.sessions[0].metrics.cached_input_tokens = m(200000);
  assert.throws(() => validateDocument(doc), /Cached input/);
  doc = fixture();
  doc.sessions[0].metrics.uncached_input_tokens = m(4);
  assert.throws(() => validateDocument(doc), /Conflicting uncached/);
  doc.sessions[0].metrics.uncached_input_tokens = m(null);
  assert.equal(validateDocument(doc).sessions[0].metrics.uncached_input_tokens.value, 32350);
  doc.sessions[0].metrics.cached_input_tokens = m(null);
  assert.equal(validateDocument(doc).sessions[0].metrics.uncached_input_tokens.value, null);
});
test('untrusted documents cannot self-authorize qualified evidence', () => {
  const doc = fixture();
  doc.comparisons[0].qualified = true;
  doc.sessions[0].qualification.qualified = true;
  assert.equal(validateDocument(doc).comparisons[0].qualified, false);
  assert.equal(validateDocument(doc).sessions[0].qualification.qualified, false);
  assert.equal(validateDocument(doc, {trusted: true}).comparisons[0].qualified, true);
});
test('duplicate receipts deduplicate; distinct reruns remain; identity conflicts reject', () => {
  const doc = validateDocument(fixture());
  const merged = mergeDocuments(doc, doc);
  assert.equal(merged.sessions.length, 2);
  assert.equal(merged.sources.length, 1);
  const rerun = structuredClone(doc);
  rerun.sessions[0].id += '-rerun';
  rerun.comparisons = [];
  assert.equal(mergeDocuments(doc, rerun).sessions.length, 3);
  const conflict = structuredClone(doc);
  conflict.sessions[0].metrics.input_tokens.value++;
  assert.throws(() => mergeDocuments(doc, conflict), /Conflicting session/);
});
test('source hash duplicates alias safely and same identifier changed hash rejects', () => {
  const doc = validateDocument(fixture());
  const alias = structuredClone(doc);
  alias.sources[0].id = 'alias';
  alias.sessions.forEach(session => { session.source_id = 'alias'; });
  assert.equal(mergeDocuments(doc, alias).sessions.length, 2);
  alias.sources[0].id = doc.sources[0].id;
  alias.sources[0].sha256 = 'a'.repeat(64);
  assert.throws(() => mergeDocuments(doc, alias), /Conflicting source identity/);
});
test('privacy fields, non-finite values, malformed/oversized schema are rejected', () => {
  assert.throws(() => validateDocument({schema: 'other'}), /schema/);
  const doc = fixture();
  doc.sessions[0].events[0].raw_command = 'secret';
  assert.throws(() => validateDocument(doc), /Private/);
  delete doc.sessions[0].events[0].raw_command;
  doc.sessions[0].metrics.input_tokens.value = Infinity;
  assert.throws(() => validateDocument(doc), /metric/);
  assert.throws(() => validateDocument(' '.repeat(8 * 1024 * 1024 + 1)), /4 MiB/);
});
test('full filter surface and half-open boundaries retain undated only outside date filters', () => {
  const sessions = fixture().sessions;
  sessions[1].started_at = null;
  assert.equal(filterSessions(sessions, {from: '2026-03-08T07:30:00Z', to: '2026-03-08T07:30:01Z'}).length, 1);
  assert.equal(filterSessions(sessions, {to: '2026-03-08T07:30:00Z'}).length, 0);
  assert.equal(filterSessions(sessions, {search: sessions[0].title, arm: 'A', model: 'Simulated model', kind: 'native'}).length, 1);
  assert.equal(filterSessions(sessions, {status: 'never'}).length, 0);
  assert.equal(filterSessions(sessions, {available: 'human_review_ms'}).length, 0);
  assert.throws(() => filterSessions(sessions, {from: 'bad'}), /interval/);
});
test('local days across spring DST and cross-midnight do not manufacture timestamps', () => {
  const rows = ['2026-03-08T04:59:59Z', '2026-03-08T05:00:00Z', '2026-03-08T06:59:59Z', '2026-03-08T07:00:00Z', '2026-03-09T03:59:59Z', '2026-03-09T04:00:00Z'].map((started_at, index) => ({...fixture().sessions[0], id: `s-${index}`, started_at}));
  rows.push({...rows[0], id: 'unknown', started_at: null});
  const groups = groupUsage(rows, 'day', 'America/New_York');
  assert.deepEqual(groups.buckets.map(row => [row.key, row.session_count]), [['2026-03-07', 1], ['2026-03-08', 4], ['2026-03-09', 1]]);
  assert.equal(groups.undated, 1);
  assert.equal(groupUsage(rows, 'day', 'UTC').buckets.length, 2);
});
test('fall DST repeated hour belongs to one local day; weekly Monday/monthly boundaries', () => {
  const dates = ['2026-11-01T05:30:00Z', '2026-11-01T06:30:00Z', '2026-11-02T05:00:00Z'];
  const rows = dates.map(started_at => ({...fixture().sessions[0], started_at}));
  assert.deepEqual(groupUsage(rows, 'day', 'America/New_York').buckets.map(row => row.session_count), [2, 1]);
  assert.deepEqual(groupUsage(rows, 'week', 'America/New_York').buckets.map(row => row.key), ['2026-10-26', '2026-11-02']);
  assert.equal(groupUsage(rows, 'month', 'America/New_York').buckets[0].key, '2026-11');
  assert.throws(() => groupUsage(rows, 'day', 'Invalid/Zone'));
});
test('V51 lower-input but slower observations preserve signed direction and disqualification', () => {
  const doc = fixture();
  const result = comparisonMetrics(doc.comparisons[0], doc.sessions);
  assert.equal(result.metrics.input_tokens.delta, -29479);
  assert.equal(result.metrics.wall_ms.delta, 4043);
  assert.equal(result.metrics.output_tokens.delta, -49);
  assert.equal(result.metrics.input_tokens.percent.toFixed(1), '-19.3');
  assert.equal(result.metrics.uncached_input_tokens.percent.toFixed(1), '-15.9');
  assert.equal(result.metrics.output_tokens.percent.toFixed(1), '-17.4');
  assert.equal(result.metrics.wall_ms.percent.toFixed(1), '20.6');
  assert.equal(result.attributable, false);
  assert.equal(result.metrics.human_review_ms.delta, null);
});
test('qualified observed improvements and regressions use authoritative qualification only', () => {
  const doc = fixture();
  doc.comparisons[0].qualified = true;
  const result = comparisonMetrics(doc.comparisons[0], doc.sessions);
  assert.equal(result.attributable, true);
  assert(result.metrics.input_tokens.delta < 0);
  assert(result.metrics.wall_ms.delta > 0);
  doc.sessions[1].kind = 'control';
  assert.equal(comparisonMetrics(doc.comparisons[0], doc.sessions).attributable, false);
  doc.sessions[1].kind = 'demo';
  assert.equal(comparisonMetrics(doc.comparisons[0], doc.sessions).simulated, true);
});
test('effective pricing requires complete rates and observed components, no cached double-count', () => {
  const session = fixture().sessions[0];
  const configuration = {schema: 'tuckbit.prices/1', version: 'example-v1', rates: [{provider: session.provider, model: session.model, currency: 'USD', source: 'manually configured example rates', effective_from: '2026-01-01T00:00:00Z', uncached_input_per_million: 2, cached_input_per_million: 0.5, output_per_million: 8}]};
  assert.equal(priceCost(session, configuration).value, (session.metrics.uncached_input_tokens.value*2+session.metrics.cached_input_tokens.value*0.5+session.metrics.output_tokens.value*8)/1e6);
  assert.equal(priceCost(session, configuration).status, 'scenario');
  const changed = structuredClone(configuration);
  changed.rates[0].output_per_million = 9;
  assert.notEqual(priceCost(session, configuration).rate.output_per_million, priceCost(session, changed).rate.output_per_million);
  changed.rates[0].effective_to = '2026-03-08T07:30:00Z';
  assert.equal(priceCost(session, changed).value, null);
  assert.equal(priceCost(session, null).value, null);
  session.metrics.cached_input_tokens = m(null);
  assert.equal(priceCost(session, configuration).value, null);
});
test('activation distinct states survive and baseline stages remain not-applicable', () => {
  const doc = fixture();
  doc.sessions[0].activation = [];
  const states = ['verified', 'not_observed', 'unknown', 'explicitly_absent', 'not_applicable', 'verified', 'unknown'];
  doc.sessions[1].activation.forEach((item, index) => { item.state = states[index]; });
  const normalized = validateDocument(doc);
  assert(normalized.sessions[0].activation.every(item => item.state === 'not_applicable'));
  assert.deepEqual(normalized.sessions[1].activation.map(item => item.state), states);
});
test('out-of-order events sort and exact duplicate public identities deduplicate', () => {
  const doc = fixture();
  doc.sessions[0].events = [{id: 'z', order: 2, category: 'test'}, {id: 'a', order: 1, category: 'read'}, {id: 'z', order: 2, category: 'test'}];
  assert.deepEqual(validateDocument(doc).sessions[0].events.map(event => event.id), ['a', 'z']);
  doc.sessions[0].events.push({id: 'z', order: 9, category: 'test'});
  assert.throws(() => validateDocument(doc), /Conflicting event/);
});
test('JSON round trip preserves missingness/eligibility; CSV neutralizes formulas', () => {
  const doc = validateDocument(fixture());
  assert.deepEqual(validateDocument(exportJSON(doc)), doc);
  doc.sessions[0].title = '=IMPORTXML("private")';
  const csv = exportCSV(doc);
  assert(csv.includes("'=IMPORTXML"));
  assert(csv.includes('"qualification"'));
  assert(csv.includes('"false"'));
});
test('distribution groups by actual identities with null coverage and outliers', () => {
  assert.equal(distribution([]).median, null);
  assert.deepEqual(distribution([1, 2, 2, 3, 3, 4, 100]).outliers, [100]);
  assert.equal(distributions(fixture().sessions, 'model')[0].count, 2);
});
test('5,000-session deterministic aggregation/filter/calendar baseline', () => {
  const base = fixture().sessions[0];
  const rows = Array.from({length: 5000}, (_, index) => ({...base, id: `perf-${index}`, started_at: new Date(Date.UTC(2026, 0, 1 + index % 90, index % 24)).toISOString()}));
  const start = performance.now();
  const totals = aggregate(rows);
  const filtered = filterSessions(rows, {search: 'synthetic', from: '2026-01-01T00:00:00Z', to: '2026-04-01T00:00:00Z'});
  const grouped = groupUsage(rows, 'week', 'America/New_York');
  const elapsed = performance.now() - start;
  assert.equal(totals.input_tokens.value, 152414 * 5000);
  assert.equal(filtered.length, 5000);
  assert.equal(grouped.buckets.reduce((sum, bucket) => sum + bucket.session_count, 0), 5000);
  console.log(`PERFORMANCE 5000 sessions aggregate/filter/calendar: ${elapsed.toFixed(2)} ms; measured local control, not native agent efficiency`);
});
test('unattempted arm remains in directory but never inflates usage or attempt denominators', () => {
  const doc = fixture();
  const missing = {...doc.sessions[0], id: 'B-unattempted', arm: 'B', status: 'unattempted'};
  const result = aggregate([...doc.sessions, missing]);
  assert.equal(result.session_count, 2);
  assert.equal(result.unattempted, 1);
  assert.equal(result.input_tokens.value, 275349);
  assert.equal(result.verified_success.total, 2);
});
test('incomplete mandatory validation cannot count as verified success', () => {
  const rows = fixture().sessions;
  rows[0].acceptance = {independent: true, accepted: true, all_passed: null, required: 100, performed: 90};
  assert.equal(aggregate(rows).verified_success.known, 1);
  assert.equal(aggregate(rows).verified_success.total, 2);
  rows[0].acceptance.accepted = false;
  assert.equal(aggregate(rows).verified_success.value, 0.5);
});
test('original reported decision survives untrusted reimport downgrade', () => {
  const doc = fixture();
  doc.comparisons[0].qualified = true;
  doc.sessions[0].qualification.qualified = true;
  const downgraded = validateDocument(doc);
  assert.equal(downgraded.comparisons[0].reported_qualified, true);
  assert.equal(downgraded.sessions[0].qualification.reported_qualified, true);
  assert.deepEqual(validateDocument(exportJSON(downgraded)), downgraded);
});
test('invalid calendar dates and malformed acceptance/policy reject', () => {
  let doc = fixture();
  doc.sessions[0].started_at = '2026-02-31T10:00:00Z';
  assert.throws(() => validateDocument(doc), /calendar/);
  doc = fixture();
  doc.sessions[0].acceptance.accepted = 'yes';
  assert.throws(() => validateDocument(doc), /acceptance/);
  doc = fixture();
  doc.sessions[0].policy.qualified = 'yes';
  assert.throws(() => validateDocument(doc), /policy/);
});
test('prototype pollution keys and unsupported nested private data reject', () => {
  const doc = fixture();
  doc.sessions[0].context = JSON.parse('{"constructor":{"prototype":{"polluted":true}}}');
  assert.throws(() => validateDocument(doc), /Private/);
  assert.equal({}.polluted, undefined);
});
test('same attempt in independently grouped source selections deduplicates by immutable attempt identity', () => {
  const doc = validateDocument(fixture());
  const regrouped = structuredClone(doc);
  regrouped.sources[0].id = 'independent-selected-batch';
  regrouped.sources[0].sha256 = 'b'.repeat(64);
  regrouped.sessions.forEach(session => { session.source_id = regrouped.sources[0].id; });
  assert.equal(mergeDocuments(doc, regrouped).sessions.length, 2);
});
test('paired CSV exports signed changes, original eligibility, and unknown fields explicitly', () => {
  const csv = exportCSV(validateDocument(fixture()), {type: 'comparisons'});
  assert(csv.includes('"delta_input_tokens"'));
  assert(csv.includes('"delta_wall_ms"'));
  assert(csv.includes('"-29479"'));
  assert(csv.includes('"4043"'));
  const sessions = exportCSV(validateDocument(fixture()));
  assert(sessions.includes('"human_review_ms_status"'));
  assert(sessions.includes('"unknown"'));
  assert(sessions.includes('"activation_delivery_verified"'));
});
test('calendar intervals map inclusive picker dates to exclusive UTC boundaries through DST', () => {
  const spring = calendarInterval({period: 'custom', from: '2026-03-08', to: '2026-03-08', timeZone: 'America/New_York'});
  assert.deepEqual(spring, {from: '2026-03-08T05:00:00.000Z', to: '2026-03-09T04:00:00.000Z'});
  assert.equal(Date.parse(spring.to) - Date.parse(spring.from), 23 * 3600000);
  const fall = calendarInterval({period: 'custom', from: '2026-11-01', to: '2026-11-01', timeZone: 'America/New_York'});
  assert.equal(Date.parse(fall.to) - Date.parse(fall.from), 25 * 3600000);
  const today = calendarInterval({period: 'today', now: '2026-03-09T03:30:00Z', timeZone: 'America/New_York'});
  assert.deepEqual(today, spring);
  assert.equal(calendarInterval({period: '7d', now: '2026-03-09T03:30:00Z', timeZone: 'America/New_York'}).from, '2026-03-02T05:00:00.000Z');
  assert.equal(calendarInterval({period: '30d', now: '2026-03-09T03:30:00Z', timeZone: 'America/New_York'}).from, '2026-02-07T05:00:00.000Z');
  assert.deepEqual(calendarInterval(), {from: null, to: null});
});
test('calendar intervals validate dates and nonexistent local days without guessing', () => {
  assert.throws(() => calendarInterval({period: 'custom', from: '2026-02-30'}), /calendar/);
  assert.throws(() => calendarInterval({period: 'custom', from: '2026-03-09', to: '2026-03-08'}), /range/);
  assert.throws(() => calendarInterval({period: 'custom', from: '2011-12-30', timeZone: 'Pacific/Apia'}), /does not exist/);
  assert.deepEqual(calendarInterval({period: 'custom', from: '2026-01-01', timeZone: 'Asia/Kathmandu'}), {from: '2025-12-31T18:15:00.000Z', to: null});
});
test('fractional tokens, null measured values and non-boolean qualification reject', () => {
  let doc = fixture();
  doc.sessions[0].metrics.output_tokens.value = 0.5;
  assert.throws(() => validateDocument(doc), /token counter/);
  doc = fixture();
  doc.sessions[0].metrics.output_tokens = {value: null, status: 'measured', source: 'event'};
  assert.throws(() => validateDocument(doc), /metric/);
  doc = fixture();
  doc.sessions[0].qualification.qualified = 'yes';
  assert.throws(() => validateDocument(doc), /qualification/);
});
test('self-reported completion is distinct from independent correctness evidence', () => {
  const doc = fixture();
  const personal = structuredClone(doc.sessions[0]);
  personal.acceptance.independent = false;
  personal.acceptance.provenance = 'caller_reported_not_independent';
  const result = aggregate([personal]);
  assert.equal(result.verified_success.value, null);
  assert.equal(result.verified_success.known, 0);
  const imported = validateDocument(doc);
  assert.equal(imported.sessions[0].acceptance.independent, false);
  assert.equal(imported.sessions[0].acceptance.reported_independent, true);
  assert.equal(aggregate(imported.sessions).verified_success.value, null);
  assert.equal(aggregate(validateDocument(doc, {trusted: true}).sessions).verified_success.value, 1);
});
test('shared batch setup is retained in source rows but excluded from additive per-session totals', () => {
  const doc = fixture();
  doc.sessions.forEach(session => { session.metrics.batch_setup_ms = m(4000); session.metrics.human_edit_ms = m(10); session.metrics.context_bytes = m(200); });
  const normalized = validateDocument(doc, {trusted: true});
  assert.equal(normalized.sessions[0].metrics.batch_setup_ms.value, 4000);
  assert.equal(aggregate(normalized.sessions).batch_setup_ms, undefined);
  assert.equal(aggregate(normalized.sessions).human_edit_ms.value, 20);
  assert.equal(aggregate(normalized.sessions).context_bytes.value, 400);
});
test('unverified external native labels become imported observations without losing reported kinds', () => {
  const doc = fixture();
  doc.comparisons[0].qualified = true;
  const external = validateDocument(doc);
  assert(external.sessions.every(session => session.kind === 'session' && session.reported_kind === 'native'));
  assert.equal(external.comparisons[0].kind, 'session');
  assert.equal(external.comparisons[0].reported_kind, 'native');
  assert.equal(comparisonMetrics(external.comparisons[0], external.sessions).attributable, false);
  assert.deepEqual(validateDocument(exportJSON(external)), external);
  assert.equal(validateDocument(doc, {trusted: true}).sessions[0].kind, 'native');
  const control = createDemoDocument();
  control.sessions[0].kind = 'control';
  assert.equal(validateDocument(control).sessions[0].kind, 'control');
});
test('workspace merge enforces cumulative counts and bytes without mutating prior documents', () => {
  const base = validateDocument(createDemoDocument());
  const before = exportJSON(base);
  const batches = Array.from({length: 34}, (_, batch) => {
    const doc = structuredClone(base);
    doc.sessions.forEach(session => { session.id += `-batch-${batch}`; });
    doc.comparisons = [];
    return doc;
  });
  assert.throws(() => mergeDocuments(...batches), /Workspace.*limit|Workspace exceeds/);
  assert.equal(exportJSON(base), before);
  const large = structuredClone(base);
  large.sessions = large.sessions.slice(0, 1); large.comparisons = [];
  large.sessions[0].limitations = Array.from({length: 100}, () => 'bounded detail'.repeat(100));
  const sized = Array.from({length: 35}, (_, index) => { const doc = structuredClone(large); doc.sessions[0].id += `-${index}`; return doc; });
  assert.throws(() => mergeDocuments(...sized), /4 MiB/);
});
test('trusted original receipt revalidation upgrades retained claims, while altered immutable content rejects', () => {
  const doc = fixture();
  doc.sessions.forEach((session, index) => {
    session.id = (index ? 'b' : 'a').repeat(64);
    session.receipt_sha256 = session.id;
    session.qualification.evaluator = 'v5_evaluation.per_task_report';
  });
  doc.comparisons[0] = {...doc.comparisons[0], id: 'c'.repeat(64), baseline_id: doc.sessions[0].id, treatment_id: doc.sessions[1].id, qualified: true, quality_qualified: true, evaluator: 'v5_evaluation.per_task_report'};
  const trusted = validateDocument(doc, {trusted: true});
  const retained = validateDocument(exportJSON(trusted));
  assert.equal(retained.sessions[0].acceptance.independent, false);
  const upgraded = mergeDocuments(retained, trusted);
  assert.equal(upgraded.sessions.length, 2);
  assert.equal(upgraded.sessions[0].acceptance.independent, true);
  assert.equal(upgraded.sessions[0].kind, 'native');
  assert.equal(upgraded.comparisons[0].qualified, true);
  assert.equal(mergeDocuments(trusted, retained).sessions[0].acceptance.independent, true);
  const changed = structuredClone(retained);
  changed.sessions[0].metrics.output_tokens.value++;
  assert.throws(() => mergeDocuments(changed, trusted), /Conflicting session/);
  const forged = structuredClone(trusted);
  assert.throws(() => mergeDocuments(retained, forged), /Conflicting session/);
});

test('Codex client cost retains limited confidence, excludes mixed identities and price transitions', () => {
  const row = fixture().sessions[0];
  row.kind = 'session';
  row.metrics.input_tokens.source = 'codex_client_cumulative';
  row.metrics.session_elapsed_ms = m(1000);
  const configuration = {schema:'tuckbit.prices/1',version:'TEST ONLY example rates',rates:[{provider:row.provider,model:row.model,currency:'USD',source:'synthetic rate control, not provider prices',effective_from:'2026-01-01T00:00:00Z',effective_to:null,uncached_input_per_million:2,cached_input_per_million:0.5,output_per_million:8}]};
  assert.equal(priceCost(row,configuration).confidence,'limited');
  assert.match(priceCost(row,configuration).reason,/estimates or replay/);
  assert.equal(priceCost(row,configuration).value,(row.metrics.uncached_input_tokens.value*2+row.metrics.cached_input_tokens.value*0.5+row.metrics.output_tokens.value*8)/1e6);
  assert.equal(priceCost(row,configuration).status,'scenario');
  const mixed=structuredClone(row);mixed.model=null;
  assert.equal(priceCost(mixed,configuration).value,null);
  configuration.rates[0].effective_to=new Date(Date.parse(row.started_at)+500).toISOString();
  assert.equal(priceCost(row,configuration).value,null);
  assert.match(priceCost(row,configuration).reason,/validity boundary/);
});

test('contract-qualified source-bound receipts cannot imply independently observed savings', () => {
  const doc = fixture();
  doc.comparisons[0].qualified = true;
  doc.sessions.forEach(row => { row.acceptance.independent = false; row.acceptance.provenance = 'source_bound_receipt_reported_grading'; });
  assert.equal(comparisonMetrics(doc.comparisons[0], doc.sessions).qualified, true);
  assert.equal(comparisonMetrics(doc.comparisons[0], doc.sessions).attributable, false);
  assert.equal(aggregate(doc.sessions).verified_success.value, null);
});

test('legacy V8 grading labels revalidate only against source-bound original receipts', () => {
  const doc = fixture();
  doc.sources[0].format = 'tuckbit_receipts';
  doc.sessions.forEach((row, index) => {
    row.id = (index ? 'b' : 'a').repeat(64); row.receipt_sha256 = row.id;
    row.qualification.evaluator = 'v5_evaluation.per_task_report';
  });
  doc.comparisons = [];
  const legacy = validateDocument(exportJSON(doc));
  const current = structuredClone(doc);
  current.sessions.forEach(row => { row.acceptance.independent = false; row.acceptance.provenance = 'source_bound_receipt_reported_grading'; });
  const original = validateDocument(current, {trusted: true});
  const merged = mergeDocuments(legacy, original);
  assert.equal(merged.sessions.length, 2);
  assert(merged.sessions.every(row => row.acceptance.independent === false));
  assert(merged.sessions.every(row => row.acceptance.provenance === 'source_bound_receipt_reported_grading'));
  assert.equal(mergeDocuments(original, legacy).sessions.length, 2);
  const changed = structuredClone(legacy); changed.sessions[0].metrics.output_tokens.value++;
  assert.throws(() => mergeDocuments(changed, original), /Conflicting session/);
  assert.throws(() => mergeDocuments(legacy, structuredClone(original)), /Conflicting session/);
});
