# README discoverability review — 2026-10-18

This review informs TuckBit's public landing page. It does **not** claim that README formatting alone causes GitHub stars or engagement.

## Visual references from a GitTrend Instagram screenshot

The screenshot shared in the project discussion shows a three-column Instagram grid of six open-source projects. The thumbnails largely display the **first viewport of each GitHub README** or a small project cover. That makes immediate visual identity, a clear promise, a project screenshot, and a first-step link disproportionately legible compared with deep architecture prose.

The public Instagram page at https://www.instagram.com/gittrend.io/ could not be fetched without platform access in this review. The screenshot is therefore the evidence for its grid layout; we do not infer specific captions, engagement metrics, rankings, or posting strategy from an unavailable feed.

## Six repositories visible in the screenshot

| Project | GitHub source | What is effective in the README | TuckBit adaptation |
|---|---|---|---|
| **OmniGet** | https://github.com/OpenSelena/omniget (the screenshot resembles this brand; other maintained OmniGet repos exist) | Immediate product promise, illustrated experience, direct install pathways, clear platform coverage and transparent limitations | Brand-first banner, concise statement of practical value, novice and CLI paths |
| **9Drive** | https://github.com/zenhosta/9drive | Describes one specific problem and follows with concrete feature scope | Keep TuckBit's core promise in plain English above its technical architecture |
| **freehire** | https://github.com/strelov1/freehire | Memorable heading, navigable quick links, product screenshots and a distinct reason to use it | Create an immediately visible quick-start anchor and a compact workflow visual |
| **Turnitout** | https://github.com/AhmadHassan-BTed/Turnitout-Humanizer | Prominent product name and a quickly accessible hosted app | Borrow the direct 'try it' placement, **not** unverified efficacy or absolute claims |
| **mcptoon** | https://github.com/activeing123/mcptoon | Developer-specific problem statement, first-action instructions, comparisons and linked reproducibility context | Lead with agent installation and preserve transparent quality/benchmark limitations |
| **reelbird** | https://github.com/btahir/reelbird | Product screenshot and a single short value proposition suited to social thumbnails | Prefer an intentional visual hierarchy and a simple graphic instead of a long ASCII chart |

The screenshots and projects represent different categories and ages. Star counts change and do not provide a controlled measure of README quality or conversion.

## Applied TuckBit design decisions

- Preserve the existing theme-aware official logo, rather than copy another project's mascots or branding.
- Use self-hosted **flat, accessible light/dark desktop and mobile SVG signal-flow diagrams**. Multiple incoming requirements converge into a deliberate discovery lens and continue to verified evidence, replacing the ordinary three-card layout. It depicts advisory semantics, not a simulated live runtime UI.
- Move a **copyable novice agent-install prompt** near the top. It requests project scope, a dry-run/preview and approval; it does not execute commands merely when pasted into documentation.
- Put the supported discovery and installation commands immediately below for experienced developers.
- Keep the real provider-status limitations, security notes and benchmark evidence visible. Neither simulated fixtures nor marketing claims are represented as actual model savings.
- Preserve the detailed architecture, CLI, evaluation and compatibility sections for developers who scroll.
- Avoid embeds dependent on Instagram access, animated stock imagery, unaudited external install scripts or arbitrary CDN logo directories.

## Follow-up / evidence still needed

- Verify the first-screen README rendering on actual GitHub in both light and dark mode and on a narrow viewport.
- Watch community feedback for successful project-scoped installation by unfamiliar users; do not assume a pasted prompt has installed anything without a verified SKILL.md.
- Measure real README discoverability using attributable visit/issue feedback rather than treating high-star reference repositories as a causal experiment.


## Design refinement: Taste (GPT/Codex variant) + Impeccable

The visually indistinct three rounded containers were replaced with one editorial signal diagram. Kept the project's real blue/charcoal palette and first-viewport legibility, while adopting Taste's anti-template direction and Impeccable's readability, mobile adaptation and contrast discipline. GitHub READMEs cannot support GSAP scripts, hover behaviors, live React interactions or self-hosted webfont installs; this is intentionally standalone static SVG with existing HTML picture source switching. The assets are generated deterministically by `scripts/build_readme_flow.py` and tested for light/dark contrast and correct narrative meaning.

The mobile diagram is independently composed, not merely a shrunken 1160px desktop strip. No gradients, stock media, unmeasured savings or external illustration hosts were added.
