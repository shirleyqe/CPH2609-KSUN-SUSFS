# CPH2609 KSUN + SUSFS

Reproducible kernel build for OnePlus 12R (`CPH2609`) OxygenOS 14.

Pinned inputs:

- OnePlus SM8550 Android 14 / OnePlus 12R kernel: `ce4627cedf3e4aac93ad0b369f623efa057707fe`
- Matching OnePlus modules/device tree: `6ada53700a567e0b92cebebccb49b74db720f96a`
- KernelSU Next SUSFS: `v3.1.0-legacy-susfs` (`ba4422f0556e10f40dda1887631d87a18ede4ec5`)
- SUSFS: Android 13 GKI 5.15 (`ccb1918684b27644d17a6c842f57b60ae5966025`)
- Public Android Clang: `r450784d` from `android13-qpr3-release`

The hosted build selects Clang ThinLTO instead of the GKI defconfig's FullLTO
so the complete verification build fits the runner execution window; the
selected mode is recorded in the artifact `.config`.

The workflow produces a kernel `Image`, not a flashable image. The final `boot.img`
must retain the exact CPH2609 `.831(EX01)` stock boot header and ramdisk.
