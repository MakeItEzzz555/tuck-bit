# Local capability metadata registry — private preview

The registry is a read-only discovery and freshness **advisor**, not an MCP server, shell router or provider permission broker.

## Why this exists

The Agent Skills standard recommends showing only small skill metadata during discovery and opening full `SKILL.md` instructions when relevant. Native Codex and Claude tools already support progressive disclosure; TuckBit should improve cross-client indexing and reduce duplicate discovery **without replacing those native mechanisms**.

Relevant references:

- https://agentskills.io/specification
- https://developers.openai.com/api/docs/guides/tools-skills
- https://modelcontextprotocol.io/specification/2026-07-28/server/tools
- https://github.com/OWASP/MCP-Taxonomy

## Supported explicit inputs

1. `--root /path/to/skills`: one or more explicitly selected directories. Each immediate child with a valid `SKILL.md` is indexed using its YAML frontmatter name and description (only), plus a SHA-256 of the file. A root that itself contains a `SKILL.md` is also supported. The index stores a root ordinal and **relative** skill path, not your user-home directory.
2. `--tools-file /path/to/catalog.json`: optional, caller-supplied snapshot of tool **metadata**. Entries have `provider`, `name`, `description`, optional `enabled`, and optional `inputSchema`. The tool schema is hashed, not included. Unknown keys (including tokens, headers and endpoints) are never copied into index output.

There is **no automatic scan** of your home directory, agent global configuration or MCP servers. The script does not connect to MCP, install a tool, fetch URLs or make model requests. Skills in symlink directories are **skipped by design** until a safe, explicitly consented resolver is validated; index coverage may therefore be incomplete.

Invalid skills are omitted, malformed provided tool catalogs are rejected. There are bounded source counts, file sizes and output sizes.

## Build and query

From the repository checkout:

```bash
python3 scripts/capability_registry.py build \
  --root skills \
  --tools-file examples/tool-metadata.synthetic.json \
  --output /tmp/tuckbit-sample-index.json

python3 scripts/capability_registry.py query \
  --snapshot /tmp/tuckbit-sample-index.json \
  --text "Swift regression tests" --limit 5

python3 scripts/capability_registry.py verify \
  --snapshot /tmp/tuckbit-sample-index.json \
  --root skills \
  --tools-file examples/tool-metadata.synthetic.json
```

Output creation refuses to overwrite a preexisting file and requests private file permissions (0600 on POSIX). The snapshot stores metadata and hashes, not instruction bodies. `verify` rebuilds from the same explicit source roots and tool metadata snapshot to check freshness, detecting changed skill files, additions/deletions and changed tool catalogs. A stale index must not be trusted as current live availability.

To avoid persistent output entirely, omit `--output` when building. Note that piping full metadata to other tools may expose names/descriptions; choose trusted destinations.

## Let a task use the index

```bash
python3 scripts/workflow_router.py examples/workflow-incident.json \
  --registry-snapshot /tmp/tuckbit-sample-index.json
```

The router ranks potential matches using local lexical overlap, reports only the name, provider, source, relevance score and explicit untrusted/authorization flags. It never incorporates arbitrary tool descriptions as executable instructions. This is **candidate discovery**, not accurate semantic classification, permission checking, or guaranteed tool existence.

## Privacy and security

- Metadata is **untrusted**; tool descriptions may contain prompt-injection attempts.
- No credentials, call arguments, tool output, full SKILL.md body or raw MCP input schemas are stored in the index.
- The registry does not grant, infer or cache permissions. Live availability and authorization must be checked by the actual host.
- Explicitly supplied file paths remain under user control. No hidden system instructions, provider state or model reasoning is read.
- Index freshness compares content, not only file modification time.
- Do not publish private capability metadata without review.

## What still needs work

Real client integration to obtain explicitly permitted active tool catalog snapshots; symbol/capability search effectiveness benchmarks; safe conflict handling for skill aliases and symlinks; schema-version invalidation across provider updates; explicit user approval for any richer indexing.

This first local implementation is **not evidence of lower agent token consumption**. Only task-level measurements can establish that.

**Current packaging boundary:** The registry command is distributed in the full repository, not in the standalone copied `SKILL.md` folder. A future dedicated CLI package or supported client adapter may expose it to portable skill installations after validation.
