# core/config.py — paths, config.toml, derived globals (single source of truth)
import os

HOME = os.path.expanduser("~")
# LETHICA_DIR bisa di-redirect via env (test isolation). Tanpa env = default
# ~/lethica (backward-compat penuh; production tidak pernah set env ini).
LETHICA_DIR = os.environ.get("LETHICA_DIR") or os.path.join(HOME, "lethica")
WORKSPACE = os.path.join(LETHICA_DIR, "workspace")
TASK_DIR = None   # v3.2: scope direktori task aktif (di-set orchestra saat run)
BACKUP_DIR = os.path.join(LETHICA_DIR, "backups")
LOG_DIR = os.path.join(LETHICA_DIR, "logs")
MEMORY_DIR = os.path.join(LETHICA_DIR, "memory")
PLAN_DIR = os.path.join(WORKSPACE, "plans")
SNAPSHOT_DIR = os.path.join(WORKSPACE, "snapshots")
CONFIG_FILE = os.path.join(LETHICA_DIR, "config.toml")
for _d in (WORKSPACE, BACKUP_DIR, LOG_DIR, MEMORY_DIR, PLAN_DIR, SNAPSHOT_DIR):
    os.makedirs(_d, exist_ok=True)

SELF_PATH = os.path.join(LETHICA_DIR, "lethica.py")
CORE_DIR = os.path.join(LETHICA_DIR, "core")
VERSION_FILE = os.path.join(LETHICA_DIR, ".lethica_version")
HISTORY_FILE = os.path.join(LETHICA_DIR, "history.json")
CHANGELOG_FILE = os.path.join(LETHICA_DIR, "changelog.md")
SESSIONS_DIR = os.path.join(LETHICA_DIR, "sessions")
os.makedirs(SESSIONS_DIR, exist_ok=True)

# Sandbox: commands & file writes confined to these paths.
SANDBOX_DIRS = [WORKSPACE, LETHICA_DIR, "/tmp"]

DEFAULT_CONFIG = """# Lethica v3.4.0 config
[server]
base = "http://127.0.0.1:20130/v1"   # routerku endpoint
key = "sk-routerku"                   # any non-empty key works (routerku bypass auth)

[model]
default = "Free-All"                  # model awal
max_tokens = 2048
temperature = 0.4
max_tool_rounds = 8                   # max tool-loop per turn
window_size = 17                      # sliding window (mode 3)
failover = ["Free-All", "Free-Kombo", "L"]  # chain failover v2.1
stream = true                         # SSE streaming v2.1 (teks realtime)
daily_budget = 0                      # v2.5: token budget/hari (0 = off), warning di 80%

[persona]
mode = "bypass"                       # "bypass" (unbound+4mode) | "plain" (technical assistant only)
name = "lethica"

[tools]
danger_confirm = true                 # confirm dangerous shell commands
http_timeout = 60
search_limit = 5

[adaptive_planning]
enabled = true
max_candidates = 4
exploration_enabled = true
exploration_budget = 0.15
min_evidence_samples = 3
max_strategy_switches = 2

[skill_evolution]
enabled = true
max_candidates_per_task = 1
max_repair_iterations = 2
max_research_calls = 5
max_build_attempts = 2
max_test_attempts = 3
max_canary_tasks = 3
max_canary_failures = 1
"""


