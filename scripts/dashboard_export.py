#!/usr/bin/env python3
"""Read-only, bounded Observatory adapters; never scan personal agent sessions."""
import argparse
import copy
import hashlib
import json
import math
import os
import stat
from pathlib import Path
import re
import sys
from datetime import datetime
from uuid import UUID

import benchmark_bundle
import execution_events
import trace_profiler
import v4_runner
import v5_evaluation

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = 'tuckbit.observatory/1'
MAX_BYTES = 4 * 1024 * 1024
MAX_SESSIONS = 1000
MAX_EVENTS = 100000
STAGES = ('available', 'offered', 'selected', 'delivery_started', 'delivery_verified', 'invocation', 'behavioral')
STATES = {'verified', 'not_observed', 'not_applicable', 'explicitly_absent', 'unknown'}
HEX = re.compile(r'^[a-f0-9]{64}$')
NAME = re.compile(r'^[a-z][a-z0-9_]{0,63}$')
UNKNOWN = {'value': None, 'source': 'unavailable', 'status': 'unknown'}
ASSET_SUFFIXES = {'.html','.css','.js','.svg','.woff2','.png','.ico'}
LIMITATIONS = [
    'Public telemetry is partial. A whole-file read proves delivery, not semantic adherence or hidden reasoning.',
    'Provider cache conditions, human effort and cost are unknown unless explicitly recorded.',
    'Signed differences are descriptive; attribution requires the existing evaluator to qualify the comparison.',
    'Dates and model identities are not guessed. Undated observations are excluded from calendar charts.',
    'Batch setup is shared and must not be summed once per arm; preparation is included in initialization.',
]


class ImportError(ValueError):
    """A bounded, safe error code; never include input contents or paths."""


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _fail(code='invalid_document'):
    raise ImportError(code)


def _text(value, nullable=False, maximum=200):
    if nullable and value is None:
        return None
    if not isinstance(value, str) or len(value) > maximum or any(ord(c) < 32 for c in value):
        _fail('invalid_text')
    return value


def _number(value):
    return type(value) in {int, float} and math.isfinite(value) and 0 <= value <= 10**15


def _bounded(value):
    try:
        encoded = json.dumps(value, allow_nan=False).encode()
    except (ValueError, TypeError, RecursionError):
        _fail('invalid_json')
    if len(encoded) > MAX_BYTES:
        _fail('size_limit')


