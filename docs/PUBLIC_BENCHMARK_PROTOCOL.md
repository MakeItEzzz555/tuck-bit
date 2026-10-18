# Public benchmark and reproducibility protocol

This protocol is for contributors assessing **whether an agent actually completes equivalent work with fewer resources**, without skipping required context, checks, or security restrictions. It complements [offline work-bundle documentation](REPRODUCIBLE_BUNDLES.md) and [Issue #5](https://github.com/MakeItEzzz555/tuck-bit/issues/5).

## Start with the outcome, not the token count

For every task and treatment, disclose:

1. **Independent pass/fail:** required functional, integration, security and completeness checks; failures and incomplete trials remain in the denominator.
2. **Comparable conditions:** exact task, start commit/tree and source hashes, acceptance checks, dependency/tool/client/model versions, effort, permissions, budgets and grader identity.
3. **Treatment proof:** whether TuckBit's instructions were actually delivered/read, and whether optional tools were invoked. Installation or a prompt mention alone is not activation.
4. **Resources:** provider-reported input and cached-input tokens, derived uncached input where supported, output tokens, model-call counts if observed, classified tool calls, context rereads, retries, elapsed time and validation/preparation overhead.
5. **Human work:** measured review and manual editing time, with provenance. If unobserved, report **unknown**, not zero.
6. **Failure/missingness:** policy-unclassified events, missing telemetry, timeouts, retries and changes to the task or fixture.

A reported reduction is not *attributable* to TuckBit if treatment activation or required policy/quality coverage is unverified.

## Freeze a versioned bundle before collecting results

Use a content-addressed task manifest recording the exact source snapshot, task description, required checks, evaluator version, tool/client/model versions, relevant permission settings and treatment configuration. Start every attempt in a fresh disposable environment from the same source state; verify the starting and ending inventories. Never expose hidden answers to agents.

Keep raw/privileged evidence private. Publish **sanitized** receipts and hashes; do not share secret keys, full command arguments, private prompts or unpublished code.

## Repeat and counterbalance

Compare baseline (A), portable TuckBit skill (B), and optional prepared-runtime treatment (C). For actual model evaluations, rotate A/B/C across execution positions, such as ABC, BCA, CAB, and—when practical—CBA, ACB, BAC. Record order, repetition number, cache limitations and budget. Different agent/condition ordering controls order effects; it is not evidence of native parallelism.

Each failed, interrupted or disqualified run remains recorded. Do not replace unfavorable attempts or selectively publish successful ones. Two identical scripted adapters may verify the **runner**, but cannot establish agent efficiency.

## Report by task before averaging

For each task/domain/difficulty/arm, publish: attempted and accepted counts, pass/failure rate and reason categories, activation evidence, original per-run samples, tokens with cached/uncached splits, tool calls, context rereads (changed vs unchanged vs mandatory verification), retries, latency, observed human review/editing time, policy coverage and unavailable metrics. Report distribution/range/median and uncertainty when the sample permits. Avoid average-only dashboards.

Distinguish a candidate redundant read from a legitimate verification read; compare the **correctness-preserving critical path**, not minimized telemetry.

## Public current state

The default branch's [offline repeated-task example](../evals/results/offline-v1.example.json) covers **three deterministic public tasks × four repetitions × two identical scripted conditions = 24 trials**. It verifies fixture isolation and reporting only. It makes **no native AI-agent, cost or token-savings claim**. A future provider-native adapter and independently qualified repeated trials are required for empirical efficacy.

## Reproduce the public offline fixture

From a clean checkout with Python 3.11+ and Git:

```sh
python3 scripts/repeat_bundle.py --bundle evals/bundles/offline-v1.json \
  --output /tmp/tuckbit-offline-run.json
```

Expected deterministic acceptance: 24 of 24 passing fixture trials; timings will vary. The tool does **not** invoke any model or read private sessions. Consult [the reproduction guide](REPRODUCIBLE_BUNDLES.md) for precise trust boundaries.

To submit a community benchmark, open the [benchmark report issue template](https://github.com/MakeItEzzz555/tuck-bit/issues/new/choose) with public, licensed fixtures, all attempted runs, sanitized paired receipts and exact reproduction steps.