def load_config():
    """Load config.toml → dict. Tomllib (py3.11+) dengan fallback parser mini."""
    cfg = {"server": {}, "model": {}, "persona": {}, "tools": {}}
    if not os.path.isfile(CONFIG_FILE):
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            f.write(DEFAULT_CONFIG)
    try:
        import tomllib
        with open(CONFIG_FILE, "rb") as f:
            raw = tomllib.load(f)
    except ImportError:
        section = None
        with open(CONFIG_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.split("#", 1)[0].strip()
                if not line:
                    continue
                if line.startswith("[") and line.endswith("]"):
                    section = line[1:-1]
                    continue
                if "=" in line and section:
                    k, v = line.split("=", 1)
                    v = v.strip().strip('"').strip("'")
                    if v.lower() in ("true", "false"):
                        v = v.lower() == "true"
                    elif v.isdigit():
                        v = int(v)
                    cfg.setdefault(section, {})[k.strip()] = v
        return cfg
    except Exception:
        return cfg
    for sec in cfg:
        if isinstance(raw.get(sec), dict):
            cfg[sec].update(raw[sec])
    # merge section lain (mis. [providers.*]) yang gak ada di default cfg
    for sec, val in raw.items():
        if isinstance(val, dict):
            cfg.setdefault(sec, {}).update(val)
    return cfg


CFG = load_config()


def get_version():
    try:
        if os.path.isfile(VERSION_FILE):
            v = open(VERSION_FILE).read().strip().split("\n")[0]
            if v:
                return v
    except Exception:
        pass
    return "3.7.0"


VERSION = get_version()

# Fallback chain untuk derived globals: (section, key, default)
# Urutan = urutan assign di reload_globals().
_DERIVED = [
    ("DEFAULT_BASE",    ("server", "base", None)),
    ("API_KEY",         ("server", "key", None)),
    ("DEFAULT_MODEL",   ("model", "default", None)),
    ("MAX_TOKENS",      ("model", "max_tokens", 4096), int),
    ("TEMPERATURE",     ("model", "temperature", 0.4), float),
    ("MAX_TOOL_ROUNDS", ("model", "max_tool_rounds", 8), int),
    ("MAX_CONTINUE_ROUNDS", ("model", "max_continue_rounds", 12), int),
    ("WINDOW_SIZE",     ("model", "window_size", 17), int),
    ("PERSONA_MODE",    ("persona", "mode", "bypass"), str),
    ("HTTP_TIMEOUT",    ("tools", "http_timeout", 60), int),
    ("SEARCH_LIMIT",    ("tools", "search_limit", 5), int),
    ("DANGER_CONFIRM",  ("tools", "danger_confirm", True)),
    ("FAILOVER_CHAIN",  ("model", "failover", ["Free-All", "Free-Kombo", "L"])),
    ("STREAM",          ("model", "stream", True)),
    ("SHOW_REASONING",   ("model", "show_reasoning", False)),
    ("AUTOLOAD_SKILLS",  ("skills", "autoload", []), list),
    ("NATIVE_FC",        ("model", "native_function_calling", True)),
]


def _read_derived(cfg, prev):
    """Derive semua global dari cfg. prev = dict nilai lama sebagai fallback
    (kalau key hilang dari config.toml, nilai lama dipertahankan)."""
    out = {}
    for item in _DERIVED:
        name, (sec, key, dflt) = item[0], item[1]
        cast = item[2] if len(item) > 2 else None
        fallback = prev.get(name, dflt)
        val = cfg.get(sec, {}).get(key, fallback)
        if cast:
            val = cast(val)
        if name == "API_KEY":
            val = os.environ.get("LETHICA_KEY") or val
        out[name] = val
    out["DAILY_BUDGET"] = int(cfg.get("model", {}).get("daily_budget", 0) or 0)
    out["ACTIVE_PROVIDER"] = cfg.get("model", {}).get("provider", "routerku")
    out["VERIFIER_MODEL"] = cfg.get("model", {}).get("verifier_model", "")
    return out


_GLOBAL_NAMES = [i[0] for i in _DERIVED] + ["DAILY_BUDGET", "ACTIVE_PROVIDER", "VERIFIER_MODEL"]

# init dari CFG (module-level, sekali) — eksplisit biar static analysis nemu semua nama
_d0 = _read_derived(CFG, {})
DEFAULT_BASE, API_KEY, DEFAULT_MODEL = _d0["DEFAULT_BASE"], _d0["API_KEY"], _d0["DEFAULT_MODEL"]
MAX_TOKENS, TEMPERATURE, MAX_TOOL_ROUNDS, MAX_CONTINUE_ROUNDS = _d0["MAX_TOKENS"], _d0["TEMPERATURE"], _d0["MAX_TOOL_ROUNDS"], _d0["MAX_CONTINUE_ROUNDS"]
WINDOW_SIZE, PERSONA_MODE = _d0["WINDOW_SIZE"], _d0["PERSONA_MODE"]
HTTP_TIMEOUT, SEARCH_LIMIT, DANGER_CONFIRM = _d0["HTTP_TIMEOUT"], _d0["SEARCH_LIMIT"], _d0["DANGER_CONFIRM"]
FAILOVER_CHAIN, STREAM, SHOW_REASONING = _d0["FAILOVER_CHAIN"], _d0["STREAM"], _d0["SHOW_REASONING"]
AUTOLOAD_SKILLS = _d0["AUTOLOAD_SKILLS"]
NATIVE_FC = _d0["NATIVE_FC"]
DAILY_BUDGET, ACTIVE_PROVIDER, VERIFIER_MODEL = _d0["DAILY_BUDGET"], _d0["ACTIVE_PROVIDER"], _d0["VERIFIER_MODEL"]
VERSION = get_version()


# ── Multi-provider (v2.6) ─────────────────────────────────────────
def providers():
    """Dict semua provider terkonfigurasi: {name: {"base":..., "key":..., "models":[...]}}."""
    out = {}
    for k, v in CFG.get("providers", {}).items():
        if isinstance(v, dict) and v.get("base"):
            out[k] = {
                "base": str(v["base"]).rstrip("/"),
                "key": v.get("key", ""),
                "models": list(v.get("models", []) or []),
            }
    # fallback: pastikan routerku selalu ada (endpoint default)
    if "routerku" not in out:
        out["routerku"] = {"base": "http://127.0.0.1:20130/v1", "key": "sk-routerku", "models": []}
    return out


def get_provider(name=None):
    """Return dict provider by name (default: aktif). None kalau gak ada."""
    name = name or ACTIVE_PROVIDER
    return providers().get(name)


def provider_names():
    return sorted(providers().keys())


def reload_globals():
    """Re-read config.toml + update module globals (dipanggil /config & /provider)."""
    global CFG, VERSION
    prev = {n: globals().get(n) for n in _GLOBAL_NAMES}
    CFG = load_config()
    for name, val in _read_derived(CFG, prev).items():
        globals()[name] = val
    VERSION = get_version()
