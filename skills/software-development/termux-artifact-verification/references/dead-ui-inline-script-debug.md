# Debugging a dead UI: inline `<script>` syntax errors (Termux, no browser console)

Session-verified path from Extension Hub Pro (mobile-first single-file HTML app on Termux).

## Symptom
Page loads, CSS renders, but EVERY button/nav/tab is dead (clicks do nothing).
Cause: one JS syntax error anywhere in the inline `<script>` → the whole script
fails to parse → no event handlers are ever attached. The UI looks fine but is
inert. This is NOT a per-feature bug.

## Verification (Termux, no browser devtools)
1. Extract the script to a temp file and syntax-check with Node:
   ```bash
   node -e "const m=require('fs').readFileSync('app/ui/index.html','utf8').match(/<script>([\s\S]*?)<\/script>/); require('fs').writeFileSync('~/tmp/ui-check.js', m[1])"
   node --check ~/tmp/ui-check.js
   ```
   (`/tmp` is unwritable on Termux — use `~/tmp`.)
2. `node --check` gives a line + caret. The caret can land a few lines AFTER the
   real culprit because the parser recovers at the next statement boundary —
   check the surrounding lines, not just the caret line.
3. Do NOT binary-search the file with `new Function(slice)` — `new Function`
   cannot compile mid-function slices or `async function` declarations, so it
   produces false "missing ) after argument list" errors at wrong lines and
   wastes time. Use `node --check` on the whole extracted script instead.
4. For huge files, a per-line paren-depth counter (open `(` vs close `)`,
   respecting string literals) localizes the unbalanced paren fast.

## Root-cause pattern (the actual bug)
Building a big HTML string with a nested chain:
```js
renderSheet(
  '...' 
  + genres.map(g => '<span>' + esc(g) + '</span>').join('')
  + (episodes.length
      ? '<div>' + episodes.map(ep => '...' + esc(ep.title || ('E' + ep.number)) + '...').join('') + '</div>'
      : stateBox('📭', 'x', 'y'));
);
```
One stray paren inside this kills the entire script (dead UI). The ternary +
arrow-function + string-concat nesting is fragile and hard to audit.

**Safer pattern — stepwise accumulation:**
```js
let body = '<div class="sheet-head">' + esc(sourceId) + '</div>';
body += '<div class="tags">';
for (const g of genres) body += '<span>' + esc(g) + '</span>';
body += '</div>';
if (episodes.length) {
  let list = '<div class="ep-list">';
  for (const ep of episodes) {
    const label = ep.title || ('Episode ' + ep.number);
    list += '<div class="ep-item">' + esc(label) + '</div>';
  }
  list += '</div>';
  body += list;
} else {
  body += stateBox('📭', 'Belum ada episode', '...');
}
renderSheet(body);
```
Same output, no nesting, and a wrong paren can't kill the whole script.

## Node test-suite pitfalls (multi-file suites, hit the same session)
- `node --test` reporting a suite as `tests 1, pass 0, fail 1` when the file has
  N tests means the FILE crashed before any test ran (throw in `before()` or
  top-level). Read the raw output ABOVE the summary — the summary line alone
  hides the real error (EADDRINUSE, `Assignment to constant variable`, etc.).
- Reassigning a `const` after `server.listen()` (e.g. capturing an OS-assigned
  port) throws `TypeError: Assignment to constant variable`. Use `let` for
  ports captured after listen.
- Fixed mock-server ports collide with a production instance of the same server
  already running in the background. Use `server.listen(0)` and read
  `server.address().port`. Any consumer env var (e.g. extension base URL) must
  be set AFTER the port is known — in `before()`, not at module load.
- Shared state leakage: a running server's `.data/state.json` (installed/enabled
  extensions) bleeds into lifecycle tests that assume only bundled extensions
  exist. A newly added bundled extension then shows up in old tests'
  multi-source results. `rm -rf .data*` before the suite, or isolate each
  suite's state dir.
