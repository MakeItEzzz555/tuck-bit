// Independent arithmetic fixtures; fictional rates and observations, no model calls.
import test from 'node:test';
import assert from 'node:assert/strict';
import {costCoverage,usageEconomics,periodComparison,priceCost,validatePrices,groupUsage,benchmarkArmDistributions} from '../../web/js/analytics.js';
import {costTrend} from '../../web/js/charts.js';
import {validateDocument,createDemoDocument,mergeDocuments} from '../../web/js/data.js';
const m=(value,source='test observation')=>({value,status:value===null?'unknown':'observed',source:value===null?null:source});
const prices={schema:'tuckbit.prices/1',version:'fictional-v7-control',rates:[{provider:'OpenAI',model:'test-model',currency:'USD',effective_from:'2026-01-01T00:00:00Z',effective_to:null,uncached_input_per_million:2,cached_input_per_million:0.5,output_per_million:8,source:'TEST ONLY manual reference'}]};
function session(id,started_at='2026-03-08T12:00:00Z',extra={}) {
  return {id,source_id:'source-'+id,kind:'session',provider:'OpenAI',model:'test-model',project:'project:hashed',started_at,status:'observed',metrics:{input_tokens:m(1000),cached_input_tokens:m(400),uncached_input_tokens:m(600),output_tokens:m(100),session_elapsed_ms:m(1000),tool_calls_observed:m(2)},...extra};
}
test('legacy configured scenario restores three-rate arithmetic without claiming actual billing',()=>{
  const rows=[session('a'),session('b')];
  const group=usageEconomics(rows,prices).groups[0];
  assert.equal(group.usage.input_tokens.value,2000);assert.equal(group.usage.cached_input_tokens.value,800);
  assert.equal(group.usage.uncached_input_tokens.value,1200);assert.equal(group.usage.output_tokens.value,200);
  assert.equal(group.cost.currencies[0].value,0.0044);assert.equal(group.cost.covered,2);assert.equal(group.cost.complete,true);
  const cost=priceCost(rows[0],prices);assert.equal(cost.value,0.0022);assert.equal(cost.status,'scenario');assert.equal(cost.label,'Legacy configured cost scenario');
  assert.match(cost.reason,/Actual API-equivalent billing remains incomplete/);assert.match(cost.reason,/Subscription charges and quota usage are unavailable/);
  assert.match(group.cost.assumption_basis,/Cache writes are not verified/);assert.equal(group.cost.currencies[0].rates[0].observations,2);
  assert.equal(priceCost(rows[0],prices).rate.version,prices.version);assert.equal(group.source_ids.length,2);
});
test('duplicate observations count once; conflicting identity refuses a total',()=>{
  const a=session('a');const row=usageEconomics([a,structuredClone(a)],prices).groups[0];
  assert.equal(row.usage.input_tokens.value,1000);assert.equal(row.cost.complete,true);assert.equal(row.cost.currencies[0].value,0.0022);
  const changed=structuredClone(a);changed.metrics.input_tokens=m(2000);
  assert.throws(()=>usageEconomics([a,changed],prices),/Conflicting/);
});
test('missing counters stay partial; known zero scenario does not claim zero actual charges',()=>{
  const a=session('a'),b=session('b');b.metrics.output_tokens=m(null);
  const cost=costCoverage([a,b],prices);
  assert.equal(cost.currencies[0].value,0.0022);assert.equal(cost.covered,1);assert.equal(cost.complete,false);assert.equal(cost.missing,1);assert.equal(cost.reasons.length,1);
  assert.equal(costCoverage([b],prices).currencies.length,0);assert.equal(costCoverage([b],prices).confidence,'unknown');assert.equal(costCoverage([],prices).complete,false);
  a.metrics.output_tokens=m(0);a.metrics.input_tokens=m(0);a.metrics.cached_input_tokens=m(0);a.metrics.uncached_input_tokens=m(0);
  assert.equal(costCoverage([a],prices).currencies[0].value,0);
  assert.equal(priceCost(a,prices).status,'scenario');assert.match(priceCost(a,prices).reason,/billing remains incomplete/);
});
test('undated and incomplete spans are unallocated but visible in project/model/provider breakdowns',()=>{
  const a=session('a',null),b=session('b');b.metrics.session_elapsed_ms=m(null);
  const report=usageEconomics([a,b],prices);
  assert.equal(report.groups.length,0);assert.equal(report.unallocated.length,2);
  for(const dimension of ['model','provider','project'])assert.equal(usageEconomics([a,b],prices,{dimension}).groups[0].usage.input_tokens.value,2000);
});
test('cross-day sessions are never prorated; a fitting week/month can use the whole session',()=>{
  const a=session('a','2026-03-03T23:59:59Z');a.metrics.session_elapsed_ms=m(2000);
  assert.equal(usageEconomics([a],prices).unallocated.length,1);
  for(const granularity of ['week','month'])assert.equal(usageEconomics([a],prices,{granularity}).groups[0].usage.input_tokens.value,1000);
  const edge=session('edge','2026-03-03T23:59:59Z');edge.metrics.session_elapsed_ms=m(1000);
  assert.equal(usageEconomics([edge],prices).unallocated.length,1);
});
test('DST and local midnight use IANA calendar buckets without 24-hour assumptions',()=>{
  const a=session('a','2026-03-08T06:59:59Z');a.metrics.session_elapsed_ms=m(2000);
  const report=usageEconomics([a],prices,{timeZone:'America/New_York'});
  assert.equal(report.groups[0].key,'2026-03-08');
  const b=session('b','2026-11-01T05:59:59Z');b.metrics.session_elapsed_ms=m(2000);
  assert.equal(usageEconomics([b],prices,{timeZone:'America/New_York'}).groups[0].key,'2026-11-01');
  const c=session('c','2026-03-09T03:59:59Z');c.metrics.session_elapsed_ms=m(2000);
  assert.equal(usageEconomics([c],prices,{timeZone:'America/New_York'}).unallocated.length,1);
});
test('week and month rollovers retain separate exact groups and previous calendar identity',()=>{
  const rows=[session('a','2026-01-31T12:00:00Z'),session('b','2026-02-01T12:00:00Z')];
  const months=usageEconomics(rows,prices,{granularity:'month'}).groups;
  assert.deepEqual(months.map(row=>row.key),['2026-01','2026-02']);
  assert.equal(periodComparison(months,'2026-02','month').cost.delta,0);
  assert.equal(usageEconomics(rows,prices,{granularity:'week'}).groups.length,1);
  rows[1].started_at='2026-02-02T12:00:00Z';
  const weeks=usageEconomics(rows,prices,{granularity:'week'}).groups;
  assert.deepEqual(weeks.map(row=>row.key),['2026-01-26','2026-02-02']);
  assert.equal(periodComparison(weeks,'2026-02-02','week').previousKey,'2026-01-26');
});
test('effective-date changes reconcile independent rates and retain each rate provenance',()=>{
  const config=structuredClone(prices);config.rates[0].effective_to='2026-04-01T00:00:00Z';
  config.rates.push({...config.rates[0],effective_from:'2026-04-01T00:00:00Z',effective_to:null,output_per_million:10,source:'TEST ONLY second rate'});
  assert.equal(priceCost(session('a','2026-03-31T12:00:00Z'),config).rate.output_per_million,8);
  assert.equal(priceCost(session('b','2026-04-01T12:00:00Z'),config).rate.output_per_million,10);
  const crossing=session('c','2026-03-31T23:59:59Z');crossing.metrics.session_elapsed_ms=m(2000);
  assert.equal(priceCost(crossing,config).value,null);
  const unknown=session('u');unknown.metrics.session_elapsed_ms=m(null);
  assert.equal(priceCost(unknown,config).value,null);
});
test('mixed currencies remain separate and cannot produce a period cost delta',()=>{
  const config=structuredClone(prices);config.rates.push({...config.rates[0],provider:'OtherProvider',currency:'EUR'});
  const a=session('a'),b=session('b','2026-03-09T12:00:00Z',{provider:'OtherProvider'});
  const costs=costCoverage([a,b],config);assert.equal(costs.currencies.length,2);assert.equal(costs.complete,true);assert.deepEqual(costs.currencies.map(row=>row.value),[0.0022,0.0022]);
  assert.equal(costs.value,undefined);
  assert.equal(periodComparison(usageEconomics([a,b],config).groups,'2026-03-09').cost.delta,null);
});
test('missing model/rate components and malformed dates/negative prices cannot become estimates',()=>{
  for(const mutation of [c=>delete c.rates[0].output_per_million,c=>c.rates[0].cached_input_per_million=-1,c=>c.rates[0].effective_from='2026-02-30T00:00:00Z',c=>c.rates[0].effective_to='2025-01-01T00:00:00Z']) {
    const config=structuredClone(prices);mutation(config);assert.throws(()=>validatePrices(config));assert.equal(priceCost(session('a'),config).value,null);
  }
  assert.equal(priceCost(session('a',undefined,{model:null}),prices).value,null);
  const config=structuredClone(prices);config.rates.push({...config.rates[0]});assert.equal(priceCost(session('a'),config).value,null);
});
test('invalid/conflicting counters cannot be priced',()=>{
  for(const [field,value] of [['cached_input_tokens',4000],['input_tokens',-1],['output_tokens',NaN],['uncached_input_tokens',100]]) {
    const a=session('a');a.metrics[field]=m(value);assert.equal(priceCost(a,prices).value,null);
  }
});
test('period deltas require complete recorded coverage; missing periods are unknown',()=>{
  const a=session('a'),b=session('b','2026-03-09T12:00:00Z');
  b.metrics.input_tokens=m(2000);b.metrics.uncached_input_tokens=m(1600);
  const groups=usageEconomics([a,b],prices).groups;
  const comparison=periodComparison(groups,'2026-03-09');
  assert.equal(comparison.metrics.input_tokens.delta,1000);assert.ok(Math.abs(comparison.cost.delta-0.002)<1e-12);assert.equal(comparison.cost.label,'Legacy configured cost scenario');assert.match(comparison.cost.assumption_basis,/billing remains incomplete/);
  assert.equal(periodComparison(groups,'2026-03-08').metrics.input_tokens.delta,null);
  assert.equal(periodComparison(groups,'2026-03-09','day',1).cost.delta,null);
  b.metrics.output_tokens=m(null);const partial=periodComparison(usageEconomics([a,b],prices).groups,'2026-03-09');
  assert.equal(partial.metrics.output_tokens.delta,null);assert.equal(partial.cost.delta,null);
});
test('synthetic controls and unattempted arms never enter actual usage economics',()=>{
  const rows=[session('a'),session('b',undefined,{kind:'demo'}),session('c',undefined,{kind:'control'}),session('d',undefined,{status:'unattempted'})];
  assert.equal(usageEconomics(rows,prices).total,1);assert.equal(costCoverage(rows,prices).excluded,3);
});
test('analytics never promote qualification or mutate original identities and observations',()=>{
  const document=validateDocument(createDemoDocument());const original=JSON.stringify(document);
  usageEconomics(document.sessions,prices);costCoverage(document.sessions,prices);
  assert.equal(JSON.stringify(document),original);assert.equal(mergeDocuments(document,document).sessions.length,document.sessions.length);
});
test('calendar cohorts preserve legacy behavior; allocated economics explain the narrower scope',()=>{
  const a=session('a');a.metrics.session_elapsed_ms=m(86400000);
  assert.equal(groupUsage([a]).buckets[0].input_tokens.value,1000);
  assert.equal(usageEconomics([a],prices).allocated,0);
});
test('clipped week/month ranges are visibly partial and cannot produce period deltas',()=>{
  const rows=[session('a','2026-02-01T12:00:00Z'),session('b','2026-03-08T12:00:00Z')];
  const report=usageEconomics(rows,prices,{granularity:'month',from:'2026-02-15T00:00:00Z',to:'2026-03-15T00:00:00Z'});
  assert.equal(report.groups[0].period_clipped,true);assert.equal(report.groups[1].period_clipped,true);
  assert.equal(periodComparison(report.groups,'2026-03','month').cost.delta,null);
  assert.equal(periodComparison(report.groups,'2026-03','month').metrics.input_tokens.delta,null);
});
test('same model ID on different providers keeps separate model/provider groups',()=>{
  const a=session('a'),b=session('b',undefined,{provider:'AnotherProvider'});
  const groups=usageEconomics([a,b],prices,{dimension:'model'}).groups;
  assert.equal(groups.length,2);assert.deepEqual(groups.map(row=>row.key),['AnotherProvider / test-model','OpenAI / test-model']);
  assert.equal(groups[0].cost.missing,1);assert.equal(groups[1].cost.covered,1);
});

