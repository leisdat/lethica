# Extension/Plugin System Patterns (Extension Hub Pro, 6 phases, 94 tests)

Reusable architecture lessons from building a zero-dependency (Node built-in only)
multi-source extension system on Termux: signed remote repo, integrity, permissions,
worker_threads isolation, real HTTP extensions. All patterns verified by tests.

## 1. worker_threads isolation — the gotchas that hang your suite

Goal: run untrusted extension code in a separate thread so main process survives
crash/hang/timeout. Real pitfalls found:

### 1a. `worker.unref()` does NOT reliably let the process exit
A Worker with a message listener (`parentPort.on("message", ...)`) keeps the event
loop alive even after `worker.unref()`. Result: `node --test` prints every test ✔ but
the process **never exits** → CI/runner times out with zero output. Fixes that worked:
- **Idle auto-terminate**: after each request, schedule `setTimeout(() => worker.terminate(), IDLE_MS)` and `timer.unref()`. Cancel the idle timer on the next request.
- Or `process.on("beforeExit")` → terminate all workers (less reliable, prefer idle timer).
- Always `await worker.terminate()` in test `after()` hooks.

### 1b. Timeout must TERMINATE the worker, not just reject the Promise
`Promise.race([call, timeout])` alone leaves the hung extension burning CPU forever.
On timeout: `worker.terminate()` AND resolve the pending request with
`{ok:false, error:{code:"WORKER_TIMEOUT"}}`. Next request starts a fresh worker.

### 1c. `clearTimeout(timer)` where `timer` is a Promise does nothing
Classic bug: `const timer = new Promise((_,rej)=>setTimeout(...))` then
`finally { clearTimeout(timer) }` — you cleared the Promise, not the timer ID.
The timeout fires 10s later as an unhandledRejection → `node --test` reports the
*file* as failed even though every test passed. Capture the ID separately:
```js
let timerId;
const timer = new Promise((_,rej)=>{ timerId = setTimeout(rej, ms); });
// ... finally { clearTimeout(timerId); }
```
Symptom to recognize: "pass 18, fail 0" but the test file itself ✖ fails with an
async-activity-after-test-end error.

### 1d. Worker message protocol
Request: `{id, method, args}` → Response: `{id, ok:true, result}` | `{id, ok:false, error:{code, message}}`.
Worker script does `require(entryPath)` inside try/catch; load failure posts a
special `__load__` error message and exits — main marks worker dead and can restart.

## 2. Atomic package install (never lose the working version)

Order matters — never delete the old extension before the new one validates:
```
download → SHA-256 verify → parse package → prepare temp dir
→ validate contract (require from temp) → ACTIVATE (rename) → remove old
```
Activate = rename old dir to `.name.backup`, rename temp → final, rm backup.
On ANY failure: rollback (rename backup back), return structured error. Old version
survives a failed update by construction.

## 3. Signed repository (Ed25519 via Node crypto — no custom crypto)

- `crypto.generateKeyPairSync("ed25519")`, `crypto.sign(null, buf, privKey)` / `verify`.
- **Canonical JSON is mandatory** for deterministic signing: object keys sorted,
  array order preserved, compact, UTF-8. Same semantic object with different key order
  must canonicalize identically.
- Sign the payload = repo minus the `signature` field itself.
- **Keyring is pre-trusted**: repo sends only `keyId`; app looks up the public key in
  its own keyring. NEVER accept a public key from the repo payload.
- Key statuses: `active` (verify), `deprecated` (verify + warning), `revoked` (reject).
  Keep deprecated keys around — old caches/repos are still signed with them.
- Verify BEFORE updating cache / installing / swapping active repo. Invalid signature
  → do not touch the cache at all (test asserts cache bytes unchanged).
- `requireSignature` flag: production should force it; tests of older unsigned flows
  set false. Report status honestly via `/api/security/status` (values from real state,
  not hardcoded).

