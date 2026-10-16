# TuckBit product roadmap

## Phase 1 — portable foundation (started)

- [x] Private source directory and Git repository
- [x] Canonical portable skill, six reference playbooks, four enabled default modules
- [x] Basic Claude Code plugin manifest
- [x] Config precedence inspector, local doctor command and tests
- [x] Initial research, architecture and security notes
- [x] Add portable plugin, Claude marketplace, Codex marketplace and Gemini extension manifests with one canonical SKILL.md
- [x] Build compatibility matrix and generated manifest consistency checks
- [ ] Verify native skill/plugin activation and packaging against current Claude, Codex, Gemini, Cursor and skills CLI clients
- [ ] Add reversible global/project installer with backups, explicit approval and conflicts checks
- [ ] Versioned sample configurations and useful task templates
- [ ] Establish benchmark harness, privacy-sensitive telemetry and quality baseline
- [ ] Run real client integration tests without burning large model allowances

## Phase 2 — on-demand capability indexing

- Safe local skill/MCP metadata registry, freshness and revision checks, per-host selective discovery.
- Review and migrate useful code from earlier LeanHarness preview rather than blindly copying it.
- Keep existing native tool search as the preferred execution route.

## Phase 3 — context and evidence optimization

- Scoped task packets and deterministic checkpoint store.
- Tool-output summarization with source references.
- Change-aware validation plans, artifact caching where safe.

## Phase 4 — orchestration and continuous workflow

- Optional dependency-aware agent delegation, ownership, compact receipts.
- Optional event-triggered loops, bounded budgets, retry/stop rules and telemetry.

## Phase 5 — public beta, website and growth

- Repeatable measured outcomes, independent users, docs portal, GitHub releases and installation.
- Public marketing and video only after validated feature claims.
- Optional creator funding, community contribution workflows.

## Distribution decisions

We should **not** create a marketplace as a prerequisite for one plugin. TuckBit stays independently installable. Architect-Agent-Superpowers already has its own Claude plugin marketplace. A separate, shared publisher catalog is a future optional project: list both independently versioned releases after reviewing author permissions and manifest rules.