test('write counters cannot be silently priced as ordinary input or subscription charges',()=>{
  const a=session('a');
  const original=JSON.stringify(a.metrics);
  assert.equal(validatePrices(prices),prices);
  for(const source of ['legacy','subscription','enterprise','unknown']) {
    a.metrics.input_tokens.source=source;
    a.metrics.cache_write_input_tokens=m(200);
    const result=priceCost(a,prices);
    assert.equal(result.value,null);assert.equal(result.status,'incomplete');
    assert.match(result.reason,/billing mode.*cache-write/);
    assert.match(result.reason,/Subscription charges and quota usage are unavailable/);
    assert.equal(a.metrics.uncached_input_tokens.value,600);
  }
  assert.equal(JSON.parse(original).uncached_input_tokens.value,1000-400);
});

test('absent writes remain unknown, explicit incompatible write observations refuse scenarios',()=>{
  const a=session('a');const original=JSON.stringify(a);
  assert.equal(priceCost(a,prices).value,0.0022);assert.equal(JSON.stringify(a),original);
  assert.match(priceCost(a,prices).reason,/Cache writes are not verified by absent counters/);
  for(const key of ['cache_write_input_tokens','cache_creation_input_tokens','cache_write_5m_input_tokens']) {
    for(const value of [1,null,-1,NaN]) {const b=structuredClone(a);b.metrics[key]=m(value);assert.equal(priceCost(b,prices).value,null);}
    const b=structuredClone(a);b.metrics[key]=m(0);assert.equal(priceCost(b,prices).value,0.0022);
  }
});
test('client confidence and rate provenance survive coverage, period differences and arm distributions',()=>{
  const a=session('a'),b=session('b','2026-03-09T12:00:00Z');a.metrics.input_tokens.source='codex_client_cumulative';
  const cost=priceCost(a,prices);assert.equal(cost.confidence,'limited');assert.match(cost.reason,/estimates or replay/);
  const coverage=costCoverage([a,b],prices);assert.equal(coverage.confidence,'limited');assert.equal(coverage.currencies[0].limited,1);
  assert.deepEqual(coverage.currencies[0].rates[0],{...prices.rates[0],version:prices.version,observations:2});
  const delta=periodComparison(usageEconomics([a,b],prices).groups,'2026-03-09').cost;
  assert.equal(delta.delta,0);assert.equal(delta.confidence,'limited');
  a.task='Fictional scenario control';const arm=benchmarkArmDistributions([a],{prices})[0];assert.equal(arm.costs[0].median,0.0022);assert.equal(arm.cost_coverage.confidence,'limited');assert.match(arm.cost_coverage.assumption_basis,/billing remains incomplete/);
  const chart=costTrend(usageEconomics([a,b],prices).groups,'USD');assert.match(chart,/Legacy configured cost scenario/);assert.match(chart,/Confidence: limited/);assert.match(chart,/Cache writes are not verified/);
});
test('unknown currencies and numeric overflow never invent a combined or finite estimate',()=>{
  const config=structuredClone(prices);config.rates[0].currency=null;assert.equal(priceCost(session('a'),config).value,null);
  config.rates[0].currency='USD';config.rates[0].output_per_million=Number.MAX_VALUE;assert.equal(priceCost(session('a'),config).value,null);
});
