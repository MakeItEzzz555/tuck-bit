"""Static, privacy-preserving checks for public onboarding and branding."""
from pathlib import Path
import re
import unittest
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
PROMPT_DOC = ROOT / "docs" / "AGENT_INSTALL_PROMPT.md"

class ReadmeOnboardingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.readme = README.read_text(encoding="utf-8")
        cls.prompt_doc = PROMPT_DOC.read_text(encoding="utf-8")

    def test_project_scope_prompt_is_copyable_and_identical_to_guide(self):
        expression = re.compile(
            r"<!-- AGENT_INSTALL_PROMPT_START -->\n(```text\n.+?\n```)\n<!-- AGENT_INSTALL_PROMPT_END -->",
            re.DOTALL,
        )
        match = expression.search(self.readme)
        self.assertIsNotNone(match)
        prompt = match.group(1)
        self.assertIn(prompt, self.prompt_doc)
        self.assertIn("https://github.com/MakeItEzzz555/tuck-bit", prompt)
        self.assertIn("CURRENT project", prompt)
        self.assertIn("project-scoped", prompt)
        self.assertIn("ask my approval", prompt)
        self.assertIn("Do not overwrite", prompt)
        self.assertIn("do not invent unsupported commands", prompt)
        self.assertIn("verify the project-scoped SKILL.md", prompt)

    def test_install_not_misrepresented_as_activation(self):
        text = self.readme.lower()
        self.assertIn("installation is distinct from successful model-driven activation", text)
        self.assertIn("token savings are **not** established", text)
        self.assertIn("pasting it here does not install anything automatically", text)
        self.assertIn("no global", self.readme.lower())

    def test_prompt_comes_before_technical_material(self):
        for heading in ("## How it works", "## The six capabilities",
                        "## Local capability index and execution profiling",
                        "## Agent support"):
            self.assertLess(self.readme.index("## Install with your AI agent"),
                            self.readme.index(heading))

    def test_new_graphics_are_local_and_accessible(self):
        self.assertIn("prefers-color-scheme: dark", self.readme)
        self.assertIn("prefers-color-scheme: light", self.readme)
        self.assertIn("alt=\"How TuckBit works:", self.readme)
        self.assertIn("(max-width: 600px) and (prefers-color-scheme: dark)", self.readme)
        self.assertIn("(max-width: 600px) and (prefers-color-scheme: light)", self.readme)
        for theme in ("light", "dark", "light-mobile", "dark-mobile"):
            file = ROOT / "assets/branding" / ("tuckbit-flow-" + theme + ".svg")
            self.assertTrue(file.is_file())
            svg = ET.parse(file).getroot()
            self.assertEqual(svg.tag, "{http://www.w3.org/2000/svg}svg")
            tags = {e.tag.rsplit("}", 1)[-1] for e in svg.iter()}
            self.assertNotIn("script", tags)
            self.assertNotIn("foreignObject", tags)
            self.assertIn("title", tags)
            self.assertIn("desc", tags)
            self.assertTrue(file.stat().st_size < 10000)

    def test_relative_markdown_links_exist(self):
        links = re.findall(r"\]\(([^)]+)\)", self.readme)
        missing = []
        for link in links:
            if link.startswith(("https:", "http:", "#", "mailto:")):
                continue
            path = link.split("#", 1)[0]
            if path and not (ROOT / path).exists():
                missing.append(path)
        self.assertEqual(missing, [])

    def test_editorial_signal_flow_is_reproducible_and_accessible(self):
        import importlib.util
        script = ROOT / "scripts/build_readme_flow.py"
        spec = importlib.util.spec_from_file_location("build_readme_flow", script)
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for theme in ("light", "dark"):
            for mobile in (False, True):
                suffix = "-mobile" if mobile else ""
                file = ROOT / "assets/branding" / f"tuckbit-flow-{theme}{suffix}.svg"
                self.assertEqual(file.read_bytes(), module.generate(theme, mobile))
                root = ET.parse(file).getroot()
                self.assertIn("full user request", next(x.text for x in root if x.tag.endswith("desc")))
                self.assertFalse(any(child.tag.endswith("script") for child in root.iter()))

        # Ensure subdued small copy in both themes clears WCAG normal-text 4.5:1.
        def luminance(value):
            rgb = [int(value[i:i+2], 16) / 255 for i in (1, 3, 5)]
            linear = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in rgb]
            return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]
        for theme, palette in module.PALETTES.items():
            background = luminance(palette["bg"])
            for role in ("fg", "secondary", "quiet", "blue"):
                foreground = luminance(palette[role])
                light, dark = sorted((background, foreground), reverse=True)
                self.assertGreaterEqual((light + 0.05) / (dark + 0.05), 4.5, (theme, role))

    def test_both_local_install_methods_are_documented(self):
        self.assertIn("npx skills add MakeItEzzz555/tuck-bit --list", self.readme)
        self.assertIn("npx skills add MakeItEzzz555/tuck-bit\n", self.readme)
        self.assertIn("--scope project", self.readme)
        self.assertIn("--dry-run", self.readme)

if __name__ == "__main__":
    unittest.main()
