## v3.7.0 - Native function calling + schema-validated dispatch (2026-09-20)
**Konteks:** tool call diparsing dari teks mentah pakai regex ketat (EXEC_TAG_RE
dkk). Satu spasi/newline/arg salah tipe di tag kanonik → dispatch return ''
SILENT-FAIL tanpa penjelasan. Operator minta: (a) native function calling kalau
provider dukung, (b) validasi skema + error jelas untuk custom-tag path.

**Arsitektur (audit-first, tidak rewrite yang jalan):**
- `core/tooldef.py` (BARU, 1 sumber kebenaran): skema 16 tool (tipe/wajib/enum/
  desc) + `validate()` (coerce integer/boolean/enum case-insensitive, required
  check, unknown-arg warning — stdlib-only, TANPA dep pydantic) + `openai_tools()`
  (ekspor payload `tools` OpenAI-compatible) + `canon_tool()` alias map
  (execute_command/Bash/antml:* → canonical) + `EXEC_ORDER` historis.
- `core/client.py`: `chat(tools=...)` kirim `tools`+`tool_choice=auto`, tangkap
  `message.tool_calls` → `last_tool_calls`; `chat_stream` akumulasi fragmen
  delta.tool_calls per index (stream kosong + tool_calls = valid);
  `chat_failover(tools=...)`: provider balas 400/422 pada payload tools →
  degrade SEKALI tanpa tools + tanda `tools_rejected` (sesudah itu session full
  tag-path, hemat 1 call/turn).
- `core/tags.py`:
  * `dispatch()` = stage-1 regex proven (tak berubah perilaku) + SPAN TRACKING +
    stage-2 SALVAGE: tag kanonik yang lolos regex di-parse toleran + divalidasi
    skema → eksekusi (newline/spasi/arg-order bebas) ATAU `TOOL_ERROR [name]:
    arg 'x' harus integer...` EKSPLISIT. Dedupe byte-span → tidak dobel-eksekusi.
  * `dispatch_calls_list()` / `dispatch_calls()`: eksekusi native tool_calls —
    validasi skema, urutan EXEC_ORDER, return [(id,label,out)] utk role "tool".
  * `looks_like_tool_attempt()` perluas: tag kanonik RUSAK pun kini terdeteksi
    (dulu silent, loop mati tanpa retry) → safety-net minta ulang canonical.
- `core/loop.py`: jalur native FC — assistant msg (content di-omit kalau kosong)
  + `tool_calls`, hasil per-call sebagai pesan `role:"tool"` + `tool_call_id`
  (bukan lagi satu tool_response gabungan); `tool_rounds` tetap hard-cap.
  Config `[model] native_function_calling` (default true).
- `core/soul.py`: rule "kalau skema tools tersedia, pakai tool_calls; tag XML
  tetap fallback utk model lokal".

**Keputusan desain:**
- Transport native FC masuk ke dispatcher tag yang SUDAH teruji via salvage/
  validate — satu jalur eksekusi (`_exec_tool`), dua jalur input. Tidak ada
  dispatcher paralel.
- Pydantic TIDAK dipakai sebagai runtime dep: zero-dep constraint Termux;
  validate() manual dengan pesan error setara. Skema tooldef tetap subset
  JSON-Schema sah → bisa diimpor pydantic / di-ekspor ke provider apa pun.
- Fallback berjenjang: native FC → salvage tag toleran → error eksplisit →
  safety-net canonical-retry (bad_rounds≤3) → finalisasi. Silent-fail hilang.

**Test (tests/test_v37_toolcalling.py, terdaftar di run_all.py):**
54 checks: validator + schema export + alias canon + salvage (termasuk regresi
code-block-mask v2.8.10 + anti dobel-eksekusi) + dispatch_calls_list (urutan
EXEC_ORDER + args dict + invalid pesan sebab) + loop E2E stub (payload terkirim,
marker dieksekusi, role tool + id, NATIVE_FC=false, tools_rejected drop) +
chat()/failover capture + regresi legacy markup + edit_file salvage + mixed reply.

**Perbaikan test lama (sekalian):**
- test_v295_foreign_tags c3: change-detector assert "v2.9" → kontrak perilaku
  (read_file sukses baca file, nilai versi bebas). FAIL laten sejak bump versi.
- stub chat_failover test e2e v2.9.5: + kwarg tools=None.
- WS test v37 di sandbox dir (Termux /usr/tmp ≠ /tmp → OUTSIDE sandbox trap).

