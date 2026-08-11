#!/usr/bin/env python3
"""Merge stock OEM IKCONFIG with the QCOM kalama_GKI.config fragment.

Fragment semantics (OnePlus/QCOM defconfig fragment style):
  - '#ifdef OPLUS_*' / '#ifdef CONFIG_*' blocks are kept (device macros true).
  - '#endif' / bare '#else' lines are dropped.
  - Only strict Kconfig lines are applied:
      CONFIG_FOO=value
      # CONFIG_FOO is not set
  - Comment-lookalikes are ignored (do NOT treat as overrides):
      # CONFIG_FOO=m          (commented-out assignment)
      #CONFIG_FOO=m           (no space after '#')
  - Bare 'CONFIG_FOO=n' is normalized to '# CONFIG_FOO is not set'.

Every strict CONFIG line in the fragment overrides the same symbol in the
stock base; symbols absent from the stock base are appended. Output is LF.
"""
from __future__ import annotations

import re
import sys

RE_ASSIGN = re.compile(r"^(CONFIG_[A-Za-z0-9_]+)=(.*)$")
RE_UNSET = re.compile(r"^# (CONFIG_[A-Za-z0-9_]+) is not set$")
RE_IF = re.compile(r"^\s*#\s*if(n?def)?\b")
RE_ENDIF = re.compile(r"^\s*#\s*endif\b")
RE_ELSE = re.compile(r"^\s*#\s*else\b")


def normalize_line(line: str) -> str | None:
    """Return a strict Kconfig line, or None if the input is not one."""
    line = line.rstrip("\r\n").strip()
    if not line:
        return None
    # Preprocessor / block markers: drop (body kept by caller skipping these).
    if RE_IF.match(line) or RE_ENDIF.match(line) or RE_ELSE.match(line):
        return None
    m = RE_ASSIGN.match(line)
    if m:
        sym, val = m.group(1), m.group(2)
        # Fragment occasionally uses '=n' instead of '# CONFIG is not set'.
        if val == "n":
            return "# %s is not set" % sym
        return "%s=%s" % (sym, val)
    m = RE_UNSET.match(line)
    if m:
        return "# %s is not set" % m.group(1)
    # Anything else with CONFIG_ is a comment or garbage - ignore.
    return None


def symbol_of(line: str) -> str:
    m = RE_ASSIGN.match(line)
    if m:
        return m.group(1)
    m = RE_UNSET.match(line)
    if m:
        return m.group(1)
    raise ValueError("not a strict kconfig line: %r" % line)


def parse(path: str) -> tuple[list[str], int]:
    entries: list[str] = []
    skipped = 0
    for raw in open(path, encoding="utf-8", errors="replace"):
        norm = normalize_line(raw)
        if norm is None:
            # Count only non-empty non-preprocessor skips that look config-ish.
            s = raw.strip()
            if s and "CONFIG_" in s and not (
                RE_IF.match(s) or RE_ENDIF.match(s) or RE_ELSE.match(s)
            ):
                skipped += 1
            continue
        entries.append(norm)
    return entries, skipped


def main() -> None:
    stock_path, frag_path, out_path = sys.argv[1:4]
    base, base_skip = parse(stock_path)
    frag, frag_skip = parse(frag_path)
    order: list[str] = []
    override: dict[str, str] = {}
    for line in frag:
        sym = symbol_of(line)
        if sym not in override:
            order.append(sym)
        override[sym] = line
    emitted: set[str] = set()
    out: list[str] = []
    for line in base:
        sym = symbol_of(line)
        emitted.add(sym)
        out.append(override.get(sym, line))
    for sym in order:
        if sym not in emitted:
            out.append(override[sym])
    with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(out) + "\n")
    print(
        "merge: base=%d frag=%d overridden=%d appended=%d "
        "skipped_nonstrict_base=%d skipped_nonstrict_frag=%d"
        % (
            len(base),
            len(frag),
            len(set(order) & emitted),
            len(set(order) - emitted),
            base_skip,
            frag_skip,
        )
    )


if __name__ == "__main__":
    main()
