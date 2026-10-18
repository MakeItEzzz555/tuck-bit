> **English canonical technical fallback — not translated.** Der Skill-Kern ist übersetzt; technische Referenzen bleiben vorläufig auf Englisch und benötigen Community-Review.
> Source SHA-256: `e1972922445c127b45ef4e8591c3f7df8d6c74e05d1539b7dd1a264a9b092af8`

# Optional: bounded multi-agent orchestration

Use only when independent task boundaries and expected benefit justify parallelism.

The orchestrator owns requirements, integration, dependency graph, source-of-truth state and final response. Workers do not inherit each other's model context automatically.

For each worker assign: goal; baseline commit; owned files; related contracts; evidence references; non-goals; targeted validation; stop conditions; concise handoff schema.
Prefer independent worktrees; serialize edits touching shared interfaces. Never let two workers edit the same files without an agreed plan.
Workers return commits/diffs, focused test evidence, open risks and integration requirements rather than entire transcripts.
Poll only when necessary; avoid parallel review loops without new evidence.
Escalate if a worker needs to expand scope beyond agreed boundaries.
