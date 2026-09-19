# `core/policy.py` — command allowlist patterns (v0.5)

The agent's `shell` tool is policy-gated. `core/policy.py` checks every command against an allowlist before passing to subprocess. The right pattern is **regex on the leading verb** (not full-path string match), so a single regex entry covers `du -sh`, `du /tmp`, etc.

## Working set (v0.5)

```python
import re

ALLOW_VERBS = (
    r"timeout|wc|stat|head|tail|du|df|ls|"
    r"cat|file|find|grep|rg|tr|cut|sort|uniq|"
    r"echo|pwd|whoami|date|uname|hostname|"
    r"mkdir|rmdir|touch|chmod|chown|"
    r"cp|mv|ln|readlink|realpath|"
    r"ps|pgrep|top|free|uptime|"
    r"curl|wget|http|ping|nslookup|dig|"
    r"node|python|python3|bash|sh|"
    r"pm2|git|"
    r"sed|awk"
)

def is_allowed(cmd: str) -> bool:
    cmd = cmd.strip()
    # extract first token
    first = cmd.split(None, 1)[0] if cmd else ""
    if not first:
        return False
    # strip path prefix
    base = first.rsplit("/", 1)[-1]
    return re.match(rf"^({ALLOW_VERBS})\b", base) is not None
```

## Why not `startswith`?

- `cmd.startswith("du")` would block `dummy_tool` if it existed as a binary.
- `cmd.startswith("du ")` requires you to remember the space — but commands like `du` alone (no args) are valid.
- `re.match(r"^du\b", cmd)` handles both `du` and `du -sh /tmp` correctly.

## Why not allow everything?

The Termux shell is unconstrained by default. The agent's "shell" tool runs subprocess directly. If a skill or a planner LLM hallucinates `rm -rf ~`, it executes. The allowlist is a **first line of defense**, not a security boundary. Pair with:
- `cwd` pinning to `~/agent/sandbox/`
- argument-allowlist for `rm`, `mv` (no `-rf` patterns)
- max output bytes (truncate after 64 KB)
- timeout per command (30s default)

## Verbs NOT in the allowlist (intentional)

- `rm` — too dangerous; use `rm` only via explicit `file_write` overwrite
- `bash` / `sh` as a command — opens arbitrary script execution; only `python` and `node` are safer interpreters
- `sudo` / `su` — not present on Termux anyway
- `dd` — bit-level device access

## Adding a new verb

1. Add it to `ALLOW_VERBS`
2. Restart the agent (registry + policy cache both reload)
3. Verify: `python -m agent "test the new verb" --budget-iters 2`
4. If the test fails with "blocked", check the verb spelling and that the binary exists on PATH (`which <verb>`)

## Common gotchas

- **Binary not on PATH.** If `rg` is in `~/bin/rg` but not exported, the agent can't call it. Either symlink to `/data/data/com.termux/files/usr/bin/` or extend `PATH` in `__main__.py` before policy loads.
- **Compound commands (`&&`, `|`, `;`).** The current policy treats them as a single string and matches only the first verb. Either allow them explicitly (and accept the risk) or split on shell operators before matching.
- **Backticks / `$()`.** Same problem as compound commands — the first verb is the only one checked. If you need subshells, route them through a named skill instead.
