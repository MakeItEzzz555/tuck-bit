# Just-in-time capability registry (default)

- First determine which single capability would answer the current question.
- Use existing native tool-search and skills discovery before adding another router.
- Read an installed skill's full instructions only when it is relevant; avoid loading every skill document at session start.
- Catalog safe metadata only: canonical name, description, input schema signature, provider identity, source and freshness.
- Exclude credentials, auth headers, outputs containing secrets, and arbitrary executable instructions from the index.
- Always resolve fresh permissions and live availability through the original authorized provider before executing.
- Invalidate schema metadata after configuration, server, version or tool-list changes.
- Avoid automatic full scans, duplicate lookup retries and caching of mutations.
- A local metadata registry is a roadmap capability; Phase 1 only provides guidance and profile checks.
