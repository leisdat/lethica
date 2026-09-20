# core/client.py — LClient: OpenAI-compatible client + streaming + failover + token accounting
import json
import time
import urllib.request
import urllib.error

from core import config, tokens

console = None  # injected by package __init__ (rich console)


class LClient:
    def __init__(self, base=None, key=None):
        self.base = (base or config.DEFAULT_BASE).rstrip("/")
        self.key = key or config.API_KEY
        self.last_usage = None  # usage dict dari call terakhir
        self.last_finish_reason = None  # "stop" | "length" | "tool_calls" | None
        self.last_tool_calls = None  # v3.7: native FC response (OpenAI shape)
        self.last_status = None  # v3.7: HTTP status terakhir (stream path)
        self.tools_rejected = False  # v3.7: provider nolak skema tools → degrade permanen/session

    def _req(self, method, path, body=None):
        url = f"{self.base}{path}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.key}",
            "User-Agent": f"Lethica/{config.VERSION}",
        }
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=config.HTTP_TIMEOUT) as r:
                return json.loads(r.read().decode("utf-8", errors="replace"))
        except urllib.error.HTTPError as e:
            return {"error": {"code": e.code, "message": e.reason}}
        except Exception as e:
            return {"error": {"code": 0, "message": str(e)}}

    @classmethod
    def for_provider(cls, name):
        """Factory: LClient dari config [providers.<name>]. Raise ValueError kalau gak ada."""
        p = config.get_provider(name)
        if not p:
            raise ValueError(f"provider '{name}' gak ada di config.toml [providers.{name}]")
        return cls(base=p["base"], key=p["key"])

    def models(self):
        d = self._req("GET", "/models")
        if "error" in d:
            return ["Free-All", "Free-Kombo", "L", "bai/hy3", "unorouter/allam-2-7b:free", "hc/MiniMax-M3"]
        return sorted([m.get("id", "") for m in d.get("data", [])])

    def chat(self, model, messages, temperature=None, max_tokens=None, timeout=None,
             tools=None):
        self.last_finish_reason = None
        self.last_usage = None
        self.last_tool_calls = None
        body = {
            "model": model, "messages": messages,
            "temperature": config.TEMPERATURE if temperature is None else temperature,
            "max_tokens": config.MAX_TOKENS if max_tokens is None else max_tokens,
            # v2.9.7: eksplisit non-stream. Provider default-stream (mis. demo.ascends)
            # ngasih SSE chunked kalau 'stream' gak diset → json.loads gagal → chat()
            # return error. Verifier (_reflect) & branch non-stream butuh ini.
            "stream": False,
            # v3.0.1: reasoning model free (hy3) makan 5-6k token buat jawaban pendek →
            # cap 900 habis, JSON verdict gak pernah keluar. Panggilan kecil (verifier,
            # planner/critic, max_tokens<=2048) minta effort rendah; main turn (16k) tidak.
            **({"reasoning_effort": "low"} if (max_tokens or 10 ** 9) <= 2048 else {}),
        }
        # v3.7: native function calling — skema dari core/tooldef.py
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        r = self._req("POST", "/chat/completions", body)
        if "error" not in r and r.get("choices"):
            ch = (r.get("choices") or [{}])[0]
            self.last_finish_reason = ch.get("finish_reason")
            # v3.7: structured tool_calls (OpenAI shape) disimpan utk dispatcher
            msg = ch.get("message") or {}
            if msg.get("tool_calls"):
                self.last_tool_calls = msg["tool_calls"]
            # v2.9.2 fix: routerku/OpenRouter taruh usage di TOP-LEVEL, bukan per-choice
            # (dulu ch.get("usage") selalu None → accounting selalu jatuh ke estimasi)
            self.last_usage = ch.get("usage") or r.get("usage")
        return r

    # ── SSE streaming ────────────────────────────────────────────────
    def chat_stream(self, model, messages, temperature=None, max_tokens=None, timeout=None, stream_cb=None,
                    tools=None):
        """Stream chat via SSE. stream_cb(delta_text, kind) per delta realtime.
        Return (content, reasoning, model_used) atau (None, None, None) kalau gagal.
        v3.7: tools → kumpul delta.tool_calls (arg arrives in fragments per index)."""
        body = {"model": model, "messages": messages,
                "temperature": config.TEMPERATURE if temperature is None else temperature,
                "max_tokens": config.MAX_TOKENS if max_tokens is None else max_tokens,
                "stream": True}
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        req = urllib.request.Request(
            f"{self.base}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.key}",
                     "User-Agent": f"Lethica/{config.VERSION}", "Accept": "text/event-stream"},
            method="POST",
        )
        content, reasoning, model_used = "", "", None
        usage = None
        tc_acc = {}   # index → {"id","type","function":{"name","arguments"}}
        self.last_finish_reason = None
        self.last_usage = None
        self.last_tool_calls = None
        self.last_status = None
        try:
            with urllib.request.urlopen(req, timeout=timeout or config.HTTP_TIMEOUT) as r:
                for raw in r:
                    line = raw.decode("utf-8", errors="replace").strip()
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload in ("", "[DONE]"):
                        continue
                    try:
                        d = json.loads(payload)
                    except Exception:
                        continue
                    model_used = d.get("model") or model_used
                    if d.get("usage"):
                        usage = d["usage"]
                    choice = (d.get("choices") or [{}])[0]
                    fr = choice.get("finish_reason")
                    if fr:
                        self.last_finish_reason = fr
                    delta = choice.get("delta") or {}
                    # v3.7: fragment tool_calls (OpenAI streaming shape)
                    for frag in delta.get("tool_calls") or []:
                        idx = frag.get("index", 0)
                        slot = tc_acc.setdefault(idx, {
                            "id": "", "type": "function",
                            "function": {"name": "", "arguments": ""}})
                        if frag.get("id"):
                            slot["id"] = frag["id"]
                        ffn = frag.get("function") or {}
                        if ffn.get("name"):
                            slot["function"]["name"] += ffn["name"]
                        if ffn.get("arguments"):
                            slot["function"]["arguments"] += ffn["arguments"]
                    if delta.get("reasoning_content"):
                        reasoning += delta["reasoning_content"]
                        if stream_cb:
                            try:
                                stream_cb(delta["reasoning_content"], "reasoning")
                            except Exception:
                                pass  # UI callback error ≠ network error (v2.8.1 fix: dulu bunuh stream)
                    if delta.get("content"):
                        content += delta["content"]
                        if stream_cb:
                            try:
                                stream_cb(delta["content"], "content")
                            except Exception:
                                pass  # idem
        except urllib.error.HTTPError as e:
            self.last_status = e.code
            return None, None, None
        except Exception:
            return None, None, None
        # v3.7: stream kosong TAPI tool_calls terakumulasi = valid (finish=tool_calls)
        if tc_acc:
            self.last_tool_calls = [tc_acc[k] for k in sorted(tc_acc)]
        if not content and not reasoning and not self.last_tool_calls:
            return None, None, None
        self.last_usage = usage
        _record_usage(model_used or model, usage, content, reasoning, messages)
        return content, reasoning, model_used

    def chat_failover(self, model, messages, models_chain=None, temperature=None, max_tokens=None,
                      timeout=None, stream_cb=None, tools=None):
        """Coba model chain berurutan. Return (reply, model_used) atau (None, None).
        Entry chain bisa 'provider::model' → route ke provider lain (v2.6).
        v2.9.5: +last-resort lintas-provider (routerku lokal) kalau SEMUA entry utama gagal —
        dulu chain yang semuanya nunjuk provider mati (mis. b.ai 429/404) → (None,None) →
        loop balik ke prompt tanpa jawaban ("berhenti di tengah").
        v3.7: tools (skema native FC). Provider yang nolak dengan 400 → retry SEKALI
        tanpa tools (degrade ke tag path) dan tandai self.tools_rejected=True."""
        chain = list(models_chain or config.FAILOVER_CHAIN)
        chain = [model] + [m for m in chain if m != model]
        # last-resort: provider lokal yang selalu ada (routerku) + model generiknya
        lr = []
        for e in ("routerku::Free-All", "routerku::Free-Kombo", "routerku::L"):
            if e not in chain and e.split("::", 1)[1] != model:
                lr.append(e)
        chain = chain + lr
        self.last_tool_calls = None
        for entry in chain:
            cl = self
            m = entry
            if "::" in entry:
                pname, m = entry.split("::", 1)
                if pname == config.ACTIVE_PROVIDER:
                    cl = self  # entry = provider aktif sendiri → jangan bikin client baru
                else:
                    try:
                        cl = LClient.for_provider(pname)
                    except ValueError:
                        if console:
                            console.print(f"[dim red]✖ provider '{pname}' gak ada, skip[/dim red]")
                        continue
            entry_tools = tools
            if stream_cb is not None:
                content, reasoning, used = cl.chat_stream(
                    m, messages, temperature, max_tokens, timeout, stream_cb, tools=entry_tools)
                if (content is None and reasoning is None
                        and entry_tools and getattr(cl, "last_status", None) == 400):
                    # provider nolak skema tools saat stream → degrade sekali
                    cl.tools_rejected = True
                    entry_tools = None
                    content, reasoning, used = cl.chat_stream(
                        m, messages, temperature, max_tokens, timeout, stream_cb, tools=None)
                if content is None and reasoning is None:
                    if console:
                        console.print(f"\n[dim red]✖ {entry} unavailable, failover...[/dim red]")
                    continue
                self.last_finish_reason = cl.last_finish_reason
                self.last_tool_calls = getattr(cl, "last_tool_calls", None)
                return content or reasoning or "(empty reply)", used or m
            for attempt in range(3):
                t0 = time.time()
                r = cl.chat(m, messages, temperature, max_tokens, timeout, tools=entry_tools)
                if "error" not in r and r.get("choices"):
                    msg = r["choices"][0]["message"]
                    reply = msg.get("content") or msg.get("reasoning_content") or "(empty reply)"
                    self.last_usage = cl.last_usage
                    _record_usage(m, cl.last_usage, reply, "", messages)
                    self.last_finish_reason = cl.last_finish_reason
                    self.last_tool_calls = getattr(cl, "last_tool_calls", None)
                    return reply, m
                # v3.7: provider nolak payload tools (400) → ulangi SEKALI tanpa tools
                err = r.get("error") if isinstance(r.get("error"), dict) else {}
                if entry_tools and err.get("code") in (400, 422):
                    cl.tools_rejected = True
                    if console:
                        console.print(f"[dim yellow]⚠ {entry} nolak skema tools (400) → "
                                      f"degrade ke tag path[/dim yellow]")
                    entry_tools = None
                    continue  # tidak dihitung sebagai retry jaringan
                # v2.8: backoff with Retry-After awareness (429 rate limit)
                err_code = err.get("code")
                err_msg = err.get("message", "")
                # v2.9.5: 404/400/401 = model/endpoint gak ada → retry gak akan nolong,
                # langsung failover (dulu buang 1+2+3s tiap turn sebelum pindah provider).
                if err_code in (400, 401, 403, 404):
                    if console:
                        console.print(f"[dim red]✖ {entry} → {err_code} {err_msg[:60]} (skip retry)[/dim red]")
                    break
                wait = 1 + attempt  # 1s → 2s → 3s
                if "429" in str(err_code) or "rate" in err_msg.lower():
                    wait = min(2 ** attempt + 2, 8)  # 2s → 4s → 8s utk rate limit
                time.sleep(wait)
            if console:
                console.print(f"[dim red]✖ {entry} unavailable, failover...[/dim red]")
        return None, None


def _record_usage(model, usage, content, reasoning, messages):
    """Token accounting: pakai usage dari API, fallback estimasi chars/4."""
    meta = {"req_chars": len(json.dumps(messages, ensure_ascii=False)),
            "reply_chars": len(content) + len(reasoning)}
    try:
        tokens.record(model, usage, meta)
    except Exception:
        pass
