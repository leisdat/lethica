# Background processes in Termux (without PM2)

Use this when a one-off Python/Node server needs to run outside Hermes but PM2
is overkill (e.g. a tool you're testing for 10 minutes, a debug instance, a
quick API proxy). PM2 still wins for anything long-lived; see
`pm2-termux-process-management.md` for that path.

## /tmp/ is ephemeral — write logs to $HOME

`/tmp/dsk.log`, `/tmp/server.log`, etc. are NOT persistent across shell sessions
on Termux — when a backgrounded process detaches and its parent shell exits, the
tmpfs may be cleared. Symptom: server backgrounded via `nohup ... &` writes
nothing to `/tmp/x.log`, no errors either, just silent.

Fix: always log to `~/` or another persistent path.

```bash
cd ~/deeperseeker && nohup python app.py > ~/dsk.log 2>&1 & disown
```

## Zsh disown gotcha

Termux default shell is zsh. `&` alone often detaches but the child is still a
zsh job — and when the parent shell exits, SIGHUP can still propagate in some
cases. The reliable pattern is `nohup ... & disown` (both), with stdout+stderr
redirected:

```bash
nohup python app.py > ~/log 2>&1 & disown
```

`disown` only removes the job from the shell's job table; it does NOT make the
process ignore SIGHUP. That's `nohup`'s job. Use both.

## pkill -f matches its own argv

If you run `pkill -f "app.py"` in a shell whose own command line contains
"app.py" (e.g. a `pkill` launched inside a bash subshell that itself uses an
`app.py` path), pkill can match the shell PID and kill the shell.

Safer patterns:

```bash
# Prefer pgrep + kill, scoped to a specific command
pgrep -f "python app.py" | xargs -r kill -9

# Or pkill only python interpreters whose argv is literally your script
pkill -9 -f "^python .*app.py"
```

After killing, verify with `ps aux | grep <unique-string>` — the unique
substring matters; "app.py" alone can match unrelated processes.

## Verify the process is actually running

After backgrounding, ALWAYS:

1. `sleep 1` then `pgrep -af <unique-substring>` — confirm PID.
2. `curl http://127.0.0.1:<port>/health` or any endpoint — confirm it responds.
3. `tail -n 30 ~/log` — confirm it didn't crash in startup.

Background "success" with no PID, no curl response, and an empty log file = the
process died immediately. Read the log; it usually says why.

## KILL flag = force-kill, not graceful

Hermes terminal may surface a "Command was flagged (force kill)" response when
the runner detects a runaway process; that's NOT a real failure of your server
— it's a meta-signal from the runner. The next foreground command runs fine.

## Skipping headless-browser cookie generation in Playwright-dependent stacks

Pattern (from deeperseeker reverse-proxy): if a Python HTTP proxy calls
`playwright` + `chromium` in `_generate_cookies()` on every cache miss, but the
cookies are only needed for AWS WAF / file upload — you can gate it behind an
env var so chat endpoints work without a browser installed:

```python
# functions.py
def get_cookies():
    if os.getenv("DEEPERSEEKER_SKIP_AWS_COOKIES") == "1":
        return []  # chat path doesn't need WAF cookies
    cache = get_cache()
    if cache and get_cookies_valid(cache):
        return cache["cookies"]
    if os.getenv("DEEPERSEEKER_HEADLESS") == "0":
        return _generate_cookies(headless=False)
    return _generate_cookies(headless=True)  # needs playwright
```

Then start server with `DEEPERSEEKER_SKIP_AWS_COOKIES=1 nohup python app.py ...`
to test the chat path on Termux (where playwright+chromium install is painful).
Verify the upstream API actually accepts requests without WAF cookies before
relying on this — many DO (they return `40002 Missing Token` for the auth
header, not 403/401 for cookies), which is the signal that cookies aren't
required for the chat path.

## Bearer-token-only APIs vs cookie+token APIs

If `curl -H "Authorization: Bearer <token>" https://api...` returns 200 but
`curl https://api...` (no headers) returns 400/401 with a "Missing Token" code,
the upstream uses token-only auth and doesn't need cookies. FastAPI reverse
proxies that wrap such APIs can skip the entire cookie-fetch path with the env
gate above.

## Diagnosing "500 Internal Server Error" from a Python reverse proxy

1. Read the proxy's stdout log — usually the traceback is there.
2. If log empty, the exception happened upstream and was swallowed: add a
   `try/except` around the upstream call that logs `response.status` and
   `await response.text()` for non-2xx.
3. Token expired / rotated: upstream returns `40003 invalid token` or
   `40002 missing token`. Refresh the token in the upstream DB and restart the
   proxy. The proxy itself is fine.
4. Cloudflare interstitial: upstream returns HTML instead of JSON, which makes
   `response.json()` raise. Detect with `content-type` header and treat as
   "upstream blocked — rotate IP / use cookie auth path".
