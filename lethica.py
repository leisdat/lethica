#!/data/data/com.termux/files/usr/bin/python3
# lethica.py — Lethica v2.5 entry point (thin)
# Semua logic di core/: config, client, tools, tags, rag, soul, ui, tokens, loop.
# Run: python3 ~/lethica/lethica.py

import os
import sys

LETHICA_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, LETHICA_DIR)

if not sys.stdin.isatty():
    try:
        sys.stdin = open("/dev/tty")
    except Exception:
        pass

from core import config  # noqa: E402
from core import client as client_mod, ui, loop, tools, tags, rag, soul, tokens  # noqa: E402

# inject console ke modules yang butuh (danger confirm, failover print)
client_mod.console = ui.console
tools.console = ui.console

# ── backward-compat re-exports (lethica_bridge.py & self-mutation pakai ini) ──
LClient = client_mod.LClient
chat_failover = client_mod.LClient.chat_failover
build_system_prompt = soul.build_system_prompt
terse_filter = ui.terse_filter
dispatch = tags.dispatch
strip_tags = tags.strip_tags
tool_self_check = tools.tool_self_check
tool_rag = rag.tool_rag
rag_stats_summary = rag.rag_stats_summary
save_snapshot = ui.save_snapshot
load_latest_snapshot = ui.load_latest_snapshot
load_history = ui.load_history
save_history = ui.save_history

# config globals re-export (module attr lookup jalan karena module sama)
SELF_PATH = config.SELF_PATH
LETHICA_DIR = config.LETHICA_DIR
MEMORY_DIR = config.MEMORY_DIR
WORKSPACE = config.WORKSPACE
DEFAULT_BASE = config.DEFAULT_BASE
API_KEY = config.API_KEY
DEFAULT_MODEL = config.DEFAULT_MODEL
MAX_TOKENS = config.MAX_TOKENS
TEMPERATURE = config.TEMPERATURE
MAX_TOOL_ROUNDS = config.MAX_TOOL_ROUNDS
WINDOW_SIZE = config.WINDOW_SIZE
PERSONA_MODE = config.PERSONA_MODE
HTTP_TIMEOUT = config.HTTP_TIMEOUT
SEARCH_LIMIT = config.SEARCH_LIMIT
DANGER_CONFIRM = config.DANGER_CONFIRM
FAILOVER_CHAIN = config.FAILOVER_CHAIN
STREAM = config.STREAM


def main():
    loop.main()


if __name__ == "__main__":
    main()
