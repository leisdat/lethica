import sys
sys.path.insert(0, '/data/data/com.termux/files/home/lethica')
from core import loop, ui, tags, tools, config, tokens, rag, soul, client, cache, stats

# ── apply_window ──
msgs = [{"role": "system", "content": "sys"},
        {"role": "user", "content": "T<tool_response>" + "y" * 3000 + "</tool_response>"}]
for i in range(28):
    msgs.append({"role": "user" if i % 2 == 0 else "assistant", "content": f"msg {i} " + "x" * 100})
out = loop.apply_window(msgs)
assert out[0]["role"] == "system"
carry = out[1]["content"]
assert "Earlier context" in carry, "carry-over hilang"
assert "(+1000 chars" in carry or "chars, baca ulang via tool" in carry, "smart-truncation marker hilang"
assert len(carry) < 6000, "carry kepanjangan"
print("apply_window OK |", len(msgs), "->", len(out), "| carry", len(carry), "chars")

# ── terse_filter ──
assert ui.terse_filter("Sure! here is the answer") == "here is the answer"
assert ui.terse_filter("<system-reminder>no</system-reminder>real text") == "real text"
assert "language model" not in ui.terse_filter("As an AI language model, I cannot help.")
print("terse_filter OK")

# ── web search (live) ──
r = tools.tool_web_search("test query python", 2)
assert '"url"' in r, "search gagal"
print("web_search OK (hasil:", len(r), "chars)")

# ── cache roundtrip + purge fix ──
cache.put("u:k", "v", ttl=60)
assert cache.get("u:k", ttl=60) == "v"
n = cache.purge(ttl=0)
assert isinstance(n, int)
print("cache OK | purge rowcount", n)

# ── config reload idempotent ──
old = {n: getattr(config, n) for n in ("WINDOW_SIZE", "PERSONA_MODE", "ACTIVE_PROVIDER")}
config.reload_globals()
for n, v in old.items():
    assert getattr(config, n) == v, f"reload ubah {n}"
print("config.reload_globals idempotent OK")

# ── dispatch + strip_tags ──
sample = '<read_file path="/tmp/x" />jawaban<invoke name="a"><parameter name="command">ls</parameter></invoke>'
assert "jawaban" in tags.strip_tags(sample) and "invoke" not in tags.strip_tags(sample)
print("strip_tags OK")

# ── module import integrity (semua core) ──
import importlib
for m in ("config", "client", "tools", "tags", "rag", "soul", "ui", "tokens", "stats", "cache", "loop"):
    importlib.reload(getattr(__import__("core." + m, fromlist=["x"]), "__self__") if False else sys.modules["core." + m])
print("all core modules import OK")

# ── entry re-exports ──
import importlib.util
spec = importlib.util.spec_from_file_location("lethica_entry", "/data/data/com.termux/files/home/lethica/lethica.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
for attr in ("LClient", "chat_failover", "build_system_prompt", "terse_filter", "dispatch",
             "strip_tags", "tool_self_check", "tool_rag", "save_snapshot", "load_history", "save_history",
             "SELF_PATH", "LETHICA_DIR", "WORKSPACE", "DEFAULT_BASE", "API_KEY", "DEFAULT_MODEL",
             "MAX_TOKENS", "TEMPERATURE", "MAX_TOOL_ROUNDS", "WINDOW_SIZE", "PERSONA_MODE",
             "HTTP_TIMEOUT", "SEARCH_LIMIT", "DANGER_CONFIRM", "FAILOVER_CHAIN", "STREAM"):
    assert hasattr(mod, attr), f"missing {attr}"
print("lethica.py re-exports OK")

print("\nALL CHECKS PASSED")
