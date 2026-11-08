#!/usr/bin/env python3
"""Inspect a YARP/TWRP ramdisk-only boot image (Android header v3/v4).

Read-only: never modifies the source image. Extracts only small text config
files into the output directory; binaries are recorded by path and size only.

Usage:
    python3 scripts/inspect-yarp-image.py <recovery.img> <output-dir>

Requires: pip install lz4
"""
import argparse
import json
import os
import struct
import sys

try:
    import lz4.block
except ImportError:
    sys.exit("missing dependency: pip install lz4")

LZ4_LEGACY_MAGIC = b"\x02\x21\x4c\x18"
PAGE = 4096

TEXT_HINTS = (
    "recovery.fstab", "fstab.qcom", "init.recovery", "init.qcom",
    "default.prop", "prop.default", "build.prop", "system.prop",
    "vintf/manifest", "twrp-pre-decrypt", "twrp-decrypt-retry",
    "twrp-reboot-cleanup", "ueventd", "modules.dep", "modules.load",
    ".rc", ".sh", ".xml", ".json", ".prop",
)
MAX_TEXT = 2 * 1024 * 1024


def align4(n):
    return (n + 3) & ~3


def parse_header(blob):
    if blob[:8] != b"ANDROID!":
        raise ValueError("not an Android boot image")
    kernel_size, ramdisk_size = struct.unpack_from("<II", blob, 8)
    os_version, header_size = struct.unpack_from("<II", blob, 16)
    header_version = struct.unpack_from("<I", blob, 40)[0]
    cmdline = blob[48:48 + 1536].split(b"\0")[0].decode("utf-8", "replace")
    return {
        "kernel_size": kernel_size,
        "ramdisk_size": ramdisk_size,
        "os_version": hex(os_version),
        "header_size": header_size,
        "header_version": header_version,
        "cmdline": cmdline,
        "ramdisk_offset": ((header_size + PAGE - 1) & ~(PAGE - 1))
                          + ((kernel_size + PAGE - 1) & ~(PAGE - 1)),
    }


def decompress_lz4_legacy(data):
    if data[:4] != LZ4_LEGACY_MAGIC:
        raise ValueError("ramdisk is not lz4_legacy (magic %s)" % data[:4].hex())
    pos, out, blocks = 4, bytearray(), 0
    while pos + 4 <= len(data):
        n = struct.unpack_from("<I", data, pos)[0]
        pos += 4
        if n == 0 or n > len(data) - pos:
            break
        block = bytes(data[pos:pos + n])
        pos += n
        try:
            out += lz4.block.decompress(block, uncompressed_size=16 * 1024 * 1024)
        except Exception:
            out += block  # trailing uncompressed block
        blocks += 1
    return bytes(out), blocks


def parse_cpio(buf):
    pos, entries = 0, []
    while pos + 110 <= len(buf):
        if buf[pos:pos + 6] not in (b"070701", b"070702"):
            break
        head = buf[pos:pos + 110]
        try:
            fields = [int(head[6 + i * 8:14 + i * 8], 16) for i in range(13)]
        except ValueError:
            break
        filesize, namesize = fields[6], fields[11]
        name = buf[pos + 110:pos + 110 + namesize].rstrip(b"\0").decode("utf-8", "replace")
        data_start = pos + align4(110 + namesize)
        data = buf[data_start:data_start + filesize]
        pos = data_start + align4(filesize)
        if name == "TRAILER!!!":
            break
        entries.append({"path": name, "mode": fields[1], "size": filesize, "data": data})
    return entries, pos


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("outdir")
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    configs = os.path.join(args.outdir, "configs")
    os.makedirs(configs, exist_ok=True)

    with open(args.image, "rb") as fh:
        head_blob = fh.read(8192)
        hdr = parse_header(head_blob)
        fh.seek(hdr["ramdisk_offset"])
        ramdisk = fh.read(hdr["ramdisk_size"])

    cpio, blocks = decompress_lz4_legacy(ramdisk)
    entries, consumed = parse_cpio(cpio)

    with open(os.path.join(args.outdir, "filelist.txt"), "w", encoding="utf-8") as fh:
        for e in entries:
            fh.write("%-10s %10d  %s\n" % (oct(e["mode"]), e["size"], e["path"]))

    dirs = {}
    saved = []
    for idx, e in enumerate(entries):
        top = e["path"].strip("/").split("/")[0] or "/"
        slot = dirs.setdefault(top, [0, 0])
        slot[0] += 1
        slot[1] += e["size"]
        p = e["path"].lower()
        if e["size"] < MAX_TEXT and any(k in p for k in TEXT_HINTS):
            rel = e["path"].lstrip("/").replace("..", "__")
            dst = os.path.join(configs, rel)
            try:
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                with open(dst, "wb") as out:
                    out.write(e["data"])
            except OSError:
                # cpio may contain both a file and a directory at the same
                # path (or a path too long for Windows); fall back to a flat name.
                flat = "%05d__%s" % (idx, os.path.basename(e["path"]))
                dst = os.path.join(configs, flat)
                with open(dst, "wb") as out:
                    out.write(e["data"])
            saved.append((e["path"], os.path.relpath(dst, args.outdir)))

    summary = {
        "image": os.path.basename(args.image),
        "image_size": os.path.getsize(args.image),
        "header": hdr,
        "lz4_blocks": blocks,
        "cpio_uncompressed_size": len(cpio),
        "cpio_consumed": consumed,
        "entries": len(entries),
        "top_level": {k: {"files": v[0], "bytes": v[1]} for k, v in sorted(dirs.items())},
        "saved_configs": len(saved),
    }
    with open(os.path.join(args.outdir, "report.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, ensure_ascii=False)

    with open(os.path.join(args.outdir, "report.txt"), "w", encoding="utf-8") as fh:
        fh.write("YARP image inspection\n=====================\n")
        for k in ("image", "image_size", "image"):
            if k in summary:
                fh.write("%-24s %s\n" % (k, summary[k]))
        fh.write("\nheader\n------\n")
        for k, v in hdr.items():
            fh.write("%-24s %s\n" % (k, v))
        fh.write("\nramdisk\n-------\n")
        fh.write("%-24s %s\n" % ("lz4_blocks", blocks))
        fh.write("%-24s %s\n" % ("cpio_uncompressed", len(cpio)))
        fh.write("%-24s %s\n" % ("cpio_consumed", consumed))
        fh.write("%-24s %s\n" % ("entries", len(entries)))
        fh.write("\ntop-level\n---------\n")
        for k, v in sorted(dirs.items()):
            fh.write("%-24s %5d files  %10d bytes\n" % (k, v[0], v[1]))
        fh.write("\nsaved text configs: %d\n" % len(saved))
        for orig, rel in saved[:80]:
            fh.write("  %s -> %s\n" % (orig, rel))

    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
