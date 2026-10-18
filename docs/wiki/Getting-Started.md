# Getting Started

TuckBit has two separable parts: (1) a portable instruction-only **Agent Skill** and (2) optional local, explicit Python utilities. Installing the skill does not automatically install the root-level CLI programs or invoke an AI model.

## Option A — Inspect and install the portable skill

```sh
npx skills add MakeItEzzz555/tuck-bit --list
npx skills add MakeItEzzz555/tuck-bit
```

Review the installer prompts and choose the correct host and scope. The community skills installer is a third-party tool. To understand host-specific packages, see the [compatibility guide](https://github.com/MakeItEzzz555/tuck-bit/blob/main/docs/COMPATIBILITY.md).

## Option B — Test the CLI locally, without AI inference

Requires Git and Python (Python 3.11+ for the public repeated-bundle example):

```sh
git clone https://github.com/MakeItEzzz555/tuck-bit.git
cd tuck-bit
python3 scripts/tuckbit.py doctor
python3 scripts/workflow_router.py examples/workflow-incident.json
python3 scripts/plan_task.py examples/task-contract.json
```

The task planner and router read caller-provided JSON. Do not publish their output when the request is sensitive.

## Option C — Preview a scoped, reversible installation

```sh
python3 scripts/install.py install --scope project \
  --project /path/to/your-project --client codex --dry-run
```

After reviewing the proposed changes, repeat **without** `--dry-run` to install. To inspect or reverse:

```sh
python3 scripts/install.py status --scope project --project /path/to/your-project --client codex
python3 scripts/install.py uninstall --scope project --project /path/to/your-project --client codex
```

Project scope is the default; global scope requires deliberate opt-in. Existing destination collisions are refused by default. Review any `--replace` backup behavior first.

## Check the public offline benchmark harness

```sh
python3 scripts/repeat_bundle.py \
  --bundle evals/bundles/offline-v1.json \
  --output /tmp/tuckbit-offline-run.json
```

This runs **24 deterministic fixture trials with no AI model**, not a token-savings benchmark. See [[Benchmarks and Evidence]].

## Expectations

TuckBit cannot bypass host permissions, collect hidden reasoning, prove skill activation merely by installing, or guarantee savings. A model-free validation proves the software's deterministic behavior, not an agent's real-world effectiveness.
