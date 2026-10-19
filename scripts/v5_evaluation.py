"""Correctness-first V5 analysis over V4 receipts, graders and atomic journals."""
import argparse
from collections import Counter, defaultdict
import json
import os
from pathlib import Path
import statistics

import execution_events
from execution_state import load, write_new, symlink, MAX_BYTES
from benchmark_journal import JournalError
import v4_runner
import v4_analysis

ROOT = Path(__file__).resolve().parents[1]


def _contract(case):
    return v4_runner.fingerprint({k: case[k] for k in ("grader_sha256", "requirements", "permissions", "source_revision", "dependency_fingerprint")})


def _expected(case_id):
    rows = json.loads((ROOT/'evals/v4/validation.json').read_text())["results"]
    return next(row['reference_checks'] for row in rows if row['id'] == case_id)


def base(receipt):
    return {**{k: v for k, v in receipt.items() if k not in {"execution", "validation", "namespace"}}, "schema": 4}


def enrich(receipt, execution, grading, case, namespace):
    value = {**receipt, "schema": 5, "execution": execution, "namespace": namespace,
             "validation": {"contract": _contract(case), "required": _expected(case['id']),
                            "performed": grading['checks'], "all_passed": grading['accepted'] is True}}
    if value['accepted'] and (grading['checks'] != value['validation']['required'] or not execution['complete']):
        value.update(accepted=False, comparison_eligible=False, validation_complete=False, status='incomplete')
        value['failure_categories'] = sorted(set(value['failure_categories']) | {'missing_validation', 'task_failed'})
    validate_receipt(value)
    return value


def validate_receipt(value):
    if not isinstance(value, dict) or value.get('schema') != 5 or not {'execution', 'validation', 'namespace'} <= value.keys():
        raise JournalError('V5 requires context/tool observations and independent validation')
    v4_runner.validate_receipt(base(value))
    execution_events.validate(value['execution'])
    case = next((c for c in v4_runner.corpus().cases() if c['id'] == value['case']), None)
    if (case is None or case['domain'] != value['domain'] or case['complexity'] != value['complexity']
            or value['identity']['source'] != case['source_revision']
            or value['identity']['dependencies'] != case['dependency_fingerprint']
            or not execution_events._digest(value['namespace'])):
        raise JournalError('V5 corpus identity differs')
    check = value['validation']
    if (not isinstance(check, dict) or set(check) != {'contract', 'required', 'performed', 'all_passed'}
            or check['contract'] != _contract(case) or check['required'] != _expected(case['id'])
            or type(check['performed']) is not int or not 0 <= check['performed'] <= 100000
            or type(check['all_passed']) is not bool
            or value['accepted'] and (not check['all_passed'] or check['performed'] != check['required'] or not value['execution']['complete'])
            or (value['observation_source'] == 'native_public_events') != (value['execution']['source'] == 'native_public_events')):
        raise JournalError('V5 validation coverage or provenance differs')
    return value


class V5Journal(v4_runner.V4Journal):
    validate_receipt = staticmethod(validate_receipt)


def review_key(row):
    return v4_runner.fingerprint(row)


