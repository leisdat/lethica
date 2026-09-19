# Lethica Skill Index

File navigasi untuk memilih skill. **Ini BUKAN skill** — tidak di-load sebagai SKILL.md, gunakan sebagai referensi saat menentukan skill mana yang dipakai.

## Cara Akses
- Baca langsung: `read_file path="~/lethica/skills/SKILL_INDEX.md"`
- Atau via tool_skill jika didukung dengan param `file`.

## Struktur: 45 Layer, 455 Skill Kustom (+273 duplikat Hermes = 728 folder)

### Layer 1 — Agent-level (16) — entry point & spesialisasi
`web-recon` · `research-intelligence` · `coding` · `reasoning-intelligence` · `self-improve` · `agent-router` · `coding-core` · `debugging` · `testing` · `code-review` · `refactoring` · `security-audit` · `performance` · `planner` · `design` · `deployment`

> Top-level dispatcher: **`agent-router`** → route ke spesialis. **`tool-core`** (Layer 2) → route ke tool.

### Layer 2 — Tool-system (10) — cara pakai alat
`tool-core` · `terminal` · `file-manager` · `git` · `browser` · `database` · `api` · `package-manager` · `process-manager` · `environment`

### Layer 3 — UI-system (9) — cara bangun antarmuka
`ui-core` · `design-reference` · `ui-builder` · `design-system` · `responsive` · `accessibility` · `animation` · `visual-review` · `anti-ai-slop`

### Layer 4 — Project-system (10) — lifecycle & manajemen
`project-core` · `project-discovery` · `project-planner` · `project-structure` · `project-tracker` · `project-dependency` · `project-progress` · `project-risk` · `project-documentation` · `project-release`

### Layer 5 — QA-system (10) — quality gate
`qa-core` · `test-planner` · `test-runner` · `unit-testing` · `integration-testing` · `e2e-testing` · `regression` · `bug-triage` · `quality-gate` · `qa-report`

### Layer 6 — Security-system (10) — security gate
`security-core` · `threat-model` · `secret-scanner` · `dependency-audit` · `code-security` · `auth-security` · `api-security` · `data-security` · `permission-security` · `security-gate`

### Layer 7 — Deployment-system (10) — build → prod → rollback
`deployment-core` · `build` · `environment` · `staging` · `production` · `migration` · `health-check` · `monitoring` · `rollback` · `release`

### Layer 8 — Documentation-system (9) — sync docs
`docs-core` · `readme` · `architecture-docs` · `api-docs` · `code-docs` · `changelog` · `migration-docs` · `user-guide` · `docs-review`

### Layer 9 — Analytics-system (10) — ukur diri sendiri
`analytics-core` · `agent-metrics` · `task-metrics` · `performance` · `cost-tracking` · `error-tracking` · `usage-analytics` · `observability` · `anomaly-detection` · `analytics-report`

### Layer 10 — Integration-system (11) — koneksi external service
`integration-core` · `connector` · `authentication` · `webhook` · `github` · `gitlab` · `messaging` · `cloud` · `database` · `third-party-api` · `integration-testing`

> Integration berjalan paralel di seluruh layer — dipakai saat Lethica butuh hubungi GitHub/GitLab/cloud/DB/API pihak ketiga. `integration-core` = dispatcher, `connector` = abstraction.

### Layer 11 — Knowledge / RAG (10) — knowledge base, indexing, retrieval
`knowledge-core` · `indexer` · `embed` · `retriever` · `chunking` · `store` · `rag-query` · `knowledge-graph` · `kb-maintenance` · `retrieval-eval`

### Layer 12 — Skill Manager (10) — install, load, update, dependency
`skill-manager-core` · `install` · `load` · `update` · `dependency` · `validate` · `discovery` · `remove` · `template` · `registry`

### Layer 13 — Workflow / Automation (10) — multi-step & otomatisasi
`workflow-core` · `builder` · `scheduler` · `trigger` · `step` · `condition` · `parallel` · `retry` · `monitor` · `template`

### Layer 14 — Policy / Guardrails (10) — permission, approval, batasan
`policy-core` · `permission` · `approval` · `constraint` · `allowlist` · `blocklist` · `audit` · `escalation` · `sandbox` · `override`

### Layer 15 — State / Cache (10) — session, cache, checkpoint
`state-core` · `session` · `cache` · `checkpoint` · `persistence` · `restore` · `invalidate` · `ttl` · `snapshot` · `sync`

### Layer 16 — Backup / Recovery (10) — backup, restore, DR
`backup-core` · `snapshot` · `incremental` · `restore` · `disaster-recovery` · `verify` · `retention` · `offsite` · `schedule` · `integrity`

