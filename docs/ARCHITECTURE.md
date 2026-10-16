# TuckBit architecture — Phase 1 contract

## Components

1. Portable skill: one concise entrypoint plus on-demand references, canonical source of truth.
2. Claude plugin: a compatible wrapper with no background hooks or permissions.
3. Read-only CLI: show effective user/project/session profile and detect missing files.
4. Future registry: index nonsecret tool and skill **metadata**, not credentials or executable output; deduplicate lookups and invalidate schemas.
5. Future context compiler: build minimal task packets from exact evidence references, contracts, files and tests.
6. Future optional controller: enforce or advise budgets and safe retries only with explicit host-supported hooks.

## Precedence

Runtime/system permissions > explicit user instructions > session policy > project policy > global policy > default policy. The policy inspector reads JSON from project/.tuck-bit/config.json and ~/.tuck-bit/config.json when present, with session overrides as CLI flags. It never rewrites provider configuration.

## Supported interfaces

Portable Agent Skills specification for reusable core; Claude Code plugin packaging as optional distribution. Later Codex and Gemini adapters must be documented and tested against live versions before claiming support for installation.

## Safety

Tools execute through their original permission mechanisms. Skill content is behavioral advice, not security enforcement. Cached tool schemas must have an identity, provenance and freshness. Changing or dangerous calls must never be replayed from result caches.

## Scope

Source under this repo only. No global modifications; no changes to Architect-Agent-Superpowers or DynamicIsland; no automatic model invocation. Performance targets require A/B evaluation against correct outcomes.

## Task-conditioned planning — experimental Phase 1 addition

\`scripts/plan_task.py\` compiles an explicitly provided JSON task contract using \`skills/tuck-bit/assets/hosts.json\` to select a small host-specific strategy. The full request, constraints, mandatory checks and user-provided tool names remain explicit. This read-only preview cannot observe private model reasoning, determine provider-level permissions, or confirm which host instructions were injected. It has no hooks and does not silently open local global instructions. Automatic per-turn adaptation requires a separately approved provider-native integration and behavior benchmarks.

## Phase 2 metadata registry proof-of-concept

The optional `scripts/capability_registry.py` reads only explicitly specified skill roots and a caller-supplied tool-metadata file. It stores only name, description, opaque schema/file hashes and relative source references. Native discovery and authorization remain authoritative. The router can receive a snapshot via `--registry-snapshot` and suggest matches; matches are not automatically executed. No MCP server connection or global scan is made.

## Phase 1 telemetry contract proof-of-concept

`scripts/trace_profiler.py` accepts structured numeric/hashed events with an explicit verified outcome and produces aggregate, descriptive statistics. Raw prompts/tool outputs and other unapproved fields are rejected. The router can accept a trace via `--trace` and reflect visible repeated calls and large outputs as advisory notes, without modifying user requirements. The profiler is not a native session parser, cost oracle or verified savings benchmark.
