# Observatory — public local-first preview

**Status:** Opt-in developer preview built from the reviewed private Observatory V9 source. The V9 real-export acceptance gate remains pending; no one has authorized or imported a real Codex JSONL file for that milestone.

## Start locally

From a fresh public TuckBit checkout with Python 3.11+ (Python 3.10 has explicitly unavailable SQLite controls):

    python3 scripts/tuckbit.py doctor
    python3 scripts/dashboard_server.py --port 8765

Open http://127.0.0.1:8765 in your browser. The local-only server neither listens on external interfaces nor scans directories. There is no account, telemetry service, hosted backend, package installation, or model invocation.

The public preview opens with **synthetic demo observations**, rather than the private historical research panel. Choose Sources & Privacy → select your own supported sanitized JSON or Codex JSONL file. Import is file-picker initiated only. No session folders are discovered. Capture preferences and optional IndexedDB retention are controlled in the UI. Imports remain local, although browser storage is not encrypted.

## Public release composition

- Shipped: portable canonical TuckBit skill v0.3.0 and optional deterministic runtime modules, Observatory local server, UI, import/counter validation, token analytics, accessible tables and charts, configurable rate scenarios, conservative qualification and safe error diagnostics.
- Included tests: public repository Python regressions; selected-file import and server boundary tests with a synthetic, canary-only Codex fixture; runtime tests for the published execution-state, benchmark-runner, journal, isolation, diagnostics, provider-event, repository-pilot, command-policy and workflow modules; and synthetic analytics JavaScript tests. CI covers Ubuntu and macOS with Python 3.10 and 3.13. Tests requiring withheld receipts or the frozen grader corpus are not shipped; the corresponding research replay commands are unsupported here.
- Intentionally **not shipped**: private V2–V8 study receipts, original graded results, frozen proprietary study assets, grader/reference answers, personal working paths, internal reviews and any real Codex session export. Their absence does not indicate that private experiments were conducted in this public release.
- Research replay and historical-grade commands that depend on withheld fixtures are **not supported by this public archive**. No assertion of independent efficacy or qualified native comparisons is made.

## Important limits

- Importing one authorized real Codex JSONL file has not yet been accepted in the V9 milestone. All published tests use controlled or synthetic fixtures, not real personal exports.
- Session/ project hashes are pseudonymous. Project hashes are currently unsalted and can be matched against guessed paths; session identifiers are linkable to a filename containing the session UUID. **Do not share exported observations publicly as anonymous data.** A versioned migration is a separate task.
- Costs use user-supplied tuckbit.prices/1 rate tables and represent **legacy configured cost scenarios**, never invoices, actual API billing, write charges, subscription use or quotas. Unknown counters and incompatible cache writes stay unavailable; currencies are not converted.
- Observed tasks are not independently accepted or qualified by virtue of being imported. Event or source hashes do not authenticate provider activity. No savings or causal efficiency benefit has been established.
- Unsupported execution/sandbox capabilities stay fail-closed. Native Codex isolation behavior has not been validated on Linux; optional native trials are not part of this public preview.

## Verify from source

    python3 -m unittest discover -s tests -q
    node --test tests/dashboard/*.test.mjs
    python3 scripts/sync_distributions.py --check
    python3 scripts/check_i18n.py
    python3 scripts/public_audit.py
    python3 scripts/smoke_free.py

Opt-in import and browser behavior should be validated against the same checked-out revision. Public-source audit checks current text files for high-confidence patterns, not a guarantee that secrets or private material cannot exist in arbitrary dependencies or git history.

## Contributing

Keep public changes independent from the private Observatory repository. Do not propose PRs carrying real sessions or retained historical receipts. Changes to identifiers, original evaluator qualification, pricing categories, or file-import bounds require explicit versioned contracts and regression review. See [the main contributing guide](../CONTRIBUTING.md) and [security policy](../SECURITY.md).
