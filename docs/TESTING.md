# Free testing and safe installation

Research and local validation date: 2026-10-16.

## Recommended free test ladder

**Level 1: No-model unit and rollback tests (completed).** Python standard-library tests exercise six native agent target paths, dry-run, existing-skill backups, uninstallation, modified-file refusal, symlink guards, corrupted state and fault-injected rollback. No paid service, agent execution or network request.

**Level 2: Official CLI interoperability (completed).** Claude's strict plugin validator accepts the marketplace; the upstream Vercel skills CLI actually copied TuckBit into a disposable Codex project and successfully rendered its instructions with the no-agent mode. No model tokens were used. The copied skill's frontmatter may contain added provenance metadata.

**Level 3: Real activation and task-quality evaluations (pending).** A capable agent model must decide whether to load the skill and follow its guidance in controlled tasks. Packaging tests cannot demonstrate that behavior. Use a disposable repository, approved permissions, pinned tasks and quality comparisons once an available model is chosen.

For subscription-free behavioral experiments, contributors may use their own locally hosted models. Local inference can consume substantial CPU/GPU/RAM and does **not** demonstrate native Claude/Codex skill activation.

## Run the free tests

From the repository root:

```bash
python3 scripts/tuckbit.py doctor
python3 scripts/sync_distributions.py --check
python3 -m unittest discover -s tests -v
python3 scripts/smoke_free.py
python3 scripts/smoke_free.py --interop --claude-validator
```

The last command invokes npx, which can download a free public package and use npm's local cache. It sets an isolated HOME and XDG_CONFIG_HOME and creates a disposable project for the skill installation. It does not invoke a language model or install a skill into the real agent directories.

## Use the reversible installer

Inspect planned changes first:

```bash
python3 scripts/install.py install --client codex --scope project --project /path/to/project --dry-run
python3 scripts/install.py install --client all --scope global --dry-run
```

Explicitly install one client, only when intended:

```bash
python3 scripts/install.py install --client codex --scope project --project /path/to/project
python3 scripts/install.py status --client codex --scope project --project /path/to/project
python3 scripts/install.py uninstall --client codex --scope project --project /path/to/project
```

The installer copies, rather than symlinks, the canonical skill. Existing destination directories cause an error by default. Opting into `--replace` backs up the previous skill to the selected root's `.tuck-bit/backups/` folder. Uninstallation restores the prior directory. An edited managed copy is never removed automatically; reconcile it first. Updating an already managed version requires uninstalling the old version and reinstalling the new one, to avoid unsafe in-place replacements.

It never changes provider-native permission files, global marketplace registrations, MCP settings or installed agent applications. Global scope must be selected explicitly. The root is the chosen project or home directory. The installer has no external Python dependencies.

| Agent | Project path | Global path |
|---|---|---|
| Codex | .agents/skills/tuck-bit | ~/.agents/skills/tuck-bit |
| Claude Code | .claude/skills/tuck-bit | ~/.claude/skills/tuck-bit |
| Gemini CLI | .gemini/skills/tuck-bit | ~/.gemini/skills/tuck-bit |
| Cursor | .cursor/skills/tuck-bit | ~/.cursor/skills/tuck-bit |
| OpenCode | .opencode/skills/tuck-bit | ~/.config/opencode/skills/tuck-bit |
| GitHub Copilot | .github/skills/tuck-bit | ~/.copilot/skills/tuck-bit |

Certain runtimes also read overlapping alias directories, especially .agents/skills. Installing multiple copies may be redundant; choose only the clients actually needed. For other clients, the upstream npx skills installer is preferred.

## Limits of current environment

The original validation was performed on a macOS development environment with Python, Git, npm/npx and Claude Code. Provider-dependent activation tests remain pending and may require installing each host CLI. Availability of experimental publishing tools depends on versions; do not claim untested marketplace support.

## Future quality tests

Use paired baseline and TuckBit conditions with the same prompts and model configuration. Include straightforward fixes, search-heavy work, deliberate tool selection, security boundary requests, multi-agent handoffs, and failure recovery. Measure acceptance-criteria completion, correct activation, uncached/cached input, output tokens, tool calls, validation repetitions, latency and unsafe behavior. Avoid publishing token savings claims before replicated outcome-level evidence.

References: https://github.com/vercel-labs/skills · https://agentskills.io/specification · https://code.claude.com/docs/en/plugins · https://geminicli.com/docs/cli/skills/ · https://docs.opencode.ai/docs/skills/ · https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/customize-cloud-agent/add-skills

## Task-aware compiler smoke test

    python3 scripts/plan_task.py examples/task-contract.json

Its input is self-authored and has no hooks, network dependency, model requests or provider configuration reads. The resulting JSON carries the full original request/constraints and should not be uploaded when sensitive.

## Provider-adaptive workflow regression tests

    python3 scripts/workflow_router.py examples/workflow-incident.json
    python3 scripts/workflow_router.py examples/workflow-parallel.json
    python3 scripts/workflow_router.py examples/workflow-loop.json
    python3 scripts/eval_routing.py

The evaluation corpus checks correct routing, preserved constraints and validation checks. **Passing is not evidence of actual model quality or token savings.** Hook adapters can be tested with the examples in [HOOKS](HOOKS.md).

## Local capability and trace experiments

```bash
python3 scripts/capability_registry.py build --root skills --tools-file examples/tool-metadata.synthetic.json
python3 scripts/trace_profiler.py profile --trace examples/trace-baseline.synthetic.json
python3 scripts/trace_profiler.py compare --baseline examples/trace-baseline.synthetic.json --candidate examples/trace-candidate.synthetic.json
```

Fixtures are fictional and outcomes are declared. Passing tests demonstrate parser safety and deterministic behavior, **not** model adaptation or token savings. See [registry docs](CAPABILITY_REGISTRY.md) and [telemetry docs](TELEMETRY.md).


## Repeated offline bundle acceptance (no AI inference)

```bash
python3 scripts/repeat_bundle.py --bundle evals/bundles/offline-v1.json \
  --output /tmp/tuckbit-offline-run.json
```

Expected: 24/24 offline fixture trials. Inputs come from a versioned manifest. Each run checks out the same temporary fixture commit in a fresh temporary Git worktree. Both labeled conditions execute identical deterministic Python logic; the output is **not** proof of model token savings. See [REPRODUCIBLE_BUNDLES.md](REPRODUCIBLE_BUNDLES.md).
