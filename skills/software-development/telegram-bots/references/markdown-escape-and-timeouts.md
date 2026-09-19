# Markdown escape + timeout lessons (Phone Vault Pro, 2026-08-24)

## 1. Markdown escaping — `Can't parse entities at byte offset N`
Rendering user content (file names, titles) with `parse_mode=MARKDOWN` crashes
with `BadRequest: Can't parse entities at byte offset N` the moment a name
contains `_`, `*`, backtick, `[`, `]`, or `~`. Real case: a file named
`Y2meta.app - Cinderella - Radja __ lirik lagu (320 kbps).mp3` broke `/list`
for a 143-file vault (offset 1016).

Sanitize EVERY dynamic string before interpolation:
```python
def esc(s): return s.replace("`","'").replace("*","").replace("_"," ").replace("[","(").replace("]",")").replace("~","-")[:42]
```
One raw name breaks the whole message, not just its own line.

## 2. yt-dlp subprocess timeout must exceed worst-case download time
Initial value 90s failed on a 24.76 MB video over mobile network (~35s at
700-900 KiB/s is fine, but slow bursts + 3-client retry chain can exceed it).
User saw `❌ Gagal: Timed out`. Verified fix: raise to 240s:
```python
stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=240)
```
Rule of thumb: timeout ≥ 3× expected download time of your max file size at
worst bandwidth; remember the fallback chain retries up to 3 clients.

## 3. SABR round 2 — `formats=missing_pot`
Later videos failed with `Only images are available for download ... Requested
format is not available` even via android/ios clients. Fix: append
`;formats=missing_pot` to every extractor-arg client spec:
```
--extractor-args "youtube:player_client=android;formats=missing_pot"
```
Verified: YOASOBI MV 7.99 MB and 24.76 MB video both download exit:0 after
this change. Keep the web→android→ios chain with this flag on all three.

## 4. UI polish pattern user responds well to
Vault messages upgraded to bordered sections and aligned columns:
```
━━━━━━━━━━━━━━━━━━━━
📦 PHONE VAULT — 143 file   Hal 1/29
━━━━━━━━━━━━━━━━━━━━
`94635960`  #foto  document  DSC 0010.JPG  6.0MB
```
Use `{k:<12} {v:>3}` column alignment for folder/type tables; header border +
footer tip line. User explicitly asked to "rapikan" messy output — keep this
format for future list/stats/help text.
