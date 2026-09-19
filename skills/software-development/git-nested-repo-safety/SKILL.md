---
name: git-nested-repo-safety
description: Use git add in a Termux subdir only with explicit paths.
---

# Git Nested-Repo Safety

## When to use
- Before `git add` / `git commit` inside any subdir that might be tracked by a larger parent repo.
- Working inside `~/lethica`, `~/routerku`, `~/.hermes`, or any project folder under `~`.
- You see `warning: adding embedded git repository` or git hangs for >30s during `add`.
- Triggers: 'commit this', 'push', 'git add', 'embedded git repository' warning, git hangs on add/commit.

## The Trap

On Termux the home directory `~` is itself a git repo, and project folders like `~/lethica`, `~/routerku`, `~/.hermes` are tracked *inside* it — not as their own repos. Running `git add -A` or `git commit -A` **from inside the subdir** spiders the entire home and tries to stage `.cargo/`, `.npm/_cacache`, `backups/`, and any *embedded git repos* (`.hermes/hermes-agent`, `workspace/.../obsidian-skills`). This:
- Hangs for minutes on embedded repos (git walks the nested `.git`).
- Triggers `warning: adding embedded git repository` and `hint: git submodule add ...`.
- Pollutes history with thousands of unrelated files.

A subdir `~/lethica` with no `.git` of its own is NOT an independent repo — `git rev-parse --show-toplevel` returns `~`, not `~/lethica`.

## Pre-flight (every time, before staging)

```bash
git rev-parse --show-toplevel     # if this prints a PARENT dir (e.g. /data/.../home),
                                   # you are inside a larger repo — do NOT `git add -A`.
```

If it returns the parent, stage **explicit paths only** from the parent's working tree:

```bash
cd ~
git add lethica/.gitignore lethica/core/ lethica/lethica.py lethica/lethica_bridge.py \
        lethica/config.toml lethica/changelog.md lethica/.lethica_version
git status --short lethica/          # confirm ONLY lethica/ paths are staged
```

## Required .gitignore (project root)

Drop a `.gitignore` at the project root to keep runtime/state out of history:

```
__pycache__/
*.pyc
*.pyo
http-cache.db
workspace-index.db
history.json
workspace/
sessions/
logs/
memory/
snapshots/
backups/
deprecated/
*.bak
*.bak-*
.cargo/
.hermes/
```

Then un-track any already-committed pyc so the ignore takes effect:

```bash
git rm --cached -r --quiet lethica/core/__pycache__/
```

## Commit

- Write the message describing the *why* (the cleanup/feature), keep it atomic.
- Never `git add -A` from a subdir of a large parent repo. Ever.
- If a commit hangs >60s on `add`, cancel, run `git reset -q HEAD <path>` to unstage, and switch to explicit-path staging.

## Embedded repo already staged?

```bash
git reset -q HEAD <path>                 # unstage everything
# then re-add with explicit paths (see above)
# to stop the embedded-repo warning for a dir you DO want tracked as files:
#   git rm --cached -r <embedded/.git parent>  (or add to .gitignore)
```

## Verification

- `git status --short <project>/` shows ONLY project files — no `.cargo`, no `.npm`, no `__pycache__/*.pyc`, no embedded `.git`.
- `git log --oneline -1 -- <project>/` shows your commit touching only intended paths.

## Red Flags
- `warning: adding embedded git repository` → stop, unstage, use explicit paths.
- `git add` running >30s → it's spidering the home; cancel.
- `git status` showing `.npm/_cacache`, `.cargo`, `.bash_history` as modified → you operated from the wrong toplevel.
