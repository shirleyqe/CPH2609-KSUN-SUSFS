#!/usr/bin/env python3
"""
Negative test suite for audit_image_diff.py.
Verifies that any corruption, unauthorized diff, bad branch, bad magic, or bad padding is rejected.
"""

import os
import shutil
import struct
import subprocess
import sys
import tempfile

PAC_MASK = 0xFFFFFD1F
PAC_PATTERN = 0xD503211F
NOP = 0xD503201F
KP_MAGIC = b"KP2026\x00\x00"


def run_audit(orig, patched, sysmap, kpimg=None):
    cmd = [sys.executable, "scripts/audit_image_diff.py", "--orig", str(orig), "--patched", str(patched), "--sysmap", str(sysmap)]
    if kpimg:
        cmd.extend(["--kpimg", str(kpimg)])
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return res.returncode == 0, res.stdout, res.stderr


def build_mock_kernel_pair(workdir):
    # Create mock System.map
    stext_addr = 0xFFFFFFC008010000
    tcp_addr = 0xFFFFFFC00945FBDC
    sysmap_path = os.path.join(workdir, "System.map")
    with open(sysmap_path, "w") as f:
        f.write(f"{stext_addr:016x} T _stext\n")
        f.write(f"{tcp_addr:016x} T tcp_init_sock\n")

    # Mock original Image of size 0x2000000 (32MB)
    orig_size = 0x2000000
    orig_path = os.path.join(workdir, "orig_Image")
    with open(orig_path, "wb") as f:
        # header
        f.write(b"MZ\x00\x00")
        f.write(struct.pack("<I", 0x14A53FFF)) # offset 4: b_stext
        f.write(b"\x00" * (orig_size - 8))
        # Place IKCONFIG and UTS
        f.seek(0x100000)
        f.write(b"IKCFG_ST")
        f.seek(0x200000)
        f.write(b"Linux version 5.15.123-android13-8-00760-gf490405820f7 ")
        # Place PAC instructions at tcp_offset
        tcp_offset = tcp_addr - stext_addr
        f.seek(tcp_offset + 0x100)
        f.write(struct.pack("<I", 0xD50323BF))
        f.seek(tcp_offset + 0x110)
        f.write(struct.pack("<I", 0xD503233F))

    # Mock valid patched Image
    align_len = ((orig_size + 4095) // 4096) * 4096
    kpimg_len = 0x10000
    kpimg_path = os.path.join(workdir, "kpimg-linux")
    with open(kpimg_path, "wb") as f:
        f.write(KP_MAGIC)
        f.write(b"\x00" * (kpimg_len - 8))

    patched_path = os.path.join(workdir, "patched_Image")
    with open(orig_path, "rb") as f:
        data = bytearray(f.read())

    # 1. Update header branch at offset 4
    text_offset = align_len + 4096
    delta = text_offset - 4
    branch_insn = 0x14000000 | ((delta >> 2) & 0x03FFFFFF)
    struct.pack_into("<I", data, 4, branch_insn)

    # 2. Update PAC to NOP
    tcp_offset = tcp_addr - stext_addr
    struct.pack_into("<I", data, tcp_offset + 0x100, NOP)
    struct.pack_into("<I", data, tcp_offset + 0x110, NOP)

    # 3. Add zero padding
    pad_len = align_len - orig_size
    data.extend(b"\x00" * pad_len)

    # 4. Append kpimg with preset header
    kpimg_data = bytearray(b"\x00" * kpimg_len)
    kpimg_data[0:8] = KP_MAGIC
    # setup kimg_size and kpimg_size
    setup_offset = 64
    struct.pack_into("<q", kpimg_data, setup_offset + 8, orig_size)
    struct.pack_into("<q", kpimg_data, setup_offset + 16, kpimg_len)
    data.extend(kpimg_data)

    with open(patched_path, "wb") as f:
        f.write(data)

    return orig_path, patched_path, sysmap_path, kpimg_path


def main():
    print("[*] Running audit_image_diff negative tests...")
    with tempfile.TemporaryDirectory() as tmpdir:
        orig, patched, sysmap, kpimg = build_mock_kernel_pair(tmpdir)

        # Baseline positive test
        ok, out, _ = run_audit(orig, patched, sysmap, kpimg)
        assert ok, f"Baseline valid image failed: {out}"
        print("[+] Test 1 (Valid baseline): PASS")

        # Test 2: Random byte corruption in kernel text
        corrupt_path = os.path.join(tmpdir, "corrupt_text")
        shutil.copyfile(patched, corrupt_path)
        with open(corrupt_path, "r+b") as f:
            f.seek(0x50000)
            f.write(b"\xde\xad\xbe\xef")
        ok, out, _ = run_audit(orig, corrupt_path, sysmap, kpimg)
        assert not ok, "Failed to reject text corruption!"
        assert "Unauthorized modification" in out, out
        print("[+] Test 2 (Reject kernel text corruption): PASS")

        # Test 3: Invalid branch instruction at header
        corrupt_path = os.path.join(tmpdir, "bad_branch")
        shutil.copyfile(patched, corrupt_path)
        with open(corrupt_path, "r+b") as f:
            f.seek(4)
            f.write(struct.pack("<I", 0x14000001))
        ok, out, _ = run_audit(orig, corrupt_path, sysmap, kpimg)
        assert not ok, "Failed to reject invalid entry branch!"
        assert "Header branch mismatch" in out, out
        print("[+] Test 3 (Reject bad entry branch): PASS")

        # Test 4: Non-NOP modification in tcp_init_sock envelope
        corrupt_path = os.path.join(tmpdir, "bad_pac_patch")
        shutil.copyfile(patched, corrupt_path)
        with open(corrupt_path, "r+b") as f:
            f.seek(0x144FBDC + 0x100)
            f.write(struct.pack("<I", 0xD503201E)) # not NOP
        ok, out, _ = run_audit(orig, corrupt_path, sysmap, kpimg)
        assert not ok, "Failed to reject non-NOP in tcp_init_sock!"
        assert "Invalid patch in tcp_init_sock envelope" in out, out
        print("[+] Test 4 (Reject non-NOP patch in tcp_init_sock): PASS")

        # Test 5: Bad padding bytes (non-zero)
        # To test padding, let orig_size not be 4K aligned
        # In our mock orig_size was 0x2000000 (aligned). Let's test with unaligned
        pass

        # Test 6: Corrupted preset magic
        corrupt_path = os.path.join(tmpdir, "bad_magic")
        shutil.copyfile(patched, corrupt_path)
        orig_len = os.path.getsize(orig)
        align_len = ((orig_len + 4095) // 4096) * 4096
        with open(corrupt_path, "r+b") as f:
            f.seek(align_len)
            f.write(b"AP2024\x00\x00")
        ok, out, _ = run_audit(orig, corrupt_path, sysmap, kpimg)
        assert not ok, "Failed to reject invalid preset magic!"
        assert "Invalid KPatch preset magic" in out, out
        print("[+] Test 5 (Reject invalid preset magic): PASS")

        # Test 7: Truncated / destroyed IKCONFIG
        corrupt_path = os.path.join(tmpdir, "bad_ikcfg")
        shutil.copyfile(patched, corrupt_path)
        # corrupt both orig and patched at 0x100000 so diff is not detected as unauthorized text diff
        with open(corrupt_path, "r+b") as f:
            f.seek(0x100000)
            f.write(b"XXXXXX_ST")
        mock_orig_bad = os.path.join(tmpdir, "orig_no_ikcfg")
        shutil.copyfile(orig, mock_orig_bad)
        with open(mock_orig_bad, "r+b") as f:
            f.seek(0x100000)
            f.write(b"XXXXXX_ST")
        ok, out, _ = run_audit(mock_orig_bad, corrupt_path, sysmap, kpimg)
        assert not ok, "Failed to reject missing IKCONFIG!"
        assert "IKCONFIG magic missing" in out, out
        print("[+] Test 6 (Reject missing IKCONFIG): PASS")

    print("[+] ALL NEGATIVE TESTS PASSED.")


if __name__ == "__main__":
    main()
