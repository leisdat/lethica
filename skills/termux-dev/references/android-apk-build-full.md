# Building a FULL Gradle Android app on Termux — manual pipeline, no NDK, no Gradle

Extends `references/android-apk-build.md` (which covers the minimal single-activity app).
This is the playbook for a real multi-module Gradle project (example in session: termux-app
v0.118.0, 4 modules, 131 Java files, 24 AAR deps, 0 Kotlin).

STATUS OF WHAT IS VERIFIED HERE (read before trusting):
- VERIFIED in-session: prebuilt-.so-from-official-APK trick + JNI symbol matching;
  `aapt2 link --rename-manifest-package` semantics (tested end-to-end on a toy manifest);
  manual Maven nearest-wins resolution of 62 deps (classpath + res dirs produced, MISSING: none);
  0-Kotlin check that makes javac+d8 viable; resource-conflict scan across AAR res dirs.
- NOT YET RUN end-to-end: the final javac -> d8 -> dex -> zip -> sign chain for the full app.
  If resuming, build it and only then promote this section to "verified".

## 0. Decide Gradle vs manual pipeline FIRST
Gradle on Termux is a deep hole: AGP version must match JDK, the NDK toolchain from
`sdkmanager` is x86_64-only and will NOT run on aarch64 (`unexpected e_type` / EM_X86_64).
If the project is all-Java (no Kotlin) and you can get the native `.so` from somewhere,
the manual pipeline wins. Check Kotlin count early:
`find app terminal-* -name "*.kt" | wc -l` — if >0, stop; Kotlin compiler via manual
pipeline is not worth it, go Gradle+JDK or prebuilt.

## 1. Native code: steal prebuilt .so from the official same-version APK
- Find the exact upstream version/tag (`aapt dump badging official.apk | grep versionName`,
  `git fetch --depth 1 origin tag v0.118.0`).
- `unzip -l official.apk "lib/arm64-v8a/*"` — Termux/F-Droid builds ship prebuilt `.so`.
- Match JNI symbols before trusting:
  `unzip -p official.apk lib/arm64-v8a/libX.so | strings | grep ^Java_` must contain every
  `native` method in the Java sources (`grep -rn "native " --include=*.java src/`).
- Drop the `.so` into `lib/arm64-v8a/` of your staged APK contents; set
  `android:extractNativeLibs="true"` (or uncompressed + aligned) and you skip the NDK.
- Do NOT `sdkmanager "ndk;..."` to "fix" the arch — it downloads x86_64 toolchain and
  cannot run here. The prebuilt-.so path is the fix.

## 2. Coexist with the installed app: package rename that KEEPS JNI
JNI symbols are keyed to the JAVA package, not the manifest package. To ship a modified
build alongside the original (e.g. a termux mod while real Termux runs):
- Keep Java sources + R package as `com.termux.*` (do NOT rename java packages).
- At link time: `aapt2 link ... --rename-manifest-package com.termux.savedtools`.
  VERIFIED: R.java is still generated as `package com.termux;`, while the compiled
  manifest installs as `com.termux.savedtools` and relative `.Foo` component names are
  rewritten to `com.termux.Foo`. So classes named `com.termux.app.TermuxActivity` still
  resolve AND the app installs side-by-side.
- If the app hardcodes its own data dir from a package constant (Termux:
  `TermuxConstants.TERMUX_PACKAGE_NAME`), patch that constant to the NEW package so the
  build is self-contained and doesn't clobber the original app's data.

## 3. Manual Maven dependency resolution (no Gradle)
No dependency graph? Write it. Verified approach (resolver script saved in-session at
`termux-app/.resolve-deps.py`, fetcher at `.maven-fetch.py`):
1. BFS from the direct deps listed in `app/build.gradle` over POMs, nearest-wins
   (first seen at lower depth is kept). Track `type` (jar/aar) — but always check BOTH
   `.jar` and `.aar` on disk because POMs often omit `<type>` for AARs.
2. Fetch from `https://repo.maven.apache.org/maven2/` and
   `https://dl.google.com/dl/android/maven2/` (androidx/material/google live on the
   dl.google.com one, NOT Maven Central). Save under `poms/` and `artifacts/` mirroring
   the maven group/artifact/version layout.
3. For each chosen AAR: `unzip -q` it into `.aars/<a>-<v>/`, add `.aars/<a>-<v>/res` to the
   aapt2 res inputs, and add `.aars/<a>-<v>/classes.jar` to the javac classpath (NOT the
   .aar itself).
4. BEFORE linking, scan for resource conflicts across all res dirs:
   - values keys (`<string|style|attr|id|...> name="x"`) appearing in >1 source
   - non-values type+filename duplicates (e.g. two `layout/foo.xml`)
   aapt2 `--auto-add-overlay` picks one by input order (later wins); a big clash set means
   you'll silently override library styles/attrs. 0 values-type conflicts is the healthy
   target.
5. Sanity: `grep -rhoE "import (androidx|com\.google|io\.[a-z]+|org\.[a-z]+)[^;]*" src/ |
   sed ...` to list every external import; each must be covered by a resolved artifact or
   it's a missing dep you forgot.

## 4. Multi-module R classes in a single flat build
All modules compile into ONE javac invocation, but each module references a DIFFERENT R
package (e.g. `com.termux.R`, `com.termux.view.R`, `com.termux.shared.R`). aapt2 link only
generates ONE R (the manifest package's). For each extra module, generate a tiny R.java in
that module's package that just `extends com.termux.R` (or duplicate the static fields),
and compile it into the same javac classpath. Collect with
`grep -rhoE "import [a-z0-9_.]+\.R;" src/ | sort -u` to know exactly which R packages are
referenced.

## 5. minSdk vs API level (desugaring)
No coreLibraryDesugaring in a manual build. If code imports `java.time` / `java.nio.file` /
`java.net.http`, those are API-gated:
- Check whether android.jar at your compileSdk already contains them
  (`unzip -l $PLATFORM/android.jar | grep 'java/nio/file/Files.class'`).
- If used unconditionally below their API level, the original app MUST have desugaring;
  find the call sites (`grep -rn "java.nio.file" src/`) and either guard with
  `Build.VERSION.SDK_INT >= O` or replace with a java.io equivalent.
- 0 `java.time`/`java.nio.file` = nothing to do.

## 6. Signing
Reuse the repo's debug keystore if present (`app/*.jks` + `signingConfigs` passwords in
`app/build.gradle`) — faster than genkeypair and matches upstream expectations.
`keytool -list -keystore app/dev_keystore.jks -storepass <pw>` to confirm 1 entry.

## 7. Verify before declaring done
- `aapt dump badging out.apk | grep -E "package:|launchable"` — package = your RENAMED
  package, launchable activity = the rewritten one.
- `apksigner verify --verbose out.apk` — v2/v3 true.
- On device: install WITHOUT uninstalling the original (proves coexistence), launch, and
  confirm the new feature AND that the original app still works.
