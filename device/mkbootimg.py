#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mkbootimg.py - minimal Android boot image (v0) packer, dependency free.

Layout:  header | kernel | ramdisk | second | dtb, each page aligned.
Addresses default to the MSM8916 values used by msm8916-mainline
(base 0x80000000, kernel +0x8000, ramdisk +0x02000000, tags +0x100).

Usage:
  mkbootimg.py --kernel Image.gz --ramdisk initramfs.cpio.gz \
               --dtb msm8916-readboy-g35s.dtb --out boot.img
"""
import argparse
import os
import struct

PAGE = 2048
BASE = 0x80000000
KERNEL_OFFSET = 0x00008000
RAMDISK_OFFSET = 0x02000000
TAGS_OFFSET = 0x00000100


def pad(b, page=PAGE):
    rem = len(b) % page
    return b + b"\x00" * (page - rem) if rem else b


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kernel", required=True)
    ap.add_argument("--ramdisk", default="")
    ap.add_argument("--dtb", default="")
    ap.add_argument("--second", default="")
    ap.add_argument("--out", required=True)
    ap.add_argument("--cmdline", default="")
    ap.add_argument("--name", default="")
    ap.add_argument("--page-size", type=int, default=PAGE)
    args = ap.parse_args()

    kern = open(args.kernel, "rb").read()
    rdisk = open(args.ramdisk, "rb").read() if args.ramdisk else b""
    dtb = open(args.dtb, "rb").read() if args.dtb else b""
    second = open(args.second, "rb").read() if args.second else b""

    if dtb and dtb[:4] not in (b"\xd0\x0d\xfe\xed",):
        raise SystemExit("dtb does not start with FDT magic: %r" % dtb[:4])

    name = args.name.encode()[:15].ljust(16, b"\x00")
    cmdline = args.cmdline.encode()[:511].ljust(512, b"\x00")

    hdr = bytearray(0)
    hdr += b"ANDROID!"
    hdr += struct.pack("<I", len(kern))
    hdr += struct.pack("<I", BASE + KERNEL_OFFSET)
    hdr += struct.pack("<I", len(rdisk))
    hdr += struct.pack("<I", BASE + RAMDISK_OFFSET)
    hdr += struct.pack("<I", len(second))
    hdr += struct.pack("<I", BASE + RAMDISK_OFFSET + len(rdisk))
    hdr += struct.pack("<I", BASE + TAGS_OFFSET)
    hdr += struct.pack("<I", args.page_size)
    hdr += struct.pack("<I", len(dtb))      # dt_size
    hdr += struct.pack("<I", 0)              # unused
    hdr += name                              # 16
    hdr += cmdline                           # 512
    hdr += b"\x00" * (8 * 4)                 # id[8]
    hdr += b"\x00" * 1024                    # extra_cmdline
    hdr = bytes(hdr)
    if len(hdr) > args.page_size:
        raise SystemExit("header larger than page size")
    hdr = hdr.ljust(args.page_size, b"\x00")

    img = hdr + pad(kern, args.page_size) + pad(rdisk, args.page_size) \
        + pad(second, args.page_size) + pad(dtb, args.page_size)

    with open(args.out, "wb") as f:
        f.write(img)

    print("boot image : %s" % args.out)
    print("  size     : %d bytes (%.1f KiB)" % (len(img), len(img) / 1024))
    print("  kernel   : %d @0x%08X" % (len(kern), BASE + KERNEL_OFFSET))
    print("  ramdisk  : %d @0x%08X" % (len(rdisk), BASE + RAMDISK_OFFSET))
    print("  dtb      : %d" % len(dtb))
    print("  page     : %d" % args.page_size)


if __name__ == "__main__":
    main()
