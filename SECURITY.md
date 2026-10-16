# Security and privacy

TuckBit is a **guidance skill**, not a sandbox or an authority to bypass host approval.

- Never store credentials, private tool-output transcripts, connection secrets or API keys in the skill index.
- Third-party MCP metadata is untrusted. Do not execute commands embedded in catalog entries.
- Every live tool execution must use the provider's original authentication and approval flow.
- Never replay a side-effecting tool result from cache in lieu of an authorized operation.
- The read-only CLI does not install hooks, start servers, access network, or invoke AI agents.
- Future log analysis must be opt-in and redact potentially sensitive data before writing reports.
- Never reduce required correctness or security checks to hit a token budget.
- Treat first-party and provider policy as stronger than local skill configuration.

## Installer behavior

The installer modifies only an explicitly selected scope. Project is the default; global requires a flag. Existing skill folders cannot be replaced unless the user supplies --replace, which saves a recoverable backup. Managed file modification, symlink ancestor detection and state mismatch cause a fail-closed error. It never starts a model, changes provider permission settings, or registers external MCP servers. Untrusted home/project directories and simultaneous manual filesystem changes are outside the installer threat model; review all pending changes before invoking it on important files.

## Task-plan preview

The experimental task planner reads only a JSON task file explicitly provided by its caller; it does not scan hidden agent instructions, other projects, or global user configuration. The JSON includes the full request and constraints, so its printed output can contain sensitive user text. Do not log, publish, or upload task-envelope output without consent. Host profiles are advisory and do not inspect model reasoning, change reasoning settings, or authorize tools.
