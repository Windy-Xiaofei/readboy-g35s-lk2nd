#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
"""Give a DTB some breathing room.

dtc emits blobs whose `totalsize` equals the file size, i.e. with zero slack.
libfdt's fdt_add_subnode()/fdt_setprop() need slack at the end of the blob, so
on such a blob every lk2nd DTB update silently fails (e.g. the ramoops node
never gets injected).

Growing `totalsize` and appending zeros is safe: libfdt shifts everything after
an insertion point and patches off_dt_strings itself. Since dtc lays out
header | mem-rsvmap | struct | strings, the appended tail becomes usable space
for both the struct block and the strings block.
"""
import struct
import sys

FDT_MAGIC = 0xD00DFEED


def pad(dtb: bytes, extra: int) -> bytes:
    magic, totalsize = struct.unpack_from(">II", dtb, 0)
    if magic != FDT_MAGIC:
        raise SystemExit("not a DTB: magic=%08x" % magic)
    if len(dtb) != totalsize:
        raise SystemExit("file size %d != header totalsize %d" % (len(dtb), totalsize))
    out = bytearray(dtb)
    out += b"\x00" * extra
    struct.pack_into(">I", out, 4, totalsize + extra)
    return bytes(out)


def main():
    if len(sys.argv) < 3:
        raise SystemExit("usage: fdtpad.py <in.dtb> <out.dtb> [extra_bytes]")
    extra = int(sys.argv[3]) if len(sys.argv) > 3 else 32768
    data = open(sys.argv[1], "rb").read()
    out = pad(data, extra)
    open(sys.argv[2], "wb").write(out)
    print("padded %d -> %d bytes (+%d)" % (len(data), len(out), extra))


if __name__ == "__main__":
    main()
