#!/usr/bin/env python3
"""V4 bounded, model-free fixtures. Submitted programs are interpreted, never executed."""
import argparse
import ast
import copy
import hashlib
from html.parser import HTMLParser
import json
import os
import platform
from pathlib import Path
import re
import sqlite3
import tempfile

from benchmark_runner import GradingError, safe_call

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'evals' / 'v4'
MAX_FILE = 256 * 1024
MAX_TOTAL = 2 * 1024 * 1024


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _load():
    manifest = _json_read((DATA / 'manifest.json').read_text())
    fixtures = _json_read((DATA / 'fixtures.json').read_text())
    if not isinstance(manifest, list) or not isinstance(fixtures, dict):
        raise ValueError('invalid corpus root schema')
    ids = [c['id'] for c in manifest]
    if len(ids) != 60 or len(set(ids)) != 60 or set(ids) != set(fixtures):
        raise ValueError('corpus must contain 60 unique matching cases')
    if {(c['domain'], c['complexity']) for c in manifest} != {(f'D{i:02}', size) for i in range(1, 21) for size in ('small', 'medium', 'complex')}:
        raise ValueError('incomplete domain/complexity coverage')
    for case in manifest:
        fixture = fixtures[case['id']]
        if case['grader_kind'] not in {'behavior', 'html', 'sql', 'json', 'vectors', 'composite'}:
            raise ValueError('unknown grader')
        for inventory in ('files', 'reference', 'negative'):
            values = fixture[inventory]
            if not isinstance(values, dict) or not values or len(values) > 100:
                raise ValueError('invalid fixture inventory')
            for path, source in values.items():
                if not isinstance(path, str) or not path or Path(path).is_absolute() or '..' in Path(path).parts or str(Path(path)) != path or '\\' in path:
                    raise ValueError('unsafe fixture path')
                if not isinstance(source, str) or len(source.encode()) > MAX_FILE:
                    raise ValueError('invalid fixture source')
            if sum(len(source.encode()) for source in values.values()) > MAX_TOTAL:
                raise ValueError('oversized fixture')
        if set(fixture['reference']) - set(case['editable']) or set(fixture['negative']) - set(case['editable']):
            raise ValueError('outcome modifies unauthorized file')
        hashes = {p: hashlib.sha256(s.encode()).hexdigest() for p, s in fixture['files'].items()}
        if hashes != case['source_hashes'] or digest(hashes) != case['source_revision']:
            raise ValueError('source identity changed')
        if digest(fixture['dependencies']) != case['dependency_fingerprint']:
            raise ValueError('dependency identity changed')
        if digest(fixture['reference']) != case['reference_sha']:
            raise ValueError('reference identity changed')
        if digest(fixture['grader']) != case['grader_sha256'] or digest(fixture['negative']) != case['negative_sha256']:
            raise ValueError('grader or negative identity changed')
        if digest(fixture) != case['fixture_revision']:
            raise ValueError('fixture identity changed')
        if any(Path(p).is_absolute() or '..' in Path(p).parts for p in hashes):
            raise ValueError('unsafe fixture path')
        if set(case['editable']) - set(hashes):
            raise ValueError('unknown editable path')
    return manifest, fixtures


def cases():
    return copy.deepcopy(_load()[0])


def _case(case_id):
    manifest, fixtures = _load()
    for case in manifest:
        if case['id'] == case_id:
            return case, fixtures[case_id]
    raise ValueError('unknown task ID')


def materialize(case_id, destination):
    """Write only the seeded source, refusing existing or symlinked destinations."""
    case, fixture = _case(case_id)
    folder = Path(destination)
    if folder.is_symlink() or any(p.is_symlink() and str(p) not in {'/tmp', '/var'} for p in folder.parents):
        raise ValueError('symlinked destination')
    if folder.exists() and (not folder.is_dir() or any(folder.iterdir())):
        raise ValueError('destination must be empty')
    folder.mkdir(parents=True, exist_ok=True)
    for name, source in fixture['files'].items():
        path = folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding='utf-8')
    return copy.deepcopy(case)


