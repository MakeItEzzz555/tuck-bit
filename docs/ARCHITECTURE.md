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
