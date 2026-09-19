#!/data/data/com.termux/files/usr/bin/python3
"""zipalign replacement for Termux (no native zipalign binary exists on aarch64).

4-byte aligns uncompressed ZIP entries by padding the local-header extra field,
mirroring AOSP zipalign. CRITICAL: the central-directory record's local-header
offset must be the RUNNING offset at the start of the entry (not entry-0 based),
and each CD record = 46-byte fixed part + filename + extra (aapt2/apksigner
reject a CD record that omits the filename). DEFLATED entries are re-compressed.
Usage: python3 zipalign.py <in.apk> <out.apk> [align=4]
"""
import sys, struct, zlib, zipfile

CD_FMT = '<IHHHHHHIIIHHHHHII'   # 46 bytes
LF_FMT = '<IHHHHHIIIHH'          # 30 bytes
assert struct.calcsize(CD_FMT) == 46 and struct.calcsize(LF_FMT) == 30

def zipalign(input_apk, output_apk, alignment=4):
    zin = zipfile.ZipFile(input_apk, 'r')
    out = open(output_apk, 'wb')
    central = []
    offset = 0
    for info in zin.infolist():
        data = zin.read(info.filename)
        name = info.filename.encode('utf-8')
        crc = zlib.crc32(data) & 0xffffffff
        if info.compress_type == zipfile.ZIP_STORED:
            method = 0
            cdata = data
        else:
            method = 8
            co = zlib.compressobj(zlib.Z_DEFAULT_COMPRESSION, zlib.DEFLATED, -15)
            cdata = co.compress(data) + co.flush()
        csize, usize = len(cdata), len(data)
        pad = ((-offset - 30 - len(name)) % alignment) if method == 0 else 0
        extra = b'\x00' * pad
        data_offset = offset + 30 + len(name) + len(extra)
        out.write(struct.pack(LF_FMT, 0x04034b50, 20, 0, method, 0, 0x21,
                              crc, csize, usize, len(name), len(extra)))
        out.write(name); out.write(extra); out.write(cdata)
        cdrec = struct.pack(CD_FMT, 0x02014b50, 20, 20, 0, method,
                            0, 0x21, crc, csize, usize, len(name), len(extra),
                            0, 0, 0, info.external_attr, offset)
        central.append(cdrec + name + extra)
        offset = data_offset + csize
    cd_offset = offset
    cb = b''.join(central)
    out.write(cb)
    n = len(central)
    out.write(struct.pack('<IHHHHIIH', 0x06054b50, 0, 0, n, n, len(cb), cd_offset, 0))
    out.close()

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: zipalign.py <input.apk> <output.apk> [alignment=4]")
        sys.exit(1)
    align = int(sys.argv[3]) if len(sys.argv) > 3 else 4
    zipalign(sys.argv[1], sys.argv[2], align)
    print(f"Aligned {sys.argv[1]} -> {sys.argv[2]} (align={align})")
