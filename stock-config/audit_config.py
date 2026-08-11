#!/usr/bin/env python3
"""Audit final .config against (stock IKCONFIG + QCOM fragment) expectation.

Prints symbols whose value in the final .config differs from what the
stock base + kalama_GKI.config fragment prescribe, then exits nonzero if
any non-whitelisted value went from y/m in the expectation to n in the
final config (i.e. olddefconfig silently dropped a required feature).

Whitelist: KSU/SUSFS family (intentional additions) and symbols with no
prescribed value (vendor-tree Kconfig defaults such as DYNAMIC_TUNING_*).
"""
import re
import sys

STOCK = sys.argv[1]
FRAG = sys.argv[2]
FINAL = sys.argv[3]
WHITELIST_PREFIXES = ("CONFIG_KSU",)


def parse(path):
    out = {}
    for line in open(path, encoding="utf-8", errors="replace"):
        line = line.rstrip("\r\n")
        m = re.match(r"^(CONFIG_[A-Za-z0-9_]+)=(.*)$", line)
        if m:
            out[m.group(1)] = m.group(2)
            continue
        m = re.match(r"^# (CONFIG_[A-Za-z0-9_]+) is not set$", line)
        if m:
            out[m.group(1)] = "n"
    return out


expect = parse(STOCK)
for sym, val in parse(FRAG).items():
    if val == "n":
        # merge_config semantics: a '# CONFIG_X is not set' fragment line just
        # removes the symbol so the Kconfig default decides; the stock IKCONFIG
        # already carries the resulting value, so do not constrain here.
        continue
    expect[sym] = val
final = parse(FINAL)

issues = 0
for sym in sorted(expect):
    if sym.startswith(WHITELIST_PREFIXES):
        continue
    if sym.startswith("CONFIG_TRIM_UNUSED_KSYMS") or sym.startswith(
            "CONFIG_UNUSED_KSYMS_WHITELIST"):
        # deliberate deviation: whitelist is a vendor build-machine absolute
        # path unavailable to public builds.
        continue
    want = expect[sym]
    got = final.get(sym)
    if got != want:
        print("DIFF %-55s expect=%s final=%s" % (sym, want, got))
        if want in ("y", "m") and got != want:
            issues += 1
print("symbols: expect=%d final=%d issues=%d" % (len(expect), len(final), issues))
sys.exit(1 if issues else 0)
