# UFS-offline artifact provenance

These artifacts were built on Ubuntu 24.04 from repository baseline `727b860`
and pinned `mu_aloha_platforms` revision
`96add763040d86d21f87a4a4022e094e17e6e3c6`. They were uploaded in commit
`cbe1074`.

The Linux build required two temporary-tree transformations that were reported
after the artifact commit but were not included in `cbe1074`'s source tree:

- move the ACPI freeform include from the LZMA-compressed `FVMAIN` into the
  uncompressed outer `FVMAIN_COMPACT`;
- set the T860 device boot-pack override to `kernel_compressed=false`.

The source commit containing this note formalizes those transformations in
`prepare-ufs-offline.py`, accepts the normal Git submodule gitfile layout, pins
the upstream revision in the build script, and explicitly exports the build
toolchain environment. This closes the source-level handoff gap, but the
published binaries remain reference artifacts rather than deployable images.

Independent verification on macOS rechecked all existing `SHA256SUMS.txt`
entries and reran `validate.py` with `uefi_firmware==1.16`. The result remained
`pass-ufs-offline-uefi-build`, with `ufs_driver_present=false`,
`sdcc_driver_present=true`, exact AML occurrence count 1 in both files, exact
firmware occurrence count 1 in the boot image, and `deployable=false`.
