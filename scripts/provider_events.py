#!/usr/bin/env python3
"""Opt-in numeric import of an explicitly approved Codex exec --json export.

Never discovers sessions, opens private logs, or emits message/tool payloads.
"""
import argparse
import json
import hashlib
import sys

from trace_profiler import MAX_EVENTS, ProfileError, read_text, validate

USAGE_FIELDS = {"input_tokens", "cached_input_tokens", "output_tokens", "reasoning_output_tokens"}
TOOL_TYPES = {"command_execution", "mcp_tool_call", "web_search"}


def public_tool_event(source, turn=None):
    """Transient command plus numeric/hashed public output; no arguments or raw output retained."""
    if source.get("type") not in {"item.started", "item.completed"}:
        return None
    item = source.get("item", {})
    if not isinstance(item, dict) or item.get("type") not in TOOL_TYPES | {"file_change"}:
        return None
    event = {"phase": "started" if source["type"] == "item.started" else "completed",
             "id": item.get("id"), "type": item["type"]}
    if turn is not None and isinstance(event['id'], str):
        event['id'] = str(turn)+':'+event['id']
    if item["type"] == "command_execution" and isinstance(item.get("command"), str):
        event["command"] = item["command"]
    status = item.get("status")
    code = item.get("exit_code")
    event["success"] = (code == 0) if type(code) is int else True if status == "completed" else False if status == "failed" else None
    output = item.get("aggregated_output")
    if isinstance(output, str):
        data = output.encode("utf-8")
        event.update(output_bytes=len(data), result=hashlib.sha256(data).hexdigest())
    if type(item.get("truncated")) is bool:
        event["truncated"] = item["truncated"]
    if item["type"] == "mcp_tool_call" and all(isinstance(item.get(k), str) for k in ("server", "tool")):
        event["capability"] = json.dumps([item["server"], item["tool"]])
    return event


def codex_execution(events, key):
    """Approved exports retain tool observations; historical source-level evidence stays unknown."""
    from execution_events import Observer
    codex_trace(events)
    observer = Observer(key)
    turn = 0
    for source in events:
        turn += source['type'] == 'turn.started'
        event = public_tool_event(source, turn)
        if event is not None:
            observer(event, None)
    complete = bool(events) and events[-1].get("type") == "turn.completed" and not any(e["type"] == "error" for e in events)
    return observer.export(complete)


def read_export(path, approved=False):
    if not approved:
        raise ProfileError("Explicit approval of this exported event file is required")
    return read_text(path)


def read_approved(path, approved=False):
    try:
        lines = read_export(path, approved).splitlines()
        if len(lines) > MAX_EVENTS:
            raise ProfileError("Export exceeds event limit")
        return [json.loads(line) for line in lines if line.strip()]
    except (UnicodeError, ValueError):
        raise ProfileError("Invalid UTF-8 JSONL export") from None


def codex_trace(events, verified=False, acceptance_checks_passed=False, *, execution=None):
    """Extract only public turn usage and completed tool invocation counts.

    Counts describe the supplied export only; completeness is the caller's duty.
    """
    if not isinstance(events, list) or len(events) > MAX_EVENTS:
        raise ProfileError("Events must be a bounded list")
    trace = {"schema": 1, "events": [], "outcome": {
        "verified": verified, "acceptance_checks_passed": acceptance_checks_passed}}
    current = None
    completed_items = set()
    completed_turns = 0
    terminal_complete = False
    stream_error = False
    for source in events:
        if not isinstance(source, dict) or not isinstance(source.get("type"), str):
            raise ProfileError("Invalid event envelope")
        kind = source["type"]
        if kind == "error":
            stream_error = True
        elif kind == "turn.started":
            if current is not None:
                raise ProfileError("Overlapping turns are unsupported")
            terminal_complete = False
            current = {"category": "other", "role": "root", "tool_invocations": 0,
                       "failed_attempts": 0}
            completed_items = set()
        elif kind == "item.completed":
            item = source.get("item")
            if not isinstance(item, dict) or not isinstance(item.get("type"), str):
                raise ProfileError("Invalid completed item")
            if item.get("type") in TOOL_TYPES:
                if current is None:
                    raise ProfileError("Tool completion outside a turn")
                identity = item.get("id")
                if not isinstance(identity, str) or not identity or identity in completed_items:
                    raise ProfileError("Missing or duplicate tool completion identifier")
                completed_items.add(identity)
                current["tool_invocations"] += 1
        elif kind in {"turn.completed", "turn.failed"}:
            if current is None:
                raise ProfileError("Turn completion without start")
            terminal_complete = kind == "turn.completed"
            if terminal_complete:
                completed_turns += 1
                usage = source.get("usage")
                if usage is not None and not isinstance(usage, dict):
                    raise ProfileError("Invalid usage object")
                current.update({key: value for key, value in (usage or {}).items() if key in USAGE_FIELDS})
            else:
                current["failed_attempts"] = 1
            trace["events"].append(current)
            current = None
        # Other envelopes, including reasoning/message payloads, are never inspected.
    incomplete = current is not None or not terminal_complete or not completed_turns or stream_error
    if incomplete and (verified or acceptance_checks_passed):
        raise ProfileError("Incomplete or failed export cannot certify a verified outcome")
    if current is not None:
        current["tool_invocations"] = None
        trace["events"].append(current)
    if execution is not None:
        trace["execution"] = execution
    validate(trace)
    return trace


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-jsonl", required=True)
    parser.add_argument("--approved", action="store_true", help="Consent to read this explicit export only")
    parser.add_argument("--verified", action="store_true", help="Caller independently verified the outcome")
    parser.add_argument("--acceptance-checks-passed", action="store_true")
    parser.add_argument("--study-key", help="Explicit private V5 key; adds tool observations, historical file coverage stays unknown")
    args = parser.parse_args()
    try:
        events = read_approved(args.codex_jsonl, args.approved)
        execution = None
        if args.study_key:
            from execution_events import read_study_key
            execution = codex_execution(events, read_study_key(args.study_key))
        trace = codex_trace(events, args.verified, args.acceptance_checks_passed, execution=execution)
        print(json.dumps(trace, sort_keys=True, indent=2))
        return 0
    except (OSError, ProfileError):
        print("TuckBit provider import rejected: invalid, inaccessible or unapproved export", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
