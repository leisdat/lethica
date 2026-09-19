# Deploying Node apps from Termux to PaaS (GitHub → Vercel/Render)

Session-validated flow (Aug 2026, NOVA `~/extension-hub-pro`): GitHub PAT (fine-grained)
→ push repo → Vercel CLI (UI) → Render (backend). Verified up to the Vercel deploy
(HTTP 200 + correct Cache-Control headers). The Render/Blueprint leg was handed to the
user's browser and NOT yet verified — do not assume it works; re-check after.

## Auth: GitHub PAT from Termux (fine-grained)

- `pkg install -y gh` works on Termux (aarch64 build exists). BUT
  `gh auth login --with-token` **rejects fine-grained tokens** with
  `error validating token: missing required scope 'read:org'` — fine-grained tokens
  have no classic scopes. Do NOT fight this.
- Verify a token without gh:
  `curl -s -H "Authorization: Bearer <tok>" https://api.github.com/user` → check `login`.
  **Pitfall: the token may belong to a different account than the user assumes** (e.g.
  user said repo should go to account A, token is account B's). Confirm `login` FIRST,
  then ask which account to push to before creating anything.
- Create repo without gh: `curl -s -X POST -H "Authorization: Bearer <tok>" -H "Content-Type: application/json" -d '{"name":"<repo>","private":false}' https://api.github.com/user/repos`.
- Push without persisting the token (token URL, never stored in `.git/config`):
  `git push "https://x-access-token:<tok>@github.com/<owner>/<repo>.git" main`
  If the remote already exists, `git remote set-url origin https://github.com/<owner>/<repo>.git` (clean) afterward.
- Before pushing a PUBLIC repo, scan for secrets:
  `grep -rn "ghp_\|github_pat_" --include="*" -l . | grep -v node_modules` and
  `git ls-files | grep -iE 'key|\.pem|\.env'` — `sk-` matches are often false positives
  (e.g. "skip"); verify each hit is actually a token before panicking.

## Vercel CLI on Termux (validated)

- `npm i -g vercel` installs fine (Node 24). Login = device flow:
  `vercel login` in `terminal(background=true)`, poll the process for
  `https://vercel.com/oauth/device?user_code=XXXX-XXXX`, user opens it in phone
  browser + approves. Poll again → "You are now signed in".
- Static deploy with a custom output dir + API rewrites: `vercel.json` at repo root
  with `"framework": null, "buildCommand": null, "outputDirectory": "app/ui"`.
  Deploy: `cd <repo> && vercel --yes --prod`. Vercel auto-links to the matching
  GitHub repo name and aliases `<repo-name>.vercel.app`.
- **vercel.json pitfall (validator error, cost a round-trip):** `headers[].source`
  patterns reject `?` mid-pattern — `"/((js|css|fonts|assets)/?.*)"` →
  `Header at index 0 has invalid source pattern`. Use one entry per directory with
  the `:path*` wildcard: `"/js/:path*"`, `"/css/:path*"`, etc.
- Cache-Control policy the user wants (consistent with local server):
  `/js/`, `/css/` → `no-cache` (phone browsers aggressively reuse stale JS — the
  recurring "old UI" bug); `/fonts/`, `/assets/` → `public, max-age=86400`.
- Verify after deploy: `curl -s -o /dev/null -w "%{http_code} %{size_download}B" <url>/`,
  one asset fetch + `curl -sI <url>/js/x.js | grep -i cache-control`, and one
  `/api/...` call to confirm the rewrite/proxy target state.

## Backend PaaS from Termux

- **Railway CLI has no npm build for android-arm64** (same class of problem as
  wrangler/workerd) → use the web dashboard (Deploy from GitHub repo) or the Railway
  REST API. User's Railway account was unavailable that session ("gk bisa udah ke pake").
- **Render** fallback (free tier, same UX as Railway): `render.yaml` at repo root
  (Blueprint) so the deploy is explicit instead of auto-detect:
  ```yaml
  services:
    - type: web
      name: <repo>
      runtime: node
      region: oregon
      plan: free
      buildCommand: npm install
      startCommand: npm start
      healthCheckPath: /api/health
  ```
  Requires a light `/api/health` liveness route in the app (pure
  `{ok:true,status:"up"}`, no compute) — add it to the app if missing.
  User flow: render.com → Sign in with GitHub → New → **Blueprint** → pick repo.
  Free tier sleeps after ~15 min idle; first request after wake is ~5-15 s cold start
  — tell the user this is expected, not a bug.

## Split-deploy pattern (validated architecture)

- Static UI → Vercel (`outputDirectory`), backend Node server → PaaS web service.
- `vercel.json` `rewrites` proxy `/api/:path*` + `/downloads/:path*` to the backend
  URL so the UI keeps relative fetches (`API=''`) unchanged.
- Backend must: handle `PORT` env, pure-JS deps only (no native modules), and write
  runtime state to a writable dir (`.data/`) — Render/Railway run FS is writable but
  **ephemeral on redeploy**; the app must tolerate a fresh `.data/`.
- Order matters: deploy backend FIRST, get its real URL, then write it into
  `vercel.json` (placeholder until then), push, `vercel --prod`.
  Until the real URL is set, `/api/*` on Vercel returns 404 — that's the expected
  interim state, verify it to distinguish "proxy not configured" from "backend down".
