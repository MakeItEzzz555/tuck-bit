# Repeated task bundles — proof of harness, not agent savings

TuckBit's first **offline fixture harness** lives in `scripts/repeat_bundle.py`. Its purpose is to prove that a task bundle can be repeated from an identical Git starting state and reported **by task and condition**. It does **not** call an AI agent, execute arbitrary manifest commands, collect private prompts, or claim model efficiency.

## Reproduce the offline demonstration

From a clean TuckBit checkout with Python 3.11+ and Git installed:

```bash
python3 scripts/repeat_bundle.py \
  --bundle evals/bundles/offline-v1.json \
  --output /tmp/tuckbit-offline-run.json
```

The checked-in bundle has three small public tasks and four repetitions. For each task and repetition, the harness executes **two identical deterministic Python adapters**, labeled `baseline` and `tuckbit` solely to exercise the paired-report format. Both conditions have the same instructions and implementation; therefore neither is evidence of TuckBit superiority.

Expected demonstration: **24/24 passing trials** (3 tasks × 4 repetitions × 2 conditions). Time measurements vary by machine. The output report includes the pinned fixture Git commit and tree SHA, versioned bundle digest, repeated trial records, explicit acceptance checks, per-task pass/failure distributions, tool-operation counts, and unavailable fields as `null`.

## How worktree isolation is enforced

1. A temporary, disconnected Git repository is created from the public task manifest.
2. The fixture is committed once with fixed metadata, generating a starting Git commit and tree hash.
3. **Each individual trial** checks out that same commit into a separate temporary Git worktree.
4. The built-in deterministic adapter performs a small file transform and writes only an output file inside the disposable worktree.
5. Mandatory checks verify the expected result, unchanged source input, and no changes to tracked files.
6. The worktree is removed. The original TuckBit checkout and other projects are never used as trial workspaces.

The manifest cannot specify an arbitrary shell command, Git URL, external model, network operation, or filesystem path. Invalid or extra fields fail closed. Output files are created only at an explicit destination and never overwritten.

## Fairness and counters

- **Task matching:** identical fixtures, expected outputs, and acceptance checks for both treatments.
- **Version pin:** bundle version + SHA-256, one starting fixture commit and tree SHA recorded in the report.
- **Budgets:** same maximum operations and adapter/check execution-wall-time budget for both conditions. Worktree provisioning time is not included in the adapter timing.
- **Order:** odd repetitions run baseline before tuckbit; even repetitions reverse the order. This counterbalances *fixture treatment order*, **not actual coding-agent sequence**.
- **Checks first:** a failed mandatory check or exceeded budget fails the run and remains visible in the per-task failure counts.
- **Metrics:** actual, instrumented offline reads/writes/check operations and result bytes are reported per run. The existing trace profiler is reused to summarize each run. This does not instrument native provider tool calls.
- **Unavailable:** AI token counts, provider costs, model/agent version, human review and editing times are `null` because no real agent was involved; they are not recorded as zero. Counted agent re-runs are zero because no agent runs at all.
- **Distributions:** every per-task repetition is included, with pass/failure counts and per-trial operation/time samples. Avoid interpreting an aggregate mean as a performance claim.

## What's required for a genuine agent benchmark

A separate opt-in, provider-specific executor must support pinned host/model/tool versions, explicit user-approved budgets and permissions, a clean worktree per **real** run, identical task requirements, correct acceptance checks and counterbalanced baseline-versus-TuckBit order. A collector must report cached/uncached tokens, tool calls, context rereads, re-runs, human review/editing time, failures and limitations without recording raw private prompts or chain of thought.

That native runner **has not been built or verified yet**. An offline passing harness is a prerequisite, not a substituted experiment. Keep real-work benchmark artifacts versioned, sanitized, public and reviewed before publication.

The issue that tracks the real benchmark is [#5](https://github.com/MakeItEzzz555/tuck-bit/issues/5).
