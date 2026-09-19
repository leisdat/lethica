# Building a native Android APK on Termux (no Android Studio)

Verified working pipeline (Game Hub app, Aug 2026): javac -> d8 -> aapt2 -> zip -> zipalign -> apksigner, all from Termux shell.

## Toolchain facts (what NOT to assume)
- Termux `android-tools` package ships ONLY `adb`/`pwdx` — no aapt, apksigner, d8, or zipalign.
- SDK build-tools native binaries (aapt2, zipalign) are x86_64 and will NOT run on aarch64 Termux:
  `error: ".../aapt2" is for EM_X86_64 (62) instead of EM_AARCH64 (183)`.
- Java-based SDK tools (d8 script, apksigner) DO run on Termux via openjdk.

## Setup (one time)
```bash
pkg install -y openjdk-21 aapt aapt2 apksigner apkeditor zip
cd ~ && mkdir -p android-sdk && cd android-sdk
curl -sL -o cmdtools.zip "https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip"
unzip -q cmdtools.zip && rm cmdtools.zip
mkdir -p cmdline-tools/latest && mv cmdline-tools/{bin,lib,NOTICE.txt,source.properties} cmdline-tools/latest/
export ANDROID_HOME=$HOME/android-sdk
yes | ./cmdline-tools/latest/bin/sdkmanager --sdk_root=$ANDROID_HOME \
  "build-tools;36.0.0" "platforms;android-34"
```
- sdkmanager refuses to run unless the package sits at `<sdk>/cmdline-tools/latest/` (or `--sdk_root` is passed).
- **Use build-tools 36, not 34** (see d8 bug below).

## Build pipeline (the 5 steps)
1. `aapt2 compile --dir res -o build/compiled.zip`  (Termux-native aapt2!)
2. `aapt2 link -o build/apk/base.apk -I $PLATFORM --manifest AndroidManifest.xml --java build/gen --min-sdk-version 21 --target-sdk-version 34 --version-code 1 --version-name 1.0 --auto-add-overlay build/compiled.zip`
   -> generates base.apk AND build/gen/com/.../R.java
3. `javac --release 8 -encoding UTF-8 -classpath $PLATFORM -d build/obj build/gen/com/gamehub/R.java src/com/gamehub/*.java`
   (UTF-8 encoding is mandatory if sources contain emoji — they will, as UI icons)
4. `$BT/d8 --release --lib $PLATFORM --output build/dex $(find build/obj -name '*.class')`  (BT = build-tools/36.0.0)
5. `zip -q -r base.apk classes.dex` -> python zipalign (scripts/zipalign.py) -> keytool genkeypair -> `apksigner sign --ks ... --out GameHub.apk aligned.apk`

Keytool one-liner: `keytool -genkeypair -keystore app.keystore -alias app -keyalg RSA -keysize 2048 -validity 10000 -storepass pass123 -keypass pass123 -dname "CN=X, OU=Dev, O=X, L=Jakarta, ST=DKI, C=ID"`

## CRITICAL pitfalls
- **d8 (R8 8.2.2) in build-tools 34 crashes on valid bytecode**:
  `java.lang.NullPointerException: Cannot invoke "String.length()" because "<parameter1>" is null`
  Reproduced on a BaseAdapter subclass that stores a typed custom-class local
  (`GameInfo game = games.get(pos);` then reads `game.name`/`game.icon`) — but NOT on
  equivalent code using `List<String>` or a plain constant. Workarounds that FAILED:
  `String.valueOf(...)` wrapping, getter methods instead of public fields, `-g:none`,
  `--release 8` vs `--release 11`. **The fix: install `build-tools;36.0.0` and use its d8.**
  Diagnostic path that worked: compile each class separately and d8 them one at a time
  to isolate the offending .class, then bisect the source pattern.
- **AAPT2 arch mismatch**: always use the Termux `aapt2` (aarch64), never the SDK one.
  SDK apksigner/d8 are fine (Java). SDK zipalign is NOT fine (native x86_64).
- **Prefer platform APIs over AndroidX for tiny apps** — manual Maven/AAR resolution is possible
  (see [android-apk-build-full.md](android-apk-build-full.md)) but costs hours; for a simple
  single-purpose app, platform APIs are faster:
  - `ListView` instead of RecyclerView/AndroidX
  - custom `DocumentFile` replacement via `DocumentsContract.buildChildDocumentsUriUsingTree()` + `ContentResolver.query()` (a 40-line `DocFile` helper covers fromTreeUri/listFiles)
  - framework theme `android:Theme.Material.NoActionBar` instead of AppCompat
- **XML escaping**: `&` inside `android:text` must be `&amp;` or aapt2 fails
  `not well-formed (invalid token)`.
- d8 `--output` directory must already exist, else `Invalid output: ...`.
- Vector drawable as `android:icon` works for a launcher icon (aapt dump badging shows it).

## Verification (do all three before declaring success)
- `aapt dump badging GameHub.apk | grep -E "package:|launchable"` — package + launcher activity
- `apksigner verify --verbose GameHub.apk` — expect "Verified using v3 scheme: true"
- Alignment of stored entries only matters for v1 signatures; v2/v3 (default) install fine regardless. Check with a tiny python local-header walker if paranoid (data offset % 4 == 0).