### Layer 17 — Maintenance (10) — cleanup, health, housekeeping
`maintenance-core` · `cleanup` · `health-check` · `dependency-housekeeping` · `lint` · `prune` · `vacuum` · `monitor-disk` · `report` · `auto-fix`

### Layer 18 — Packaging / Distribution (10) — build, package, versioning
`packaging-core` · `build` · `package` · `version` · `manifest` · `sign` · `publish` · `install` · `registry` · `compatibility`

### Layer 19 — Benchmark / Evaluation (10) — evaluasi kemampuan
`benchmark-core` · `task-suite` · `metric` · `eval-runner` · `compare` · `report` · `regression-bench` · `baseline` · `scorecard` · `analyze`

### Layer 20 — Learning / Improvement (10) — feedback → analisis → improvement
`learning-core` · `feedback` · `analysis` · `extract-lesson` · `apply` · `memory` · `pattern` · `correction` · `suggestion` · `verify`

### Layer 21 — Frontend / Backend Specialization (10) — agent khusus domain
`febe-core` · `frontend-agent` · `backend-agent` · `fullstack-agent` · `api-agent` · `ui-agent` · `db-agent` · `test-agent` · `devops-agent` · `router`

### Layer 22 — Network / Web (10) — browsing, scraping aman, diagnostik
`network-core` · `browse` · `scrape` · `http-client` · `dns` · `proxy` · `diagnose` · `crawler` · `rate-limit` · `capture`

### Layer 23 — Data / Storage (10) — file, structured, import/export
`data-core` · `file-ops` · `structured` · `import` · `export` · `transform` · `validate` · `query` · `schema` · `backup`

### Layer 24 — Developer Experience (10) — CLI, logs, config, onboarding
`dx-core` · `cli` · `logs` · `config` · `onboarding` · `error-message` · `docs` · `prompt` · `environment` · `feedback-loop`

### Layer 25 — Planning / Decision Intelligence (10) — keputusan & trade-off
`decision-core` · `tradeoff` · `scenario` · `option` · `criteria` · `risk-decision` · `multi-objective` · `simulation` · `recommendation` · `review`

> Layer 11–25 adalah foundational/cross-cutting — dipakai di seluruh lifecycle. `policy` & `state` berjalan sebagai guardrails & memory di setiap layer. `learning` menutup loop kembali ke `self-improve` (Layer 1).

### Layer 26 — Multi-Agent Collaboration (10) — agent-to-agent, shared context, conflict
`multi-agent-core` · `message-bus` · `shared-context` · `conflict-resolution` · `agent-handoff` · `consensus` · `task-delegation` · `blackboard` · `negotiation` · `termination`

### Layer 27 — Memory Intelligence (10) — short/long-term, forgetting, relevance
`memory-core` · `short-term` · `long-term` · `forgetting` · `relevance` · `consolidation` · `retrieval` · `episodic` · `semantic` · `working-set`

### Layer 28 — Search Intelligence (10) — query planning, web, verification
`search-core` · `query-plan` · `web-search` · `source-verify` · `ranking` · `extract` · `deep-search` · `local-search` · `aggregate` · `fact-check`

### Layer 29 — Computer Use (10) — GUI, screenshots, mouse/keyboard
`computer-use-core` · `screenshot` · `mouse` · `keyboard` · `window` · `form-fill` · `navigation` · `observation` · `action-plan` · `safety`

### Layer 30 — Communication (10) — chat, voice, notify, messaging
`communication-core` · `chat` · `voice` · `notify` · `messaging` · `template` · `broadcast` · `inbound` · `summary` · `escalation-msg`

### Layer 31 — Simulation / Sandbox (10) — kode/command terisolasi
`sandbox-core` · `exec` · `filesystem` · `network` · `resource-limit` · `snapshot` · `rollback` · `artifact` · `monitor` · `escape-detect`

> Layer 26–31 memperluas kapabilitas runtime: kolaborasi antar-agent (26), memori cerdas (27), pencarian terverifikasi (28), kontrol GUI (29), komunikasi (30), eksekusi terisolasi (31). Semua berjalan di bawah guardrails `policy` & `state`.

### Layer 32 — Credential / Secret Management (10)
`credential-core` · `vault` · `api-key` · `token` · `rotation` · `injection` · `discovery-secret` · `permission-secret` · `audit-secret` · `leak-response`

### Layer 33 — Concurrency / Queue (10)
`concurrency-core` · `queue` · `worker` · `parallel` · `rate-limit` · `lock` · `semaphore` · `scheduler` · `batch` · `backpressure`

