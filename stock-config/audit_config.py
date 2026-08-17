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

V4-A experiment: --allow CONFIG_<sym> adds an exact-symbol whitelist entry.
The workflow passes exactly the four QTI panic-on switches that the fragment
sets =y and V4-A deliberately disables as its single experiment variable
(QCOM_PANIC_ON_NOTIF_TIMEOUT, QCOM_PANIC_ON_PDR_NOTIF_TIMEOUT,
QCOM_FORCE_WDOG_BITE_ON_PANIC, EDAC_QCOM_LLCC_PANIC_ON_UE). The whitelist is
scoped per invocation (no global broadening); any other deviation from
stock+fragment still fails.

Final-only detection (--allow-new FILE): symbols present in the final config
as y/m (or asserted exact value) that are entirely absent from stock+fragment
are normally unexpected drift; with --allow-new, every such symbol must be
listed (CONFIG_X=value asserts the exact final value, CONFIG_X allows any
y/m) and is then printed as NEW (informational). Without --allow-new the
final-only y/m symbols are WARNed only (backward compatible), but the
810-CONTROL workflow passes the allowlist so regressions are hard failures.

Dep-resolution n->m/y (fragment pulls in select/depends) is printed as DIFF
but does not fail.
"""
from __future__ import annotations

import argparse
import re
import sys

RE_ASSIGN = re.compile(r"^(CONFIG_[A-Za-z0-9_]+)=(.*)$")
RE_UNSET = re.compile(r"^# (CONFIG_[A-Za-z0-9_]+) is not set$")
RE_IF = re.compile(r"^\s*#\s*if(n?def)?\b")
RE_ENDIF = re.compile(r"^\s*#\s*endif\b")
RE_ELSE = re.compile(r"^\s*#\s*else\b")

WHITELIST_PREFIXES = ("CONFIG_KSU",)
WHITELIST_EXACT = {
    "CONFIG_TRIM_UNUSED_KSYMS",
    "CONFIG_UNUSED_KSYMS_WHITELIST",
    "CONFIG_LOCALVERSION_AUTO",
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allow",
        action="append",
        default=[],
        metavar="CONFIG_SYM",
        help="exact symbol whitelist for this invocation (repeatable); "
        "used for the V4-A panic-on experiment variable only",
    )
    parser.add_argument(
        "--allow-new",
        metavar="FILE",
        default=None,
        help="allowlist for final-only symbols (absent from stock+fragment); "
        "lines: 'CONFIG_X=value' asserts exact final value, 'CONFIG_X' allows "
        "any y/m, '#' comments; unlisted final-only y/m becomes a FAIL",
    )
    parser.add_argument("stock")
    parser.add_argument("frag")
    parser.add_argument("final")
    args = parser.parse_args()
    extra_allow = set(args.allow)
    if extra_allow:
        unknown = sorted(s for s in extra_allow if not s.startswith("CONFIG_"))
        if unknown:
            parser.error("--allow entries must be CONFIG_ symbols: %s"
                         % ", ".join(unknown))
    allow_new: dict[str, str | None] = {}
    allow_new_given = args.allow_new is not None
    if allow_new_given:
        for raw in open(args.allow_new, encoding="utf-8", errors="replace"):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            m = RE_ASSIGN.match(line)
            if m:
                allow_new[m.group(1)] = m.group(2).split("#", 1)[0].strip()
                continue
            m = RE_UNSET.match(line)
            if m:
                allow_new[m.group(1)] = "n"
                continue
            if line.startswith("CONFIG_"):
                allow_new[line] = None  # any y/m accepted
                continue
            parser.error("--allow-new %s: unparsable line: %s"
                         % (args.allow_new, line))
        if not allow_new:
            parser.error("--allow-new %s: no entries parsed" % args.allow_new)
    STOCK, FRAG, FINAL = args.stock, args.frag, args.final

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
        if is_whitelisted(sym) or sym in extra_allow:
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

    # Final-only detection: y/m (or n asserted via allowlist) symbols that
    # stock+fragment does not mention at all.
    # Asserted-n allowlist entries: must stay n.
    for sym in sorted(allow_new):
        want = allow_new[sym]
        if want != "n":
            continue
        got = final.get(sym)
        if got == "n":
            diffs += 1
            print("%-4s %-55s final=n (asserted n OK)" % ("NEW", sym))
        else:
            issues += 1
            print("%-4s %-55s final=%s (allowlist asserts n)" % ("FAIL", sym, got))
    for sym in sorted(final):
        if sym in expect or is_whitelisted(sym) or sym in extra_allow:
            continue
        got = final[sym]
        if got not in ("y", "m"):
            continue  # final-only 'n' is stock-equivalent; not drift
        if allow_new_given:
            want = allow_new.get(sym, "<unlisted>")
            if want is None:
                tag, note = "NEW", "allowed (any y/m)"
                diffs += 1
            elif want == got:
                tag, note = "NEW", "allowed (exact %s)" % want
                diffs += 1
            else:
                tag = "FAIL"
                issues += 1
                note = "allowlist wants %s" % want
        else:
            tag, note = "WARN", "no --allow-new given"
            warns += 1
        print("%-4s %-55s final=%s (%s)" % (tag, sym, got, note))

    print(
        "symbols: expect=%d final=%d diffs=%d warns=%d issues=%d"
        % (len(expect), len(final), diffs, warns, issues)
    )
    sys.exit(1 if issues else 0)


if __name__ == "__main__":
    main()
