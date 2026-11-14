#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# -*- coding: utf-8 -*-
"""
fdtpatch.py - edit a property value inside a compiled FDT blob in place.

Only supports same-length replacement of an existing property, which is
enough for things like filling in the memory size.
"""
import struct
import sys

FDT_BEGIN_NODE = 1
FDT_END_NODE = 2
FDT_PROP = 3
FDT_NOP = 4
FDT_END = 9


def be32(b, o):
    return struct.unpack_from(">I", b, o)[0]


def align4(x):
    return (x + 3) & ~3


def patch(blob, path, prop, newval):
    """Replace property `prop` of node `path` with `newval` (same length)."""
    off_struct = be32(blob, 8)
    off_strings = be32(blob, 12)
    size_struct = be32(blob, 36)
    size_strings = be32(blob, 32)
    strings = blob[off_strings:off_strings + size_strings]

    buf = bytearray(blob)
    pos = off_struct
    end = off_struct + size_struct
    stack = []
    while pos < end:
        tok = be32(buf, pos)
        pos += 4
        if tok == FDT_BEGIN_NODE:
            nul = buf.index(0, pos)
            name = bytes(buf[pos:nul]).decode("utf-8", "replace")
            pos = align4(nul + 1)
            stack.append(name)
        elif tok == FDT_END_NODE:
            if stack:
                stack.pop()
        elif tok == FDT_PROP:
            ln = be32(buf, pos)
            nameoff = be32(buf, pos + 4)
            pos += 8
            nul = strings.index(0, nameoff)
            pname = bytes(strings[nameoff:nul]).decode("ascii", "replace")
            cur = "/" + "/".join(n for n in stack if n)
            if cur == path and pname == prop:
                if len(newval) != ln:
                    raise SystemExit("length mismatch: existing %d, new %d" % (ln, len(newval)))
                buf[pos:pos + ln] = newval
                return bytes(buf), True
            pos = align4(pos + ln)
        elif tok == FDT_NOP:
            continue
        elif tok == FDT_END:
            break
    return bytes(buf), False


if __name__ == "__main__":
    src, dst, path, prop, valhex = sys.argv[1:6]
    blob = open(src, "rb").read()
    new = bytes.fromhex(valhex)
    out, ok = patch(blob, path, prop, new)
    if not ok:
        raise SystemExit("property not found: %s %s" % (path, prop))
    open(dst, "wb").write(out)
    print("patched %s %s -> %s (%d bytes)" % (path, prop, valhex, len(new)))
