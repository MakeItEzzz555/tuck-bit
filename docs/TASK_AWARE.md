# TuckBit task-aware execution design

## What the user is asking us to build

A **task-conditioned efficiency layer** that adapts its method to the current request, constraints, available capabilities and agent runtime. The goal is equivalent or better verified outcomes with fewer unnecessary reads, calls, build loops and delegated-agent turns.

This is not a universal prompt rewriter, a source of privileged instructions, or access to private model deliberation.

## Inputs and provenance

| Input | Available to the actual agent? | Available to local CLI preview? |
|---|---|---|
| User request and follow-ups | Yes, as delivered by the host | Only if explicitly supplied in task JSON |
| Global/project/session instructions | When the host loads them | Explicit reference strings only; files are not read |
| System/developer instructions | Subject to runtime delivery and visibility | Not accessible |
| Available tools and permissions | Via provider runtime | Only explicitly declared tool names; permissions not checked |
| Skills and MCP metadata | Via native discovery/activation | Only declared tools; future registry |
| Private chain-of-thought | Not accessible to TuckBit | Not accessible |
| Tool-call outcomes and usage telemetry | Where authorized and exposed | Not collected in current prototype |

**Precedence:** the actual runtime/system and developer policies always win. TuckBit may optimize *within* those boundaries, but cannot detect or reorder hidden policies. Untrusted tool descriptions must never become instructions.

## Minimal external task contract

Task files are authored explicitly as JSON. The `request` and `constraints` fields are preserved verbatim and the plan computes a request hash.

- `request`: full user task as provided to the planner.
- `constraints`: explicit nonnegotiable requirements and prohibitions.
- `checks`: stated acceptance and mandatory validation checks.
- `host`: codex, claude, gemini, cursor, opencode, copilot or generic.
- `model`: optional display label, not used to infer hidden reasoning.
- `tools`: tools declared available by the caller.
- `needed_tools`: tools the caller requests; unknown tools remain unresolved.
- `instruction_references`: user-provided string references, **not** file contents.
- `risk`: normal or high, explicitly supplied rather than guessed.
- `parallel`, `continuous`: explicit requested modes, reported as candidates.

Example, using the checked-in sample:

```bash
python3 scripts/plan_task.py examples/task-contract.json
```

Use `--output /path/to/new-file.json` only if persistent output is wanted. The script refuses to overwrite an existing output. By default the envelope is printed to the terminal, and no model is invoked.

## Agent runtime adaptation

**Codex:** short task contract, AGENTS.md as loaded by Codex, provider-native skill/tool discovery, explicit acceptance criteria, and limited parallelism. Respect the user's/model's chosen reasoning setting.

**Claude Code:** CLAUDE.md as actually loaded, native tool search, optional subagents with isolated task packets and focused reports. Don't spawn additional workers for small changes.

**Gemini CLI:** GEMINI.md and activation consent, available hook lifecycle, and opt-in context injection only when authorized. Do not install hooks implicitly.

**Other hosts:** rely on standard portable skill instructions and verified host capabilities. Unsupported assumptions default to conservative behavior.

TuckBit may **adapt to visible effects of reasoning**, such as failed attempts, repeated tool results, task completion rate and measured cost. It cannot read the model's private thought process; no profile may promise that.

## Future implementation milestones

1. Consent-based host adapter obtains only explicitly exposed active instruction provenance and available tool metadata.
2. Task intent extraction and requirements audit against the original prompt, with mandatory quality evaluation on negatives and ambiguities.
3. Context selection from referenced evidence and native tool discovery.
4. Adaptive budget controller informed by structured, privacy-redacted telemetry, not untested model stereotypes.
5. Repeated A/B tests comparing correct outcomes before/after the layer under equivalent tasks.

This roadmap intentionally does **not** ask to reveal hidden chain-of-thought or bypass provider permissions.

## References

- https://developers.openai.com/blog/rethinking-skills-and-prompts-for-gpt-6-astra
- https://developers.openai.com/plugins/concepts/skills
- https://geminicli.com/docs/cli/skills/
- https://geminicli.com/docs/hooks/reference/

## Completed subsequent prototype work

A deterministic workflow router now selects Fast/Standard/Deep based on declared risk, complexity and observed tool/test behavior. Parallel work requires opt-in and separate owned files; recurring work requires an explicit event trigger and checkpoint. Optional Claude/Gemini prompt-entry hook prototypes are implemented but not registered globally. Both are advisory, cannot inspect private reasoning, and are **not** equivalent to native model-driven activation. See [provider study](PROVIDER_EXECUTION.md) and [hook details](HOOKS.md).
