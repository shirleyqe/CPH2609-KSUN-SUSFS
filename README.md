# CPH2609 KSUN + SUSFS

Reproducible kernel build for OnePlus 12R (`CPH2609`) OxygenOS 14.

Pinned inputs:

- OnePlus SM8550 Android 14 / OnePlus 12R kernel: `ce4627cedf3e4aac93ad0b369f623efa057707fe`
- Matching OnePlus modules/device tree: `6ada53700a567e0b92cebebccb49b74db720f96a`
- KernelSU Next SUSFS: `v3.1.0-legacy-susfs` (`ba4422f0556e10f40dda1887631d87a18ede4ec5`)
- SUSFS: Android 13 GKI 5.15 (`ccb1918684b27644d17a6c842f57b60ae5966025`)
- Public Android Clang: `r450784d` from `android13-qpr3-release`

Toolchain note: the stock `.831(EX01)` boot kernel was compiled with clang
`r450784e` ("Android (8508608, based on r450784e)"). `r450784e` is NOT
published on `android13-qpr3-release` (googlesource archive returns 400 for
`clang-r450784e.tar.gz`), so the closest obtainable public build is
`r450784d` (one build number earlier, same branch). The resulting compiler
self-string differs only in the `r450784d` vs `r450784e` suffix; everything
else (clang 14.0.7 line, AArch64 defaults) matches the stock toolchain.

V2 build policy (stock fidelity):

- Config base: `stock-config/stock_config.txt` — the OEM `.config` embedded
  in the stock `.831(EX01)` boot kernel (IKCONFIG blob), extracted verbatim.
- Only KSUN/SUSFS switches are added (`--enable KSU --enable KSU_SUSFS`).
- Full LTO is KEPT (stock profile). The previous ThinLTO selection was a
  runner-time compromise and is no longer applied.
- `CONFIG_QCOM_SMEM` stays off like stock (vendor_boot dlkm carries it).
- The workflow also regenerates the V1 reference config (gki_defconfig +
  legacy V1 switches) into the artifact for the V1/V2 config diff.

The workflow produces a kernel `Image`, not a flashable image. The final `boot.img`
must retain the exact CPH2609 `.831(EX01)` stock boot header and ramdisk.
