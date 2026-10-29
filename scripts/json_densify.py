#!/usr/bin/env python3
"""Lossless densification of uniform JSON arrays of objects into a schema header plus CSV rows.

Format idea adapted from Headroom's agent-mode compaction (Apache-2.0,
github.com/headroomlabs-ai/headroom); this is an independent stdlib implementation.
A result is returned only when decoding it reproduces the parsed JSON value exactly
(same structure, key order and primitive types); anything else is left unchanged.
This is value equality, not byte equality: whitespace and number spelling such as
1.50 or 1e2 are not preserved. Smaller text is not a proven saving: measure it.
"""
import argparse
import csv
import io
import json
import math
import re
import sys

KEY = re.compile(r'[A-Za-z0-9_.-]{1,64}')
TYPES = {bool: 'bool', int: 'int', float: 'float', str: 'string'}
MAX_BYTES = 4 * 1024 * 1024
PARSE = {'bool': lambda s: {'true': True, 'false': False}[s], 'int': int, 'float': float, 'string': str}


def _schema(rows):
    keys = list(rows[0])
    if not all(isinstance(k, str) and KEY.fullmatch(k) for k in keys):
        return None
    columns = []
    for key in keys:
        kinds = {type(row[key]) for row in rows}
        nullable = type(None) in kinds
        kinds.discard(type(None))
        if len(kinds) != 1 or next(iter(kinds)) not in TYPES:
            return None
        if float in kinds and not all(row[key] is None or math.isfinite(row[key]) for row in rows):
            return None
        columns.append((key, TYPES[next(iter(kinds))], nullable))
    return columns


def _cell(value):
    if value is None: return ''
    if isinstance(value, bool): return 'true' if value else 'false'
    if isinstance(value, (int, float)): return json.dumps(value)
    return value


def encode(value):
    """Dense text for a uniform list of flat objects, or None when not applicable."""
    if not isinstance(value, list) or len(value) < 2 or not all(isinstance(r, dict) and r for r in value):
        return None
    if any(list(r) != list(value[0]) for r in value):
        return None
    columns = _schema(value)
    if columns is None:
        return None
    out = io.StringIO()
    out.write('[%d]{%s}\n' % (len(value), ','.join(k + ':' + t + ('?' if n else '') for k, t, n in columns)))
    writer = csv.writer(out, lineterminator='\n')
    for row in value:
        writer.writerow([_cell(row[k]) for k, _, _ in columns])
    return out.getvalue()


def expand(text):
    header, _, body = text.partition('\n')
    match = re.fullmatch(r'\[(\d+)\]\{(.+)\}', header)
    if not match:
        raise ValueError('not_densified')
    columns = []
    for spec in match[2].split(','):
        key, _, kind = spec.partition(':')
        nullable = kind.endswith('?')
        kind = kind.rstrip('?')
        if not KEY.fullmatch(key) or kind not in PARSE:
            raise ValueError('invalid_schema')
        columns.append((key, PARSE[kind], nullable))
    if len({key for key, _, _ in columns}) != len(columns):
        raise ValueError('invalid_schema')  # a dict row would silently keep only the last duplicate column
    rows = []
    for cells in csv.reader(io.StringIO(body)):
        if len(cells) != len(columns):
            raise ValueError('invalid_row')
        rows.append({k: None if n and c == '' else parse(c) for (k, parse, n), c in zip(columns, cells)})
    if len(rows) != int(match[1]):
        raise ValueError('row_count_mismatch')
    return rows


def _pairs(pairs):
    if len({key for key, _ in pairs}) != len(pairs):
        raise ValueError('duplicate_key')  # json.loads would silently keep only the last value
    return dict(pairs)


def _no_constant(name):
    raise ValueError('non_finite_number')


def densify(text):
    """Return (text, applied). Falls back to the original unless the round trip is exact and shorter."""
    try:
        if len(text.encode('utf-8')) > MAX_BYTES:
            return text, False
        value = json.loads(text, object_pairs_hook=_pairs, parse_constant=_no_constant)
        dense = encode(value)
        if dense is None or len(dense) >= len(text):
            return text, False
        dense.encode('utf-8')  # lone surrogates cannot be written out
        # Ordered serialization distinguishes True/1, 1/1.0 and key order, unlike ==.
        if json.dumps(expand(dense)) != json.dumps(value):
            return text, False
        return dense, True
    except (ValueError, KeyError, RecursionError):
        return text, False


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('file', help='explicitly selected JSON file')
    args = parser.parse_args(argv)
    try:
        with open(args.file, 'rb') as handle:
            data = handle.read(MAX_BYTES + 1)  # bounded: never load an oversized file whole
        if len(data) > MAX_BYTES:
            print(json.dumps({'error': 'size_limit'}), file=sys.stderr)
            return 2
        text = data.decode('utf-8')
    except (OSError, UnicodeDecodeError):
        print(json.dumps({'error': 'unreadable_file'}), file=sys.stderr)
        return 2
    result, applied = densify(text)
    sys.stdout.write(result)
    # Characters and UTF-8 bytes only; neither is a token count.
    print(json.dumps({'applied': applied, 'original_chars': len(text), 'densified_chars': len(result),
                      'original_utf8_bytes': len(text.encode('utf-8')), 'densified_utf8_bytes': len(result.encode('utf-8'))}), file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
