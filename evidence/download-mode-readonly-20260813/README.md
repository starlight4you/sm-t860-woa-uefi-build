# SM-T860 current-session read-only Download Mode drill

Date: 2026-08-13. The user explicitly authorized one reboot into Samsung
Download Mode, one read-only PIT download, and a return to Android. The scope
excluded partition uploads, `flash`, PIT writes, repartitioning, and all UEFI
image writes.

## Result

- Preflight matched one `SM-T860` / `gts6lwifi`, bootloader
  `T860XXS5DWH1`, unlocked/orange state, and 100% battery. The raw device
  serial is deliberately not published.
- The tablet initially disappeared from USB after `adb reboot download`.
  No Heimdall command was run until macOS later enumerated exactly one Samsung
  Download Mode device as `04e8:685d`.
- The fixed ARM64 Heimdall v2.0.2 binary had SHA-256
  `636997aca4845d1ff253bf30adc98b4f2bd7a9fafbdceda7e7647527d17843ef`.
- The only acquisition command was:

```text
/Volumes/Clips 2301-04/t860-ui8/heimdall download-pit --output /Volumes/Clips 2301-04/current-session.pit --no-reboot --stdout-errors
```

- It returned exit code 0 and printed `Session begun.` and
  `PIT file download successful.` No upload, flash, PIT write, repartition, or
  `--skip-size-check` operation was requested.
- The downloaded PIT is 16,384 bytes with SHA-256
  `74f72dbd9c219665c8cd6c21bbb52344f34f78dff6c8ef6b04030c0f09ac8a4f`.
  It parses as `COM_TAR2`, `SM8150`, 4 logical units, and 76 entries.
- All fields of all 76 partition entries match the fixed DWH1 stock PIT. The
  complete 10,572-byte stock PIT is an exact prefix of the downloaded file,
  including its 512-byte Samsung trailer. The download only adds 5,812
  zero-padding bytes, explaining why its raw size and hash differ.
- The separate exit command was:

```text
/Volumes/Clips 2301-04/t860-ui8/heimdall close-pc-screen --resume --stdout-errors
```

  It returned exit code 0 and printed `Rebooting device...`. About one minute
  later, the same preflight device identity returned through ADB with
  `sys.boot_completed=1`, the same DWH1 bootloader, and orange verified-boot
  state.

The repository validator accepted the current transport evidence as
`pass-recovery-transport-drill`. This is local, self-attested evidence rather
than cryptographic execution attestation. It does not authorize a device
write. `RECOVERY_BOOT_TRIGGER_VALIDATED` remains `false`, so the aggregate
result remains `blocked-first-boot-execution`, `execution_prerequisites_ready:
false`, and `deployable: false`.

This evidence is permanently scoped to the historical, untraceable Heimdall
2.0.2 binary recorded by transport schema 2. It does not establish provenance
or liveness for the separate SourceHut v2.2.2 execution-tool candidate, and it
must not be rewritten to claim that it does.

## Files

- The exact `current-session.pit` remains local at
  `/Volumes/Clips 2301-04/current-session.pit`; it is not published because it
  contains the complete device partition layout. Its fixed hash and parsed
  comparison are published below.
- `download-pit.normalized.log`: normalized acquisition transcript. It was
  reconstructed from the captured command output during the same collection
  window; it is not claimed to be tamper-proof telemetry.
- `exit-and-android.normalized.log`: normalized exit and Android return record.
- `pit-comparison.json`: parsed structure and byte-layout comparison.
- `transport-gate-summary.json`: result extracted from the pinned validator at
  UEFI repository commit `49d0758ded56f38eea0eac91e9f5da046c630474`.
- `SHA256SUMS.txt`: hashes for the five published evidence payloads. The local
  PIT is deliberately excluded from that machine-checkable list; its hash is
  recorded above.

No raw device serial is included in this public evidence set.
