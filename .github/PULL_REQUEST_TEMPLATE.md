## Summary

Describe the problem and focused change. Link the relevant issue or discussion.

## Why this approach?

Explain compatibility, alternative approaches, new dependencies (if any), and why this keeps correctness and native permissions intact.

## Verification

- [ ] No unrelated changes, credentials, personal paths, raw prompts, or proprietary data.
- [ ] Relevant focused tests and the full local unit suite passed, or failures are clearly documented.
- [ ] Distribution manifests updated if required.
- [ ] Router evaluation cases or synthetic fixtures updated when policy changes.
- [ ] Documentation and explicit provider limitations updated.
- [ ] No automatic global installation, service, hook or permission change was introduced without a documented opt-in.

**Commands and exact results:**

**What remains untested (native acceptance / unsupported clients):**

## Security and privacy impact

Describe any new file/network access, persistence, tool execution, logging, or external dependencies. If the change concerns a vulnerability, use private vulnerability reporting before public disclosure.
