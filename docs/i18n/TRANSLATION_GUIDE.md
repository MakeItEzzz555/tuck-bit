# Translating TuckBit safely

TuckBit's **English** `README.md` and `skills/tuck-bit/SKILL.md` are canonical. This repository provides 14 translated onboarding pages, 14 optional core-skill translations and 14 localized Wiki landing pages. The eight deeper technical references for each variant currently retain exact English copies as **marked fallbacks**. This is an accessibility preview, not a full-repository or fully translated-playbook release.

## Languages and install locations

See [language directory](README.md) for each locale and its explicit project-local installation path. The localized package path is `locales/<code>/tuck-bit-<code>/SKILL.md` and its sibling `references/`. Do **not** install an additional variant automatically or rename the canonical skill. Host-native permissions and project instruction priority remain unchanged.

For a manual Codex project install, review the translated skill and references first:

```sh
mkdir -p /path/to/project/.agents/skills
cp -R locales/es/tuck-bit-es /path/to/project/.agents/skills/
```

Other hosts use their own documented project skill directory (see [compatibility](../COMPATIBILITY.md)); the command above **does not** install for them. Installing a localized skill does not prove that the host reads or obeys it.

## Contribution standards

1. Keep command syntax, shell flags, package names, repository paths, URLs, config keys, JSON fields, model identifiers, code samples, source hashes, exact-match security keywords and mandatory checks unchanged.
2. **Translate complete sections, not summaries.** Preserve the scope and force of constraints, negations, approval boundaries and stop conditions. Never broaden permissions or drop independent verification.
3. For full localization, review and translate **each of eight** technical reference playbooks alongside the core `SKILL.md`. Remove the English-fallback label only after reference parity has been independently checked.
4. Add a bilingual reviewer for each target language before labeling it reviewed. Current locale pages are unreviewed initial drafts and **not** independently linguistically verified.
5. Record an English source revision/hash, reviewed locale and reviewer attribution where consented. Version translations when the canonical skill changes.
6. Run `python3 scripts/build_i18n.py`, `python3 scripts/check_i18n.py`, the full tests, six-manifest check, privacy audit and native host installation/activation checks where available. The generator is deterministic; edit `localization-catalog.json`, not generated files.

Translation correctness is distinct from equivalent native behavior. Future comparisons must independently verify that the translated skill actually activates and maintains the original task's correctness and host permission boundaries.

## Wiki publication

Localized landing pages are versioned at `docs/wiki/i18n/<locale>.md`. The **live GitHub Wiki is a separate Git repository**. After the documentation PR is approved and merged, maintainers can copy these files into the Wiki repo as `Home-<locale>.md`, verify page links, and push with separate authorization. There is no automatic wiki publishing hook. See [Wiki publishing](../WIKI_PUBLISHING.md).

## Privacy

Do not send source code, private prompts, personal files or raw agent conversations to public translation services. Report linguistic errors through issues using synthetic examples, or privately report any security implications.
