#!/usr/bin/env python3
"""Audit final .config against (stock IKCONFIG + QCOM fragment) expectation.

Expectation is built with the same strict fragment rules as merge_config.py:
  stock base, then fragment overrides (including '# CONFIG_X is not set').

Failure policy (real regressions only):
  - want y/m and final is n          -> FAIL (explicitly disabled)
  - want y/m and final is other y/m  -> FAIL (tristate mismatch)
  - want y/m and final is None:
      * symbol came from fragment    -> FAIL (requested feature vanished)
      * symbol only from stock       -> WARN (OEM IKCONFIG ghost / absent
        Kconfig in public tree; V2 already drops these, e.g. F2FS_APPBOOST)
  - host/toolchain noise whitelisted (CC_CAN_LINK*, PAHOLE_VERSION, ...)
  - KSU* and TRIM_UNUSED_KSYMS family whitelisted (intentional deltas)

Dep-resolution n->m/y (fragment pulls in select/depends) is printed as DIFF
but does not fail.
"""
from __future__ import annotations

import re
import sys

STOCK = sys.argv[1]
FRAG = sys.argv[2]
FINAL = sys.argv[3]

WHITELIST_PREFIXES = ("CONFIG_KSU",)
WHITELIST_EXACT = {
    "CONFIG_TRIM_UNUSED_KSYMS",
    "CONFIG_UNUSED_KSYMS_WHITELIST",
    # Host/toolchain probe symbols — not ABI, vary by runner.
    "CONFIG_CC_CAN_LINK",
    "CONFIG_CC_CAN_LINK_STATIC",
    "CONFIG_ARCH_SUPPORTS_PGO_CLANG",
    "CONFIG_PAHOLE_VERSION",
    "CONFIG_UAPI_HEADER_TEST",
    "CONFIG_GCC_VERSION",
    "CONFIG_CLANG_VERSION",
    "CONFIG_AS_VERSION",
    "CONFIG_LD_VERSION",
    "CONFIG_LLD_VERSION",
    "CONFIG_CC_VERSION_TEXT",
    "CONFIG_TOOL_BINUTILS_VERSION",
}

RE_ASSIGN = re.compile(r"^(CONFIG_[A-Za-z0-9_]+)=(.*)$")
RE_UNSET = re.compile(r"^# (CONFIG_[A-Za-z0-9_]+) is not set$")
RE_IF = re.compile(r"^\s*#\s*if(n?def)?\b")
RE_ENDIF = re.compile(r"^\s*#\s*endif\b")
RE_ELSE = re.compile(r"^\s*#\s*else\b")


def normalize_line(line: str) -> str | None:
    line = line.rstrip("\r\n").strip()
    if not line:
        return None
    if RE_IF.match(line) or RE_ENDIF.match(line) or RE_ELSE.match(line):
        return None
    m = RE_ASSIGN.match(line)
    if m:
        sym, val = m.group(1), m.group(2)
        if val == "n":
            return "# %s is not set" % sym
        return "%s=%s" % (sym, val)
    m = RE_UNSET.match(line)
    if m:
        return "# %s is not set" % m.group(1)
    return None


def parse_map(path: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in open(path, encoding="utf-8", errors="replace"):
        norm = normalize_line(raw)
        if norm is None:
            # Final .config from olddefconfig is already strict; also accept
            # raw assigns that normalize_line got (always). For completeness
            # parse classic forms directly when normalize returns None only
            # for comments — already handled.
            continue
        m = RE_ASSIGN.match(norm)
        if m:
            out[m.group(1)] = m.group(2)
            continue
        m = RE_UNSET.match(norm)
        if m:
            out[m.group(1)] = "n"
    return out


def parse_final(path: str) -> dict[str, str]:
    """Parse a kernel .config (post-olddefconfig)."""
    out: dict[str, str] = {}
    for raw in open(path, encoding="utf-8", errors="replace"):
        line = raw.rstrip("\r\n")
        m = RE_ASSIGN.match(line)
        if m:
            out[m.group(1)] = m.group(2)
            continue
        m = RE_UNSET.match(line)
        if m:
            out[m.group(1)] = "n"
    return out


def is_whitelisted(sym: str) -> bool:
    if sym in WHITELIST_EXACT:
        return True
    if sym.startswith(WHITELIST_PREFIXES):
        return True
    if sym.startswith("CONFIG_UNUSED_KSYMS_WHITELIST"):
        return True
    return False


def main() -> None:
    stock = parse_map(STOCK)
    frag = parse_map(FRAG)
    # Expectation = stock then fragment overrides (including explicit n).
    expect = dict(stock)
    expect.update(frag)
    frag_syms = set(frag)
    final = parse_final(FINAL)

    issues = 0
    warns = 0
    diffs = 0
    for sym in sorted(expect):
        if is_whitelisted(sym):
            continue
        want = expect[sym]
        got = final.get(sym)
        if got == want:
            continue
        diffs += 1
        tag = "DIFF"
        # Only y/m expectations can be hard failures.
        if want in ("y", "m"):
            if got is None:
                if sym in frag_syms:
                    tag = "FAIL"
                    issues += 1
                else:
                    tag = "WARN"
                    warns += 1
            elif got == "n" or got in ("y", "m"):
                tag = "FAIL"
                issues += 1
            else:
                # string/int value mismatch
                tag = "FAIL"
                issues += 1
        # n->y/m or value noise: informational DIFF only
        print("%-4s %-55s expect=%s final=%s" % (tag, sym, want, got))

    print(
        "symbols: expect=%d final=%d diffs=%d warns=%d issues=%d"
        % (len(expect), len(final), diffs, warns, issues)
    )
    sys.exit(1 if issues else 0)


if __name__ == "__main__":
    main()
