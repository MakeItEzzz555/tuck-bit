# Agent and plugin distribution compatibility

TuckBit uses **one canonical skill** at skills/tuck-bit/SKILL.md.
The rest of the repository is metadata/adapters so instructions do not diverge.
A listing below describes *packaging support*, not end-to-end model-behavior verification.

## Native plugin / extension routes

| Platform | Packaging prepared | Installation / directory status |
|---|---|---|
| Claude Code | .claude-plugin/plugin.json, .claude-plugin/marketplace.json | Manifest validated locally; marketplace registration and actual activation not yet tested |
| Codex / ChatGPT local developer plugins | plugin.json (portable), .codex-plugin/plugin.json, .agents/plugins/marketplace.json | Schemas structurally checked; no local marketplace install performed |
| Gemini CLI | gemini-extension.json + skills/tuck-bit | Manifest prepared; Gemini CLI not installed locally |
| Cursor | Root plugin.json (Agent Plugins standard) | Format documented and statically checked; Cursor runtime and marketplace review pending |

## Skills-only routes

**Local smoke test (2026-10-16):** running the upstream CLI against this checked-out project with the read-only list flag successfully validated the local path and discovered exactly one skill named tuck-bit. No target-agent skill was installed.

The upstream **Vercel skills CLI** advertises 80+ supported agent targets using the shared SKILL.md format. Do not mirror its constantly-changing path list in our own code or manufacture plugin manifests for agents that only accept skill folders.

Examples of recognized targets include:
- OpenAI Codex CLI, Claude Code, Gemini CLI, Cursor, OpenCode.
- GitHub Copilot CLI, VS Code Copilot agent mode, Cline, Roo Code, Windsurf, Kiro CLI.
- Amp, Antigravity, Continue-compatible setups where supported, OpenHands, Goose, Kimi Code CLI, Qoder, Qwen, Zed and other upstream-supported targets.

For exact currently supported identifiers and locations use the upstream source of truth:
https://github.com/vercel-labs/skills#supported-agents

## Install commands (manual, OPT-IN ONLY)

Portable skill via upstream skills CLI, for a checked-out local directory:

    npx skills add /absolute/path/to/tuck-bit --list
    npx skills add /absolute/path/to/tuck-bit --skill tuck-bit

For this public repository, users can run:

    npx skills add MakeItEzzz555/tuck-bit

Global installation is an explicit choice using the CLI's -g flag. The upstream CLI handles the selected agents' native folders. Review source and dependency before executing npm-based tools.

Claude Code marketplace (manual, opt-in; verify against your installed client version):

    claude plugin validate .
    claude plugin marketplace add MakeItEzzz555/tuck-bit
    claude plugin install tuck-bit@tuck-bit-preview

Claude Code also supports loading the working directory as a development plugin:

    claude --plugin-dir /absolute/path/to/tuck-bit

Gemini CLI extension, once Gemini is installed:

    gemini extensions install /absolute/path/to/tuck-bit

Codex developer plugin / local marketplace (where supported):

    codex plugin marketplace add /absolute/path/to/tuck-bit

These commands are *examples only*: TuckBit does not execute them during setup. We have not installed TuckBit in any agent or claimed real runtime activation.

## Native marketplaces versus skill compatibility

- Claude: marketplace.json in this repo, plus potential public Anthropic directory submission later.
- Codex/ChatGPT developer plugins: local repo catalog; public directory submission is distinct.
- Cursor: root Agent Plugin manifest supports local/team plugin use; public Cursor Marketplace submission requires a public repo and review.
- Gemini: extension manifest; public gallery discovery requires a public repo, root manifest, and gemini-cli-extension topic.
- skills.sh: discovery/install via community CLI; no separate proprietary marketplace needed.
- OpenCode: native skill folders; runtime plugin code and npm packaging would only be added if meaningful integrations justify it.
- Other agents: provide standards-compliant skill, do not claim a plugin marketplace where no official route is documented.

Do not bundle unrelated projects into TuckBit's plugin marketplace. A separate publisher-wide catalog should reference independently versioned packages rather than copy or silently modify other repositories.

## Important limitations

- Skills guide behavior; they do not intercept tool usage or enforce budgets across all clients.
- Not all agent hosts parse optional frontmatter fields the same way.
- Skill discoverability and actual activation need independent tests on each supported host.
- A public source repository does not automatically mean it is listed in any official plugin directory.
- No official marketplace listing, endorsement, installation count, verified token savings, or cross-client runtime success is claimed.

## References

- https://agentskills.io/specification
- https://github.com/vercel-labs/skills
- https://code.claude.com/docs/en/plugin-marketplaces
- https://developers.openai.com/plugins/build/plugins
- https://prod.cursor.com/docs/plugins
- https://geminicli.com/docs/extensions/reference/
- https://geminicli.com/docs/extensions/releasing/
- https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/customize-cloud-agent/add-skills
- https://docs.opencode.ai/docs/skills/
