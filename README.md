# CPH2609 KSUN + SUSFS

Reproducible kernel build for OnePlus 12R (`CPH2609`) OxygenOS 14.

Pinned inputs:

- OnePlus SM8550 Android 14 / OnePlus 12R kernel: `ce4627cedf3e4aac93ad0b369f623efa057707fe`
- Matching OnePlus modules/device tree: `6ada53700a567e0b92cebebccb49b74db720f96a`
- KernelSU Next SUSFS: `v3.1.0-legacy-susfs` (`ba4422f0556e10f40dda1887631d87a18ede4ec5`)
- SUSFS: Android 13 GKI 5.15 (`ccb1918684b27644d17a6c842f57b60ae5966025`)
- Public Android Clang: `r450784e` from `android14-release`

OxygenOS 14 `.810` control status:

- `CONTROL-V2` is confirmed not bootable. It incorrectly built the QCOM
  `msm-kernel` tree as the boot kernel even though the production kalama build
  is a mixed build whose boot `Image` comes from the separate ACK `common` tree.
- `ACK-CONTROL-V1` pins the public OnePlus ACK 5.15.123 release commit
  `4a62ecfd0ea4e2a3ffb932921133a6f499968574`. It contains the stock-required
  `F2FS_APPBOOST` and `F2FS_FS_DEDUP` changes and is built without KSU/SUSFS.
- ACK control artifacts must pass stock config and OEM module CRC audits before
  they are eligible for a device boot test.
- `ACK-CONTROL-V1` passed those gates and booted `.810` successfully on the
  CPH2609. The same workflow now supports a `ksun` variant so KernelSU Next can
  be isolated and tested before any SUSFS patch is added.

Toolchain note: the stock `.831(EX01)` boot kernel was compiled with clang
`r450784e` ("Android (8508608, based on r450784e)"). V3 pulls the matching
public tarball from `android14-release` (`clang-r450784e.tar.gz`) and asserts
the compiler self-string contains `r450784e`.

V3 build policy (stock fidelity + official QCOM fragment):

- Config base: `stock-config/stock_config.txt` — the OEM `.config` embedded
  in the stock `.831(EX01)` boot kernel (IKCONFIG blob), extracted verbatim.
- Fragment: `stock-config/kalama_GKI.config` — official OnePlus/QCOM kalama
  GKI defconfig fragment, merged with strict Kconfig line rules:
  - `#ifdef OPLUS_*` bodies kept (device feature macros assumed true)
  - only `CONFIG_FOO=val` and `# CONFIG_FOO is not set` apply
  - comment-lookalikes such as `# CONFIG_ZRAM=m` are ignored (not overrides)
- Intentional delta only: `--enable KSU --enable KSU_SUSFS` and
  `--disable TRIM_UNUSED_KSYMS` (stock whitelist is a vendor-machine path).
- Full LTO is KEPT (stock profile).
- Official fragment values restored vs V2 stock-only profile, including
  `CONFIG_QCOM_SMEM=m`, `CONFIG_OPLUS_FEATURE_SENSOR_CFG=m`,
  `CONFIG_OPLUS_FEATURE_OPROJECT=m`, `CONFIG_HORAE_THERMAL_SHELL=m`,
  `CONFIG_OPLUS_CHG=m`, plus the QCOM UFS/PHY/SMEM chain.

The workflow produces a kernel `Image`, not a flashable image. The final `boot.img`
must retain the exact CPH2609 `.831(EX01)` stock boot header and ramdisk.
