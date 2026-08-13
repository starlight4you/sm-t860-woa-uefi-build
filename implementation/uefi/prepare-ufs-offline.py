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
FDF = Path("Platforms/SurfaceDuo1Pkg/SurfaceDuo1.fdf")
BOOTPACK = DEVICE / "bootpack.json"
ACPI_INCLUDE = "!include SurfaceDuo1Pkg/Include/ACPI.inc"
COMPRESSED_FV_MARKER = "[FV.FvMain]"
COMPACT_FV_MARKER = "[FV.FVMAIN_COMPACT]"
INNER_FV_MARKER = "  FILE FV_IMAGE = 9E21FD93-9C72-4c15-8C4B-E77F1DB2D792"


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

# The stock FDF puts ACPI in FVMAIN, which is LZMA-compressed inside
# FVMAIN_COMPACT. Keep the ACPI freeform file in the outer FV so the exact
# safety DSDT can be independently found and hashed in the final FD.
fdf = root / FDF
if not fdf.is_file():
    raise SystemExit(f"UFS-offline preparation failed: missing {fdf}")
fdf_text = fdf.read_text(encoding="utf-8")
active_acpi_includes = [
    line
    for line in fdf_text.splitlines()
    if line.strip() == ACPI_INCLUDE
]
if len(active_acpi_includes) != 1:
    raise SystemExit(
        "UFS-offline preparation failed: expected exactly one active ACPI include"
    )
compressed_index = fdf_text.index(COMPRESSED_FV_MARKER)
compact_index = fdf_text.index(COMPACT_FV_MARKER)
include_index = fdf_text.index(f"  {ACPI_INCLUDE}\n")
inner_fv_index = fdf_text.index(INNER_FV_MARKER, compact_index)
if not compressed_index < include_index < compact_index < inner_fv_index:
    raise SystemExit(
        "UFS-offline preparation failed: unexpected SurfaceDuo1 FDF layout"
    )
fdf_text = fdf_text.replace(
    f"  {ACPI_INCLUDE}\n",
    "  # T860_UFS_OFFLINE: ACPI moved to the uncompressed outer FV\n",
    1,
)
compact_index = fdf_text.index(COMPACT_FV_MARKER)
inner_fv_index = fdf_text.index(INNER_FV_MARKER, compact_index)
outer_include = (
    "  # T860_UFS_OFFLINE: exact safety ACPI remains independently verifiable\n"
    f"  {ACPI_INCLUDE}\n\n"
)
fdf_text = fdf_text[:inner_fv_index] + outer_include + fdf_text[inner_fv_index:]
fdf.write_text(fdf_text, encoding="utf-8")

# Keep the boot payload uncompressed so the boot image contains the exact FD
# once. This device-local override avoids changing every SM8150 target.
bootpack = root / BOOTPACK
if bootpack.exists():
    raise SystemExit(
        f"UFS-offline preparation failed: review unexpected existing {bootpack}"
    )
bootpack.write_text(
    json.dumps({"default_aboot_args": {"kernel_compressed": False}}, indent=2)
    + "\n",
    encoding="utf-8",
)

report["firmware_layout"] = {
    "fdf": str(FDF),
    "acpi_source_fv": "FVMAIN",
    "acpi_target_fv": "FVMAIN_COMPACT",
    "acpi_outer_fv_uncompressed": True,
    "bootpack": str(BOOTPACK),
    "kernel_compressed": False,
}

report["status"] = "pass-ufs-offline-source-preparation"
if args.report:
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report, indent=2))
