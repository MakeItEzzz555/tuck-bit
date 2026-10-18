# Troubleshooting

## The skill is installed but my agent does not use it

Check the correct host/project directory and the client's documented discovery behavior. Inspect the skill rather than installing copies into multiple global directories. **Installation is not verified runtime activation.** See [[Agent Compatibility]].

## The CLI says a module or script is missing

The portable Agent Skill is instruction-only. For root-level Python utilities, clone the full repository. Check Python 3, your working directory and the commands in [[Getting Started]]. Use `python3 scripts/tuckbit.py doctor` from the checkout root.

## The installer refuses to overwrite a skill

This is intentional collision protection. First inspect:

```sh
python3 scripts/install.py install --scope project --project /path/to/project \
  --client codex --dry-run
```

Read [installer backup/rollback behavior](https://github.com/MakeItEzzz555/tuck-bit/blob/main/docs/TESTING.md) before using replacement flags. Never delete a user's existing skills directory to bypass a conflict.

## A benchmark has 24 passing runs but no model tokens

The public repeated-task demo is **model-free**. Both labels run the same scripted adapter. Token, model activation and human review metrics are therefore unavailable. This is expected; see [[Benchmarks and Evidence]].

## The profiler reports unknown or missing data

Missing provider counters or unrecognized commands must remain **unknown**, not zero. Supply only supported, sanitized evidence. A successful tool process or a lower token count does not alone establish equivalent task completion.

## The offline setup fails

Run `python3 scripts/tuckbit.py doctor`, confirm Git and Python 3.11+ for the public repeated fixture, and check the exact required output path. The repeat harness refuses overwriting existing result files; choose a **new** path. Its private disposable worktrees are temporary and distinct from your project.

## I found a possible security problem

Stop testing on sensitive data. Use [private vulnerability reporting](https://github.com/MakeItEzzz555/tuck-bit/security/advisories/new) and follow [SECURITY.md](https://github.com/MakeItEzzz555/tuck-bit/blob/main/SECURITY.md). Do not post raw dumps or exploit details in public issues.

For nonsecurity questions, use [Discussions](https://github.com/MakeItEzzz555/tuck-bit/discussions) or [Support](https://github.com/MakeItEzzz555/tuck-bit/blob/main/SUPPORT.md).
