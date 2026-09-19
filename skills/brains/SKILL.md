# BRAINS — Cross-Session Context Manager

Skill ini nyimpen **state kerjaan aktif** (task, progress, context) biar lo bisa lanjut di platform mana pun (Termux CLI, Telegram, Discord) tanpa "eh tadi lagi ngapain ya?".

## Trigger

- "apa lagi yang lagi dikerjain?" / "lanjutin tadi" / "save context"
- Session baru dimulai (auto-load)
- Mau pindah platform tapi belum selesai

## Auto-Load (tiap session baru)

Saat skill ini loaded, LANGSUNG baca `~/.brains/current.md` dan summary-kan ke user:
```
🧠 BRAINS: Context terbaru
[TASK] <judul task>
[PROGRESS] <persentase>%
[LAST] <apa yang terakhir dikerjakan>
[NEXT] <action berikutnya>
[PLATFORM] termux|gateway
```

Kalau file tidak ada atau kosong → skip, gak perlu notif.

## Auto-Save (tiap akhir task/review)

Gue wajib save context kalau:
- Task selesai/berhenti sementara
- Mau pindah ke platform lain
- Ada perubahan penting (file dimodif, command dijalankan)
- User minta "save"

### Format: Session File
Simpan ke `~/.brains/sessions/YYYY-MM-DD_HH-MM-SS.md`:
```markdown
# Session: <judul>
## Task
- <deskripsi task>
## Progress
- [x] step 1
- [ ] step 2 (terhenti di sini)
## Context
- File: ~/path/to/file
- Command: <command terakhir>
- Error terakhir: <jika ada>
## Next Action
- <yang harus dilanjutin>
```

### Format: Current State (ringkas)
Update `~/.brains/current.md` (max 20 baris):
```markdown
# Aktif: <nama task>
Progress: 60%
Last: <apa yang terakhir dikerjakan>
Next: <action berikutnya>
Platform: termux
```

### Format: History Log
Append ke `~/.brains/history.json`:
```json
{
  "timestamp": "2026-08-31T14:30:00+07:00",
  "title": "Clean 9Router Combos",
  "status": "completed",
  "progress": 100,
  "platform": "termux"
}
```

## Commands (slash commands)

### `/brains save`
Simpan context sekarang. Gue otomatis eksekusi sebelum stop/berhenti.

### `/brains continue`
Muat context terakhir dan lanjutkan.

### `/brains status`
Tampilkan current state.

### `/brains list`
Daftar semua session yang tersimpan.

### `/brains clear`
Reset current state (kosongkan).

## Workflow Default

1. **Session baru** → Load `current.md` → tau lagi ngapain
2. **Task baru** → Buat session file + update current.md
3. **Setiap selesai step** → Update progress di current.md
4. **Sebelum berhenti** → Save full session file
5. **Pindah platform** → Context tetap ada di file, auto-load di platform baru

## File Locations

```
~/.brains/
  current.md          # State aktif (ringkas)
  sessions/           # Full session logs
    2026-08-31_14-30-00.md
    2026-08-31_15-45-12.md
  history.json        # Log ringkas semua session (untuk quick scan)
```

## Integration dengan Memory

- Save juga ke Hermes Memory (key: `active_task`, `task_progress`, `next_action`)
- Memory lebih cepat dibaca, file lebih lengkap untuk reference

## Contoh Penggunaan

User: "tadi lagi fix 9Router, sekarang gue pindah ke Telegram"
Bot: *load context, lanjut di Telegram tanpa kehilangan state*

User: "lanjutin yang tadi"
Bot: *baca current.md, teruskan dari progress terakhir*
