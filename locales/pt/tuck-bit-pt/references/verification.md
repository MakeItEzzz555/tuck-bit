> **English canonical technical fallback — not translated.** O núcleo da habilidade está traduzido; as referências técnicas permanecem temporariamente em inglês e precisam de revisão da comunidade.
> Source SHA-256: `89c6aba5e5d6b4cfdc783478899b1a4f99db0d48eddeeec1736c0047470787c7`

# Change-aware verification (default)

- Match validation to the modified contract and the relevant failure modes.
- During implementation run focused tests, lint or incremental compile when necessary.
- Do not repeatedly run the same expensive full suite on unchanged sources and environment.
- Integration and release milestones require an appropriate broader validation of a frozen revision.
- Do not suppress failing tests or skip mandatory security, signing, packaging, migration or accessibility checks to save tokens.
- Recheck when code, test inputs, compiler options, dependency lockfile or environment changes.
- Record command, exit code, revision, skipped tests and scope of validation; state remaining live/hardware gaps explicitly.
- Stop and request user decisions for risky operations, rather than guessing.
