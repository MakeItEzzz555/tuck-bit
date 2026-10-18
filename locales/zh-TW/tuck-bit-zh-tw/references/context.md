> **English canonical technical fallback — not translated.** 核心技能檔案已翻譯；技術參考資料暫時維持英文，仍需社群審閱。
> Source SHA-256: `f2a27bfd0e9a74d08600bbaa8bf477f10117038b57349869bc25cb90da4a0f03`

# Scoped context and evidence packets (default)

- Begin from the user's named paths, symbols, errors and current revision.
- Retrieve exact line ranges or the smallest necessary module plus adjacent tests and public contracts.
- Record relevant commits, file hashes and acceptance constraints once, as external inspectable evidence.
- Prefer short references and summaries of terminal outputs; preserve exact error text and paths.
- Expand scope on proven missing dependencies, not because a whole-project scan feels safer.
- At handoff, include task ID, baseline SHA, owned files, relevant interfaces, acceptance criteria, links to source evidence, risk and outstanding unknowns.
- At checkpoint, include current SHA, changes, last validated tests, next action, pending permissions, and failure history. Do not claim a checkpoint equals a verified final result.
- Avoid leaking secrets to logs, checkpoints or worker prompts.
