#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# -*- coding: utf-8 -*-
"""
dtb_dump.py - extract Qualcomm QCDT container entries from a boot image and
convert each FDT blob into readable DTS-like text. Pure python, no dtc needed.
"""
import os
import struct
import sys

FDT_MAGIC = 0xD00DFEED
FDT_BEGIN_NODE = 1
FDT_END_NODE = 2
FDT_PROP = 3
FDT_NOP = 4
FDT_END = 9


def align(x, a):
    return (x + a - 1) // a * a


def u32(b, o):
    return struct.unpack_from(">I", b, o)[0]


def parse_fdt(b, base=0):
    """Return (root_node, strings_block)."""
    if u32(b, base) != FDT_MAGIC:
        raise ValueError("bad fdt magic at %d" % base)
    totalsize = u32(b, base + 4)
    off_struct = u32(b, base + 8)
    off_strings = u32(b, base + 12)
    size_strings = u32(b, base + 32)
    size_struct = u32(b, base + 36)
    strings = b[base + off_strings: base + off_strings + size_strings]
    st = b[base + off_struct: base + off_struct + size_struct]

    pos = 0
    root = {"name": "/", "props": [], "children": []}
    stack = [root]
    while pos < len(st):
        tok = u32(st, pos)
        pos += 4
        if tok == FDT_BEGIN_NODE:
            end = st.index(b"\x00", pos)
            name = st[pos:end].decode("utf-8", "replace")
            pos = align(end + 1, 4)
            node = {"name": name, "props": [], "children": []}
            stack[-1]["children"].append(node)
            stack.append(node)
        elif tok == FDT_END_NODE:
            if len(stack) > 1:
                stack.pop()
        elif tok == FDT_PROP:
            ln = u32(st, pos)
            nameoff = u32(st, pos + 4)
            pos += 8
            val = st[pos:pos + ln]
            pos = align(pos + ln, 4)
            end = strings.index(b"\x00", nameoff)
            pname = strings[nameoff:end].decode("utf-8", "replace")
            stack[-1]["props"].append((pname, val))
        elif tok == FDT_NOP:
            continue
        elif tok == FDT_END:
            break
        else:
            break
    return root


def fmt_val(v):
    if not v:
        return "(empty)"
    if len(v) % 4 == 0 and len(v) <= 64:
        nums = struct.unpack(">%dI" % (len(v) // 4), v)
        if all(32 <= c < 127 for c in v) and b"\x00" not in v[:-1]:
            pass
        else:
            # hex words plus printable rendering
            hx = " ".join("%#x" % n for n in nums)
            return "<%s>" % hx
    # printable?
    if all(32 <= c < 127 or c == 0 for c in v):
        s = v.rstrip(b"\x00").decode("ascii", "replace")
        return '"%s"' % s
    if len(v) <= 80:
        return "[%s]" % " ".join("%02x" % c for c in v)
    return "[%d bytes]" % len(v)


def emit(node, out, depth=0):
    ind = "\t" * depth
    if depth == 0:
        out.append("/dts-v1/;")
        out.append("")
        out.append("/ {")
    else:
        out.append('%s%s {' % (ind, node["name"]))
    for name, val in node["props"]:
        out.append("%s\t%-24s = %s;" % (ind, name, fmt_val(val)))
    for ch in node["children"]:
        emit(ch, out, depth + 1)
    if depth == 0:
        out.append("};")
    else:
        out.append("%s};" % ind)


def walk(node, path=""):
    yield path or "/", node
    for ch in node["children"]:
        p = path + "/" + ch["name"]
        yield from walk(ch, p)


def main():
    src = sys.argv[1]
    outdir = sys.argv[2]
    os.makedirs(outdir, exist_ok=True)

    if src.lower().endswith(".img") and open(src, "rb").read(8) == b"ANDROID!":
        d = open(src, "rb").read()
        ks, _, rs, _, ss, _, _, page = struct.unpack_from("<IIIIIIII", d, 8)
        dt_off = align(align(align(page + ks, page) + rs, page) + ss, page)
        blob = d[dt_off:]
        print("boot image: dtb area @%d, %d bytes" % (dt_off, len(blob)))
    else:
        blob = open(src, "rb").read()
        print("raw dtb file: %d bytes" % len(blob))

    if blob[:4] != b"QCDT":
        raise SystemExit("not a QCDT container: %r" % blob[:8])

    # The QCDT header layout varies between Qualcomm releases, so locate the
    # FDT blobs by their magic instead of trusting the entry table.
    magic_be = b"\xd0\x0d\xfe\xed"
    offs, pos = [], 0
    while True:
        i = blob.find(magic_be, pos)
        if i < 0:
            break
        offs.append(i)
        pos = i + 4
    print("QCDT container: %d bytes, %d FDT blob(s) found" % (len(blob), len(offs)))
    print()

    for i, off in enumerate(offs):
        try:
            root = parse_fdt(blob, off)
        except Exception as e:
            print("[%d] @%-9d parse failed: %s" % (i, off, e))
            continue
        out = []
        emit(root, out)
        txt = "\n".join(out)
        fn = os.path.join(outdir, "dtb_%02d.dts" % i)
        open(fn, "w", encoding="utf-8").write(txt)
        props = {}
        for p, n in walk(root):
            for nm, val in n["props"]:
                if nm in ("model", "compatible", "qcom,board-id", "qcom,msm-id"):
                    props.setdefault(nm, []).append(val.rstrip(b"\x00").decode("utf-8", "replace"))
        nodes = sum(1 for _ in walk(root))
        print("[%d] @%-9d %3d nodes  -> %s" % (i, off, nodes, os.path.basename(fn)))
        for k, v in props.items():
            print("      %-14s %s" % (k, " | ".join(dict.fromkeys(v))[:160]))


if __name__ == "__main__":
    main()
