# Static review of Android/Kotlin projects on Termux (no JDK)

Termux has no JDK/Android SDK, so `gradlew` and `kotlinc` cannot run. Do a STATIC review instead — say so explicitly to the user; do not attempt installs mid-task.

## Working approach
1. Read core files fully with read_file (use offset paging for 1000+ line files).
2. Grep sweeps for risk patterns:
   - `TODO|FIXME|XXX|HACK`
   - `!!.` non-null assertions outside `runCatching` (fragile-but-safe pattern worth noting, not a bug per se)
   - `printStackTrace`, bare `catch {}` swallowing errors
   - `Thread(` usage near shared mutable state (check for synchronization / ThreadLocal / message-passing)
3. Test-coverage map:
   - `grep -c "@Test" app/src/test/**/*.kt | awk -F: '{s+=$2} END{print "total @Test:", s}'`
   - Diff main-source class names against test filenames to list untested modules.
4. Report honestly: findings are STATIC only. Claims like "all N tests pass" that come from repo docs were not executed — attribute them explicitly.

## Java archive (.jar / J2ME MIDlet) analysis
- `unzip -l x.jar | head/tail` lists contents and totals.
- `unzip -p x.jar META-INF/MANIFEST.MF` instantly identifies MIDlet-Name, main class (`MIDlet-1: ...,<class>`), vendor, CLDC/MIDP versions.
- Obfuscated single-letter `.class` files are normal in game jars; assets (png/ttf/onnx) are directly readable after extract.

## Zip hand-off hygiene check
When analyzing a project zip the user may redistribute, scan for secrets FIRST and flag loudly:
- `keystore.properties` / `*.jks` (Android release signing keys = leaked signing identity)
- `.env`, tokens in config files
- Also note bloat dirs (`.git/`, `.android/`, `node_modules/`) that should be excluded from distribution zips.
