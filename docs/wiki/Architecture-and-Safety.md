# Architecture and Safety

TuckBit is primarily an **execution-guidance layer**, not an agent runtime or permission system.

## Execution flow

1. Preserve the user's task, constraints and mandatory checks as an explicit task contract.
2. Recommend Fast, Standard or Deep based on declared evidence and risk.
3. Discover relevant skill/tool **metadata** from authorized sources; recommendations do not grant execution rights.
4. Read only task-relevant evidence and invalidate context on source changes.
5. Run the user's required tests and security checks; emit a bounded result/evidence receipt.
6. Consider parallel work only for genuinely independent ownership with independent integration review.

The local CLI evaluates explicitly provided files. The portable skill is instruction-only. Optional hooks are **off unless the user configures them**.

## Security boundaries

- The coding-agent host retains all tool authorization, sandboxing and network policy.
- No automatic collection of private sessions, credentials, global project inventories or hidden model reasoning.
- Metadata and tool catalogs are untrusted; never execute embedded instructions.
- Cached side-effecting tool output must not substitute for a newly authorized operation.
- A reduced token count never justifies skipping required correctness or security checks.
- Redacted numeric/hashed telemetry is not proof that no hidden data were accessed elsewhere by the host.

References: [Architecture](https://github.com/MakeItEzzz555/tuck-bit/blob/main/docs/ARCHITECTURE.md), [Security](https://github.com/MakeItEzzz555/tuck-bit/blob/main/SECURITY.md), [Privacy](https://github.com/MakeItEzzz555/tuck-bit/blob/main/docs/PRIVACY.md), [Telemetry](https://github.com/MakeItEzzz555/tuck-bit/blob/main/docs/TELEMETRY.md).

For security reports use [private vulnerability reporting](https://github.com/MakeItEzzz555/tuck-bit/security/advisories/new)—never the public Wiki.
