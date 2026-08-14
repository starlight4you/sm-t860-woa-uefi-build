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
4. enables framebuffer DEBUG output;
5. removes Qualcomm and generic UEFI watchdog drivers for this diagnostic build.

The diagnostic artifact remains `deployable: false`. A stall may require a
manual long-press reboot because automatic watchdog reset is deliberately
disabled. It is not eligible for another device test until the Linux build,
recursive FV validation, compressed-payload binding, and artifact review pass.