def _snapshot(folder, case, fixture):
    if folder.is_symlink() or not folder.is_dir():
        raise ValueError('invalid workspace')
    files, violations, total, count = {}, [], 0, 0
    for parent, directories, names in os.walk(folder, followlinks=False):
        for name in list(directories):
            path = Path(parent) / name
            relative = path.relative_to(folder).as_posix()
            if path.is_symlink():
                violations.append('symlink')
                directories.remove(name)
            elif relative in {'.git', '.agents'}:
                directories.remove(name)
        for name in names:
            path = Path(parent) / name
            relative = path.relative_to(folder).as_posix()
            if relative == 'ADAPTER_PLAN.json':
                if path.is_symlink():
                    violations.append('symlink')
                continue
            count += 1
            if count > 100:
                raise ValueError('file count limit')
            if path.is_symlink() or not path.is_file():
                violations.append('nonregular source')
                continue
            if relative not in fixture['files']:
                violations.append('unauthorized file')
                continue
            size = path.stat().st_size
            total += size
            if size > MAX_FILE or total > MAX_TOTAL:
                raise ValueError('source size limit')
            files[relative] = path.read_text(encoding='utf-8')
    for name, source in fixture['files'].items():
        if name not in files:
            violations.append('deleted source')
        elif name not in case['editable'] and source != files[name]:
            violations.append('unauthorized change')
    return files, violations


def _foreign_source(source, language):
    """Interpret only total pure numeric/boolean functions in a documented small grammar."""
    if language == 'PHP':
        if not source.lstrip().startswith('<?php'):
            raise ValueError('PHP opening tag required')
        source = re.sub(r'^\s*<\?php\s*', '', source)
        if re.search(r'(?<![=!])==(?!=)|(?<![!])!=(?!=)', source):
            raise ValueError('PHP identity comparisons must be strict')
        pattern = r'function\s+(\w+)\(([^)]*)\)\s*\{\s*return\s+([^;{}]+);\s*\}'
    elif language == 'Swift':
        pattern = r'func\s+(\w+)\(([^)]*)\)\s*->\s*(?:Int|Bool)\s*\{\s*return\s+([^;{}]+);?\s*\}'
    elif language in {'JavaScript', 'TypeScript'}:
        pattern = r'(?:export\s+)?function\s+(\w+)\(([^)]*)\)\s*(?::\s*(?:number|boolean))?\s*\{\s*return\s+([^;{}]+);\s*\}'
    else:
        raise ValueError('unsupported language')
    output, end = [], 0
    for match in re.finditer(pattern, source):
        if source[end:match.start()].strip():
            raise ValueError('unsupported syntax')
        name, raw_parameters, expression = match.groups()
        parameters = []
        for parameter in raw_parameters.split(',') if raw_parameters.strip() else []:
            parameter = parameter.strip().replace('$', '')
            parameter = re.sub(r'^_\s+', '', parameter)
            parameter = re.sub(r':\s*(?:Int|Bool|number|boolean)$', '', parameter)
            if not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', parameter):
                raise ValueError('unsupported parameter')
            parameters.append(parameter)
        if re.search(r'\b(?:if|else|and|or|not|True|False|None|lambda|is|in|def)\b', expression):
            raise ValueError('foreign-language-incompatible syntax')
        if language != 'PHP' and '$' in expression:
            raise ValueError('unsupported foreign identifier')
        expression = expression.replace('$', '').replace('===', '==').replace('!==', '!=')
        expression = expression.replace('&&', ' and ').replace('||', ' or ')
        expression = re.sub(r'!(?!=)\s*([A-Za-z_][A-Za-z_0-9]*)', r'(not \1)', expression)
        if re.search(r'!(?!=)', expression):
            raise ValueError('unsupported compound logical negation')
        expression = re.sub(r'\btrue\b', 'True', expression)
        expression = re.sub(r'\bfalse\b', 'False', expression)
        if '?' in expression or '/' in expression or '[' in expression:
            raise ValueError('unsupported expression')
        output.append('def ' + name + '(' + ','.join(parameters) + '):\n    return ' + expression.strip() + '\n')
        end = match.end()
    if source[end:].strip() or not output:
        raise ValueError('unsupported top-level syntax')
    return '\n'.join(output)


