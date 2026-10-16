# Contributing (private preview)

Use Python 3.10+ for local tooling; avoid runtime dependencies until necessary.

    python3 -m unittest discover -s tests -v
    python3 scripts/tuckbit.py doctor

Keep the canonical SKILL.md concise; put detailed guidance in selective reference files.
Changes should include deterministic tests and example evidence. Never claim quality or token improvements without comparing successful tasks to a pinned baseline.
Do not change other local projects or global agent configurations as part of TuckBit development.

Before editing model-specific guidance, cite the provider's primary documentation and distinguish published runtime behavior from TuckBit heuristics. Keep the canonical SKILL.md short and move larger descriptions to references. Update `evals/routing-cases.json` whenever routing decisions change; a lower token count never overrides correct outcomes or mandatory checks.
