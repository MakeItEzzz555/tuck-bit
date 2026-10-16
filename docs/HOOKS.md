# Optional task-entry hook adapters (experimental)

**Default: disabled.** TuckBit does not install, register or activate lifecycle hooks automatically.

The small, pure-Python `scripts/hook_advisor.py` reads a **single JSON event from stdin** and emits a short response appropriate to Claude Code or Gemini CLI. It never starts an agent, runs tools, reads project files, changes tool schemas, modifies reasoning settings or stores prompt text.

## Why an opt-in hook?

The user wants guidance **conditioned on the current prompt**. Host-provided hooks can supply that prompt before an agent turn, without requiring a TuckBit MCP server to run constantly. A hook is not a license to read hidden system instructions or model reasoning.

To avoid extra context on every unrelated message, the adapter:
- returns `{}` for prompts without obvious coding context;
- honors explicit requests not to use TuckBit;
- injects a short fixed advisory rather than the original prompt or source paths;
- emits no blocking/approval action and does not change tool permissions;
- has a strict input size bound, and fails open with empty output on invalid input.

This **does not** yet perform semantic task-contract extraction, measure model behavior, or enforce budgets. Hooks run on the critical path, and even short context injections can add token cost. Measure their value before using them broadly.

## Offline simulation

```bash
printf '%s\n' '{"hook_event_name":"UserPromptSubmit","prompt":"Fix the parser bug"}' \
  | python3 scripts/hook_advisor.py --host claude

printf '%s\n' '{"hook_event_name":"BeforeAgent","prompt":"Implement the API feature"}' \
  | python3 scripts/hook_advisor.py --host gemini
```

The output is an object with `hookSpecificOutput.hookEventName` and `additionalContext` only for matching tasks.

## Manual, explicit registration (reference only)

**Claude Code** supports `UserPromptSubmit` hooks. Developers can *manually* add a hook to a project-level Claude settings file after reviewing security and permission behavior:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 /absolute/path/to/tuck-bit/scripts/hook_advisor.py --host claude",
            "timeout": 3
          }
        ]
      }
    ]
  }
}
```

**Gemini CLI** supports `BeforeAgent` hooks:

```json
{
  "hooks": {
    "BeforeAgent": [
      {
        "hooks": [
          {
            "type": "command",
            "name": "tuck-bit-advisor",
            "command": "python3 /absolute/path/to/tuck-bit/scripts/hook_advisor.py --host gemini",
            "timeout": 3000
          }
        ]
      }
    ]
  }
}
```

These are **snippets for manual merging**, not complete replacement settings files. Do not overwrite existing settings, approvals or hook definitions. Use absolute paths from the installation being tested; remove the hook block to reverse activation.

The hook is **not** auto-registered in any plugin manifest, so simply installing TuckBit never activates it.

## Interoperability and limitations

Claude's event is `UserPromptSubmit`, Gemini's is `BeforeAgent`. Their payload/output shapes differ. Codex also has plugin hooks, but we have **not** validated an equivalent prompt-entry event for this adapter; don't install the Claude/Gemini adapter under Codex. Other hosts use the portable skill without this hook until a separately tested native adapter exists.

No-model event simulation and negative-trigger tests exist in `tests/test_hook_advisor.py`; actual in-client injection tests are pending.

Official specifications:
- https://code.claude.com/docs/en/hooks
- https://geminicli.com/docs/hooks/reference/
- https://geminicli.com/docs/hooks/best-practices/
- https://developers.openai.com/plugins/build/plugins
