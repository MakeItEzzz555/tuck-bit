#!/usr/bin/env python3
"""Conservative public-source privacy guard; no credentials, network, or model access.

High-confidence findings only. This does not replace GitHub secret scanning,
manual review, nor an independent check of reachable Git history.
"""
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
MAX_TEXT_BYTES = 5_000_000
SENSITIVE_FILENAMES = {
    ".env", ".netrc", ".npmrc", "id_rsa", "id_ed25519",
    "credentials.json", "service-account.json"
}
SENSITIVE_EXTENSIONS = {".pem", ".p12", ".pfx", ".key", ".har", ".sqlite", ".db", ".jsonl"}
KEY_PREFIXES = ["gh" + "p_", "gh" + "o_", "github" + "_pat_",
                "sk" + "-proj-", "xox" + "b-", "xox" + "p-"]
TOKEN_REGEX = re.compile(
    "(?:" + "|".join(re.escape(prefix) for prefix in KEY_PREFIXES) + r")[A-Za-z0-9_-]{24,}"
)
PEM_REGEX = re.compile("-----BEGIN " + "(?:RSA |OPENSSH |EC |DSA )?PRIVATE KEY" + "-----")
HOME_REGEX = re.compile(
    "/" + "Users/" + r"[A-Za-z0-9._-]{2,}/"
    + "|" + r"C:\\" + "Users" + r"\\" + r"[A-Za-z0-9._-]{2,}\\"
)

def scan_text(text):
    """Return category names; never expose matching credential/path values."""
    if not isinstance(text, str):
        raise ValueError("Expected decoded text")
    issues = []
    if TOKEN_REGEX.search(text):
        issues.append("recognizable_token_prefix")
    if PEM_REGEX.search(text):
        issues.append("private_key_block")
    if HOME_REGEX.search(text):
        issues.append("personal_home_path")
    return issues

def check_path(rel):
    if not isinstance(rel, str):
        return ["invalid_filename"]
    path = Path(rel)
    if path.name in SENSITIVE_FILENAMES or path.suffix.lower() in SENSITIVE_EXTENSIONS:
        return ["high_risk_filename"]
    if any(part in ("private", "internal", "sessions", "captures") for part in path.parts):
        return ["private_workspace_path"]
    return []

def tracked_and_new_files(root):
    p = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        capture_output=True, check=True
    )
    return sorted(set(x.decode("utf-8", "replace") for x in p.stdout.split(b"\0") if x))

def audit(root=ROOT):
    findings = []
    inspected = 0
    skipped_binary = 0
    for rel in tracked_and_new_files(root):
        path = root / rel
        for issue in check_path(rel):
            findings.append((rel, issue))
        if path.is_symlink():
            findings.append((rel, "unreviewed_symlink"))
            continue
        if not path.is_file():
            continue
        if path.stat().st_size > MAX_TEXT_BYTES:
            findings.append((rel, "oversized_unreviewed_file"))
            continue
        data = path.read_bytes()
        if b"\x00" in data:
            skipped_binary += 1
            continue
        try:
            body = data.decode("utf-8")
        except UnicodeDecodeError:
            skipped_binary += 1
            continue
        inspected += 1
        for issue in scan_text(body):
            findings.append((rel, issue))
    return inspected, skipped_binary, findings

def main():
    try:
        checked, binary, issues = audit()
    except (OSError, subprocess.CalledProcessError) as exc:
        print("Public source audit could not complete: " + type(exc).__name__, file=sys.stderr)
        return 2
    print(f"Public-source audit: {checked} text files inspected, {binary} non-text files not inspected")
    for path, category in issues:
        print(f"REVIEW REQUIRED: {path} [{category}]")
    if issues:
        return 1
    print("No high-confidence credential/private-path patterns found. History and binaries still require review.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
