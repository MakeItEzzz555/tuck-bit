#!/usr/bin/env python3
"""Validate localized skill and documentation integrity without model calls."""
from __future__ import annotations
import hashlib
import json
import re
import sys
from pathlib import Path
from build_i18n import ROOT, CATALOG, REFERENCES, ENGLISH_REFERENCE_PATH, expected_files


def validate():
    source = json.loads(CATALOG.read_text(encoding="utf-8"))
    names = source["locales"]
    assert len(names) == 14
    expected = expected_files()
    generated_roots = (ROOT / "docs/i18n", ROOT / "docs/wiki/i18n", ROOT / "locales")
    existing = set()
    for path in generated_roots:
        if path.exists():
            existing.update(p.relative_to(ROOT) for p in path.rglob("*") if p.is_file())
    assert existing == (set(expected) | {Path("docs/i18n/TRANSLATION_GUIDE.md")}), "Generated localization set differs from catalog"
    for path, content in expected.items():
        current = (ROOT / path).read_text(encoding="utf-8")
        assert current == content, f"Out-of-date localization: {path}"
    assert len(list((ROOT / "locales").rglob("SKILL.md"))) == 14
    for locale in names:
        root = ROOT / "locales" / locale / ("tuck-bit-" + locale.lower())
        body = (root / "SKILL.md").read_text(encoding="utf-8")
        assert body.startswith("---\nname: tuck-bit-" + locale.lower() + "\n")
        assert re.search(r"^\d+\. ",body,re.M) and len(re.findall(r"^\d+\. ",body,re.M))==6
        assert "permission" in body or locale != "en"
        for name in REFERENCES:
            original = (ENGLISH_REFERENCE_PATH / (name + ".md")).read_bytes()
            localized = (root / "references" / (name + ".md")).read_text(encoding="utf-8")
            assert hashlib.sha256(original).hexdigest() in localized
            assert localized.endswith(original.decode("utf-8"))
        docs = (ROOT / "docs/i18n" / locale / "README.md").read_text(encoding="utf-8")
        assert "npx skills add MakeItEzzz555/tuck-bit --list" in docs
        assert "cp -R locales/" + locale + "/" in docs
    # The core canonical plugin remains unchanged and is not overwritten by localized paths.
    assert (ROOT / "skills/tuck-bit/SKILL.md").is_file()
    assert len(list((ROOT / "skills").rglob("SKILL.md"))) == 1
    return f"i18n PASS: {len(names)} locales; {len(expected)} generated files; native canonical skill preserved"


if __name__ == "__main__":
    try:
        print(validate())
    except (AssertionError, OSError, ValueError, KeyError, TypeError) as exc:
        print("i18n FAIL: " + str(exc)[:220], file=sys.stderr)
        sys.exit(1)
