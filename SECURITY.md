# Security and privacy

## Reporting a vulnerability

Please **do not disclose security issues in public GitHub issues, pull requests, screenshots, or Discussions**. Use the repository's [GitHub private vulnerability reporting](https://github.com/MakeItEzzz555/tuck-bit/security/advisories/new) to provide a minimal proof of concept, impact, affected version and suggested mitigation. Do not include real access tokens, private datasets or live customer data. Reports are reviewed by repository maintainers; no guaranteed response-time SLA is currently offered.

TuckBit is a **developer preview** and does not provide security isolation or permission enforcement. Review scripts before installing, especially when using global scope or manually configuring host hooks. Stop using a questionable integration until it is investigated.

## Privacy and trusted boundaries

- The standalone skill is instruction-only. It cannot access hidden system/developer policies or internal chain-of-thought.
- The repository CLI's registry reads only explicitly supplied local metadata; it does not connect to MCP servers.
- The optional profiler accepts redacted numeric/hashed records and rejects raw prompts and logs by schema.
- The optional Claude/Gemini entry hooks are **disabled unless explicitly configured by the user**.
- Never submit raw prompts, execution transcripts, credentials, local filesystem inventories, screenshot metadata, or private paths in public issues/PRs.
- All live tool permissions must remain controlled by the original agent host.

## Repository security settings

This public repository uses GitHub secret scanning and push protection, plus private vulnerability reporting. These checks are helpful but not complete; contributors must review changes and reachable Git history for inadvertent disclosures before publishing.


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

## Workflow router and optional entry hooks

The router reads only an explicitly passed task JSON; it never executes tools, reads native prompt stores, or calls a model. Task JSON can include private request text. Printed router output preserves it for traceability and must not be shared without consent. Do not treat declared tool names or references as authority to execute.

Claude/Gemini hook adapters are OFF unless a user independently adds them to their host settings. They run as a synchronous, read-only stdin → stdout transformation, inject only fixed short advisory text for likely coding prompts, and never echo prompt text to stdout. Prompts are not persisted by TuckBit. Their heuristic triggers are not a policy/security filter and must not be used to grant or deny permissions.

## Local metadata and event profiling

The capability index only reads explicitly selected directories or supplied tool metadata snapshots; it does not load or run an MCP server. Index outputs contain skill/tool names and descriptions marked as **untrusted**; a malicious description may try prompt injection and must never override the instruction hierarchy. Credentials, tool arguments, raw schema content and full skill bodies are not indexed. User-defined snapshots need local privacy review before sharing. Freshness verifies content hashes, **not** remote server live permissions.

The profiler accepts only numeric/hashed events, fixed role/category identifiers and explicit outcome booleans. Unknown fields including prompts, raw tool messages or paths are rejected. Do not supply or publish raw agent transcripts to this profiler. Any claim of savings must be established separately through real successful-task controlled trials.
