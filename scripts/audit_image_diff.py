#!/usr/bin/env python3
"""
Strict Independent Bounded Image Diff Audit for KPatch-Next on ARM64 Linux Kernel.

Validates that:
1. Patcher modifies ONLY authorized envelopes:
   - Kernel primary entry branch instruction at offset 4 (b_stext_insn_offset): exactly 4 bytes.
   - PAC instructions (0xd503211f / 0xd503233f / 0xd50323bf) substituted with NOP (0xd503201f)
     strictly within tcp_init_sock area (tcp_init_sock_offset <= offset < tcp_init_sock_offset + 0x1000).
   - Zero modifications anywhere else in the original kernel image range [0, orig_len).
2. Padding between orig_len and align_ceil(orig_len, 4096) is all zeroes.
3. Appended payload at align_ceil(orig_len, 4096) starts with preset_t header:
   - Magic: 'KP2026\0\0'
   - Setup kimg_size == orig_len
   - Setup kpimg_size == kpimg_len
4. Preserves IKCONFIG and UTS release string in the original kernel area.
"""

import argparse
import os
import struct
import sys

PAC_MASK = 0xFFFFFD1F
PAC_PATTERN = 0xD503211F
NOP = 0xD503201F
KP_MAGIC = b"KP2026\x00\x00"


def find_symbol_offset(system_map_path, symbol_name, text_sym="_text"):
    text_addr = None
    target_addr = None
    with open(system_map_path, "r", encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) >= 3:
                addr, _, name = parts[0], parts[1], parts[2]
                if name == text_sym and text_addr is None:
                    text_addr = int(addr, 16)
                elif name == "_stext" and text_addr is None:
                    # fallback if _text is absent
                    text_addr = int(addr, 16)
                if name == symbol_name and target_addr is None:
                    target_addr = int(addr, 16)
    if text_addr is None:
        raise ValueError(f"Symbol '{text_sym}' not found in System.map")
    if target_addr is None:
        raise ValueError(f"Symbol '{symbol_name}' not found in System.map")
    return target_addr - text_addr


