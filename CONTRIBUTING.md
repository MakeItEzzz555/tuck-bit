# Contributing to TuckBit

Thanks for helping improve AI coding-agent workflows **without weakening correctness or safety**.

## Ways to participate

You can help by reproducing bugs, testing actual skill activation in supported hosts, finding edge cases in installers and permissions, improving documentation, or building reproducible **quality-preserving** efficiency benchmarks. Check [Issues](https://github.com/MakeItEzzz555/tuck-bit/issues) and [Discussions](https://github.com/MakeItEzzz555/tuck-bit/discussions) first.

## Your first contribution

1. Read the [public roadmap](docs/ROADMAP.md), [security policy](SECURITY.md), and [Code of Conduct](CODE_OF_CONDUCT.md).
2. Open or find a focused issue. Discuss changes that introduce new dependencies, hooks, network access, or execution permissions before implementing.
3. Create a branch or fork. Keep unrelated changes out of the pull request.
4. Include tests and documentation for changed behavior.
5. Run these commands in the project root:

        python3 scripts/tuckbit.py doctor
        python3 scripts/public_audit.py
        python3 scripts/sync_distributions.py --check
        python3 -m unittest discover -s tests -v
        python3 scripts/eval_routing.py
        python3 scripts/smoke_free.py

   Optional client packaging check (requires npm and the Claude CLI; **no LLM inference**):

        python3 scripts/smoke_free.py --interop --claude-validator

6. Explain exact checks, failures, skips and remaining manual acceptance in the PR template.

Python 3.10+ is recommended for the dependency-light local tooling.

## Engineering boundaries

- Keep one canonical skill in **skills/tuck-bit/SKILL.md**. Put detailed instructions in on-demand references.
- Use the provider's native permissions; never create silent global installs, hidden hooks, arbitrary tool execution, secret indexing, or chain-of-thought extraction.
- Distinguish documented host behavior from TuckBit workflow heuristics. Cite official provider specifications for integration changes.
- Update the deterministic routing cases when changing execution policies.
- Benchmark **successful verified work**, not isolated token savings. Declare synthetic fixtures clearly.
- Never include credentials, private prompts, raw model transcripts, personal file paths, proprietary source, session archives, API keys or unredacted screenshots in issues or PRs.

Contributions are accepted under the [MIT license](LICENSE).

## Security issues

Please do **not** open a public issue for a vulnerability. Use the repository's [private vulnerability reporting](https://github.com/MakeItEzzz555/tuck-bit/security/advisories/new), described in [SECURITY.md](SECURITY.md).
