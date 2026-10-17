<div align="center">

# 🎼 TuckBit

### Every tool. Right on cue.

**A lightweight execution layer for AI coding agents.**

Give agents the right context, tools, and workflow at the right moment—without sacrificing correctness.

**Task-aware · Host-aware · Portable · MIT-licensed**

[Get started](#quick-start) · [How it works](#how-it-works) · [Agent support](#agent-support) · [Contribute](CONTRIBUTING.md) · [Research](docs/PROVIDER_EXECUTION.md) · [Roadmap](docs/ROADMAP.md)

</div>

---

### Your coding agent doesn't need every instrument playing at once.

One request becomes a repository-wide search. Three agents reread the same documentation. Terminal logs pile up in context. A successful test suite is run again, unchanged.

**TuckBit aims to cut the unnecessary work—not the thinking that makes good software.**

When activated, the portable skill guides an agent using the user's requirements, applicable host instructions, and authorized tools. The optional local router recommends a workflow from explicitly supplied task data and observable signals; it does not automatically intercept live sessions.

**Public developer preview (v0.1.2).** The skill, plugin packaging, reversible installer, task-contract compiler, capability registry, and workflow router exist. **Automatic tool interception, broadly verified native activation, and measured token savings are not yet available.** Contributions and independent testing are welcome.

## How it works

```text
                         YOUR REQUEST
                  + constraints and checks
                               │
                     ┌─────────▼─────────┐
                     │  Task contract    │  ← preserve original intent
                     └─────────┬─────────┘
                               │
                      ┌────────▼────────┐
                      │  TuckBit router │  ← host + risk + evidence
                      └────────┬────────┘
                               │
             ┌─────────────────┼─────────────────┐
             ▼                 ▼                 ▼
         FAST               STANDARD            DEEP
      local fix          normal feature      risky / complex
             └─────────────────┬─────────────────┘
                               │
                 ┌─────────────▼─────────────┐
                 │  Right tool, right scope │
                 │  Focused → required tests│
                 │  Evidence receipt + stop │
                 └───────────────────────────┘
```

TuckBit recommends **Single** by default. **Parallel**, **Continuous**, and **Review-only** are separate workflows, not automatic extra agents. Real runtime integrations must honor each provider's native tool permissions.

## The six capabilities

| Capability | Default | What it guides |
|---|---|---|
| **Tool discovery** | On | Find relevant skills and MCP tools *on demand*; prefer native search |
| **Context control** | On | Load targeted evidence; use compact handoffs and checkpoints |
| **Verification** | On | Test changed behavior without skipping mandatory safety/release gates |
| **Execution budgets** | On | Reconsider unproductive calls, repeated output, retries and unnecessary delegation |
| **Agent orchestration** | Opt-in | Split genuinely independent tasks by ownership and integrate results |
| **Metrics & evaluation** | Opt-in | Compare successful outcomes, context, tokens, tool calls and latency |

No background service is required for the portable skill. TuckBit does not grant itself access to credentials, private reasoning, or tools the host hasn't authorized.

## Quick start

### Option 1 — Discover the skill without installing

```bash
# Preview the skill before installing:
npx skills add MakeItEzzz555/tuck-bit --list
```

Install the standard Agent Skill with the community installer:

```bash
npx skills add MakeItEzzz555/tuck-bit
```

Review the skill and confirm the agent and installation scope before installing. The standalone skill provides instructions; optional Python registry/profiler utilities require a full source checkout.

Claude Code also has a plugin/marketplace manifest; see the [compatibility guide](docs/COMPATIBILITY.md) for manual opt-in installation. This does not imply an official marketplace listing.

### Option 2 — Use the Python preview (no AI tokens)

```bash
git clone https://github.com/MakeItEzzz555/tuck-bit.git
cd tuck-bit

python3 scripts/tuckbit.py doctor
python3 scripts/workflow_router.py examples/workflow-incident.json
python3 scripts/workflow_router.py examples/workflow-parallel.json
python3 scripts/workflow_router.py examples/workflow-loop.json
```

The router reads only the explicitly supplied JSON task. It **does not** silently read your global instructions, launch agents, change model settings, execute tools, or call an AI provider.

### Option 3 — Preview a reversible install

```bash
python3 scripts/install.py install --scope project \
  --project /path/to/your-project --client codex --dry-run
```

Six native target paths are available (Claude Code, Codex, Gemini, Cursor, OpenCode, Copilot). No global install is performed by default; real installation is an explicit separate action. [Install, rollback and testing details](docs/TESTING.md).

## Local capability index and execution profiling

The **full source checkout** now includes opt-in, read-only metadata discovery and redacted event profiling. The registry indexes only explicitly selected skill roots and optional tool catalogs; it never contacts MCP servers or activates tools. The standalone Agent Skill installation remains instruction-only: root-level Python CLI utilities are **not yet bundled** into the portable skill package.

```bash
# Index this repository's skill and a synthetic, nonsecret tool catalog.
python3 scripts/capability_registry.py build \
  --root skills \
  --tools-file examples/tool-metadata.synthetic.json \
  --output /tmp/tuckbit-preview-index.json

# Find candidates (metadata only), and ensure the snapshot is still fresh.
python3 scripts/capability_registry.py query \
  --snapshot /tmp/tuckbit-preview-index.json \
  --text "Swift regression tests"
python3 scripts/capability_registry.py verify \
  --snapshot /tmp/tuckbit-preview-index.json \
  --root skills --tools-file examples/tool-metadata.synthetic.json

# Supply a catalog and optional redacted observations to the task router.
python3 scripts/workflow_router.py examples/workflow-incident.json \
  --registry-snapshot /tmp/tuckbit-preview-index.json \
  --trace examples/trace-baseline.synthetic.json
```

A lightweight profiler compares caller-supplied numeric trace summaries without accepting raw prompts, logs, or tool arguments:

```bash
python3 scripts/trace_profiler.py compare \
  --baseline examples/trace-baseline.synthetic.json \
  --candidate examples/trace-candidate.synthetic.json
```

The trace files above are **synthetic test fixtures, not real token savings**. No user-agent session is queried. See [metadata registry](docs/CAPABILITY_REGISTRY.md) and [safe telemetry](docs/TELEMETRY.md).

## Agent support

**One canonical Agent Skill. Provider-specific policies only where the runtime genuinely differs.**

| Agent ecosystem | Distribution | Execution guidance |
|---|---|---|
| **Codex** | Portable skill + plugin/local marketplace manifests | Direct requests, scoped discovery, appropriate reasoning settings |
| **Claude Code** | Plugin + marketplace | Native tool search, adaptive effort, compact subagent handoffs |
| **Gemini CLI** | Extension + skill | Consent-based activation, bounded tools/turns for subagents |
| **Cursor** | Portable Agent Plugin/skill | Context-isolated subagents; separate local/cloud concerns |
| **OpenCode** | Portable skill | Plan/build separation, native on-demand skills, permissions |
| **GitHub Copilot** | Portable skill | Well-scoped issues, project instructions, PR/CI evidence |
| **Other Agent Skills hosts** | Standard `SKILL.md` | Conservative portable fallback |

The manifests and local skill discovery are tested, but native inference-driven activation **has not been validated** across all these clients. [Compatibility matrix](docs/COMPATIBILITY.md).

## Real-world workflow choices

<details>
<summary><strong>🔧 Small bug — Fast / Single</strong></summary>

Locate one behavior, inspect connected contracts, implement the narrowest complete fix, run the focused test, review diff and stop. Don't create a whole team for a one-line change.

</details>

<details>
<summary><strong>🧠 Authentication race — Deep / Single</strong></summary>

Preserve session invariants and rollback options; inspect ownership and data flow; implement incrementally; run required security and regression checks. An execution budget never cancels mandatory verification.

```bash
python3 scripts/workflow_router.py examples/workflow-incident.json
```

</details>

<details>
<summary><strong>🎻 Independent changes — Parallel (opt-in)</strong></summary>

Assign separate file ownership, exact deliverables and tests. Workers return evidence rather than full transcripts. The coordinator integrates and validates the result.

```bash
python3 scripts/workflow_router.py examples/workflow-parallel.json
```

</details>

<details>
<summary><strong>🔁 Recurring maintenance — Event-driven (opt-in)</strong></summary>

Require a genuine trigger, saved checkpoint and explicit authorization. An idle workflow shouldn't burn model turns polling for something to happen.

```bash
python3 scripts/workflow_router.py examples/workflow-loop.json
```

</details>

## What is actually implemented?

| Engineering milestone | Status |
|---|---|
| Canonical Agent Skill and progressive instructions | ✅ |
| Portable plugin, Claude marketplace, Codex and Gemini manifests | ✅ structural packaging |
| Reversible six-client project/global installer | ✅ tested in isolated directories |
| Declarative task-contract and workflow router | ✅ deterministic, no-model |
| Provider research and host policies | ✅ published-source grounded |
| Opt-in Claude/Gemini prompt-entry advisors | ✅ Prototype, no automatic registration |
| Local skill/MCP metadata index and freshness verification | ✅ explicit inputs, read-only |
| Redacted event profiling and router signals | ✅ explicit inputs, deterministic |
| Native tool-call interception / adaptive control | Planned — opt-in |
| Benchmarked token/cost savings without quality loss | Not yet established |
| Public marketplace listings, npm release, website | Not published |

Run all local checks at zero model-token cost:

```bash
python3 -m unittest discover -s tests -v
python3 scripts/public_audit.py
python3 scripts/sync_distributions.py --check
python3 scripts/smoke_free.py --interop --claude-validator
```

The last command may use npm/network for the public `skills` package; it still launches no language model.

## Why this isn't another orchestration framework

TuckBit is designed to **work with** native agent features instead of wrapping every task in another expensive coordination loop. It's an efficiency *policy and capability layer*, not a replacement for Codex, Claude, Gemini, or their existing skills.

It deliberately prioritizes:
- **Instructions before automation:** start from the full prompt and genuine host constraints.
- **Useful evidence over broad context:** only request more when it changes the answer.
- **One capable worker over unnecessary agents:** parallelism must justify its coordination overhead.
- **Verified quality over vanity metrics:** no made-up cost reduction graphs or “10×” claims.
- **Reversibility and local privacy:** no silent global hooks, credentials indexing or background scraping.

## Help build the next version

We'd especially value feedback from people who use **Codex, Claude Code, Gemini CLI, Cursor, OpenCode, or Copilot** on real repositories.

- Reproducible **native skill activation** reports using non-sensitive sample projects.
- Public benchmark tasks comparing equivalent *correct outcomes*.
- Reviews of install/uninstall paths, hook opt-in boundaries and untrusted skill/MCP metadata.
- Provider documentation fixes, regression tests and onboarding improvements.

**[Report a bug or feature request](https://github.com/MakeItEzzz555/tuck-bit/issues/new/choose)** · **[Browse issues](https://github.com/MakeItEzzz555/tuck-bit/issues)** · **[Join discussions](https://github.com/MakeItEzzz555/tuck-bit/discussions)**

For security vulnerabilities, use GitHub **private vulnerability reporting** rather than a public issue; see [SECURITY.md](SECURITY.md).

## Research, architecture and contribution

[Privacy](docs/PRIVACY.md) · [Capability index](docs/CAPABILITY_REGISTRY.md) · [Profiler](docs/TELEMETRY.md) · [Provider execution research](docs/PROVIDER_EXECUTION.md) · [Opt-in hook adapters](docs/HOOKS.md) · [Task-aware design](docs/TASK_AWARE.md) · [Architecture](docs/ARCHITECTURE.md) · [Roadmap](docs/ROADMAP.md) · [Security](SECURITY.md) · [Tests](docs/TESTING.md) · [Contributing](CONTRIBUTING.md)

TuckBit is **public and MIT-licensed**, but remains an early developer preview. Contributions, issue reports and reproducible experiments are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md), the [public roadmap](docs/ROADMAP.md), and [SECURITY.md](SECURITY.md) before sharing logs or code.

---

<div align="center">

**TuckBit — make every tool call count.**

*Not fewer checks. Fewer wasted moves.*

</div>