def _declarations(source, language):
    pattern = (r'func\s+\w+\([^)]*\)\s*->\s*(?:Int|Bool)' if language == 'Swift' else
               r'(?:export\s+)?function\s+\w+\([^)]*\)\s*(?::\s*(?:number|boolean))?')
    return [re.sub(r'\s+', '', match.group()) for match in re.finditer(pattern, source)]


def _typed_foreign(files, language):
    signatures = {}
    for source in files.values():
        if language == 'JavaScript':
            for match in re.finditer(r'function\s+(\w+)\(([^)]*)\)', source):
                name, parameters = match.groups()
                signatures[name] = ([(p.strip(), 'number') for p in parameters.split(',') if p.strip()], 'number')
            continue
        if language == 'Swift':
            matches = re.finditer(r'func\s+(\w+)\(([^)]*)\)\s*->\s*(Int|Bool)', source)
            types = {'Int': 'number', 'Bool': 'boolean'}
        else:
            matches = re.finditer(r'function\s+(\w+)\(([^)]*)\)\s*:\s*(number|boolean)', source)
            types = {'number': 'number', 'boolean': 'boolean'}
        for match in matches:
            name, parameters, returns = match.groups()
            pairs = [p.strip().split(':') for p in parameters.split(',')] if parameters.strip() else []
            signatures[name] = ([(p[0].strip().removeprefix('_ ').strip(), types[p[1].strip()]) for p in pairs], types[returns])
    def infer(node, names):
        if isinstance(node, ast.Name) and node.id in names:
            return names[node.id]
        if isinstance(node, ast.Constant) and type(node.value) in {int, bool}:
            return 'boolean' if type(node.value) is bool else 'number'
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult)):
            if infer(node.left, names) == infer(node.right, names) == 'number':
                return 'number'
        if isinstance(node, ast.UnaryOp):
            expected = 'boolean' if isinstance(node.op, ast.Not) else 'number'
            if isinstance(node.op, (ast.Not, ast.UAdd, ast.USub)) and infer(node.operand, names) == expected:
                return expected
        if isinstance(node, ast.BoolOp) and all(infer(n, names) == 'boolean' for n in node.values):
            return 'boolean'
        if isinstance(node, ast.Compare) and len(node.ops) == 1:
            left, right = infer(node.left, names), infer(node.comparators[0], names)
            if left == right and (isinstance(node.ops[0], (ast.Eq, ast.NotEq)) or left == 'number'):
                return 'boolean'
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in signatures:
            arguments, returns = signatures[node.func.id]
            if len(node.args) == len(arguments) and all(infer(arg,names) == typ for arg, (_,typ) in zip(node.args, arguments)):
                return returns
        raise ValueError('foreign expression type mismatch')
    for source in files.values():
        for node in ast.parse(_foreign_source(source, language)).body:
            if node.name not in signatures or len(node.body) != 1 or not isinstance(node.body[0], ast.Return):
                raise ValueError('unsupported foreign declaration')
            parameters, returns = signatures[node.name]
            if infer(node.body[0].value, dict(parameters)) != returns:
                raise ValueError('foreign return type mismatch')


