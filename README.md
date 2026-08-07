# CPH2609 KSUN + SUSFS

Reproducible kernel build for OnePlus 12R (`CPH2609`) OxygenOS 14.

Pinned inputs:

- OnePlus SM8550 Android 14 / OnePlus 12R kernel: `ce4627cedf3e4aac93ad0b369f623efa057707fe`
- KernelSU Next: `v3.3.0` (`3b18216f71df189ab3d1b1ce0bdb21be1268e771`)
- SUSFS: Android 13 GKI 5.15 (`ccb1918684b27644d17a6c842f57b60ae5966025`)
- Public Android Clang: `r450784d` from `android13-qpr3-release`

The workflow produces a kernel `Image`, not a flashable image. The final `boot.img`
must retain the exact CPH2609 `.831(EX01)` stock boot header and ramdisk.