def report(rows, reviews=None):
    if not isinstance(rows, list) or len(rows) > 1000:
        raise JournalError('Expected bounded V5 receipt list')
    for row in rows:
        validate_receipt(row)
    reviews = {} if reviews is None else reviews
    if not isinstance(reviews, dict) or set(reviews) - {review_key(r) for r in rows}:
        raise JournalError('Independent review must bind the complete immutable run receipt')
    quality = v4_analysis.report([base(r) for r in rows])
    summaries = {review_key(r):execution_events.summarize(r['execution'], reviews.get(review_key(r))) for r in rows}
    observations = [{"case": r['case'], "domain": r['domain'], "complexity": r['complexity'], "mode": r['mode'],
                     "trial": r['trial'], "accepted": r['accepted'], "eligible": r['comparison_eligible'],
                     "independent_validation": r['validation'], "provider_metrics": r['metrics'],
                     "review_binding":review_key(r), "execution": summaries[review_key(r)]} for r in rows]
    slots = defaultdict(dict)
    for row in rows:
        slots[(row['case'], row['trial'])][row['mode']] = row
    comparisons = []
    for (case, trial), arms in slots.items():
        for arm in ('B', 'C', 'D'):
            if 'A' not in arms or arm not in arms:
                continue
            a,b = arms['A'],arms[arm]
            matched = all(a['identity'][k] == b['identity'][k] for k in v4_analysis.MATCHED_IDENTITIES)
            qualified = matched and all(r['comparison_eligible'] for r in (a,b))
            same_namespace = a['namespace'] == b['namespace']
            counts = [summaries[review_key(r)] for r in (a,b)]
            differences = {}
            for name, getter in {
                'observed_tool_calls': lambda s:s['total_observed_calls'],
                'potential_redundant_unchanged_rereads': lambda s:s['context_counts'].get('potential_redundant_unchanged_rereads',0)
            }.items():
                covered = name == 'observed_tool_calls' or same_namespace and all(s['coverage']['exact_file_observations'] > 0 for s in counts)
                differences[name] = getter(counts[0])-getter(counts[1]) if qualified and covered else None
            comparisons.append({'case':case, 'domain':a['domain'], 'complexity':a['complexity'], 'trial':trial, 'arm':arm,
                'quality_qualified':qualified, 'matched_identity':matched, 'same_opaque_namespace':same_namespace,
                'observed_baseline_minus_treatment':differences,
                'scope':'Observed public events only; file/range coverage is partial. No total-context or token savings inference.'})
    groups = []
    for dimension in ('case','domain','complexity','mode'):
        for label in sorted({r[dimension] for r in rows}):
            for arm in ('A','B','C','D'):
                subset = [r for r in rows if r[dimension] == label and r['mode'] == arm]
                if not subset: continue
                accepted = [r for r in subset if r['accepted']]
                walls = [r['metrics']['wall_ms']['value'] for r in accepted if r['metrics']['wall_ms']['value'] is not None]
                groups.append({'dimension':dimension, 'value':label, 'mode':arm, 'attempts':len(subset), 'verified_success_rate':len(accepted)/len(subset),
                    'accepted':len(accepted), 'failed_or_incomplete':len(subset)-len(accepted),
                    'median_time_to_accepted_ms':statistics.median(walls) if walls else None,
                    'tool_calls_per_verified_success': statistics.mean(len(r['execution']['calls']) for r in accepted) if accepted else None})
    # Never pool models/environments or correlated tasks for a resource confidence interval.
    strata = defaultdict(list)
    for pair in comparisons:
        if pair['quality_qualified']:
            anchor=slots[(pair['case'],pair['trial'])]['A']
            key=(pair['case'],pair['arm'],*(anchor['identity'][k] for k in v4_analysis.STRATUM_IDENTITIES))
            strata[key].append(pair)
    uncertainty=[]
    for key,pairs in sorted(strata.items()):
        metrics={}
        for metric in ('observed_tool_calls','potential_redundant_unchanged_rereads'):
            values=[p['observed_baseline_minus_treatment'][metric] for p in pairs if p['observed_baseline_minus_treatment'][metric] is not None]
            interval=v4_analysis._bootstrap(values)
            if interval: interval={**interval,'unit':'count'}
            metrics[metric]={'pairs':len(values),'median_difference':statistics.median(values) if values else None,
                             'dispersion':v4_analysis._dispersion(values),'bootstrap_95_percent_ci':interval}
        uncertainty.append({'case':key[0], 'arm':key[1], 'stratum_sha256':v4_runner.fingerprint(key[2:]),'metrics':metrics})
    demonstrated = any(p['quality_qualified'] and all(v is not None for v in p['observed_baseline_minus_treatment'].values()) for p in comparisons)
    return {'schema':5, 'track':'mandatory_context_tool_correctness', 'quality_first':quality, 'runs':observations,
            'groups':groups, 'paired_comparisons':comparisons, 'uncertainty':uncertainty,
            'completion_gate_met':demonstrated, 'token_savings_claim':False,
            'conclusion': 'Matched independently accepted runs expose coverage-limited public context/tool differences; no generalized or token-saving claim follows.' if demonstrated else 'Native task-matched behavior remains unproven: no eligible accepted pair has sufficient observed context evidence. Controlled tests validate instrumentation only.',
            'roadmap': [{'mode':mode,'decision':'Unproven','proposal':proposal} for mode,proposal in {
                'Fast':'Avoid mandatory setup; investigate independently unnecessary reads/activation.',
                'Standard':'Select relevant instructions/context from qualified matched evidence.',
                'Deep':'Preserve comprehensive independent checks; do not optimize them away.',
                'Parallel':'Count duplicate worker context separately from required independent review.',
                'Continuous':'Reuse current source-bound evidence; invalidate on source changes.'}.items()]}


