# TuckBit — public roadmap

**Status: open-source developer preview.** TuckBit helps AI coding agents choose relevant tools, context and execution strategies while preserving correctness, required tests and host permissions.

This is a **directional** roadmap—not a promised release schedule. The detailed engineering delivery plan lives in a separate private planning workspace. Please propose changes through [Issues](https://github.com/MakeItEzzz555/tuck-bit/issues) and [Discussions](https://github.com/MakeItEzzz555/tuck-bit/discussions).

## Available today (preview)

- Portable Agent Skill with progressive instructions and four default policies: discovery, context, verification and budgeting.
- Multi-agent plugin and extension manifests, a reversible project/global skill installer, and static compatibility checks.
- Task-aware guidance and deterministic Fast / Standard / Deep routing; independent parallel and event-driven workflows are advisory opt-in candidates.
- Local read-only skill/tool **metadata** discovery with explicit source paths and freshness checks.
- Redacted numeric event profiling from explicitly supplied files; synthetic example traces.
- Optional Claude/Gemini prompt-entry hook prototypes. They are **not enabled or installed automatically**.
- Unit tests and deterministic policy evaluations.

These features do **not** yet prove real token savings, automatically intercept tool calls or guarantee native activation across all clients.

## Next: trustworthy compatibility and benchmarks

- Test native skill activation for supported coding agents using disposable projects and approved permissions.
- Improve install/uninstall and compatibility documentation across host versions.
- Build reproducible, publicly shareable baseline-versus-TuckBit trials. Compare verified success, cached/uncached input, total spend where measurable, unnecessary calls, latency and safety regressions.
- Accept independent community benchmark results and corrections.

## Next: better context and tool discovery

- Add permission-aware provider adapters for currently available tool metadata, with cache invalidation and revocation checks.
- Support compact evidence-linked context packets, scoped work handoffs and durable checkpoints.
- Explore safe large-output reduction while retaining original evidence and mandatory verification.
- Package optional CLI tools for standalone skill users when portable distribution is properly tested.

## Later: optional orchestration and continuous workflows

- Independent subagent assignments with disjoint ownership, handoff contracts and integrated validation.
- Event-driven resumability, bounded retries, explicit stop conditions and consent-based execution.
- Additional agent-specific workflows only when benchmark data justifies their maintenance and complexity.

## How to contribute

Check [CONTRIBUTING.md](../CONTRIBUTING.md), [compatibility](COMPATIBILITY.md) and [security](../SECURITY.md). A useful contribution includes a minimal reproducible case, exact host/version, expected result and **sanitized** supporting evidence.

We do not claim specific cost or token reduction percentages, access to hidden reasoning, or publication in every agent marketplace.
