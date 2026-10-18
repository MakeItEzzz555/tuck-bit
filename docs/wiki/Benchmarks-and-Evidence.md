# Benchmarks and Evidence

TuckBit treats **independent task correctness as the first metric**, and resource consumption as meaningful only when the compared runs actually perform the required work.

## What can you repeat today?

The released public branch includes an **offline repeated-task harness**, not a provider-native experiment:

```sh
git clone https://github.com/MakeItEzzz555/tuck-bit.git
cd tuck-bit
python3 scripts/repeat_bundle.py \
  --bundle evals/bundles/offline-v1.json \
  --output /tmp/tuckbit-offline-run.json
```

This public example contains three tasks, four repetitions and two identical scripted conditions: **24 offline trials**. The conditions have distinct labels only to test the paired-report format. Passing fixtures do **not** demonstrate TuckBit activation, inference efficiency or cost reductions.

## What would qualify as native evidence?

| Requirement | Why |
|---|---|
| Same pinned source commit/tree, task and dependencies | Prevent source drift |
| Same model/client versions, effort, budgets and mandatory checks | Make the experimental conditions comparable |
| Fresh disposable environment per arm and trial | Prevent output contamination |
| Independently measured skill instruction consumption | Distinguish activation from installation |
| Policy/tool coverage and independent grading | Stop skipped safety/verification appearing as savings |
| Order rotation and repeated trials | Reduce warmup, cache and treatment-position bias |
| Full per-task distributions and failures | Avoid hiding harder cases in aggregate averages |
| Provider-reported token metrics and explicit unknowns | Prevent fabricated savings |

Include observed cached and uncached input tokens, output tokens, rereads, tool calls, retries, review/editing effort and latency when available. Never infer missing human effort from total wall time, or label candidate rereads as waste without independent assessment.

## Contribute an independently reproducible result

Consult the [public benchmarking protocol](https://github.com/MakeItEzzz555/tuck-bit/blob/main/docs/PUBLIC_BENCHMARK_PROTOCOL.md) and [Issue #5](https://github.com/MakeItEzzz555/tuck-bit/issues/5). Attach only licensed/synthetic fixtures, sanitized reports, pinned versions, exact checks and **all attempts**, including failures.

Full implementation protocol: [Repeated task bundles](https://github.com/MakeItEzzz555/tuck-bit/blob/main/docs/REPRODUCIBLE_BUNDLES.md).

If a benchmark is native but activation, safety coverage or grader independence is unknown, label it exploratory and avoid an attributed efficiency claim.
