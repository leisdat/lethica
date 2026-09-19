---
name: hermes-termux-maintenance
description: "Update & fix Hermes di Termux (API level, cache, stash)."
---

# Hermes Termux Maintenance

Updating Hermes Agent on Termux/Android has known failure modes that require env vars and cache clearing — Rust/C extensions compile from source (no prebuilt wheels for aarch64 Android).

## Trigger
- "update Hermes" / "hermes update gagal"
- build error jiter/pydantic-core/cryptography di Termux
- "berat setelah update" / bersihin cache
- conflict stash setelah update

## Update workflow (validated 2026-09-03, v0.20.6 → v0.21.0)

1. **Backup**: `cp -r ~/.hermes ~/.hermes-backup-$(date +%Y%m%d-%H%M%S)` — config, .env, skills, memories, cron, jailbreak-templates. Jangan backup hermes-agent repo (restore dari git).
2. **Jalankan**: `hermes update` (background, 5-15 menit). Auto-stash perubahan lokal (SOUL.md, prompt_builder.py).

### Fix 1: ANDROID_API_LEVEL (error maturin "Failed to determine Android API level")

```bash
# Cek platform tag yang diharapkan Python:
venv/bin/python -c "import sysconfig; print(sysconfig.get_platform())"
# → android-30-arm64_v8a (API 30, bukan 33 walau Android 13)

# Set env saat install — HARUS SAMA dengan tag yang diharapkan
ANDROID_API_LEVEL=30 ~/.hermes/bin/uv pip install -e . --python venv/bin/python
```

**Pitfall**: Kalau set 33 → jiter build jadi `android_33_arm64_v8a.whl` → uv tolak ("not compatible with current Python"). Selalu cek `sysconfig.get_platform()` dulu.

### Fix 2: Corrupted build cache (linker error "no such file ... .rcgu.o")

pydantic-core (dan package Rust lain) bisa gagal link karena cache korup dari build sebelumnya:

```bash
rm -rf ~/.cache/uv/sdists-v9/pypi/pydantic-core*
ANDROID_API_LEVEL=30 ~/.hermes/bin/uv pip install -e . --python venv/bin/python
```

### 3. Post-update: stash conflict resolution

`hermes update` me-stash modifikasi lokal. Setelah update:

```bash
cd ~/.hermes/hermes-agent
git stash apply --index stash@{0}   # apply (bukan pop) — stash tetap aman
# Kalau CONFLICT di prompt_builder.py: gabung kedua sisi
# (keep upstream feature + local RED-TEAM block), hapus marker
git add -A && git commit -m "merge: upstream + local mods"
git stash drop stash@{0}   # setelah yakin
```

Conflict umum di `agent/prompt_builder.py` karena upstream nambah fitur di area yang sama dengan mod lokal. Jangan pilih salah satu — merge kedua sisi.

### 4. Verify

```bash
hermes --version        # → v0.21.0
ps aux | grep "hermes gateway"   # gateway jalan
```

### 5. Cleanup

```bash
rm -rf ~/.cache/uv      # 2.1GB cache build — aman dihapus
```

## Pitfall

- `pip install frida-tools` di Termux juga gagal (no wheel aarch64) — beda konteks, client frida dari PC.
- Update compile 5+ rustc paralel → HP ngelag (load 70+, RAM 2GB+). Wajar, biarin kelar.
- Jangan kill update di tengah — git udah reset, tinggal fix dependency.
- psutil di-build khusus Termux oleh script update (Linux source path compatibility) — jangan di-uninstall.