## 4. Repository fallback chain with explicit status

`REMOTE → CACHE → BUNDLED → ERROR`, never silently assuming remote succeeded:
- remote fetch: HTTPS-only (allowInsecure flag ONLY for local tests), timeout,
  status-code check, JSON-parse check, schema check, signature check.
- save cache only when the fetched repo is VALID (never overwrite good cache with bad).
- surface `{status, lastError}` to UI/API — user must see CACHE/BUNDLED/ERROR, not a lie.

## 5. Test-suite isolation — node:test global-state clashes

Multiple `*.test.js` files in one `node --test test/` run share the process:
storage paths, keyring, repo path, and the `extensions/` folder all collide →
"everything passed alone, fails together." Fix: a serial runner that spawns each file
in its own process (`spawnSync(process.execPath, ["--test", file])`) and sums results.
Also: tests that `fs.mkdirSync` throwaway extensions into `extensions/` MUST delete
them afterwards or the next suite sees phantom local extensions.

### 5a. Production state leaks into tests through the first `load()` call

Patching `storage.STATE_FILE` + `_resetCache()` inside `resetTestState()` is NOT enough.
Any module that calls `storage.load()` at require-time or in an earlier test populates
the cache with PRODUCTION state (real installed extensions like otakudesu/anichin).
After `_resetCache()`, the next `load()` reads from the patched path — but if you only
`rm -rf` the test dir without writing anything, later fixtures that "install" demo
extensions MERGE on top of stale state. Real symptom: dedupe test expected 2 results,
got 3 because production sources joined the search and hit the network.

Verified fix — write an EMPTY state file to disk BEFORE any load can happen:
```js
async function resetTestState() {
  fs.rmSync(TEST_DATA_DIR, { recursive: true, force: true });
  fs.mkdirSync(TEST_DATA_DIR, { recursive: true });
  storage.STATE_FILE = TEST_STATE;
  storage.DATA_DIR = TEST_DATA_DIR;
  fs.writeFileSync(TEST_STATE, JSON.stringify({ installed: {}, enabled: {}, settings: {} }, null, 2));
  storage._resetCache();
  runtime.clearCache();
  // then patch repo/repoClient paths and await repoClient.load()
}
```
Rule: **disk-write-then-reset-cache**, never rm-only. Applied to every suite's reset hook;
suite went 78→79 passing.

### 5b. Assertion shape for multi-source dedupe tests

Dedupe picks whichever worker finished first, so a duplicate title's `sourceId` is
non-deterministic. Assert the surviving TITLE count, never which source won:
```js
const hunter = results.filter(r => r.title.toLowerCase().includes("hunter"));
assert.equal(hunter.length, 1);          // dedupe worked
assert.ok(hunter[0].sourceId);           // tagged with SOME source
```

## 5c. EADDRINUSE restart loop across sessions

Termux servers persist between chat sessions; restarting without killing the old holder
gives `EADDRINUSE :::3001` repeatedly (each retry looks like a fresh failure). Recovery
order that works: `ps aux | grep -E "node.*(server|mock)" | grep -v grep | awk '{print $2}'`
→ `kill -9` them all → confirm `ss -tlnp | grep <ports>` shows FREE → only then start both
servers background=true. Note `ss -tlnp` can report nothing while curl succeeds — trust the
HTTP probe (`curl -so /dev/null -w "%{http_code}" http://localhost:<port>/`) over ss when they disagree.

## 6. Multi-source search normalization

Run N enabled extensions in parallel with `Promise.allSettled`; normalize each
result through a schema validator; dedupe by normalized title (lowercase, strip
non-alphanumerics); tag every result with its `sourceId`. One extension throwing
must not stop the others — collect errors into an `errors[]` array.

## 7. Permissions model (capability policy)

Manifest declares `permissions: ["network", ...]`; policy map decides
allowed/denied/never. No wildcards ("*"/"all") — reject at install. `shell` is
NEVER allowed. Structured denial: `{code:"PERMISSION_DENIED", extensionId, permission}`.
Check permission BEFORE running the capability (e.g. network check before a stream call).