### Layer 34 — Resource Management (10)
`resource-core` · `cpu` · `memory` · `disk` · `token-budget` · `context-budget` · `quotas` · `optimize` · `monitor-res` · `reclaim`

### Layer 35 — Navigation / Environment Awareness (10)
`navigation-core` · `repo-map` · `env-awareness` · `runtime-detect` · `project-state` · `cwd-sense` · `discover-files` · `config-sense` · `capability-detect` · `orientation`

### Layer 36 — Plugin Ecosystem (10)
`plugin-core` · `discovery-plugin` · `compatibility` · `lifecycle` · `permission-plugin` · `sandbox-plugin` · `registry-plugin` · `hook` · `api-plugin` · `update-plugin`

### Layer 37 — Tool Discovery (10)
`tool-discovery-core` · `index-tools` · `match` · `rank-tools` · `capability-map` · `auto-select` · `fallback-tool` · `validate-tool` · `tool-meta` · `learn-tool`

### Layer 38 — Change Management (10)
`change-mgmt-core` · `diff` · `approval-change` · `rollback-change` · `history` · `impact` · `staged` · `review-change` · `changelog-change` · `freeze`

### Layer 39 — Incident Management (10)
`incident-core` · `detect` · `triage` · `investigate` · `mitigate` · `recover` · `comms` · `postmortem` · `runbook` · `warroom`

### Layer 40 — Architecture Intelligence (10)
`architecture-core` · `dep-graph` · `module-analysis` · `design-decision` · `pattern-detect` · `bottleneck-arch` · `tech-debt` · `consistency` · `evolution` · `review-arch`

### Layer 41 — Product Intelligence (10)
`product-core` · `requirement` · `prioritize` · `roadmap` · `user-research` · `feature-eval` · `feedback-prod` · `metric-prod` · `experiment-prod` · `vision`

### Layer 42 — Experimentation (10)
`experimentation-core` · `hypothesis` · `ab-test` · `control-group` · `metric-exp` · `rollout` · `analysis-exp` · `tracking` · `stop` · `report-exp`

### Layer 43 — Localization / i18n (10)
`i18n-core` · `locale` · `translate` · `timezone` · `format` · `rtl` · `plural` · `extraction` · `review-i18n` · `fallback-i18n`

### Layer 44 — Self-Healing (10)
`self-healing-core` · `detect-fail` · `diagnose` · `repair` · `verify-heal` · `watchdog` · `recover-state` · `degrade` · `prevent` · `escalate-heal`

### Layer 45 — Agent Self-Evaluation (10)
`agent-eval-core` · `rubric` · `self-check` · `gate-eval` · `bias-check` · `consistency` · `safety-eval` · `calibrate` · `feedback-eval` · `report-eval`

> Layer 32–45 adalah operasional + kecerdasan sistem: rahasia (32), konkurensi (33), resource (34), orientasi (35), plugin (36), discover tool (37), perubahan (38), insiden (39), arsitektur (40), produk (41), eksperimen (42), lokalisasi (43), self-healing (44), self-eval (45). Loop tertutup: output → `agent-eval` → `learning`/`self-improve`.

---

## Redundansi & Canonical Mapping

Beberapa skill di Layer 1 (agent-level) overlap dengan layer dedicated. Gunakan mapping ini agar tidak bingung memilih:

| # | Redundan A (agent-level) | Redundan B (layer) | Canonical | Catatan |
|---|--------------------------|--------------------|-----------|---------|
| 1 | `deployment` | `deployment/*` | **`deployment/*`** | Agent-level = summary legacy. Operasi nyata pakai `deployment/deployment-core` + sub-skill. |
| 2 | `project/project-release` | `deployment/release` | **`deployment/release`** | `project-release` = gate di level project (sebelum handoff). `deployment/release` = eksekusi + checklist + status. |
| 3 | `design-reference` (root) | `ui/design-reference` | **`ui/design-reference`** | Root = legacy. UI layer konsisten dengan `ui/*`. |
| 4 | `planner` | `project/project-planner` | **`project/project-planner`** | `planner` = quick alias. Project-planner punya workflow + rules task lengkap. |
| 5 | `testing` | `qa/*` | **`qa/*`** | `testing` = summary entry. QA layer granular (unit/integration/e2e/regression). |
| 6 | `security-audit` | `security/*` | **`security/*`** | `security-audit` = summary entry. Security layer granular (threat/secret/code/api/data). |
| 7 | `project/project-documentation` | `documentation/*` | **`documentation/*`** | `project-documentation` = reminder di level project. Docs layer granular. |
| 8 | `performance` (agent) | `analytics/performance` | **Keduanya valid** | BUKAN redundan: `performance` = optimasi software (code/DB/caching, Measure→Optimize→Measure). `analytics/performance` = observability metric sistem (CPU/latency/queue). Pakai sesuai konteks. |

