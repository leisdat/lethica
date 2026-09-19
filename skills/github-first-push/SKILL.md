---
name: github-first-push
description: Push a fresh repo to GitHub via PAT. No gh CLI needed.
---

# GitHub First-Push (no gh CLI, PAT only)

When the user has a fresh local repo, no remote, and gives you a Personal Access Token (PAT) to push with, this is the playbook. No `gh` CLI required — works on any machine with `git` and `curl`. Pairs with the `github-auth` skill for the token mechanics.

## Pre-flight (do these in order)

### 1. Verify the token is valid

```bash
curl -s -H "Authorization: Bearer $TOKEN" https://api.github.com/user \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('login', d))"
```

If the response is `{"message": "Bad credentials"}` — stop. Tell the user the token is bad. Don't try to push anyway.

### 2. Learn the real GitHub username

The token's `/user` endpoint returns the canonical `login` for whoever issued it. **The user may give you a different username** (typo, old account, the username they *want* rather than the one they *have*). Always use what the API returns:

```bash
LOGIN=$(curl -s -H "Authorization: Bearer $TOKEN" https://api.github.com/user \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['login'])")
echo "GitHub login: $LOGIN"
```

### 3. Check the token's scopes

The `x-oauth-scopes` response header lists the token's scopes. **This is the most important pre-flight check** — pushing a `.github/workflows/*.yml` requires the `workflow` scope, not just `repo`:

```bash
curl -s -I -H "Authorization: Bearer $TOKEN" https://api.github.com/user \
  | grep -i "x-oauth-scopes"
# Example: x-oauth-scopes: repo, workflow
```

Common scope gates:
- `repo` — required for any code push
- `workflow` — required for pushes that add/modify `.github/workflows/*.yml`
- `delete_repo` — required for repo deletion via API
- `admin:org` — required to create repos in an org

## Create the repo

If the repo doesn't exist yet, create it via the API. The response is a 201 with the new repo metadata on success, or 422 (with `errors: [{resource: 'Repository', code: 'name_exists'}]`) if it already exists:

```bash
curl -s -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"<repo>","description":"<one-liner>","private":false}' \
  https://api.github.com/user/repos \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('OK:', d['full_name']) if 'full_name' in d else print('ERR:', d.get('message'))"
```

## Add the remote + push

### Rename the branch to `main` (GitHub convention)

```bash
git branch -m master main
```

### The credential helper form (mandatory)

**Do NOT embed the token in the remote URL** — the shell expands `***REMOVED***` inside URLs, breaking the auth. Use the helper form with `GIT_TERMINAL_PROMPT=0` so git never tries to read a password from stdin:

```bash
cd /path/to/local/repo
git remote add origin "https://github.com/${LOGIN}/<repo>.git"

GIT_TERMINAL_PROMPT=0 \
  git -c credential.helper='!f() { printf "username='"$LOGIN"'\npassword='"$TOKEN"'\n\n"; }; f' \
  push -u origin main
```

The `printf` format must end with `\n\n` (two newlines) — git's credential protocol uses a blank line as the message terminator.

## Pitfall: the `workflow` scope gate

If the repo includes `.github/workflows/*.yml` and the token lacks the `workflow` scope, push will fail with:

```
remote: Invalid username or token.
remote: refusing to allow a Personal Access Token to create or update
        workflow `.github/workflows/ci.yml` without `workflow` scope
```

**Recommended fix**: ask the user to regenerate the PAT with the `workflow` scope added (classic PAT: Settings → Developer settings → Personal access tokens → Tokens (classic) → Edit → check `workflow`).

**Stopgap fix** (lets the rest of the repo push, but the workflow file stays local-only until the PAT is upgraded):

```bash
# 1. Move the workflow file aside (it'll be restored later)
mv .github/workflows/ci.yml .github/workflows/ci.yml.pending

# 2. Remove from index but keep on disk
git rm -r --cached .github/workflows/

# 3. Commit + push
git commit -m "ci: temporarily remove workflow (PAT lacks 'workflow' scope)"
GIT_TERMINAL_PROMPT=0 git -c credential.helper='!f() { ... }; f' push -u origin main

# 4. Reset to remote, restore the file
git reset --hard origin/main
mv .github/workflows/ci.yml.pending .github/workflows/ci.yml
git add .github/workflows/ci.yml
git commit -m "ci: restore workflow (push via UI or upgraded PAT)"
# this commit will fail to push until the PAT is upgraded — that's expected
```

The stopgap leaves the workflow file in the local repo, on the `main` branch locally, but un-pushed remotely. The user can either (a) regenerate the PAT and `git push`, or (b) drag-and-drop the file via the GitHub web UI.

## Verifying the push

```bash
# List commits on remote
curl -s -H "Authorization: Bearer $TOKEN" \
  https://api.github.com/repos/${LOGIN}/<repo>/commits \
  | python3 -c "import sys,json; [print(f'  {c[\"sha\"][:8]} {c[\"commit\"][\"message\"][:60]}') for c in json.load(sys.stdin)]"

# List top-level files
curl -s -H "Authorization: Bearer $TOKEN" \
  https://api.github.com/repos/${LOGIN}/<repo>/contents/ \
  | python3 -c "import sys,json; [print(f'  {i[\"type\"][0]} {i[\"name\"]}') for i in json.load(sys.stdin)]"
```

## Why not `gh`?

If `gh` is installed and authenticated, prefer it. The whole flow above becomes:

```bash
gh repo create <repo> --public --source=. --remote=origin --push
```

`gh` handles credentials, remote setup, and the initial push in one command. The PAT-based flow above is the fallback for headless servers, minimal Docker containers, or machines where installing `gh` isn't possible.

See `github-auth` for the broader auth setup, including gh's own quirks on headless boxes.