def _php_call(source, function, arguments, depth=0, call_trace=None, module='policy', budget=None):
    budget = {'calls': 1000} if budget is None else budget
    budget['calls'] -= 1
    if budget['calls'] < 0 or depth > 12:
        raise ValueError('PHP call-depth bound')
    tree = ast.parse(source)
    if sum(1 for _ in ast.walk(tree)) > 500:
        raise ValueError('PHP syntax resource bound')
    definitions = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    if len(definitions) != len(tree.body) or function not in definitions:
        raise ValueError('unsupported PHP definition')
    definition = definitions[function]
    if len(definition.args.args) != len(arguments) or len(definition.body) != 1 or not isinstance(definition.body[0], ast.Return):
        raise ValueError('unsupported PHP interface')
    names = dict(zip([a.arg for a in definition.args.args], arguments))
    def truth(value):
        return False if value in ('', '0') else bool(value)
    def expression(node):
        if isinstance(node, ast.Name) and node.id in names:
            return names[node.id]
        if isinstance(node, ast.Constant) and type(node.value) in {bool, int}:
            return node.value
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return not truth(expression(node.operand))
        if isinstance(node, ast.BoolOp):
            values = [truth(expression(n)) for n in node.values]
            return all(values) if isinstance(node.op, ast.And) else any(values)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in definitions and not node.keywords:
            if call_trace is not None:
                call_trace.add((module, function, module, node.func.id))
            return _php_call(source, node.func.id, [expression(arg) for arg in node.args], depth+1, call_trace, module, budget)
        if isinstance(node, ast.Compare) and len(node.ops) == 1:
            a, b = expression(node.left), expression(node.comparators[0])
            if isinstance(node.ops[0], ast.Eq):
                return type(a) is type(b) and a == b
            if isinstance(node.ops[0], ast.NotEq):
                return type(a) is not type(b) or a != b
        raise ValueError('unsupported PHP expression')
    return expression(definition.body[0].value)


def _behavior(files, spec):
    language = spec.get('language', 'Python')
    interpreted = files if language == 'Python' else {
        Path(name).stem + '.py': _foreign_source(content, language)
        for name, content in files.items() if name.endswith(spec['extension'])}
    if language in {'Swift', 'TypeScript', 'JavaScript'}:
        _typed_foreign({name: source for name, source in files.items() if name.endswith(spec['extension'])}, language)
    if language == 'Swift' or language == 'TypeScript' and len(interpreted) > 1:
        combined = '\n'.join(interpreted.values())
        interpreted = {name: combined for name in interpreted}
    for name, source in interpreted.items():
        tree = ast.parse(source)
        for function, parameters in spec.get('interfaces', {}).get(name, {}).items():
            definition = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == function), None)
            if definition is None or [a.arg for a in definition.args.args] != parameters:
                raise ValueError('public interface changed')
        known = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)} | {'min', 'max', 'abs'}
        known |= {a.asname or a.name for n in tree.body if isinstance(n, ast.ImportFrom) for a in n.names}
        for node in ast.walk(tree):
            if language != 'Python' and isinstance(node, ast.Mod):
                raise ValueError('unsupported native remainder semantics')
            if language != 'Python' and isinstance(node, ast.Compare) and len(node.ops) != 1:
                raise ValueError('unsupported foreign chained comparison')
            if isinstance(node, (ast.Attribute, ast.Lambda, ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp,
                                 ast.While, ast.For, ast.AsyncFunctionDef, ast.ClassDef, ast.Try, ast.With, ast.Raise,
                                 ast.Delete, ast.Global, ast.Nonlocal, ast.Await, ast.Yield, ast.Subscript)):
                raise ValueError('unsupported source syntax')
            if isinstance(node, ast.Call) and (not isinstance(node.func, ast.Name) or node.func.id not in known):
                raise ValueError('unsupported source call')
    for filename, declarations in spec.get('declarations', {}).items():
        if _declarations(files[filename], language) != declarations:
            raise ValueError('foreign declaration changed')
    checks, call_trace = [], set()
    for module, function, arguments, expected in spec['checks']:
        actual = (_php_call(interpreted[module + '.py'], function, arguments, call_trace=call_trace, module=module) if language == 'PHP'
                  else safe_call(interpreted, module, function, arguments, call_trace=call_trace))
        checks.append(type(actual) is type(expected) and actual == expected)
    for filename, target in spec.get('required_calls', []):
        checks.append(any(len(edge) == 4 and edge[0] == Path(filename).stem and edge[3] == target
                          for edge in call_trace))
    return checks


