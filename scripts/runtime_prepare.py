#!/usr/bin/env python3
"""Consolidate explicit V3 preparation; advice never grants execution permission.

Output includes task/source excerpts and must remain private. Finalization accepts
caller-attested receipts, not subprocess exit codes or proof of independent grading.
"""
import argparse
import copy
import json
import time

import adaptive_execution as adaptive
import capability_registry as registry
import execution_state as state
from plan_task import compile_plan
from workflow_router import route


def prepare(envelope):
    adaptive.exact(envelope, ("task", "scope", "binding", "source_root", "source_ranges"),
                   "consolidated input", ("registry", "events", "evidence", "max_chars"))
    value = copy.deepcopy(envelope)
    stages = {}

    def timed(name, operation):
        started = time.perf_counter_ns()
        result = operation()
        stages[name] = time.perf_counter_ns() - started
        return result

    advice = timed("adaptive", lambda: adaptive.prepare(value["task"], value["scope"], value["binding"],
                                                       value.get("events"), value.get("evidence")))
    selected = value.get("registry")
    snapshot = None
    kwargs = {}
    if selected is not None:
        adaptive.exact(selected, ("roots",), "registry input", ("tools_file", "snapshot", "focused"))
        if not isinstance(selected["roots"], list) or any(not isinstance(root, str) for root in selected["roots"]):
            raise ValueError("Registry roots must be explicit paths")
        kwargs = {"capability_roots": selected["roots"], "capability_tools_file": selected.get("tools_file"),
                  "focused_discovery": selected.get("focused", False),
                  "capability_revision": value["binding"]["revision"],
                  "capability_environment": value["binding"]["environment"]}
        if "snapshot" in selected:
            registry.validate_snapshot(selected["snapshot"])
        snapshot = timed("registry", lambda: selected["snapshot"] if "snapshot" in selected else registry.build(
            selected["roots"], selected.get("tools_file"), value["binding"]["revision"], value["binding"]["environment"]))
    workflow = timed("routing", lambda: route(value["task"], snapshot, **kwargs))
    packet = timed("context", lambda: state.packet(value["task"], value["source_ranges"], value["source_root"],
                    value["binding"]["revision"], value["binding"]["environment"], value.get("max_chars", 8000)))
    contract = advice["contract"]
    if contract != workflow["task"] or contract != packet["contract"]:
        raise ValueError("Preparation contract mismatch")
    body = {"schema": 1, "kind": "consolidated_preparation", "inputs": value, "contract": contract,
            "adaptive": advice, "workflow": workflow, "packet": packet,
            "stage_ns": stages, "permissions_granted": False, "tools_executed": False,
            "activation": {"recommended": bool(workflow["routing"]["suggested_capabilities"]),
                           "selected": None, "instructions_read": None, "tool_invoked": None,
                           "result_verified": None},
            "limitations": ["Explicit source ranges are caller-selected; this is not a repository index.",
                            "Registry metadata is untrusted advice, never permission.",
                            "Receipts and binding labels require independent host verification."]}
    return {**body, "sha256": state.digest(body)}


def _validate_prepared(prepared):
    if not isinstance(prepared, dict) or prepared.get("kind") != "consolidated_preparation":
        raise ValueError("Expected consolidated preparation")
    if prepared.get("sha256") != state.digest({k: v for k, v in prepared.items() if k != "sha256"}):
        raise ValueError("Preparation integrity mismatch")
    inputs = prepared["inputs"]
    if prepared["contract"] != compile_plan(inputs["task"]) or prepared["packet"]["contract"] != prepared["contract"]:
        raise ValueError("Preparation task changed")
    state.validate_packet(prepared["packet"], inputs["source_root"], **inputs["binding"])
    return inputs


def delivery(prepared, mode="compact"):
    """Experimental agent view; full preparation remains the finalization authority."""
    inputs = _validate_prepared(prepared)
    if mode not in {"full", "compact", "references"}:
        raise ValueError("Unknown experimental delivery mode")
    if mode == "full":
        return copy.deepcopy(prepared)
    if prepared["workflow"]["task"] != prepared["contract"] or prepared["adaptive"]["contract"] != prepared["contract"]:
        raise ValueError("Delivery contract mismatch")
    sources = copy.deepcopy(prepared["packet"]["sources"])
    if mode == "references":
        for source in sources:
            source.pop("excerpt")
    body = {"schema": 1, "kind": "experimental_preparation_delivery", "mode": mode,
            "preparation_sha256": prepared["sha256"], "packet_sha256": prepared["packet"]["sha256"],
            "binding": inputs["binding"], "contract": prepared["contract"], "sources": sources,
            "routing": prepared["workflow"]["routing"],
            "adaptive": {key: prepared["adaptive"][key] for key in ("routing", "recommendations", "verification", "limitations")},
            "permissions_granted": False, "tools_executed": False, "activation": prepared["activation"],
            "limitations": prepared["limitations"]}
    body = copy.deepcopy(body)
    return {**body, "sha256": state.digest(body)}


def validate_delivery(value, prepared, mode):
    if value != delivery(prepared, mode):
        raise ValueError("Delivery/source/mandatory guidance changed")
    return True


def finalize(prepared, validations, next_action, previous=None):
    _validate_prepared(prepared)
    if not prepared["contract"]["required_checks_verbatim"]:
        raise ValueError("Final verification needs explicit acceptance checks")
    return state.checkpoint(prepared["packet"], validations, next_action, previous)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("input")
    p = sub.add_parser("finalize")
    p.add_argument("input")
    p.add_argument("validations")
    p.add_argument("--next-action", required=True)
    p.add_argument("--previous")
    for p in sub.choices.values():
        p.add_argument("--output", required=True, help="New private output; refuses overwrite")
    args = parser.parse_args()
    try:
        value = state.load(args.input)
        result = prepare(value) if args.command == "prepare" else finalize(
            value, state.load(args.validations), args.next_action,
            state.load(args.previous) if args.previous else None)
        state.write_new(args.output, result)
        print(json.dumps({"written": True, "sha256": result["sha256"]}))
    except (ValueError, OSError, KeyError, TypeError, UnicodeError, RecursionError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
