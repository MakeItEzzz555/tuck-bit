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

## Distribution across coding agents

TuckBit is intentionally one canonical Agent Skill with native distribution wrappers for Claude Code, Codex/ChatGPT developer plugins, Gemini CLI and Cursor Agent Plugins. Other supported coding agents can install the same skill through the Vercel skills CLI.

In a local checkout, the following command **lists** TuckBit without installing it:

    npx skills add /absolute/path/to/tuck-bit --list

Once the repository is public, the intended skills installer is:

    npx skills add MakeItEzzz555/tuck-bit

Claude Code's private preview marketplace is validated with:

    claude plugin validate .

Its manual install command, only after you register the marketplace yourself:

    /plugin install tuck-bit --marketplace MakeItEzzz555/tuck-bit

Read [the compatibility matrix](docs/COMPATIBILITY.md) for native formats, scope, auth limitations and marketplace publication requirements. No user/global installation is performed automatically.

## Free verification and reversible installation

No model request is needed to check the skill packaging, no-model client discovery, or installer rollback:

```bash
python3 -m unittest discover -s tests -v
python3 scripts/smoke_free.py --interop --claude-validator
python3 scripts/install.py install --client codex --scope project --project /path/to/project --dry-run
```

The installer supports **project or explicitly selected global scope**, with safe failure on collisions, optional backed-up replacement, tamper detection and tracked uninstall. It does not change your Mac's agent configuration unless you run an actual non-dry-run install. See [TESTING](docs/TESTING.md) for usage, client paths and the limits of no-model tests.

## Relation to other repositories

Architect-Agent-Superpowers is a separate project with its own Claude marketplace manifest. We do not import, edit, or publish its content through TuckBit. A future optional multi-plugin marketplace can reference separately released repositories with their maintainers' approval.

## Status

Phase 1 baseline. Private repository. No released npm package, public website, or verified real-world token savings.
