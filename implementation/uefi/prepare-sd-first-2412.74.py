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

    after = {str(path.relative_to(root)): sha256(path) for path in (source, inf)}
    report = {
        "schema": 1,
        "profile": "project-aloha-2412.74-sd-marker-diagnostic",
        "purpose": "boot only a SimpleFS volume containing root startup.nsh and visibly stop on failure",
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
