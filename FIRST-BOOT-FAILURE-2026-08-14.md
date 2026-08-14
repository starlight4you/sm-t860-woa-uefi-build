# SM-T860 first-boot failure and recovery — 2026-08-14

## Result

The exact UFS-offline recovery image reached its first visible firmware screen,
then reset into Samsung Download mode. It must not be flashed again unchanged.
The device did not display `SECURE CHECK FAIL`; Download mode reported a custom
binary. This places the failure after ABL accepted and started the recovery
payload, not at the Samsung image-signature gate.

The stock DWH1 recovery image was then written back to **RECOVERY only**. The
user confirmed that Android booted normally afterwards. No BOOT, DTBO, VBMETA,
PIT, userdata, ESP, or other partition was written in this test.

## Exact tested and rollback artifacts

- failed candidate: `gts6lwifi-ufs-offline.img`
  - bytes: `3837952`
  - SHA-256: `09043c50d3f6b46806ce6b26693cd6c4a010f37888d50bb69297711f55c6ceba`
- embedded FD:
  - bytes: `3145728`
  - SHA-256: `c08f5ef09c6674884f9833abe197ddbb00248b861c20e636f96d442ec135c89b`
- stock DWH1 recovery restored:
  - bytes: `82792448`
  - SHA-256: `e8a3ce8166feb198ee8e329110c0a12a2f075e7ab77e28a2fabdd80fb0cb8aab`
- current-session PIT read before the write:
  - bytes: `16384`
  - SHA-256: `74f72dbd9c219665c8cd6c21bbb52344f34f78dff6c8ef6b04030c0f09ac8a4f`
  - RECOVERY: entry 20, UFS identifier 21, 20213 blocks / 82792448 bytes

Both the candidate write and stock rollback completed with Heimdall reporting a
successful `RECOVERY` upload. The recovery image was far smaller than the fixed
RECOVERY partition and did not alter the PIT.

## Root-cause correction now under test

The failed image differed from upstream in three coupled ways: UFSDxe was
removed, but `EnableUfsIOC` and `UfsSmmuConfigForOtherBootDev` remained enabled;
the ACPI file was moved from the compressed inner FV to the outer FV; and boot
payload gzip was disabled. Both screen and memory serial output were disabled,
so the reset left no stage marker.

The new `first-boot-diagnostic` profile therefore:

1. restores the upstream compressed FV and gzip boot-payload layout;
2. removes UFSDxe and also sets both UFS initialization switches to zero;
3. preserves SdccDxe for the microSD path;
4. enables framebuffer DEBUG output in both secure-boot and no-secure-boot DSCs;
5. removes Qualcomm and generic UEFI watchdog drivers for this diagnostic build.

The diagnostic artifact remains `deployable: false`. A stall may require a
manual long-press reboot because automatic watchdog reset is deliberately
disabled. It is not eligible for another device test until the Linux build,
recursive FV validation, compressed-payload binding, and artifact review pass.

## Second controlled test — 2026-08-15

The reviewed diagnostic build completed all Linux CI and independent macOS
validation gates, then was written to **RECOVERY only** under a separate user
authorization:

- image: `gts6lwifi-first-boot-diagnostic.img`
- bytes: `2809856`
- SHA-256: `56fc7e18911f316dcb0e33862e4ccc833bd32d30b937ed9a6557f1bf9e3a3122`
- source commit: `7f654176a6f403ab4d6f4bc30724b1006b123327`
- GitHub Actions run: `31821798904`

The tablet briefly displayed text beginning with `UEFI Firmware`, then the
screen went black and the device repeatedly reset. This proves that ABL accepts
the Android boot container, BootShim reaches the FD, and framebuffer DEBUG is
active. Because both firmware watchdog drivers were absent from the exact FD,
the observation does not support the previous watchdog-timeout hypothesis. It
instead points to an early EDK2/platform failure or an explicit platform reset.

The exact DWH1 stock recovery listed above was immediately restored to
**RECOVERY only**. Heimdall reported a successful upload and normal reboot. No
other partition was written.

## Next binary control

Do not keep tuning the 2026 `main` build without a version control experiment.
The official Project Aloha `2412.74` SM8150 release differs materially from the
failed diagnostic FD: its parsed inventory includes `PciHostBridge`,
`GlinkDxe`, `PmicGlinkDxe`, `OSConfigDxe`, `AdapterInformationDxe`, and other
components absent from the current-main diagnostic build. The exact official
NOSB control is therefore the next useful isolation point:

- release: `https://github.com/Project-Aloha/mu_aloha_platforms/releases/tag/2412.74`
- tag: `994c2a064372aa56213f8ad79bda02d8b8e81c75`
- release ZIP bytes: `377543917`
- locally observed release ZIP SHA-256:
  `7ddc39aac2c92cf3ce341256baad34f34e50cc99af7cca55dd3b27971d724024`
- `samsung-gts6lwifi_NOSB.img` bytes: `2990080`
- image SHA-256:
  `92e0b002b5d14ab47a7851611529e0fa7700a8d160825120a2c2c561306548f5`
- embedded `SM8150_EFI_NOSB.fd` SHA-256:
  `119d01594436f83658bb6200c0295f9532b872e20d4130d9069a6c4c936bc394`

The control image independently passes the expected Android v0/page-4096,
six-byte ramdisk, gzip, 112-byte BootShim, exact-FD, and appended-DTB structure
checks. It remains non-deployable and is not authorized for device use merely
by being recorded here. If separately tested on RECOVERY and it boots, the
regression lies in post-2412.74 source/configuration changes. If it resets in
the same way, the upstream gts6lwifi port or this tablet's firmware revision is
the primary compatibility boundary.
