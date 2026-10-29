# Using TuckBit with Headroom

**Status: opt-in companion tools.** No combined savings have been measured.

[Headroom](https://github.com/headroomlabs-ai/headroom) (Apache-2.0) compresses what an agent reads (tool output, logs, files, history) before it reaches the model, through a proxy, a library or `headroom wrap <agent>`. TuckBit works earlier in the process: it decides which tools and context to fetch in the first place. The Observatory checks what actually happened. They are complementary layers:

| Layer | Question it answers | Tool |
|---|---|---|
| Selection | Should this context be fetched at all? | TuckBit skill |
| Compression | How small can the fetched context be made? | Headroom |
| Measurement | Did the bill and the outcome actually improve? | Observatory |

## Why measure, not assume

Fewer input tokens do not guarantee lower cost. Providers bill cached input far below uncached input, and a compressor that changes the prompt between turns can stop the prompt cache from hitting. A session can then send fewer tokens and still cost more. Headroom's own lossless agent mode keeps output deterministic for this reason.

## Compare your own sessions

Run comparable work without and then with the compressor, and select the session files yourself:

```bash
python3 scripts/headroom_compare.py \
  --without a.jsonl b.jsonl --with c.jsonl d.jsonl \
  --prices '{"uncached_input_per_million":3,"cached_input_per_million":0.3,"output_per_million":15}'
```

The output gives per-session means of observed input, cached, uncached and output tokens, the cache fraction, and an optional **configured** cost scenario (your prices, not provider billing). It sets flags such as `cache_fraction_decreased` and `fewer_input_tokens_but_configured_cost_not_lower`.

**Sample unit:** unique complete sessions. A session counts as complete when its input, cached input, uncached input and output were all observed (none marked `estimated`), and cached plus uncached equals input. A session ID selected in both arms is refused even when one copy is incomplete. Incomplete sessions are counted separately (each unique session once) and never averaged in. An arm with no complete session has no mean; it is never shown as a zero.

**Configured cost:** you supply three finite rates per million tokens, each between 0 and 1,000,000. NaN, infinity, booleans and missing or extra fields are refused with `invalid_prices`. The cost is computed only when every session in both arms shares one known provider and model, none is a control or demo, and no cache writes were observed. Otherwise `cost_unavailable_reason` explains why. This matches the dashboard's legacy configured scenario and is never a bill, tier, subscription or cache-write price.

**Errors** are bounded codes, with no file contents, paths or tracebacks: `unreadable_file`, `unsupported_file`, `size_limit` (files over 4 MiB are refused before they are read whole), `invalid_prices`, `session_in_both_arms`, `conflicting_session`, plus the importer's own codes. Only the files you name are read.

Sessions are user-selected, not matched tasks, and success is not assessed. Arms can differ in task difficulty, so differences are observations, not proven or causal savings.

## Lossless JSON densification (`scripts/json_densify.py`)

This is a stdlib-only implementation of the idea behind Headroom's agent-mode compaction. A uniform JSON array of flat objects becomes a schema header plus CSV rows:

```
[3]{id:int,name:string,ok:bool}
1,alpha,true
...
```

Dense text is returned only when decoding it reproduces the **parsed JSON value** exactly (structure, key order, and the distinctions between string, int, float, bool and null) and the result is shorter. This is value equality, not byte equality: whitespace and number spelling such as `1.50` or `1e2` are not kept.

The original is returned unchanged for:
- nested values, mixed column types, or an empty string next to null;
- duplicate keys, NaN or infinity, or lone surrogates;
- malformed input or input over 4 MiB (the command-line tool refuses files over 4 MiB with `size_limit` instead of reading them whole);
- arrays that are not at the top level.

The command-line tool reports characters and UTF-8 bytes, never tokens. The densifier is opt-in and is not connected to agent execution. Character reduction is not token or cost reduction until it is measured with the comparison above on successful tasks.
