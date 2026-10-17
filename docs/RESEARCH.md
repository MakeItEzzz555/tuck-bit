# TuckBit — research and evidence boundaries

This public document summarizes technical assumptions, not any contributor's computer setup, account configuration, local project inventory or private work.

## Primary references

- Agent Skills specification: https://agentskills.io/specification
- Claude Code skills and plugins: https://code.claude.com/docs/en/skills
- Claude Code marketplaces: https://code.claude.com/docs/en/plugin-marketplaces
- Codex skills: https://developers.openai.com/codex/skills
- Gemini CLI extension reference: https://geminicli.com/docs/extensions/reference/
- MCP tool specification: https://modelcontextprotocol.io/specification/2025-11-25/server/tools
- Community skills installer: https://github.com/vercel-labs/skills

## Documented behavior versus hypotheses

A portable skill is an instruction package. It cannot independently intercept every tool, read hidden host instructions, inspect private chain-of-thought or override permissions. Stronger controls need explicitly authorized, supported runtime integration.

Subagents generally have separate model contexts and may redundantly retrieve evidence from a shared repository. That creates an optimization opportunity, but delegation can also increase total tokens and integration overhead.

Some hosts already offer native on-demand tool discovery, skill activation and prompt caching. TuckBit should use existing host facilities where possible, not duplicate them without a measured benefit.

The sample traces and routing scenarios here are synthetic. A credible performance claim requires comparable real tasks, correct final results, privacy-preserving measurement and repeated trials.

See [provider research](PROVIDER_EXECUTION.md), [metadata registry](CAPABILITY_REGISTRY.md), and [trace methodology](TELEMETRY.md).
