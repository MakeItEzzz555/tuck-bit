import {existsSync} from 'node:fs';
import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {benchmarkGroups, benchmarkArmDistributions, benchmarkStratum, evidenceGaps, comparisonMetrics} from '../../web/js/analytics.js';
import {createDemoDocument, validateDocument, exportJSON, exportCSV} from '../../web/js/data.js';

const metric = value => ({value, source: value === null ? 'unavailable' : 'TEST ONLY', status: value === null ? 'unknown' : 'observed'});
function fixture() {
  const row = createDemoDocument().sessions[0];
  row.kind = 'control'; row.task = 'D08-medium'; row.domain = 'D08'; row.complexity = 'medium';
  row.identity = Object.fromEntries(['client','configuration','dependencies','environment','model','permissions','runtime','source','task'].map(key => [key, key.padEnd(64, 'a')]));
  row.bundle_sha256 = 'b'.repeat(64);row.trial=1;
  row.acceptance = {independent:true,accepted:true,required:33,performed:33,all_passed:true};
  row.experiment = {order_index:0,block_order:'ABC',benchmark_rerun:0};
  row.metrics.input_tokens=metric(100);row.metrics.cached_input_tokens=metric(50);row.metrics.uncached_input_tokens=metric(50); row.metrics.wall_ms=metric(1000);
  const a = {...structuredClone(row),id:'a',arm:'A',status:'accepted',identity:{...row.identity,treatment:'baseline'}};
  const b = {...structuredClone(row),id:'b',arm:'B',status:'accepted',identity:{...row.identity,treatment:'skill'},experiment:{...row.experiment,order_index:1}};
  const pair={id:'pair',baseline_id:'a',treatment_id:'b',qualified:false,reasons:['activation_unverified'],sample_size:1};
  return {a,b,pair};
}

