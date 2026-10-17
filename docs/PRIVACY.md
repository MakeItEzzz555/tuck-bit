# Privacy and data-handling principles

TuckBit's public preview is designed to work with provider-native permissions and keep execution data under the developer's control.

## What is not collected automatically

- TuckBit does **not** run a central telemetry service.
- The portable Agent Skill is an instruction document, not a monitoring daemon.
- The local capability registry reads only user-selected skill directories and optional metadata snapshots. It never contacts an MCP provider on its own.
- The profiler reads only explicitly supplied structured numeric/hashed events, and refuses raw prompt/output fields.
- Claude/Gemini hook prototypes are not enabled or registered automatically. The documented adapters emit a brief generic advisory and do not persist the prompt.

## Inputs you should treat as sensitive

Task JSON may contain the full user request, constraints or local references. Router output preserves those fields and is **not automatically sanitized**. Do not upload task JSON, generated task envelopes, raw agent transcripts, private logs, credentials, file inventories or screenshots containing personal information.

A capability index can still reveal the names and descriptions of locally installed skills or tools. Review that metadata before sharing.

## Installing safely

Use project-scoped or dry-run installation first. Global scope requires explicit selection. Review the skill and optional scripts before executing them. Host tool approvals always remain authoritative; TuckBit does not grant permission to perform operations.

## Security review and public contributions

The repository enables GitHub secret scanning, push protection and private vulnerability reporting. CI additionally runs a limited public-source privacy-pattern audit, which checks obvious credential signatures and personal home paths. **Neither mechanism guarantees discovery of every sensitive value.**

Never paste actual credentials or proprietary examples into public issues or PRs. Report vulnerabilities privately using the [Security policy](../SECURITY.md).

The filename guard flags exact sensitive basenames and selected extensions (case-insensitive),
so `.env.example` is allowed while `.env` is flagged. The home-path pattern is deliberately
narrow and substring-based: a relative example with a home-like `Users` segment can also be flagged.
Use `<HOME>` or `<user>` placeholders in public examples. If file discovery or reading fails,
the audit exits with code `2`; findings exit `1`, and a completed clean scan exits `0`.

## Git history and retention

Files removed from the current branch can remain accessible in earlier public Git commits, forks, caches or clones. A normal commit does **not** erase previously public information. Treat any accidentally exposed credential as compromised, revoke/rotate it, and coordinate remediation with maintainers; history rewriting is not automatic and needs explicit review.