def parse_bytes(data, limit=MAX_BYTES):
    if len(data) > limit:
        _fail('size_limit')
    def unique(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                _fail('duplicate_json_key')
            out[key] = value
        return out
    try:
        return json.loads(data.decode('utf-8'), object_pairs_hook=unique,
                          parse_constant=lambda _: _fail('invalid_number'))
    except ImportError:
        raise
    except (UnicodeError, ValueError, RecursionError):
        _fail('invalid_json')


def read_selected(path):
    # Reuse the profiler's no-symlink, ordinary-file reader; it has a stricter 2 MiB bound.
    target=Path(path).absolute()
    if any(p.is_symlink() for p in (target,*target.parents)): _fail('symlink_input')
    return parse_bytes(trace_profiler.read_text(target).encode())


def _metric(value=None, source='unavailable', status=None):
    return {'value': value, 'source': source if value is not None else 'unavailable',
            'status': status or ('measured' if value is not None else 'unknown')}


def _metrics(values):
    if not isinstance(values, dict) or len(values) > 100:
        _fail('invalid_metrics')
    result = {}
    for name, row in values.items():
        if not NAME.fullmatch(name) or not isinstance(row, dict) or set(row) != {'value', 'source', 'status'}:
            _fail('invalid_metrics')
        value = row['value']
        if value is not None and (not _number(value) or name.endswith('_tokens') and type(value) is not int):
            _fail('invalid_metrics')
        _text(row['source'], nullable=value is None, maximum=100)
        if row['status'] not in {'measured', 'observed', 'derived', 'estimated', 'unknown', 'unavailable'}:
            _fail('invalid_metrics')
        if (value is None) != (row['status'] in {'unknown', 'unavailable'}):
            _fail('invalid_metrics')
        result[name] = dict(row)
    total, cached, uncached = (result.get(k, UNKNOWN)['value'] for k in ('input_tokens', 'cached_input_tokens', 'uncached_input_tokens'))
    if total is not None and cached is not None:
        if cached > total or uncached is not None and uncached != total - cached:
            _fail('conflicting_usage')
        if uncached is None:
            result['uncached_input_tokens'] = _metric(total-cached, 'validated_input_minus_cached', 'derived')
    return result


def _source(value, label, format_name, trust):
    sha = digest(value)
    return {'id': sha, 'sha256': sha, 'label': label, 'kind': trust, 'format': format_name,
            'imported_at': None, 'trust': trust, 'identity_semantics': 'SHA-256 of canonical JSON; original receipt hashes retained separately'}


def _stage(stage, state='unknown', note='No supported public observation.', provenance='unavailable', events=None):
    return {'stage': stage, 'state': state, 'note': note, 'provenance': provenance, 'events': events or []}


def activation(row):
    baseline = row['mode'] == 'A'
    observation = row.get('observability', {}).get('activation', {})
    calls = row['execution']['calls']
    skill = [c for c in calls if c['category'] == 'skill_instructions']
    supported = row.get('schema') == 52
    def events(items):
        return [{'id': c['id'], 'order': calls.index(c), 'timestamp': None,
                 'category': c['category'], 'source_sha256': (c['evidence'] or {}).get('source'),
                 'content_sha256': (c['evidence'] or {}).get('content'),
                 'delivery_complete': (c['evidence'] or {}).get('delivered'),
                 'provenance': row['execution']['source']} for c in items]
    result = [_stage(name) for name in STAGES]
    if baseline:
        return [_stage(name, 'not_applicable', 'Baseline has no TuckBit treatment.', 'experimental_arm') for name in STAGES]
    if observation.get('offered') is True:
        result[0] = _stage('available', 'verified', 'Treatment made the skill available; installation is not activation.', 'frozen_runtime_contract')
        result[1] = _stage('offered', 'verified', 'Skill offered in the runtime.', 'frozen_runtime_contract')
    else:
        result[0] = _stage('available', 'unknown', 'Configured treatment; installation availability was not separately observed.', 'receipt_arm')
    for name, field in [('selected', 'selected'), ('invocation', 'invoked')]:
        caps = [c for c in calls if any(cap['stage'] == ('invoked' if name == 'invocation' else 'selected') for cap in c['capabilities'])]
        if caps:
            result[STAGES.index(name)] = _stage(name, 'verified', 'Supported public capability transition observed.', 'public_tool_observer', events(caps))
        elif observation.get(field) is False:
            result[STAGES.index(name)] = _stage(name, 'explicitly_absent', 'Explicit negative observation.', 'receipt_observability')
        else:
            result[STAGES.index(name)] = _stage(name, 'not_observed', 'No public event proves this transition.', 'public_tool_observer')
    if skill:
        result[3] = _stage('delivery_started', 'verified', 'Skill instruction access was observed.', 'public_tool_observer', events(skill))
    complete = supported and observation.get('instructions_delivered') is True
    if complete:
        result[4] = _stage('delivery_verified', 'verified', 'Full instruction bytes verified by the original observer; consumption remains unobservable.', 'whole_instruction_byte_verification', events(skill))
    elif skill:
        result[4] = _stage('delivery_verified', 'not_observed', 'Instruction access does not establish full canonical instruction delivery.', 'public_tool_observer', events(skill))
    result[6] = _stage('behavioral', 'unknown', 'Independent task acceptance does not establish semantic instruction adherence.', 'unavailable')
    return result


def _reasons(row):
    reasons = list(row['failure_categories'])
    if not row['accepted']: reasons.append('independent_acceptance_failed')
    if row['mode'] != 'A' and not row['activation_qualified']: reasons.append('activation_unverified')
    if row['metrics']['unclassified_commands']['value'] != 0: reasons.append('policy_coverage_incomplete')
    if row['observation_source'] != 'native_public_events': reasons.append('model_free_control')
    return sorted(set(reasons))


def _receipt_session(row, source_id, run, model_map, stratum_sha256):
    summary = execution_events.summarize(row['execution'])
    metrics = _metrics({**copy.deepcopy(row['metrics']), **copy.deepcopy(run['effort']), **copy.deepcopy(run['observed_metrics'])})
    policy = row.get('observability', {}).get('policy', {})
    unclassified = row['metrics']['unclassified_commands']['value']
    return {'id': v5_evaluation.review_key(row), 'receipt_sha256': v5_evaluation.review_key(row), 'source_id': source_id,
        'kind': 'native' if row['observation_source'] == 'native_public_events' else 'control',
        'title': f"{row['case']} · {row['mode']} · trial {row['trial']}", 'agent': 'Codex' if row['observation_source'] == 'native_public_events' else 'Deterministic client',
        'provider': 'OpenAI' if row['observation_source'] == 'native_public_events' else None,
        'model': model_map.get(row['identity']['model']), 'project': 'TuckBit evaluation', 'started_at': None,
        'arm': row['mode'], 'status': row['status'], 'task': row['case'], 'domain': row['domain'], 'complexity': row['complexity'],
        'trial': row['trial'], 'bundle_sha256': row.get('bundle_sha256'), 'stratum_sha256': stratum_sha256, 'identity': copy.deepcopy(row['identity']),
        'metrics': metrics, 'acceptance': {**row['validation'], 'accepted': row['accepted'], 'independent': False, 'provenance': 'source_bound_receipt_reported_grading'},
        'activation': activation(row), 'policy': {'qualified': run['policy_coverage_qualified'],
            'observed_commands': policy.get('observed_commands'), 'classified_commands': policy.get('classified_commands'),
            'unclassified': unclassified, 'reason_counts': policy.get('reason_counts', {}), 'provenance': 'command_policy_observer'},
        'events': [{**copy.deepcopy(c), 'order': i, 'timestamp': None, 'provenance': row['execution']['source']} for i,c in enumerate(row['execution']['calls'])],
        'context': summary, 'experiment': copy.deepcopy(row.get('experiment')),
        'qualification': {'qualified': row['comparison_eligible'], 'evaluator': 'v5_evaluation.per_task_report', 'reasons': _reasons(row)},
        'limitations': list(LIMITATIONS) + ['Contract-consistent record bound to the selected receipt hash; source binding does not authenticate its origin.', 'Grading is receipt-reported, not independently observed here. Provider activity is not externally corroborated.', 'Receipt contains no observation timestamp.', 'Invocation and semantic adherence are distinct from instruction delivery.']}


def receipts_document(rows, label='Selected receipts', trust='selected_file', model_map=None):
    _bounded(rows)
    if not isinstance(rows, list) or not rows or len(rows) > MAX_SESSIONS:
        _fail('invalid_receipt_list')
    unique, slots = {}, {}
    for row in rows:
        if (not isinstance(row, dict) or not isinstance(row.get('identity'),dict)
                or not isinstance(row.get('case'),str) or type(row.get('trial')) is not int
                or not isinstance(row.get('mode'),str) or row.get('bundle_sha256') is not None and not isinstance(row['bundle_sha256'],str)
                or 'experiment' in row and not isinstance(row['experiment'],dict)):
            _fail('invalid_receipt')
        key = digest(row)
        slot = (row.get('bundle_sha256'), row.get('case'), row.get('trial'), row.get('mode'),
                digest({k:v for k,v in row.get('identity', {}).items() if k != 'treatment'}),
                row.get('experiment', {}).get('benchmark_rerun', 0))
        if slot in slots and slots[slot] != key: _fail('conflicting_attempt')
        slots[slot] = key
        unique[key] = row
    rows = list(unique.values())
    try:
        report = v5_evaluation.per_task_report(rows)
    except (ValueError, KeyError, TypeError, StopIteration, AttributeError):
        _fail('receipt_validation_failed')
    if sum(len(r['execution']['calls']) for r in rows) > MAX_EVENTS: _fail('event_limit')
    source = _source(rows, _text(label), 'tuckbit_receipts', trust)
    runs = {r['receipt_sha256']: r for task in report['tasks'] for arm in task['arms'] for r in arm['runs']}
    strata = {run['receipt_sha256']: task['stratum_sha256'] for task in report['tasks'] for arm in task['arms'] for run in arm['runs']}
    sessions = [_receipt_session(r, source['id'], runs[v5_evaluation.review_key(r)], model_map or {}, strata[v5_evaluation.review_key(r)]) for r in rows]
    comparisons = []
    for task in report['tasks']:
        bindings={run['receipt_sha256'] for arm in task['arms'] for run in arm['runs']}
        task_rows=[row for row in rows if v5_evaluation.review_key(row) in bindings]
        for pair in task['paired_comparisons']:
            candidates = [r for r in task_rows if r['case'] == pair['case'] and r['trial'] == pair['trial'] and r['mode'] == pair['arm']]
            for b in candidates:
                baseline=[r for r in task_rows if r['case']==b['case'] and r['trial']==b['trial'] and r['mode']=='A'
                          and r.get('experiment',{}).get('benchmark_rerun',0)==b.get('experiment',{}).get('benchmark_rerun',0)]
                if len(baseline)!=1:_fail('ambiguous_evaluator_pair')
                a=baseline[0]
                qualified = pair['quality_qualified']
                comparisons.append({'id': digest([v5_evaluation.review_key(a), v5_evaluation.review_key(b)]),
                    'baseline_id': v5_evaluation.review_key(a), 'treatment_id': v5_evaluation.review_key(b),
                    'qualified': qualified, 'quality_qualified': qualified, 'evaluator': 'v5_evaluation.per_task_report',
                    'reasons': sorted(set(_reasons(a)+_reasons(b))) + ([] if pair['matched_identity'] else ['identity_mismatch']),
                    'matched_identity': pair['matched_identity'], 'sample_size': 1, 'task': b['case'], 'complexity': b['complexity'],
                    'kind': 'native' if a['observation_source'] == b['observation_source'] == 'native_public_events' else 'control',
                    'bundle_sha256': b.get('bundle_sha256'), 'trial': b['trial'], 'repeatable_efficacy': False,
                    'limitations': ['Single matched attempt; no repeatability or significance claim.', 'Receipt validation checks consistency, not cryptographic authenticity.']})
    return {'schema': SCHEMA, 'sources': [source], 'sessions': sessions, 'comparisons': comparisons, 'limitations': list(LIMITATIONS)}


def _trace_document(value, label):
    try:
        summary = trace_profiler.profile(value)
    except (ValueError, KeyError, TypeError):
        _fail('trace_validation_failed')
    source = _source(value, _text(label), 'trace_profiler/1', 'selected_file')
    names = {'input_tokens': 'reported_input_tokens', 'cached_input_tokens': 'reported_cached_input_tokens',
             'uncached_input_tokens': 'reported_uncached_input_tokens', 'output_tokens': 'reported_output_tokens',
             'wall_ms': 'wall_time_ms', 'tool_invocations': 'reported_metrics'}
    metrics = {name: _metric(summary[key], 'explicit_redacted_trace') for name,key in names.items() if name != 'tool_invocations'}
    metrics['tool_invocations'] = _metric(summary['reported_metrics']['tool_invocations'], 'explicit_redacted_trace')
    session = {'id': digest(value), 'source_id': source['id'], 'kind': 'session', 'title': 'Selected redacted trace',
        'agent': None, 'provider': None, 'model': None, 'project': None, 'started_at': None, 'arm': None,
        'status': 'completed' if summary['verified_outcome'] else 'unknown', 'task': None, 'domain': None, 'complexity': None,
        'metrics': metrics, 'acceptance': {'accepted': summary['verified_outcome'] and summary['acceptance_checks_passed'],
            'required': None, 'performed': None, 'all_passed': summary['acceptance_checks_passed'], 'independent': False, 'provenance': 'caller_reported_not_independent'},
        'activation': [_stage(s) for s in STAGES], 'policy': {'qualified': None, 'observed_commands': None, 'classified_commands': None,
            'unclassified': None, 'reason_counts': {}, 'provenance': 'unavailable'},
        'events': [{'id': digest([source['id'], i]), 'order': i, 'timestamp': None, 'category': e['category'],
                    'duration_ms': e.get('duration_ms'), 'output_bytes': e.get('output_bytes'), 'success': None,
                    'agent': e['role'], 'capabilities': [], 'evidence': None, 'provenance': 'explicit_redacted_trace'} for i,e in enumerate(value['events'])],
        'context': summary.get('execution', {}), 'qualification': {'qualified': False, 'evaluator': 'none', 'reasons': ['observational_trace_not_benchmark']},
        'limitations': summary['limitations'] + ['No timestamp/model/provider metadata is present in this trace format.']}
    return {'schema': SCHEMA, 'sources': [source], 'sessions': [session], 'comparisons': [], 'limitations': list(LIMITATIONS)}


def _timestamp(value):
    if value is None: return None
    _text(value, maximum=35)
    if not value.endswith('Z'): _fail('utc_timestamp_required')
    try: datetime.fromisoformat(value[:-1]+'+00:00')
    except ValueError: _fail('invalid_timestamp')
    return value


def normalized_document(value):
    """Round trips retain observations but cannot self-authorize benchmark eligibility."""
    _bounded(value)
    if not isinstance(value, dict) or set(value) != {'schema', 'sources', 'sessions', 'comparisons', 'limitations'} or value['schema'] != SCHEMA:
        _fail('unsupported_schema')
    if not isinstance(value['sources'], list) or len(value['sources']) > 2000 or not isinstance(value['sessions'], list) or len(value['sessions']) > MAX_SESSIONS:
        _fail('count_limit')
    if not isinstance(value['comparisons'], list) or len(value['comparisons']) > 10000:
        _fail('count_limit')
    out = copy.deepcopy(value)
    _safe_json(out)
    _strings(out['limitations'])
    source_ids = set()
    for source in out['sources']:
        if not isinstance(source, dict) or set(source) - {'id','sha256','label','kind','format','imported_at','trust','identity_semantics'}:
            _fail('invalid_source')
        if not HEX.fullmatch(str(source.get('sha256',''))) or source.get('id') in source_ids: _fail('invalid_source_identity')
        _text(source.get('id')); _text(source.get('label')); _text(source.get('format'))
        _timestamp(source.get('imported_at')); source_ids.add(source['id'])
        source['trust'] = 'selected_file'
        source['kind'] = 'selected_file'
    seen, total_events = {}, 0
    for row in out['sessions']:
        allowed = {'id','receipt_sha256','source_id','kind','title','agent','provider','model','project','started_at','arm','status','task','domain','complexity',
            'trial','bundle_sha256','stratum_sha256','identity','reported_kind','metrics','acceptance','activation','policy','events','context','experiment','qualification','limitations'}
        if not isinstance(row, dict) or set(row)-allowed or row.get('source_id') not in source_ids or row.get('kind') not in {'native','control','demo','session'}:
            _fail('invalid_session')
        for name in ('id','title','agent','provider','model','project','status','task','domain','complexity'):
            _text(row.get(name), nullable=name not in {'id','title'})
        if row.get('arm') not in {None,'A','B','C','D'}: _fail('invalid_arm')
        if row.get('reported_kind') is not None and row['reported_kind'] not in {'native','control','demo','session'}:_fail('invalid_reported_kind')
        if row['kind']=='native':
            row.setdefault('reported_kind','native')
            row['kind']='session'
        row['started_at'] = _timestamp(row.get('started_at'))
        row['metrics'] = _metrics(row.get('metrics'))
        for field in ('receipt_sha256','bundle_sha256','stratum_sha256'):
            if row.get(field) is not None and not HEX.fullmatch(str(row[field])):_fail('invalid_receipt_identity')
        identity=row.get('identity')
        if identity is not None:
            _shape(identity,' '.join(v4_runner.IDENTITY),'invalid_runtime_identity')
            if any(not HEX.fullmatch(str(item)) for item in identity.values()):_fail('invalid_runtime_identity')
        experiment=row.get('experiment')
        if experiment is not None:
            _shape(experiment,'seed schedule_sha256 order_index block_order source_before_sha256 workspace_sha256 benchmark_rerun control_variant','invalid_experiment')
            for name in ('schedule_sha256','source_before_sha256','workspace_sha256'):
                if name in experiment and not HEX.fullmatch(str(experiment[name])):_fail('invalid_experiment')
            for name in ('seed','order_index','benchmark_rerun'):
                if name in experiment and (type(experiment[name]) is not int or experiment[name]<0):_fail('invalid_experiment')
            if experiment.get('block_order') is not None and experiment['block_order'] not in {'ABC','BCA','CAB','CBA','ACB','BAC'}:_fail('invalid_experiment')
            if experiment.get('control_variant') is not None and experiment['control_variant'] not in v4_runner.CONTROL_VARIANTS:_fail('invalid_experiment')
        _validate_structures(row)
        _strings(row.get('limitations',[]))
        _qualification(row.get('qualification',{}))
        total_events += len(row.get('events',[]))
        if total_events > MAX_EVENTS: _fail('event_limit')
        content = digest(row)
        if row['id'] in seen and seen[row['id']] != content: _fail('conflicting_session')
        seen[row['id']] = content
        prior_acceptance=row.get('acceptance',{})
        prior_acceptance['reported_independent']=prior_acceptance.get('reported_independent',prior_acceptance.get('independent'))
        prior_acceptance['independent']=False
        row['acceptance']=prior_acceptance
        prior = row.get('qualification', {})
        row['qualification'] = {**prior, 'qualified': False, 'reported_eligible': prior.get('reported_eligible', prior.get('reported_qualified',prior.get('qualified'))),
                                'reported_reasons': prior.get('reported_reasons', prior.get('reasons', [])),
                                'reported_evaluator': prior.get('reported_evaluator', prior.get('evaluator')),
                                'evaluator': 'external_normalized_export_unverified',
                                'reasons': ['original_receipts_required_to_revalidate']}
        row['limitations'] = list(dict.fromkeys([*row.get('limitations', []), 'Imported normalized observations; original receipt evaluation is not authenticated by this export.']))
    unique = {}
    for row in out['sessions']: unique.setdefault(row['id'], row)
    out['sessions'] = list(unique.values())
    for pair in out['comparisons']:
        if not isinstance(pair,dict) or set(pair)-{'id','baseline_id','treatment_id','qualified','quality_qualified','evaluator','reasons','matched_identity','sample_size','task','complexity','kind','bundle_sha256','trial','repeatable_efficacy','limitations','reported_kind','reported_qualified','reported_reasons','reported_evaluator'}:
            _fail('invalid_comparison')
        _qualification({k:v for k,v in pair.items() if k in {'qualified','evaluator','reasons','reported_qualified','reported_reasons','reported_evaluator'}})
        if pair.get('baseline_id') not in seen or pair.get('treatment_id') not in seen: _fail('invalid_comparison_identity')
        if pair.get('reported_kind') is not None and pair['reported_kind'] not in {'native','control','demo','session'}:_fail('invalid_reported_kind')
        if pair.get('kind')=='native':
            pair.setdefault('reported_kind','native')
            pair['kind']='session'
        pair.update(reported_qualified=pair.get('reported_qualified',pair.get('qualified')),
                    reported_reasons=pair.get('reported_reasons',pair.get('reasons',[])),
                    reported_evaluator=pair.get('reported_evaluator',pair.get('evaluator')),
                    qualified=False,quality_qualified=False,evaluator='external_normalized_export_unverified',
                    reasons=['original_receipts_required_to_revalidate'],repeatable_efficacy=False)
    return out


def _safe_json(value, depth=0):
    if depth > 15: _fail('nesting_limit')
    if isinstance(value, dict):
        if len(value)>100: _fail('object_limit')
        for key,item in value.items():
            if not isinstance(key,str) or key in {'__proto__','constructor','prototype','prompt','raw','stderr','command','path','credentials','transcript','reasoning'}:
                _fail('private_or_unsafe_field')
            _safe_json(item,depth+1)
    elif isinstance(value,list):
        if len(value)>MAX_EVENTS: _fail('count_limit')
        for item in value: _safe_json(item,depth+1)
    elif isinstance(value,str): _text(value,maximum=500)
    elif value is not None and type(value) not in {bool,int,float}: _fail('invalid_value')
    elif type(value) in {int,float} and not math.isfinite(value): _fail('invalid_number')



def _strings(value):
    if not isinstance(value,list) or len(value)>200:_fail('invalid_text_list')
    for item in value:_text(item,maximum=500)


def _qualification(value):
    if not isinstance(value,dict) or set(value)-{'qualified','evaluator','reasons','reported_qualified','reported_eligible','reported_reasons','reported_evaluator'}:
        _fail('invalid_qualification')
    for name in ('qualified','reported_qualified','reported_eligible'):
        if value.get(name) is not None and type(value[name]) is not bool:_fail('invalid_qualification')
    for name in ('evaluator','reported_evaluator'):_text(value.get(name),nullable=True,maximum=150)
    for name in ('reasons','reported_reasons'):
        if name in value:_strings(value[name])


def _shape(value, fields, reason):
    if not isinstance(value,dict) or set(value)-set(fields.split()):_fail(reason)


def _context(value):
    if value==[]:return
    _shape(value,'total_observed_calls stream_complete tool_totals by_category context_counts context_observations capability_lifecycle coverage observer_ns limitations','invalid_context_summary')
    numeric_groups={
        'tool_totals':'successful failed unknown_status potential_repeated_calls output_bytes_observed_sum output_bytes_complete_total output_bytes_measured_calls duration_ms_observed_sum duration_ms_measured_calls',
        'context_counts':'independently_irrelevant_activation independently_unnecessary_activation independently_unnecessary first_observed_access unverified_delivery required_verification truncated_output_recovery changed_source_reread identical_unchanged_source_reread unknown_purpose_reread potential_redundant_unchanged_rereads relevant_context irrelevant_context unknown_relevance_context'}
    for group,fields in numeric_groups.items():
        _shape(value.get(group,{}),fields,'invalid_context_summary')
        if any(v is not None and not _number(v) for v in value.get(group,{}).values()):_fail('invalid_context_summary')
    _shape(value.get('by_category',{}),' '.join(execution_events.CATEGORIES),'invalid_context_summary')
    for group in value.get('by_category',{}).values():
        _shape(group,'calls successful failed unknown_status output_bytes_observed output_bytes_coverage duration_ms_observed duration_ms_coverage independently_unnecessary potential_repeated_calls','invalid_context_summary')
        if any(v is not None and not _number(v) for v in group.values()):_fail('invalid_context_summary')
    observations=value.get('context_observations',[])
    if not isinstance(observations,list) or len(observations)>10000:_fail('invalid_context_summary')
    for row in observations:
        _shape(row,'call classification previously_available_to_agent delivery_verified source_changed observed_in_other_agent required_verification independently_unnecessary relevance','invalid_context_summary')
        if not HEX.fullmatch(str(row.get('call',''))):_fail('invalid_context_summary')
        if row.get('classification') not in {'first_observed_access','unverified_delivery','required_verification','truncated_output_recovery','changed_source_reread','identical_unchanged_source_reread','unknown_purpose_reread'}:_fail('invalid_context_summary')
        if row.get('relevance') not in {'unknown','relevant','irrelevant'}:_fail('invalid_context_summary')
        for key in ('previously_available_to_agent','delivery_verified','source_changed','observed_in_other_agent','required_verification','independently_unnecessary'):
            if row.get(key) is not None and type(row[key]) is not bool:_fail('invalid_context_summary')
    lifecycle=value.get('capability_lifecycle',{})
    if not isinstance(lifecycle,dict):_fail('invalid_context_summary')
    for identity,stages in lifecycle.items():
        if not HEX.fullmatch(identity):_fail('invalid_context_summary')
        _shape(stages,' '.join(execution_events.STAGES),'invalid_context_summary')
        if any(v is not None and type(v) is not bool for v in stages.values()):_fail('invalid_context_summary')
    _shape(value.get('coverage',{}),'exact_file_observations candidate_file_observations tool_calls unclassified_calls file_range_coverage purpose_and_relevance','invalid_context_summary')
    if 'limitations' in value:_strings(value['limitations'])


def _validate_structures(row):
    acceptance=row.get('acceptance',{})
    if not isinstance(acceptance,dict) or set(acceptance)-{'accepted','required','performed','all_passed','provenance','contract','independent','reported_independent'}:
        _fail('invalid_acceptance')
    if acceptance.get('contract') is not None and not HEX.fullmatch(str(acceptance['contract'])):_fail('invalid_acceptance_contract')
    for name in ('accepted','all_passed','independent','reported_independent'):
        if acceptance.get(name) is not None and type(acceptance[name]) is not bool: _fail('invalid_acceptance')
    for name in ('required','performed'):
        if acceptance.get(name) is not None and (type(acceptance[name]) is not int or not 0 <= acceptance[name] <= 100000): _fail('invalid_acceptance')
    if acceptance.get('performed') is not None and acceptance.get('required') is not None and acceptance['performed']>acceptance['required']:
        _fail('invalid_acceptance')
    stages=row.get('activation',[])
    if not isinstance(stages,list) or len(stages)>len(STAGES): _fail('invalid_activation')
    seen=set()
    for stage in stages:
        if not isinstance(stage,dict) or set(stage)-{'stage','state','note','provenance','events'} or stage.get('stage') not in STAGES or stage['stage'] in seen or stage.get('state') not in STATES:
            _fail('invalid_activation')
        seen.add(stage['stage'])
        stage_events=stage.get('events',[])
        if not isinstance(stage_events,list) or len(stage_events)>10000:_fail('invalid_activation_events')
        for event in stage_events:
            _shape(event,'id order timestamp category source_sha256 content_sha256 delivery_complete provenance','invalid_activation_event')
            _timestamp(event.get('timestamp'))
            for key in ('source_sha256','content_sha256'):
                if event.get(key) is not None and not HEX.fullmatch(str(event[key])):_fail('invalid_activation_event')
            if event.get('delivery_complete') is not None and type(event['delivery_complete']) is not bool:_fail('invalid_activation_event')
    events=row.get('events',[])
    if not isinstance(events,list) or len(events)>10000: _fail('event_limit')
    ids=set()
    allowed={'id','agent','category','operation','success','output_bytes','duration_ms','result','evidence','capabilities','order','timestamp','provenance'}
    for event in events:
        if not isinstance(event,dict) or set(event)-allowed or not isinstance(event.get('id'),str) or event['id'] in ids: _fail('duplicate_or_invalid_event')
        ids.add(event['id'])
        _text(event.get('category'), maximum=64)
        if event.get('success') is not None and type(event['success']) is not bool: _fail('invalid_event_outcome')
        for key in ('operation','result'):
            if event.get(key) is not None and not HEX.fullmatch(str(event[key])): _fail('invalid_event_digest')
        evidence=event.get('evidence')
        if evidence is not None:
            if not isinstance(evidence,dict) or set(evidence)!={'source','selector','revision','content','delivered','truncated','bytes','tokens'}: _fail('invalid_context_evidence')
            for key in ('source','selector','revision','content'):
                if not HEX.fullmatch(str(evidence[key])): _fail('invalid_context_digest')
            if type(evidence['delivered']) is not bool or evidence['truncated'] is not None and type(evidence['truncated']) is not bool: _fail('invalid_context_delivery')
            for key in ('bytes','tokens'):
                if evidence[key] is not None and not _number(evidence[key]): _fail('invalid_context_metric')
        capabilities=event.get('capabilities',[])
        if not isinstance(capabilities,list) or len(capabilities)>20: _fail('invalid_capability')
        for capability in capabilities:
            if not isinstance(capability,dict) or set(capability)!={'id','stage'} or not HEX.fullmatch(str(capability['id'])) or capability['stage'] not in execution_events.STAGES: _fail('invalid_capability')
        if event.get('order') is not None and (type(event['order']) is not int or event['order']<0): _fail('invalid_event_order')
        _timestamp(event.get('timestamp'))
        for name in ('duration_ms','output_bytes'):
            if event.get(name) is not None and not _number(event[name]): _fail('invalid_event_metric')
    # The original supplied order is retained; timestamps do not establish causality.
    _context(row.get('context',{}))
    policy=row.get('policy',{})
    if not isinstance(policy,dict) or set(policy)-{'qualified','observed_commands','classified_commands','unclassified','reason_counts','provenance'}:
        _fail('invalid_policy')
    if policy.get('qualified') is not None and type(policy['qualified']) is not bool: _fail('invalid_policy')
    for key in ('observed_commands','classified_commands','unclassified'):
        if policy.get(key) is not None and (type(policy[key]) is not int or not 0<=policy[key]<=100000): _fail('invalid_policy')


# Wire shapes verified against openai/codex 89461ea (protocol.rs and history/rollout_payload.rs).
# Raw selected content is parsed in memory and never copied into the read model.
def import_text(text):
    data = text.encode('utf-8')
    if len(data) > MAX_BYTES: _fail('size_limit')
    try:
        value = parse_bytes(data)
    except ImportError as error:
        if str(error) != 'invalid_json': raise
        return codex_rollout(text)
    if isinstance(value, dict) and value.get('type') == 'session_meta':
        return codex_rollout(text)
    return import_document(value)


def codex_rollout(text):
    if len(text.encode('utf-8')) > MAX_BYTES: _fail('size_limit')
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines or len(lines) > MAX_EVENTS: _fail('codex_line_limit')
    rows = []
    for index, line in enumerate(lines):
        try: rows.append(parse_bytes(line.encode('utf-8')))
        except ImportError as error:
            # A broken later line in a session export is distinct from selecting a non-JSON file.
            if index and isinstance(rows[0], dict) and rows[0].get('type') == 'session_meta' and str(error) == 'invalid_json': _fail('codex_malformed_line')
            raise
    if any(not isinstance(row, dict) or not isinstance(row.get('payload'), dict) for row in rows):
        _fail('codex_invalid_record')
    meta = rows[0]['payload']
    if rows[0].get('type') != 'session_meta': _fail('codex_session_meta_required')
    try: thread = str(UUID(meta.get('id', '')))
    except (ValueError, TypeError, AttributeError): _fail('codex_invalid_identity')
    if any(row.get('type') == 'session_meta' for row in rows[1:]): _fail('codex_multiple_sessions')
    if meta.get('forked_from_id') or meta.get('parent_thread_id') or meta.get('history_base'):
        _fail('codex_inherited_history_unsupported')

    def instant(value):
        if value is None: return None
        if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)', value):
            _fail('codex_invalid_timestamp')
        try: return datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError: _fail('codex_invalid_timestamp')

    started = instant(meta.get('timestamp'))
    if started is None: _fail('codex_timestamp_required')
    timestamps = [instant(row.get('timestamp')) for row in rows]
    if any(at is not None and at < started for at in timestamps): _fail('codex_timestamp_before_session')
    valid_times = [at for at in timestamps if at is not None]
    out_of_order = any(a > b for a,b in zip(valid_times,valid_times[1:]))
    span_complete = len(valid_times) == len(rows) and not out_of_order
    counters = ('input_tokens', 'cached_input_tokens', 'output_tokens')
    latest, previous, snapshots, missing_usage = None, None, 0, False
    models, missing_model, events, calls, errors = set(), False, [], {}, set()
    limits = [
        'Codex client counters may include estimates or replay; they are not an authenticated provider invoice.',
        'The final cumulative snapshot is used once; last-response counters are never added to it.',
        'Session elapsed span includes idle time and is not measured agent execution latency.',
        'No independent correctness, policy, TuckBit activation, retry or source-reread evidence is available.',
        'Only explicit tool-call items are counted; shell arguments and results are discarded, so their purpose and outcome remain unknown.',
        'Calendar buckets assign the session total to its start date; within-session daily allocation is unavailable.',
    ]
    for index, row in enumerate(rows):
        payload, kind = row['payload'], row.get('type')
        if kind == 'turn_context':
            model = payload.get('model')
            if isinstance(model, str) and re.fullmatch(r'(?:gpt-[a-zA-Z0-9._-]+|o[1-9][a-zA-Z0-9._-]*)', model) and len(model) <= 100:
                models.add(model)
            else: missing_model = True
        if kind == 'event_msg' and payload.get('type') == 'token_count':
            info = payload.get('info')
            if info is None: continue
            if not isinstance(info, dict): _fail('codex_invalid_usage')
            total = info.get('total_token_usage')
            if not models: missing_model = True
            if total is None:
                missing_usage, latest = True, None
                continue
            if not isinstance(total, dict): _fail('codex_invalid_usage')
            current = {key: total.get(key) for key in counters}
            if any(value is not None and (type(value) is not int or not 0 <= value <= 10**15) for value in current.values()):
                _fail('codex_invalid_usage')
            if current['input_tokens'] is not None and current['cached_input_tokens'] is not None and current['cached_input_tokens'] > current['input_tokens']:
                _fail('codex_cache_exceeds_input')
            if total.get('total_tokens') is not None and all(current[key] is not None for key in ('input_tokens','output_tokens')):
                if type(total['total_tokens']) is not int or total['total_tokens'] != current['input_tokens'] + current['output_tokens']:
                    _fail('codex_inconsistent_total')
            if previous and any(current[key] is not None and previous[key] is not None and current[key] < previous[key] for key in counters):
                _fail('codex_counter_reset')
            # Keep the last known counter for reset detection, never fill missing final fields.
            previous = {key: current[key] if current[key] is not None else (previous or {}).get(key) for key in counters}
            latest, snapshots = current, snapshots + 1
        if kind == 'event_msg' and payload.get('type') == 'error':
            errors.add(digest([row.get('timestamp'), payload]))
        if kind == 'response_item' and payload.get('type') in {'function_call','custom_tool_call','local_shell_call'}:
            call = payload.get('call_id') or payload.get('id')
            if not isinstance(call, str) or not call or len(call) > 200: _fail('codex_call_identity_required')
            name = payload.get('name')
            if name is not None and not isinstance(name, str): _fail('codex_invalid_tool_name')
            category = {'apply_patch':'source_modification', 'update_plan':'validation_review', 'request_user_input':'validation_review',
                        'view_image':'file_inspection'}.get(name, 'other')
            identity = digest([thread, call])
            if identity in calls:
                if calls[identity] != (payload['type'], name): _fail('codex_conflicting_call')
                continue
            calls[identity] = (payload['type'], name)
            events.append({'id':identity,'order':index,'timestamp':timestamps[index].isoformat().replace('+00:00','Z') if timestamps[index] else None,
                'category':category,'success':None,'duration_ms':None,'output_bytes':None,'evidence':None,
                'capabilities':[],'provenance':'codex_rollout_call_item'})
    if len(events) > 10000: _fail('event_limit')
    if out_of_order: limits.append('Record timestamps are out of order; supplied order is preserved and elapsed duration is unavailable.')
    if not span_complete and not out_of_order: limits.append('Some record timestamps are absent; session elapsed duration is unavailable.')
    if missing_usage: limits.append('Incremental-only reports were ignored: no stable response identity supports safe accumulation.')
    if latest is None: limits.append('No usable final cumulative token snapshot is available; token usage is unavailable.')
    metrics = {key:_metric((latest or {}).get(key), 'codex_client_cumulative', 'observed' if (latest or {}).get(key) is not None else 'unknown') for key in counters}
    input_value, cached = [metrics[key]['value'] for key in counters[:2]]
    metrics['uncached_input_tokens'] = _metric(input_value-cached if input_value is not None and cached is not None else None, 'codex_client_input_minus_cached', 'derived' if input_value is not None and cached is not None else 'unknown')
    metrics['tool_calls_observed'] = _metric(len(events), 'codex_selected_call_items', 'observed')
    metrics['error_events_observed'] = _metric(len(errors), 'codex_selected_error_events', 'observed')
    metrics['session_elapsed_ms'] = _metric((max(valid_times)-started).total_seconds()*1000 if span_complete else None, 'codex_timestamp_span', 'derived' if span_complete else 'unknown')
    metrics['usage_snapshots_observed'] = _metric(snapshots, 'codex_selected_token_count_events', 'observed')
    provider = 'OpenAI' if meta.get('model_provider') == 'openai' else None
    model = next(iter(models)) if len(models) == 1 and not missing_model else None
    if model is None: limits.append('Model is missing, unsupported or changed within the session; model attribution and cost are unavailable.')
    if provider is None: limits.append('Provider is absent or not a recognized OpenAI provider ID; provider attribution and cost are unavailable.')
    for key in counters:
        if metrics[key]['value'] is None: limits.append(key+' is absent in the final cumulative snapshot; it is not zero.')
    project = meta.get('cwd')
    project = 'project:'+digest(project)[:24] if isinstance(project,str) and project else None
    session = {'id':digest(['codex_rollout',thread]),'kind':'session','title':'Codex session '+digest(thread)[:12],
        'agent':'Codex','provider':provider,'model':model,'project':project,'started_at':started.isoformat().replace('+00:00','Z'),
        'arm':None,'status':'observed','task':None,'domain':None,'complexity':None,'metrics':metrics,
        'acceptance':{'accepted':None,'independent':False,'provenance':'unavailable'},
        'activation':[_stage(stage) for stage in STAGES],'policy':{},'events':events,'context':{},
        'qualification':{'qualified':False,'evaluator':'none','reasons':['observational_session_not_benchmark']},'limitations':limits}
    source = _source(session,'Selected Codex JSONL','codex.rollout.jsonl/1','selected_file')
    source['identity_semantics'] = 'SHA-256 of sanitized observations; session and project identities are hashed; raw content is discarded.'
    session['source_id'] = source['id']
    result = {'schema':SCHEMA,'sources':[source],'sessions':[session],'comparisons':[],'limitations':list(LIMITATIONS)}
    return normalized_document(result)


