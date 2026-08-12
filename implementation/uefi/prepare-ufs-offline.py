#!/usr/bin/env python3
"""Patch a temporary mu_aloha_platforms tree for UFS-offline T860 builds."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


DEVICE = Path("Platforms/SurfaceDuo1Pkg/Device/samsung-gts6lwifi")
UFS_INF = (
    "SurfaceDuo1Pkg/Device/$(TARGET_DEVICE)/Binaries/"
    "QcomPkg/Drivers/UFSDxe/UFSDxe.inf"
)
SDCC_INF = (
    "SurfaceDuo1Pkg/Device/$(TARGET_DEVICE)/Binaries/"
    "QcomPkg/Drivers/SdccDxe/SdccDxe.inf"
)
EFFECTIVE_FILES = ("APRIORI.inc", "DXE.inc", "DXE.dsc.inc")


def is_active_inf(line: str, inf: str) -> bool:
    stripped = line.strip()
    if not stripped or stripped.startswith(("#", ";")):
        return False
    return stripped == f"INF {inf}" or stripped == inf


parser = argparse.ArgumentParser()
parser.add_argument("source_tree", type=Path)
parser.add_argument("--report", type=Path)
args = parser.parse_args()

root = args.source_tree.resolve()
device = root / DEVICE
if not device.is_dir():
    raise SystemExit(f"UFS-offline preparation failed: missing {device}")

report: dict[str, object] = {
    "schema": 1,
    "profile": "gts6lwifi-ufs-offline",
    "source_tree": str(root),
    "files": {},
}

for relative in EFFECTIVE_FILES:
    path = device / relative
    if not path.is_file():
        raise SystemExit(f"UFS-offline preparation failed: missing {path}")
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    active_ufs = [index for index, line in enumerate(lines) if is_active_inf(line, UFS_INF)]
    active_sdcc = [index for index, line in enumerate(lines) if is_active_inf(line, SDCC_INF)]
    if len(active_ufs) != 1:
        raise SystemExit(
            f"UFS-offline preparation failed: expected one active UFSDxe entry in "
            f"{path}, found {len(active_ufs)}"
        )
    if not active_sdcc:
        raise SystemExit(
            f"UFS-offline preparation failed: removable SDCC entry absent in {path}"
        )
    index = active_ufs[0]
    indentation = lines[index][: len(lines[index]) - len(lines[index].lstrip())]
    lines[index] = f"{indentation}# T860_UFS_OFFLINE: UFSDxe intentionally excluded\n"
    path.write_text("".join(lines), encoding="utf-8")

    rewritten = path.read_text(encoding="utf-8").splitlines()
    if any(is_active_inf(line, UFS_INF) for line in rewritten):
        raise SystemExit(f"UFS-offline preparation failed: UFSDxe still active in {path}")
    report["files"][relative] = {
        "active_ufs_before": 1,
        "active_ufs_after": 0,
        "active_sdcc_after": sum(is_active_inf(line, SDCC_INF) for line in rewritten),
    }

report["status"] = "pass-ufs-offline-source-preparation"
if args.report:
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report, indent=2))
