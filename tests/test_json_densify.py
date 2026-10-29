import json
from pathlib import Path
import random
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from json_densify import densify, expand

ROWS=[{'id':i,'name':'item %d'%i,'ok':i%2==0,'score':i/4,'owner':None if i%3 else 'a, "b"\nc'} for i in range(20)]


class DensifyTests(unittest.TestCase):
    def test_round_trip_is_exact_and_smaller(self):
        text=json.dumps(ROWS,indent=2)
        dense,applied=densify(text)
        self.assertTrue(applied)
        self.assertLess(len(dense),len(text))
        self.assertTrue(dense.startswith('[20]{id:int,name:string,ok:bool,score:float,owner:string?}\n'))
        self.assertEqual(expand(dense),ROWS)

    def test_unverifiable_inputs_are_returned_unchanged(self):
        cases=[
            [{'v':''},{'v':None},{'v':'x'}],             # "" and null collide in a nullable column
            [{'v':1},{'v':True}],                         # bool is not int
            [{'v':1},{'v':1.5}],                          # mixed numeric types
            [{'v':{'nested':1}},{'v':{'nested':2}}],      # nested values unsupported
            [{'a':1,'b':2},{'b':2,'a':1}],                # key order differs
            [{'a,b':1},{'a,b':2}],                        # unsafe key
            [{'a':1}],                                    # single row never shrinks
            {'items':[{'a':1},{'a':2}]},                  # shortcut: top-level arrays only; extend when tool outputs need it
        ]
        for value in cases:
            text=json.dumps(value,indent=2)
            with self.subTest(value=value):
                self.assertEqual(densify(text),(text,False))
        self.assertEqual(densify('not json'),('not json',False))

    def test_adversarial_values_survive_the_densified_path(self):
        rows=[{'s':s,'f':f,'i':i,'b':b} for s,f,i,b in (
            ('ünïcødé 漢字 🙂',-0.0,10**30,True),(',"\r\n\t;|',5e-324,-1,False),('true',1.0,0,True),
            ('null',1e300,7,False),('  padded  ',0.1,2**63,True),('\\',123456.789,-(2**70),False))]
        dense,applied=densify(json.dumps(rows))
        self.assertTrue(applied,'must exercise the densified path, not fallback')
        self.assertTrue(dense.startswith('[6]{s:string,f:float,i:int,b:bool}\n'))
        self.assertEqual(json.dumps(expand(dense)),json.dumps(rows))
        self.assertEqual(densify(json.dumps(rows)),(dense,True),'deterministic')

    def test_lossy_or_unsafe_inputs_fall_back(self):
        filler=[{'a':i} for i in range(5)]
        for text in ('[{"a":1,"a":2},{"a":3,"a":4},{"a":5,"a":6}]',     # duplicate keys
                     json.dumps(filler)[:-1]+',{"a":NaN}]',               # non-finite constant
                     json.dumps(filler)[:-1]+',{"a":1e400}]',             # overflows to infinity
                     json.dumps([{'a':'\ud800'+'x'*20} for _ in range(5)]),  # lone surrogate
                     '[{"a":1},{"a":2}'):                                  # malformed
            with self.subTest(text=text[:40]):self.assertEqual(densify(text),(text,False))
        big=json.dumps([{'a':'x'*100} for _ in range(50_000)])
        self.assertGreater(len(big.encode()),4*1024*1024)
        self.assertEqual(densify(big),(big,False))

    def test_value_equality_not_byte_equality(self):
        text='[{"a":1.50,"b":1e2},{"a":2.50,"b":3e2},{"a":3.50,"b":4e2}]'
        dense,applied=densify(text)
        self.assertTrue(applied)
        self.assertEqual(expand(dense),json.loads(text))
        self.assertNotIn('1.50',dense)

    def test_cli_reports_chars_and_bytes_and_bounded_errors(self):
        import subprocess,tempfile
        script=str(Path(__file__).resolve().parents[1]/'scripts/json_densify.py')
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'rows.json';path.write_text(json.dumps(ROWS))
            p=subprocess.run([sys.executable,script,str(path)],capture_output=True,text=True,timeout=30)
            stats=json.loads(p.stderr)
            self.assertEqual((p.returncode,stats['applied']),(0,True))
            self.assertEqual(expand(p.stdout),ROWS)
            self.assertLess(stats['densified_utf8_bytes'],stats['original_utf8_bytes'])
            path.write_bytes(b'\xff\xfe')
            p=subprocess.run([sys.executable,script,str(path)],capture_output=True,text=True,timeout=30)
            self.assertEqual((p.returncode,json.loads(p.stderr),p.stdout),(2,{'error':'unreadable_file'},''))

    def test_random_flat_rows_never_change_meaning(self):
        rng=random.Random(20261019)
        pools=[lambda:rng.randint(-10**9,10**9),lambda:rng.choice([True,False]),lambda:rng.uniform(-1e6,1e6),
               lambda:''.join(rng.choice('ab ,"\n\'\\é0') for _ in range(rng.randint(0,8)))]
        applied_count=0
        for _ in range(200):
            gens=[rng.choice(pools) for _ in range(rng.randint(1,5))]
            rows=[{'k%d'%i:(None if rng.random()<0.1 else g()) for i,g in enumerate(gens)} for _ in range(rng.randint(2,12))]
            text=json.dumps(rows)
            dense,applied=densify(text)
            applied_count+=applied
            self.assertEqual(json.loads(text) if not applied else expand(dense),rows)
        self.assertGreater(applied_count,100,'fuzz must exercise the densified path, not only fallbacks')


if __name__=='__main__':unittest.main()
