#!/usr/bin/env python3
"""Patch an exact Project Aloha 2412.74 build tree to try microSD first."""

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
        + eol
        + b"#include <Library/MsPlatformDevicesLib.h>"
        + eol
        + eol
        + b"#define USB_DRIVE_SECOND_CHANCE_DELAY_S",
        "platform-devices include",
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
        + b"  MsBootHDD,"
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
            b"BOOLEAN EFIAPI",
            b"IsDevicePathSD (",
            b"  EFI_DEVICE_PATH_PROTOCOL  *DevicePath",
            b"  )",
            b"{",
            b"  EFI_DEVICE_PATH_PROTOCOL  *SdCardDevicePath;",
            b"  UINTN                     DevicePathSize;",
            b"  UINTN                     SdCardDevicePathSize;",
            b"",
            b"  if ((DevicePath == NULL) || !IsDevicePathValid (DevicePath, 0)) {",
            b"    return FALSE;",
            b"  }",
            b"",
            b"  SdCardDevicePath = GetSdCardDevicePath ();",
            b"  if ((SdCardDevicePath == NULL) || !IsDevicePathValid (SdCardDevicePath, 0)) {",
            b"    return FALSE;",
            b"  }",
            b"",
            b"  DevicePathSize       = GetDevicePathSize (DevicePath);",
            b"  SdCardDevicePathSize = GetDevicePathSize (SdCardDevicePath);",
            b"  if ((SdCardDevicePathSize <= END_DEVICE_PATH_LENGTH) ||",
            b"      (DevicePathSize <= SdCardDevicePathSize))",
            b"  {",
            b"    return FALSE;",
            b"  }",
            b"",
            b"  return (CompareMem (",
            b"            DevicePath,",
            b"            SdCardDevicePath,",
            b"            SdCardDevicePathSize - END_DEVICE_PATH_LENGTH",
            b"            ) == 0);",
            b"}",
            b"",
            b"BOOLEAN EFIAPI",
            b"FilterOnlySD (",
            b"  EFI_DEVICE_PATH_PROTOCOL  *DevicePath",
            b"  )",
            b"{",
            b"  return IsDevicePathSD (DevicePath);",
            b"}",
            b"",
            b"BOOLEAN EFIAPI",
            b"FilterOnlyUSB (",
        )
    )
    data = replace_once(data, ipv6_tail, sd_filter, "SD device-path filter")

    hdd_case = b"      case MsBootHDD:" + eol
    sd_case = eol.join(
        (
            b"      case MsBootSD:",
            b"        GraphicStatus = SetGraphicsConsoleMode (GCM_NATIVE_RES);",
            b"        if (EFI_ERROR (GraphicStatus) != FALSE) {",
            b'          DEBUG ((DEBUG_ERROR, "%a Unable to set console mode - %r\\n", __FUNCTION__, GraphicStatus));',
            b"        }",
            b"",
            b"        Status = SelectAndBootDevice (&gEfiSimpleFileSystemProtocolGuid, FilterOnlySD);",
            b"        break;",
            b"      case MsBootHDD:",
        )
    ) + eol
    data = replace_once(data, hdd_case, sd_case, "SD boot case")
    source.write_bytes(data)

    inf_data = inf.read_bytes()
    inf_eol = b"\r\n" if b"\r\n" in inf_data else b"\n"
    inf_data = replace_once(
        inf_data,
        b"  MsBootPolicyLib" + inf_eol + b"  UefiBootManagerLib",
        b"  MsBootPolicyLib"
        + inf_eol
        + b"  MsPlatformDevicesLib"
        + inf_eol
        + b"  UefiBootManagerLib",
        "MsPlatformDevicesLib dependency",
    )
    inf.write_bytes(inf_data)

    after = {str(path.relative_to(root)): sha256(path) for path in (source, inf)}
    report = {
        "schema": 1,
        "profile": "project-aloha-2412.74-sd-first",
        "purpose": "try the exact microSD device path before internal non-USB storage",
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
