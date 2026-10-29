#!/usr/bin/env python3
"""Deterministic localized docs and portable-skill generation. No AI/network calls."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "localization-catalog.json"
REFERENCES = ("task-contract", "workflows", "registry", "context", "verification", "budget", "orchestration", "metrics")
ENGLISH_REFERENCE_PATH = ROOT / "skills/tuck-bit/references"
READONLY_NOTICE = "Canonical English technical reference preserved for complete behavior coverage. Community translation review requested."


def expected_files():
    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    assert data["schema"] == 1 and len(data["locales"]) >= 13
    produced = {}
    lang_lines = ["# TuckBit — Languages / Idiomas / Langues / Sprachen", "",
                  "The original English README and `skills/tuck-bit/SKILL.md` remain canonical.",
                  "Localized landing pages and optional core skills below are **community-review candidates**.",
                  "The optional localized skills preserve the complete English technical references as a marked fallback.",
                  "They do not modify the canonical distribution or automatically activate inside any agent.",
                  "Translations of the entire repository and of all technical reference playbooks are **not yet complete**.", "",
                  "| Language | Documentation | Optional skill |", "|---|---|---|",
                  "| English (canonical) | [README](../../README.md) | [tuck-bit](../../skills/tuck-bit/SKILL.md) |"]
    for code, t in data["locales"].items():
        assert len(t["steps"]) == 6 and t["label"] and t["dir"] in ("ltr", "rtl")
        safe = code.replace("-", "").isalnum()
        assert safe
        skill_name = "tuck-bit-" + code.lower()
        skilldir = Path("locales") / code / skill_name
        skill = [
            "---",
            f"name: {skill_name}",
            "description: " + json.dumps(t["intro"], ensure_ascii=False),
            "license: MIT",
            "compatibility: Portable Agent Skills; project-scoped install only.",
            "metadata:",
            "  author: TuckBit contributors",
            "  version: \"0.4.0\"",
            f"  locale: {code}",
            "---", "",
            "# TuckBit — " + t["label"],
            "",
            "> " + t["translated"], "",
            t["score"], "",
            t["modes"], "",
            "## " + t["method"], "",
            t["setup"], "",
        ]
        for i, step in enumerate(t["steps"], 1):
            skill.append(f"{i}. {step}")
        skill += ["", "## " + t["refs"], "",
                  "- `references/task-contract.md` — task contracts / host instructions.",
                  "- `references/workflows.md` — Fast / Standard / Deep workflows.",
                  "- `references/registry.md` — discovery and permission limits.",
                  "- `references/context.md` — source-linked evidence and checkpoints.",
                  "- `references/verification.md` — tests and integration checks.",
                  "- `references/budget.md` — bounded iterations.",
                  "- `references/orchestration.md` — optional independent agents.",
                  "- `references/metrics.md` — optional evaluation.",
                  "", "## " + t["bounds"], "",
                  t["safety"], "",
                  "**" + t["limit"] + "**", ""]
        produced[skilldir / "SKILL.md"] = "\n".join(skill)
        for ref in REFERENCES:
            # Deliberate English fallback, not represented as a complete translation.
            english = (ENGLISH_REFERENCE_PATH / (ref + ".md")).read_text(encoding="utf-8")
            source_hash = hashlib.sha256(english.encode("utf-8")).hexdigest()
            produced[skilldir / "references" / (ref + ".md")] = (
                "> **English canonical technical fallback — not translated.** " + t["translated"] +
                "\n> Source SHA-256: `" + source_hash + "`\n\n" + english
            )
        readme = [
            "# TuckBit — " + t["label"], "", "**" + t["tagline"] + "**", "", t["intro"], "",
            "> " + t["limit"], "",
            "## " + t["quick"], "",
            "```sh",
            "npx skills add MakeItEzzz555/tuck-bit --list",
            "git clone https://github.com/MakeItEzzz555/tuck-bit.git",
            "cd tuck-bit",
            "python3 scripts/tuckbit.py doctor",
            "```", "",
            "## " + t["install"], "",
            t["install_notice"],
            t["install_instruction"],
            "",
            "```sh",
            "mkdir -p /path/to/project/.agents/skills",
            f"cp -R locales/{code}/{skill_name} /path/to/project/.agents/skills/",
            "```", "",
            t["translated"], "",
            "## " + t["overview"], "",
            "- [" + t["canonical_label"] + "](../../../README.md)",
            "- [" + t["evaluation_label"] + "](../../PUBLIC_BENCHMARK_PROTOCOL.md)",
            "- [" + t["compatibility_label"] + "](../../COMPATIBILITY.md)",
            "- [" + t["privacy_label"] + "](../../../SECURITY.md)",
            f"- [" + t["skill_label"] + f"](../../../{skilldir.as_posix()}/SKILL.md)",
            "- [" + t["languages_label"] + "](../README.md)",
            "", t["safety"], ""
        ]
        # docs/i18n/{code}/README.md -> ../../.. to repository root, ../../ to docs/
        produced[Path("docs/i18n") / code / "README.md"] = "\n".join(readme)
        wiki = [
            "# TuckBit — " + t["label"], "", "**" + t["tagline"] + "**", "",
            t["intro"], "", "> " + t["limit"], "",
            "## " + t["quick"], "",
            "- [Localized README](https://github.com/MakeItEzzz555/tuck-bit/blob/main/docs/i18n/" + code + "/README.md)",
            "- [Portable localized skill](https://github.com/MakeItEzzz555/tuck-bit/blob/main/" + skilldir.as_posix() + "/SKILL.md)",
            "- [English Wiki](https://github.com/MakeItEzzz555/tuck-bit/wiki)",
            "- [All languages](https://github.com/MakeItEzzz555/tuck-bit/blob/main/docs/i18n/README.md)",
            "", t["translated"], ""
        ]
        produced[Path("docs/wiki/i18n") / (code + ".md")] = "\n".join(wiki)
        lang_lines.append(f'| {t["label"]} (`{code}`) | [README]({code}/README.md) | [SKILL.md](../../locales/{code}/{skill_name}/SKILL.md) |')
    lang_lines += ["", "## Reliability and security", "",
                   "Keep code symbols, file paths, shell commands, version identifiers and exact-match test fixtures unchanged.",
                   "Localized instructions are opt-in, project-scoped and require per-host validation. Never assume translation proves equivalent model behavior.",
                   "Each source English reference is bundled and marked as a fallback; community-reviewed full translations can replace them in future versioned releases.", ""]
    produced[Path("docs/i18n/README.md")] = "\n".join(lang_lines)
    return produced


def main():
    generated = expected_files()
    for path, text in generated.items():
        full = ROOT / path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(text, encoding="utf-8")
    print(f"Wrote {len(generated)} versioned localization files for 14 locales. No model calls.")


if __name__ == "__main__":
    main()
