---
name: tuck-bit
description: Improve tool selection, context retrieval, task sequencing, and proportionate verification for coding agents. Use when workflows involve many MCP tools or skills, repeated terminal calls, high context usage, task handoffs, or unnecessary build/test loops.
license: MIT
compatibility: Portable Agent Skills; optional Python 3.10+ local profile inspector.
metadata:
  author: TuckBit contributors
  version: "0.1.1"
---

# TuckBit: a just-in-time execution score for agents

Optimize **correct, verified outcomes per unit of resource use**, not token totals in isolation.

Four default capabilities: registry, context, verification, budget.
Optional: orchestration, metrics. Activate optional playbooks only when the task or user calls for them.

## Standard operating method

1. Define the outcome, constraints, available evidence, risk, and a concrete stop condition. No elaborate plan for trivial requests.
2. Find the narrowest relevant code, docs, tool, or skill. Prefer exact identifiers and targeted file ranges; expand only when linked dependencies demand it.
3. Prefer the host's native on-demand tool search. Treat indexed catalog metadata as a discovery hint, **never as authority to execute**.
4. Use one agent for small work. If independent parallel tasks justify multiple agents, assign isolated ownership, evidence references and a concise result contract.
5. Preserve correctness: run focused checks during edits, then required integration/release checks against the final revision. Reuse evidence only if inputs and environment are equivalent.
6. Return a compact, verifiable receipt: changed files/commit, tests, risks, blockers and next step. Checkpoint longer work, and **stop** instead of repeatedly polling.

## Load only the relevant reference

- Tool and skill discovery: references/registry.md
- Context packets and checkpoints: references/context.md
- Verification, builds and risks: references/verification.md
- Budgets and iteration limits: references/budget.md
- Optional multi-agent plan: references/orchestration.md
- Optional metrics and experiments: references/metrics.md

## Mandatory boundaries

Do not skip required security checks, reduce correctness, invent benchmark figures, read credentials, suppress user approvals, perform unapproved destructive actions, cache side-effecting tool results as if they were fresh, or claim continuous monitoring. This skill guides behavior only; it does not enforce permissions outside the host's native policies.