EFFORT_METRICS = ('human_review_ms', 'human_edit_ms', 'human_interventions', 'agent_retries',
                  'tool_retries', 'benchmark_reruns', 'preparation_ms', 'automated_edit_observed_sum_ms')


def _distribution(metrics):
    values = [m['value'] for m in metrics if m['value'] is not None]
    return {'values': values, 'available': len(values), 'missing': len(metrics)-len(values),
            'median': statistics.median(values) if values else None,
            'min': min(values) if values else None, 'max': max(values) if values else None,
            'provenance': dict(Counter(m['source'] for m in metrics))}


def per_task_report(rows, reviews=None, human_effort=None, interrupted=None):
    """Task-first distributions over immutable, validated V5/V5.1/V5.2 receipts."""
    import benchmark_bundle
    if not isinstance(rows, list) or len(rows) > 1000:
        raise JournalError('Expected bounded task receipt list')
    for row in rows:
        if not isinstance(row, dict): raise JournalError('Expected receipt')
        validator = {5: validate_receipt, 51: benchmark_bundle.validate_receipt,
                     52: getattr(benchmark_bundle, 'validate_v52_receipt', None)}.get(row.get('schema'))
        if validator is None: raise JournalError('Unsupported task receipt schema')
        validator(row)
    bindings = {review_key(row) for row in rows}
    reviews={} if reviews is None else reviews
    human_effort={} if human_effort is None else human_effort
    interrupted=[] if interrupted is None else interrupted
    if not isinstance(interrupted,list) or len(interrupted)>1000:raise JournalError('Bounded interrupted markers required')
    for marker in interrupted:v4_runner._marker(marker)
    def common(item):return {k:v for k,v in item['identity'].items() if k!='treatment'}
    def slot(item):return (item['case'],item['trial'],item['mode'],v4_runner.fingerprint(common(item)))
    complete_slots={slot(row) for row in rows}
    lost_slots=[slot(m) for m in interrupted]
    if len(lost_slots)!=len(set(lost_slots)) or complete_slots&set(lost_slots):
        raise JournalError('Duplicate or completed interrupted observation')
    if (not isinstance(reviews, dict) or set(reviews)-bindings
            or not isinstance(human_effort, dict) or set(human_effort)-bindings):
        raise JournalError('Annotations must bind the complete original receipt')
    human_names = {'human_review_ms', 'human_edit_ms', 'human_interventions'}
    for annotation in human_effort.values():
        if (not isinstance(annotation, dict) or set(annotation) != human_names | {'provenance'}
                or annotation['provenance'] != 'explicit_study_measurement'
                or any(annotation[k] is not None and not v4_runner._number(annotation[k]) for k in human_names)
                or annotation['human_interventions'] is not None and type(annotation['human_interventions']) is not int):
            raise JournalError('Invalid explicit study effort measurement')
    strata = defaultdict(list)
    seen = set()
    for row in rows:
        identity = {k:v for k,v in row['identity'].items() if k != 'treatment'}
        stratum = {'observation_source':row['observation_source'], 'identity':identity,
                   'bundle_sha256':row.get('bundle_sha256'), 'receipt_schema':row['schema']}
        key = (row['case'], row['complexity'], v4_runner.fingerprint(stratum))
        slot = (*key, row['trial'], row['mode'])
        if slot in seen: raise JournalError('Duplicate task/stratum/trial/arm')
        seen.add(slot)
        binding = review_key(row)
        summary = execution_events.summarize(row['execution'], reviews.get(binding))
        effort = {name:row.get('observability', {}).get('effort', {}).get(name, v4_runner._metric()) for name in EFFORT_METRICS}
        if binding in human_effort:
            for name in human_names:
                value = human_effort[binding][name]
                effort[name] = {'value':value, 'source':'explicit_study_measurement' if value is not None else 'unavailable',
                                'status':'measured' if value is not None else 'unknown'}
        context = summary['context_counts']
        coverage = summary['coverage']['exact_file_observations'] > 0
        observed = {'tool_calls_observed': {'value':summary['total_observed_calls'], 'source':'public_tool_observer', 'status':'measured'}}
        for name in ('potential_redundant_unchanged_rereads', 'changed_source_reread', 'required_verification',
                     'relevant_context', 'irrelevant_context', 'unknown_relevance_context'):
            known=coverage and (name not in {'required_verification','relevant_context','irrelevant_context'} or bool(reviews.get(binding)))
            observed[name] = {'value':context.get(name,0) if known else None,
                              'source':'public_tool_observer' if known else 'unavailable', 'status':'measured' if known else 'unknown'}
        run = {'receipt_sha256':binding, 'trial':row['trial'], 'arm':row['mode'], 'status':row['status'],
               'accepted':row['accepted'], 'comparison_eligible':row['comparison_eligible'],
               'activation_qualified':row['activation_qualified'], 'validation':row['validation'],
               'policy_coverage_qualified':row['metrics']['unclassified_commands']['value'] == 0 and row['isolation_verified'],
               'failure_categories':row['failure_categories'], 'metrics':row['metrics'], 'effort':effort,
               'observed_metrics':observed, 'execution':summary, 'experiment':row.get('experiment'),
               'activation':row.get('observability',{}).get('activation'),
               'policy':row.get('observability',{}).get('policy')}
        strata[key].append((row, stratum, run))
    lost_strata=defaultdict(list)
    for marker in interrupted:
        matches=[key for key,entries in strata.items() if key[0]==marker['case'] and entries[0][1]['identity']==common(marker)]
        if len(matches)>1:raise JournalError('Ambiguous interruption stratum')
        if matches:key=matches[0]
        else:
            case=benchmark_bundle._case(marker['case'])
            stratum={'observation_source':'unknown','identity':common(marker),'bundle_sha256':None,'receipt_schema':None}
            key=(marker['case'],case['complexity'],v4_runner.fingerprint(stratum))
            strata[key]=[(None,stratum,{'observed_metrics':{name:None for name in ('tool_calls_observed','potential_redundant_unchanged_rereads',
                'changed_source_reread','required_verification','relevant_context','irrelevant_context','unknown_relevance_context')}})]
        lost_strata[key].append(marker)
    tasks = []
    for (case, difficulty, stratum_hash), entries in sorted(strata.items()):
        arms = []
        for arm in ('A','B','C','D'):
            selected = [run for row, _, run in entries if row is not None and row['mode'] == arm]
            lost=[m for m in lost_strata[(case,difficulty,stratum_hash)] if m['mode']==arm]
            for marker in lost:
                selected.append({'receipt_sha256':None,'trial':marker['trial'],'arm':arm,'status':'interrupted',
                    'accepted':False,'comparison_eligible':False,'activation_qualified':False,'policy_coverage_qualified':False,
                    'validation':{'all_passed':None,'performed':None,'required':_expected(case)},
                    'failure_categories':['interrupted_unknown_outcome'],'metrics':{k:v4_runner._metric() for k in v4_runner.METRICS},
                    'effort':{k:v4_runner._metric() for k in EFFORT_METRICS},
                    'observed_metrics':{k:v4_runner._metric() for k in entries[0][2]['observed_metrics']},
                    'experiment':None,'activation':None,'policy':None,'execution':None})
            if not selected: continue
            selected.sort(key=lambda r:(r['experiment']['order_index'] if r['experiment'] else r['trial'], r['trial']))
            accepted = [r for r in selected if r['accepted']]
            metrics = {name:_distribution([r['metrics'][name] for r in selected]) for name in sorted(v4_runner.METRICS)}
            metrics.update({name:_distribution([r['effort'][name] for r in selected]) for name in EFFORT_METRICS})
            metrics.update({name:_distribution([r['observed_metrics'][name] for r in selected]) for name in selected[0]['observed_metrics']})
            first = [r for r in selected if r['experiment'] is not None and r['experiment']['benchmark_rerun'] == 0]
            arms.append({'arm':arm, 'attempts':len(selected), 'accepted':len(accepted),
                'verified_success_rate':len(accepted)/len(selected), 'failed_or_incomplete':len(selected)-len(accepted),
                'status_counts':dict(Counter(r['status'] for r in selected)),
                'failure_categories':dict(Counter(reason for r in selected for reason in r['failure_categories'])),
                'failure_rate':(len(selected)-len(accepted))/len(selected),
                'mandatory_checks_pass_rate':sum(r['validation']['all_passed'] is True and r['validation']['performed'] == r['validation']['required'] for r in selected)/len(selected),
                'mandatory_validation_coverage':{'required':sum(r['validation']['required'] for r in selected),
                                                 'performed':sum(r['validation']['performed'] for r in selected if r['validation']['performed'] is not None),
                                                 'unknown_attempts':sum(r['validation']['performed'] is None for r in selected)},
                'first_scheduled_attempts':len(first),
                'first_scheduled_attempt_success_rate':sum(r['accepted'] for r in first)/len(first) if first else None,
                'first_pass_success_rate':None,
                'first_pass_definition':'First scheduled benchmark attempt is distinct from internal agent retries, which are not inferred.',
                'activation_qualified':sum(r['activation_qualified'] for r in selected),
                'policy_coverage_qualified':sum(r['policy_coverage_qualified'] for r in selected),
                'comparison_eligible':sum(r['comparison_eligible'] for r in selected),
                'metrics':metrics, 'time_to_accepted_ms':_distribution([r['metrics']['wall_ms'] for r in accepted]),
                'estimated_cost':None, 'pricing_evidence':None, 'provider_cache_condition':'unknown',
                'runs':selected})
        converted = []
        for row, _, _ in entries:
            if row is None:continue
            if row['schema'] == 52:
                row = {**{k:v for k,v in row.items() if k not in {'experiment','observability'}}, 'schema':51}
            converted.append(benchmark_bundle.base(row) if row['schema'] == 51 else row)
        paired = report(converted)
        tasks.append({'case':case, 'domain':benchmark_bundle._case(case)['domain'], 'complexity':difficulty,
                      'stratum_sha256':stratum_hash, 'stratum':entries[0][1], 'arms':arms,
                      'paired_comparisons':paired['paired_comparisons'], 'uncertainty':paired['uncertainty'],
                      'qualified_resource_comparisons':paired['quality_first']})
    return {'schema':52, 'track':'task_matched_repeated_correctness_first', 'attempts':len(rows)+len(interrupted),
            'completed_receipts':len(rows),'interrupted_attempts':len(interrupted),'interrupted_markers':interrupted,'tasks':tasks,
            'token_savings_claim':False, 'repeatable_efficacy_established':False,
            'reproduction':'Use the pinned bundle and private runtime archive with benchmark_bundle reproduce; scheduling and native execution require separately approved budgets.',
            'limitations':['Individual runs and task strata precede pooling; controlled and native observations remain separate.',
                'All failures remain in attempt denominators; accepted latency is conditional on independent success.',
                'Public tool/context coverage is partial. Potential rereads are not established waste.',
                'Human effort is unknown unless explicitly measured within this study and bound to the complete receipt.',
                'Provider cache state, internal agent retries and unobserved human activity remain unknown.',
                'Tiny samples support descriptive observations only; uncertainty intervals are absent below existing minimum counts.',
                'Historical V2 mixed outcomes and V5.1 exploratory token reductions do not establish general efficacy.']}


