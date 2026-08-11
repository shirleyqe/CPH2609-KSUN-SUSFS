#!/usr/bin/env python3
"""Merge stock OEM IKCONFIG with the QCOM kalama_GKI.config fragment.

Fragment semantics: '#ifdef OPLUS_*' blocks are kept (all OnePlus feature
macros are assumed true for this device), '#endif' lines dropped.  Every
CONFIG_ line in the fragment overrides the same symbol in the stock base;
symbols absent from the stock base are appended.  Output is LF.
"""
import re
import sys


def parse(path):
    entries = []
    for line in open(path, encoding="utf-8", errors="replace"):
        line = line.rstrip("\r\n")
        if not line or re.match(r"^\s*#(if|endif|else)", line):
            continue
        if line.startswith("CONFIG_") or line.startswith("# CONFIG_"):
            entries.append(line)
    return entries


def main():
    stock_path, frag_path, out_path = sys.argv[1:4]
    base = parse(stock_path)
    frag = parse(frag_path)
    order = []
    override = {}
    for line in frag:
        sym = re.match(r"^(?:# )?(CONFIG_[A-Za-z0-9_]+)", line).group(1)
        order.append(sym)
        override[sym] = line
    emitted = set()
    out = []
    for line in base:
        sym = re.match(r"^(?:# )?(CONFIG_[A-Za-z0-9_]+)", line).group(1)
        emitted.add(sym)
        out.append(override.get(sym, line))
    for sym in order:
        if sym not in emitted:
            out.append(override[sym])
    with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(out) + "\n")
    print("merge: base=%d frag=%d overridden=%d appended=%d"
          % (len(base), len(frag), len(set(order) & emitted),
             len(set(order) - emitted)))


if __name__ == "__main__":
    main()