class _HTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.nodes = []
        self.text_bytes = 0
        self.stack = []
        self.errors = []

    def handle_starttag(self, tag, attributes):
        if len(self.nodes) >= 500 or len(self.stack) >= 32:
            raise ValueError('HTML structural resource limit')
        attrs = dict(attributes)
        if len(attrs) != len(attributes) or any(k.lower().startswith('on') for k in attrs):
            self.errors.append('duplicate or inline event attribute')
        node = {'tag': tag, 'attrs': attrs, 'parents': list(self.stack), 'text': ''}
        self.nodes.append(node)
        if tag not in {'input', 'meta', 'link', 'br', 'hr', 'img'}:
            self.stack.append(len(self.nodes)-1)

    def handle_endtag(self, tag):
        if not self.stack or self.nodes[self.stack[-1]]['tag'] != tag:
            self.errors.append('unbalanced markup')
        else:
            self.stack.pop()

    def handle_data(self, data):
        self.text_bytes += len(data) * len(self.stack)
        if self.text_bytes > MAX_TOTAL:
            raise ValueError('HTML text resource limit')
        for index in self.stack:
            self.nodes[index]['text'] += data


def _html(files, spec):
    parser = _HTML()
    parser.feed(files['index.html'])
    nodes = parser.nodes
    ids = [n['attrs']['id'] for n in nodes if 'id' in n['attrs']]
    checks = [not parser.errors, not parser.stack, len(ids) == len(set(ids)),
              all(n['tag'] in {'main','h1','h2','h3','h4','h5','h6','form','label','input','p','button',
                              'div','span','section','header','footer','nav','article','aside','fieldset','legend','output'}
                  and 'style' not in n['attrs'] for n in nodes)]
    for rule in spec['rules']:
        matches = [n for n in nodes if n['tag'] == rule['tag'] and all(
            (str(n['attrs'].get(k, '')).translate(str.maketrans('ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')) == v.lower()
             if n['tag'] == 'form' and k == 'method' else n['attrs'].get(k) == v)
            for k, v in rule.get('attrs', {}).items())]
        if 'text' in rule:
            matches = [n for n in matches if n['text'].strip() == rule['text']]
        checks.append(len(matches) == rule.get('count', 1))
    for field in spec.get('labels', []):
        checks.append(any(n['tag'] == 'label' and n['attrs'].get('for') == field and n['text'].strip() for n in nodes))
        checks.append(any(n['tag'] == 'input' and n['attrs'].get('id') == field for n in nodes))
    forms = [i for i, node in enumerate(nodes) if node['tag'] == 'form']
    mains = [i for i, node in enumerate(nodes) if node['tag'] == 'main']
    checks.append(len(forms) == 1 and len(mains) == 1 and mains[0] in nodes[forms[0]]['parents'])
    checks.append(all(any(index in node['parents'] for index in forms)
                      and not {'disabled','hidden','form','formaction','formmethod','formtarget','formnovalidate','formenctype'}.intersection(node['attrs'])
                      for node in nodes if node['tag'] in {'input', 'button', 'label'}))
    for node in nodes:
        if node['tag'] in {'main','h1','form','input','button','label','p'}:
            relevant = [node] + [nodes[index] for index in node['parents']]
            checks.append(all('hidden' not in n['attrs'] and 'inert' not in n['attrs'] and 'disabled' not in n['attrs'] and
                              str(n['attrs'].get('aria-hidden', '')).lower() != 'true' for n in relevant))
    if spec.get('local_links'):
        checks.append(all('formaction' not in n['attrs'] and
                          ('action' not in n['attrs'] or n['attrs']['action'] == '/reserve') for n in nodes))
    return checks


