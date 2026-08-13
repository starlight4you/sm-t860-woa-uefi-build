# UFS-offline artifact provenance

These artifacts are a clean rebuild from repository baseline
`55fab00da43330b5720767182bff243d9cc8adf9` ("Make UFS-offline build artifacts
reproducible") with pinned `mu_aloha_platforms` revision
`96add763040d86d21f87a4a4022e094e17e6e3c6`. The build script and
`prepare-ufs-offline.py` were executed unmodified; no source fixes were
required this round.

Build host and toolchain:

- Ubuntu 24.04 LTS, Linux 6.8.0-71-generic x86_64
- Python 3.12.3, Git 2.43.0, Mono 6.8.0.105, NuGet 7.9.0.83
- clang/LLVM/lld 18.1.3 (`CLANGPDB_BIN=/usr/lib/llvm-18/bin/`,
  auto-detected by the build script)
- aarch64-linux-gnu-gcc 13.3.0 (`CLANGPDB_AARCH64_PREFIX=aarch64-linux-gnu-`)
- ACPICA iasl 20230628, NASM 2.16.01
- edk2-pytool-extensions 0.31.0, uefi_firmware 1.16 (temporary build venv)

Source preparation performed by the official `prepare-ufs-offline.py` inside
the temporary upstream tree:

- removed the single active `UFSDxe` reference from `APRIORI.inc`,
  `DXE.inc` and `DXE.dsc.inc` (1 -> 0 in each), keeping `SdccDxe`;
- moved the ACPI freeform include from the LZMA-compressed `FVMAIN` into the
  uncompressed outer `FVMAIN_COMPACT`;
- generated the T860 device `bootpack.json` override with
  `kernel_compressed=false`.

Static verification (`validate.py --profile ufs-offline`, recursive firmware
volume parsing with uefi_firmware 1.16) reports
`pass-ufs-offline-uefi-build`: exact safety DSDT embedded once in both the FD
and the boot image, boot image embeds the exact FD once, UFSDxe absent,
SdccDxe present. All artifacts remain `deployable=false`; no device writes
were performed.

## Difference from the `cbe1074` reference artifacts

The new FD/IMG are not byte-identical to the `cbe1074` reference artifacts
(`b86c695a...` / `ec672cf4...`). Comparison after decompressing the nested
LZMA FV shows the content difference is limited to:

- UTC-date firmware version values written by upstream `timebuild.sh`
  (2026-08-12 vs 2026-08-13 build dates) in PeiUniCore, SmBiosTableDxe and
  one generated FFS;
- the temporary build directory path embedded in LinuxLoader
  (`t860-uefi-build.XXXXXX`);
- compressed-container byte shifts resulting from the above.

The ACPI table storage file carrying the safety DSDT is byte-identical
between the two builds. The boot image difference is fully derived from the
embedded FD: bootshim, device tree and ramdisk sections are byte-identical.
The rebuilt artifacts passed the complete structural validation again after
the comparison.
