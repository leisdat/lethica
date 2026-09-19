---
name: frida-injector
description: "Inject kode ke app Android via Frida (gadget tanpa root)."
---

# Frida Injector

Dynamic instrumentation untuk app Android — inject JS ke proses app buat intercept function, bypass detection, dump memory. Dua mode: frida-server (root) & frida-gadget (tanpa root).

## Trigger
- "bypass root detection app"
- "bypass SSL pinning"
- "intercept function / method app"
- "dump data dari app"
- "app nolak jalan karena deteksi frida/root/emulator"

## Binary yang Dibutuhkan

Sudah di-download di `~/.hermes/tmp/`:
- `frida-server` — 53MB, butuh ROOT (attach ke proses app)
- `frida-gadget.so` — 25MB, TANPA ROOT (di-embed ke APK)
- Versi: 17.17.0, aarch64, Android 21+

Frida client (`frida-tools`) **tidak bisa di-install via pip di Termux** (gak ada wheel aarch64, build source gagal). Client jalan dari PC: `pip install frida-tools` di komputer, lalu `adb forward` atau konek gadget via TCP.

## Mode 1: Frida Gadget (TANPA ROOT) — untuk device no-root

Gadget di-embed ke APK target, app jalan normal, gadget buka port buat koneksi dari luar.

### Langkah: inject gadget ke APK

```bash
# 1. Decode APK
apktool d app.apk -o app_mod

# 2. Copy gadget ke lib dir yang sesuai
# Cek architecture target: lib/arm64-v8a (64-bit) atau lib/armeabi-v7a (32-bit)
mkdir -p app_mod/lib/arm64-v8a
cp ~/.hermes/tmp/frida-gadget.so app_mod/lib/arm64-v8a/libgadget.so

# 3. Patch smali: panggil System.loadLibrary("gadget") di awal app
# Cari entry point (Application class / MainActivity.onCreate)
# Tambah di onCreate:
#   const-string v0, "gadget"
#   invoke-static {v0}, Ljava/lang/System;->loadLibrary(Ljava/lang/String;)V

# 4. Build ulang + sign
apktool b app_mod -o app_modded.apk
zipalign -f 4 app_modded.apk app_aligned.apk
apksigner sign --ks key.jks app_aligned.apk

# 5. Install & jalankan app — gadget listen di port 27042
```

### Konek dari PC
```bash
# PC: install frida-tools
pip install frida-tools

# Konek ke gadget (default listen 127.0.0.1:27042)
frida-ps -H 127.0.0.1:27042

# Attach
frida -H 127.0.0.1:27042 -f com.example.app -l script.js
```

## Mode 2: Frida Server (BUTUH ROOT)

```bash
# 1. Push server ke device
adb push frida-server /data/local/tmp/
adb shell chmod 755 /data/local/tmp/frida-server

# 2. Jalankan (root)
adb shell su -c /data/local/tmp/frida-server &

# 3. Konek
frida-ps -U          # list proses
frida -U -f com.app -l script.js   # spawn mode
```

## Script JS Umum

### Bypass SSL Pinning (universal)
```javascript
Java.perform(function () {
  // TrustManager bypass
  var TrustAll = Java.registerClass({
    name: 'com.bypass.TrustAll',
    implements: [Java.use('javax.net.ssl.X509TrustManager')],
    methods: {
      checkClientTrusted: function () {},
      checkServerTrusted: function () {},
      getAcceptedIssuers: function () { return []; }
    }
  });
  var SSLContext = Java.use('javax.net.ssl.SSLContext');
  SSLContext.init.overload('[Ljavax.net.ssl.KeyManager;', '[Ljavax.net.ssl.TrustManager;', 'java.security.SecureRandom')
    .implementation = function (km, tm, sr) {
      this.init(km, [TrustAll.$new()], sr);
    };
  console.log('[+] SSL pinning bypassed');
});
```

### Bypass Root Detection (hook checkRoot)
```javascript
Java.perform(function () {
  // Hook method checkRoot — paksa return false
  var target = Java.use('com.example.app.RootChecker');
  target.checkRoot.implementation = function () {
    console.log('[*] checkRoot called → returning false');
    return false;
  };
  
  // Alternatif: hook File.exists untuk /su, /magisk
  var File = Java.use('java.io.File');
  File.exists.implementation = function () {
    var p = this.getAbsolutePath();
    if (/\/su$|magisk|Superuser/.test(p)) return false;
    return this.exists();
  };
});
```

### Bypass Frida Detection
```javascript
// Hook yang deteksi string "frida" di /proc/self/maps
var FileReader = Java.use('java.io.FileReader');
FileReader.read.overload('[C]', 'int', 'int').implementation = function (buf, off, len) {
  // modifikasi buffer — hapus "frida"
  var result = this.read(buf, off, len);
  for (var i = 0; i < len; i++) {
    if (String.fromCharCode(buf[i]).match(/frida|gadget|gum-js/i)) buf[i] = 0;
  }
  return result;
};
```

### Dump String dari Method
```javascript
Java.perform(function () {
  var target = Java.use('com.example.app.SecretClass');
  target.getToken.implementation = function () {
    var result = this.getToken();
    console.log('[+] Token: ' + result);
    return result;
  };
});
```

### Intercept Network Request
```javascript
Java.perform(function () {
  var OkHttp = Java.use('okhttp3.OkHttpClient');
  // intercept URL & body
  var Request = Java.use('okhttp3.Request');
  Request.url.implementation = function () {
    var url = this.url();
    console.log('[+] Request to: ' + url);
    return url;
  };
});
```

## Pitfall

- **`pip install frida` gagal di Termux** — gak ada wheel aarch64 Android, build source butuh compiler Android yang gak bisa. Client HARUS dari PC.
- **frida-server butuh root** — di device no-root, jalankan via gadget mode.
- **Gadget default listen 127.0.0.1:27042** — untuk akses dari PC perlu `adb forward tcp:27042 tcp:27042`.
- **App dengan anti-tamper** (cek signature sendiri) → modif APK langsung ketauan. Bypass: patch signature check juga (lihat skill android-detection-bypass).
- **Gadget di-app yang dianalisa** — beberapa app deteksi library aneh di lib/ dir. Rename `libgadget.so` ke nama mirip library asli app.
- **Architecture mismatch** — device arm64 (aarch64) pakai `lib/arm64-v8a/`. Kalau app cuma punya 32-bit, pakai gadget armeabi-v7a.

## Batas

Frida buat testing app sendiri / riset = fine. Bypass DRM/license buat redistribute app berbayar = gak dibantu.

## File

- `~/.hermes/tmp/frida-server` (53MB, root mode)
- `~/.hermes/tmp/frida-gadget.so` (25MB, no-root mode)
- Download: `https://github.com/frida/frida/releases/download/17.17.0/frida-server-17.17.0-android-arm64.xz` (ganti nama file sesuai mode)
