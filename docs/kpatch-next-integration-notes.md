# KPatch-Next Integration and Bounded Image Diff Specification

## 1. Overview and Architecture

KPatch-Next is an external post-link binary patcher and runtime KPM (KernelPatch Module) loader maintained by `KernelSU-Next` (`https://github.com/KernelSU-Next/KPatch-Next`).
It integrates with Android kernels without requiring in-tree source code changes or `CONFIG_KPM=y`.

### Architectural Components

- **Kernel Trampoline (`kpimg`)**: Injected into the stripped ARM64 `Image` binary.
- **Patcher Utility (`kptools`)**: Host executable (`tools/kptools`) that inspects kernel `kallsyms`, locates required anchor symbols, patches PAC instructions in `tcp_init_sock` to NOPs, redirects kernel primary entry (`b_stext`) to `kpimg`, and appends `kpimg` and preset configuration metadata.
- **Userspace Companion CLI (`kpatch`)**: Android ARM64 binary communicating with `kpimg` via SuperCall (Syscall 45) governed by `current_uid() == 0u`.
- **Demo Module (`demo-hello.kpm`)**: Benign reference KPM demonstrating load, control ioctl, and unload lifecycle (`KPM_NAME("kpm-hello-demo")`).

## 2. Pinned Toolchain and Upstream Sources

- **KPatch-Next Upstream Commit**: `456744b29efb9989445463ab29e368fa59a103c4`
  - Incorporates critical SMP text-patching fixes (`kernel: fix stop_machine` dynamically resolving `__cpu_online_mask` and passing online CPU mask to `stop_machine`).
- **Bare-Metal Toolchain**: ARM GNU Toolchain 12.2.rel1 (`aarch64-none-elf`)
  - Toolchain archive: `arm-gnu-toolchain-12.2.rel1-x86_64-aarch64-none-elf.tar.xz`
  - SHA256: `62d66e0ad7bd7f2a183d236ee301a5c73c737c886c7944aa4f39415aab528daf`
- **Android NDK**: AOSP NDK `r26b` (for building `kpatch` CLI targeting Android API 33, `arm64-v8a`)
- **Host Compiler**: Host GCC 11 / Clang with CMake and `zlib1g-dev`

## 3. Golden Kernel Baseline Provenance

- **Firmware**: OnePlus 12R `CPH2609_14.0.0.810(EX01)`, SDK 34
- **Kernel Baseline**: ACK common `5.15.123` (`sm8550@4a62ecf`), KSUN `v3.3.0@3b18216`, SUSFS `v2.2.0@ccb1918`
- **Golden Run ID**: `32922903844`
- **Golden Image SHA256**: `95e944346efd50cb197b3b5887a26aa0e4f158c2167f45915176fcc94e78948e`
- **Golden vmlinux SHA256**: `5bfa9da3066093e56130eaaaef79e501518338862e0bf5d99a166df3a1f599b7`
- **Golden System.map SHA256**: `4103d1f35f3c1ae4679cc52276580d271889b6fea162631b21c374ae9d6d2ba9`

## 4. Strict Bounded Image Diff Specification

`audit_image_diff.py` enforces mathematical boundaries on every byte modified between the golden `Image` and the patched `Image`:

1. **Kernel Header Branch (4 bytes)**:
   - Offset: 0x4 (`b_stext_insn_offset` in ARM64 EFI header).
   - Expected instruction: `b #(align_ceil(len(Image), 4096) + 4096 - 4)`.
   - Replaces the original branch to `primary_entry`.
2. **PAC Instruction Replacement Envelope**:
   - Location: Strictly within `[tcp_init_sock, tcp_init_sock + 0x1000)`.
   - Condition: Every modified word must have original instruction matching PAC mask `0xFFFFFD1F == 0xD503211F` (e.g., `paciasp`, `autiasp`) and replaced by ARM64 NOP (`0xD503201F`).
3. **Zero In-Body Modification**:
   - Every single byte outside the 4-byte header branch and the `tcp_init_sock` PAC substitutions in `[0, len(orig_Image))` must be identical to the original golden Image.
4. **Alignment Padding**:
   - Padding between `len(orig_Image)` and `align_ceil(len(orig_Image), 4096)` must be 100% zero bytes.
5. **Appended Payload Boundary & Metadata**:
   - Starts at `align_ceil(len(orig_Image), 4096)`.
   - Begins with `preset_t` header: magic `KP2026\0\0`.
   - Setup field `kimg_size` must equal `len(orig_Image)`.
   - Setup field `kpimg_size` must equal `len(kpimg)`.
   - Preserved `IKCONFIG` (`IKCFG_ST`) and UTS release string (`Linux version 5.15.123-android13-8-00760-gf490405820f7`) remain intact at identical offsets.

## 5. Distinction Between OEM CRC Audit and Binary Diff Proof

- **OEM CRC Audit (`audit_module_crcs.py`)**:
  - Compares `__kcrctab` symbol checksums in `vmlinux` against `__versions` tables in all 751 vendor `.ko` modules.
  - Certifies that the compile-time kernel ABI is 100% compatible with stock OnePlus modules (0 mismatches).
  - *Crucial note*: Because `kptools` patches only the stripped ARM64 `Image`, `vmlinux` is not touched. OEM CRC audit verifies the compilation baseline, but cannot detect binary patching defects.
- **Bounded Binary Diff Audit (`audit_image_diff.py`)**:
  - Directly verifies byte-level modifications on the final flashable binary `Image`.
  - Guarantees zero unintended instruction alterations, zero data corruption, and exact alignment/metadata compliance.