def audit_image_diff(orig_path, patched_path, system_map_path, expected_kpimg_path=None):
    with open(orig_path, "rb") as f:
        orig_data = f.read()
    with open(patched_path, "rb") as f:
        patched_data = f.read()

    orig_len = len(orig_data)
    patched_len = len(patched_data)

    if patched_len <= orig_len:
        print(f"[-] Patched Image length ({patched_len}) must be larger than original ({orig_len})")
        return False

    align_orig_len = ((orig_len + 4095) // 4096) * 4096
    print(f"[+] Original Image size: {orig_len} (0x{orig_len:x}), aligned: {align_orig_len} (0x{align_orig_len:x})")
    print(f"[+] Patched Image size: {patched_len} (0x{patched_len:x})")

    # Locate tcp_init_sock
    tcp_offset = find_symbol_offset(system_map_path, "tcp_init_sock")
    print(f"[+] tcp_init_sock offset: 0x{tcp_offset:x} ({tcp_offset})")

    # Scan diffs in original kernel range [0, orig_len)
    diffs = []
    for i in range(orig_len):
        if orig_data[i] != patched_data[i]:
            diffs.append(i)

    print(f"[+] Found {len(diffs)} modified bytes in original kernel body [0, {orig_len})")

    # Group modified bytes into 4-byte instruction words
    modified_words = set(d & ~3 for d in diffs)
    print(f"[+] Modified 4-byte instruction words: {len(modified_words)}")

    header_branch_offset = 4  # ARM64 EFI header b_stext
    unauthorized_diffs = []
    pac_substitutions = []

    for word_offset in sorted(modified_words):
        orig_word = struct.unpack_from("<I", orig_data, word_offset)[0]
        patch_word = struct.unpack_from("<I", patched_data, word_offset)[0]

        if word_offset == header_branch_offset:
            # Must be branch to align_orig_len + 4096 (text_offset)
            expected_text_offset = align_orig_len + 4096
            delta = expected_text_offset - header_branch_offset
            expected_branch = 0x14000000 | ((delta >> 2) & 0x03FFFFFF)
            if patch_word != expected_branch:
                unauthorized_diffs.append(
                    f"Header branch mismatch at 0x{word_offset:x}: expected 0x{expected_branch:08x}, got 0x{patch_word:08x}"
                )
            else:
                print(f"  [VALID] Header branch substituted at 0x{word_offset:x}: 0x{orig_word:08x} -> 0x{patch_word:08x}")
            continue

        # Check if inside tcp_init_sock PAC envelope: [tcp_offset, tcp_offset + 0x1000)
        if tcp_offset <= word_offset < tcp_offset + 0x1000:
            # Must be PAC/AUT -> NOP substitution
            if (orig_word & PAC_MASK) == PAC_PATTERN and patch_word == NOP:
                pac_substitutions.append((word_offset, orig_word, patch_word))
                print(f"  [VALID] PAC substitution at 0x{word_offset:x} (+0x{word_offset - tcp_offset:x}): 0x{orig_word:08x} -> 0x{patch_word:08x} (NOP)")
                continue
            else:
                unauthorized_diffs.append(
                    f"Invalid patch in tcp_init_sock envelope at 0x{word_offset:x}: 0x{orig_word:08x} -> 0x{patch_word:08x} (not PAC->NOP)"
                )
                continue

        unauthorized_diffs.append(
            f"Unauthorized modification at 0x{word_offset:x}: 0x{orig_word:08x} -> 0x{patch_word:08x}"
        )

    # 1. Enforce zero unauthorized modifications
    if unauthorized_diffs:
        print("[-] REJECT: Unauthorized modifications detected outside bounded envelopes:")
        for u in unauthorized_diffs:
            print(f"    {u}")
        return False

    if len(pac_substitutions) == 0:
        print("[-] REJECT: No PAC substitutions found in tcp_init_sock envelope!")
        return False

    # 2. Check padding between orig_len and align_orig_len
    padding_bytes = patched_data[orig_len:align_orig_len]
    if any(b != 0 for b in padding_bytes):
        print(f"[-] REJECT: Non-zero padding bytes found between 0x{orig_len:x} and 0x{align_orig_len:x}")
        return False
    print(f"[+] Page alignment padding ({len(padding_bytes)} bytes) is all zero.")

    # 3. Check preset_t at align_orig_len
    preset_bytes = patched_data[align_orig_len:align_orig_len + 0x400]
    magic = preset_bytes[:8]
    if magic != KP_MAGIC:
        print(f"[-] REJECT: Invalid KPatch preset magic: {magic!r}, expected {KP_MAGIC!r}")
        return False

    setup_offset = align_orig_len + 64
    kimg_size = struct.unpack_from("<q", patched_data, setup_offset + 8)[0]
    kpimg_size = struct.unpack_from("<q", patched_data, setup_offset + 16)[0]

    print(f"[+] Preset header magic: {magic!r}")
    print(f"[+] Preset setup kimg_size: {kimg_size} (expected {orig_len})")
    print(f"[+] Preset setup kpimg_size: {kpimg_size}")

    if kimg_size != orig_len:
        print(f"[-] REJECT: Preset kimg_size ({kimg_size}) does not match original Image size ({orig_len})")
        return False

    if expected_kpimg_path and os.path.exists(expected_kpimg_path):
        expected_kpimg_len = os.path.getsize(expected_kpimg_path)
        if kpimg_size != expected_kpimg_len:
            print(f"[-] REJECT: Preset kpimg_size ({kpimg_size}) != expected file size ({expected_kpimg_len})")
            return False
        # Compare kpimg code text payload
        injected_kpimg = patched_data[align_orig_len:align_orig_len + kpimg_size]
        with open(expected_kpimg_path, "rb") as kf:
            orig_kpimg = kf.read()
        if injected_kpimg[4096:] != orig_kpimg[4096:]:
            print("[-] REJECT: Injected kpimg code text (at +4096) does not match source kpimg-linux binary!")
            return False
        print("[+] Injected kpimg code payload verified against input kpimg-linux.")

    # 4. Validate IKCONFIG and UTS release string preservation
    ikconfig_magic = b"IKCFG_ST"
    if ikconfig_magic not in patched_data[:orig_len]:
        print("[-] REJECT: IKCONFIG magic missing from patched kernel!")
        return False
    orig_ikconfig_pos = orig_data.find(ikconfig_magic)
    patched_ikconfig_pos = patched_data.find(ikconfig_magic)
    if orig_ikconfig_pos != patched_ikconfig_pos:
        print(f"[-] REJECT: IKCONFIG position shifted from 0x{orig_ikconfig_pos:x} to 0x{patched_ikconfig_pos:x}")
        return False
    print(f"[+] IKCONFIG intact at 0x{orig_ikconfig_pos:x}.")

    uts_needle = b"Linux version 5.15.123-android13-8-00760-gf490405820f7"
    if uts_needle not in patched_data[:orig_len]:
        print("[-] REJECT: Stock UTS release string missing from patched kernel!")
        return False
    print("[+] Stock UTS release string intact.")

    print(f"[+] SUCCESS: Patched Image strictly satisfies bounded diff audit.")
    print(f"    - PAC modifications count: {len(pac_substitutions)}")
    print(f"    - Entry branch: correct target to text_offset")
    print(f"    - Zero unauthorized modifications anywhere in kernel text/data")
    print(f"    - Valid preset header and payload boundaries")
    return True


def main():
    parser = argparse.ArgumentParser(description="Strict Bounded Image Diff Audit for KPatch-Next")
    parser.add_argument("--orig", required=True, help="Path to original golden Image")
    parser.add_argument("--patched", required=True, help="Path to patched Image")
    parser.add_argument("--sysmap", required=True, help="Path to golden System.map")
    parser.add_argument("--kpimg", required=False, help="Path to kpimg-linux binary")
    args = parser.parse_args()

    ok = audit_image_diff(args.orig, args.patched, args.sysmap, args.kpimg)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
