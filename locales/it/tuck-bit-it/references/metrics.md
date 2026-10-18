> **English canonical technical fallback — not translated.** Il nucleo della competenza è tradotto; i riferimenti tecnici restano temporaneamente in inglese e richiedono revisione.
> Source SHA-256: `1b1aa187e4feb38a9c44b0a0bd7cc03781fe23b595973fb7c308e6eb5498fb3b`

# Optional: privacy-conscious evaluation

Compare the same representative tasks with a baseline agent, skill-only guidance and optional runtime integrations.

Measure correctly completed tasks, cached/uncached input, output/reasoning, tool calls, response size, retries, subagents, build/test repetition, latency and safety regressions.
Measure cost per **successful verified** task, not isolated token counts. Use multiple trials and report variation.
Only inspect agent logs with user authorization; redact secrets and sensitive outputs. Never upload private prompt history automatically.
Performance savings are **hypotheses**, not release claims until measured on real supported clients.

## Deterministic baseline profiling prototype

`scripts/trace_profiler.py` summarizes an **explicitly supplied redacted JSON trace** of numeric counts and optional SHA-256 operation/output/revision identifiers. It never parses raw agent conversation logs or accesses global telemetry. Identical calls are investigation candidates, not proven inefficiencies. The router accepts `--trace` to emit *advisory* observations. No cost-savings or performance claims are supported by these synthetic examples. See `docs/TELEMETRY.md`.

**Packaging note:** The profiler CLI requires the full repository checkout; a standalone Agent Skill installation does not yet include root-level scripts.