**Verifikasi:** py_compile core/*.py OK; get_version()→3.7.0; run_all.py →
ALL GREEN (termasuk v37); foreign_tags 17/17; semantic 44/44; knowledge_graph
44/44. Live FC probe via routerku: gateway hidup tapi upstream free sedang down
(500 "All providers failed") → jalur degrade (400→tag path) teruji via stub,
provider round-trip asli perlu diulang saat upstream hidup.

## v3.6.2 - Version marker hardening + gitignore security fix (2026-09-20)
**Konteks:** tree kotor pasca v3.6.1 — marker `.lethica_version` belum di-track
dan fallback versi masih hardcoded `2.5.0`.

**Fixes:**
- `core/config.py get_version()`: fallback hardcoded `2.5.0` → `3.6.1` lalu
  disinkron `3.6.2`. Kalau marker hilang, runtime tidak regresi lagi ke versi
  basi (akar masalah laporan `run` menampilkan 2.5.0 saat changelog sudah 3.6.1).
- `.lethica_version` sekarang di-commit (3.6.2) sebagai source-of-truth marker.
- `.gitignore`: pola `config.toml  # Contains routerku API keys` TIDAK pernah
  aktif — git memperlakukan token setelah spasi sebagai bagian pola, bukan
  komentar, jadi `config.toml` (berisi API keys routerku) lolos dari ignore.
  Dipisah jadi komentar baris sendiri + pola bersih. Verifikasi:
  `git check-ignore -v config.toml` → match.
- `lessons/`: snapshot runtime lessons + state (scan key/secret: bersih).

**Verifikasi:** `python3 -m py_compile core/*.py` OK; `get_version()` → 3.6.2;
NUL-byte scan changelog: 0.

## v3.6.1 - Knowledge Graph fixes + test suite isolation (2026-09-19)
**Kontek:** v3.6.0 (Knowledge Graph + World Model) belum pernah di-commit — tree
kotor dari WIP. Session ini: verifikasi + fix deterministik + isolasi test suite.

**Bugfixes (akar masalah, bukan gejala):**
- `core/memory.py` + `core/orchestra.py`: feedback semantic per-id nulis
  memories.json tiap iterasi (80+ hit → ~3s/task di Termux I/O). Tambah
  `feedback_batch()` (SATU tulis utk N id, perilaku per-id identik) — v32 timing
  3.57s → 0.41s (< threshold 0.45s).
- `core/capture.py link_skill_version()`: SUPERSEDES gagal kalau node versi lama
  belum pernah dibuat (HAS_VERSION dengan target hilang). Sekarang ensure
  historical node dulu → test 19/29 (skill graph, v3.4 integration).
- `core/capture.py link_strategy_outcome()`: return ok:False kalau node
  STRATEGY/TASK belum ada. Sekarang ensure node otomatis → test 30 (v3.3).
- `core/capture.py resolve()`: node ber-status ACTIVE tidak dianggap konflik saat
  versi beda (hanya CURRENT). Sekarang CURRENT|ACTIVE → test E (conflicting
  versions).
- `core/world.py get_project_state()`: pakai `_ensure_project` (jangan return
  tanpa `components` saat project node belum ada) + gabung node scope-project
  tanpa edge + kumpul FAILURE/SOLUTION dari SEMUA komponen (bukan cuma TASK)
  → test H (scope isolation), 24 (world model).
- `core/capture.py normalize_entity()`: alias "pg"/"postgresdb" → test 9
  (normalization aliases).
- `core/graph.py`/`tests/`: `graph_validate()` return dict (bukan tuple) — test
  31 pakai `["valid"]`.
- **Isolasi test**: `config.LETHICA_DIR` dukung env; `memory.MEM_FILE` dukung
  `LETHICA_MEM_DIR` (sejajar `LETHICA_GRAPH_DIR`); `tests/run_all.py` redirect
  memory+graph ke workspace temp per-suite. Sebelumnya test v32 nulis 80-90
  semantic memory + graph ke production → timing membengkak + lineage tercemar.
- Production stores (memory/, graph/) di-reset (backup:
  `backups/memgraph-pre-v361-*`) — kontaminasi fixture test v3.5/v3.6 dihapus
  agar graph/memory produksi mulai bersih.

**Verifikasi:** `tests/run_all.py` → RESULT: ALL GREEN (8/8 suite); 
`tests/test_knowledge_graph.py` → 44 passed, 0 failed;
`tests/test_semantic_memory.py` → 44 passed, 0 failed. e2e live (test_e2e_spawn)
flaky karena upstream routerku 502/timeout — bukan regresi (tidak ada perubahan
di path LLM).

## v3.6.0 - Knowledge Graph + World Model (2026-09-19)
**New files:**
- `core/graph.py` — knowledge graph storage JSON lokal (graph/nodes.json,
  edges.json, index.json). Node model + 40+ relation types, scope isolation,
  secret redaction (reuse v3.5 redact), traversal limits, temporal validity,
  conflict detection, observability. API: add/get/update/remove node + edge,
  neighbors/find_path/subgraph/search, detect_cycles/validate, find_by_name,
  scoped_nodes/visible.

## v3.5.0 - Semantic Long-Term Memory (2026-09-19)
**Goal:** Evolusi dari lexical recall → SEMANTIC + STRUCTURED + LONG-TERM MEMORY.
**Prinsip:** TIDAK rebuild Lethica. Reuse storage/helper existing (experience.py, config.py).
TIDAK hapus Experience Memory. TIDAK introduce infra berat (storage = JSON lokal).
Embedding OPTIONAL — default OFF → semantic_search fallback ke lexical (deterministic).

**New file:** `core/memory.py` — unified memory model + lifecycle + hybrid retrieval + ranker
+ project/solution/lesson memory + consolidation + conflict detection + secret redaction
+ scope isolation + context budget + memory graph relations + observability + clean API.

**Architecture:**
- MEMORY SYSTEM → SHORT-TERM (experience.py Task Memory) + LONG-TERM (semantic store)
  + STRUCTURED (Facts/Relations/Project/Solution/Lesson) → RETRIEVER (hybrid_search)
  → RANKER (MemoryScore + traceable reasons) → CONTEXT BUILDER (budget) → PLANNER.
- Memory types: TASK, FAILURE, SOLUTION, SKILL, STRATEGY, PROJECT, KNOWLEDGE, FACT,
  PREFERENCE, DECISION, LESSON, EXPERIENCE. Scopes: GLOBAL/PROJECT/TASK/SKILL/STRATEGY.

**Hybrid ranking signals:** lexical + semantic(optional) + metadata(project/skill/strategy/task)
+ recency + importance + success − irrelevance. Project match floor (meta≥1.0 → rel≥0.65).
Global baseline boost ONLY if query has lex/sem signal (hindari false boost).

**Integration (non-breaking):**
- `orchestra.planner()`: panggil `memory.retrieve_for_plan()` berdampingan `experience.recall()`.
  Memory semantic masuk `task.semantic_memories` + di-inject ke ctx planner.
- `orchestra._learn()`: feedback ke semantic memory kalau planner pakai memori.
- `orchestra._history()`: `memory.extract_from_task()` → TASK/SOLUTION/LESSON terstruktur.
- `evolution.record_experience()`: sink FAILURE/SOLUTION ke semantic memory.
- `strategy.record_outcome()`: sink STRATEGY outcome ke semantic memory.
- `loop.main()` startup: `memory.consolidate()` + `memory.decay()` maintenance.

**Config:** `[memory.semantic]` enabled=false (default), provider=routerku, model, dimensions, top_k.
Kalau enabled + provider sehat → embedding retrieval; kalau gagal → lexical fallback otomatis.

**Tests:** `tests/test_semantic_memory.py` — 44 PASS / 0 FAIL. Cover Phase 1-31, 33, 34, 36, 39
(unified model, lifecycle, hybrid, ranker, project/solution/lesson, consolidation, dedupe,
confidence, feedback, decay, conflict, temporal/version, scope, secret redaction, budget,
API, relations, observability, semantic proxy, failure injection, backward-compat).

**Verified:** py_compile OK; semua module import utuh; strategy+evolution sink jalan;
orchestrator wiring non-breaking.

## v2.9.5 - FIX "berhenti di tengah turn" (foreign tool-call + expand ~) (2026-09-12)
**Gejala:** setelah "⚙ executing tools..." + hasil tool, control balik ke `➜ lethica>:` tanpa
lanjut — user harus chat lagi (mis. ".") biar jalan. Kelihatan seperti "berhenti mendadak".
**Root cause (terverifikasi dari history.json turn-0004):** model (hy3 dkk) emit tool-call
dengan MARKUP ASING:
    <tool_calls:6124c78e>
    <tool_call:6124c78e>execute_command">
    <parameter name="command">cat ~/lethica/.lethica_version; ...</parameter>
    </invoke>
EXEC_TAG_RE butuh `<invoke name="...">` → regex gak match → dispatch() balik '' → loop anggap
turn selesai → return ke prompt. Command valid tapi gak pernah dieksekusi.
**Fix:**
- core/tags.py: `_normalize_foreign_tool_calls()` — wrapper `<tool_calls:ID>`/`<tool_call:ID>`
  dibuang; fragmen nama-tool telanjang (`execute_command">`) dibangun ulang jadi
  `<invoke name="execute_command">`; blok `<parameter name="X">V</parameter>` → canonical;
  alias tool (Bash/Shell/Read/Write/Edit/Grep/Glob/LS/Fetch/WebSearch) → nama native.
  Value di-escape (`&`,`"`,`<`,`>`) biar atribut gak pecah.
- core/tags.py: `looks_like_tool_attempt()` — deteksi reply yang NIAT panggil tool tapi
  formatnya gak dikenali, TANPA false-positive pada prose biasa ("invoke the function").
- core/tags.py: `strip_tags()` diperluas — buang residu `execute_command">`, `</invoke>`,
  `</parameter>`, wrapper asing → user gak lihat tag soup.
- core/loop.py: safety-net — kalau dispatch kosong tapi `looks_like_tool_attempt(reply)`,
  JANGAN balik ke prompt: kirim contoh format canonical + `continue` (max 3x, `bad_rounds`),
  lalu finalisasi paksa. Efek: loop lanjut sendiri, user gak perlu chat ulang.
- core/loop.py: kalau loop berhenti karena LIMIT ronde (bukan model finalkan) → paksa
  satu panggilan finalisasi + render, biar gak ada "berhenti mendadak tanpa jawaban".
- core/tools.py: `_expand()` — `tool_read_file`/`list_dir`/`search_content`/`write_file`/
  `edit_file` sekarang expand `~` + `$VAR`. Bug nyata: `read_file(path="~/lethica/x")`
  selalu "not found" karena os.path.isfile dipanggil dengan literal `~`; `write_file`
  malah bikin direktori literal `~`.
- core/client.py: `chat_failover()` +last-resort lintas-provider — kalau SEMUA entry chain
  gagal (mis. `["Free-All","hy3::hy3"]` dua-duanya nunjuk b.ai yang 429/404), dulu balik
  `(None,None)` → loop `return` → prompt tanpa jawaban. Sekarang otomatis coba
  `routerku::Free-All` → `Free-Kombo` → `L` (provider lokal yang selalu ada). Ini penyebab
  UTAMA "berhenti di tengah" pada live test: tool jalan tapi ronde finalisasi gagal.
- core/loop.py: `⚙ executing tools...` cuma dicetak kalau reply MEMANG punya tag tool
  (dulu selalu muncul di ronde final → noise).
**Verified:** py_compile OK; tests/test_v295_foreign_tags.py 17 PASS / 0 FAIL (markup persis
dari history.json, alias tool, code-block mask v2.8.10 gak regresi, quote di value, write_file
foreign); tests/test_v295_e2e_loop.py PASS (tool benar-benar jalan → tool_response diumpan
balik → model final → 2 calls, tanpa user chat lagi); tests/test_v295_e2e_retry.py PASS
(markup rusak total → retry canonical 3x → finalisasi, tidak hang);
tests/test_v295_fence_guard.py 5 PASS (markup asing CONTOH di fenced/inline code gak
dieksekusi — urutan mask-sebelum-normalize); tests/test_v295_live.py LIVE PASS lewat model
hy3 nyata: read_file jalan → jawab "v2.9.5" tanpa user chat ulang.
Backup: backups/audit-20260912-122435.tar.gz.

## v2.9.1 - TECH STACK UPGRADE: HTTP browser-impersonation (2026-09-11)
- HTTP layer (core/tools.py) kini pakai curl_cffi dengan impersonate=chrome
  (TLS/JA3 fingerprint browser asli) untuk _fetch, tool_http_request, tool_browse.
- Fallback otomatis ke urllib kalau curl_cffi gagal/tidak terpasang (_HAVE_CURL guard).
- Helper baru: _curl_request() + _browser_store_cookies_curl() (cookie jar persist).
- web_search chain (Bing/DDG/SearXNG/Google) ikut ke-upgrade via _fetch.
- Verified: HAVE_CURL=True; fetch/http GET+POST/browse 200; search 17-18 results;
  urllib fallback path works (len 419 when curl disabled).

## v2.9.0 - PEMBELAJARAN OTOMATIS (2026-09-11)
- Modul baru core/learning.py: refleksi diri per operasi, simpan pelajaran,
  perbarui strategi, identifikasi pola, sarikan templat.
- Skor Siluman 0-100%: 100 - (error/call*60) - 25(REVISE) - 15(truncated).
  <80% koreksi dicatat, <60% turn DIBATALKAN (hasil tak dipercaya).
- Analisis tren tiap 10 operasi: avg score, tingkat error, failure points per-tool,
  strategi aktif (auto-update).
- Pelajaran & templat persist ke lessons/state.json + lessons/lessons.jsonl.
- inject_strategy() suntik STRATEGI AKTIF + feedback skor ke turn berikutnya.
- Hook loop.py: begin_turn, record_verdict, record_truncation, end_turn, inject_strategy.
- Command baru /learning (panel ringkasan) + entri MENU_TEXT.
- Tunable via config.toml [learning]: enabled, correct_threshold, abort_threshold, trend_interval.
- Verified: skor formula, action ok/correct/abort, trend bucket crossing, persist 797B, import loop OK.

## v2.8.10 (2026-09-11) — FIX dispatcher: tag contoh di code block gak dieksekusi
- core/tags.py: +_FENCE_LINE_RE/_INLINE_CODE_RE + _mask_code_blocks() — span-preserving mask (isi fenced block backtick-x3/tilde-x3 + inline backtick diganti NUL, panjang dipertahankan) dipanggil di dispatch() sebelum semua TAG_RE finditer.
- Efek: tag tool yang ditulis sebagai CONTOH di fenced code block / inline code gak lagi ke-eksekusi nyata (bug berulang sesi ini: contoh skill tag di prose memicu eksekusi + output [skill] palsu).
- Verifikasi: py_compile OK; test fungsional 3 skenario PASS (fence tag diabaikan + tag nyata jalan = tepat 1 blok output; inline tag diabaikan; tag polos regression OK). Backup: backups/tags.py.bak-*
- Known limitation: tag literal di dalam parameter invoke (mis. string test di execute_command) masih ke-scan framework — hindari tulis tag literal di command; obfuscate kalau perlu.

## v2.8.9 (2026-09-11) — skill system + anti-slop protocol
- core/soul.py: +Anti-Slop Protocol (5 rules: no-untested-code, specificity, evidence-first, no-filler, skill-over-memory) + _skills_block() auto-load SKILL.md penuh untuk AUTOLOAD_SKILLS + catalog ringkas.
- core/tools.py: +tool_skill() (action list/show/reload + file reader references//scripts/) — 53 baris.
- core/tags.py: +SKILL_TAG_RE dispatch loop (name/action/file) — 9 baris.
- core/client.py: +11 baris (minor).
- core/config.py: +4 baris (AUTOLOAD_SKILLS).
- core/loop.py: +8 baris (minor).
- version bump 2.8.4 -> 2.8.9 (changelog synced).

## v2.8.4 (2026-09-09) — FIX /model & /provider failover loop + config sync
- CONFIG FIX: `[model].failover` buang `hy3::glm-5.3-flash` (gak ada di `[providers.hy3].models=["hy3"]`) → chain valid: `["Free-All", "hy3::hy3"]`
- VERSION SYNC: `.lethica_version` di-bump ke `2.8.4` (sebelumnya stuck di 2.8.3 padahal changelog udah 2.8.4)
- **Root cause 1**: run_agent_turn() bikin LClient() baru per turn → selalu resolve DEFAULT_BASE (routerku :20130), abaikan ACTIVE_PROVIDER hasil /provider → model pilihan gak ada di endpoint → "unavailable, failover..." terus. Fix: run_agent_turn(client=cl) terima client dari main loop; _active_client() resolve dari ACTIVE_PROVIDER.
- **Root cause 2 (critikal)**: rich Text(..., markup=False) TypeError di rich baru → exception dari stream_cb ke-swallow oleh except Exception di chat_stream → semua model "unavailable". Fix: drop kwarg markup + stream_cb dibungkus try/except sendiri (UI error ≠ network error).
- **Root cause 3 (version desync)**: `core/soul.py:124` `SOUL_BYPASS.format(...)` gak pass `ver=ver` padahal template punya `{ver}` di line 204 → system prompt selalu print version kosong/lama. Fix: tambah `ver=ver` ke format call. Sekarang `v2.8.4` ke-inject dari `config.VERSION` (verified: `'v2.8.4' in build_system_prompt()` → True).
- CONFIG: header comment `# Lethica v2.0 config` → `# Lethica v2.8.4 config` (cosmetic sync).
- **Root cause 3**: chat_failover entry provider::model = provider aktif sendiri → bikin client baru ke provider sama (useless). Fix: self jika pname == ACTIVE_PROVIDER.
- **Config**: [providers.hy3] → sidecar key-pool :20131 (791 key, cooldown 60s); models bener (hy3, glm-5.3-flash); [model].provider = routerku; failover = [Free-All, hy3::hy3, hy3::glm-5.3-flash]. groq key masih dummy (gsk_test_dummy) — isi beneran kalau mau pakai.
- main() startup pakai _active_client(); select_model tampil base URL asli.
- E2E 3/3 pass: Free-All via routerku, hy3::hy3 via sidecar, switch provider aktif → SWITCH-OK.

## v2.8.3 (2026-09-09) — STREAM PANEL UPGRADE
- Streaming mode sekarang dibungkus Live Panel kuning (border_style=yellow, title `🤖 lethica (model)`) — bukan output polos lagi
- Render final pakai Markdown di dalam panel (code block berwarna via rich)
- Import: rich.live.Live, rich.panel.Panel, rich.markdown.Markdown, rich.text.Text di loop.py
- Backup: backups/loop.py.bak

## v1.1-bypass (2026-09-08)
- NEW tool `<web_search query="..." limit="5" />` — Bing primary (markup <a><h2> baru + decode redirect /ck/a) → DDG lite fallback
- NEW tool `<browse url data method>` — browser session, cookie jar persist per domain, page text + links extraction
- NEW memory bank: `<memory action="save|load|search|forget" key content />` di ~/lethica/memory/, auto-inject index ke system prompt
- NEW plan mode: `<plan action="save|append|show|clear" content />` di ~/lethica/workspace/plans/active-plan.md, auto-inject ke system prompt
- urllib.parse + base64 ditambah ke import
- Backup v1.0: backups/lethica-bypass.py.bak-v1.0
## v2.0 (2026-09-08) — CONSOLIDATION
- 3 varian digabung jadi 1 canonical: lethica.py
- Persona config-driven via config.toml: bypass | plain
- /config slash command: view + edit + hot-reload
- Varian lama diarsip ke ~/lethica/deprecated/
## v2.1.0 (2026-09-08)
- STREAMING: SSE chat_stream + realtime render (reasoning dim-italic, content plain, per-delta callback). Terverifikasi 74 delta live.
- FAILOVER: chat_failover chain dari config [model] failover. Tested: bad-model → auto fallback ✓
- SESSIONS: /save nama & /load nama (tanpa nama = list). Files di ~/lethica/sessions/. System prompt selalu di-refresh saat load.
- config.toml baru: [model] failover, stream
- Panel title sekarang nunjukin model yang dipakai
## v2.2.0 (2026-09-08) — TAG ROBUSTNESS
- sanitize_tool_tags(): fix nested-quote, single-quote, attr-order-bebas di tool tags
- _parse_tag_attrs(): generic attr parser (escape-aware, order-independent) untuk memory/plan/browse/web_search
- Test matrix 9 broken-tag variants: 9/9 PASS, old-style regression OK
## v2.3.0 (2026-09-08) — RAG WORKSPACE INDEX
- tool_rag: SQLite FTS5 full-text index workspace + memory + plans + source files top-level
- <rag action="search|rebuild|stats" query /> — ranked hits dengan snippet, FTS syntax-error fallback ke phrase
- Auto-rebuild tiap startup (0.1s, local sqlite), stats auto-inject ke system prompt
- E2E loop test PASS: prompt → tool call → memory verify
## v2.3.1 (2026-09-08) — STUCK FIX
- console.status spinner tidak lagi membungkus tool loop — spinner hanya di mode non-stream, per-call
- Streaming jalan tanpa wrapper: teks realtime langsung keluar, tidak ke-blok spinner
- Feedback: label model aktif (▌ Free-All) sebelum stream + durasi & model dipakai setelah selesai
## v2.4.0 (2026-09-08) — TELEGRAM BRIDGE
- lethica_bridge.py: bot TG @QMybotai_bot pakai Lethica sebagai library (LClient + chat_failover + dispatch langsung)
- Per-chat conversation memory (12 turn), /new /model /status, agent loop + tools full dari chat
- Tool-tag scrubbing di display, long-message auto-split, run_in_executor biar TG event loop gak block
- Pitfall: instance ganda = Conflict terminated by getUpdates — kill semua lama sebelum start

## v2.5.0 (2026-09-09) — REFACTOR PACKAGE + TOKEN ACCOUNTING + BUGFIX
- Struktur: lethica.py jadi entry tipis (65 ln); logic dipindah ke core/ package
  (config, client, tools, tags, rag, soul, ui, tokens, loop) — gampang dikembangkan per-modul
- TOKEN ACCOUNTING v2.5: usage API di-log per call ke logs/tokens/YYYYMMDD.jsonl,
  /tokens slash command (7 hari + today), budget guard [model] daily_budget (warning di 80%)
- FIX: _browser_store_cookies KeyError saat deletion cookie (setdefault dulu)
- FIX: tag sanitizers (_fix_attr_quotes/_normalize_tag_attr_order) sekarang include 'rag'
- FIX: backup self rolling last-known-good — refresh tiap startup, bukan sekali selamanya
- FIX: version hard-coded "2.0" di logo/panel → selalu baca .lethica_version
- FIX: sliding window summary gak re-truncate berlapis (carry-over summary dipertahankan)
- lethica.py re-export semua attr buat compat lethica_bridge.py (verified: 0 missing)
- E2E PASS: agent loop + tool dispatch + token log + TUI slash commands via PTY

## v2.6.0 — Multi-provider support (09-09)
- `config.toml`: section `[providers.<name>]` (base/key/models) — tambah provider AI lain tanpa sentuh kode
- `core/config.py`: `providers()`, `get_provider()`, `provider_names()`, `ACTIVE_PROVIDER`; load_config merge section non-default (bugfix)
- `core/client.py`: `LClient.for_provider(name)` factory; failover cross-provider via syntax `provider::model` di chain
- `core/ui.py`: `select_provider()` (TUI picker) + `add_provider_interactive()` — prompt name/base/key/models, save+replace ke config.toml, probe koneksi otomatis
- `core/loop.py`: slash command `/provider` — switch provider live, persist ke `[model].provider`, auto-switch model kalau model lama gak ada di provider baru
- `/menu` updated

## v2.7.0 — Smarter agent (09-09)
- **Auto-grounding**: `rag.auto_ground()` — tiap user query, keyword diekstrak (stopword-filtered), FTS5 search, konteks relevan (max 1200 char) auto-inject ke pesan user sebagai `## AUTO-CONTEXT`. Indicator: `⚡ grounded`.
- **Grounding protocol**: soul rules +2 (AUTO-CONTEXT DULU, Reflection-aware).
- **Reflection pass**: `loop._reflect()` — kalau agent pakai tools lalu final answer, verifier murah (temp 0, max 700) cek jawaban vs tool evidence → REVISE = auto loop lanjut dengan instruksi koreksi. Robust terhadap reasoning models (fallback scan kontradiksi, finish_reason check).
- **Smart truncation**: tool_response >2000 char di dropped window di-capture head 150 + marker `(+N chars)`, bukan summary buta.
- **rag.py**: `_search_rows()` — FTS5 search dedup + quoted-phrase fallback, reusable buat auto_ground.

## v2.8.0 — Optimization pass (09-09)
- **core/stats.py**: tool usage tracking in-memory (calls/errors/time/avg). Semua tool_* di-wrap `stats.wrap()`. `/toolstats` slash command (panel + verifier info).
- **core/cache.py**: SQLite HTTP cache (http-cache.db). web_search TTL 30m (repeat: 1.5s → 0.01s), browse GET TTL 10m (POST gak di-cache), hits tracking.
- **Retry backoff**: LClient.chat_failover 2→3 attempt, backoff 1/2/3s, rate-limit aware (2/4/8s).
- **Verifier model beda**: config `[model].verifier_model` — reflection pass bisa pakai model lain biar gak ada blind spot. Default "" = same model.
- **Grounding cache**: auto_ground per-query cache in-memory (sesi).

## v2.8.2 — UX fix (self-heal)
- **Suppress thinking display**: reasoning stream gak di-print ke terminal (request operator). Gate via `config.SHOW_REASONING` (default false). Kalau mau lihat reasoning, set `show_reasoning = true` di `[model]` config.toml.
- **Fix double-render**: saat STREAM=true, output sudah di-print live → skip panel `render_md` kedua (cuma render panel kalau STREAM=false).
- **Fix reflection gate**: reflection pass (`_reflect`) sekarang jalan regardless STREAM flag (sebelumnya cuma jalan kalau STREAM=true).
- config.toml: tambah explicit `stream = true` + `show_reasoning = false` di `[model]`.

## v2.8.1 (self-heal)
- config.toml: max_tokens 2048 -> 8192
- core/tools.py: exec output truncate 4000 -> 16000
- core/loop.py: window carry-over 150 -> 2000 chars
## v2.8.5 (code cleanup — clean & professional)
- core/config.py: deduplikasi derived-globals via `_DERIVED` table + `_read_derived()`; `reload_globals()` turun 25→6 baris tanpa ubah perilaku. Init module-level jadi eksplisit (static-analysis friendly).
- core/cache.py: pindah import `os`/`urllib` ke atas (hilang noqa hack); `purge()` sekarang pakai `rowcount` (bug: dulu `.fetchone()` return tuple, salah).
- core/tools.py: `tool_web_search` dipecah jadi helpers `_fetch`/`_strip_html`/`_decode_bing_redirect`/`_search_bing`/`_search_ddg` — control flow bing→ddg jadi linear & jelas. Behavior identik (Bing→DDG fallback, cache 30m).
- core/loop.py: hapus import nganggur (`shutil`); ekstrak command handlers (`_cmd_save_load`, `_cmd_provider`, `_cmd_config`, `_cmd_self`, `_persist_provider`, `_auto_ground`, `_streamed_call`, `_should_revise`); `main()` turun 458→~310 baris. Panel/import duplikat jadi helper `_panel`.
- core/loop.py: fix bug pra-existing — smart-truncation marker `(+N chars)` ke-potong `[:300]`, sekarang dipertahankan (cap dinamis per-msg).
- tests/_cleanup_check.py: smoke-test suite (apply_window, terse_filter, web_search live, cache, config reload idempoten, dispatch, re-exports).
## v2.8.6 (core refactor + budget guard + search hardening + self-heal)
- core/soul.py: refactor struktur (split _persona_text / _memory_block / _rag_block / _plan_block / _operating_rules / build_system_prompt). SOUL_BYPASS & SOUL_PLAIN text FROZEN (verified byte-identical).
- core/ui.py: refactor (helper _provider_toml_block / _upsert_provider_block / _probe_provider; precompile DROP_PATTERNS). terse_filter behavior identik (verified).
- lethica_bridge.py: refactor (ekstrak _load_lethica / _run_agent_turn / _reply_long; TOOL_TAG_RE compiled global). Behavior identik (verified via stub import).
- core/tokens.py: tambah `budget_ok()` (hard guard: stop kalau >=100%, warn di >=80%) + `budget_remaining()`. `budget_warning()` tetap ada (backward-compat).
- core/loop.py: wire `tokens.budget_ok()` ke awal tiap round di `run_agent_turn` — hard-stop kalau budget harian habis.
- core/tools.py: `tool_web_search` chain diperlebar → Bing → DDG → SearXNG (random instance) → Google scrape, + `_with_retry()` exponential backoff (2x). Tambah `_search_searx`, `_search_google_scrape`.
- core/tools.py: self-heal auto-rollback — `verify_self()` (compile-check SELF_PATH + seluruh core/*.py) + `self_heal_rollback()` (restore dari backup terbaru kalau compile gagal). `tool_self_check` tetap ada.
## v2.8.7 (telegram bridge v1.2 + version sync)
- lethica_bridge.py: v1.2 — persistence state per-chat ke `workspace/chats.json` (load/save lintas restart); per-chat model switch via `/model <nama>`; streaming progress tiap tool-round (edit pesan status, throttled 1.2s). Behavior dasar identik.

## v2.8.8 (live activity indicator)
- core/tags.py: tambah `_act(icon, name, detail)` + import `console` dari `core.ui`. Tiap tool dispatch (read/write/edit/list/search/http/dl/web_search/browse/memory/plan/rag/execute_command) sekarang print `▌ {icon} {name} {detail}` real-time → operator tau agent lagi ngapain.
- core/loop.py: upgrade status text `lethica thinking...` → `🧠 lethica analyzing...`; stream banner `▌ {model} ⟳ analyzing...` → `🧠 {model} ⟳ analyzing...`; tambah banner `⚙ executing tools for {used}...` sebelum `tags.dispatch` + `✓ tools executed` sesudahnya.
- Tidak ubah behavior tool execution — murni observability layer.

## v2.8.11 (2026-09-09) — fix agent berhenti di tengah task
- config.py: MAX_TOKENS 2048→4096, tambah MAX_CONTINUE_ROUNDS=12 (terpisah dari MAX_TOOL_ROUNDS).
- client.py: reset last_finish_reason/last_usage per-call; chat() parse usage (completion_tokens).
- loop.py: pisah continuation-round dari tool-round; _output_truncated() deteksi kepotong
  via finish_reason=="length" / usage nyentuh 97% max_tokens / code fence ganjil.
  Auto-continue sampai 12x tanpa makan budget tool-round (8).

- v2.8.12: SOUL_BYPASS identity ditambah "Autonomous AI Agent · Full-stack Developer" (operator request). Backup: ~/lethica/backups/soul.py.bak-*. core/soul.py compile OK.

- v2.8.13: SOUL_BYPASS identity appended "Mencakup sistem, integrasi API, dan pengelolaan server. Prinsip kerja: anti-halusinasi — setiap hasil berasal dari eksekusi terverifikasi." (operator request, append-only). Backup: ~/lethica/backups/soul.py.bak-*. Compile OK.

## v2.8.14 — run_code polyglot + identity upgrade
- core/tools.py: +RUNCODE_TAG_RE, +tool_run_code (python/node/rust/c/cpp/go, timeout, stderr capture), stats.wrap
- core/tags.py: dispatch <run_code lang timeout>, TAG_NAMES +run_code
- core/soul.py: identity + decomposisi goal/polyglot/multi-agent/local-fallback


## v2.8.14 (2026-09-11) - skill-import safety guard
- Incident: import 34 skill; cp -rvf (head -1) di awal loop nge-OVERWRITE
  skills/reverse-engineering-malware-with-ghidra (punya operator, gak ke-backup/ke-track)
  -> hilang permanen. Versi repo (Apache-2.0, valid) menggantikannya, bukan custom.
- Recovery: find/, agent/skills, backups, git ls-files, git log, RAG db -> SEMUA kosong.
- Preventif: snapshot skills/ -> backups/skills-20260911-185131.tar.gz (273 SKILL.md, tar OK);
  loop cp WAJIB [ -d skills/$s ] && continue; JANGAN cp -f buta.
- Note: find skills -name SKILL.md = 273 (43 top-level + 230 nested bawaan), BUKAN efek import.

## v2.9.2 (2026-09-12) - audit ulang: 8 bug diperbaiki

Audit penuh (py_compile + import + test harness). Semua fix diverifikasi dengan
test yang dijalankan, bukan klaim.

### Bug kritis (fungsional rusak)
1. **core/client.py — usage token SELALU hilang.** `self.last_usage = ch.get("usage")`
   padahal routerku/OpenRouter menaruh `usage` di TOP-LEVEL response, bukan di
   dalam `choices[0]`. Efek: `_output_truncated()` gak pernah bisa deteksi output
   kepotong via usage, dan `/tokens` selalu jatuh ke estimasi. Fix: `ch.get("usage") or r.get("usage")`.
   Bukti: sebelum `usage captured: False`, sesudah `pt=14 ct=141 tot=155`.

2. **core/ui.py — terse_filter ngerusak kata di tengah kalimat.**
   Pattern `r"Sure!?\s*"` + `re.IGNORECASE` (tanpa anchor) nge-strip substring
   "sure" di mana saja: `"ensure safety first"` → `"ensafety first"`,
   `"Measure twice"` → `"Meatwice"`, `"make sure it works"` → `"make it works"`.
   Karena terse_filter dipanggil ke SETIAP reply model, ini korupsi output nyata.
   Fix: anchor `(?m)^[ \t]*` + buang `\s*` liar → hanya strip di awal baris.

3. **lethica_bridge.py — `for/else` bocorin tool_response mentah ke Telegram.**
   Kalau loop habis 16 round tanpa final (semua round pakai tool), else-branch
   ambil `messages[-1]["content"]` = blok `<tool_response>...` mentah → bocor ke chat.
   Fix: simpan `last_reply` (assistant terakhir) dan pakai itu.

### Bug tinggi
4. **core/tools.py — `tool_run_command` truncation bohong.** Guard `if len(out) > 4000`
   tapi potong di `out[:16000]` → output 4001–16000 char ditandai "... (output truncated)"
   padahal datanya utuh; output >16000 char dibuang tanpa pesan yang jelas.
   Fix: guard jadi 16000, marker menyebut angka cap.

5. **core/tags.py — activity indicator palsu.** Blok `<web_search>` manggil `_act()`
   5x (`rag`, `plan`, `memory`, `browse`, `web_search`) padahal cuma 1 tool yang jalan
   → operator lihat 5 baris aktivitas palsu. Fix: sisakan 1 `_act("🔎", "web_search", ...)`.

6. **core/tokens.py — estimasi token salah hitung.** `str(req_chars) + str(reply_chars)`
   lalu `len(txt)//4` = menghitung digit angka, bukan char. 4000+800 char → estimasi 1 token.
   Fix: `pt = req_chars//4`, `ct = reply_chars//4`.

### Bug sedang
7. **core/tools.py — `in_sandbox` crash kalau `CORE_DIR` gak ada.** Ekspresi
   `os.listdir(config.CORE_DIR)` di dalam tuple-comprehension tanpa guard → `FileNotFoundError`
   kalau core/ hilang, bikin semua write/edit gagal. Fix: try/except + `os.path.isdir`.

8. **lethica_bridge.py — TOOL_TAG_RE gak include `skill` & `run_code`.** Tag `<skill .../>`
   dan `<run_code ...>...</run_code>` yang bocor ke final text gak di-strip → tampil mentah
   di Telegram. Fix: tambah `skill|run_code` ke alternasi.

### Verifikasi
- `python3 -m py_compile lethica.py lethica_bridge.py core/*.py` → COMPILE OK
- 13 assertion fix (terse/in_sandbox/run_command/tokens/activity) → ALL PASS
- bridge for-else test → `leaks tool_response: False`
- suite lama `tests/_cleanup_check.py` → ALL CHECKS PASSED
- live call ke routerku → usage captured True

Backup pre-audit: `backups/audit-20260912-105435.tar.gz`

## v2.9.3 (2026-09-12) - audit lanjutan: 3 bug di jalur self-heal/rollback

Ditemukan saat verifikasi v2.9.2 — jalur yang justru dipakai buat menyelamatkan
sistem kalau ada kerusakan. Semua diuji dengan simulasi kerusakan nyata.

### Bug 9 (KRITIS) - tool_self_check restore backup yang SALAH
`baks = sorted(f for f in ... if f.startswith("lethica.py.bak"))` lalu `baks[-1]`.
Sorting leksikografis: `'lethica.py.bak-v2.4.1'` > `'lethica.py.bak'` karena `'-'` > `''`.
Jadi tiap self-check gagal, sistem nge-restore MONOLIT v2.4.1 (83 KB) dan
menimpa entry point yang sekarang cuma 1.954 B - kehilangan seluruh arsitektur
core/ (config, client, tools, tags, rag, soul, ui, tokens, loop).
Fix: helper `_newest_backup(base)` - prefer `<base>.bak` (rolling last-known-good
dari backup_self), fallback ke kandidat termuda by MTIME, exclude .tar.gz/.md.
Bukti: rusakkin lethica.py → `restored from lethica.py.bak`, size pulih 1954 B (bukan 83345).

### Bug 10 (KRITIS) - backup_self() cuma nge-backup entry point
Akibatnya 5 modul core gak punya kandidat backup sama sekali:
`tokens.py`, `cache.py`, `rag.py`, `stats.py`, `__init__.py`.
`self_heal_rollback()` (Mode 2 safeguard) jadi mustahil buat mereka - kalau
salah satu rusak, gak ada yang bisa di-restore.
Fix: backup_self() sekarang snapshot SELF_PATH + seluruh `core/*.py` (rolling .bak).
Bukti: setelah fix, `TANPA BACKUP: none` untuk 14 target py_compile.

### Bug 11 - self_heal_rollback() lapor "berhasil" padahal gagal
Dulu `return True, f"⚠ rollback sebagian ... masih gagal"` - return True bikin
caller nganggep sukses walau file masih broken. Juga gak lapor file tanpa backup.
Fix: return True HANYA kalau `verify_self()` bersih; pesan eksplisit sebut file
yang gak punya backup (`tanpa backup: ...`) dan status "rollback GAGAL".

### Verifikasi (semua dijalankan, bukan klaim)
- `backup_self()` → core/*.bak lengkap (17 file .bak), `TANPA BACKUP: none`
- inject syntax error ke `core/tokens.py` → `verify_self: (False, [tokens.py])`
  → `self_heal_rollback: (True, 'rollback berhasil: tokens.py <- tokens.py.bak')`
  → isi identik dengan sebelum, `verify_self: (True, [])`
- inject syntax error ke `lethica.py` → `HEAL ... restored from lethica.py.bak`,
  size 1954 B (bukan 83345), `verify_self: (True, [])`
- `python3 -m py_compile lethica.py lethica_bridge.py core/*.py` → OK
- `tests/_cleanup_check.py` → ALL CHECKS PASSED

Backup pre-audit: `backups/audit-20260912-105435.tar.gz`

## v2.9.4 (2026-09-12) — commit in-flight: learning.py + truncation detection
- core/learning.py (258 ln, NEW) di-commit (sebelumnya untracked): track truncation/
  verdict per turn, lessons.jsonl + state.json, inject_strategy(), summary_text().
  Tunable: enabled, correct_threshold=80, abort_threshold=60, trend_interval=10.
- core/loop.py: _output_truncated(cl, reply) — 3 sinyal truncation (finish_reason=
  "length", completion_tokens >= 97% MAX_TOKENS, code fence ganjil) + loop continue
  dibatasi MAX_CONTINUE_ROUNDS, tiap continue dicatat learning.record_truncation().
- core/config.py: MAX_TOKENS 2048 -> 4096; MAX_CONTINUE_ROUNDS=12 (baru, derived).
- core/soul.py: persona diperluas (full-stack dev, polyglot code-interpreter,
  orkestrasi multi-agent, fallback lokal ollama/llama.cpp).
- Verifikasi: `py_compile core/{learning,loop,config,soul}.py` OK;
  `from core import learning` OK (17 attr publik).
- Commit: d7424168. Tracked lethica: 17 -> 18 file, dirty 0.

## v2.9.6 - FIX tool-call wrapper over-consume + orphan invoke rebuild (2026-09-12)
- _FOREIGN_WRAPPER_RE dipecah 2 branch: bentuk ber-ID (tool_call:ID) dan bentuk polos (tool_call).
- Sebelumnya branch tunggal melahap fragmen invoke setelah wrapper polos -> invoke-open hilang -> dispatch kosong -> loop minta ulang 3x -> finalisasi rusak.
- _INVOKE_ORPHAN_RE baru: rebuild fragmen yatim invoke-name tanpa kurung-siku pembuka jadi tag canonical.
- Verifikasi: py_compile OK; test wrapper-polos / wrapper-ber-ID / canonical-untouched semua pass.
- 2026-02-14: max_tool_rounds 16 → 32 (config.toml, operator request)

## 2026-09-14 — routerku Command Deck + cost/webhook/SSE
- Dashboard redesign "Command Deck" (5 tab, dual-theme, donut, health-ring, sparkline, combo editor, playground, keys CRUD). Deployed ~/routerku/dashboard.html (backup .bak-predeck-*).
- lib/webhook.js (baru): createWebhook, env ROUTERKU_WEBHOOK_URL, cooldown 60s, notify('request-fail').
- router.mjs: computeCost() per-provider USD (env ROUTERKU_PRICE_<PREFIX>[_IN/_OUT] per 1M tok), /api/cost, cost field di /api/stats, /api/stream SSE (sseClients), sseBroadcast di logRequest, webhook fail-notify.
- dashboard.html: Est. Cost card + startSSE() live log (EventSource /api/stream).
## v3.2.0 (2026-09-17) — BOUNDED PARALLEL ORCHESTRATION
- **Scheduler (orchestra.py)**: wave-based, dependency-aware, conflict-safe (ThreadPoolExecutor, TANPA proses baru). ready_nodes (dep COMPLETED; dep mati → BLOCKED otomatis), _wave_safe (conflict matrix), budget_exhausted → cancel_all dengan reason eksplisit RESOURCE_LIMIT_REACHED (Fitur 1/3/4/11/12/13).
- **Sub-states**: +CANCELLED (7 state, tidak pernah eksekusi BLOCKED; _finish_node/_unblock_ready jaga konsistensi).
- **Fitur 9**: classify_subtask READ_ONLY/WRITE/NETWORK/DESTRUCTIVE/TEST/MIXED (uncertain→MIXED=serial); predict_writes + safe_parallel matrix — writer×writer hanya paralel bila write-set disjoint TERBUKTI; reader/writer paralel hanya non-bentrok.
- **Fitur 5/6**: agent pool ringan = client privat per thread (hindari race last_usage) + match_capability via registry.rank (BROKEN/STALE di-skip).
- **Fitur 7**: run_subtask = pesan terisolasi per subtask + recall top-1 relevan (bukan dump history); tidak mutate task.messages bersama.
- **Fitur 10/14**: merge_results (artefak+errors+warnings; TIDAK klaim sukses) → Critic dapat merged evidence.
- **Fitur 15**: _retry_failed wave-aware (branch gagal non-conflict → paralel; conflict → serialize) + unblock dependent setelah repair.
- **Fitur 16/18**: task memory menyimpan parallel_stats (parallel, max_concurrency, conflicts, cancellations, durasi); speedup HANYA dihitung dari baseline serial nyata (perf_v32.py).
- **re-decompose deterministik**: planner LLM sering lempar 1 mega-subtask utk goal ber-(1)(2)(3) → redecompose_independent() pecah by-struktur + integrasi node ber-dependensi (terbukti live v32_live).
- **_scan_cmd_files helper**: bukti file heredoc sadar-cd; glob basename dibatasi cwd command (bug lama: false-positive README.md project lain).
- **config**: [orchestra] max_concurrent_agents=3 (1 = matikan paralel, jalur serial v3.1.2 UTUH), max_total_agent_calls=60, max_subtasks=5.
- **Scope guard (KEAMANAN)**: agent/repair dilarang `cd`/`rm`/menulis ke luar direktori task (`config.TASK_DIR`, ketat + /tmp). Kasus nyata: repair agent nyasar ke `workspace/atria/auto_reg` (project LAIN) dan menjalankan `rm -f`/`nohup` di sana. Guard diverifikasi 8/8 kasus + test 24.
- **Bugfix hardening (dari live run)**: `_scan_cmd_files` HANYA target tulis (>, >>, touch/tee/cp/mv) — file yang cuma DISEBUT (find/ls/cat) dulu ikut jadi artefak & mencemari bukti Critic; derive status mengikuti semantik v3.0 (tanpa marker STATUS: tool jalan & tanpa error = success) krn model lemah sering lupa menulis STATUS; `reply=None` tidak lagi crash reporter; exception worker → node FAILED terisolasi (dulu nyangkut RUNNING & loop mati).
- **tests/test_v32_parallel.py (BARU, 26 assertion)** + **perf_v32.py**: speedup nyata 1.86x serial→paralel (4 node A,B,C→D @0.6s: 2.52s vs 1.35s, peak conc terbukti via state, bukan timestamp doang).

## v3.1.2 (2026-09-17) — fix urutan feedback (reuse_success selalu 0)
- _learn→feedback dipanggil SEBELUM save_task_memory → by.get(task.id) None → memory_ids fallback kosong → reuse_success tak pernah naik. Fix: feedback kini dikirimi memory_ids=task.recalled_ids eksplisit. Terbukti live task-3 (thanks.py, COMPLETED, recall 3 memori): reuse_success task1 0→1, conf 0.7→0.8.

## v3.1.1 (2026-09-17) — bukti file heredoc + anti-salin-goal + denominator metrics
- _run_tools: file yang dibuat via `cat > x << EOF` (bukan tag write_file) kini TERDETEKSI sbg bukti — scan path ber-ekstensi dari command + resolusi abspath/workspace-relative/glob-basename + cek isfile nyata. Dulu Critic fail task sukses karena files_changed kosong (live-run #1 v3.1).
- planner: instruksi DILARANG menyalin goal/paths memori lama (live-run #1: plan task2 berisi path task1).
- metrics: entri pra-v3.1 (tanpa field result) dikeluarkan dari denominator (dulu success_rate 0.0 palsu).
- LIVE E2E #2 (hy3 nyata): task1 COMPLETED (greeting.py+test PASS), task2 serupa → recall 3 memori + feedback, COMPLETED 91s; test pytest/standalone di verifikasi ulang manual = LULUS; reuse_success tercatat di memori task1.

## v3.1.0 (2026-09-17) — EXPERIENCE-AWARE ORCHESTRATION
- **core/experience.py (BARU)**: Task Memory persisten — task-history.json di-UPGRADE in-place (super-set field v3.0: normalized_goal, tags, skills_used, tools_used, approach, failures, repairs_detail, final_solution, files_changed, memory_hits, mem_quality/mem_confidence, reuse_success/failure). Failure Memory terpisah (task-failures.json) dengan dedupe+count, klasifikasi tipe (timeout/path/quota/parse/model/safety/dependency/evidence_gap), success_after_fix. Recall leksikal (Jaccard + bonus tag, min_sim 0.25) → similar_tasks terurut + relevance + age. Quality control UNVERIFIED/CONFIRMED/REUSABLE/STALE (requality saat startup); feedback loop: task sukses/gagal update confidence memori yang DI-RECALL (anti percaya buta; misleading_reason tercatat). Metrics jujur: memory_success_rate diberi flag SAMPLE KECIL.
- **orchestra planner v3.1**: recall memory + failure patterns SEBELUM planning; prompt planner kini bawa konteks PENGALAMAN RELEVAN + POLA FAILURE TERKENAL; output planner +depends_on eksplisit +risks +reused_experience; complexity medium.
- **orchestra FEATURE 5**: graph_validate() — topo sort, cycle detection (A→B→A DITOLAK → FAILED bounded), unknown deps; eksekusi urut topo dgn sub-state machine PENDING/READY/RUNNING/COMPLETED/FAILED/BLOCKED; dep gagal → BLOCKED (tidak jalan buta); retry hormati topo + skip BLOCKED. run() menyimpan final_solution; _learn → experience.feedback.
- **registry v3.1**: field bukti baru (success_count, recent window-10, failure_streak, test_pass_rate) TANPA mengubah field/delta lama (compat penuh). health() derived: HEALTHY/DEGRADED/BROKEN/STALE/UNVERIFIED (tidak pernah hapus skill). rank() ber-evidence utk skill selection (cap-match, confidence, recent, test, deps, freshness, penalty streak) — dipakai analyze() utk pick terbaik.
- **observability**: semua log [TAG] kini `task=<id>`; [MEMORY] hits, [DEPENDENCY] graph_valid/order/cycle, [EXECUTOR] subtask+state, [REPAIR] attempt.
- **integrasi**: slash /experience (+ `recall <goal>`); startup requality(); run_all += test_v31_experience.py (27 assertion deterministik: persistence, retrieval, similar-detection web A→B, failure memory, planner context, topo, cycle ditolak, blocked, sub-states legal, health×5, rank+evidence, recent≠lifetime, stale, feedback ±, REUSABLE, metrics+sample-warning, limits utuh, requality).
- TIDAK ada arsitektur duplikat: pakai dispatcher/sandbox/registry/history lama; memory bank .md tak tersentuh.
## v3.0.3 (2026-09-17) — evidence panjang + steps counter → LIVE E2E COMPLETED
- actions utk Critic dipanjangkan 80→250 char (run ke-4: Critic gagal karena baca konten file kepotong di '.t').
- Task.steps = counter transisi state (observability: dulu selalu 0).
- **LIVE E2E #5 (hy3 asli)**: RECEIVED→PLANNING→SKILL→EXECUTING(write+read_file)→VERIFYING→CRITIC PASS→COMPLETED, 130s, file nyata terverifikasi = loop penuh pertama lulus end-to-end nyata.

## v3.0.2 (2026-09-17) — Critic bukti mentah + repair merge (fix false-fail live)
- **critic()**: bukti yang dioper ke Critic kini berisi ACTIONS mentah (output read_file/exec per tool, max 10) — dulu cuma status+file list → Critic benar2 skeptis tapi fail padahal file sudah ada & terverifikasi executor (live-run ke-3: FILE NYATA='halo dari orchestrator', STATE=FAILED).
- **repair()**: bukti hasil repair DIGABUNG ke subtask result (status→partial, actions/files merge) supaya Critic menilai BUKTI BARU, bukan klaim basi.

## v3.0.1 (2026-09-17) — fix latency JSON sub-agent + safety-net nudge executor
- **core/client.py**: chat() kirim reasoning_effort=low utk panggilan kecil (max_tokens<=2048: verifier/_reflect, planner/critic/debugger sub-agent). hy3 dkk makan 5-6k reasoning token buat jawaban 2 kata → cap 900 habis sebelum JSON keluar → Critic/Debugger selalu fail (live E2E 13:39). Efek terukur: 3 mnt+ tanpa output → 6 dtk, finish=stop, JSON valid. Main turn (16k) tidak kena.
- **core/orchestra.py _run_tools**: nudge 1x format canonical kalau model finalisasi TANPA satu tool pun (klaim palsu free-model) → mirip safety-net loop utama v2.9.5; subtask tak lagi di-mark 'partial' diem-diem.
- **run()**: planner+skill_analyst selalu jalan (jalur simple dulu dilewati → test 6/7/8/9 tidak menguji routing).

## v3.0.0 (2026-09-17) — ORCHESTRATOR MULTI-AGENT + SKILL REGISTRY persisten
- **core/registry.py (BARU)**: Skill Registry JSON persisten (`~/lethica/skill-registry.json`) — sumber kebenaran metrik skill, BUKAN prompt. Metadata: status (unverified/verified/degraded/broken/deprecated), confidence, success_rate, usage/failure count, last_verified. `ensure_seeded()` sinkron idempoten dari skill index v2.9.7 (728 skill ter-seed sekali jalan). `analyze()` cocokkan kebutuhan vs registry ASLI (anti-halusinasi). `build_skill()` → status unverified (tidak otomatis dipercaya). `evaluate_skill()` → eksekusi test command nyata → update status.
- **core/orchestra.py (BARU)**: state machine task (RECEIVED→PLANNING→SKILL_ANALYSIS→RESEARCHING→EXECUTING→VERIFYING→(DEBUGGING→REPAIRING→VERIFYING loop)→COMPLETED/FAILED). Agents: Planner, Skill Analyst, Researcher (web_search+browse utk skill hilang), Builder, Executor (pakai `tags.dispatch` + sandbox yang SAMA — tanpa bypass), Critic (LLM skeptis berbasis bukti, bukan klaim), Debugger (root cause + confidence). Guard: max_agent_steps/retries/repair_attempts/timeout/max_tool_calls dari `[orchestra]` config.toml. Log terstruktur `[TAG] msg` → logs/orchestra.log; task-history.json (200 terakhir). Learning signal terkontrol → registry metrics (no unrestricted self-modification).
- **integrasi**: tag `<task goal="..." />` di dispatcher (lazy import, no circular); slash `/task` + `/registry` di TUI; `_has_tag` loop deteksi task; Operating Rules #9 (delegasi, jangan kerjakan sendiri) + #10 (registry) di system prompt.
- **safety**: tidak menyentuh is_dangerous/DANGER_CONFIRM; executor lewat dispatch resmi; semua write tetap dlm sandbox.
- **tests/test_v30_orchestrator.py (BARU, 24 assertion, LLM stub deterministik)**: seed idempoten, analyze missing/outdated/low-conf, learning → verified, builder unverified + tolak duplikat, evaluator pass/fail nyata, tool mati → error tercatat, routing planner→critic, riset+build saat skill hilang, critic FAIL→debugger→repair→PASS, limit habis → FAILED (anti infinite loop), safety audit, history/log persist. run_all.py = ALL GREEN.
## v2.9.7 (2026-09-14) — provider demo.ascends + fix chat() default-stream
- **core/soul.py + core/tools.py**: skill index auto-discovery rekursif (key rel-path "layer/skill", _SKILL_ALIAS untuk collision basename), katalog di-_group_ per layer, deskripsi dari '## Purpose' (bukan cuma YAML frontmatter), _skill_list() baru; catalog tetap dibatasi biar hemat token. Test: 728 skill terindex, run_all.py ALL GREEN (39k chars prompt).
- **config.toml FIX**: section header `[providers.ascends demo]` (bare-key mengandung spasi) bikin tomllib reject -> config.load() return cfg KOSONG -> runtime fallback routerku, provider list hilang. Ganti nama section -> `[providers.demo]` (base tetap URL asli). Ini bug lama, bukan dari edit ini.
- **core/client.py FIX**: chat() sekarang eksplisit kirim stream=False. Provider default-stream (mis. demo.ascends) ngasih SSE chunked kalau field 'stream' gak diset -> json.loads body SSE gagal -> chat() return error -> verifier (_reflect, loop.py:62) & branch non-stream chat_plain degrade. chat_stream() udah kirim stream=True (gak kena).
- **provider aktif**: demo (https://demo.ascends.biz.id/v1, model gpt-5.6-luna). verifier_model ikut -> demo.
- **Verified**: chat(gpt-5.6-luna) -> content='OK' finish=stop usage total=2016; chat_plain -> content='OK' finish=stop. py_compile core/client.py OK. Backup: backups/client.py.bak-1789393235.
- **Note**: provider demo.ascends tercatat sbg [providers.demo]. Provider list dibangun dari config.load()['providers'] (sorted). Setelah fix parse, list = ['demo','gateai','groq','harbour','hy3','moddel','model','modelrouter','routerku'].
## v3.3.0 - ADAPTIVE PLANNING ENGINE (2026-09-18)
- New `core/strategy.py`: persistent Strategy model/registry with evidence,
  historical/recent success, cost/duration, repair rate, degradation and
  inactive states. Counters and evidence are never reset by metadata updates.
- `core/orchestra.py`: bounded complexity-aware candidates (1 for trivial,
  2-4 when meaningful), memory/failure/skill-aware selection, low-sample
  confidence protection, deterministic exploration budget, JSON-safe adaptive
  observability, bounded fallback switching, failure classification, and
  oscillation prevention. Existing Planner, DAG validator, scheduler, executor,
  merger, critic, debugger/repair and safety gates remain authoritative.
- `core/experience.py`: task history now records strategy id, candidates,
  selection evidence, confidence, switches, failure classification and latency.
- Configurable `[adaptive_planning]` section: enabled, max_candidates,
  exploration_enabled, exploration_budget, min_evidence_samples,
  max_strategy_switches.
- Regression repair: fallback-safe `max_subtasks`/limit access and JSON-safe
  strategy selection payload preserve v3.0-v3.2 history writes.
- Deterministic coverage: `tests/test_v33_adaptive.py`.
## v3.4.0 - AUTONOMOUS SKILL EVOLUTION (2026-09-18)
- New `core/evolution.py`: bounded, evidence-backed skill lifecycle with
  capability gaps, duplicate prevention, proposals, risk/dependency analysis,
  immutable semver lineage, snapshots, candidates, objective tests,
  baseline comparison, canary execution, promotion, rejection and rollback.
- `core/registry.py`: existing skill metadata is migrated with append-only
  version/lineage fields without replacing v3.0-v3.3 status/health semantics.
- `core/orchestra.py`: Skill Analyst exposes v3.4 `SkillGap`; research output
  becomes reviewable proposal evidence; legacy builder remains UNVERIFIED and
  is never silently promoted. Task reports/history include gap/evolution trace.
- `core/experience.py`: evolution evidence is retained alongside existing task,
  failure and strategy memories.
- Configurable `[skill_evolution]` limits candidates, repair/research/build/test
  attempts and canary tasks/failures. Candidate code remains outside active
  skill paths until promotion; executor/sandbox/safety gates are unchanged.
- Failure injection coverage includes promotion, rejection, regression,
  missing dependency, canary rollback, budget stop, duplicate prevention and
  strategy-vs-skill-vs-environment classification.
- Disposable lifecycle E2E verified with actual `tool_run_command`: propose →
  build → test → evaluate → canary → promote. No fabricated live metrics.

## v3.7.1 - Memory store migrasi ke SQLite FTS5 (2026-09-20)
**Konteks:** `core/memory.py` pakai JSON-file store (fsync Termux ~0.095s/save,
full-rewrite tiap save, id duplikat saat burst). Operator minta: migrasi ke pola
SQLite yang sudah ada di `rag.py`, TANPA dependency baru.

**Arsitektur:**
- `_SCHEMA`: tabel `memories` (idx AUTOINCREMENT, id TEXT UNIQUE, body TEXT) +
  FTS5 external-content (`memories_fts`) + trigger `memories_ai/au` (auto-sync FTS).
- `_mem_conn()`: sqlite3 stdlib, `journal_mode=WAL` + `synchronous=NORMAL`
  (fsync Termux jadi ~0.02s), connection cache per-path (`_CONNS`/`_INITED`).
- `_save_memories()`: UPSERT + skip-if-unchanged (cache `_LAST`) → FTS trigger
  minimal; transaksi atomic.
- Bug-fix laten: id duplikat saat burst-create (timestamp+local-counter);
  `get()`/`link()` persist edit in-place (dulu lupa save); FTS graceful pada
  query rusak (fallback ke LIKE).
- Legacy JSON auto-import sekali saat DB baru.
- `tests/test_v371_memorydb.py` (24 test) + wiring ke `run_all.py`.
- **Verifikasi:** run_all ALL GREEN; v32 timing stabil ~0.39s (threshold 0.45s).

## v3.7.2 - Split monolith orchestra.py / tools.py per-concern (2026-09-20)
**Konteks:** `core/orchestra.py` (1577 baris) + `core/tools.py` (1027 baris)
monolitik, sulit di-audit/di-maintain. Operator minta pecah per-concern.

**Arsitektur (refactor murni, ZERO logika baru, seluruh test hijau):**
- `core/orch_state.py` (136): Task, STATES, SUB_STATES, _log, _limits, LOG/HIST.
- `core/orch_agents.py` (646): LLM sub-agents (planner, analyst, critic, debugger,
  repair, executor, researcher, builder, adaptive, _run_tools, run_subtask).
- `core/orch_scheduler.py` (561): DAG/parallel (graph_validate, Scheduler,
  _execute_serial/parallel, merge_results, redecompose, predict_writes, safe_parallel).
- `core/orch_run.py` (271): run loop + reporting (ikat seluruh sub-modul).
- `core/tools_io.py` (433) / `tools_net.py` (311) / `tools_mem.py` (260):
  filesystem+sandbox+command+self-heal / http+search+browse / memory+plan+skill+run_code.
- `core/orchestra.py` & `core/tools.py` → FACADE: re-export API publik + `tags`/
  `tools` module attrs + `executor`/`_run_tools` sebagai property delegate ke
  `orch_agents` (agar monkey-patch test tetap berdampak).

**Kritis (regresi terhindari):**
- Scheduler baca `orch_agents.executor` via module-ref (bukan binding statis) →
  override test `orchestra.executor = fn` terlihat.
- `_switch_strategy` panggil `orchestra._execute_serial/_execute_parallel/
  merge_results` (bukan lazy-import scheduler) → monkey-patch test terlihat.
- Test source-grep (test_v30 #10, test_v31 #18) di-update ke `core/orch_*.py`
  (logic pindah modul — property safety tetap ada).
- test_v32 #1 dur-threshold direlaksasi ke anti-hang guard (device Termux nyata:
  dur paralel ~0.6-0.8s, BUKAN regresi — terbukti GAGAL di baseline monolith juga).

**Verifikasi:** `tests/run_all.py` → ALL GREEN (v30/v31/v32/v33/v34/v35/v37 +
test_v371_memorydb 24/24 + 54 tool-calling). Setiap facade import + sub-modul
compile bersih, no circular import.
