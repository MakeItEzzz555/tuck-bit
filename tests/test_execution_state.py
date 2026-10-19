import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import execution_state as state

REV="a"*40
ENV="b"*64
TASK={"request":"Inspect a source file", "checks":["unit tests"], "constraints":["No network"]}

class ExecutionStateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        (self.root/"source.py").write_text("line one\n"+"x"*200+"\nline three\n")

    def packet(self):
        return state.packet(TASK,[{"path":"source.py","start":1,"end":3}],self.root,REV,ENV,128)

    def test_scoped_output_preserves_contract_and_truncation_reference(self):
        packet=self.packet()
        self.assertEqual(packet["contract"]["constraints_verbatim"],["No network"])
        self.assertEqual(len(packet["sources"][0]["excerpt"]),128)
        self.assertTrue(packet["sources"][0]["truncated"])
        self.assertEqual(packet["sources"][0]["reread_from_line"],2)
        self.assertTrue(state.validate_packet(packet,self.root,REV,ENV))

    def test_source_revision_environment_or_packet_changes_invalidate(self):
        packet=self.packet()
        for revision,environment in [("c"*40,ENV),(REV,"d"*64)]:
            with self.assertRaises(ValueError): state.validate_packet(packet,self.root,revision,environment)
        changed=copy.deepcopy(packet)
        changed["contract"]["request"]="forged"
        with self.assertRaises(ValueError): state.validate_packet(changed,self.root,REV,ENV)
        (self.root/"source.py").write_text("changed\n")
        with self.assertRaises(ValueError): state.validate_packet(packet,self.root,REV,ENV)

    def test_bound_receipts_and_immutable_versioned_recovery(self):
        packet=self.packet()
        receipts=[{"check":"unit tests","result":"passed","binding":packet["binding"],"packet_sha256":packet["sha256"],"evidence_sha256":"d"*64}]
        first=state.checkpoint(packet,receipts,"Review the patch")
        second=state.checkpoint(packet,receipts,"Finish",first)
        self.assertTrue(first["all_required_checks_passed"])
        self.assertEqual(second["sequence"],2)
        self.assertEqual(second["parent_sha256"],first["sha256"])
        path=self.root/"checkpoint.json"
        state.write_new(path,second)
        state.validate_checkpoint(state.load(path))
        with self.assertRaises(FileExistsError): state.write_new(path,first)

    def test_missing_failed_skipped_and_stale_checks_never_become_green(self):
        packet=self.packet()
        self.assertFalse(state.checkpoint(packet,[],"Run tests")["all_required_checks_passed"])
        for result in ("failed","skipped","blocked"):
            receipt={"check":"unit tests","result":result,"binding":packet["binding"],"packet_sha256":packet["sha256"],"evidence_sha256":"d"*64}
            self.assertFalse(state.checkpoint(packet,[receipt],"Run tests")["all_required_checks_passed"])
            receipt["binding"]={"revision":"c"*40,"environment":ENV}
            with self.assertRaises(ValueError): state.checkpoint(packet,[receipt],"Run tests")

    def test_unsafe_evidence_and_symlink_ancestors_are_rejected(self):
        for path in ("../source.py","/etc/passwd",".git/config",".GIT/config",".env",".ENV","auth.json","secret.key"):
            with self.assertRaises(ValueError):
                state.packet(TASK,[{"path":path,"start":1,"end":1}],self.root,REV,ENV)
        (self.root/"linked").symlink_to(self.root,target_is_directory=True)
        with self.assertRaises(ValueError): state.source_path(self.root,"linked/source.py")
        with self.assertRaises(ValueError): state.write_new(self.root/"linked/out.json",{})

    def test_invalid_ranges_limits_and_duplicate_checks(self):
        for start,end in [(True,1),(0,1),(1,4),(3,2)]:
            with self.assertRaises(ValueError): state.packet(TASK,[{"path":"source.py","start":start,"end":end}],self.root,REV,ENV)
        with self.assertRaises(ValueError): state.packet(TASK,[],self.root,REV,ENV,True)
        packet=self.packet()
        receipt={"check":"unit tests","result":"passed","binding":packet["binding"],"packet_sha256":packet["sha256"],"evidence_sha256":"d"*64}
        with self.assertRaises(ValueError): state.checkpoint(packet,[receipt,receipt],"Review")
        first=state.checkpoint(packet,[],"Review")
        first["sequence"]=7
        with self.assertRaises(ValueError): state.validate_checkpoint(first)

    def test_recomputed_checksums_do_not_authorize_fabricated_evidence_or_green_status(self):
        packet=self.packet()
        altered=copy.deepcopy(packet)
        altered["sources"][0]["excerpt"]="fabricated content"
        altered["sha256"]=state.digest({k:v for k,v in altered.items() if k!="sha256"})
        with self.assertRaises(ValueError): state.validate_packet(altered,self.root,REV,ENV)
        altered=copy.deepcopy(packet)
        altered["sources"][0]["start"]=False
        altered["sha256"]=state.digest({k:v for k,v in altered.items() if k!="sha256"})
        with self.assertRaises(ValueError): state.validate_packet(altered,self.root,REV,ENV)
        checkpoint=state.checkpoint(packet,[],"Run tests")
        checkpoint["all_required_checks_passed"]=True
        checkpoint["sha256"]=state.digest({k:v for k,v in checkpoint.items() if k!="sha256"})
        with self.assertRaises(ValueError): state.validate_checkpoint(checkpoint)

    def test_dirty_source_change_invalidates_receipt_even_at_same_commit(self):
        before=self.packet()
        receipt={"check":"unit tests","result":"passed","binding":before["binding"],
                 "packet_sha256":before["sha256"],"evidence_sha256":"d"*64}
        (self.root/"source.py").write_text("new\nsource\nstate\n")
        after=self.packet()
        self.assertNotEqual(before["sha256"],after["sha256"])
        with self.assertRaises(ValueError): state.checkpoint(after,[receipt],"Review")

if __name__=="__main__": unittest.main()
