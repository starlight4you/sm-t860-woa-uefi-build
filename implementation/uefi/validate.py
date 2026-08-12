#!/usr/bin/env python3
"""Validate T860 AML and its mu_aloha_platforms integration path."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


WORKSPACE = Path(__file__).resolve().parents[2]
AML = WORKSPACE / "implementation/build/acpi/DSDT.aml"
UEFI = WORKSPACE / "research/repos/mu_aloha_platforms"
ACPI_INCLUDE = UEFI / "Platforms/SurfaceDuo1Pkg/Include/ACPI.inc"
REFERENCE_AML = (
    UEFI
    / "Platforms/SurfaceDuo1Pkg/Device/samsung-gts6lwifi/ACPI/DSDT.aml"
)
OUTPUT = WORKSPACE / "implementation/build/uefi/integration-validation.json"
EXPECTED_REFERENCE_SHA256 = (
    "a710f7a40002babe7f3c7de78093fffa6dd2c5078a19d3a3c7a76b0d0e72c698"
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def artifact_record(path: Path, needle: bytes | None = None) -> dict[str, object]:
    data = path.read_bytes()
    try:
        display_path = str(path.relative_to(WORKSPACE))
    except ValueError:
        display_path = str(path)
    record: dict[str, object] = {
        "path": display_path,
        "bytes": len(data),
        "sha256": sha256_bytes(data),
    }
    if needle is not None:
        record["embedded_aml_occurrences"] = data.count(needle)
        if data.count(needle) < 1:
            raise SystemExit(f"validation failed: exact DSDT AML not embedded in {path}")
    return record


parser = argparse.ArgumentParser()
parser.add_argument("--firmware", type=Path)
parser.add_argument("--boot-image", type=Path)
args = parser.parse_args()

for required in (AML, ACPI_INCLUDE, REFERENCE_AML):
    if not required.is_file():
        raise SystemExit(f"validation failed: missing {required}")

aml = AML.read_bytes()
if aml[:4] != b"DSDT":
    raise SystemExit("validation failed: AML does not start with a DSDT signature")
declared_length = int.from_bytes(aml[4:8], byteorder="little")
if declared_length != len(aml):
    raise SystemExit(
        f"validation failed: DSDT header length {declared_length} != {len(aml)}"
    )
if sum(aml) % 256 != 0:
    raise SystemExit("validation failed: DSDT checksum is not zero modulo 256")

reference_hash = sha256_bytes(REFERENCE_AML.read_bytes())
if reference_hash != EXPECTED_REFERENCE_SHA256:
    raise SystemExit(
        "validation failed: upstream T860 reference AML changed; review before integration"
    )

include_text = ACPI_INCLUDE.read_text(encoding="utf-8")
include_line = (
    "SECTION RAW = "
    "SurfaceDuo1Pkg/Device/$(TARGET_DEVICE)/ACPI/DSDT.aml"
)
if include_line not in include_text:
    raise SystemExit("validation failed: device DSDT is not selected by ACPI.inc")

result: dict[str, object] = {
    "schema": 1,
    "validated_at_utc": datetime.now(timezone.utc).isoformat(),
    "device": "samsung-gts6lwifi",
    "status": "pass-integration-preflight",
    "deployable": False,
    "aml": artifact_record(AML),
    "reference_aml_sha256": reference_hash,
    "fdf_device_dsdt_include": include_line,
    "host_build_required": "Linux x86_64, Python >= 3.12",
    "device_writes_performed": False,
}

if args.firmware is not None:
    firmware = args.firmware.resolve()
    if not firmware.is_file():
        raise SystemExit(f"validation failed: firmware artifact missing: {firmware}")
    result["firmware"] = artifact_record(firmware, aml)

if args.boot_image is not None:
    boot_image = args.boot_image.resolve()
    if not boot_image.is_file():
        raise SystemExit(f"validation failed: boot image missing: {boot_image}")
    result["boot_image"] = artifact_record(boot_image, aml)

if args.firmware is not None and args.boot_image is not None:
    result["status"] = "pass-offline-uefi-build"

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
OUTPUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
print(json.dumps(result, indent=2))
