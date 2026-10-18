# TuckBit social-preview artwork

Repository link previews use **GitHub's Social preview setting**, not the README's theme-aware `<picture>` tags. GitHub shows only **one uploaded image per repository at a time**, so social previews cannot automatically change between dark and light themes.

## Choose your version

| Version | File | Recommended use |
|---|---|---|
| **Dark (recommended)** | [Dark social preview](../assets/branding/tuckbit-social-preview-dark.png) | GitHub/Threads/X/Discord dark or mixed surfaces |
| Light | [Light social preview](../assets/branding/tuckbit-social-preview-light.png) | Light publication backgrounds |

Both are **1280 × 640 PNG files**, under 1 MB, and use the canonical [dark](../assets/branding/tuckbit-logo-dark.png) and [light](../assets/branding/tuckbit-logo-light.png) logos. They include only conservative copy: `Every tool. Right on cue.` and `Scoped context · Relevant tools · Required checks`. They do **not** make numeric cost/token savings claims.

## Apply the dark card to GitHub (repository admin required)

1. Open [TuckBit repository Settings](https://github.com/MakeItEzzz555/tuck-bit/settings) while signed into an account with administrator access.
2. On the **General** page, locate **Social preview**, then click **Edit**.
3. Choose **Upload an image…** and upload `assets/branding/tuckbit-social-preview-dark.png` from your computer.
4. Save/confirm, then revisit the public repository and inspect its link preview. The old default preview featuring the owner's avatar should eventually be replaced by the branded image.

This repository cannot deploy that setting through ordinary Git commits or GitHub's supported REST/GraphQL repository API. Simply storing the PNGs here **does not change the live preview**. The image must be uploaded through GitHub's Settings interface.

Previously shared links on Threads or other social platforms may retain a cached thumbnail for a period of time; a new post or waiting for its cache to refresh may be required.

GitHub documentation: [Customizing your repository's social media preview](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/customizing-your-repositorys-social-media-preview).

## Regenerate the cards

The two cards use the **exact branded PNGs** and a flat, dependency-free renderer on macOS:

```bash
swift assets/branding/generate-social-preview.swift
python3 -m unittest tests.test_social_previews -v
```

Do not use a regenerated image without reviewing both themes; GitHub may crop or cache these cards differently on different surfaces.
