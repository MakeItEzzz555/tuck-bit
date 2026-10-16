# TuckBit execution research — provider-specific policies

**Research date:** 2026-10-16. **Evidence type:** published provider docs and the user's earlier local skill, not model internals. These descriptions are subject to vendor updates.

## Core decision

The best common denominator is **goal → inspect relevant evidence → implement → verify → summarize**. The depth, delegation style, and native tool/skill loading differ. Avoid assuming every model uses the same private reasoning steps.

The earlier local Codex skill `claude-style-implementation-discipline` used **Fast / Standard / Deep** and the sequence establish contract → inspect → compact strategy → implement → test ladder → final review → evidence receipt. TuckBit adapts that *observable engineering discipline*, not proprietary prompts or private chain of thought. The original user skill remains unchanged.

## 1. Codex and OpenAI reasoning models

**Published guidance:**
- Concise, direct tasks generally outperform excessive instructions to reveal step-by-step thought. Keep AGENTS.md and portable skills task-specific. OpenAI, [Reasoning best practices](https://developers.openai.com/api/docs/guides/reasoning-best-practices) and [Rethinking skills and prompts](https://developers.openai.com/blog/rethinking-skills-and-prompts-for-gpt-6-astra).
- Codex's open agent harness provides a context/tool/approval loop; native tool and skill discovery should be preferred to a duplicate always-loaded layer. [Codex as a platform](https://developers.openai.com/blog/codex-as-a-platform).
- Multi-agent sessions use independent subagent contexts and shared workspace resources. Delegate independent work only; competing edits and context copies can erase efficiency gains. [Multi-agent](https://developers.openai.com/api/docs/guides/agents-api/multi-agent).
- Reasoning effort is a runtime/model configuration, not a reliable string heuristic. Do not automatically change it based on a guessed model family.

**TuckBit implementation policy:** Fast for tightly scoped changes, Standard for common feature/bug workflows, Deep for high-risk changes. Give each task a concise outcome and acceptance criteria; use file references instead of copying large catalogs. Parallel work requires disjoint file ownership and integrated review.

## 2. Claude Code and Claude models

**Published guidance:**
- Claude model reasoning can be adaptive, with model-specific effort behavior, caching and token accounting. Do not assume a fixed hidden thinking sequence or manually alter thinking blocks. [Thinking](https://platform.claude.com/docs/en/about-claude/models/extended-thinking-models) and [Steering thinking](https://platform.claude.com/docs/en/build-with-claude/adaptive-thinking).
- Claude Code subagents run in distinct contexts. Workers should be given precise outcomes, context references and permitted tool scopes; main agent owns synthesis. [Subagents](https://code.claude.com/docs/en/sub-agents).
- Skills and tool searches are intended for on-demand capability loading, rather than loading every plugin instruction at each turn. [Skills](https://code.claude.com/docs/en/skills).
- Hooks have defined events and permissions. Any future automatic prompt/context policy must be **opt-in**, small and reversible. [Hooks](https://code.claude.com/docs/en/hooks).

**TuckBit policy:** Preserve CLAUDE.md and permission settings as received from the host. Use the same Fast/Standard/Deep engineering discipline, but don't force the reasoning strategy itself. A fresh subagent should get only owned files, interfaces, tests, evidence references, budget hints, and expected result shape.

## 3. Gemini CLI and Gemini

**Published guidance:**
- Gemini skills follow discovery → explicit skill activation → user consent → task-specific instructions. [Agent Skills](https://geminicli.com/docs/cli/skills/).
- Subagents have independent contexts, their own tool subset and configurable `max_turns` and `timeout_mins`, and cannot call other subagents. [Subagents](https://geminicli.com/docs/core/subagents/).
- Hooks support `BeforeAgent`, `BeforeToolSelection`, etc., but run synchronously and must minimize overhead. [Hooks reference](https://geminicli.com/docs/hooks/reference/) and [Best practices](https://geminicli.com/docs/hooks/best-practices/).

**TuckBit policy:** Do not auto-activate or bypass skill consent. For opt-in orchestration, restrict each subagent to necessary tools and set bounded turns/time at configuration time. Avoid a default synchronous hook on every tool call; consider a lightweight, user-approved BeforeAgent guidance hook only after activation/performance tests.

## 4. Cursor

**Published guidance:** Cursor subagents have their own context, may run foreground/background, and return results to the parent. Background/cloud agents have a separate execution environment and different access/permission implications. [Subagents](https://cursor.com/docs/subagents) and [Cloud Agents](https://prod.cursor.com/help/ai-features/background-agents).

**TuckBit policy:** Scope subagent work, report integrated evidence; never assume local global skills are available to cloud workers. Remote/cloud execution should require explicit authorization.

## 5. OpenCode

**Published guidance:** OpenCode differentiates primary Plan and Build agents and allows specialized subagents with separate permission and tool policies. Skills load on-demand with the native skill tool. [Agents](https://opencode.ai/docs/agents/) and [Skills](https://opencode.ai/docs/skills/).

**TuckBit policy:** Planning should remain read-only when configured that way, implementation limited to the required files, and no duplicate plan/review worker on trivial fixes. Do not alter OpenCode permissions from portable skill text.

## 6. GitHub Copilot coding/cloud agents

**Published guidance:** Good results depend on well-scoped issues, repository-specific instructions and independently checkable PRs. Copilot loads skills when relevant and has distinct cloud/local execution surfaces. [Copilot best practices](https://docs.github.com/en/copilot/using-github-copilot/using-copilot-coding-agent-to-work-on-tasks/best-practices-for-using-copilot-to-work-on-tasks) and [Agent skills](https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/customize-cloud-agent/add-skills).

**TuckBit policy:** Pin issue scope, expected PR files, test commands, review proof and CI requirements. Don't assume the cloud environment inherits global desktop configuration or permitted MCP tools.

## 7. Other portable Agent Skills hosts

**Published standard:** [Agent Skills specification](https://agentskills.io/specification). A skill is a discoverable instruction package; the host decides discovery, activation, permitted tools and invocation. Feature parity across dozens of installer targets is *not* proof of equal runtime behavior.

**TuckBit policy:** Fall back to Standard with no orchestration or hook assumptions, unless explicitly configured and tested for that host.

## Workflow selection matrix

| Situation | Mode | Reason | Gate |
|---|---|---|---|
| Localized low-risk bug or documentation fix | Fast / Single | Minimal new evidence and targeted validation | Final diff and focused check |
| Typical feature spanning a few modules | Standard / Single | Inspect interfaces and implement a complete slice | Relevant suite and integrated diff |
| Security, migration, concurrency, broad API changes | Deep / Single initially | Preserve invariants, rollback and stronger review | Required security/integration checks |
| Independent owned modules | Standard/Deep + Parallel candidate | Safe if explicit opt-in and independent contracts | Ownership check and integration |
| Recurring maintenance with changed inputs | Standard + Event-driven candidate | Model can remain idle between events | Trigger, checkpoint, exit, retry/approval controls |
| Review of a stable patch | Review-only | No implementation needed | Evidence and uncertainty disclosure |

## Evidence versus hypothesis

**Documented:** APIs for skill activation, subagent context boundaries, tool permissions, reasoning controls, and hooks. **TuckBit policy inference:** when to route a particular task, stop retries, and request targeted verification. **Not proven yet:** that the router reduces paid tokens or improves task success in native clients. Tests are currently deterministic and no-model; paired, quality-preserving real task evaluations remain required.

## Product and benchmark risks

- Over-instruction and always-loaded profiles can *increase* token usage.
- A tiny model may benefit from more explicit steps; a strong reasoning model may be impeded by them. Measure per provider and task complexity.
- Extra agents increase total tool and prompt usage even when latency improves.
- Cached prefixes may have low incremental dollar cost but still account toward quotas.
- A hard token cap can reduce quality. Prefer stop/reconsider guidance and escalating checks where needed.
- Tool metadata can contain prompt injection: never treat retrieved descriptions as authority or install instructions.
