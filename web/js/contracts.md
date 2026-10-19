# Observatory normalized read model — `tuckbit.observatory/1`

The Python adapters are the public-data boundary. They reuse `trace_profiler`, existing receipt validation and `v5_evaluation.per_task_report`. Browser aggregation does not independently qualify experiments. Native ES modules require no runtime framework or compilation.

A document has exactly `schema`, `sources`, `sessions`, `comparisons`, `limitations` collections. The importer and merged workspace are bounded to 4 MiB, 1,000 sessions, 2,000 sources, 10,000 comparisons and 100,000 events. Imports validate UTC timestamps, finite counters, duplicate identities, evidence depth and private-field exclusions. Raw selected JSON text reaches the server's duplicate-key-aware parser unchanged.

## Entities

- Source: `id`, canonical content `sha256`, `label`, `format`, `trust`, nullable `imported_at`, optional identity semantics. Whitespace changes do not create a new canonical JSON observation. Never merge by display label.
- Session/attempt: immutable `id`, `source_id`, optional `receipt_sha256`, `kind`, title, agent/provider/model/project, nullable UTC start, status, arm, task/domain/complexity, trial, bundle/runtime/environment identities, metrics, independent acceptance, policy, activation, events, context and limitations. Distinct attempts and reruns remain distinct. Unattempted arms remain visible but are excluded from attempt denominators.
- Metric: `{value: number|null, source: string|null, status: string}`. Unknown/unavailable requires null. An absent token counter, human annotation or event source is not a measured zero. Provider usage remains separate from derived values.
- Acceptance: accepted/all_passed/independent, required/performed counts, provenance. Caller-reported checks do not establish independent success. Failed and incomplete trials remain in denominators.
- Activation: seven separate stage records — available, offered, selected, delivery_started, delivery_verified, invocation, behavioral. Each carries state, note, provenance and optional sanitized public events. States are verified, not_observed, not_applicable, explicitly_absent or unknown. Whole-file delivery never proves semantic adherence.
- Policy: qualified, observed/classified/unclassified counts, bounded reason-count map and provenance. Missing coverage remains unknown.
- Event: unique identity, public order/timestamp when exposed, category, success/null, duration/null and bounded opaque evidence. No raw command, prompt, transcript, credential, hidden reasoning, source contents or private path is part of this contract. Out-of-order input is sorted by observed order; duplicate conflicting events are rejected.
- Comparison: baseline/treatment session references, original evaluator, matched identities, sample size, reasons, effective qualification and limitations. References must resolve. Existing evaluator-qualified receipts can enable a descriptive paired difference; one pair cannot establish repeatability or causality across unrelated usage.

Normalized selected JSON is untrusted: native self-claims become `kind: session`, with `reported_kind` preserved. Effective independent acceptance and qualification are downgraded while original `reported_*` fields remain available. Restored IndexedDB data and static exports follow this same rule. Browser-local authority cannot be restored from JSON claims. Only exact original-receipt revalidation can upgrade a matching retained record; changed measurements or immutable identity still conflict. This is validation against a trusted local contract, not cryptographic authentication of a provider transcript.

## Analytics semantics

Cached input is a validated subset of provider total input. Uncached input is derived as input minus cached only when compatible counters are present. Cached tokens are never added again to total input. Bytes and characters are not converted into tokens.

Date selection uses inclusive local calendar dates converted through the selected IANA timezone to `[start, next_day)` UTC instants. Day/week/month buckets honor daylight-saving changes. Undated records remain in all-time totals, not calendar plots or effective-date pricing. Model-free controls and demonstrations remain separate from observational usage totals.

Signed differences are treatment minus baseline: positive resource use is an increase. Token and wall differences are independent outcomes. Shared batch setup is not summed per arm; preparation is nested within initialization, and checkpoint within verification. Public event duration sums do not equal elapsed task time.

Price configuration is a separate optional `tuckbit.prices/1` object with version, exact provider/model, currency, effective interval, source reference and uncached/cached/output per-million rates. Estimates require every compatible usage component and exactly one applicable rate. Missing cost stays unavailable.

## Delivery and storage

`GET /api/historical` serves sanitized preserved evidence. Optional controls remain separate. `POST /api/import` requires explicit selected-file header, same-origin validation and bounded JSON; a `{document_text, capture}` envelope retains strict raw parsing and per-scope detail choices. The six scope flags affect future manual imports, not background collection. No API accepts arbitrary filesystem paths.

The static exporter copies only allowlisted application assets and sanitized historical JSON. It excludes source, hidden evaluator files and raw sessions; static imports are disabled. The optional existing portable CLI includes the same assets and verifies archive content hashes before extraction.

Memory-only import is the default. Optional IndexedDB retention stores sanitized normalized data, unencrypted, in the local browser profile. Theme/timezone/scope/retention preferences use localStorage; pricing is tab-local. Disable retention/delete imports to remove persisted observations. No Sentry, remote requests, provider folder scanning or global hooks are configured.

JSON and session/comparison CSV exports preserve identity, provenance, signed deltas, eligibility and missingness. CSV strings are formula-safe. Exports do not confer evaluator authority on subsequent imports.


## Explicit Codex rollout subset

The local `{document_text, capture}` import envelope also accepts Codex JSONL, starting with a single `session_meta` record. `import_text` routes supported records through `codex_rollout` and the same normalized validator. Only allowlisted metadata, counter values and hashed identities survive. Raw content is never an extension field in this read model.

`codex_client_cumulative` counters are client-observed, not provider-authenticated; uncached tokens and `session_elapsed_ms` are derived. `wall_ms`, independent acceptance, experimental arm, retries and activation remain unknown. `tool_calls_observed`, `error_events_observed` and `usage_snapshots_observed` are counts in the selected file, not completeness guarantees. Pricing of client counters has limited confidence. Resets, inherited histories and mismatched totals reject. Exact duplicate imports deduplicate; changed immutable snapshots conflict and require an explicit export/delete/reimport workflow. Repeated normalized imports deduplicate the normalization warning.


## V7 derived economics (no storage-schema replacement)

`usageEconomics` deduplicates immutable session identities and calls existing `aggregate` for counters and `priceCost` through `costCoverage`. Groups retain session/source IDs. Model keys include provider. Calendar allocation uses the configured IANA bucket and a complete session span; unknown/cross-boundary observations carry unallocated reasons. Date filters operate on session starts. Optional from/to bounds flag clipped buckets, suppressing period differences. No per-response allocation is inferred.

`costCoverage` returns total/covered/missing/complete, separate currency subtotals, exact effective rate source/version/components with observation counts, limited-confidence counts and unavailable reasons. It never returns a combined multi-currency value. Completeness describes selected recorded observations, not full account expenditure. The schema remains `tuckbit.observatory/1`; derived views do not alter normalized observations or evaluator decisions.
