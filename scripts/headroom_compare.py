#!/usr/bin/env python3
"""Compare explicitly selected sessions run without and with a context compressor (e.g. Headroom).

Observational only: sessions are not matched tasks, so differences are not proven savings.
Reports per-session means of observed client counters and an optional configured cost scenario.
"""
import argparse
import json
import math
import re
from pathlib import Path

import dashboard_export as exporter

COUNTERS = ('input_tokens', 'cached_input_tokens', 'uncached_input_tokens', 'output_tokens')
RATES = ('uncached_input_per_million', 'cached_input_per_million', 'output_per_million')
MAX_RATE = 1_000_000


def validate_prices(prices):
    """Three finite, bounded, non-negative rates; booleans and extra fields are refused."""
    if (not isinstance(prices, dict) or set(prices) != set(RATES)
            # The range check also refuses NaN (all comparisons false) and +/-inf; it never converts huge ints.
            or any(type(v) not in (int, float) or not 0 <= v <= MAX_RATE for v in prices.values())):
        exporter._fail('invalid_prices')
    return prices


def _arm(documents):
    """Unique sessions by ID; a repeated ID must carry identical observations."""
    seen = {}
    for document in documents:
        for row in document['sessions']:
            metrics = row.get('metrics') or {}
            values = {key: (metrics.get(key) or {}).get('value') for key in COUNTERS}
            writes = sorted(key for key in metrics if re.search(r'cache.*(write|creation)', key, re.I))
            observation = (values, row.get('provider'), row.get('model'), row.get('kind'),
                           [(metrics[key] or {}).get('value') for key in writes])
            if seen.setdefault(row['id'], observation) != observation:
                exporter._fail('conflicting_session')
    complete = {sid: o for sid, o in seen.items() if all(type(v) is int and v >= 0 for v in o[0].values())
                and o[0]['cached_input_tokens'] + o[0]['uncached_input_tokens'] == o[0]['input_tokens']}
    return complete, len(seen) - len(complete)


def _summary(sessions, excluded):
    count = len(sessions)
    totals = {key: sum(o[0][key] for o in sessions.values()) for key in COUNTERS}
    return {'complete_sessions': count, 'incomplete_sessions_excluded': excluded,
            'mean': {key: totals[key] / count for key in COUNTERS} if count else None,
            'cache_fraction': totals['cached_input_tokens'] / totals['input_tokens'] if totals['input_tokens'] else None,
            'mean_configured_cost': None}


def _cost_blocker(arms):
    observations = [o for sessions in arms for o in sessions.values()]
    if not all(arms): return 'arm_without_complete_sessions'
    if len({(o[1], o[2]) for o in observations}) != 1 or None in (observations[0][1], observations[0][2]):
        return 'mixed_or_unknown_provider_model'
    if any(o[3] in ('control', 'demo') for o in observations): return 'synthetic_or_control_session'
    if any(value != 0 for o in observations for value in o[4]): return 'cache_write_billing_unresolved'
    return None


def compare(without, with_, prices=None):
    """Each arm is a list of normalized Observatory documents; prices is an optional configured scenario."""
    if prices is not None: validate_prices(prices)
    base, base_excluded = _arm(without)
    treated, treated_excluded = _arm(with_)
    if set(base) & set(treated): exporter._fail('session_in_both_arms')
    a, b = _summary(base, base_excluded), _summary(treated, treated_excluded)
    blocker = _cost_blocker((base, treated)) if prices else 'prices_not_configured'
    if blocker is None:
        for summary, sessions in ((a, base), (b, treated)):
            total = sum(o[0]['uncached_input_tokens'] * prices['uncached_input_per_million'] + o[0]['cached_input_tokens'] * prices['cached_input_per_million']
                        + o[0]['output_tokens'] * prices['output_per_million'] for o in sessions.values()) / 1_000_000
            if not math.isfinite(total): exporter._fail('invalid_prices')
            summary['mean_configured_cost'] = total / len(sessions)
    flags = []
    if not a['complete_sessions'] or not b['complete_sessions']:
        flags.append('arm_without_complete_sessions')
    else:
        delta = lambda key: b['mean'][key] - a['mean'][key]
        if delta('input_tokens') < 0 and delta('uncached_input_tokens') >= 0:
            flags.append('fewer_input_tokens_but_not_fewer_uncached')
        if a['cache_fraction'] is not None and b['cache_fraction'] is not None and b['cache_fraction'] < a['cache_fraction']:
            flags.append('cache_fraction_decreased')
        if blocker is None and delta('input_tokens') < 0 and b['mean_configured_cost'] >= a['mean_configured_cost']:
            flags.append('fewer_input_tokens_but_configured_cost_not_lower')
    return {'schema': 'tuckbit.compressor_comparison/1', 'without': a, 'with': b, 'flags': flags,
            'cost_basis': 'configured_scenario' if blocker is None else 'unavailable', 'cost_unavailable_reason': blocker,
            'sample_unit': 'unique complete session observations (total, cached and uncached input and output observed, cached + uncached = input)',
            'limitations': ['Sessions are selected by the user and are not matched tasks; difficulty may differ between arms.',
                            'Differences are observations, not proven or causal savings.',
                            'Configured cost uses user-supplied rates for a single provider/model, not provider billing, tiers, subscriptions or cache writes.',
                            'Task success is not assessed here; fewer tokens on a failed task is not a saving.']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--without', nargs='+', required=True, help='explicitly selected Codex JSONL or Observatory JSON files')
    parser.add_argument('--with', dest='with_', nargs='+', required=True)
    parser.add_argument('--prices', help='JSON object: ' + ', '.join(RATES))
    args = parser.parse_args(argv)

    def load(paths):
        documents = []
        for path in paths:
            try:
                text = Path(path).read_text(encoding='utf-8')
            except UnicodeDecodeError:
                exporter._fail('unsupported_file')
            except OSError:
                exporter._fail('unreadable_file')
            documents.append(exporter.import_text(text))
        return documents
    try:
        try:
            prices = json.loads(args.prices) if args.prices else None
        except ValueError:
            exporter._fail('invalid_prices')
        result = compare(load(args.without), load(args.with_), prices)
    except exporter.ImportError as error:
        print(json.dumps({'error': str(error)}))
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