test('benchmark strata retain backend qualification and full original attempt denominators',()=>{
  const {a,b,pair}=fixture();const groups=benchmarkGroups([a,b],[pair]);
  assert.equal(groups.length,1);assert.equal(groups[0].pairs[0],pair);assert.equal(groups[0].qualified,0);assert.equal(pair.qualified,false);
  pair.qualified=true;assert.equal(benchmarkGroups([a,b],[pair])[0].qualified,1);
});
for(const key of ['task','complexity','provider','model','bundle_sha256'])test(`different ${key} cannot pool`,()=>{
  const {a,b}=fixture();b[key]='DIFFERENT';assert.equal(benchmarkGroups([a,b]).length,2);
});
for(const key of ['source','task','model','environment','permissions','configuration','dependencies','client','runtime'])test(`different ${key} fingerprint cannot pool`,()=>{
  const {a,b}=fixture();b.identity[key]='changed';assert.notEqual(benchmarkStratum(a),benchmarkStratum(b));
});
test('acceptance requirements and unknown identities stay separate',()=>{
  const {a,b}=fixture();b.acceptance.required=34;assert.equal(benchmarkGroups([a,b]).length,2);
  delete a.identity;delete b.identity;assert.equal(benchmarkGroups([a,b]).length,2);
});
test('duplicate attempts do not inflate count and conflicting identities fail closed',()=>{
  const {a}=fixture();assert.equal(benchmarkGroups([a,structuredClone(a)])[0].rows.length,1);
  assert.throws(()=>benchmarkGroups([a,{...a,status:'failed'}]),/Conflicting session identity/);
});
test('treatment versions remain separate within arm distributions',()=>{
  const {b}=fixture();const next=structuredClone(b);next.id='next';next.identity.treatment='runtime-v2';
  assert.equal(benchmarkArmDistributions([b,next]).length,2);
});
test('failed interrupted and unattempted attempts survive accepted-only selection denominators',()=>{
  const {b}=fixture();const rejected={...structuredClone(b),id:'rejected',status:'failed',trial:2,acceptance:{...b.acceptance,accepted:false,all_passed:false}};
  const interrupted={...structuredClone(b),id:'interrupted',status:'interrupted',trial:3,acceptance:{required:33}};
  const unattempted={...structuredClone(b),id:'unattempted',status:'unattempted',trial:4,acceptance:{required:33}};
  const d=benchmarkArmDistributions([b,rejected,interrupted,unattempted],{acceptedOnly:true})[0];
  assert.deepEqual([d.total,d.attempted,d.accepted,d.failed,d.interrupted,d.unattempted,d.selected],[4,3,1,1,1,1,1]);
  assert.equal(d.metrics.input_tokens.count,1);assert.equal(d.trials.length,3);
});
test('descriptive medians ranges individual values and missing overhead reconcile',()=>{
  const {b}=fixture();const next=structuredClone(b);next.id='next';next.trial=2;next.metrics.input_tokens=metric(300);next.experiment.order_index=0;
  const d=benchmarkArmDistributions([b,next])[0];assert.deepEqual(d.metrics.input_tokens.values,[100,300]);assert.equal(d.metrics.input_tokens.median,200);
  assert.equal(d.metrics.human_review_ms.median,null);assert.deepEqual(d.costs,[]);assert.deepEqual(d.order.map(row=>row.position),[1,0]);
  assert.match(d.limitation,/no significance/);
});
test('delivery never proves invocation or behavioral use; absence and unknown remain distinct',()=>{
  const {a,b,pair}=fixture();b.activation=b.activation.map(row=>({...row,state:row.stage==='delivery_verified'?'verified':row.stage==='invocation'?'explicitly_absent':'unknown'}));
  const gaps=evidenceGaps(pair,[a,b]);assert(!gaps.some(gap=>gap.code==='delivery_verified'));assert.equal(gaps.find(gap=>gap.code==='invocation').state,'explicitly_absent');
  assert.equal(gaps.find(gap=>gap.code==='behavioral').state,'unknown');assert(gaps.every(gap=>gap.resolve));assert.equal(pair.qualified,false);
});
test('gaps retain incomplete policy missing resources prices trial order and repetition',()=>{
  const {a,b,pair}=fixture();a.policy={qualified:false,classified_commands:2,observed_commands:3};b.experiment=null;
  b.metrics.wall_ms=metric(null);const gaps=evidenceGaps(pair,[a,b]);
  for(const code of ['policy_coverage','missing_metrics','pricing','execution_order','repetition'])assert(gaps.some(gap=>gap.code===code));
  assert(gaps.some(gap=>gap.meaning.includes('2 of 3')));assert(gaps.some(gap=>gap.meaning.includes('human review ms')));
});
test('signed improvements and regressions stay descriptive for model-free controls',()=>{
  const {a,b,pair}=fixture();b.metrics.input_tokens=metric(80);b.metrics.wall_ms=metric(1500);pair.qualified=true;
  const result=comparisonMetrics(pair,[a,b]);assert.equal(result.metrics.input_tokens.delta,-20);assert.equal(result.metrics.wall_ms.delta,500);assert.equal(result.attributable,false);
});
test('export roundtrip preserves missingness order and decision downgrade; CSV carries source and treatment',()=>{
  const doc=createDemoDocument();const {a,b,pair}=fixture();a.source_id=doc.sources[0].id;b.source_id=a.source_id;b.metrics.human_review_ms=metric(null);
  doc.sessions=[a,b];doc.comparisons=[pair];const original=validateDocument(doc,{trusted:true});const restored=validateDocument(exportJSON(original));
  assert.equal(restored.sessions[1].metrics.human_review_ms.value,null);assert.equal(restored.sessions[1].experiment.order_index,1);assert.equal(restored.comparisons[0].qualified,false);
  const csv=exportCSV(original);assert.match(csv,/model_effort_identity/);assert.match(csv,/order_index/);assert.match(csv,/treatment_identity/);
});
test('public preview excludes private historical evaluation receipts',()=>{

  assert.equal(existsSync('docs/evaluations/V51_NATIVE_RECEIPTS.json'),false);
  assert.equal(existsSync('docs/evaluations/V52_D11_CALIBRATION_RECEIPTS.json'),false);
});
test('original evaluator strata and unknown acceptance cannot be pooled',()=>{
  const {a,b}=fixture();a.stratum_sha256='one-schema';b.stratum_sha256='other-schema';assert.equal(benchmarkGroups([a,b]).length,2);
  delete a.stratum_sha256;delete b.stratum_sha256;a.acceptance={};b.acceptance={};assert.equal(benchmarkGroups([a,b]).length,2);
});
