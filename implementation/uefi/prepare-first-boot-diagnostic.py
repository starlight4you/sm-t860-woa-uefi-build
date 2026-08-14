#!/usr/bin/env python3
"""Prepare a reversible, observable SM-T860 first-boot diagnostic build.

This only edits the disposable upstream build tree.  It keeps the upstream
compressed FV/Android boot-payload layout, disables all UFS bring-up knobs,
enables framebuffer serial output, and removes watchdog drivers so a stall is
visible instead of immediately resetting the tablet into Download mode.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


DEVICE = Path("Platforms/SurfaceDuo1Pkg/Device/samsung-gts6lwifi")
PLATFORM_DSCS = (
    Path("Platforms/SurfaceDuo1Pkg/SurfaceDuo1.dsc"),
    Path("Platforms/SurfaceDuo1Pkg/SurfaceDuo1NoSb.dsc"),
)
PLATFORM_FDF = Path("Platforms/SurfaceDuo1Pkg/SurfaceDuo1.fdf")
CONFIG_MAP = DEVICE / "Library/PlatformConfigurationMapLib/PlatformConfigurationMapLib.c"
BOOTPACK = DEVICE / "bootpack.json"
DEVICE_FILES = ("APRIORI.inc", "DXE.inc", "DXE.dsc.inc")
UFS_INF = (
    "SurfaceDuo1Pkg/Device/$(TARGET_DEVICE)/Binaries/"
    "QcomPkg/Drivers/UFSDxe/UFSDxe.inf"
)
SDCC_INF = (
    "SurfaceDuo1Pkg/Device/$(TARGET_DEVICE)/Binaries/"
    "QcomPkg/Drivers/SdccDxe/SdccDxe.inf"
)
QCOM_WDOG_INF = (
    "SurfaceDuo1Pkg/Device/$(TARGET_DEVICE)/Binaries/"
    "QcomPkg/Drivers/QcomWDogDxe/QcomWDogDxe.inf"
)
UEFI_WDOG_INF = "MdeModulePkg/Universal/WatchdogTimerDxe/WatchdogTimer.inf"


def active_inf(line: str, inf: str) -> bool:
    stripped = line.strip()
    if not stripped or stripped.startswith(("#", ";")):
        return False
    return stripped in {inf, f"INF {inf}"}


def disable_inf(path: Path, inf: str, marker: str, expected: int) -> int:
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    matches = [index for index, line in enumerate(lines) if active_inf(line, inf)]
    if len(matches) != expected:
        raise SystemExit(
            f"diagnostic preparation failed: expected {expected} active {inf} "
            f"entry/entries in {path}, found {len(matches)}"
        )
    for index in matches:
        indentation = lines[index][: len(lines[index]) - len(lines[index].lstrip())]
        lines[index] = f"{indentation}# T860_DIAGNOSTIC_{marker}: {inf}\n"
    path.write_text("".join(lines), encoding="utf-8")
    if any(active_inf(line, inf) for line in path.read_text(encoding="utf-8").splitlines()):
        raise SystemExit(f"diagnostic preparation failed: {inf} remains active in {path}")
    return len(matches)


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise SystemExit(
            f"diagnostic preparation failed: expected one {label} marker in {path}, "
            f"found {text.count(old)}"
        )
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


parser = argparse.ArgumentParser()
parser.add_argument("source_tree", type=Path)
parser.add_argument("--report", type=Path)
args = parser.parse_args()

root = args.source_tree.resolve()
device = root / DEVICE
if not device.is_dir():
    raise SystemExit(f"diagnostic preparation failed: missing {device}")
if (root / BOOTPACK).exists():
    raise SystemExit(
        "diagnostic preparation failed: unexpected device bootpack override; "
        "the diagnostic build must retain the upstream gzip payload"
    )

report: dict[str, object] = {
    "schema": 1,
    "profile": "gts6lwifi-first-boot-diagnostic",
    "source_tree": str(root),
    "files": {},
}

for relative in DEVICE_FILES:
    path = device / relative
    if not path.is_file():
        raise SystemExit(f"diagnostic preparation failed: missing {path}")
    before = path.read_text(encoding="utf-8").splitlines()
    sdcc_count = sum(active_inf(line, SDCC_INF) for line in before)
    if sdcc_count < 1:
        raise SystemExit(f"diagnostic preparation failed: SdccDxe absent in {path}")
    ufs_removed = disable_inf(path, UFS_INF, "NO_UFS", 1)
    qcom_wdog_removed = disable_inf(path, QCOM_WDOG_INF, "NO_QCOM_WDOG", 1)
    report["files"][relative] = {
        "ufs_removed": ufs_removed,
        "qcom_watchdog_removed": qcom_wdog_removed,
        "sdcc_active_after": sdcc_count,
    }

apriori = device / "APRIORI.inc"
fdf = root / PLATFORM_FDF
if not fdf.is_file():
    raise SystemExit(f"diagnostic preparation failed: missing {fdf}")
generic_watchdog_removed = {
    "APRIORI.inc": disable_inf(apriori, UEFI_WDOG_INF, "NO_UEFI_WDOG", 1),
    str(PLATFORM_FDF): disable_inf(fdf, UEFI_WDOG_INF, "NO_UEFI_WDOG", 1),
}

for relative in PLATFORM_DSCS:
    replace_once(
        root / relative,
        "  USE_SCREEN_FOR_SERIAL_OUTPUT    = 0\n",
        "  USE_SCREEN_FOR_SERIAL_OUTPUT    = 1\n",
        f"screen serial setting in {relative.name}",
    )

config_map = root / CONFIG_MAP
replace_once(
    config_map,
    '    {"EnableUfsIOC", 1},\n',
    '    {"EnableUfsIOC", 0}, /* T860 diagnostic: do not initialize UFS IOC */\n',
    "EnableUfsIOC setting",
)
replace_once(
    config_map,
    '    {"UfsSmmuConfigForOtherBootDev", 1},\n',
    '    {"UfsSmmuConfigForOtherBootDev", 0}, /* T860 diagnostic: no UFS SMMU */\n',
    "UfsSmmuConfigForOtherBootDev setting",
)

report["diagnostic_controls"] = {
    "screen_serial_output": True,
    "screen_serial_platform_descriptors": [str(path) for path in PLATFORM_DSCS],
    "memory_serial_output": False,
    "ufs_driver_present": False,
    "enable_ufs_ioc": 0,
    "ufs_smmu_config_for_other_boot_device": 0,
    "qcom_hardware_watchdog_present": False,
    "uefi_watchdog_timer_present": False,
    "generic_watchdog_removed": generic_watchdog_removed,
    "upstream_fv_layout_preserved": True,
    "upstream_gzip_boot_payload_preserved": True,
}
report["expected_behavior"] = (
    "Framebuffer DEBUG output remains visible. A firmware stall may require a manual "
    "long-press reboot because watchdog reset paths are intentionally absent."
)
report["status"] = "pass-first-boot-diagnostic-source-preparation"

if args.report:
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report, indent=2))
