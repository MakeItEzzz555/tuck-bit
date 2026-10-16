# TuckBit product roadmap

## Phase 1 — portable foundation (started)

- [x] Private source directory and Git repository
- [x] Canonical portable skill, six core module playbooks plus task/workflow references, four enabled default modules
- [x] Basic Claude Code plugin manifest
- [x] Config precedence inspector, local doctor command and tests
- [x] Initial research, architecture and security notes
- [x] Add portable plugin, Claude marketplace, Codex marketplace and Gemini extension manifests with one canonical SKILL.md
- [x] Build compatibility matrix and generated manifest consistency checks
- [x] Validate Claude marketplace and real skills CLI copying/instruction rendering without an AI model
- [ ] Test real model-driven skill activation and quality on available native coding-agent clients
- [x] Add a reversible project/global installer with conflict refusal, explicit backups, integrity checks and failure rollback
- [ ] Versioned sample configurations and useful task templates
- [x] Add opt-in, no-model task-contract planner with declarative host profiles
- [x] Document provider-specific execution policies, based on official documentation and earlier local implementation skill
- [x] Add deterministic Fast/Standard/Deep router with independent Parallel/Continuous/Review candidates
- [x] Add opt-in, unregistered Claude/Gemini prompt-entry hook prototypes and negative-trigger tests
- [x] Add reproducible no-model routing scenarios and README product overview
- [ ] Test optional prompt-entry hooks in actual Claude/Gemini client sessions with user-approved settings
- [ ] Native active-context and tool-availability adapters, strictly permission-aware (opt-in)
- [x] Add explicit-input local skill/MCP metadata registry, search and freshness checks (proof-of-concept)
- [x] Add redacted numeric/hashed trace profiler and optional routing observations (proof-of-concept)
- [ ] Establish real provider telemetry adapters, benchmark harness and quality-controlled baseline
- [ ] Run real client integration tests without burning large model allowances

## Phase 2 — on-demand capability indexing

- [x] Proof-of-concept safe local skill/MCP metadata registry, SHA freshness and deterministic candidate search.
- [ ] Broader provider-native metadata adapters and revocation-aware live discovery, with explicit authorization and accuracy benchmarks.
- [ ] Make registry/profiler CLI available to standalone skill users via independently tested optional distribution (no duplicate codebase).
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
