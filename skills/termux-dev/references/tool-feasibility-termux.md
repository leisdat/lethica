# Tool feasibility on Termux Android — evaluation checklist

Recurring question: user links a GitHub repo ("coba ini bisa gk") and you must decide
whether it can run on their Termux phone. Evaluate in this order — 80% of the time the
answer is found in the README prerequisites.

## 1. Pull the facts fast
- GitHub API: `curl -s https://api.github.com/repos/<owner>/<repo>` → description,
  language, stargazers, updated_at. Cheap and structured.
- README: `curl -s https://raw.githubusercontent.com/<owner>/<repo>/main/README.md`
  (fallback `master`). Grep for "Prerequisites", "Docker", "requires", "Install".

## 2. Hard blockers (instant NO)
- **Docker required** → does NOT run on Termux/Android kernel (needs cgroups/namespaces
  Android doesn't expose). `proot-distro + Docker-in-Docker` is impractical (2-3GB RAM).
- **Native browser binary** (Playwright/Chromium/Puppeteer) → Playwright ships Chromium
  built against **glibc**; Termux uses **bionic libc**, so `playwright install chromium`
  fails. Even the browser that ships *with* Chrome-the-app on Android is unreachable from
  Termux (separate process space).
- **needs X11 GUI** → Termux has no display by default; termux-x11 is heavy.
- **needs systemd / long-running daemon** → not available on Android.

## 3. Soft blockers (weigh against available RAM)
- Check `free -m` — available (not total) is what matters. A phone showing ~1GB free is
  too tight for Chromium + a dev server together.
- proot-distro + Ubuntu exists as an escape hatch for glibc tools, but each nested layer
  costs RAM and speed.

## 4. NOT blockers (feasible)
- **Skill/agent suites** (e.g. ClawSec `npx skills add`) — no Docker/browser/daemon,
  just files + node/python. These run fine on Termux.
- Pure-CLI tools with no native deps.
- Anything the user can verify manually in Chrome-the-app via `localhost:<port>`.

## 5. Recommend the lightest path
When a desktop-centric tool is infeasible, say so plainly and offer the alternative that
already works (manual browser testing, existing Hermes skill, curl-based verification).
User prefers honesty + a working alternative over forcing a heavy install.

## Worked example — ClawSec (prompt-security/clawsec)
Skill suite FOR Hermes agents (`"platform": "hermes"`), so unlike Playwright/Strix it IS
installable. Evaluated 4 skills:
- `hermes-attestation-guardian` — posture attestation + drift detection, node scripts,
  writes under `~/.hermes/security/`. Read-only by default; fail-closed verifier.
- `soul-guardian` — drift detection on SOUL.md/AGENTS.md/USER.md/MEMORY.md, python3.
  **DANGER: auto-restore mode overwrites drifted files** (incl. legit user edits) until
  `approve`. Warn the user before enabling restore-mode monitoring.
- `hermes-traffic-guardian` — v0.0.1-beta is a SPEC only ("does not ship a proxy yet").
  Skip until an implementation exists.
- `clawsec-suite` — manager + advisory feed; needs `openclaw` binary the Hermes-only user
  doesn't have. Skip for Hermes-only setups.
- All AGPL-3.0 license — modifying/sharing the skill forces open-sourcing it.
- Termux caveat: setup scripts assume standard `cron`; Termux has no cron by default.
