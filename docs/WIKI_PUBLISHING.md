# Wiki source and publishing procedure

GitHub's **Wiki** is a separate Git repository from the main TuckBit code repository. To make documentation auditable, the reviewed Markdown source lives in [docs/wiki](wiki/) first.

**Publication status:** These files are wiki **source**, not proof that the hosted Wiki has been initialized or synchronized. The public code repository already has extensive documentation; the wiki should be an approachable navigation layer, not a replacement source of truth.

## Initialize a new GitHub Wiki safely

1. In [TuckBit's Wiki tab](https://github.com/MakeItEzzz555/tuck-bit/wiki), select **Create the first page** if prompted.
2. Name the first page **Home**. Copy the reviewed content of [wiki/Home.md](wiki/Home.md) and save. This initial browser step creates the separate wiki Git repository.
3. Clone the new wiki repository in **a different, clean local folder**:

   ```sh
   git clone https://github.com/MakeItEzzz555/tuck-bit.wiki.git
   ```

4. Copy the reviewed Markdown files from `docs/wiki/` into the wiki checkout. Retain page filenames (`Getting-Started.md`, `Benchmarks-and-Evidence.md`, etc.) and `_Sidebar.md`.
5. Inspect `git diff`, confirm no preexisting wiki edits are overwritten, then commit and push the wiki repository **only with explicit authorization**.

The first GitHub Wiki page cannot be created by the regular source-repository contents API. If the wiki has never had a Home page, the `.wiki.git` remote can return **Repository not found** even while `has_wiki=true`.

## Synchronization and review

- Edit the source Markdown in a normal code-repository PR first, then mirror approved changes to the Wiki.
- Use public-repo URLs for canonical security, contribution, compatibility and evaluation policies.
- Verify privacy/security claims, all navigation links and the public benchmark status before each sync.
- Do not publish private experimental journals, hidden graders, raw tool outputs, original model conversations or developer workspace paths.
- Separate **public released** capabilities from local unpublished research.
- Keep historical benchmark evidence immutable; publish only sanitized, reproducible comparison packages.

This procedure intentionally does not enable GitHub Pages, install remote automation or overwrite a Wiki without review.