**Aturan emas:** Kalau ragu antara agent-level summary vs layer granular → pakai **layer granular** untuk eksekusi, agent-level untuk quick reference.

---

## Name Collision Lintas Layer (gunaakan full path)

Skill dengan nama sama di folder beda — selalu sebut full path saat invoke:

- `environment` → `tools/environment` (konfigurasi runtime) vs `deployment/environment` (env dev/test/staging/prod)
- `migration` → `deployment/migration` (DB migration) vs `documentation/migration-docs` (dokumentasi breaking change)
| `performance` → agent-level (optimasi) vs `analytics/performance` (observability)
- `database` → `tools/database` (operasi DB lokal) vs `integrations/database` (external DB resource terpisah)
- `api` → `tools/api` (HTTP/API interaction umum) vs `integrations/third-party-api` (third-party dgn dokumentasi/rate-limit/mock)

---

## Lifecycle Flow (default pipeline)

```
PROJECT (project-core)
  → AGENT (agent-router → spesialis Layer 1)
    → TOOL (tool-core → Layer 2)  +  UI (Layer 3)
      → SECURITY (security-core → Layer 6, gate paralel)
        → QA (qa-core → Layer 5, quality gate)
          → DEPLOYMENT (deployment-core → Layer 7)
            → DOCUMENTATION (docs-core → Layer 8, sync)
              → ANALYTICS (analytics-core → Layer 9, ukur)
                → SELF-IMPROVE (agent-level, loop balik ke PROJECT)

INTEGRATION (integration-core → Layer 10, parallel di semua layer saat butuh external service)
```

## Quick Dispatch Table

| Kebutuhan | Skill utama |
|-----------|-------------|
| Route task ke agent | `agent-router` |
| Riset sebelum decision | `research-intelligence` |
| Analisis sebelum action | `reasoning-intelligence` |
| Implement kode | `coding` / `coding-core` |
| Fix error | `debugging` |
| Test | `qa/test-runner` + `qa/unit-testing` dll |
| Review kode | `code-review` |
| Restruktur | `refactoring` |
| Audit security | `security/security-core` |
| Deploy | `deployment/deployment-core` |
| Docs | `documentation/docs-core` |
| Ukur/optimasi | `analytics/analytics-core` |
| Belajar dari hasil | `self-improve` |
| Web recon/scrape | `web-recon` |
| Bangun UI | `ui/ui-core` |
| Manage project | `project/project-core` |
| Hubungkan external service | `integrations/integration-core` |
| GitHub/GitLab ops | `integrations/github` / `integrations/gitlab` |
| Knowledge/retrieval | `knowledge/knowledge-core` |
| Install/update skill | `skill-manager/skill-manager-core` |
| Automation | `workflow/workflow-core` |
| Guardrails/approval | `policy/policy-core` |
| Cache/checkpoint | `state/state-core` |
| Backup/restore | `backup/backup-core` |
| Health/cleanup | `maintenance/maintenance-core` |
| Build/package | `packaging/packaging-core` |
| Evaluasi diri | `benchmark/benchmark-core` |
| Belajar dari feedback | `learning/learning-core` |
| FE/BE routing | `febe/febe-core` |
| Network/web | `network/network-core` |
| Data/storage | `data/data-core` |
| DX/CLI | `dx/dx-core` |
| Keputusan kompleks | `decision/decision-core` |
| Kolaborasi antar-agent | `multi-agent/multi-agent-core` |
| Memori cerdas | `memory/memory-core` |
| Pencarian terverifikasi | `search/search-core` |
| Kontrol GUI | `computer-use/computer-use-core` |
| Chat/notify | `communication/communication-core` |
| Eksekusi terisolasi | `sandbox/sandbox-core` |
| Secret/credential | `credential/credential-core` |
| Konkurensi/queue | `concurrency/concurrency-core` |
| Resource budget | `resource/resource-core` |
| Orientasi repo/OS | `navigation/navigation-core` |
| Self-healing | `self-healing/self-healing-core` |
| Self-evaluation | `agent-eval/agent-eval-core` |

---
*Generated untuk navigasi skill Lethica v2.9.7. 455 skill kustom across 45 layers. Update manual jika skill baru ditambah.*
