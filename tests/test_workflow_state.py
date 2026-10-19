import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import workflow_state as flow

class WorkflowStateTests(unittest.TestCase):
    def event(self,state,kind,task=None,**extra):
        event={"id":str(len(state["events"])+1),"kind":kind,**extra}
        if task: event["task"]=task
        if kind in ("succeed","rollback"): event["receipt_sha256"]="a"*64
        return flow.advance(state,event)

    def test_dependency_order_and_parallel_capacity(self):
        state=flow.create({"mode":"parallel","opt_in":True,"max_parallel":2,"tasks":[
            {"id":"a","owned_files":["a.py"]},{"id":"b","owned_files":["b.py"]},
            {"id":"review","owned_files":["report.md"],"depends_on":["a","b"]}]})
        self.assertEqual(flow.ready(state),["a","b"])
        state=self.event(state,"start","a")
        state=self.event(state,"start","b")
        self.assertEqual(flow.ready(state),[])
        state=self.event(state,"succeed","a")
        state=self.event(state,"succeed","b")
        self.assertEqual(flow.ready(state),["review"])
        flow.validate(state)

    def test_overlap_cycles_missing_dependencies_and_opt_in(self):
        for paths in [("src","src/a.py"),("A.py","a.py"),("../x","b.py")]:
            with self.assertRaises(ValueError): flow.create({"mode":"parallel","opt_in":True,"tasks":[
                {"id":"a","owned_files":[paths[0]]},{"id":"b","owned_files":[paths[1]]}]})
        for dependency in ("a","missing"):
            with self.assertRaises(ValueError): flow.create({"tasks":[{"id":"a","depends_on":[dependency]}]})
        with self.assertRaises(ValueError): flow.create({"mode":"parallel","tasks":[{"id":"a","owned_files":["a"]}]})

    def test_interrupt_restart_retry_bound_and_duplicate_event(self):
        state=flow.create({"tasks":[{"id":"a","max_attempts":2}]})
        state=self.event(state,"start","a")
        state=self.event(state,"interrupt","a")
        saved=copy.deepcopy(state)
        flow.validate(saved)
        self.assertEqual(flow.advance(saved,saved["events"][-1]),saved)
        conflict={**saved["events"][-1],"kind":"fail"}
        with self.assertRaises(ValueError): flow.advance(saved,conflict)
        state=self.event(saved,"start","a")
        state=self.event(state,"fail","a")
        self.assertEqual(flow.ready(state),[])
        with self.assertRaises(ValueError): self.event(state,"start","a")

    def test_continuous_explicit_trigger_event_budget_and_stop(self):
        spec={"mode":"continuous","opt_in":True,"event_trigger":"source_changed","stop_condition":"user_stop",
              "max_events":2,"tasks":[{"id":"a"}]}
        state=flow.create(spec)
        with self.assertRaises(ValueError): self.event(state,"start","a")
        state=self.event(state,"start","a",trigger="source_changed")
        state=self.event(state,"stop")
        self.assertEqual(flow.ready(state),[])
        with self.assertRaises(ValueError): self.event(state,"start","a",trigger="source_changed")

    def test_review_only_forbids_write_actions_and_requires_host_receipts(self):
        state=flow.create({"mode":"review","tasks":[{"id":"audit"}]})
        self.assertFalse(state["writes_allowed"])
        self.assertFalse(state["permissions_granted"])
        with self.assertRaises(ValueError): self.event(state,"write","audit")
        state=self.event(state,"start","audit")
        with self.assertRaises(ValueError): flow.advance(state,{"id":"next","kind":"succeed","task":"audit"})

    def test_rollback_cancels_dependent_work_and_tampering_is_rejected(self):
        state=flow.create({"tasks":[{"id":"a"},{"id":"b","depends_on":["a"]}]})
        state=self.event(state,"start","a")
        state=self.event(state,"succeed","a")
        state=self.event(state,"start","b")
        state=self.event(state,"rollback","a")
        self.assertEqual(state["nodes"]["b"]["status"],"cancelled")
        flow.validate(state)
        state["permissions_granted"]=True
        with self.assertRaises(ValueError): flow.validate(state)

    def test_non_integer_limits_and_unknown_events_refused(self):
        for field in ("max_parallel","max_events"):
            with self.assertRaises(ValueError): flow.create({field:True,"tasks":[{"id":"a"}]})
        state=flow.create({"tasks":[{"id":"a"}]})
        with self.assertRaises(ValueError): flow.advance(state,{"id":"1","kind":"start","task":[]})

    def test_exhausted_budget_still_allows_stop_and_post_stop_rollback(self):
        state=flow.create({"max_events":1,"tasks":[{"id":"a"}]})
        state=self.event(state,"start","a")
        state=self.event(state,"stop")
        state=self.event(state,"rollback","a")
        self.assertEqual(state["nodes"]["a"]["status"],"rolled_back")
        self.assertEqual(flow.ready(state),[])
        flow.validate(state)

    def test_continuous_repeated_trigger_starts_bounded_new_cycle(self):
        state=flow.create({"mode":"continuous","opt_in":True,"event_trigger":"changed","stop_condition":"done",
                           "max_events":4,"tasks":[{"id":"a"}]})
        state=self.event(state,"start","a",trigger="changed")
        state=self.event(state,"succeed","a")
        state=self.event(state,"cycle",trigger="changed")
        self.assertEqual(state["cycles"],2)
        state=self.event(state,"start","a",trigger="changed")
        state=self.event(state,"succeed","a")
        with self.assertRaises(ValueError): self.event(state,"cycle",trigger="changed")
        flow.validate(state)

if __name__=="__main__": unittest.main()