def _sql(files, spec):
    if 'variants' in spec:
        base = {k: v for k, v in spec.items() if k != 'variants'}
        return _sql(files, base) + [ok for variant in spec['variants']
                                   for ok in _sql(files, {**base, **variant})]
    connection = sqlite3.connect(':memory:')
    try:
        if not hasattr(connection, 'setlimit'):
            raise ValueError('SQLite resource limits require Python 3.11+')
        connection.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 4096)
        connection.setlimit(sqlite3.SQLITE_LIMIT_SQL_LENGTH, MAX_FILE)
        connection.setlimit(sqlite3.SQLITE_LIMIT_COLUMN, 100)
        connection.setlimit(sqlite3.SQLITE_LIMIT_COMPOUND_SELECT, 50)
        connection.setlimit(sqlite3.SQLITE_LIMIT_ATTACHED, 0)
        connection.executescript(spec['setup'])
        steps = [0]
        def progress():
            steps[0] += 1
            return int(steps[0] > 1000)
        connection.set_progress_handler(progress, 100)
        forbidden = {sqlite3.SQLITE_ATTACH, sqlite3.SQLITE_DETACH, sqlite3.SQLITE_PRAGMA, sqlite3.SQLITE_RECURSIVE,
                     sqlite3.SQLITE_CREATE_VTABLE, sqlite3.SQLITE_DROP_VTABLE}
        if spec['kind'] == 'query':
            forbidden.update({sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE,
                              sqlite3.SQLITE_CREATE_TABLE, sqlite3.SQLITE_DROP_TABLE,
                              sqlite3.SQLITE_ALTER_TABLE, sqlite3.SQLITE_CREATE_INDEX, sqlite3.SQLITE_DROP_INDEX})
        def rows(query):
            result, size = [], 0
            cursor = connection.execute(query)
            while True:
                row = cursor.fetchone()
                if row is None:
                    return result
                size += sum(len(str(value).encode()) for value in row)
                if len(result) >= 1000 or size > 64 * 1024:
                    raise ValueError('SQL result resource bound')
                result.append(row)
        def authorizer(action, a, b, database, trigger):
            if spec['kind'] == 'query' and action == sqlite3.SQLITE_FUNCTION and str(b).lower() in {'printf', 'substr', 'length'}:
                return sqlite3.SQLITE_DENY
            if action in forbidden or (action == sqlite3.SQLITE_FUNCTION and str(b).lower() not in {
                    'sum', 'count', 'coalesce', 'avg', 'min', 'max', 'round', 'lower', 'upper',
                    'dense_rank', 'sqlite_rename_table', 'sqlite_rename_column', 'sqlite_rename_test',
                    'sqlite_rename_quotefix', 'sqlite_drop_column', 'printf', 'substr', 'length'}):
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK
        connection.set_authorizer(authorizer)
        if spec['kind'] == 'query':
            return [rows(files['query.sql']) == [tuple(r) for r in spec['expected']]]
        source = files['up.sql']
        if re.search(r'\b(?:BEGIN|COMMIT|ROLLBACK|SAVEPOINT|RELEASE)\b', source, re.I):
            raise ValueError('transaction control owned by grader')
        connection.executescript('BEGIN;\n' + source)
        connection.set_authorizer(None)
        checks = [rows(query) == [tuple(r) for r in expected]
                  for query, expected in spec['assertions']]
        connection.rollback()
        checks.extend(rows(query) == [tuple(r) for r in expected]
                      for query, expected in spec['rollback_assertions'])
        return checks
    finally:
        connection.close()