def _import_document(value, label='Manual import'):
    _bounded(value)
    if isinstance(value, list): return receipts_document(value,label)
    if not isinstance(value, dict): _fail('unsupported_schema')
    if value.get('schema') == SCHEMA: return normalized_document(value)
    if value.get('schema') == 'tuckbit.session/1' and set(value)=={'schema','session'}:
        row=copy.deepcopy(value['session']); source=_source(value,_text(label),'tuckbit.session/1','selected_file')
        row['source_id']=source['id'];row.setdefault('kind','session');row.setdefault('title','Selected session observation')
        row.setdefault('qualification',{'qualified':False,'evaluator':'none','reasons':['observational_session_not_benchmark']})
        return normalized_document({'schema':SCHEMA,'sources':[source],'sessions':[row],'comparisons':[],'limitations':list(LIMITATIONS)})
    if value.get('schema') == 1 and 'events' in value: return _trace_document(value,label)
    if value.get('schema') in {5,51,52}: return receipts_document([value],label)
    _fail('unsupported_schema')



def import_document(value, label='Manual import'):
    try:
        return _import_document(value,label)
    except ImportError:
        raise
    except (ValueError,TypeError,KeyError,AttributeError,IndexError,RecursionError):
        _fail('invalid_document')


def historical(include_controls=False):
    folder=ROOT/'docs/evaluations'
    bundle=json.loads((folder/'V51_BUNDLE.json').read_text())
    if v4_runner.fingerprint(bundle['payload']) != bundle['sha256']: _fail('historical_bundle_changed')
    model=bundle['payload']['model']['id']
    model_map={v4_runner.fingerprint(model):model}
    files=['V51_NATIVE_RECEIPTS.json','V52_D11_CALIBRATION_RECEIPTS.json']
    if include_controls:files.append('V52_CONTROLLED_RECEIPTS.json')
    result={'schema':SCHEMA,'sources':[],'sessions':[],'comparisons':[],'limitations':list(LIMITATIONS)}
    for name in files:
        value=json.loads((folder/name).read_text())
        doc=receipts_document(value,name,'repository',model_map)
        for key in ('sources','sessions','comparisons'):result[key].extend(doc[key])
    # Closed-study report explicitly says B was not attempted; do not turn it into a failure.
    report=(folder/'V52_D11_CALIBRATION.md').read_text()
    if 'B was not launched' not in report or 'actual CA' not in report:
        _fail('historical_study_metadata_changed')
    source=_source({'report_sha256':hashlib.sha256(report.encode()).hexdigest()},'V52 closed-study schedule','study_metadata','repository')
    result['sources'].append(source)
    result['sessions'].append({'id':digest(['V52_D11','B','unattempted',source['sha256']]),'source_id':source['id'],
        'kind':'native','title':'D11-small · B · not attempted','agent':'Codex','provider':'OpenAI','model':model,
        'project':'TuckBit evaluation','started_at':None,'arm':'B','status':'unattempted','task':'D11-small','domain':'D11','complexity':'small',
        'metrics':{},'acceptance':{'accepted':None,'required':100,'performed':None,'all_passed':None,'independent':False,'provenance':'closed_study_report'},
        'activation':[_stage(s,'not_observed','Arm was not launched after the study stop.','closed_study_report') for s in STAGES],
        'policy':{'qualified':None,'observed_commands':None,'classified_commands':None,'unclassified':None,'reason_counts':{},'provenance':'unavailable'},
        'events':[],'context':{},'qualification':{'qualified':False,'evaluator':'closed_study_report','reasons':['not_attempted_after_stop']},
        'limitations':['Unattempted arm is excluded from attempted-success denominators; not a failed launch.']})
    result['limitations'].append('Community suggestions from @bomtobe.sw (Orke at BOMTOBE), GitHub issue #5, are research feedback, not independent TuckBit validation or product integration.')
    return result



