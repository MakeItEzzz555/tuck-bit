# Minimal redacted execution telemetry and baseline comparison

`scripts/trace_profiler.py` takes **one explicit, schema-limited JSON file**, validates it, and outputs aggregate counts. It does not inspect live Codex/Claude/other session databases or parse arbitrary agent transcripts.

It is intended as the privacy-preserving **input format for future instrumentation**. We are *not* measuring real model-token savings yet.

## Input format

```json
{
  "schema": 1,
  "outcome": {"verified": true, "acceptance_checks_passed": true},
  "events": [
    {
      "category": "tool_read",
      "role": "root",
      "input_tokens": 1000,
      "cached_input_tokens": 700,
      "output_tokens": 50,
      "reasoning_output_tokens": 0,
      "result_bytes": 500,
      "duration_ms": 20
    }
  ]
}
```

Allowed event categories: `tool_read`, `tool_write`, `test`, `build`, `handoff`, `agent_message`, `planning`, `other`. Allowed roles: `root`, `worker`, `reviewer`. All counters are nonnegative integer measurements. Cached input is assumed to be a subset of reported input; reasoning output is assumed to be a subset of reported output. If a provider uses different definitions, map the data carefully first.

Optional **hex SHA-256 digests** `operation_sha256`, `result_sha256`, and `revision_sha256` allow identifying repeated identical operations with the same observed output at an unchanged revision. No tool arguments, prompts, paths, raw logs, URLs, credentials, or private reasoning should be included. Unknown input keys are rejected rather than silently accepted.

**A possible repetition is not proven waste.** An unchanged test command might deliberately validate environmental flakiness, and an identical tool read might be necessary after an external state change. `identical_repeats_by_category` splits the count so repeated `test`/`build` validation is reported apart from repeated reads.

### Context rereads

An optional `target_sha256` is an opaque digest of what a `tool_read` or `tool_write` targeted (for example a file and line range, or a symbol), computed by the caller. Never send the path itself. A read is **tracked** when it carries both `target_sha256` and `result_sha256`. The profiler walks events in the supplied order and reports `context_rereads`:

| Field | Meaning |
|---|---|
| `first_reads` | First tracked read of a source. |
| `unchanged_content` | Reread with the same result digest and no write since. **Potentially redundant**, not proven waste. |
| `changed_content` | Reread whose content changed without an observed write (external change). |
| `after_mutation` | Reread after a write to that source: expected verification. A `tool_write` without `target_sha256` counts as touching every source already read. |
| `untracked_reads` | Reads missing either digest; they are not classified. |

`coverage` is `complete` only when every `tool_read` is tracked, `partial` when some are, and `unknown` when none are. `compare` reports reread deltas only when both traces are `complete`. Rereads across roles are counted the same way; the report does not split them by role. Overlapping ranges with different target digests are not linked; choose one source granularity per trace.

## Use

Synthetic fixture, explicitly labeled and **not measured**:

```bash
python3 scripts/trace_profiler.py profile \
  --trace examples/trace-baseline.synthetic.json

python3 scripts/trace_profiler.py compare \
  --baseline examples/trace-baseline.synthetic.json \
  --candidate examples/trace-candidate.synthetic.json
```

Outputs provide total/cached/uncached input, reported output, summed event durations, tool-result bytes, number of large outputs, and potential identical repetitions. No raw event identifiers, digests, or provider payloads are echoed.

The `compare` command **never asserts cost savings**, even when both examples claim completed tasks. The event durations are summed and may overlap in parallel agent workflows, so they are not equivalent to wall-clock latency.

## The next genuine benchmark

Run the same representative task in a disposable repository under identical model configuration, permission settings, task input, environment and success criteria:
- Baseline without TuckBit policy.
- TuckBit skill-only.
- Optional skill + explicit registry/hook when available.
- Repeat across samples and different task classes, avoid picking only best runs.
- Evaluate correctness and policy violations first. Then interpret resource and latency differences; separate cold/cached token accounting where available.

Any future log import must be user-authorized, parse only documented fields, redact before output, and exclude prompts, credentials, private reasoning and raw tool messages. Debugging a failed run does not justify uploading user transcripts by default.

## Retention and privacy

The profiler is stateless. It does not write output to disk unless the user explicitly redirects stdout. Refrain from storing telemetry inside Git; if saved locally, use a private ignored folder. A compiled digest is an opaque identifier, not proof that an operation was safe, authorized or unnecessary.


## Repeated task-bundle infrastructure

For a reproducible **offline** task bundle run, see [REPRODUCIBLE_BUNDLES.md](REPRODUCIBLE_BUNDLES.md). The runner uses disposable Git worktrees and feeds its local read/write/check event records into this profiler. It produces per-task run and failure distributions, but **no real agent inference or token measurements**. Use the outputs only to test the benchmark pipeline, not to advertise efficiency.
