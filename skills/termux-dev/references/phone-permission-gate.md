# Permission-gated phone skills via Termux:API (proven 2026-09-05, agent android_device v0.8)

## The pattern
SAFE actions run free; everything privacy- or system-changing returns
`{ok:False, policy_deny:True, deny_kind:"phone", deny_target:<action>}` unless
`task.grants` contains `{type:"phone", pattern}` where pattern is the action name,
a comma list (`"location,notify,vibrate"`), or `"all"`. The agent loop turns
policy_deny into `awaiting_permission`; the Telegram bot prints
`/allow <id> phone "<aksi>"` / `"all"` and `/deny`. Generic `/allow` parsing
needs no change — it already stores `{type, pattern}` verbatim.

## Tier table (28 actions)
SAFE (no grant): probe, battery, volume, audio_info, tts_engines, camera_info, sensor_list.
NEEDS phone grant: location, clipboard/clipboard_set, wifi, telephony, sensors_read,
notify, toast, tts, vibrate, torch, screenshot, brightness, wallpaper, open_url, share,
dialog, call_log, sms_list, sms_inbox, notification_list, nfc, usb.
DANGEROUS (grant + think twice): sms_send (number+text), call (number), contacts,
camera_photo, mic_record/mic_stop.

## Grant check (copy-paste)
```python
def _has_phone_grant(task, action):
    a = (action or "").strip().lower()
    for g in (task.get("grants") or []):
        if not isinstance(g, dict) or g.get("type") != "phone": continue
        pat = (g.get("pattern") or "").strip().lower()
        if pat in ("all", "*", "phone"): return True
        if pat == a or a in [p.strip() for p in pat.split(",")]: return True
    return False
```

## Correct Termux:API flags (v0.59.1 — old flags were wrong)
- location: `termux-location -p network -r once` (fallback `-p gps -r last`).
  There is NO `-m` flag. Providers: gps/network/passive; requests: once/last/updates.
- sensors: `termux-sensor -l` lists; `-s` alone is illegal (needs sensor names +
  `-n 1 -d <ms>` for one-shot reads).
- mic: `termux-microphone-record -f <file> -l <sec> -e opus`; `-q` stops, `-i` status.
- camera: `termux-camera-photo -c <id> <file>`; `termux-camera-info` lists IDs.
- brightness: `termux-brightness <0-255|auto>` (bare command prints usage, exits nonzero).

## Companion-app detection
Without the Termux:API Android app (F-Droid, pkg com.termux.api), privileged calls print
`Termux:API is not yet available ...` on stdout OR stderr. Detect the substring in
combined output and return a single `TERMUX_API_APP_MISSING` hint (install + open once
+ grant Android runtime permissions) instead of raw stderr.
Works WITHOUT the app: battery, volume, audio_info, camera_info, tts_engines,
clipboard-get, vibrate, toast, tts-speak, notify. Needs the app: wifi, telephony,
torch, notification-list, contacts, sms, call-log, sensor reads, location.

## Verification recipe (ran green)
Direct skill calls with fake tasks: SAFE ok without grants; sensitive without grant
-> policy_deny phone; with `grants:[{type:phone,pattern}]` -> executes; comma-list
and `all` honored; out-of-list action still denied. Then `executor.execute` +
`tg_bot` import to prove loop/bot wiring.
