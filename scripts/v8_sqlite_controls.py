#!/usr/bin/env python3
"""Versioned D08 controls over the frozen bounded SQLite grader; no model runner."""
import copy
import hashlib
import json
from pathlib import Path
import platform
import sqlite3

import v4_corpus as corpus

ROOT = Path(__file__).resolve().parents[1]
VERSION = 'D08-medium-v8-controls/1'


def specs():
    _, fixture = corpus._case('D08-medium')
    base = copy.deepcopy(fixture['grader'])
    base['assertions'].append(["SELECT name FROM sqlite_master WHERE type='trigger'", []])
    base['rollback_assertions'].extend([
        ['PRAGMA table_info(accounts)', [[0, 'id', 'INTEGER', 0, None, 1], [1, 'balance', 'INTEGER', 1, None, 0]]],
        ["SELECT name FROM sqlite_master WHERE type='index'", []],
    ])
    controls = []
    # Nonsequential ids, zero, negative and large balances catch id-based/threshold shortcuts.
    for balances in ([], [(41, -1), (7, 0), (23, 1), (99, -500), (100, 500)],
                     [(8, -9007199254740991), (3, 9007199254740991), (2, 0), (22, -2)]):
        spec = copy.deepcopy(base)
        setup = 'CREATE TABLE accounts(id INTEGER PRIMARY KEY, balance INTEGER NOT NULL);'
        if balances:
            setup += 'INSERT INTO accounts VALUES' + ','.join(f'({key},{balance})' for key, balance in balances) + ';'
        spec['setup'] = setup
        spec['assertions'][0][1] = [[key, balance, int(balance >= 0)] for key, balance in sorted(balances)]
        spec['rollback_assertions'][0][1] = [[key, balance] for key, balance in sorted(balances)]
        controls.append(spec)
    return controls


def checked(source, spec):
    try:
        checks = corpus._sql({'up.sql': source}, spec)
        return {'accepted': bool(checks) and all(checks), 'assertions': len(checks)}
    except (sqlite3.Error, ValueError):
        return {'accepted': False, 'assertions': 0}


def validate():
    if not hasattr(sqlite3.Connection, 'setlimit'):
        raise ValueError('V8 SQLite controls unavailable: Python/SQLite must provide Connection.setlimit (Python 3.11+)')
    case, fixture = corpus._case('D08-medium')
    reference = fixture['reference']['up.sql']
    identity = corpus.digest([case, fixture])
    controls = specs()
    sources = {
        'seed': '-- no migration',
        'original_negative': fixture['negative']['up.sql'],
        'zero_deactivated': reference.replace('balance<0', 'balance<=0'),
        'id_shortcut': reference.replace('balance<0', 'id=3'),
        'nullable_column': reference.replace('INTEGER NOT NULL DEFAULT', 'INTEGER DEFAULT'),
        'wrong_default': reference.replace('DEFAULT 1', 'DEFAULT 0'),
        'wrong_index': reference.replace('accounts(active)', 'accounts(balance)'),
        'unique_index': reference.replace('CREATE INDEX', 'CREATE UNIQUE INDEX'),
        'lost_balances': reference + 'UPDATE accounts SET balance=0;',
        'commit_escape': reference + 'COMMIT;',
        'savepoint_escape': 'SAVEPOINT escape;' + reference,
        'attachment': "ATTACH DATABASE ':memory:' AS outside;" + reference,
        'extension': "SELECT load_extension('unavailable');" + reference,
        'pragma': 'PRAGMA writable_schema=ON;' + reference,
        'recursive_work': 'WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM n) SELECT SUM(x) FROM n;' + reference,
        'hidden_trigger': reference + 'CREATE TRIGGER surprise AFTER INSERT ON accounts BEGIN DELETE FROM accounts; END;',
        'syntax_failure': reference + 'INVALID SQL;',
    }
    reference_results = [checked(reference, spec) for spec in controls]
    negatives = [{'name': name, 'rejected': not all(checked(source, spec)['accepted'] for spec in controls)} for name, source in sources.items()]
    # A failed transaction must not poison later fresh, in-memory grading; no idempotency claim.
    recovery = checked(reference, controls[1])['accepted']
    if corpus.digest(list(corpus._case('D08-medium'))) != identity:
        raise ValueError('Frozen corpus changed during control validation')
    result = {
        'schema': 'tuckbit.v8-sqlite-controls/1', 'version': VERSION, 'native_launches': 0,
        'case': case['id'], 'source_revision': case['source_revision'], 'grader_sha256': case['grader_sha256'],
        'implementation_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'sqlite_grader_implementation_sha256': hashlib.sha256((ROOT/'scripts/v4_corpus.py').read_bytes()).hexdigest(),
        'control_spec_sha256': corpus.digest(controls), 'environment': f'Python {platform.python_version()} / SQLite {sqlite3.sqlite_version}',
        'reference_variants': len(reference_results), 'reference_passed': sum(row['accepted'] for row in reference_results),
        'reference_assertions': sum(row['assertions'] for row in reference_results),
        'negative_controls': negatives, 'negative_rejected': sum(row['rejected'] for row in negatives),
        'fresh_database_recovery': recovery, 'native_ready': False,
        'limits': 'Existing in-memory SQLite, authorizer, VM progress, SQL/result/column/attachment bounds; no arbitrary host-language code.',
        'scope': 'Versioned synthetic control companion; original corpus and historical receipts unchanged. Not a native measurement or general migration/idempotency guarantee.',
    }
    if result['reference_passed'] != len(controls) or result['negative_rejected'] != len(sources) or not recovery:
        raise ValueError('V8 SQLite controls failed')
    return result


def public_metadata(result):
    pilot = json.loads((ROOT/'evals/v6/pilot.json').read_text())
    rows = []
    for row in pilot['cases']:
        if row['id'].split('-')[0] not in {'D01','D04','D07','D08','D09','D13','D19'}:
            continue
        controls = 'Existing bounded SQLite reference / negative controls' if row['runtime_ready'] else 'Structural/pure controls only; executable companion where documented'
        if row['id'] == result['case']:
            controls = f"V8: {result['reference_passed']} seeded variants / {result['reference_assertions']} reference assertions / {result['negative_rejected']} negative controls; rollback and fresh-database recovery"
        rows.append({'id': row['id'], 'structural': 'Existing frozen corpus controls', 'controls': controls, 'gap': row['acceptance_gap']})
    return {key: result[key] for key in ('version','implementation_sha256','source_revision','grader_sha256','environment','scope')} | {'candidates': rows}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write-public', action='store_true', help='Write only sanitized readiness metadata to the existing web assets')
    args = parser.parse_args()
    result = validate()
    if args.write_public:
        target = ROOT/'web/data/readiness.json'
        target.parent.mkdir(exist_ok=True)
        target.write_text(json.dumps(public_metadata(result), indent=2) + '\n')
    print(json.dumps(result, indent=2))