def render_markdown(value):
    """Render the same validated report data; no second aggregation path."""
    lines = ['# TuckBit task-matched results', '', f"Attempts: {value['attempts']}. No generalized efficiency or token-savings claim.", '']
    for task in value['tasks']:
        lines += [f"## {task['case']} · {task['domain']} · {task['complexity']}", '',
                  f"Stratum: `{task['stratum_sha256']}`; source: {task['stratum']['observation_source']}; bundle: `{task['stratum']['bundle_sha256'] or 'unknown'}`.", '',
                  '| Arm | Attempts | Accepted | Success rate | Eligible | Accepted median wall ms |',
                  '| --- | ---: | ---: | ---: | ---: | ---: |']
        for arm in task['arms']:
            median = arm['time_to_accepted_ms']['median']
            lines.append(f"| {arm['arm']} | {arm['attempts']} | {arm['accepted']} | {arm['verified_success_rate']:.3f} | {arm['comparison_eligible']} | {median if median is not None else 'unknown'} |")
        for arm in task['arms']:
            lines += ['', f"### Arm {arm['arm']}: individual runs", '',
                      '| Trial | Status | Activation | Policy | Input tokens | Cached input | Output tokens | Wall ms |',
                      '| --- | --- | --- | --- | ---: | ---: | ---: | ---: |']
            for run in arm['runs']:
                values = [run['metrics'][k]['value'] for k in ('input_tokens','cached_input_tokens','output_tokens','wall_ms')]
                lines.append('| ' + ' | '.join(str(v) if v is not None else 'unknown' for v in [run['trial'],run['status'],run['activation_qualified'],run['policy_coverage_qualified'],*values]) + ' |')
            lines += ['', 'Distributions retain every attempt; missing observations remain unknown.', '',
                      '| Metric | Available / missing | Median | Range |', '| --- | ---: | ---: | --- |']
            for name, dist in arm['metrics'].items():
                lines.append(f"| {name} | {dist['available']} / {dist['missing']} | {dist['median'] if dist['median'] is not None else 'unknown'} | {str(dist['min'])+'–'+str(dist['max']) if dist['available'] else 'unknown'} |")
    lines += ['', '## Limitations', '', *['- '+line for line in value['limitations']], '', value['reproduction'], '']
    return '\n'.join(lines)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--journal', required=True, help='Explicit private V5 journal or sanitized receipt list')
    parser.add_argument('--approved', action='store_true', help='Consent to read this explicit sanitized file only')
    parser.add_argument('--output', required=True)
    parser.add_argument('--reviews', help='Explicit independent per-run/per-call sanitized review attestations')
    parser.add_argument('--per-task', action='store_true', help='Task-first V5/V5.1/V5.2 distributions with immutable strata')
    parser.add_argument('--human-effort', help='Explicit study-only effort annotations keyed by complete receipt SHA-256')
    parser.add_argument('--markdown-output', help='New private Markdown export of --per-task report')
    args=parser.parse_args()
    try:
        if not args.approved: raise JournalError('Explicit journal approval required')
        if (args.human_effort or args.markdown_output) and not args.per_task:
            raise JournalError('Task-first report required for effort or Markdown exports')
        value=load(args.journal)
        if isinstance(value,dict):
            journal_type=V5Journal
            if args.per_task and value.get('runs'):
                import benchmark_bundle
                journal_type={5:V5Journal,51:benchmark_bundle.V51Journal,52:getattr(benchmark_bundle,'V52Journal',None)}.get(value['runs'][0].get('schema'))
                if journal_type is None:raise JournalError('Unsupported journal receipt schema')
            journal=object.__new__(journal_type);journal.document=value;journal._validate()
            rows=value['runs'];markers={k:value[k] for k in ('inflight','interrupted')}
        else: rows,markers=value,None
        reviews=load(args.reviews) if args.reviews else None
        unresolved=(markers['interrupted']+([markers['inflight']] if markers['inflight'] is not None else [])) if markers else None
        result=(per_task_report(rows,reviews,load(args.human_effort) if args.human_effort else None,unresolved)
                if args.per_task else report(rows,reviews));result['journal_markers']=markers
        write_new(args.output,result)
        if args.markdown_output:
            target=Path(args.markdown_output).absolute()
            if any(symlink(p) for p in (target,*target.parents)):raise JournalError('Symlink destination refused')
            data=render_markdown(result).encode()
            if len(data)>MAX_BYTES:raise JournalError('Markdown export too large')
            fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'wb') as output:output.write(data)
        print(json.dumps({'written':True,'attempts':len(rows),'completion_gate_met':result.get('completion_gate_met',False)}))
    except (ValueError,OSError,KeyError,TypeError):
        parser.error('Invalid or unapproved sanitized V5 evidence')


if __name__ == '__main__':
    main()
