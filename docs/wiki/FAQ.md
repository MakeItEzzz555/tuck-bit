# Frequently Asked Questions

### Is TuckBit a model, coding agent or orchestration service?
No. The public preview is a portable Agent Skill and optional local tools that guide how an existing AI coding host selects relevant context, skills and verification. The host still performs and authorizes execution.

### Does installing the skill save 19% of tokens?
No such general claim is supported by the public release. Early single-task observations cannot establish repeatable, attributable savings without verified activation, matched budgets and independently checked results.

### Can I repeat a task bundle today?
**Yes, offline.** The public harness repeats three deterministic tasks in fresh worktrees across four iterations and two *identical scripted adapters*. It checks the repetition and reporting mechanism, **not AI inference**. See [[Benchmarks and Evidence]].

### Is the benchmark open to community contributions?
Yes. Contribute licensed or synthetic tasks, exact acceptance checks, full per-trial results (including failures) and sanitized receipts through [Issue #5](https://github.com/MakeItEzzz555/tuck-bit/issues/5) or the evaluation issue template.

### Does TuckBit run in the background or collect conversations?
The portable skill does not. Local commands operate on explicitly supplied files; optional hooks are disabled unless you enable them in the original host. Review the host's own privacy policy independently.

### Does it bypass permission prompts or grant access to MCP tools?
No. Provider-native tools and permissions are authoritative. Metadata discovery is not permission.

### Can I install project-local rather than globally?
Yes, and it is the recommended first experiment. Run the installer's dry-run and review any changes. See [[Getting Started]].

### Is the project production-ready?
It is a public developer preview under the MIT license. Compatibility varies by host/version; performance and security isolation are not guaranteed. See the [roadmap](https://github.com/MakeItEzzz555/tuck-bit/blob/main/docs/ROADMAP.md).
