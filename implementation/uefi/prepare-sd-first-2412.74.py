#!/usr/bin/env python3
"""Patch Project Aloha 2412.74 for an SM8150 MTP SdccDxe A/B diagnostic."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def replace_once(data: bytes, old: bytes, new: bytes, label: str) -> bytes:
    count = data.count(old)
    if count != 1:
        raise SystemExit(f"error: {label} marker count is {count}, expected 1")
    return data.replace(old, new, 1)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_root", type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()

    root = args.source_root.resolve()
    source = root / "Common/MU/PcBdsPkg/MsBootPolicy/MsBootPolicy.c"
    inf = root / "Common/MU/PcBdsPkg/MsBootPolicy/MsBootPolicy.inf"
    t860_sdcc = (
        root
        / "Platforms/SurfaceDuo1Pkg/Device/samsung-gts6lwifi/Binaries/QcomPkg/Drivers/SdccDxe/SdccDxe.efi"
    )
    mtp_sdcc = (
        root
        / "Platforms/SurfaceDuo1Pkg/Device/qcom-mtp8150/Binaries/QcomPkg/Drivers/SdccDxe/SdccDxe.efi"
    )
    t860_depex = t860_sdcc.with_suffix(".depex")
    mtp_depex = mtp_sdcc.with_suffix(".depex")
    for path in (source, inf, t860_sdcc, mtp_sdcc, t860_depex, mtp_depex):
        if not path.is_file() or path.is_symlink():
            raise SystemExit(f"error: missing regular source file: {path}")

    expected_t860_sdcc = "7a8104ad2d939fc61247421211f4e408b61301b3c726239119de56e86e137f8e"
    expected_mtp_sdcc = "3a47429a719b4aae1eee72fee1c352c54b50237e7de14e834efb8981dbd16e64"
    expected_shared_depex = "96d3dcd80ec35498b71c6d2f1d0e08aab0caa5c6d8b8903d3f1d469636544f1f"
    if sha256(t860_sdcc) != expected_t860_sdcc:
        raise SystemExit("error: fixed T860 SdccDxe hash mismatch")
    if sha256(mtp_sdcc) != expected_mtp_sdcc:
        raise SystemExit("error: fixed SM8150 MTP SdccDxe hash mismatch")
    if sha256(t860_depex) != expected_shared_depex or sha256(mtp_depex) != expected_shared_depex:
        raise SystemExit("error: T860 and SM8150 MTP SdccDxe dependency expressions differ")

    before = {
        str(path.relative_to(root)): sha256(path)
        for path in (source, inf, t860_sdcc, mtp_sdcc, t860_depex, mtp_depex)
    }
    data = source.read_bytes()
    eol = b"\r\n" if b"\r\n" in data else b"\n"

    data = replace_once(
        data,
        b'#include "MsBootPolicy.h"' + eol + eol + b"#define USB_DRIVE_SECOND_CHANCE_DELAY_S",
        b'#include "MsBootPolicy.h"'
        + eol
        + b"#include <Protocol/BlockIo.h>"
        + eol
        + b"#include <Library/IoLib.h>"
        + eol
        + eol
        + b"#define USB_DRIVE_SECOND_CHANCE_DELAY_S",
        "BlockIo and read-only MMIO includes",
    )

    data = replace_once(
        data,
        b"static BOOT_SEQUENCE  mSddBootSequence[] = {"
        + eol
        + b"  MsBootHDD,"
        + eol
        + b"  MsBootDone"
        + eol
        + b"};",
        b"static BOOT_SEQUENCE  mSddBootSequence[] = {"
        + eol
        + b"  MsBootSD,"
        + eol
        + b"  MsBootDone"
        + eol
        + b"};",
        "SDD boot sequence",
    )

    ipv6_tail = (
        b"  return CheckDeviceNode (DevicePath, MESSAGING_DEVICE_PATH, MSG_IPv6_DP);"
        + eol
        + b"}"
        + eol
        + eol
        + b"BOOLEAN EFIAPI"
        + eol
        + b"FilterOnlyUSB ("
    )
    sd_filter = eol.join(
        (
            b"  return CheckDeviceNode (DevicePath, MESSAGING_DEVICE_PATH, MSG_IPv6_DP);",
            b"}",
            b"",
            b"STATIC",
            b"BOOLEAN",
            b"FileSystemHasSdMarker (",
            b"  EFI_HANDLE  Handle",
            b"  )",
            b"{",
            b"  EFI_SIMPLE_FILE_SYSTEM_PROTOCOL  *FileSystem;",
            b"  EFI_FILE_PROTOCOL                *Root;",
            b"  EFI_FILE_PROTOCOL                *Marker;",
            b"  EFI_STATUS                       Status;",
            b"",
            b"  Root   = NULL;",
            b"  Marker = NULL;",
            b"  Status = gBS->HandleProtocol (",
            b"                  Handle,",
            b"                  &gEfiSimpleFileSystemProtocolGuid,",
            b"                  (VOID **)&FileSystem",
            b"                  );",
            b"  if (EFI_ERROR (Status)) {",
            b"    return FALSE;",
            b"  }",
            b"",
            b"  Status = FileSystem->OpenVolume (FileSystem, &Root);",
            b"  if (EFI_ERROR (Status) || (Root == NULL)) {",
            b"    return FALSE;",
            b"  }",
            b"",
            b"  Status = Root->Open (",
            b"                   Root,",
            b"                   &Marker,",
            b"                   L\"\\\\startup.nsh\",",
            b"                   EFI_FILE_MODE_READ,",
            b"                   0",
            b"                   );",
            b"  if (Marker != NULL) {",
            b"    Marker->Close (Marker);",
            b"  }",
            b"",
            b"  Root->Close (Root);",
            b"  return !EFI_ERROR (Status);",
            b"}",
            b"",
            b"STATIC",
            b"UINT64",
            b"BlockIoSizeMiB (",
            b"  EFI_BLOCK_IO_PROTOCOL  *BlockIo",
            b"  )",
            b"{",
            b"  if ((BlockIo == NULL) || (BlockIo->Media == NULL)) {",
            b"    return 0;",
            b"  }",
            b"",
            b"  return MultU64x32 (BlockIo->Media->LastBlock + 1, BlockIo->Media->BlockSize) / (1024 * 1024);",
            b"}",
            b"",
            b"STATIC",
            b"VOID",
            b"PrintHandleDevicePath (",
            b"  EFI_HANDLE  Handle",
            b"  )",
            b"{",
            b"  CHAR16  *Text;",
            b"",
            b"  Text = ConvertDevicePathToText (DevicePathFromHandle (Handle), TRUE, TRUE);",
            b"  if (Text == NULL) {",
            b"    Print (L\"    device-path: unavailable\\r\\n\");",
            b"    return;",
            b"  }",
            b"",
            b"  Print (L\"    %s\\r\\n\", Text);",
            b"  FreePool (Text);",
            b"}",
            b"",
            b"STATIC",
            b"VOID",
            b"DiagnoseSdcc2Hardware (",
            b"  VOID",
            b"  )",
            b"{",
            b"  UINT32  CardDetectCtl;",
            b"  UINT32  CardDetectIo;",
            b"  UINT32  ClockAppsCbcr;",
            b"  UINT32  ClockAhbCbcr;",
            b"  UINT32  ClockCmdRcgr;",
            b"  UINT32  ClockCfgRcgr;",
            b"  UINT32  PresentState;",
            b"  UINT32  HostPower;",
            b"  UINT32  ClockReset;",
            b"  UINT32  InterruptStatus;",
            b"  UINT32  Capabilities0;",
            b"  UINT32  Capabilities1;",
            b"  UINT16  HostVersion;",
            b"",
            b"  // SM-T860 Android DTS: SDHCI2=0x08804000 and active-low card detect=TLMM GPIO96.",
            b"  // These are read-only diagnostics. No GPIO, clock, regulator, or controller register is written.",
            b"  CardDetectCtl  = MmioRead32 (0x03960000);",
            b"  CardDetectIo   = MmioRead32 (0x03960004);",
            b"  ClockAppsCbcr  = MmioRead32 (0x00114004);",
            b"  ClockAhbCbcr   = MmioRead32 (0x00114008);",
            b"  ClockCmdRcgr   = MmioRead32 (0x0011400C);",
            b"  ClockCfgRcgr   = MmioRead32 (0x00114010);",
            b"  PresentState   = MmioRead32 (0x08804024);",
            b"  HostPower      = MmioRead32 (0x08804028);",
            b"  ClockReset     = MmioRead32 (0x0880402C);",
            b"  InterruptStatus = MmioRead32 (0x08804030);",
            b"  Capabilities0  = MmioRead32 (0x08804040);",
            b"  Capabilities1  = MmioRead32 (0x08804044);",
            b"  HostVersion    = MmioRead16 (0x088040FE);",
            b"",
            b"  Print (L\"SDCC2 read-only register diagnostic:\\r\\n\");",
            b"  Print (",
            b"    L\" GPIO96 CTL=%08x IO=%08x inserted(active-low)=%d\\r\\n\",",
            b"    CardDetectCtl,",
            b"    CardDetectIo,",
            b"    ((CardDetectIo & BIT0) == 0)",
            b"    );",
            b"  Print (",
            b"    L\" GCC apps=%08x ahb=%08x cmd=%08x cfg=%08x\\r\\n\",",
            b"    ClockAppsCbcr,",
            b"    ClockAhbCbcr,",
            b"    ClockCmdRcgr,",
            b"    ClockCfgRcgr",
            b"    );",
            b"  Print (",
            b"    L\" SDHCI present=%08x host/pwr=%08x clk/rst=%08x int=%08x\\r\\n\",",
            b"    PresentState,",
            b"    HostPower,",
            b"    ClockReset,",
            b"    InterruptStatus",
            b"    );",
            b"  Print (",
            b"    L\" SDHCI caps=%08x/%08x version=%04x\\r\\n\",",
            b"    Capabilities0,",
            b"    Capabilities1,",
            b"    HostVersion",
            b"    );",
            b"}",
            b"",
            b"STATIC",
            b"VOID",
            b"DiagnoseStorageHandles (",
            b"  VOID",
            b"  )",
            b"{",
            b"  EFI_STATUS             Status;",
            b"  EFI_HANDLE             *Handles;",
            b"  EFI_BLOCK_IO_PROTOCOL  *BlockIo;",
            b"  UINTN                  HandleCount;",
            b"  UINTN                  Index;",
            b"  UINTN                  CandidateCount;",
            b"  UINT64                 SizeMiB;",
            b"  BOOLEAN                Marker;",
            b"",
            b"  Handles     = NULL;",
            b"  HandleCount = 0;",
            b"  Status = gBS->LocateHandleBuffer (",
            b"                  ByProtocol,",
            b"                  &gEfiSimpleFileSystemProtocolGuid,",
            b"                  NULL,",
            b"                  &HandleCount,",
            b"                  &Handles",
            b"                  );",
            b"  Print (L\"SimpleFS: %u handle(s), status=%r\\r\\n\", HandleCount, Status);",
            b"  if (Handles != NULL) {",
            b"    for (Index = 0; Index < HandleCount; Index++) {",
            b"      Marker = FileSystemHasSdMarker (Handles[Index]);",
            b"      Status = gBS->HandleProtocol (",
            b"                      Handles[Index],",
            b"                      &gEfiBlockIoProtocolGuid,",
            b"                      (VOID **)&BlockIo",
            b"                      );",
            b"      if (EFI_ERROR (Status) || (BlockIo->Media == NULL)) {",
            b"        Print (L\" SFS%u marker=%d BlockIO=none\\r\\n\", Index, Marker);",
            b"        continue;",
            b"      }",
            b"",
            b"      Print (",
            b"        L\" SFS%u marker=%d media=%d rem=%d logical=%d size=%LuMiB\\r\\n\",",
            b"        Index,",
            b"        Marker,",
            b"        BlockIo->Media->MediaPresent,",
            b"        BlockIo->Media->RemovableMedia,",
            b"        BlockIo->Media->LogicalPartition,",
            b"        BlockIoSizeMiB (BlockIo)",
            b"        );",
            b"    }",
            b"",
            b"    FreePool (Handles);",
            b"  }",
            b"",
            b"  Handles        = NULL;",
            b"  HandleCount    = 0;",
            b"  CandidateCount = 0;",
            b"  Status = gBS->LocateHandleBuffer (",
            b"                  ByProtocol,",
            b"                  &gEfiBlockIoProtocolGuid,",
            b"                  NULL,",
            b"                  &HandleCount,",
            b"                  &Handles",
            b"                  );",
            b"  if (Handles != NULL) {",
            b"    for (Index = 0; Index < HandleCount; Index++) {",
            b"      Status = gBS->HandleProtocol (",
            b"                      Handles[Index],",
            b"                      &gEfiBlockIoProtocolGuid,",
            b"                      (VOID **)&BlockIo",
            b"                      );",
            b"      if (EFI_ERROR (Status) || (BlockIo->Media == NULL) || !BlockIo->Media->MediaPresent) {",
            b"        continue;",
            b"      }",
            b"",
            b"      SizeMiB = BlockIoSizeMiB (BlockIo);",
            b"      if (BlockIo->Media->RemovableMedia || ((SizeMiB >= 24000) && (SizeMiB <= 40000))) {",
            b"        CandidateCount++;",
            b"      }",
            b"    }",
            b"  }",
            b"",
            b"  Print (L\"BlockIO: %u total, %u removable/24-40GiB candidate(s)\\r\\n\", HandleCount, CandidateCount);",
            b"  if (Handles != NULL) {",
            b"    for (Index = 0; Index < HandleCount; Index++) {",
            b"      Status = gBS->HandleProtocol (",
            b"                      Handles[Index],",
            b"                      &gEfiBlockIoProtocolGuid,",
            b"                      (VOID **)&BlockIo",
            b"                      );",
            b"      if (EFI_ERROR (Status) || (BlockIo->Media == NULL) || !BlockIo->Media->MediaPresent) {",
            b"        continue;",
            b"      }",
            b"",
            b"      SizeMiB = BlockIoSizeMiB (BlockIo);",
            b"      if (!BlockIo->Media->RemovableMedia && ((SizeMiB < 24000) || (SizeMiB > 40000))) {",
            b"        continue;",
            b"      }",
            b"",
            b"      Print (",
            b"        L\" BIO%u rem=%d logical=%d block=%u size=%LuMiB\\r\\n\",",
            b"        Index,",
            b"        BlockIo->Media->RemovableMedia,",
            b"        BlockIo->Media->LogicalPartition,",
            b"        BlockIo->Media->BlockSize,",
            b"        SizeMiB",
            b"        );",
            b"      PrintHandleDevicePath (Handles[Index]);",
            b"    }",
            b"",
            b"    FreePool (Handles);",
            b"  }",
            b"}",
            b"",
            b"STATIC",
            b"VOID",
            b"FilterMarkedFileSystems (",
            b"  EFI_HANDLE  *HandleBuffer,",
            b"  UINTN       *HandleCount",
            b"  )",
            b"{",
            b"  UINTN  Index;",
            b"",
            b"  for (Index = 0; Index < *HandleCount;) {",
            b"    if (!FileSystemHasSdMarker (HandleBuffer[Index])) {",
            b"      (*HandleCount)--;",
            b"      CopyMem (",
            b"        &HandleBuffer[Index],",
            b"        &HandleBuffer[Index + 1],",
            b"        (*HandleCount - Index) * sizeof (EFI_HANDLE)",
            b"        );",
            b"      continue;",
            b"    }",
            b"",
            b"    Index++;",
            b"  }",
            b"}",
            b"",
            b"BOOLEAN EFIAPI",
            b"FilterOnlySD (",
            b"  EFI_DEVICE_PATH_PROTOCOL  *DevicePath",
            b"  )",
            b"{",
            b"  return (DevicePath != NULL);",
            b"}",
            b"",
            b"BOOLEAN EFIAPI",
            b"FilterOnlyUSB (",
        )
    )
    data = replace_once(data, ipv6_tail, sd_filter, "SD device-path filter")

    data = replace_once(
        data,
        b"  FilterHandles (Handles, &HandleCount, ByFilter);" + eol,
        eol.join(
            (
                b"  if (ByFilter == FilterOnlySD) {",
                b"    Print (L\"\\r\\nT860 SD probe: %u SimpleFS handle(s)\\r\\n\", HandleCount);",
                b"    FilterMarkedFileSystems (Handles, &HandleCount);",
                b"    Print (L\"T860 SD probe: %u startup.nsh marker(s)\\r\\n\", HandleCount);",
                b"  } else {",
                b"    FilterHandles (Handles, &HandleCount, ByFilter);",
                b"  }",
            )
        ) + eol,
        "marker-aware filesystem filtering",
    )

    hdd_case = b"      case MsBootHDD:" + eol
    sd_case = eol.join(
        (
            b"      case MsBootSD:",
            b"        GraphicStatus = SetGraphicsConsoleMode (GCM_NATIVE_RES);",
            b"        if (EFI_ERROR (GraphicStatus) != FALSE) {",
            b'          DEBUG ((DEBUG_ERROR, "%a Unable to set console mode - %r\\n", __FUNCTION__, GraphicStatus));',
            b"        }",
            b"",
            b"        Print (L\"\\r\\nT860 SM8150 MTP SDCC DRIVER A/B DIAGNOSTIC\\r\\n\");",
            b"        Print (L\"Looking for \\\\startup.nsh; internal UFS fallback is disabled.\\r\\n\");",
            b"        DiagnoseSdcc2Hardware ();",
            b"        DiagnoseStorageHandles ();",
            b"        Status = SelectAndBootDevice (&gEfiSimpleFileSystemProtocolGuid, FilterOnlySD);",
            b"        Print (L\"\\r\\nSD boot did not transfer control: %r\\r\\n\", Status);",
            b"        Print (L\"Diagnostic stopped. Hold Power + Volume Down to reboot.\\r\\n\");",
            b"        while (TRUE) {",
            b"          gBS->Stall (1000 * 1000);",
            b"        }",
            b"      case MsBootHDD:",
        )
    ) + eol
    data = replace_once(data, hdd_case, sd_case, "SD boot case")
    source.write_bytes(data)

    inf_data = inf.read_bytes()
    inf_eol = b"\r\n" if b"\r\n" in inf_data else b"\n"
    inf_data = replace_once(
        inf_data,
        b"[LibraryClasses]" + inf_eol + b"  DevicePathLib",
        b"[LibraryClasses]"
        + inf_eol
        + b"  IoLib"
        + inf_eol
        + b"  DevicePathLib",
        "IoLib dependency",
    )
    inf_data = replace_once(
        inf_data,
        b"[Protocols]" + inf_eol + b"  gEfiSimpleFileSystemProtocolGuid",
        b"[Protocols]"
        + inf_eol
        + b"  gEfiBlockIoProtocolGuid"
        + inf_eol
        + b"  gEfiSimpleFileSystemProtocolGuid",
        "BlockIo protocol dependency",
    )
    inf.write_bytes(inf_data)
    t860_sdcc.write_bytes(mtp_sdcc.read_bytes())

    after = {
        str(path.relative_to(root)): sha256(path)
        for path in (source, inf, t860_sdcc, mtp_sdcc, t860_depex, mtp_depex)
    }
    if sha256(t860_sdcc) != expected_mtp_sdcc:
        raise SystemExit("error: staged T860 SdccDxe does not match fixed SM8150 MTP binary")
    report = {
        "schema": 1,
        "profile": "project-aloha-2412.74-sm8150-mtp-sdcc-ab-diagnostic",
        "purpose": "replace only the T860 SdccDxe with the fixed SM8150 MTP binary, read diagnostic registers, enumerate storage, then boot only a root startup.nsh volume",
        "sdcc_driver_replacement": {
            "original_path": str(t860_sdcc.relative_to(root)),
            "original_sha256": expected_t860_sdcc,
            "replacement_path": str(mtp_sdcc.relative_to(root)),
            "replacement_sha256": expected_mtp_sdcc,
            "staged_sha256": sha256(t860_sdcc),
            "shared_depex_sha256": expected_shared_depex,
        },
        "mmio_reads": {
            "gcc_sdcc2": ["0x00114004", "0x00114008", "0x0011400c", "0x00114010"],
            "sdhci2": [
                "0x08804024",
                "0x08804028",
                "0x0880402c",
                "0x08804030",
                "0x08804040",
                "0x08804044",
                "0x088040fe",
            ],
            "tlmm_gpio96": ["0x03960000", "0x03960004"],
        },
        "diagnostic_patch_mmio_writes": [],
        "files_before": before,
        "files_after": after,
        "device_writes_performed": False,
        "deployable": False,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
