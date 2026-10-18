# Agent Compatibility

TuckBit provides a **portable skill** plus optional host-specific packaging and local Python utilities. A host accepting a manifest is not the same as a model choosing to read and apply it.

| Host | Public repository integration | Important qualification |
|---|---|---|
| Codex | Agent Skills directory + optional preview manifest | Skill discovery and task-level native use require separate validation |
| Claude Code | Skill + plugin/marketplace manifest | Strict structural validation is not a claim of inference-time behavior |
| Gemini CLI | Skill + extension metadata / opt-in hook example | Experimental adapter must be enabled explicitly |
| Cursor | Agent Skills/plugin packaging | Do not assume identical behavior across editor versions |
| OpenCode | Agent Skills path | Provider behavior and authorization remain host-specific |
| GitHub Copilot | Agent Skills path | Local presence does not imply a hosted/cloud agent read the skill |

See the maintained [compatibility matrix and exact commands](https://github.com/MakeItEzzz555/tuck-bit/blob/main/docs/COMPATIBILITY.md).

## Two things to verify separately

1. **Installation:** Is the TuckBit skill placed under an authorized host/project directory, and can the host discover it?
2. **Activation:** Is there supported, public evidence that the agent actually read the instructions for the task? Further compliance must be assessed through observable behavior and independent checks.

Do not modify native host permissions to make a skill appear activated. Project scope is the safer starting point; global installs and hooks are opt-in.

See [[Getting Started]] and [[Troubleshooting]].
