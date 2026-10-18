> **English canonical technical fallback — not translated.** मुख्य स्किल का अनुवाद किया गया है; तकनीकी संदर्भ अभी अंग्रेज़ी में हैं और सामुदायिक समीक्षा आवश्यक है।
> Source SHA-256: `e1972922445c127b45ef4e8591c3f7df8d6c74e05d1539b7dd1a264a9b092af8`

# Optional: bounded multi-agent orchestration

Use only when independent task boundaries and expected benefit justify parallelism.

The orchestrator owns requirements, integration, dependency graph, source-of-truth state and final response. Workers do not inherit each other's model context automatically.

For each worker assign: goal; baseline commit; owned files; related contracts; evidence references; non-goals; targeted validation; stop conditions; concise handoff schema.
Prefer independent worktrees; serialize edits touching shared interfaces. Never let two workers edit the same files without an agreed plan.
Workers return commits/diffs, focused test evidence, open risks and integration requirements rather than entire transcripts.
Poll only when necessary; avoid parallel review loops without new evidence.
Escalate if a worker needs to expand scope beyond agreed boundaries.
