#!/usr/bin/env python3
"""Patch Project Aloha 2412.74 to boot a marker-identified microSD only."""

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
    for path in (source, inf):
        if not path.is_file() or path.is_symlink():
            raise SystemExit(f"error: missing regular source file: {path}")

    before = {str(path.relative_to(root)): sha256(path) for path in (source, inf)}
    data = source.read_bytes()
    eol = b"\r\n" if b"\r\n" in data else b"\n"

    data = replace_once(
        data,
        b'#include "MsBootPolicy.h"' + eol + eol + b"#define USB_DRIVE_SECOND_CHANCE_DELAY_S",
        b'#include "MsBootPolicy.h"'
        + eol
        + b"#include <Protocol/BlockIo.h>"
        + eol
        + eol
        + b"#define USB_DRIVE_SECOND_CHANCE_DELAY_S",
        "BlockIo protocol include",
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
            b"        Print (L\"\\r\\nT860 MICROSD MARKER BOOT DIAGNOSTIC\\r\\n\");",
            b"        Print (L\"Looking for \\\\startup.nsh; internal UFS fallback is disabled.\\r\\n\");",
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
        b"[Protocols]" + inf_eol + b"  gEfiSimpleFileSystemProtocolGuid",
        b"[Protocols]"
        + inf_eol
        + b"  gEfiBlockIoProtocolGuid"
        + inf_eol
        + b"  gEfiSimpleFileSystemProtocolGuid",
        "BlockIo protocol dependency",
    )
    inf.write_bytes(inf_data)

    after = {str(path.relative_to(root)): sha256(path) for path in (source, inf)}
    report = {
        "schema": 1,
        "profile": "project-aloha-2412.74-sd-blockio-diagnostic",
        "purpose": "enumerate SimpleFS and candidate BlockIO media, then boot only a root startup.nsh volume",
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