def static_export(destination, *, include_controls=False, web_root=None):
    """Copy only public application assets and evaluated sanitized historical data."""
    source=Path(web_root or ROOT/'web').absolute()
    target=Path(destination).absolute()
    if source==target or source in target.parents or '..' in target.parts or any(p.is_symlink() for p in (target,*target.parents)):
        _fail('unsafe_output_directory')
    if not target.parent.is_dir() or target.exists():
        _fail('output_directory_must_be_new')
    if not source.is_dir() or any(p.is_symlink() for p in (source,*source.parents)):
        _fail('unsafe_asset_directory')
    assets={}
    total=0
    for folder,directories,files in os.walk(source,followlinks=False):
        directories[:]=[name for name in directories if not name.startswith('.')]
        for name in directories:
            if (Path(folder)/name).is_symlink(): _fail('asset_symlink')
        for name in files:
            path=Path(folder)/name
            if name.startswith('.') or (path.suffix not in ASSET_SUFFIXES and path.relative_to(source)!=Path('data/readiness.json')):continue
            fd=os.open(path,os.O_RDONLY|os.O_NONBLOCK|getattr(os,'O_NOFOLLOW',0))
            with os.fdopen(fd,'rb') as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode): _fail('invalid_asset')
                data=stream.read(MAX_BYTES+1)
            total+=len(data)
            if len(data)>MAX_BYTES or total>16*MAX_BYTES: _fail('asset_size_limit')
            assets[path.relative_to(source)]=data
            if len(assets)>1000:_fail('asset_count_limit')
    if Path('index.html') not in assets: _fail('missing_application_entry')
    data=json.dumps(historical(include_controls),indent=2,allow_nan=False).encode()+b'\n'
    target.mkdir(mode=0o700)
    for relative,content in {**assets,Path('data/historical.json'):data}.items():
        output=target/relative
        output.parent.mkdir(parents=True,exist_ok=True)
        with output.open('xb') as stream:stream.write(content)
    return {'files':len(assets)+1,'historical_sha256':hashlib.sha256(data).hexdigest()}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input',nargs='?',help='Explicit sanitized JSON file; no session-directory scans')
    parser.add_argument('--controls',action='store_true',help='Include clearly labeled historical model-free controls')
    outputs=parser.add_mutually_exclusive_group()
    outputs.add_argument('--output',type=Path,help='New sanitized JSON file; existing files are never overwritten')
    outputs.add_argument('--static-output',type=Path,help='New directory containing only application assets and sanitized historical JSON')
    args=parser.parse_args(argv)
    try:
        if args.static_output:
            if args.input: _fail('static_export_uses_historical_sources_only')
            result=static_export(args.static_output,include_controls=args.controls)
            print(json.dumps(result))
            return 0
        result=import_document(read_selected(args.input)) if args.input else historical(args.controls)
        text=json.dumps(result,indent=2,allow_nan=False)+'\n'
        if args.output:
            with args.output.open('x',encoding='utf-8') as stream:stream.write(text)
        else:sys.stdout.write(text)
    except (ValueError,OSError,KeyError):
        print('Observatory export failed: invalid_or_unavailable_source',file=sys.stderr)
        return 2
    return 0


if __name__=='__main__':raise SystemExit(main())
