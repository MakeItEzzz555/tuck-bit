# Phase 1 research pointers (2026-10-16)

Primary specifications to validate during implementation:

- Agent Skills: https://agentskills.io/specification
- Claude Code plugins: https://code.claude.com/docs/en/plugins
- Claude Code marketplaces: https://code.claude.com/docs/en/plugin-marketplaces
- Codex skills: https://developers.openai.com/codex/skills
- GitHub private repository CLI: https://cli.github.com/manual/gh_repo_create

## Findings

- A portable skill's advice cannot intercept or enforce arbitrary tool calls. Runtime integration is optional, provider-specific, and may have additional context overhead.
- Installed MCP tool definitions can be expensive, but some providers already offer native deferred loading. Do not duplicate native capabilities without empirical benefit.
- Parallel agent contexts are separate; each worker may independently reread shared files and project instructions. Task-local context and external evidence receipts reduce duplication.
- Effective optimization measures cost per verified successful task, not absolute token reduction.
- A marketplace catalogs plugins for distribution; it is not automatically a runtime orchestrator.
- DynamicIsland historical workflows showed many repeated log views, terminal queries, and test calls, but not every repeat was waste. Controlled task benchmarks should separate necessary checks from redundant work.

## Mac inspection

The user's Mac had Git, GitHub CLI, Python, Node, Claude, Codex. GitHub CLI authenticated as MakeItEzzz555.
Architect-Agent-Superpowers already had a .claude-plugin/marketplace.json and dirty worktree. We leave it unchanged.
