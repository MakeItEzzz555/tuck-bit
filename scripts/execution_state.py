#!/usr/bin/env python3
"""Explicit evidence packets and immutable checkpoints; never runs tools or agents."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re

MAX_BYTES = 2_000_000
DIGEST = re.compile(r"^[0-9a-f]{64}$")
REVISION = re.compile(r"^[0-9a-f]{40}([0-9a-f]{24})?$")

def symlink(path):
    # macOS exposes these immutable system aliases to normal temporary paths.
    aliases = {Path("/tmp"): Path("/private/tmp"), Path("/var"): Path("/private/var")}
    return path.is_symlink() and aliases.get(path) != path.resolve()

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()

def binding(revision, environment):
    if not isinstance(revision, str) or not REVISION.fullmatch(revision):
        raise ValueError("revision must be an explicit commit or source SHA-256")
    if not isinstance(environment, str) or not DIGEST.fullmatch(environment):
        raise ValueError("environment must be a SHA-256 of declared environment inputs")
    return {"revision": revision, "environment": environment}

def regular(path):
    path = Path(path).absolute()
    if any(symlink(p) for p in (path, *path.parents)):
        raise ValueError("symlink sources/destinations are not supported")
    if not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise ValueError("expected a bounded regular file")
    return path

def load(path):
    return json.loads(regular(path).read_text(encoding="utf-8"))

def write_new(path, value):
    path = Path(path).absolute()
    if any(symlink(p) for p in (path, *path.parents)):
        raise ValueError("symlink destination refused")
    data = json.dumps(value, indent=2, ensure_ascii=False).encode() + b"\n"
    if len(data) > MAX_BYTES:
        raise ValueError("checkpoint too large")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as output:
        output.write(data)

def source_path(root, relative):
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise ValueError("source must be a repository-relative file")
    parts = Path(relative).parts
    if Path(relative).is_absolute() or any(p.casefold() in ("..", ".git") for p in parts):
        raise ValueError("source escapes the allowed repository")
    if any(p.casefold().startswith(".env") or p.lower() in ("auth.json", "credentials", "credentials.json")
           or p.lower().endswith((".key", ".pem")) for p in parts):
        raise ValueError("credential-like evidence must not be included")
    root = Path(root).absolute()
    return regular(root / relative)

def packet(task, evidence, root, revision, environment, max_chars=8000):
    from plan_task import compile_plan
    contract = compile_plan(task)
    if type(max_chars) is not int or not 128 <= max_chars <= 64000:
        raise ValueError("output limit must be 128..64000 characters")
    if not isinstance(evidence, list) or len(evidence) > 20:
        raise ValueError("evidence must be an explicit list of at most 20 ranges")
    sources = []
    remaining = max_chars
    for ref in evidence:
        if not isinstance(ref, dict) or set(ref) != {"path", "start", "end"}:
            raise ValueError("evidence needs path/start/end only")
        path = source_path(root, ref["path"])
        raw = path.read_bytes()
        lines = raw.decode("utf-8").splitlines(keepends=True)
        start, end = ref["start"], ref["end"]
        if type(start) is not int or type(end) is not int or not 1 <= start <= end <= len(lines):
            raise ValueError("evidence line range is invalid")
        selected = "".join(lines[start-1:end])
        excerpt = selected[:remaining]
        remaining -= len(excerpt)
        sources.append({**ref, "sha256": hashlib.sha256(raw).hexdigest(), "excerpt": excerpt,
                        "truncated": len(excerpt) < len(selected),
                        "reread_from_line": start + excerpt.count("\n") if len(excerpt) < len(selected) else None})
    body = {"schema": 1, "kind": "scoped_evidence_packet", "binding": binding(revision, environment),
            "contract": contract, "sources": sources, "excerpt_character_limit": max_chars,
            "metadata_is_instruction": False, "tools_executed": False}
    return {**body, "sha256": digest(body)}

def packet_identity(value):
    """Check intrinsic identity; live source freshness still requires validate_packet."""
    from plan_task import compile_plan
    if not isinstance(value, dict) or value.get("kind") != "scoped_evidence_packet" or type(value.get("schema")) is not int or value["schema"] != 1:
        raise ValueError("unsupported evidence packet")
    body = {k:v for k,v in value.items() if k != "sha256"}
    if value.get("sha256") != digest(body):
        raise ValueError("packet integrity mismatch")
    if value["contract"] != compile_plan(value["contract"]["task_input"]):
        raise ValueError("packet contract mismatch")
    binding(**value["binding"])

def validate_packet(value, root, revision, environment):
    packet_identity(value)
    if value.get("binding") != binding(revision, environment):
        raise ValueError("revision/environment changed; invalidate previous verification")
    expected = packet(value["contract"]["task_input"],
                      [{k:ref[k] for k in ("path", "start", "end")} for ref in value["sources"]],
                      root, revision, environment, value["excerpt_character_limit"])
    if expected != value:
        raise ValueError("source, contract or excerpt changed; reread evidence and rerun affected checks")
    return True

def checkpoint(value, validations, next_action, previous=None):
    packet_identity(value)
    if not isinstance(next_action, str) or not next_action.strip() or len(next_action) > 1000:
        raise ValueError("a bounded next action is required")
    if not isinstance(validations, list) or len(validations) > 100:
        raise ValueError("invalid verification receipts")
    required = value["contract"]["required_checks_verbatim"]
    observed = {}
    for receipt in validations:
        if not isinstance(receipt, dict) or set(receipt) != {"check", "result", "binding", "packet_sha256", "evidence_sha256"}:
            raise ValueError("verification needs check/result/binding/packet_sha256/evidence_sha256")
        if receipt["check"] not in required or receipt["check"] in observed:
            raise ValueError("unknown/duplicate required check")
        if receipt["result"] not in ("passed", "failed", "skipped", "blocked"):
            raise ValueError("invalid verification result")
        if receipt["binding"] != value["binding"] or receipt["packet_sha256"] != value["sha256"] or not isinstance(receipt["evidence_sha256"], str) or not DIGEST.fullmatch(receipt["evidence_sha256"]):
            raise ValueError("verification is stale or has no evidence hash")
        observed[receipt["check"]] = receipt["result"]
    if previous is not None:
        validate_checkpoint(previous)
        if (previous["packet"]["contract"] != value["contract"] or
                previous["packet"]["binding"]["environment"] != value["binding"]["environment"]):
            raise ValueError("task contract or environment changed; start a new checkpoint chain")
    body = {"schema": 1, "kind": "execution_checkpoint", "sequence": previous["sequence"]+1 if previous else 1,
            "parent_sha256": previous["sha256"] if previous else None, "packet": value,
            "validations": validations, "next_action": next_action,
            "all_required_checks_passed": bool(required) and all(observed.get(check) == "passed" for check in required)}
    return {**body, "sha256": digest(body)}

def validate_checkpoint(value):
    if not isinstance(value, dict) or value.get("schema") != 1 or value.get("kind") != "execution_checkpoint":
        raise ValueError("unsupported checkpoint")
    if value.get("sha256") != digest({k:v for k,v in value.items() if k != "sha256"}):
        raise ValueError("checkpoint integrity mismatch")
    if type(value.get("sequence")) is not int or value["sequence"] < 1:
        raise ValueError("invalid checkpoint sequence")
    parent = value.get("parent_sha256")
    if (value["sequence"] == 1 and parent is not None) or (value["sequence"] > 1 and (not isinstance(parent,str) or not DIGEST.fullmatch(parent))):
        raise ValueError("invalid parent checkpoint hash")
    expected = checkpoint(value["packet"], value["validations"], value["next_action"])
    ignored = {"sha256", "sequence", "parent_sha256"}
    if {k:v for k,v in value.items() if k not in ignored} != {k:v for k,v in expected.items() if k not in ignored}:
        raise ValueError("checkpoint verification status does not match receipts")

def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    create = sub.add_parser("packet")
    create.add_argument("task")
    create.add_argument("evidence")
    create.add_argument("--max-chars", type=int, default=8000)
    for name in ("checkpoint", "resume"):
        q = sub.add_parser(name)
        q.add_argument("input")
        if name == "checkpoint":
            q.add_argument("--validations", required=True)
            q.add_argument("--next-action", required=True)
            q.add_argument("--previous")
    for q in (create, *[sub.choices[x] for x in ("checkpoint", "resume")]):
        q.add_argument("--root", required=True)
        q.add_argument("--revision", required=True)
        q.add_argument("--environment", required=True)
        if q != sub.choices["resume"]:
            q.add_argument("--output", required=True)
    args = p.parse_args()
    try:
        if args.command == "packet":
            result = packet(load(args.task), load(args.evidence), args.root, args.revision, args.environment, args.max_chars)
        elif args.command == "checkpoint":
            value = load(args.input)
            validate_packet(value, args.root, args.revision, args.environment)
            result = checkpoint(value, load(args.validations), args.next_action, load(args.previous) if args.previous else None)
        else:
            result = load(args.input)
            validate_checkpoint(result)
            validate_packet(result["packet"], args.root, args.revision, args.environment)
            print(json.dumps({"resumable":True,"sequence":result["sequence"],"next_action":result["next_action"],
                              "all_required_checks_passed":result["all_required_checks_passed"]}))
            return
        write_new(args.output, result)
        print(json.dumps({"written": True, "sha256": result["sha256"]}))
    except (ValueError, OSError, KeyError, TypeError, UnicodeError) as exc:
        p.error(str(exc))

if __name__ == "__main__":
    main()