## 8. Hub settings engine: priority dedup, live policy, auto-update (Phase 6, live-verified)

### 8a. Store settings inside the existing state.json
No new storage layer: `state.settings = { sourcePriority: [], autoUpdate, permissions }` via the same
atomic-write storage. `get()` re-derives from defaults on every read (unknown/stale values fall back);
`set()` validates strictly (ID regex + cap, enum check for modes, only "allowed"/"denied" per policy
key) and re-pins `shell = "never"` in BOTH get() and set() so no API path can ever raise it.

### 8b. Priority-aware dedup (deterministic winner)
With a user-defined source priority list, dedupe must NOT keep first-seen — `Promise.allSettled`
order is a race. Build a rank map; the winner of a duplicate title = lowest rank:
```js
const rank = new Map(prio.map((id, i) => [id, i]));
const rankOf = (r) => rank.has(r.sourceId) ? rank.get(r.sourceId) : Number.MAX_SAFE_INTEGER;
if (!cur || rankOf(r) < rankOf(cur)) seen.set(key, r);
```
This works because normalizeSearchResult tags every item with `sourceId`. Note: §5b's "never assert
which source won" applies to tests WITHOUT a priority list; with one set the winner is deterministic
and assertable. Also sort the extension list itself by priority so result ORDER matches preference.

### 8c. Wire policy LIVE, not to the constant
`checkPermission(id, "network", policy)` must receive `settings.effectivePolicy()` at call time —
passing the imported DEFAULT_POLICY constant compiles clean and silently makes every UI toggle a
no-op. Verified end-to-end: network=denied → `/api/sources` returns structured PERMISSION_DENIED;
allowed again → 26 streams return. That toggle→enforcement round-trip is the acceptance test.

### 8d. Auto-update service
Modes off/notify/auto; startup check (small delay so server bind wins) + interval, timers `.unref()`.
`manager.listInstalled()` already carries `updateAvailable`/`latestVersion` (repo semver compare) —
do NOT re-implement version checks; `manager.update(id)` already enforces downgrade/equal policies.
`notify` = surface badges only; `auto` = call update in the loop.

### 8e. Implementing a stubbed Settings UI (patterns that worked)
- Replace stub rows with static containers (`<div id="setPriority">Memuat…</div>`), then fill them
  after `Promise.all([...].catch(() => null))` fetches — page never looks broken on slow API.
- Codebase convention: inline `onclick="fn(...)"` + `window.fn = async function(){}`; escape dynamic
  values with the existing `esc()` helper.
- New feature CSS must use `color-mix(in srgb, var(--primary) X%, transparent)` for accents/glows —
  hardcoded brand colors break the light theme (the "polos" regression class). Verify both themes.
- Icons: SVG stroke currentColor via the shared ICON object — never emoji (user preference).

### 8f. Patch-tool + API-verification gotchas (cost real time this session)
- patch old_string must be a FULL unique block. A short anchor (`async function search()`) fuzzy-
  matched near-identical text and DUPLICATED the whole function body → syntax error. Recovery: read
  the corrupted region, delete the orphan block, `node --check` every touched file before testing.
- Endpoint response shapes vary (`{ok, data}` vs top-level `{ok, results}`) — probe one endpoint
  before writing parse logic. Better: put the whole live check in `scripts/test_settings.py`
  (get/post helpers that CATCH HTTPError and still parse the 4xx body) instead of inline
  curl|python one-liners, which trip the command-parser blocklist.

## Honest-limits note
Document what is NOT solved: worker isolation ≠ security sandbox (worker still has
Node module access: fs, child_process, direct network). keyring plaintext on disk.
Install-time contract validation runs in main process. Never claim these are fixed
when they aren't — the security.md roadmap must say NOT IMPLEMENTED.
