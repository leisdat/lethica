# APKTOOL SETUP IN TERMUX

## Problem: `apktool: can't find apktool.jar`

This error occurs when Termux's apktool installation cannot locate its required JAR file. The apktool script searches for `apktool.jar` in specific locations but Termux installs it in a non-standard path.

## Root Cause

The apktool wrapper script (`/data/data/com.termux/files/usr/bin/apktool`) uses this logic to find its JAR:

```bash
jarfile=apktool.jar
libdir="$progdir"
if [ ! -r "$libdir/$jarfile" ]; then
    # Find highest version of apktool_*.jar in the directory
    highest_jarfile=$(ls "$libdir"/apktool_*.jar 2>/dev/null | sort -V | tail -n 1)
    if [ -n "$highest_jarfile" ]; then
        jarfile=$(basename "$highest_jarfile")
    else
        echo `basename "$prog"`": can't find $jarfile"
        exit 1
    fi
fi
```

Termux installs the actual JAR at `/data/data/com.termux/files/usr/share/java/apktool.jar`, but the script looks in `/usr/bin/`.

## Solution

Create a symbolic link from the actual JAR location to where apktool expects it:

```bash
ln -s /data/data/com.termux/files/usr/share/java/apktool.jar /data/data/com.termux/files/usr/bin/apktool.jar
```

## Verification

After creating the link, verify with:

```bash
apktool --version
```

Expected output: `3.0.3` (or current version)

## Why This Works

The symbolic link makes the JAR appear in the expected location without duplicating the file. This approach:
- Preserves the original installation
- Requires no modification to apktool's script
- Survives Termux package updates as long as the JAR location remains consistent

## Alternative Approaches (Less Recommended)

1. **Modify .bashrc**: Adding `export APKTOOL_JAR="$PREFIX/share/java/apktool.jar"` helps but doesn't fix the underlying script issue
2. **Edit apktool script**: Directly modifying the wrapper script is fragile and will be overwritten on updates

## Troubleshooting

If the link already exists but apktool still fails:
- Check link validity: `ls -la /data/data/com.termux/files/usr/bin/apktool.jar`
- Verify JAR exists: `ls -l /data/data/com.termux/files/usr/share/java/apktool.jar`
- Confirm Termux has proper permissions: `termux-setup-storage` (if needed)

## Related Skills

- [JAR/APK inspection techniques](../SKILL.md#jar-apk-inspection)
- [Android APK install debugging](references/android-apk-install-debug.md)