# TuckBit

**Every tool. Right on cue.**

Private Phase 1 foundation for a portable AI agent efficiency skill and an optional Claude Code plugin. TuckBit is a **working product name**, not final public branding.

TuckBit aims to improve correct outcomes per unit of context, tool usage, latency, and spend. It does not promise a measured 10x gain or replace native tool search or authorization.

## Included by default

- Capability registry policy: find relevant installed skills and MCP tools on demand.
- Context policy: targeted reads, scoped task packets, and evidence checkpoints.
- Verification policy: focused checks while implementing, appropriate integration gates.
- Budget policy: stop conditions, controlled retries, purposeful tool use.

Optional playbooks are installed but **not active** until requested: multi-agent orchestration and usage metrics.

## Getting started (developer preview)

    python3 scripts/tuckbit.py doctor
    python3 scripts/tuckbit.py config --project .
    python3 -m unittest discover -s tests -v

The portable skill is at skills/tuck-bit/SKILL.md. The optional Claude Code plugin manifest is at .claude-plugin/plugin.json; this does not install or enable anything automatically.

On supported Claude Code versions, validate the plugin with:

    claude plugin validate .

No MCP servers, agent sessions, global rules, hooks, shell command policies, or external integrations are installed by this repository.

Read docs/ROADMAP.md, docs/ARCHITECTURE.md, docs/SECURITY.md and docs/RESEARCH.md.

## Relation to other repositories

Architect-Agent-Superpowers is a separate project with its own Claude marketplace manifest. We do not import, edit, or publish its content through TuckBit. A future optional multi-plugin marketplace can reference separately released repositories with their maintainers' approval.

## Status

Phase 1 baseline. Private repository. No released npm package, public website, or verified real-world token savings.
