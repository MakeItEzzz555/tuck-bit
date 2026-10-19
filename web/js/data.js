export const SCHEMA = 'tuckbit.observatory/1';
export const ACTIVATION_STAGES = ['available', 'offered', 'selected', 'delivery_started', 'delivery_verified', 'invocation', 'behavioral'];
export const METRIC_KEYS = ['input_tokens', 'cached_input_tokens', 'uncached_input_tokens', 'output_tokens', 'wall_ms', 'agent_ms', 'initialization_ms', 'preparation_ms', 'verification_ms', 'checkpoint_ms', 'delegation_ms', 'automated_edit_observed_sum_ms', 'context_bytes', 'tool_invocations', 'tool_calls_observed', 'potential_redundant_unchanged_rereads', 'human_review_ms', 'human_edit_ms', 'manual_edit_ms', 'human_interventions', 'agent_retries', 'tool_retries', 'benchmark_reruns'];
const STATES = new Set(['verified', 'not_observed', 'not_applicable', 'explicitly_absent', 'unknown']);
const KINDS = new Set(['native', 'control', 'demo', 'session']);
const STATUS = new Set(['observed', 'derived', 'unknown', 'estimated', 'unavailable', 'provider_reported', 'measured']);
const MAX_BYTES = 4 * 1024 * 1024;
// Authority is process-local and never restored from an exported claim.
const authoritativeRows = new WeakSet();
const authoritativePairs = new WeakSet();
const text = (value, limit = 512) => {
  if (value === null || value === undefined) return null;
  if (typeof value !== 'string' || value.length > limit || /[\u0000-\u0008\u000b\u000c\u000e-\u001f]/u.test(value)) throw new Error('Invalid bounded text');
  return value;
};
const object = value => value && typeof value === 'object' && !Array.isArray(value);
const number = value => value === null || (typeof value === 'number' && Number.isFinite(value) && value >= 0);
function timestamp(value) {
  if (value === null || value === undefined) return null;
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)$/.test(value) || !Number.isFinite(Date.parse(value))) throw new Error('Expected a UTC timestamp');
  const normalized = new Date(value).toISOString();
  if (normalized.slice(0, 10) !== value.slice(0, 10)) throw new Error('Invalid calendar date');
  return normalized;
}
function strings(values, limit = 100) {
  if (!Array.isArray(values) || values.length > limit) throw new Error('Invalid text list');
  return values.map(value => text(value, 2000));
}
function safeEvidence(value, depth = 0) {
  if (depth > 8) throw new Error('Evidence is too deeply nested');
  if (value === null || typeof value === 'boolean') return value;
  if (typeof value === 'number') { if (!Number.isFinite(value)) throw new Error('Invalid evidence number'); return value; }
  if (typeof value === 'string') return text(value, 2000);
  if (Array.isArray(value)) { if (value.length > 10000) throw new Error('Too many evidence rows'); return value.map(item => safeEvidence(item, depth + 1)); }
  if (!object(value)) throw new Error('Invalid evidence');
  const out = {};
  for (const [key, item] of Object.entries(value)) {
    if (['constructor', 'prototype', 'raw', 'command', 'path'].includes(key) || !(/^[a-zA-Z][a-zA-Z0-9_]{0,79}$/.test(key) || /^[a-f0-9]{64}$/.test(key)) || /(?:prompt|stderr|transcript|credential|password|secret|command_text|raw_command|arguments|file_content|source_text|reasoning)/i.test(key)) throw new Error('Private or unsupported evidence field');
    out[key] = safeEvidence(item, depth + 1);
  }
  return out;
}
function metric(value) {
  if (!object(value) || !number(value.value) || !STATUS.has(value.status)) throw new Error('Invalid metric observation');
  if ((value.value === null) !== ['unknown', 'unavailable'].includes(value.status)) throw new Error('Unknown metric has a value');
  return {value: value.value, source: text(value.source, 512), status: value.status};
}
function unique(rows, name) {
  const seen = new Map();
  for (const row of rows) {
    if (!row.id) throw new Error(`Missing ${name} identity`);
    const previous = seen.get(row.id);
    if (previous && stable(previous) !== stable(row)) throw new Error(`Conflicting ${name} identity`);
    seen.set(row.id, row);
  }
  return [...seen.values()];
}
export function stable(value) {
  if (Array.isArray(value)) return `[${value.map(stable).join(',')}]`;
  if (object(value)) return `{${Object.keys(value).sort().map(key => `${JSON.stringify(key)}:${stable(value[key])}`).join(',')}}`;
  return JSON.stringify(value);
}
export function validateDocument(input, {trusted = false} = {}) {
  let value = input;
  if (typeof input === 'string') {
    if (new TextEncoder().encode(input).length > MAX_BYTES) throw new Error('Import exceeds 4 MiB');
    try { value = JSON.parse(input); } catch { throw new Error('Invalid JSON'); }
  }
  if (!object(value) || Object.keys(value).some(key => !['schema', 'sources', 'sessions', 'comparisons', 'limitations'].includes(key)) || value.schema !== SCHEMA) throw new Error('Unsupported Observatory schema');
  if (new TextEncoder().encode(JSON.stringify(value)).length > MAX_BYTES) throw new Error('Import exceeds 4 MiB');
  for (const [key, limit] of [['sources', 2000], ['sessions', 1000], ['comparisons', 10000], ['limitations', 200]]) {
    if (!Array.isArray(value[key]) || value[key].length > limit) throw new Error(`Invalid ${key} collection`);
  }
  const sources = unique(value.sources.map(source => {
    if (!object(source) || !/^[a-f0-9]{64}$/i.test(source.sha256)) throw new Error('Invalid source hash');
    const result = {id: text(source.id), sha256: source.sha256.toLowerCase(), label: text(source.label), format: text(source.format), imported_at: timestamp(source.imported_at), trust: text(source.trust)};
    for (const key of ['kind', 'identity_semantics']) if (source[key] !== undefined) result[key] = safeEvidence(source[key]);
    return result;
  }), 'source');
  const sourceIDs = new Set(sources.map(source => source.id));
  let eventCount = 0;
  const sessions = unique(value.sessions.map(session => {
    if (!object(session) || !KINDS.has(session.kind) || !sourceIDs.has(session.source_id) || !object(session.metrics)) throw new Error('Invalid session');
    const result = {};
    for (const field of ['id', 'source_id', 'title', 'agent', 'provider', 'model', 'project', 'arm', 'status', 'task', 'domain', 'complexity']) result[field] = text(session[field]);
    for (const key of ['receipt_sha256', 'trial', 'bundle_sha256', 'stratum_sha256', 'identity', 'experiment', 'reported_kind']) if (session[key] !== undefined) result[key] = safeEvidence(session[key]);
    result.kind = session.kind;
    if (result.reported_kind !== undefined && !KINDS.has(result.reported_kind)) throw new Error('Invalid reported observation kind');
    if (!trusted && result.kind === 'native') { result.reported_kind ??= 'native'; result.kind = 'session'; }
    result.started_at = timestamp(session.started_at);
    result.metrics = {};
    for (const [key, observation] of Object.entries(session.metrics)) {
      if (!/^[a-z][a-z0-9_]{0,79}$/.test(key)) throw new Error('Invalid metric identifier');
      result.metrics[key] = metric(observation);
      if (key.endsWith('_tokens') && observation.value !== null && !Number.isInteger(observation.value)) throw new Error('Invalid token counter');
    }
    for (const key of METRIC_KEYS) result.metrics[key] = session.metrics[key] === undefined ? {value: null, source: null, status: 'unknown'} : metric(session.metrics[key]);
    const {input_tokens: total, cached_input_tokens: cached, uncached_input_tokens: uncached} = result.metrics;
    if (total.value !== null && cached.value !== null) {
      if (cached.value > total.value) throw new Error('Cached input exceeds total input');
      if (uncached.value !== null && uncached.value !== total.value - cached.value) throw new Error('Conflicting uncached input');
      if (uncached.value === null) result.metrics.uncached_input_tokens = {value: total.value - cached.value, source: 'derived: input_tokens - cached_input_tokens', status: 'derived'};
    }
    result.acceptance = safeEvidence(session.acceptance || {accepted: null, required: null, performed: null, all_passed: null, provenance: 'unavailable'});
    for (const key of ['accepted', 'all_passed', 'independent', 'reported_independent']) if (result.acceptance[key] !== undefined && result.acceptance[key] !== null && typeof result.acceptance[key] !== 'boolean') throw new Error('Invalid acceptance boolean');
    for (const key of ['required', 'performed']) if (result.acceptance[key] !== undefined && result.acceptance[key] !== null && (!Number.isInteger(result.acceptance[key]) || result.acceptance[key] < 0 || result.acceptance[key] > 100000)) throw new Error('Invalid acceptance count');
    if (result.acceptance.required !== null && result.acceptance.performed > result.acceptance.required) throw new Error('Invalid acceptance coverage');
    result.policy = safeEvidence(session.policy || {qualified: null, observed_commands: null, classified_commands: null, unclassified: null, reason_counts: {}, provenance: 'unavailable'});
    if (result.policy.qualified !== undefined && result.policy.qualified !== null && typeof result.policy.qualified !== 'boolean') throw new Error('Invalid policy boolean');
    for (const key of ['observed_commands', 'classified_commands', 'unclassified']) if (result.policy[key] !== undefined && result.policy[key] !== null && (!Number.isInteger(result.policy[key]) || result.policy[key] < 0 || result.policy[key] > 100000)) throw new Error('Invalid policy count');
    const observed = session.activation || [];
    if (!Array.isArray(observed) || observed.length > ACTIVATION_STAGES.length || new Set(observed.map(item => item.stage)).size !== observed.length) throw new Error('Invalid activation stages');
    result.activation = ACTIVATION_STAGES.map(stage => {
      const evidence = observed.find(item => item.stage === stage);
      if (!evidence) return {stage, state: session.arm === 'A' ? 'not_applicable' : 'unknown', note: null, provenance: null, events: []};
      if (!STATES.has(evidence.state)) throw new Error('Invalid activation state');
      return safeEvidence(evidence);
    });
    if (observed.some(item => !ACTIVATION_STAGES.includes(item.stage))) throw new Error('Unsupported activation stage');
    for (const field of ['events', 'context']) {
      const rows = session[field] || [];
      if (field === 'context' && object(rows)) { result[field] = safeEvidence(rows); continue; }
      if (!Array.isArray(rows) || rows.length > 10000) throw new Error('Invalid event collection');
      eventCount += rows.length;
      result[field] = unique(rows.map((row, index) => {
        const clean = safeEvidence(row);
        // Events without public identities cannot safely be deduplicated by their display text.
        return {...clean, id: clean.id || `${result.id}:${field}:${index}`};
      }), 'event').sort((a, b) => (a.order ?? Number.MAX_SAFE_INTEGER) - (b.order ?? Number.MAX_SAFE_INTEGER));
    }
    result.qualification = safeEvidence(session.qualification || {qualified: false, evaluator: null, reasons: ['qualification_missing']});
    if (typeof result.qualification.qualified !== 'boolean') throw new Error('Invalid qualification decision');
    if (!trusted && result.acceptance.independent === true) { result.acceptance.reported_independent ??= true; result.acceptance.independent = false; }
    if (!trusted && result.qualification.qualified) result.qualification = {...result.qualification, reported_qualified: result.qualification.reported_qualified ?? true, qualified: false, reasons: [...new Set([...(result.qualification.reasons || []), 'external_qualification_unverified'])]};
    result.limitations = strings(session.limitations || []);
    return result;
  }), 'session');
  if (eventCount > 100000) throw new Error('Too many events');
  if (trusted) for (const session of sessions) {
    const source = sources.find(item => item.id === session.source_id);
    if (session.status === 'unattempted' && session.acceptance.provenance === 'closed_study_report' && source?.trust === 'repository' && source?.format === 'study_metadata') authoritativeRows.add(session);
    if (/^[a-f0-9]{64}$/.test(session.receipt_sha256 || '') && session.id === session.receipt_sha256 && (session.acceptance.independent === true || (session.acceptance.provenance === 'source_bound_receipt_reported_grading' && source?.format === 'tuckbit_receipts')) && ['v5_evaluation.per_task_report', 'capture_settings'].includes(session.qualification.evaluator)) authoritativeRows.add(session);
  }
  const sessionIDs = new Set(sessions.map(session => session.id));
  const comparisons = unique(value.comparisons.map((comparison, index) => {
    if (!object(comparison) || !sessionIDs.has(comparison.baseline_id) || !sessionIDs.has(comparison.treatment_id) || typeof comparison.qualified !== 'boolean') throw new Error('Invalid comparison');
    const clean = safeEvidence(comparison);
    if (clean.reported_kind !== undefined && !KINDS.has(clean.reported_kind)) throw new Error('Invalid reported comparison kind');
    if (!trusted && clean.kind === 'native') { clean.reported_kind ??= 'native'; clean.kind = 'session'; }
    clean.id ||= `comparison:${comparison.baseline_id}:${comparison.treatment_id}:${index}`;
    if (!trusted && clean.qualified) { clean.reported_qualified ??= true; clean.qualified = false; clean.quality_qualified = false; clean.reasons = [...new Set([...(clean.reasons || []), 'external_qualification_unverified'])]; }
    return clean;
  }), 'comparison');
  if (trusted) for (const pair of comparisons) {
    if (/^[a-f0-9]{64}$/.test(pair.id) && ['v5_evaluation.per_task_report', 'capture_settings'].includes(pair.evaluator) && [pair.baseline_id, pair.treatment_id].every(id => authoritativeRows.has(sessions.find(session => session.id === id)))) authoritativePairs.add(pair);
  }
  return {schema: SCHEMA, sources, sessions, comparisons, limitations: strings(value.limitations)};
}
function immutableObservation(row, pair = false) {
  const content = {...row, kind: row.reported_kind || row.kind};
  for (const key of Object.keys(content)) if (key.startsWith('reported_')) delete content[key];
  for (const key of pair ? ['qualified', 'quality_qualified', 'evaluator', 'reasons', 'limitations'] : ['source_id', 'qualification', 'limitations']) delete content[key];
  if (!pair) {
    content.acceptance = {...row.acceptance};
    delete content.acceptance.independent;
    delete content.acceptance.reported_independent;
    // V8 adapter labels are derived; original receipt content remains the authority.
    if (content.acceptance.provenance === 'independent_corpus_grader') content.acceptance.provenance = 'source_bound_receipt_reported_grading';
  }
  return stable(content);
}
function mergeIdentity(rows, authority, name, pair = false) {
  const distinct = new Map();
  for (const row of rows) {
    const prior = distinct.get(row.id);
    if (!prior) { distinct.set(row.id, row); continue; }
    if (stable({...prior, source_id: null}) === stable({...row, source_id: null})) continue;
    const same = immutableObservation(prior, pair) === immutableObservation(row, pair);
    if (same && (authority.has(prior) || authority.has(row))) { if (authority.has(row)) distinct.set(row.id, row); continue; }
    throw new Error(`Conflicting ${name} identity`);
  }
  return [...distinct.values()];
}
function boundWorkspace(document) {
  if (document.sources.length > 2000 || document.sessions.length > 1000 || document.comparisons.length > 10000 || document.limitations.length > 200) throw new Error('Workspace collection limit exceeded');
  const eventCount = document.sessions.reduce((sum, row) => sum + row.events.length + (Array.isArray(row.context) ? row.context.length : 0), 0);
  if (eventCount > 100000) throw new Error('Workspace event limit exceeded');
  if (new TextEncoder().encode(JSON.stringify(document)).length > MAX_BYTES) throw new Error('Workspace exceeds 4 MiB');
  return document;
}
export function mergeDocuments(...documents) {
  if (documents.length === 1 && Array.isArray(documents[0])) documents = documents[0];
  const sourceMap = new Map();
  const sourceIDs = new Map();
  const sessions = [];
  const comparisons = [];
  for (const doc of documents) {
    for (const source of doc.sources) {
      const existing = sourceMap.get(source.sha256);
      if (existing && existing.format !== source.format) throw new Error('Conflicting source provenance');
      if (sourceIDs.has(source.id) && sourceIDs.get(source.id) !== source.sha256) throw new Error('Conflicting source identity');
      sourceIDs.set(source.id, source.sha256);
      if (!existing) sourceMap.set(source.sha256, source);
    }
    for (const session of doc.sessions) {
      const source = doc.sources.find(item => item.id === session.source_id);
      const copy = {...session, source_id: sourceMap.get(source.sha256).id};
      if (authoritativeRows.has(session)) authoritativeRows.add(copy);
      sessions.push(copy);
    }
    comparisons.push(...doc.comparisons);
  }
  return boundWorkspace({schema: SCHEMA, sources: [...sourceMap.values()], sessions: mergeIdentity(sessions, authoritativeRows, 'session'), comparisons: mergeIdentity(comparisons, authoritativePairs, 'comparison', true), limitations: [...new Set(documents.flatMap(doc => doc.limitations))]});
}
export function exportJSON(document) { return JSON.stringify(document, null, 2); }
export function exportCSV(document, {type = 'sessions'} = {}) {
  if (!['sessions', 'comparisons'].includes(type)) throw new Error('Unsupported CSV table');
  const cell = value => {
    let str = value === null || value === undefined ? '' : String(value);
    if (typeof value === 'string' && /^[\s]*[=+\-@]/u.test(str)) str = `'${str}`;
    return `"${str.replaceAll('"', '""')}"`;
  };
  const columns = type === 'sessions'
    ? ['id', 'source_id', 'source_sha256', 'kind', 'reported_kind', 'started_at', 'title', 'agent', 'provider', 'model', 'project', 'arm', 'status', 'task', 'domain', 'complexity', 'trial', 'bundle_sha256', 'stratum_sha256', 'source_identity', 'model_effort_identity', 'grader_task_identity', 'environment_identity', 'treatment_identity', 'order_index', 'block_order', 'benchmark_rerun', 'acceptance_required', 'acceptance_performed', 'accepted', 'mandatory_checks_passed', 'qualification', 'qualification_reasons', 'policy_qualified', ...ACTIVATION_STAGES.map(stage => `activation_${stage}`), ...METRIC_KEYS.flatMap(key => [key, `${key}_status`, `${key}_source`])]
    : ['id', 'kind', 'reported_kind', 'baseline_id', 'treatment_id', 'qualified', 'reported_qualified', 'evaluator', 'reasons', 'sample_size', 'matched_identity', 'bundle_sha256', 'trial', ...METRIC_KEYS.flatMap(key => [`baseline_${key}`, `treatment_${key}`, `delta_${key}`])];
  const rows = type === 'sessions' ? document.sessions.map(session => {
    const row = {...session, source_identity: session.identity?.source, model_effort_identity: session.identity?.model, grader_task_identity: session.identity?.task, environment_identity: session.identity?.environment, treatment_identity: session.identity?.treatment, order_index: session.experiment?.order_index, block_order: session.experiment?.block_order, benchmark_rerun: session.experiment?.benchmark_rerun, acceptance_required: session.acceptance?.required, acceptance_performed: session.acceptance?.performed, source_sha256: document.sources.find(source => source.id === session.source_id)?.sha256, accepted: session.acceptance.accepted, mandatory_checks_passed: session.acceptance.all_passed, qualification: session.qualification.qualified, qualification_reasons: (session.qualification.reasons || []).join('; '), policy_qualified: session.policy.qualified};
    for (const stage of session.activation) row[`activation_${stage.stage}`] = stage.state;
    for (const key of METRIC_KEYS) { row[key] = session.metrics[key]?.value; row[`${key}_status`] = session.metrics[key]?.status; row[`${key}_source`] = session.metrics[key]?.source; }
    return row;
  }) : document.comparisons.map(pair => {
    const row = {...pair, reasons: (pair.reasons || []).join('; ')};
    const a = document.sessions.find(session => session.id === pair.baseline_id);
    const b = document.sessions.find(session => session.id === pair.treatment_id);
    for (const key of METRIC_KEYS) { const av = a?.metrics[key]?.value ?? null; const bv = b?.metrics[key]?.value ?? null; row[`baseline_${key}`] = av; row[`treatment_${key}`] = bv; row[`delta_${key}`] = av !== null && bv !== null ? bv - av : null; }
    return row;
  });
  return [columns.map(cell).join(','), ...rows.map(row => columns.map(key => cell(row[key])).join(','))].join('\r\n');
}
export function createDemoDocument() {
  const source = {id: 'demo-source', sha256: 'd'.repeat(64), label: 'Synthetic interaction demonstration', format: SCHEMA, imported_at: null, trust: 'synthetic'};
  const sessions = Array.from({length: 30}, (_, index) => {
    const arm = ['A', 'B', 'C'][index % 3];
    const input = 16000 + (index % 7) * 2500;
    const metric = value => ({value, source: 'synthetic fixture — not a provider observation', status: 'estimated'});
    const unknown = {value: null, source: null, status: 'unknown'};
    return {id: `demo-${index + 1}`, source_id: source.id, kind: 'demo', title: `Synthetic ${['CLI repair', 'Repository search', 'Refactor'][index % 3]} ${index + 1}`, agent: 'Demo agent', provider: 'Synthetic provider', model: 'Simulated model', project: ['demo-cli', 'demo-web'][index % 2], started_at: new Date(Date.UTC(2026, 9, index + 1, 14)).toISOString(), arm, status: index % 9 === 0 ? 'failed' : 'accepted', task: `demo-task-${Math.floor(index / 3)}`, domain: ['D09', 'D05', 'D04'][index % 3], complexity: ['small', 'medium', 'complex'][index % 3], metrics: {input_tokens: metric(input), cached_input_tokens: metric(input / 2), uncached_input_tokens: metric(input / 2), output_tokens: metric(500 + index * 11), wall_ms: metric(18000 + (index % 5) * 3000), agent_ms: metric(17000 + (index % 5) * 3000), preparation_ms: arm === 'C' ? metric(25) : unknown, verification_ms: metric(350), tool_calls_observed: metric(4 + index % 6), potential_redundant_unchanged_rereads: index % 4 ? metric(index % 3) : unknown}, acceptance: {accepted: index % 9 !== 0, required: 10, performed: 10, all_passed: index % 9 !== 0, provenance: 'synthetic checks'}, activation: ACTIVATION_STAGES.map((stage, stageIndex) => ({stage, state: arm === 'A' ? 'not_applicable' : index % 5 === 0 ? 'unknown' : stageIndex < 5 ? 'verified' : 'not_observed', note: 'Synthetic evidence only', provenance: 'demo fixture', events: []})), policy: {qualified: index % 6 !== 0, observed_commands: 5, classified_commands: index % 6 === 0 ? 4 : 5, unclassified: index % 6 === 0 ? 1 : 0, reason_counts: {}, provenance: 'synthetic'}, events: ['search', 'file_inspection', 'tests'].map((category, eventIndex) => ({id: `demo-event-${index}-${eventIndex}`, order: eventIndex, category, operation: null, success: !(eventIndex === 2 && index % 9 === 0), result: null, evidence: null, capabilities: [], duration_ms: 30 + eventIndex * 20, provenance: 'synthetic event'})), context: [], qualification: {qualified: false, evaluator: 'demo', reasons: ['synthetic_not_native_evidence']}, limitations: ['Synthetic data for interface exploration. Not observed usage or performance.']};
  });
  const comparisons = [{id: 'demo-comparison-1', baseline_id: 'demo-2', treatment_id: 'demo-3', kind: 'demo', qualified: false, quality_qualified: false, evaluator: 'synthetic fixture', reasons: ['simulation_not_measured_savings'], sample_size: 1}];
  return validateDocument({schema: SCHEMA, sources: [source], sessions, comparisons, limitations: ['DEMONSTRATION — all values are synthetic; excluded from real usage and attributable savings.']}, {trusted: true});
}