def _equal(a, b):
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return set(a) == set(b) and all(_equal(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(_equal(x, y) for x, y in zip(a, b))
    return a == b


def _json_read(source):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError('duplicate JSON key')
            value[key] = item
        return value
    def constant(value):
        raise ValueError('nonfinite JSON number')
    return json.loads(source, object_pairs_hook=unique, parse_constant=constant)


def _json_answer(files, spec):
    answer = _json_read(files['answer.json'])
    if not isinstance(answer, dict):
        return [False]
    expected = spec['expected']
    return [set(answer) == set(expected)] + [_equal(answer.get(key), value) for key, value in expected.items()]


def _vectors(files, spec):
    vectors = _json_read(files['vectors.json'])
    if not isinstance(vectors, list) or not 3 <= len(vectors) <= 30:
        return [False]
    kills = set()
    for vector in vectors:
        if not isinstance(vector, dict) or set(vector) != {'input', 'expected'}:
            return [False]
        x = vector['input']
        if type(x) is not int or abs(x) > 100 or str(x) not in spec['oracle']:
            return [False]
        if type(vector['expected']) is not type(spec['oracle'][str(x)]):
            return [False]
        if vector['expected'] != spec['oracle'][str(x)]:
            return [False]
        for index, mutant in enumerate(spec['mutants']):
            if mutant[str(x)] != vector['expected']:
                kills.add(index)
    return [len(kills) == len(spec['mutants'])]


def _composite(files, spec):
    """Grade dependent artifacts with the same trusted, non-executing evaluators."""
    if not isinstance(spec, dict):
        raise ValueError('invalid composite grader')
    parts = spec.get('parts')
    if set(spec) != {'parts'} or not isinstance(parts, list) or not 2 <= len(parts) <= 8:
        raise ValueError('invalid composite grader')
    evaluators = {'behavior': _behavior, 'html': _html, 'sql': _sql, 'json': _json_answer, 'vectors': _vectors}
    checks = []
    for part in parts:
        if (not isinstance(part, dict) or set(part) != {'kind', 'files', 'spec'}
                or part['kind'] not in evaluators or not isinstance(part['files'], dict)
                or not 1 <= len(part['files']) <= 20
                or any(not isinstance(name, str) or name not in files for name in part['files'].values())):
            raise ValueError('invalid composite artifact mapping')
        selected = {name: files[path] for name, path in part['files'].items()}
        result = evaluators[part['kind']](selected, part['spec'])
        if not result:
            raise ValueError('empty composite acceptance')
        checks.extend(result)
    return checks


def grade(case_id, workspace, final_text=''):
    """Independent private evaluator; exit status and model claims are never acceptance."""
    case, fixture = _case(case_id)
    try:
        files, violations = _snapshot(Path(workspace), case, fixture)
        if violations:
            return {'accepted': False, 'checks': 0, 'safety_violations': len(violations),
                    'limited': False, 'limitations': case['limitations']}
        kind = case['grader_kind']
        evaluators = {'behavior': _behavior, 'html': _html, 'sql': _sql, 'composite': _composite,
                      'json': _json_answer, 'vectors': _vectors}
        checks = evaluators[kind](files, fixture['grader'])
        return {'accepted': bool(checks) and all(checks), 'checks': len(checks),
                'safety_violations': 0, 'limited': False, 'limitations': case['limitations']}
    except (ValueError, SyntaxError, OSError, UnicodeError, KeyError, TypeError,
            GradingError, sqlite3.Error, RecursionError, ArithmeticError):
        return {'accepted': False, 'checks': 0, 'safety_violations': 0,
                'limited': True, 'limitations': case['limitations'] + ['Malformed or unsupported submission; fail closed.']}


def validate_all(case_ids=None):
    manifest, fixtures = _load()
    selected=manifest
    if case_ids is not None:
        if (not isinstance(case_ids,list) or not case_ids or any(not isinstance(n,str) for n in case_ids)
                or len(case_ids)!=len(set(case_ids)) or set(case_ids)-{c['id'] for c in manifest}):
            raise ValueError('Explicit unique corpus selection required')
        selected=[c for c in manifest if c['id'] in case_ids]
    identities = {name: hashlib.sha256((ROOT/'scripts'/name).read_bytes()).hexdigest()
                  for name in ('v4_corpus.py', 'benchmark_runner.py')}
    results = []
    for case in selected:
        fixture = fixtures[case['id']]
        with tempfile.TemporaryDirectory(prefix='tuckbit-v4-corpus-') as directory:
            folder = Path(directory)
            materialize(case['id'], folder)
            seed = grade(case['id'], folder)
            for name, source in fixture['reference'].items():
                (folder / name).write_text(source)
            reference = grade(case['id'], folder)
            for name, source in fixture['negative'].items():
                (folder / name).write_text(source)
            negative = grade(case['id'], folder)
            results.append({'id': case['id'], 'available': case['grader_kind'] != 'sql' or hasattr(sqlite3.Connection, 'setlimit'), 'seed_rejected': not seed['accepted'],
                            'reference_accepted': reference['accepted'], 'negative_rejected': not negative['accepted'],
                            'reference_checks': reference['checks']})
    if identities != {name: hashlib.sha256((ROOT/'scripts'/name).read_bytes()).hexdigest() for name in identities} or _load() != (manifest, fixtures):
        raise ValueError('corpus or grader changed during validation')
    return {'schema_version': 1, 'manifest_sha256': digest(manifest), 'fixtures_sha256': digest(fixtures),
            'grader_implementation_sha256': digest(identities),
            'environment': {'python': platform.python_version(), 'sqlite': sqlite3.sqlite_version},
            'cases': len(results), 'graders_validated': sum(
        r['seed_rejected'] and r['reference_accepted'] and r['negative_rejected'] for r in results),
            'acceptance_assertions': sum(r['reference_checks'] for r in results),
            'unavailable_graders': sum(not r['available'] for r in results), 'results': results}


def pilot(path=None, runtime_controls=False):
    """V6 readiness references the frozen corpus; it never promotes structural graders to runtime evidence."""
    body=json.loads(Path(path or ROOT/'evals/v6/pilot.json').read_text())
    if (not isinstance(body,dict) or set(body)!={'schema','license','cases'} or type(body['schema']) is not int or body['schema']!=6
            or body['license']!='MIT' or not isinstance(body['cases'],list) or not 1<=len(body['cases'])<=10):
        raise ValueError('Invalid V6 pilot manifest')
    known={c['id']:c for c in cases()};seen=set();ready=[]
    fields={'id','source_revision','source_hashes','dependency_fingerprint','grader_sha256','runtime_ready','acceptance_gap'}
    for row in body['cases']:
        if not isinstance(row,dict) or set(row)!=fields or not isinstance(row['id'],str) or row['id'] not in known or row['id'] in seen:
            raise ValueError('Invalid or duplicate V6 candidate')
        case=known[row['id']];seen.add(row['id'])
        if (any(row[k]!=case[k] for k in fields-{'runtime_ready','acceptance_gap'})
                or type(row['runtime_ready']) is not bool or not isinstance(row['acceptance_gap'],str)
                or not row['acceptance_gap'] or len(row['acceptance_gap'])>1000
                or row['runtime_ready'] and case['grader_kind']!='sql'):
            raise ValueError('Source/grader mismatch or unsupported runtime acceptance')
        if row['runtime_ready']:ready.append(row['id'])
    controls=validate_all(ready)
    if controls['graders_validated']!=len(ready) or controls['unavailable_graders']:raise ValueError('V6 controls unavailable')
    result = {'schema':6,'model_calls':0,'manifest_sha256':digest(body),'candidates':body['cases'],
            'runtime_acceptance_controls':controls,'native_ready':False,
            'blockers':['Qualified repeated V52 calibration and separately approved V6 budget are required.',
                        'Non-SQL candidates require stronger independent runtime/compile/browser acceptance.',
                        'D requires a separately verified genuine native delegation transport.']}
    if runtime_controls:
        import v6_runtime
        result['runtime_companions'] = v6_runtime.validate_all()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['validate', 'manifest','pilot'])
    parser.add_argument('--runtime-controls', action='store_true', help='Pilot only: execute pinned V6 companion controls in checked local isolation; no inference')
    args = parser.parse_args()
    if args.runtime_controls and args.command != 'pilot': parser.error('--runtime-controls requires pilot')
    result = validate_all() if args.command == 'validate' else pilot(runtime_controls=args.runtime_controls) if args.command=='pilot' else cases()
    print(json.dumps(result, indent=2))
    return int(args.command == 'validate' and result['graders_validated'] != 60)


if __name__ == '__main__':
    raise SystemExit(main())
