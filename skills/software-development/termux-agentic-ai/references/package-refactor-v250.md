# Lethica v2.5 refactor — verification evidence & test matrix

Session 2026-09-09. Monolith `lethica.py` (1743 ln) → package (10 modules, 1996 ln total).

## Final layout with line counts

```
lethica.py 65 | core/__init__ 2 | client 137 | config 142 | loop 316 |
rag 107 | soul 203 | tags 168 | tokens 114 | tools 594 | ui 150
```

## Smoke-test sequence that caught real bugs (run after any refactor)

```python
import sys; sys.path.insert(0, '~/lethica')
from core import config, tools, tags, rag, tokens, loop
assert config.VERSION == '2.5.0'
assert tools.in_sandbox('~/lethica/workspace/x') and not tools.in_sandbox('/etc/passwd')
assert tools.is_dangerous('rm -rf /x') and not tools.is_dangerous('ls')
out = tags.dispatch('<memory action="save" key="t" content="ok" />', config.SELF_PATH)
assert 'OK memory saved' in out
# window logic
msgs = [{'role':'system','content':'s'}] + [{'role':'user','content':f'm{i}'} for i in range(30)]
w = loop.apply_window(msgs); assert len(w) == 19
```

Bridge compat check (the step that failed silently the first time — lethica.py had no re-exports):

```python
need = ['LClient','DEFAULT_BASE','API_KEY','build_system_prompt','dispatch','terse_filter',
        'strip_tags','chat_failover','FAILOVER_CHAIN','TEMPERATURE','MAX_TOKENS','HTTP_TIMEOUT',
        'SELF_PATH','MEMORY_DIR','PERSONA_MODE','STREAM','rag_stats_summary']
missing = [n for n in need if not hasattr(lethica, n)]  # must be []
```

## Tag sanitizer roundtrip matrix (6/6 after v2.5 fixes)

Roundtrip = `sanitize_tool_tags(tag)` → regex-extract attr string → `_parse_tag_attrs` → compare value.

| # | Input tag | Attr | Expected value | Bug it catches |
|---|---|---|---|---|
| 1 | `<rag action="search" query="a 'b' c" />` | query | `a 'b' c` | single-quote inside double-quoted value (v2.5 fix) |
| 2 | `<memory action='load' key='t2' />` | key | `t2` | single-quote delimiters |
| 3 | `<memory action="save" key="t1" content="say "hi" ok" />` | content | `say "hi" ok` | nested unescaped quotes + re-escape 2x (v2.5 fix) |
| 4 | `<web_search query='multi word query' limit='5' />` | query | `multi word query` | multi-word single-quote |
| 5 | `<browse url="https://x.test/p?a='q'&b=2" />` | url | `https://x.test/p?a='q'&b=2` | quote in URL querystring |
| 6 | `<memory action="save" key="t4" content="line1\nline2 'q' end" />` | content | `line1\nline2 'q' end` | escape sequences + mixed |

Pre-fix symptom for #3: `_fix_attr_quotes` correctly produced `say \"hi\" ok`, then `_normalize_tag_attr_order` escaped again → `say \\"hi\\" ok` → parser yielded `{'content': 'say \\', 'hi\\\\"': 'true', 'ok"': 'true'}`. Keep #1+#3 as regression anchors whenever the sanitizer changes.

## Token accounting (v2.5) — live evidence

```
{"ts":"08:32:06","model":"hy3","pt":67,"ct":449,"tot":516,"meta":{"req_chars":227,"reply_chars":1498}}
{"ts":"08:32:09","model":"hy3","pt":166,"ct":172,"tot":338,...}
```
- `pt`/`ct` came from routerku's `usage` in the SSE final frames — capture `d.get('usage')` per frame, keep last.
- Non-stream path: `r.get('usage')` off the completion JSON.
- `/tokens` renders 7-day table from `logs/tokens/*.jsonl` + budget bar when `daily_budget > 0`.

## TUI E2E via PTY (the only method that works with the /dev/tty stdin patch)

1. `terminal(command='cd ~/lethica && TERM=dumb python3 lethica.py', background=true, pty=true)`
2. `process_manage wait` → expect model picker + Pick model prompt
3. `process_manage submit data=''` (accept default model) — NOTE: bare `submit`/`submit text=...` without `data` sends ONLY Enter; the parameter is `data`
4. `submit data="/menu"` → wait → expect commands panel with `/tokens` line
5. `submit data="/tokens"` → expect `📊 TOKEN USAGE` + today line
6. `submit data="/exit"` → expect `signing off` + exit_code 0

Anti-pattern that wasted 3 attempts this session: piped stdin (`printf ... | python3 agent.py`) and `subprocess.run(input=...)` both hang at the first `Prompt.ask` because the agent reopens `/dev/tty`. No error surfaces — the process just shows one prompt and consumes nothing.