## Building a large multi-module upstream app (Termux 0.118.0 mod, Aug 2026)
Lessons from building a Termux fork (4 Java modules, ~134 source files, 55 Maven deps) with no Gradle:
- **compileSdk must match the original project** — Termux 0.118.0 declares `compileSdkVersion=30` in gradle.properties. Compiling against android-34 breaks on removed APIs (`WebSettings.setAppCacheEnabled` gone in 34). Check `compileSdkVersion` in gradle.properties BEFORE picking a platform jar.
- **Pin Maven deps to the versions the module build.gradle files DECLARE, not transitive "newest wins"** — my resolver upgraded material 1.4.0→1.12.0 + appcompat 1.3.1→1.6.1, and that pair hard-conflicts in aapt2 (both define a `SearchView` styleable). `--auto-add-overlay` only overlays one app's resources; library-vs-library duplicate styleables are fatal. If you pin older top-level AARs, their older transitive deps may be missing from the cache — fetch them explicitly (dl.google.com for androidx, maven central for org.jetbrains).
- **When source imports are the source of truth**: grep `import com.x.y` across all modules to find which R packages and which library classes are actually referenced. Missing transitive annotations (org.jetbrains:annotations for @NotNull) and widgets (androidx.customview:customview for Openable, and 1.0.0 does NOT contain Openable — use ≥1.1.0) surface as "cannot access X" / "package does not exist".
- **Generated R.java for the main app package must be added to javac sources explicitly** — only the module-level R copies (com.termux.shared.R, com.termux.view.R) get copied around; the aapt2-link output `gen/com/termux/R.java` needs to be in the source list too or every `import com.termux.R` fails.
- **Multi-line javac failures**: javac reports ALL errors; fix them all at once (mine were: wrong TypedValue package in my new code, a dead import from a merge, a removed-API call, and two missing transitive deps).
- **`pm install` can be broken by the ROM** — this user's ROM throws `SecurityException: You either need MANAGE_USERS or CREATE_USERS permission to: query users` on any `pm install` from the Termux shell (PackageManagerShellCommand.translateUserId path). No root available. Fallback: `cp apk /sdcard/Download/` and have the user tap it in the Files app.
- **CRITICAL: `--rename-manifest-package` alone is NOT enough** — it only renames the package in `AndroidManifest.xml`. The `resources.arsc` table still contains the ORIGINAL package name. If these mismatch, the device shows "Problem parsing the package / ada masalah saat menguraikan paket". ALWAYS also pass:
  ```
  --rename-resources-package com.example.newname
  --rename-instrumentation-target-package com.example.newname
  --rename-overlay-target-package com.example.newname
  ```
  All three flags exist in modern aapt2. Verify with `aapt2 link --help | grep rename`. After the build, verify the arsc package matches the manifest: `python3 -c "import zipfile,struct; raw=zipfile.ZipFile('apk.apk').read('resources.arsc'); name=raw[12+12:12+12+256].decode('utf-16-le').split('\x00')[0]; print('arsc pkg:', name)"`.
- **apksigner v2+v3 verify: true** is enough on Android 11+ (v1/JAR not needed).
- **Don't `| tee` background builds** — `bash build.sh 2>&1 | tee log` masks the exit
  code (tee returns 0), so FAILED builds still arrive as "completed normally (exit code 0)"
  notifications. Stale builds from earlier attempts keep reporting long after a later run
  superseded them, which reads as confusing contradictory results. Run the build bare
  (background output is captured by the process tool), or `set -o pipefail` before the
  pipe. When an old "completed normally" notification arrives, check the artifact
  timestamp (`ls -la build/.../app.apk`) before telling the user anything.
- **APK staging for user install — name it unambiguously** — in this session the user
  looked for the built mod APK inside `termux-analysis/` (where the 101MB
  `termux-official.apk` reference lives) and nearly installed the wrong file. Stage the
  deliverable at a clean top-level path with an unmistakable name
  (`~/storage/downloads/<app>-<version>-<flavor>.apk`), state the exact filename, and
  explicitly say "NOT the <ref-dir>/<ref-apk> one".

## Notes
- **Zipalign is NOT the usual cause of "Problem parsing the package"** (Aug 2026 correction): a long debug detour blamed misaligned `resources.arsc` for a parse failure, but measuring data offset (`header_offset + 30 + len(filename) + len(extra)`, NOT `header_offset` alone) showed the failing APK was already 4-byte aligned. The actual cause was the **arsc package-name vs manifest mismatch** (see the CRITICAL bullet above → `--rename-resources-package`). Keep `scripts/zipalign.py` in the pipeline for correctness, but check arsc/manifest package consistency FIRST when diagnosing parse failures. If you do measure alignment, use the correct metric: `data_offset % 4`, not `header_offset % 4`.
- Folder-picker apps: `Intent.ACTION_OPEN_DOCUMENT_TREE` + `takePersistableUriPermission(READ)` needs no runtime permission on modern Android; recursive scan runs on a background thread.
- APK size ~21KB for a single-activity app; fine to `cp` to `~/storage/downloads/` for the user to install.
