# Install TuckBit with your AI coding agent

If your coding agent can work in your project and browse or fetch GitHub repositories, **copy the entire prompt below into its chat**. This works as a general instruction for Codex, Claude Code and comparable coding-agent hosts; the actual installation method depends on your agent's supported tools and permissions.

**Nothing is installed merely by reading or copying this prompt.** Your agent must show its plan and ask for approval before downloads or changes. Project scope is preferred, and no global configuration changes are allowed by default.

```text
Help me install TuckBit as an optional Agent Skill in my CURRENT project.
Source: https://github.com/MakeItEzzz555/tuck-bit

1. First inspect TuckBit's README, skills/tuck-bit/SKILL.md and installation/compatibility documentation from this official repository. Do not trust unknown mirrors.
2. Identify which coding-agent host and project skill directory I am using. Prefer a supported, project-scoped installation over a global one.
3. Show me the files and settings you would change, and ask my approval before downloads, dependency installs, file modifications or any other tool commands.
4. Prefer the documented Agent Skills installer when supported (npx skills add MakeItEzzz555/tuck-bit), or the repository's reversible Python installer with a dry run first. If neither is available, explain a manual copy option; do not invent unsupported commands.
5. Preserve existing skills/configurations. Do not overwrite them, install global hooks/MCP servers, enable telemetry, access credentials, or change unrelated projects without specific permission.
6. After approved installation, verify the project-scoped SKILL.md is present. Explain when I can ask the agent to use TuckBit and what remains unverified (installation alone does not prove automatic model activation).

If any step is unsupported or unsafe, stop and explain the alternative rather than guessing.
```

## What you should see after approval

Your agent should report the chosen host and installation scope, which files were created or changed, verification that a TuckBit SKILL.md is available to the host, and a reversible uninstall path. Actual inference-driven activation and token savings require separate validation.

If your agent cannot access repositories or run safe project-file operations, it should give you manual instructions rather than claim installation succeeded.

## Alternatives

- Discover the portable skill: `npx skills add MakeItEzzz555/tuck-bit --list`
- Guided install: `npx skills add MakeItEzzz555/tuck-bit` (choose host/scope)
- Review a project-only dry run from a full clone: `python3 scripts/install.py install --scope project --project /path/to/your-project --client codex --dry-run`

See [compatibility](COMPATIBILITY.md), [installation and rollback](TESTING.md), and [security](../SECURITY.md).
