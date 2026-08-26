# CPH2609 KSUN + SUSFS

Reproducible ACK kernel builds for the OnePlus 12R (`CPH2609`) OxygenOS 14 `.810(EX01)` baseline.

## Pinned Inputs

- ACK common: `OnePlusOSS/android_kernel_common_oneplus_sm8550@4a62ecfd0ea4e2a3ffb932921133a6f499968574`
- OPlus modules/device tree: `OnePlusOSS/android_kernel_modules_and_devicetree_oneplus_sm8550@6ada53700a567e0b92cebebccb49b74db720f96a`
- KernelSU Next modern: `v3.1.0@4855fa3a844579eca5171aae7f3805fd72729b56`
- KernelSU Next SELinux-hide control: `v3.3.0@3b18216f71df189ab3d1b1ce0bdb21be1268e771`
- KernelSU Next legacy: `v3.1.0-legacy-susfs@ba4422f0556e10f40dda1887631d87a18ede4ec5`
- SUSFS: `gki-android13-5.15@ccb1918684b27644d17a6c842f57b60ae5966025`
- Android Clang: `r450784e`

The boot `Image` comes from the separate OnePlus ACK `common` tree, not the QCOM `msm-kernel` tree. `CONTROL-V2` proved the latter topology is not bootable on this baseline; `ACK-CONTROL-V1` proved the pinned ACK topology.

## Workflow Variants

`.github/workflows/build-810-ack-control.yml` supports:

- `control`: ACK without KernelSU or SUSFS
- `ksun`: plain KernelSU Next `v3.1.0`
- `ksun-susfs`: runtime-proven legacy branch
- `ksun-modern-susfs`: runtime-proven plain `v3.1.0` with the narrow glue in `scripts/patch_ksun_modern_susfs.py`
- `ksun-v330-control`: build-proven KernelSU Next `v3.3.0` control with Feature 4 `selinux_hide` and no SUSFS
- `ksun-v330-modern-susfs`: runtime-proven latest-stable KSUN route, combining native `v3.3.0` with the proven SUSFS `v2.2.0` kernel half through `scripts/patch_ksun_v330_modern_susfs.py`

All flashable candidates must preserve stock UTS, full LTO, CFI, MODVERSIONS, `F2FS_APPBOOST`, and `F2FS_FS_DEDUP`. The only intentional stock config exception is disabling `TRIM_UNUSED_KSYMS`, because the OEM private whitelist is unavailable. OEM CRC and boot/AVB audits are mandatory before deployment.

## Golden Nodes

- Legacy boot: `artifacts/final-810-ack-ksun-susfs/CPH2609_14.0.0.810_ACK_KSUN_SUSFS_boot.img`, SHA256 `84f26dc2b79e99d768199c1c2fb8e2133cc49922504c0da6a7048d460d9a70ed`
- Modern Manager-visible boot: `artifacts/final-810-ack-ksun-modern-susfs-manager-visible/boot.img`, SHA256 `76054f1b59b7900fe5133a8e8969bf1b843c9abcbb88b61d90e1b4381dbe09c6`
- Modern Manager-visible run: `32800414603`, project commit `7526bb564bb3fe2b3c1986df50631f9e4a9d40a7`
- Previous modern rollback: `artifacts/final-810-ack-ksun-modern-susfs/boot.img`, SHA256 `d67e607142c63010f730a407a1700e4ad40f016007f98abbff1f86cc797336d9`
- v3.3 SELinux-hide boot: `artifacts/final-810-ack-ksun-v330-modern-susfs/boot.img`, SHA256 `1df1ba37acc5a72d2b8d3936f5271dfedc946f2e0356e7f01c4469ffb2650084`
- v3.3 control run: `32919626207`; v3.3 Modern + SUSFS run: `32922903844`, project commit `8a8723149d99910c36074f6c11cf619daec6c499`

The Manager-visible modern node passed the 751-module zero-mismatch CRC gate, boot v4/AVB audit, full device boot, 473 loaded modules, Root, Manager `v3.1.0-modern-susfs (33024)`, SUSFS `v2.2.0` GKI supercalls, and bidirectional AVC Feature 10003/SUSFS CLI synchronization on `2026-08-25`.

The v3.3 node passed the same 751-module and 42,211-entry zero-mismatch CRC gate, boot v4/AVB audit, two complete device boots, 473 loaded modules, Root, SELinux Enforcing, Manager `v3.3.0-modern-susfs (33214-2)`, and SUSFS `v2.2.0` GKI supercalls on `2026-08-26`. Feature 4 was persisted across reboot; its first late enable correctly returned `EAGAIN`, while the same enable after reboot succeeded, proving that the boot-time policydb backup and native selinuxfs/`attr/current` hook initialization path completed.

## Feature Boundaries

- `avc_spoof` (Feature 10003) sanitizes SELinux contexts exposed through AVC denial/audit logs. The modern golden node synchronizes KSUN's implementation with the SUSFS `enable_avc_log_spoofing` command.
- `selinux_hide` (Feature 4) is a separate Dirty SEPolicy mitigation. It answers selected selinuxfs and process-attribute checks from a boot-time backup policydb.
- The pinned KSUN `v3.1.0` kernel, ksud, and Manager do not implement `selinux_hide`. The current modern and legacy golden nodes therefore prove AVC spoofing only, not SELinux-policy hiding.
- KernelSU Next `v3.3.0@3b18216f71df189ab3d1b1ce0bdb21be1268e771` is the first stable KSUN release containing the upstream `selinux_hide` implementation and its `attr/current` fix. The `ksun-v330-modern-susfs` route is now the preferred golden node; the v3.1.0 modern, legacy, and stock images remain independent rollback paths.

This device does not support `fastboot boot`. Always re-read the live slot, keep both legacy and stock rollback images, and write only the matching `boot_<slot>` partition after explicit confirmation.
