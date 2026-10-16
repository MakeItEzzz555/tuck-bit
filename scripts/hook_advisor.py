#!/usr/bin/env python3
"""Optional read-only task-entry hook for supported provider runtimes.

This script is NOT automatically registered. It never executes tools or logs prompts.
"""
import argparse
import json
import re
import sys

MAX_EVENT_BYTES = 65536
TRIGGER = re.compile(
    r"\b(fix|debug|implement|refactor|test|build|review|"
    r"migrat\w*|deploy|audit|investigat\w*|agentic|orchestrat\w*|"
    r"subagents?|coding|codebase|repository|compil\w*)\b", re.I
)
COMPLEX = re.compile(
    r"\b(auth|secur\w*|migrat\w*|production|payment|"
    r"concurren\w*|race condition|database schema|data loss)\b", re.I
)
PARALLEL = re.compile(r"\b(parallel|subagents?|agent team|orchestrat\w*)\b", re.I)
TECH_CONTEXT = re.compile(
    r"\b(bug|code|codebase|agents?|repo|repository|projects?|files?|"
    r"functions?|methods?|api|ui|tests?|application|app|software|cli|"
    r"skills?|tools?|feature|pull request|pr|migration|deploy|auth|security)\b",re.I
)
OPT_OUT = re.compile(r"\b(no|without|disable|skip|don't use|do not use)\s+tuck\s*-?\s*bit\b",re.I)


CORE = ("TuckBit advisory: preserve the user's full requirements and native "
        "permissions. Retrieve relevant evidence/tools on demand; implement "
        "fully, validate proportionately, and stop when verified.")
HIGH_RISK = " Preserve mandatory risk, security and rollback checks."
MULTI = " Delegate only independent, owned work when authorized."

def advise(event, host):
    expected = "UserPromptSubmit" if host=="claude" else "BeforeAgent"
    if not isinstance(event, dict) or event.get("hook_event_name") != expected:
        return {}
    prompt = event.get("prompt")
    if not isinstance(prompt, str) or len(prompt.encode("utf-8")) > MAX_EVENT_BYTES:
        return {}
    if OPT_OUT.search(prompt) or not TRIGGER.search(prompt) or not TECH_CONTEXT.search(prompt):
        return {}
    message = CORE
    if COMPLEX.search(prompt):
        message += HIGH_RISK
    if PARALLEL.search(prompt):
        message += MULTI
    # Nothing about the original prompt or paths is echoed to stdout.
    if host == "claude":
        return {"hookSpecificOutput":{
            "hookEventName":"UserPromptSubmit",
            "additionalContext":message}}
    return {"hookSpecificOutput":{
        "hookEventName":"BeforeAgent",
        "additionalContext":message}}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", choices=("claude","gemini"),required=True)
    args=parser.parse_args()
    try:
        payload=sys.stdin.buffer.read(MAX_EVENT_BYTES+1)
        if len(payload)>MAX_EVENT_BYTES:
            result={}
        else:
            result=advise(json.loads(payload.decode("utf-8")),args.host)
    except (ValueError,UnicodeError,OSError):
        result={}
    print(json.dumps(result,ensure_ascii=False))

if __name__=="__main__":
    main()
