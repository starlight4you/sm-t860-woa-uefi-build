#!/usr/bin/env python3
"""Aggregate offline evidence for a recoverable SM-T860 WoA first boot.

The program reads local artifacts and validation reports only.  It never calls
ADB, reboots the tablet, writes removable media, or flashes a partition.  A
successful run is deliberately not a deployment or device-write authorization.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


WORKSPACE = Path(__file__).resolve().parents[2]
DEFAULT_FIRMWARE = (
    WORKSPACE / "dist-gts6lwifi-ufs-offline/gts6lwifi-ufs-offline.fd"
)
DEFAULT_BOOT_IMAGE = (
    WORKSPACE / "dist-gts6lwifi-ufs-offline/gts6lwifi-ufs-offline.img"
)
DEFAULT_AML = WORKSPACE / "implementation/build/acpi-ufs-offline/DSDT.aml"
DEFAULT_SOURCE_REPORT = (
    WORKSPACE
    / "dist-gts6lwifi-ufs-offline/ufs-offline-source-preparation.json"
)
DEFAULT_UEFI_REPORT = (
    WORKSPACE / "dist-gts6lwifi-ufs-offline/ufs-offline-validation.json"
)
DEFAULT_ACPI_REPORT = (
    WORKSPACE / "implementation/build/acpi-ufs-offline/validation.json"
)
DEFAULT_OUTPUT = WORKSPACE / "implementation/build/uefi/first-boot-readiness.json"
UEFI_SOURCE_REL = "research/repos/mu_aloha_platforms"
UEFI_SOURCE = WORKSPACE / UEFI_SOURCE_REL
EXPECTED_UEFI_COMMIT = "96add763040d86d21f87a4a4022e094e17e6e3c6"
UPSTREAM_GTS6L_COMMIT = "9ff4c1f9202b19ef53e68214f25c58718dc6d1f2"
UPSTREAM_POSTBUILD_PATH = "Platforms/SurfaceDuo1Pkg/PythonLibs/PostBuild.py"
UPSTREAM_POSTBUILD_SHA256 = (
    "e07309e4b10bd16bd91173d20c34d02ada297710ee72589f026f40497aff89e4"
)
PINNED_POSTBUILD_PATH = "PythonLibs/PostBuild.py"
PINNED_POSTBUILD_SHA256 = (
    "4e670636f2d7584277d9ef9d28c9c91c33895208ca68bcc837cee77635ab8c2a"
)
PINNED_SM8150_CONFIG_PATH = "build_cfg/sm8150.json"
PINNED_SM8150_CONFIG_SHA256 = (
    "50e6b6b6744a7a9176b1a98fc4f8e1892ae6155e290a6fa19f45b5a8d169b1ba"
)
EXPECTED_AML_SHA256 = (
    "43616254541c522b4bdd171776224e32205b6edd7deace17067466d15a961b0d"
)
EXPECTED_FIRMWARE_BYTES = 3_145_728
EXPECTED_FIRMWARE_SHA256 = (
    "c08f5ef09c6674884f9833abe197ddbb00248b861c20e636f96d442ec135c89b"
)
EXPECTED_BOOT_IMAGE_BYTES = 3_837_952
EXPECTED_BOOT_IMAGE_SHA256 = (
    "09043c50d3f6b46806ce6b26693cd6c4a010f37888d50bb69297711f55c6ceba"
)
EXPECTED_SOURCE_REPORT_BYTES = 844
EXPECTED_SOURCE_REPORT_SHA256 = (
    "961b8ff072a1ccd42e494da0026d1f33d8970847abe4e66f4d4dea498fdc039f"
)
EXPECTED_UEFI_REPORT_BYTES = 1_434
EXPECTED_UEFI_REPORT_SHA256 = (
    "ae441e29e80d8db198793014a49c4be99cf384bb1fe725d6e60b9ca674202a91"
)
EXPECTED_ACPI_REPORT_BYTES = 499
EXPECTED_ACPI_REPORT_SHA256 = (
    "f55f7f94af2675f857906ee719a818651ec8f5626353aec820c1971e5374c9aa"
)
EXPECTED_WINDOWS_VALIDATOR_SHA256 = (
    "34e28d4100024c11840ec1d634c0fbe556dd9c0adf86f515cb076d073b5a3a6f"
)
# Historical evidence identifies a plausible physical-key transition, but no
# current-session report has yet bound that transition to this device and the
# post-EndSession(false) state.  The trigger gate therefore has no accepted
# evidence digest.  Enabling it requires a reviewed code change that pins the
# exact report SHA-256; there is no Boolean switch that can unlock execution.
RECOVERY_TRIGGER_PROTOCOL_ID = (
    "t860-dwh1-download-black-to-recovery-key-transition-v1"
)
EXPECTED_RECOVERY_TRIGGER_REPORT_SHA256: str | None = None

# A future execution binary is deliberately separate from the untraceable
# Heimdall 2.0.2 binary retained in the historical transport evidence.  These
# immutable source facts identify the only currently reviewed source candidate.
# None of the review digests below may be supplied by an evidence report: they
# require a code review and a validator change.  Their None defaults make every
# candidate fail closed at a pending state.
EXECUTION_HEIMDALL_REPOSITORY = "https://git.sr.ht/~grimler/Heimdall"
EXECUTION_HEIMDALL_TAG = "v2.2.2"
EXECUTION_HEIMDALL_TAG_OBJECT = "2316fe346fece34726619498f34446b6d3df7c3a"
EXECUTION_HEIMDALL_COMMIT = "d9554e7fa30a00abed7f0ac86b10e63c2c3b8e20"
EXECUTION_HEIMDALL_TREE = "5ea9109a5005fbdc075443ebe16955b87d002ed5"
EXECUTION_HEIMDALL_ARCHIVE_URL = (
    "https://git.sr.ht/~grimler/Heimdall/archive/v2.2.2.tar.gz"
)
EXECUTION_HEIMDALL_ARCHIVE_SHA256 = (
    "7d01dd8bf9c2f93ea016ae8b059110c50cea49e78670e8a1333ebd5899cdaaa3"
)
EXECUTION_HEIMDALL_SIGNING_FINGERPRINT = (
    "2C7F29AE97891F6419A9E2CDB0076E490B71616B"
)
EXPECTED_EXECUTION_HEIMDALL_SIGNING_KEY_SHA256: str | None = None
EXPECTED_EXECUTION_TOOL_BINARY_SHA256: str | None = None
EXPECTED_EXECUTION_TOOL_PROVENANCE_REPORT_SHA256: str | None = None
EXPECTED_EXECUTION_TOOL_LIVENESS_REPORT_SHA256: str | None = None
# The current implementation is a fail-closed candidate collector only.  Do
# not set this True merely because the four review digests above are known.
# A later reviewed implementation must first parse the actual binary and its
# dependencies, perform real signature verification, bind source to build
# output, require an exact allowlisted collector/watchdog invocation, and
# remove pathname TOCTOU from the executor handoff.
EXECUTION_TOOL_PASS_VALIDATION_IMPLEMENTED = False
RECOVERY_TRIGGER_REQUIRED_STOP_CONDITIONS = {
    "identity-mismatch",
    "multiple-or-no-download-device",
    "read-only-precondition-failed",
    "operator-sequence-deviation",
    "both-volume-keys-active-at-abl-sample",
    "android-boot-observed",
    "download-mode-reentered",
    "recovery-evidence-timeout",
    "host-loses-observability",
    "any-host-partition-write-observed",
}
HISTORICAL_HEIMDALL_SHA256 = (
    "636997aca4845d1ff253bf30adc98b4f2bd7a9fafbdceda7e7647527d17843ef"
)
HISTORICAL_TWRP_SHA256 = (
    "cbc6e03563a9229b7034dd775964ef412af94a7074f50b519ce1ccc1fd4f2e16"
)
HISTORICAL_TWRP_BYTES = 67_080_192
HISTORICAL_TRANSPORT_FILES = {
    "recovery_upload_log": {
        "sha256": "cdc2b57e5036801af0fa4644aa6dcba4d6b50ef76de5266023bd07b3e5a5b4c9",
        "markers": [
            "Heimdall v2.0.2",
            "Session begun.",
            "PIT file download successful.",
            "RECOVERY upload successful",
        ],
    },
    "boot_vbmeta_upload_log": {
        "sha256": "0e4f2553a1953d9ad962ab5fe3bf5bb8887583f07bfe86ac5be6f18f719825fa",
        "markers": [
            "Heimdall v2.0.2",
            "Session begun.",
            "PIT file download successful.",
            "BOOT upload successful",
            "VBMETA upload successful",
        ],
    },
    "usb_identification_log": {
        "sha256": "dc7a529a430c1ec114c35004965c73c8e6bfca34cda2ba520b618d499bcfebda",
        "markers": ["Heimdall v2.0.2", "VID:PID: 04E8:685D"],
    },
    "flash_record": {
        "sha256": "ea3b0c1180b096607bf3c7930f6c540689ad6bb95425e01f6c37aae5fa34accc",
        "markers": [
            "Device state: Samsung Download Mode",
            "PIT header: `COM_TAR2`, CPU/bootloader tag `SM8150`, 76 entries",
            "RECOVERY: PASS",
            "BOOT: PASS",
            "VBMETA: PASS",
            "No PIT/repartition operation was used.",
        ],
    },
    "runtime_audit": {
        "sha256": "3758ba664f46fe99da7cbc704acc40af9dcd87587f666233086d80470f6843cd",
        "markers": [
            "PASS Android 16 completed boot",
            "PASS SELinux is Enforcing and user 0 reached RUNNING_UNLOCKED",
            "PASS fixed TWRP prefix SHA-256 remained",
            HISTORICAL_TWRP_SHA256,
        ],
    },
    "runtime_getprop": {
        "sha256": "368b05a9b67c4935d114d2e2ed0ca4a0498582681453bdf8d897669988e04459",
        "markers": [
            "[sys.boot_completed]: [1]",
        ],
    },
    "runtime_user": {
        "sha256": "be7f5973601aa7eb93980987586276c13e0137e8c808c5e7708930ba5051ba83",
        "markers": ["State: RUNNING_UNLOCKED"],
    },
    "recovery_prefix_readback": {
        "sha256": "eb9c074100bde9a4932b8038a3520e520085df2f48891507d15ee67df898f3f6",
        "markers": [HISTORICAL_TWRP_SHA256, "recovery-prefix-67080192-bytes"],
    },
    "unlocked_recovery_boot_log": {
        "sha256": "376859f2753944879413d4a20427cc2cc331601160843c1c0a88e5e14bc5a430",
        "markers": [
            "VB2: Authenticate complete! boot state is: orange",
            "(Booting) AUTHENTICATE fail but allow Recovery binary: recovery",
        ],
    },
    "twrp_image": {
        "sha256": HISTORICAL_TWRP_SHA256,
        "markers": [],
    },
}

REQUIRED_MODULES = {
    "BdsDxe": "6d33944a-ec75-4855-a54d-809c75241f6c",
    "MsBootPolicy": "50670071-478f-4be7-ad13-8754f379c62f",
    "SdccDxe": "f10f76db-42c1-533f-34a8-69be24653110",
    "DiskIoDxe": "6b38f7b4-ad98-40e9-9093-aca2b5a253c4",
    "PartitionDxe": "1fa1f39e-feff-4aae-bd7b-38a070a3b609",
    "Fat": "961578fe-b6b7-44c3-af35-6bc705cd2b1f",
}
USB_FALLBACK_MODULES = {
    "XhciDxe": "b7f50e91-a759-412c-ade4-dcd03e7f7c28",
    "UsbBusDxe": "240612b7-a063-11d4-9a3a-0090273fc14d",
    "UsbMassStorageDxe": "9fb4b4a7-42c0-4bcd-8540-9bcc6711f83e",
}
FORBIDDEN_MODULES = {
    "QcomBds": "5a50aa81-c3ae-4608-a0e3-41a2e69baf94",
    "UFSDxe": "0d35cd8e-97ea-4f9a-96af-0f0d89f76567",
}

WINDOWS_CHECK_IDS = {
    "media.same_physical_disk",
    "media.target_disk_safety",
    "media.windows_ntfs",
    "media.esp_fat32",
    "media.esp_gpt_type",
    "pe.sdbus_arm64",
    "pe.sdstor_arm64",
    "pe.winload_arm64",
    "pe.bootmgfw_source_arm64",
    "pe.bootmgfw_esp_arm64",
    "pe.bootaa64_arm64",
    "efi.boot_files_identical",
    "inf.qcom2466_mapping",
    "manifest.sdbus_qcom2466",
    "manifest.sdbus_bootflags",
    "manifest.sdstor_bootflags",
    "bcd.regf",
    "bcd.semantic",
}
WINDOWS_PE_CHECK_IDS = {
    "pe.sdbus_arm64",
    "pe.sdstor_arm64",
    "pe.winload_arm64",
    "pe.bootmgfw_source_arm64",
    "pe.bootmgfw_esp_arm64",
    "pe.bootaa64_arm64",
}

STOCK_ARCHIVE_SHA256 = (
    "c058d8cb176bd796e67b7520b1cb5abbdf74d7dbe40f2bbfad0b38209082f436"
)
STOCK_ARCHIVE_BYTES = 6_746_376_090
STOCK_VERSION = "T860XXS5DWH1/T860OXM5DWH1/T860XXS5DWH1/T860XXS5DWH1"
STOCK_MEMBERS = {
    "BL_T860XXS5DWH1_T860XXS5DWH1_MQB68901788_REV00_user_low_ship_MULTI_CERT.tar.md5": (
        "70e99c4d8cfa3b11d51473af1227fe4a"
    ),
    "AP_T860XXS5DWH1_T860XXS5DWH1_MQB68901788_REV00_user_low_ship_MULTI_CERT_meta_OS12.tar.md5": (
        "c5200642d191e4945bb8eda0a888972f"
    ),
    "HOME_CSC_OXM_T860OXM5DWH1_CL26185793_QB68899680_REV00_user_low_ship_MULTI_CERT.tar.md5": (
        "80e34188ee2294443df0faa5de45c700"
    ),
    "CSC_OXM_T860OXM5DWH1_CL26185793_QB68899680_REV00_user_low_ship_MULTI_CERT.tar.md5": (
        "b556d21a4b1d18b57496d007e9909ea2"
    ),
}
STOCK_CRITICAL = {
    "boot.img": {
        "bytes": 67_108_864,
        "sha256": "714ae657b927ba64c8ee58cc03d16370ad2f05a9c020086df5b2d73488a9ed1f",
    },
    "recovery.img": {
        "bytes": 82_792_448,
        "sha256": "e8a3ce8166feb198ee8e329110c0a12a2f075e7ab77e28a2fabdd80fb0cb8aab",
    },
    "dtbo.img": {
        "bytes": 10_485_760,
        "sha256": "864ca763a1362a77aa929c3e2f147baa70196c31401b52f76bf0f879d7eb99ec",
    },
    "vbmeta.img": {
        "bytes": 8_320,
        "sha256": "b79f51f4e96b62ed1c0e9e0276838ca7727b0139ec02699463fd114741890888",
    },
    "GTS6LWIFI_EUR_OPEN.pit": {
        "bytes": 10_572,
        "sha256": "de3f707d2f2ef0207341e0fd8a53b7c433423920ae1214e74454e6c618ec47b4",
    },
}

SHA256_RE = re.compile(r"[0-9a-fA-F]{64}\Z")


class DuplicateJsonKey(ValueError):
    """Raised when an evidence JSON object contains an ambiguous duplicate key."""


def reject_duplicate_json_keys(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise DuplicateJsonKey(f"duplicate JSON key {key!r}")
        value[key] = item
    return value


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=reject_duplicate_json_keys,
        )
    except (OSError, json.JSONDecodeError, DuplicateJsonKey) as exc:
        raise SystemExit(f"validation failed: cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SystemExit(f"validation failed: expected JSON object in {path}")
    return value


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_record(path: Path, data: bytes | None = None) -> dict[str, Any]:
    resolved = path.resolve()
    if not resolved.is_file():
        raise SystemExit(f"validation failed: missing file {resolved}")
    if data is None:
        return {
            "path": str(resolved),
            "bytes": resolved.stat().st_size,
            "sha256": sha256_file(resolved),
        }
    return {
        "path": str(resolved),
        "bytes": len(data),
        "sha256": sha256_bytes(data),
    }


def android_boot_record(data: bytes) -> dict[str, Any]:
    has_magic = data.startswith(b"ANDROID!")
    page_size = int.from_bytes(data[36:40], "little") if len(data) >= 44 else None
    header_version = int.from_bytes(data[40:44], "little") if len(data) >= 44 else None
    return {
        "android_magic": has_magic,
        "kernel_bytes": int.from_bytes(data[8:12], "little") if len(data) >= 44 else None,
        "ramdisk_bytes": int.from_bytes(data[16:20], "little") if len(data) >= 44 else None,
        "second_bytes": int.from_bytes(data[24:28], "little") if len(data) >= 44 else None,
        "header_version": header_version,
        "page_size": page_size,
        "samsung_signer_ver02_occurrences": data.count(
            b"SEANDROIDENFORCESignerVer02"
        ),
        "avb_vbmeta_magic_occurrences": data.count(b"AVB0"),
        "avb_footer_magic_occurrences": data.count(b"AVBf"),
        "avb_footer_at_partition_end": len(data) >= 64 and data[-64:-60] == b"AVBf",
        "partition_tail_64_all_zero": len(data) >= 64 and data[-64:] == bytes(64),
    }


def pit_structure_record(data: bytes) -> dict[str, Any]:
    """Parse the fixed fields needed to compare two Samsung PIT layouts."""

    magic = int.from_bytes(data[0:4], "little") if len(data) >= 32 else None
    entry_count = int.from_bytes(data[4:8], "little") if len(data) >= 32 else None
    header = (
        data[8:16].split(b"\0", 1)[0].decode("ascii", errors="replace")
        if len(data) >= 32
        else None
    )
    cpu_tag = (
        data[16:24].split(b"\0", 1)[0].decode("ascii", errors="replace")
        if len(data) >= 28
        else None
    )
    logic_unit_count = int.from_bytes(data[24:28], "little") if len(data) >= 28 else None
    entries: list[dict[str, Any]] = []
    if isinstance(entry_count, int) and 0 <= entry_count <= 256:
        for index in range(entry_count):
            offset = 28 + index * 132
            if offset + 132 > len(data):
                break
            entry = data[offset : offset + 132]
            entries.append(
                {
                    "binary_type": int.from_bytes(entry[0:4], "little"),
                    "device_type": int.from_bytes(entry[4:8], "little"),
                    "identifier": int.from_bytes(entry[8:12], "little"),
                    "attributes": int.from_bytes(entry[12:16], "little"),
                    "update_attributes": int.from_bytes(entry[16:20], "little"),
                    "block_offset": int.from_bytes(entry[20:24], "little"),
                    "block_count": int.from_bytes(entry[24:28], "little"),
                    "file_offset": int.from_bytes(entry[28:32], "little"),
                    "file_size": int.from_bytes(entry[32:36], "little"),
                    "partition_name": entry[36:68]
                    .split(b"\0", 1)[0]
                    .decode("ascii", errors="replace"),
                    "flash_filename": entry[68:100]
                    .split(b"\0", 1)[0]
                    .decode("ascii", errors="replace"),
                    "fota_filename": entry[100:132]
                    .split(b"\0", 1)[0]
                    .decode("ascii", errors="replace"),
                }
            )
    return {
        "magic": f"0x{magic:08x}" if isinstance(magic, int) else None,
        "entry_count": entry_count,
        "header": header,
        "cpu_bootloader_tag": cpu_tag,
        "logic_unit_count": logic_unit_count,
        "entries_parsed": len(entries),
        "entries": entries,
    }


def report_record(path: Path) -> dict[str, Any]:
    data = path.resolve().read_bytes()
    return file_record(path, data)


def valid_sha256(value: object) -> bool:
    return isinstance(value, str) and SHA256_RE.fullmatch(value) is not None


def require_equal(
    reasons: list[str], label: str, actual: object, expected: object
) -> None:
    if not values_strictly_equal(actual, expected):
        reasons.append(f"{label}: expected {expected!r}, found {actual!r}")


def values_strictly_equal(actual: object, expected: object) -> bool:
    """Compare JSON-like facts without Python's bool/int equivalence."""

    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        return set(actual) == set(expected) and all(
            values_strictly_equal(actual[key], expected[key]) for key in expected
        )
    if isinstance(expected, (list, tuple)):
        return len(actual) == len(expected) and all(
            values_strictly_equal(left, right)
            for left, right in zip(actual, expected)
        )
    return actual == expected


def require_exact_keys(
    reasons: list[str], label: str, value: object, expected: set[str]
) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        reasons.append(f"{label} must be an object")
        return None
    require_equal(reasons, f"{label} keys", set(value), expected)
    return value


def validate_bound_file(
    reasons: list[str],
    label: str,
    evidence_root: Path | None,
    value: object,
) -> dict[str, Any] | None:
    binding = require_exact_keys(
        reasons, label, value, {"path", "bytes", "sha256"}
    )
    if binding is None or evidence_root is None:
        return None
    relative = binding.get("path")
    if not isinstance(relative, str) or not relative:
        reasons.append(f"{label} path must be a non-empty relative path")
        return None
    try:
        relative_path = Path(relative)
        if relative_path.is_absolute():
            reasons.append(f"{label} path must be a non-empty relative path")
            return None
        unresolved = evidence_root / relative_path
        resolved = unresolved.resolve()
        if evidence_root not in resolved.parents or not resolved.is_file():
            reasons.append(f"{label} path escapes evidence_root or is missing")
            return None
        if unresolved.is_symlink():
            reasons.append(f"{label} must not be a symbolic link")
            return None
        record = file_record(resolved)
    except (OSError, RuntimeError, ValueError) as exc:
        reasons.append(f"{label} path cannot be resolved safely: {exc}")
        return None
    require_equal(reasons, f"{label} bytes", binding.get("bytes"), record["bytes"])
    require_equal(
        reasons, f"{label} SHA-256", binding.get("sha256"), record["sha256"]
    )
    return record


def require_distinct_bound_files(
    reasons: list[str], label: str, records: dict[str, dict[str, Any]]
) -> None:
    seen: dict[tuple[int, int], str] = {}
    for name, record in records.items():
        try:
            stat = Path(record["path"]).stat()
        except (KeyError, OSError, TypeError, ValueError) as exc:
            reasons.append(f"{label} {name} cannot be stat'ed: {exc}")
            continue
        identity = (stat.st_dev, stat.st_ino)
        if identity in seen:
            reasons.append(
                f"{label} {name} must be a distinct file from {seen[identity]}"
            )
        else:
            seen[identity] = name


def read_bound_text(
    reasons: list[str], label: str, record: dict[str, Any]
) -> str | None:
    """Read an already-bound text file without exposing a TOCTOU traceback."""

    try:
        return Path(record["path"]).read_text(encoding="utf-8", errors="replace")
    except (KeyError, OSError, RuntimeError, TypeError, ValueError) as exc:
        reasons.append(f"{label} cannot be read safely: {exc}")
        return None


def read_bound_bytes(
    reasons: list[str], label: str, record: dict[str, Any]
) -> bytes | None:
    """Read an already-bound binary file without exposing a TOCTOU traceback."""

    try:
        return Path(record["path"]).read_bytes()
    except (KeyError, OSError, RuntimeError, TypeError, ValueError) as exc:
        reasons.append(f"{label} cannot be read safely: {exc}")
        return None


def stat_bound_file(
    reasons: list[str], label: str, record: dict[str, Any]
) -> os.stat_result | None:
    """Stat an already-bound file without exposing a TOCTOU traceback."""

    try:
        return Path(record["path"]).stat()
    except (KeyError, OSError, RuntimeError, TypeError, ValueError) as exc:
        reasons.append(f"{label} cannot be stat'ed safely: {exc}")
        return None


def run_git(repository: Path, *arguments: str) -> str:
    try:
        return subprocess.run(
            ["git", "-C", str(repository), *arguments],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SystemExit(
            f"validation failed: git {' '.join(arguments)} failed in {repository}"
        ) from exc


def git_file_bytes(commit: str, path: str) -> bytes:
    try:
        return subprocess.run(
            ["git", "-C", str(UEFI_SOURCE), "show", f"{commit}:{path}"],
            check=True,
            capture_output=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SystemExit(
            f"validation failed: cannot read {path} at fixed commit {commit}"
        ) from exc


def git_file(commit: str, path: str) -> str:
    return run_git(UEFI_SOURCE, "show", f"{commit}:{path}")


def firmware_inventory(path: Path) -> tuple[dict[str, Any], str]:
    try:
        from uefi_firmware import AutoParser
    except ImportError as exc:
        raise SystemExit(
            "validation failed: install pinned parser with "
            "python3 -m pip install uefi_firmware==1.16"
        ) from exc

    version = importlib.metadata.version("uefi_firmware")
    if version != "1.16":
        raise SystemExit(
            "validation failed: firmware inventory requires "
            f"uefi_firmware 1.16, found {version}"
        )
    parsed = AutoParser(path.read_bytes()).parse()
    if parsed is None:
        raise SystemExit("validation failed: firmware parser rejected the artifact")

    names: set[str] = set()
    guids: set[str] = set()
    pairs: set[tuple[str, str]] = set()

    def descendant_names(value: object) -> set[str]:
        found: set[str] = set()
        if isinstance(value, dict):
            name = value.get("name")
            if isinstance(name, str):
                found.add(name)
            for child in value.values():
                found.update(descendant_names(child))
        elif isinstance(value, list):
            for child in value:
                found.update(descendant_names(child))
        return found

    def walk(value: object) -> None:
        if isinstance(value, dict):
            name = value.get("name")
            guid = value.get("guid")
            if isinstance(name, str):
                names.add(name)
            if isinstance(guid, str):
                guids.add(guid.lower())
            # FFS entries expose both fileType and guid.  Type 11 is a nested FV
            # container; associating all descendant UI names with its GUID would
            # create false name/GUID pairs, so it is excluded.
            if (
                isinstance(guid, str)
                and "fileType" in value
                and value.get("type") != 11
            ):
                for ui_name in descendant_names(value.get("sections", [])):
                    names.add(ui_name)
                    pairs.add((ui_name, guid.lower()))
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(parsed.to_dict())
    return {
        "names": names,
        "guids": guids,
        "pairs": pairs,
    }, version


def validate_source_pin_and_policy() -> tuple[dict[str, Any], bool]:
    reasons: list[str] = []
    index_entry = run_git(WORKSPACE, "ls-files", "-s", "--", UEFI_SOURCE_REL)
    fields = index_entry.split()
    gitlink_commit = fields[1] if len(fields) >= 2 and fields[0] == "160000" else None
    source_head = run_git(UEFI_SOURCE, "rev-parse", "HEAD")
    require_equal(reasons, "superproject gitlink", gitlink_commit, EXPECTED_UEFI_COMMIT)
    require_equal(reasons, "submodule HEAD", source_head, EXPECTED_UEFI_COMMIT)

    policy_source = git_file(
        EXPECTED_UEFI_COMMIT,
        "Platforms/AndromedaPkg/Library/MsBootPolicyLib/MsBootPolicyLib.c",
    )
    options_source = git_file(
        EXPECTED_UEFI_COMMIT,
        "Platforms/AndromedaPkg/Library/MsBootOptionsLib/MsBootOptionsLib.c",
    )
    boot_sequence_hdd_then_usb = re.search(
        r"BootSequenceHUP\[\]\s*=\s*\{.*?MsBootHDD,\s*MsBootUSB,",
        policy_source,
        re.DOTALL,
    ) is not None
    sdd_call = (
        "RegisterFvBootOption (&gMsBootPolicyFileGuid, MS_SDD_BOOT"
        in options_source
    )
    usb_call = (
        "RegisterFvBootOption (&gMsBootPolicyFileGuid, MS_USB_BOOT"
        in options_source
    )
    policy_checks = {
        "sd_boot_suppression_disabled": (
            "SdCardDevicePath = NULL" in policy_source
            and "will not disable SD Card Boot" in policy_source
        ),
        "normal_boot_sequence_hdd_then_usb": boot_sequence_hdd_then_usb,
        "internal_storage_option_registered": (
            'MS_SDD_BOOT_PARM  "SDD"' in options_source and sdd_call
        ),
        "usb_storage_option_registered": (
            'MS_USB_BOOT_PARM  "USB"' in options_source and usb_call
        ),
        "storage_options_registered_in_order": (
            sdd_call
            and usb_call
            and options_source.index(
                "RegisterFvBootOption (&gMsBootPolicyFileGuid, MS_SDD_BOOT"
            )
            < options_source.index(
                "RegisterFvBootOption (&gMsBootPolicyFileGuid, MS_USB_BOOT"
            )
        ),
    }
    for label, passed in policy_checks.items():
        if not passed:
            reasons.append(f"boot policy source check failed: {label}")
    return {
        "expected_commit": EXPECTED_UEFI_COMMIT,
        "superproject_gitlink": gitlink_commit,
        "submodule_head": source_head,
        "policy_checks": policy_checks,
        "reasons": reasons,
    }, not reasons


def validate_boot_container_lineage(
    boot_format: dict[str, Any], source_report: dict[str, Any]
) -> tuple[dict[str, Any], bool]:
    """Bind the current container format to fixed upstream packaging sources.

    Absence of Samsung/AVB trailers is recorded, not treated as an authentication
    failure: the unlocked target has booted an unsigned TWRP container before and
    the upstream gts6l Windows/SD implementation intentionally used header v0.
    The exact current image is nevertheless untested on hardware.
    """

    reasons: list[str] = []
    upstream_bytes = git_file_bytes(UPSTREAM_GTS6L_COMMIT, UPSTREAM_POSTBUILD_PATH)
    pinned_bytes = git_file_bytes(EXPECTED_UEFI_COMMIT, PINNED_POSTBUILD_PATH)
    pinned_config_bytes = git_file_bytes(
        EXPECTED_UEFI_COMMIT, PINNED_SM8150_CONFIG_PATH
    )
    upstream_source = upstream_bytes.decode("utf-8")
    pinned_source = pinned_bytes.decode("utf-8")
    pinned_config_text = pinned_config_bytes.decode("utf-8")
    try:
        pinned_config = json.loads(pinned_config_text)
    except json.JSONDecodeError as exc:
        reasons.append(f"pinned SM8150 boot configuration is invalid JSON: {exc}")
        pinned_config = {}

    require_equal(
        reasons,
        "upstream gts6l PostBuild SHA-256",
        sha256_bytes(upstream_bytes),
        UPSTREAM_POSTBUILD_SHA256,
    )
    require_equal(
        reasons,
        "pinned PostBuild SHA-256",
        sha256_bytes(pinned_bytes),
        PINNED_POSTBUILD_SHA256,
    )
    require_equal(
        reasons,
        "pinned SM8150 configuration SHA-256",
        sha256_bytes(pinned_config_bytes),
        PINNED_SM8150_CONFIG_SHA256,
    )

    upstream_checks = {
        "header_version_0": '"--header_version", "0"' in upstream_source,
        "page_size_4096": '"--pagesize", "4096"' in upstream_source,
        "empty_ramdisk": '"--ramdisk", "./ImageResources/emptyramdisk"'
        in upstream_source,
        "gzip_payload": "gzip.compress(data, 9)" in upstream_source,
        "dtb_appended": "data = dtb.read()" in upstream_source
        and "f.write(data)" in upstream_source,
    }
    pinned_source_checks = {
        "header_version_parameterized": '"--header_version", str(self.header_version)'
        in pinned_source,
        "page_size_parameterized": '"--pagesize", str(self.pagesize)' in pinned_source,
        "empty_ramdisk_parameterized": 'args.extend(["--ramdisk", "./PythonLibs/emptyramdisk"])'
        in pinned_source,
        "optional_gzip_payload": "if self.kernel_compressed:" in pinned_source
        and "gzip.compress(payload_data, 9)" in pinned_source,
        "v0_v1_dtb_appended": "if self.header_version < 2:" in pinned_source,
    }
    expected_config = {
        "header_version": 0,
        "kernel_compressed": True,
        "emptyramdisk": True,
        "pagesize": 4096,
        "base": "0x0",
        "os_version": "11.0.0",
        "os_patch_level": "2023-04-01",
    }
    actual_config = pinned_config.get("default_aboot_args")
    if actual_config != expected_config:
        reasons.append("pinned SM8150 Android boot defaults do not match the fixed set")
    for label, passed in {**upstream_checks, **pinned_source_checks}.items():
        if not passed:
            reasons.append(f"Android boot container source check failed: {label}")
    try:
        ancestor_check = subprocess.run(
            [
                "git",
                "-C",
                str(UEFI_SOURCE),
                "merge-base",
                "--is-ancestor",
                UPSTREAM_GTS6L_COMMIT,
                EXPECTED_UEFI_COMMIT,
            ],
            check=False,
            capture_output=True,
        )
        if ancestor_check.returncode != 0:
            reasons.append(
                "fixed upstream gts6l container commit is not an ancestor of "
                "the pinned UEFI source commit"
            )
    except OSError as exc:
        reasons.append(f"cannot run fixed source ancestry check: {exc}")
    require_equal(reasons, "current Android boot header", boot_format.get("header_version"), 0)
    require_equal(reasons, "current Android boot page size", boot_format.get("page_size"), 4096)
    require_equal(reasons, "current Android boot ramdisk size", boot_format.get("ramdisk_bytes"), 6)
    for field, expected in {
        "android_magic": True,
        "second_bytes": 0,
        "samsung_signer_ver02_occurrences": 0,
        "avb_vbmeta_magic_occurrences": 0,
        "avb_footer_magic_occurrences": 0,
        "avb_footer_at_partition_end": False,
        "partition_tail_64_all_zero": True,
    }.items():
        require_equal(reasons, f"current Android boot {field}", boot_format.get(field), expected)
    require_equal(
        reasons,
        "temporary source report kernel_compressed",
        source_report.get("firmware_layout", {}).get("kernel_compressed"),
        False,
    )

    return {
        "state": "pass" if not reasons else "fail",
        "reasons": reasons,
        "boot_image_container_static_support": not reasons,
        "authentication_path_historically_supported_on_unlocked_device": False,
        "exact_current_image_hardware_tested": False,
        "current_container": boot_format,
        "upstream_gts6l_container": {
            "commit": UPSTREAM_GTS6L_COMMIT,
            "path": UPSTREAM_POSTBUILD_PATH,
            "sha256": UPSTREAM_POSTBUILD_SHA256,
            "checks": upstream_checks,
        },
        "pinned_container_builder": {
            "commit": EXPECTED_UEFI_COMMIT,
            "postbuild_path": PINNED_POSTBUILD_PATH,
            "postbuild_sha256": PINNED_POSTBUILD_SHA256,
            "config_path": PINNED_SM8150_CONFIG_PATH,
            "config_sha256": PINNED_SM8150_CONFIG_SHA256,
            "checks": pinned_source_checks,
            "base_config": actual_config,
            "temporary_kernel_compressed_override": False,
        },
        "historical_unlocked_device_evidence_expected": {
            "twrp_image_sha256": HISTORICAL_TWRP_SHA256,
            "unlocked_recovery_boot_log_sha256": HISTORICAL_TRANSPORT_FILES[
                "unlocked_recovery_boot_log"
            ]["sha256"],
            "bound_by_transport_report": False,
        },
        "trust_boundary": (
            "Header v0/page 4096 follows the upstream gts6l Windows/SD packer. "
            "The pinned builder keeps that format, while this artifact disables "
            "gzip only so FD/AML bytes remain independently verifiable.  Historical "
            "unlocked-device acceptance does not prove this exact image hash boots."
        ),
    }, not reasons


def validate_static_reports_and_artifacts(
    firmware: Path,
    boot_image: Path,
    aml: Path,
    source_report_path: Path,
    uefi_report_path: Path,
    acpi_report_path: Path,
) -> tuple[dict[str, Any], bool]:
    reasons: list[str] = []
    firmware_data = firmware.read_bytes()
    boot_data = boot_image.read_bytes()
    aml_data = aml.read_bytes()
    firmware_record = file_record(firmware, firmware_data)
    boot_record = file_record(boot_image, boot_data)
    aml_record = file_record(aml, aml_data)
    boot_format = android_boot_record(boot_data)

    require_equal(reasons, "firmware bytes", firmware_record["bytes"], EXPECTED_FIRMWARE_BYTES)
    require_equal(reasons, "firmware SHA-256", firmware_record["sha256"], EXPECTED_FIRMWARE_SHA256)
    require_equal(reasons, "boot image bytes", boot_record["bytes"], EXPECTED_BOOT_IMAGE_BYTES)
    require_equal(reasons, "boot image SHA-256", boot_record["sha256"], EXPECTED_BOOT_IMAGE_SHA256)
    require_equal(reasons, "AML SHA-256", aml_record["sha256"], EXPECTED_AML_SHA256)
    if not aml_data.startswith(b"DSDT"):
        reasons.append("AML does not start with DSDT")
    elif len(aml_data) < 8 or int.from_bytes(aml_data[4:8], "little") != len(aml_data):
        reasons.append("AML declared length does not equal file length")
    if sum(aml_data) % 256 != 0:
        reasons.append("AML checksum is not zero modulo 256")

    firmware_aml_occurrences = firmware_data.count(aml_data)
    boot_aml_occurrences = boot_data.count(aml_data)
    boot_firmware_occurrences = boot_data.count(firmware_data)
    if firmware_aml_occurrences != 1:
        reasons.append(
            "firmware must contain the exact AML once, "
            f"found {firmware_aml_occurrences}"
        )
    if not boot_format["android_magic"]:
        reasons.append("boot image lacks ANDROID! header")
    if boot_firmware_occurrences != 1:
        reasons.append(
            "boot image must contain the exact firmware once, "
            f"found {boot_firmware_occurrences}"
        )
    if boot_aml_occurrences != 1:
        reasons.append(
            f"boot image must contain the exact AML once, found {boot_aml_occurrences}"
        )

    source_report = load_json(source_report_path)
    source_report_record = report_record(source_report_path)
    require_equal(
        reasons,
        "source report bytes",
        source_report_record["bytes"],
        EXPECTED_SOURCE_REPORT_BYTES,
    )
    require_equal(
        reasons,
        "source report SHA-256",
        source_report_record["sha256"],
        EXPECTED_SOURCE_REPORT_SHA256,
    )
    source_report_expectations = {
        "schema": 1,
        "profile": "gts6lwifi-ufs-offline",
        "status": "pass-ufs-offline-source-preparation",
    }
    for field, expected in source_report_expectations.items():
        require_equal(reasons, f"source report {field}", source_report.get(field), expected)
    expected_source_files = {
        name: {
            "active_ufs_before": 1,
            "active_ufs_after": 0,
            "active_sdcc_after": 1,
        }
        for name in ("APRIORI.inc", "DXE.inc", "DXE.dsc.inc")
    }
    require_equal(
        reasons, "source report files", source_report.get("files"), expected_source_files
    )
    expected_layout = {
        "fdf": "Platforms/SurfaceDuo1Pkg/SurfaceDuo1.fdf",
        "acpi_source_fv": "FVMAIN",
        "acpi_target_fv": "FVMAIN_COMPACT",
        "acpi_outer_fv_uncompressed": True,
        "bootpack": "Platforms/SurfaceDuo1Pkg/Device/samsung-gts6lwifi/bootpack.json",
        "kernel_compressed": False,
    }
    require_equal(
        reasons,
        "source report firmware_layout",
        source_report.get("firmware_layout"),
        expected_layout,
    )

    acpi_report = load_json(acpi_report_path)
    acpi_report_record = report_record(acpi_report_path)
    require_equal(
        reasons,
        "ACPI report bytes",
        acpi_report_record["bytes"],
        EXPECTED_ACPI_REPORT_BYTES,
    )
    require_equal(
        reasons,
        "ACPI report SHA-256",
        acpi_report_record["sha256"],
        EXPECTED_ACPI_REPORT_SHA256,
    )
    for field, expected in {
        "schema": 1,
        "profile": "gts6lwifi-ufs-offline",
        "status": "pass-ufs-offline-acpi",
        "deployable": False,
        "device_writes_performed": False,
        "aml_bytes": aml_record["bytes"],
        "aml_sha256": aml_record["sha256"],
        "internal_ufs_acpi_status": {"UFS0": 0, "UFS1": 0},
        "removable_storage_acpi_status": {"SDC2": 15},
    }.items():
        require_equal(reasons, f"ACPI report {field}", acpi_report.get(field), expected)

    uefi_report = load_json(uefi_report_path)
    uefi_report_record = report_record(uefi_report_path)
    require_equal(
        reasons,
        "UEFI report bytes",
        uefi_report_record["bytes"],
        EXPECTED_UEFI_REPORT_BYTES,
    )
    require_equal(
        reasons,
        "UEFI report SHA-256",
        uefi_report_record["sha256"],
        EXPECTED_UEFI_REPORT_SHA256,
    )
    for field, expected in {
        "schema": 1,
        "device": "samsung-gts6lwifi",
        "profile": "ufs-offline",
        "status": "pass-ufs-offline-uefi-build",
        "deployable": False,
        "device_writes_performed": False,
    }.items():
        require_equal(reasons, f"UEFI report {field}", uefi_report.get(field), expected)
    require_equal(
        reasons,
        "UEFI report AML",
        uefi_report.get("aml"),
        {
            "path": "implementation/build/acpi-ufs-offline/DSDT.aml",
            "bytes": aml_record["bytes"],
            "sha256": aml_record["sha256"],
        },
    )
    require_equal(
        reasons,
        "UEFI report firmware",
        uefi_report.get("firmware"),
        {
            "path": "implementation/build/uefi/gts6lwifi-ufs-offline.fd",
            "bytes": firmware_record["bytes"],
            "sha256": firmware_record["sha256"],
            "embedded_aml_occurrences": firmware_aml_occurrences,
        },
    )
    require_equal(
        reasons,
        "UEFI report boot image",
        uefi_report.get("boot_image"),
        {
            "path": "implementation/build/uefi/gts6lwifi-ufs-offline.img",
            "bytes": boot_record["bytes"],
            "sha256": boot_record["sha256"],
            "embedded_aml_occurrences": boot_aml_occurrences,
            "embedded_exact_firmware_occurrences": boot_firmware_occurrences,
        },
    )
    require_equal(
        reasons,
        "UEFI report driver inventory",
        uefi_report.get("firmware_driver_inventory"),
        {
            "parser": "uefi_firmware 1.16",
            "ufs_driver_guid": FORBIDDEN_MODULES["UFSDxe"],
            "ufs_driver_present": False,
            "sdcc_driver_guid": REQUIRED_MODULES["SdccDxe"],
            "sdcc_driver_present": True,
        },
    )

    container_lineage, container_lineage_pass = validate_boot_container_lineage(
        boot_format, source_report
    )
    if not container_lineage_pass:
        reasons.extend(container_lineage["reasons"])

    inventory, parser_version = firmware_inventory(firmware)
    required_pairs = {item for item in REQUIRED_MODULES.items()}
    usb_pairs = {item for item in USB_FALLBACK_MODULES.items()}
    missing_required_pairs = sorted(required_pairs - inventory["pairs"])
    missing_usb_pairs = sorted(usb_pairs - inventory["pairs"])
    forbidden_present: list[dict[str, str]] = []
    for name, guid in FORBIDDEN_MODULES.items():
        if name in inventory["names"] or guid in inventory["guids"]:
            forbidden_present.append({"name": name, "guid": guid})
    if missing_required_pairs:
        reasons.append(f"required module name/GUID pairs missing: {missing_required_pairs}")
    if missing_usb_pairs:
        reasons.append(f"USB module name/GUID pairs missing: {missing_usb_pairs}")
    if forbidden_present:
        reasons.append(f"forbidden module name or GUID present: {forbidden_present}")

    source_pin, source_pin_pass = validate_source_pin_and_policy()
    if not source_pin_pass:
        reasons.extend(source_pin["reasons"])

    return {
        "state": "pass" if not reasons else "fail",
        "reasons": reasons,
        "artifacts": {
            "firmware": firmware_record,
            "boot_image": boot_record,
            "aml": aml_record,
            "firmware_aml_occurrences": firmware_aml_occurrences,
            "boot_image_aml_occurrences": boot_aml_occurrences,
            "boot_image_exact_firmware_occurrences": boot_firmware_occurrences,
            "boot_image_android_header": boot_format,
            "boot_image_container_static_support": container_lineage_pass,
            "exact_current_image_hardware_tested": False,
        },
        "reports": {
            "source_preparation": source_report_record,
            "uefi_build": uefi_report_record,
            "acpi": acpi_report_record,
        },
        "module_inventory": {
            "parser": f"uefi_firmware {parser_version}",
            "required_name_guid_pairs": [
                {"name": name, "guid": guid}
                for name, guid in sorted(REQUIRED_MODULES.items())
            ],
            "required_name_guid_pairs_missing": [
                {"name": name, "guid": guid}
                for name, guid in missing_required_pairs
            ],
            "usb_name_guid_pairs": [
                {"name": name, "guid": guid}
                for name, guid in sorted(USB_FALLBACK_MODULES.items())
            ],
            "usb_name_guid_pairs_missing": [
                {"name": name, "guid": guid} for name, guid in missing_usb_pairs
            ],
            "forbidden_name_or_guid_present": forbidden_present,
        },
        "boot_container_compatibility_evidence": container_lineage,
        "source_pin_and_boot_policy": source_pin,
    }, not reasons


def pending_gate(reason: str) -> dict[str, Any]:
    return {"state": "pending", "reasons": [reason]}


def validate_execution_tool_provenance_report(
    path: Path | None,
) -> dict[str, Any]:
    """Validate facts for a candidate Heimdall execution binary.

    This gate intentionally has no report-controlled status or trust Boolean.
    A binary/report digest must be fixed in this validator by later code review
    before a structurally valid candidate can pass.
    """

    if path is None:
        return {
            "state": "pending",
            "status": "pending-source-provenance",
            "reasons": ["execution-tool provenance report was not supplied"],
        }
    reasons: list[str] = []
    try:
        report_path = path.expanduser().resolve()
        report = load_json(report_path)
        report_file = report_record(report_path)
    except (OSError, RuntimeError, SystemExit, ValueError) as exc:
        return {
            "state": "fail",
            "status": "fail-execution-tool-provenance",
            "path": str(path),
            "report": None,
            "reasons": [str(exc)],
        }

    require_exact_keys(
        reasons,
        "execution-tool provenance report",
        report,
        {
            "schema",
            "report_type",
            "device_writes_performed",
            "deployable",
            "explicit_device_write_authorization_recorded",
            "evidence_root",
            "source",
            "build",
            "binary",
        },
    )
    for field, expected in {
        "schema": 1,
        "report_type": "sm-t860-execution-tool-provenance",
        "device_writes_performed": False,
        "deployable": False,
        "explicit_device_write_authorization_recorded": False,
    }.items():
        require_equal(reasons, f"execution-tool provenance {field}", report.get(field), expected)

    evidence_root_value = report.get("evidence_root")
    evidence_root: Path | None = None
    if not isinstance(evidence_root_value, str) or not evidence_root_value:
        reasons.append("execution-tool provenance evidence_root must be a non-empty path")
    else:
        try:
            evidence_root = Path(evidence_root_value).expanduser().resolve()
        except (OSError, RuntimeError, ValueError) as exc:
            reasons.append(
                f"execution-tool provenance evidence_root cannot be resolved safely: {exc}"
            )
            evidence_root = None
        if evidence_root is not None and not evidence_root.is_dir():
            reasons.append(
                f"execution-tool provenance evidence_root is missing: {evidence_root}"
            )

    source = require_exact_keys(
        reasons,
        "execution-tool source",
        report.get("source"),
        {
            "repository",
            "tag",
            "tag_object",
            "commit",
            "tree",
            "archive_url",
            "archive",
            "signing_key",
            "git_object_status",
            "git_signature_status",
        },
    )
    source_records: dict[str, Any] = {}
    if source is not None:
        for field, expected in {
            "repository": EXECUTION_HEIMDALL_REPOSITORY,
            "tag": EXECUTION_HEIMDALL_TAG,
            "tag_object": EXECUTION_HEIMDALL_TAG_OBJECT,
            "commit": EXECUTION_HEIMDALL_COMMIT,
            "tree": EXECUTION_HEIMDALL_TREE,
            "archive_url": EXECUTION_HEIMDALL_ARCHIVE_URL,
        }.items():
            require_equal(reasons, f"execution-tool source {field}", source.get(field), expected)

        archive_record = validate_bound_file(
            reasons, "execution-tool source archive", evidence_root, source.get("archive")
        )
        if archive_record is not None:
            source_records["archive"] = archive_record
            require_equal(
                reasons,
                "execution-tool source archive SHA-256",
                archive_record["sha256"],
                EXECUTION_HEIMDALL_ARCHIVE_SHA256,
            )

        signing_key = require_exact_keys(
            reasons,
            "execution-tool signing key",
            source.get("signing_key"),
            {"path", "bytes", "sha256", "fingerprint"},
        )
        if signing_key is not None:
            require_equal(
                reasons,
                "execution-tool signing-key fingerprint",
                signing_key.get("fingerprint"),
                EXECUTION_HEIMDALL_SIGNING_FINGERPRINT,
            )
            key_binding = {
                field: signing_key.get(field) for field in ("path", "bytes", "sha256")
            }
            key_record = validate_bound_file(
                reasons, "execution-tool signing key", evidence_root, key_binding
            )
            if key_record is not None:
                source_records["signing_key"] = key_record

        for name in ("git_object_status", "git_signature_status"):
            record = validate_bound_file(
                reasons,
                f"execution-tool {name.replace('_', ' ')}",
                evidence_root,
                source.get(name),
            )
            if record is not None:
                source_records[name] = record
                text = read_bound_text(
                    reasons,
                    f"execution-tool {name.replace('_', ' ')}",
                    record,
                )
                if text is None:
                    continue
                if name == "git_object_status":
                    for marker in (
                        EXECUTION_HEIMDALL_TAG_OBJECT,
                        EXECUTION_HEIMDALL_COMMIT,
                        EXECUTION_HEIMDALL_TREE,
                    ):
                        if marker not in text:
                            reasons.append(
                                f"execution-tool git object status lacks marker: {marker}"
                            )
                else:
                    status_lines = [
                        line
                        for line in text.splitlines()
                        if line.startswith("[GNUPG:] ")
                    ]
                    valid_signatures: list[tuple[str, str]] = []
                    for line in status_lines:
                        fields = line.split()
                        if len(fields) >= 12 and fields[1] == "VALIDSIG":
                            signing_fingerprint = fields[2].upper()
                            primary_fingerprint = fields[-1].upper()
                            valid_signatures.append(
                                (signing_fingerprint, primary_fingerprint)
                            )
                    if len(valid_signatures) != 2:
                        reasons.append(
                            "execution-tool signature status must contain exactly "
                            "two VALIDSIG records (tag and commit)"
                        )
                    if sum(
                        line.startswith("[GNUPG:] GOODSIG ")
                        for line in status_lines
                    ) != 2:
                        reasons.append(
                            "execution-tool signature status must contain exactly "
                            "two GOODSIG records (tag and commit)"
                        )
                    for signing_fingerprint, primary_fingerprint in valid_signatures:
                        if EXECUTION_HEIMDALL_SIGNING_FINGERPRINT not in {
                            signing_fingerprint,
                            primary_fingerprint,
                        }:
                            reasons.append(
                                "execution-tool VALIDSIG is not bound to the fixed "
                                "primary fingerprint"
                            )
                    if not any(
                        line.startswith("[GNUPG:] KEYEXPIRED ")
                        for line in status_lines
                    ):
                        reasons.append(
                            "execution-tool signature status must retain the observed "
                            "KEYEXPIRED fact"
                        )

    build = require_exact_keys(
        reasons,
        "execution-tool build",
        report.get("build"),
        {
            "host",
            "patches",
            "source_export",
            "tree_manifest",
            "cmake_argv",
            "build_argv",
            "environment",
            "toolchain_manifest",
            "dependency_manifest",
            "build_log",
        },
    )
    build_records: dict[str, Any] = {}
    host: dict[str, Any] | None = None
    if build is not None:
        host = require_exact_keys(
            reasons,
            "execution-tool build host",
            build.get("host"),
            {"os", "architecture", "binary_format"},
        )
        if host is not None:
            platform_formats = {
                "linux": ("x86_64", "arm64", "ELF"),
                "darwin": ("x86_64", "arm64", "Mach-O"),
                "windows": ("x86_64", "arm64", "PE"),
            }
            host_os = host.get("os")
            if host_os not in platform_formats:
                reasons.append("execution-tool build host os is not supported")
            else:
                allowed = platform_formats[host_os]
                if host.get("architecture") not in allowed[:2]:
                    reasons.append("execution-tool build host architecture is not canonical")
                require_equal(
                    reasons,
                    "execution-tool build host binary format",
                    host.get("binary_format"),
                    allowed[2],
                )
        require_equal(reasons, "execution-tool source patches", build.get("patches"), [])
        for field in ("cmake_argv", "build_argv"):
            argv = build.get(field)
            if (
                not isinstance(argv, list)
                or not argv
                or any(not isinstance(item, str) or not item for item in argv)
            ):
                reasons.append(f"execution-tool {field} must be a non-empty string array")
            elif re.search(
                r"(?:^|\s)(?:sudo|apt(?:-get)?|dnf|yum|pacman|brew|winget)(?:\s|$)",
                " ".join(argv),
                re.IGNORECASE,
            ):
                reasons.append(
                    f"execution-tool {field} must only describe the offline build"
                )
        for name in (
            "source_export",
            "tree_manifest",
            "environment",
            "toolchain_manifest",
            "dependency_manifest",
            "build_log",
        ):
            record = validate_bound_file(
                reasons,
                f"execution-tool build {name.replace('_', ' ')}",
                evidence_root,
                build.get(name),
            )
            if record is not None:
                build_records[name] = record

    binary = require_exact_keys(
        reasons,
        "execution-tool binary",
        report.get("binary"),
        {"artifact", "format", "architecture", "version_output", "dynamic_dependencies"},
    )
    binary_record: dict[str, Any] | None = None
    binary_records: dict[str, Any] = {}
    if binary is not None:
        binary_record = validate_bound_file(
            reasons, "execution-tool binary artifact", evidence_root, binary.get("artifact")
        )
        if binary_record is not None:
            binary_records["artifact"] = binary_record
        for name in ("version_output", "dynamic_dependencies"):
            record = validate_bound_file(
                reasons,
                f"execution-tool binary {name.replace('_', ' ')}",
                evidence_root,
                binary.get(name),
            )
            if record is not None:
                binary_records[name] = record
        if host is not None:
            require_equal(
                reasons,
                "execution-tool binary format",
                binary.get("format"),
                host.get("binary_format"),
            )
            require_equal(
                reasons,
                "execution-tool binary architecture",
                binary.get("architecture"),
                host.get("architecture"),
            )
        version_record = binary_records.get("version_output")
        if version_record is not None:
            version_text = read_bound_text(
                reasons, "execution-tool binary version output", version_record
            )
            if version_text is not None and not re.search(
                r"(?:Heimdall\s+)?v2\.2\.2(?:\s|$)", version_text
            ):
                reasons.append("execution-tool version output lacks v2.2.2")

    require_distinct_bound_files(
        reasons,
        "execution-tool provenance evidence",
        {**source_records, **build_records, **binary_records},
    )

    signing_key_record = source_records.get("signing_key")
    if reasons:
        state = "fail"
        status = "fail-execution-tool-provenance"
    elif EXPECTED_EXECUTION_HEIMDALL_SIGNING_KEY_SHA256 is None:
        state = "pending"
        status = "pending-source-provenance"
    elif (
        signing_key_record is None
        or signing_key_record["sha256"]
        != EXPECTED_EXECUTION_HEIMDALL_SIGNING_KEY_SHA256
    ):
        state = "fail"
        status = "fail-execution-tool-signing-key-review"
        reasons.append("execution-tool signing key does not match the reviewed digest")
    elif EXPECTED_EXECUTION_TOOL_BINARY_SHA256 is None:
        state = "pending"
        status = "pending-binary-review"
    elif binary_record is None or binary_record["sha256"] != EXPECTED_EXECUTION_TOOL_BINARY_SHA256:
        state = "fail"
        status = "fail-execution-tool-binary-review"
        reasons.append("execution-tool binary does not match the reviewed digest")
    elif EXPECTED_EXECUTION_TOOL_PROVENANCE_REPORT_SHA256 is None:
        state = "pending"
        status = "pending-binary-review"
    elif report_file["sha256"] != EXPECTED_EXECUTION_TOOL_PROVENANCE_REPORT_SHA256:
        state = "fail"
        status = "fail-execution-tool-provenance-review"
        reasons.append("execution-tool provenance report does not match the reviewed digest")
    elif not EXECUTION_TOOL_PASS_VALIDATION_IMPLEMENTED:
        state = "pending"
        status = "pending-validator-hardening"
        reasons.append(
            "execution-tool pass remains disabled until binary parsing, real "
            "signature verification, source/build binding, and executor handoff "
            "hardening are implemented and reviewed"
        )
    else:
        state = "pass"
        status = "pass-execution-tool-provenance"

    return {
        "state": state,
        "status": status,
        "path": str(report_path),
        "report": report_file,
        "binary": binary_record,
        "host": host,
        "source_records": source_records,
        "build_records": build_records,
        "binary_records": binary_records,
        "reasons": reasons,
        "trust_boundary": (
            "This report contains locally reproducible source/build facts only. "
            "It cannot self-declare signature validity, traceability, or execution approval."
        ),
    }


def validate_execution_tool_liveness_report(
    path: Path | None,
    provenance_gate: dict[str, Any],
) -> dict[str, Any]:
    """Validate a separately authorized, read-only final-host liveness record."""

    if path is None:
        return {
            "state": "pending",
            "status": "pending-execution-tool-liveness",
            "reasons": ["execution-tool liveness report was not supplied"],
        }
    reasons: list[str] = []
    try:
        report_path = path.expanduser().resolve()
        report = load_json(report_path)
        report_file = report_record(report_path)
    except (OSError, RuntimeError, SystemExit, ValueError) as exc:
        return {
            "state": "fail",
            "status": "fail-execution-tool-liveness",
            "path": str(path),
            "report": None,
            "reasons": [str(exc)],
        }

    require_exact_keys(
        reasons,
        "execution-tool liveness report",
        report,
        {
            "schema",
            "report_type",
            "device",
            "model",
            "evidence_root",
            "provenance_report_sha256",
            "binary",
            "host",
            "collection",
            "usb",
            "execution",
            "files",
            "host_partition_writes_performed",
            "partition_uploads",
            "pit_write_performed",
            "repartition_performed",
            "skip_size_check",
            "device_writes_performed",
            "deployable",
            "explicit_device_write_authorization_recorded",
        },
    )
    for field, expected in {
        "schema": 1,
        "report_type": "sm-t860-execution-tool-read-only-liveness",
        "device": "samsung-gts6lwifi",
        "model": "SM-T860",
        "host_partition_writes_performed": False,
        "partition_uploads": [],
        "pit_write_performed": False,
        "repartition_performed": False,
        "skip_size_check": False,
        "device_writes_performed": False,
        "deployable": False,
        "explicit_device_write_authorization_recorded": False,
    }.items():
        require_equal(reasons, f"execution-tool liveness {field}", report.get(field), expected)

    evidence_root_value = report.get("evidence_root")
    evidence_root: Path | None = None
    if not isinstance(evidence_root_value, str) or not evidence_root_value:
        reasons.append("execution-tool liveness evidence_root must be a non-empty path")
    else:
        try:
            evidence_root = Path(evidence_root_value).expanduser().resolve()
        except (OSError, RuntimeError, ValueError) as exc:
            reasons.append(
                f"execution-tool liveness evidence_root cannot be resolved safely: {exc}"
            )
            evidence_root = None
        if evidence_root is not None and not evidence_root.is_dir():
            reasons.append(
                f"execution-tool liveness evidence_root is missing: {evidence_root}"
            )

    expected_provenance_report = provenance_gate.get("report")
    provenance_binary = provenance_gate.get("binary")
    provenance_host = provenance_gate.get("host")
    provenance_facts_available = (
        provenance_gate.get("state") != "fail"
        and isinstance(expected_provenance_report, dict)
        and isinstance(provenance_binary, dict)
        and isinstance(provenance_host, dict)
    )
    expected_provenance_sha = (
        expected_provenance_report.get("sha256")
        if provenance_facts_available
        else None
    )
    declared_provenance_sha = report.get("provenance_report_sha256")
    if not valid_sha256(declared_provenance_sha):
        reasons.append(
            "execution-tool liveness provenance_report_sha256 must be a SHA-256"
        )
    elif provenance_facts_available:
        require_equal(
            reasons,
            "execution-tool liveness provenance report SHA-256",
            declared_provenance_sha,
            expected_provenance_sha,
        )

    host = require_exact_keys(
        reasons,
        "execution-tool liveness host",
        report.get("host"),
        {"os", "architecture", "binary_format"},
    )
    if host is not None:
        platform_formats = {
            "linux": ("x86_64", "arm64", "ELF"),
            "darwin": ("x86_64", "arm64", "Mach-O"),
            "windows": ("x86_64", "arm64", "PE"),
        }
        host_os = host.get("os")
        if host_os not in platform_formats:
            reasons.append("execution-tool liveness host os is not supported")
        else:
            allowed = platform_formats[host_os]
            if host.get("architecture") not in allowed[:2]:
                reasons.append(
                    "execution-tool liveness host architecture is not canonical"
                )
            require_equal(
                reasons,
                "execution-tool liveness host binary format",
                host.get("binary_format"),
                allowed[2],
            )
        if provenance_facts_available:
            require_equal(reasons, "execution-tool final host", host, provenance_host)

    binary_record = validate_bound_file(
        reasons, "execution-tool liveness binary", evidence_root, report.get("binary")
    )
    if binary_record is not None and provenance_facts_available:
        require_equal(
            reasons,
            "execution-tool liveness binary SHA-256",
            binary_record.get("sha256"),
            provenance_binary.get("sha256") if isinstance(provenance_binary, dict) else None,
        )

    collection = require_exact_keys(
        reasons,
        "execution-tool liveness collection",
        report.get("collection"),
        {"started_at_utc", "completed_at_utc"},
    )
    collection_start: datetime | None = None
    collection_end: datetime | None = None
    if collection is not None:
        for field in ("started_at_utc", "completed_at_utc"):
            value = collection.get(field)
            if not isinstance(value, str):
                reasons.append(f"execution-tool liveness collection lacks {field}")
                continue
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                reasons.append(f"execution-tool liveness {field} is not ISO 8601")
                continue
            if parsed.tzinfo is None:
                reasons.append(f"execution-tool liveness {field} lacks a timezone")
                continue
            if field == "started_at_utc":
                collection_start = parsed.astimezone(timezone.utc)
            else:
                collection_end = parsed.astimezone(timezone.utc)
        if collection_start is not None and collection_end is not None:
            if collection_end < collection_start:
                reasons.append("execution-tool liveness collection window is reversed")
            elif collection_end - collection_start > timedelta(minutes=15):
                reasons.append("execution-tool liveness collection window exceeds 15 minutes")

    usb = require_exact_keys(
        reasons,
        "execution-tool liveness usb",
        report.get("usb"),
        {"vid_pid", "before", "after"},
    )
    usb_records: dict[str, Any] = {}
    if usb is not None:
        require_equal(reasons, "execution-tool liveness USB VID:PID", usb.get("vid_pid"), "04e8:685d")
        for phase in ("before", "after"):
            record = validate_bound_file(
                reasons,
                f"execution-tool liveness USB {phase}",
                evidence_root,
                usb.get(phase),
            )
            if record is not None:
                usb_records[phase] = record
                text = read_bound_text(
                    reasons, f"execution-tool liveness USB {phase}", record
                )
                if text is None:
                    continue
                exact_lines = {line.strip() for line in text.splitlines()}
                for marker in ("USB_DEVICE_COUNT:1", "USB_VID_PID:04e8:685d"):
                    if marker not in exact_lines:
                        reasons.append(
                            f"execution-tool liveness USB {phase} lacks marker: {marker}"
                        )

    files = require_exact_keys(
        reasons,
        "execution-tool liveness files",
        report.get("files"),
        {"stdout", "stderr", "pit", "stock_pit", "pit_comparison", "environment"},
    )
    file_records: dict[str, Any] = {}
    if files is not None:
        for name in files:
            record = validate_bound_file(
                reasons,
                f"execution-tool liveness {name.replace('_', ' ')}",
                evidence_root,
                files.get(name),
            )
            if record is not None:
                file_records[name] = record

    require_distinct_bound_files(
        reasons,
        "execution-tool liveness evidence",
        {**usb_records, **file_records},
    )

    current_pit_record = file_records.get("pit")
    stock_pit_record = file_records.get("stock_pit")
    current_pit_path = Path(current_pit_record["path"]) if current_pit_record else None
    stock_pit_path = Path(stock_pit_record["path"]) if stock_pit_record else None
    if stock_pit_record is not None:
        require_equal(
            reasons,
            "execution-tool liveness stock PIT SHA-256",
            stock_pit_record["sha256"],
            STOCK_CRITICAL["GTS6LWIFI_EUR_OPEN.pit"]["sha256"],
        )
    if current_pit_path is not None and stock_pit_path is not None:
        if current_pit_path == stock_pit_path:
            reasons.append("execution-tool liveness PIT must differ from stock PIT")
        else:
            current_stat = stat_bound_file(
                reasons, "execution-tool liveness PIT", current_pit_record
            )
            stock_stat = stat_bound_file(
                reasons, "execution-tool liveness stock PIT", stock_pit_record
            )
            if (
                current_stat is not None
                and stock_stat is not None
                and current_stat.st_dev == stock_stat.st_dev
                and current_stat.st_ino == stock_stat.st_ino
            ):
                reasons.append("execution-tool liveness PIT must use an independent inode")
            current_pit_data = read_bound_bytes(
                reasons, "execution-tool liveness PIT", current_pit_record
            )
            stock_pit_data = read_bound_bytes(
                reasons, "execution-tool liveness stock PIT", stock_pit_record
            )
            if current_pit_data is not None and stock_pit_data is not None:
                current_structure = pit_structure_record(current_pit_data)
                stock_structure = pit_structure_record(stock_pit_data)
                for field, expected in {
                    "magic": "0x12349876",
                    "entry_count": 76,
                    "header": "COM_TAR2",
                    "cpu_bootloader_tag": "SM8150",
                    "logic_unit_count": 4,
                    "entries_parsed": 76,
                }.items():
                    require_equal(
                        reasons,
                        f"execution-tool liveness PIT {field}",
                        current_structure.get(field),
                        expected,
                    )
                require_equal(
                    reasons,
                    "execution-tool liveness PIT partition layout",
                    current_structure.get("entries"),
                    stock_structure.get("entries"),
                )

    execution = require_exact_keys(
        reasons,
        "execution-tool liveness execution",
        report.get("execution"),
        {
            "binary_argv",
            "launcher_argv",
            "watchdog_argv",
            "exit_code",
            "timed_out",
            "attempt_count",
            "output_preexisted",
            "automatic_retry",
            "automatic_reboot",
        },
    )
    if execution is not None:
        binary_path = Path(binary_record["path"]) if binary_record is not None else None
        expected_binary_argv = (
            [
                str(binary_path),
                "download-pit",
                "--output",
                str(current_pit_path),
                "--no-reboot",
                "--stdout-errors",
            ]
            if binary_path is not None and current_pit_path is not None
            else None
        )
        require_equal(
            reasons,
            "execution-tool liveness binary argv",
            execution.get("binary_argv"),
            expected_binary_argv,
        )
        for field in ("launcher_argv", "watchdog_argv"):
            argv = execution.get(field)
            if (
                not isinstance(argv, list)
                or not argv
                or any(not isinstance(item, str) or not item for item in argv)
            ):
                reasons.append(f"execution-tool liveness {field} must be a non-empty string array")
            elif expected_binary_argv is not None and not any(
                argv[index : index + len(expected_binary_argv)] == expected_binary_argv
                for index in range(len(argv) - len(expected_binary_argv) + 1)
            ):
                reasons.append(f"execution-tool liveness {field} does not bind exact binary argv")
        for field, expected in {
            "exit_code": 0,
            "timed_out": False,
            "attempt_count": 1,
            "output_preexisted": False,
            "automatic_retry": False,
            "automatic_reboot": False,
        }.items():
            require_equal(reasons, f"execution-tool liveness {field}", execution.get(field), expected)
        argv_text = json.dumps(execution, ensure_ascii=False)
        if re.search(r"(?:--wait|--resume|--repartition|--skip-size-check|\bflash\b|\bupload\b)", argv_text, re.IGNORECASE):
            reasons.append("execution-tool liveness argv contains a forbidden action or flag")

    output_text = ""
    for name in ("stdout", "stderr"):
        record = file_records.get(name)
        if record is not None:
            text = read_bound_text(
                reasons, f"execution-tool liveness {name}", record
            )
            if text is not None:
                output_text += text
    if re.search(
        r"Uploading\s|upload successful|(?:^|\s)(?:flash|--repartition|--skip-size-check)(?:\s|=|$)|Repartition\s",
        output_text,
        re.IGNORECASE | re.MULTILINE,
    ):
        reasons.append("execution-tool liveness output contains a write/repartition marker")
    for marker in ("Session begun.", "PIT file download successful."):
        if marker not in {line.strip() for line in output_text.splitlines()}:
            reasons.append(
                f"execution-tool liveness output lacks success marker: {marker}"
            )
    environment_record = file_records.get("environment")
    if environment_record is not None:
        environment_text = read_bound_text(
            reasons, "execution-tool liveness environment", environment_record
        )
        if environment_text is not None and re.search(
            r"^(?:LD_|DYLD_)[^=]*=", environment_text, re.MULTILINE
        ):
            reasons.append("execution-tool liveness environment contains dynamic-loader injection variables")

    if collection_start is not None and collection_end is not None:
        for label, record in {
            **usb_records,
            **file_records,
        }.items():
            stat = stat_bound_file(
                reasons, f"execution-tool liveness {label}", record
            )
            if stat is None:
                continue
            mtime = datetime.fromtimestamp(stat.st_mtime, timezone.utc)
            if not (
                collection_start - timedelta(seconds=5)
                <= mtime
                <= collection_end + timedelta(seconds=5)
            ):
                reasons.append(f"execution-tool liveness {label} mtime is outside collection window")

    if reasons:
        state = "fail"
        status = "fail-execution-tool-liveness"
    elif provenance_gate.get("state") != "pass":
        state = "pending"
        status = provenance_gate.get("status", "pending-source-provenance")
        reasons.append(
            "execution-tool liveness is structurally valid but cannot be reviewed "
            "before provenance and the exact binary pass independent review"
        )
    elif EXPECTED_EXECUTION_TOOL_LIVENESS_REPORT_SHA256 is None:
        state = "pending"
        status = "pending-liveness-review"
    elif report_file["sha256"] != EXPECTED_EXECUTION_TOOL_LIVENESS_REPORT_SHA256:
        state = "fail"
        status = "fail-execution-tool-liveness-review"
        reasons.append("execution-tool liveness report does not match the reviewed digest")
    else:
        state = "pass"
        status = "pass-execution-tool-liveness"

    return {
        "state": state,
        "status": status,
        "path": str(report_path),
        "report": report_file,
        "binary": binary_record,
        "host": host,
        "usb_records": usb_records,
        "file_records": file_records,
        "reasons": reasons,
        "trust_boundary": (
            "This is a read-only download-pit liveness record for one exact host "
            "binary. It is not a flash test, deployment proof, or write authorization."
        ),
    }


def validate_execution_tool_gate(
    provenance_path: Path | None, liveness_path: Path | None
) -> dict[str, Any]:
    provenance_gate = validate_execution_tool_provenance_report(provenance_path)
    liveness_gate = validate_execution_tool_liveness_report(
        liveness_path, provenance_gate
    )
    if provenance_gate.get("state") == "fail" or liveness_gate.get("state") == "fail":
        state = "fail"
        status = "fail-traceable-execution-transport"
    elif provenance_gate.get("state") == "pass" and liveness_gate.get("state") == "pass":
        state = "pass"
        status = "pass-traceable-execution-transport"
    else:
        state = "pending"
        status = (
            provenance_gate.get("status")
            if provenance_gate.get("state") != "pass"
            else liveness_gate.get("status")
        )
    return {
        "state": state,
        "status": status,
        "binary": liveness_gate.get("binary") if state == "pass" else None,
        "candidate_binary": provenance_gate.get("binary"),
        "host": provenance_gate.get("host"),
        "provenance": provenance_gate,
        "liveness": liveness_gate,
        "reasons": provenance_gate.get("reasons", []) + liveness_gate.get("reasons", []),
        "trust_boundary": (
            "Historical Heimdall 2.0.2 evidence is never promoted into this gate. "
            "Only a reviewed source build and a new same-binary final-host liveness can pass."
        ),
    }


def validate_recovery_trigger_report(
    path: Path | None, transport_gate: dict[str, Any]
) -> dict[str, Any]:
    """Gate a future no-partition-flash Recovery trigger drill.

    A report cannot pass until its exact digest is pinned by an independent
    code review.  This deliberately avoids a self-attested status field or a
    manually flipped Boolean becoming execution authority.
    """

    if path is None:
        return pending_gate(
            "current-session no-partition-flash Recovery trigger report was not supplied"
        )
    report_path = path.resolve()
    reasons: list[str] = []
    try:
        report = load_json(report_path)
        report_record_value = report_record(report_path)
    except SystemExit as exc:
        return {
            "state": "fail",
            "path": str(report_path),
            "report": None,
            "protocol_id": RECOVERY_TRIGGER_PROTOCOL_ID,
            "reasons": [str(exc)],
        }
    if transport_gate.get("state") != "pass":
        reasons.append(
            "Recovery trigger report cannot pass before recovery transport gate passes"
        )
    expected_top_level_keys = {
        "schema",
        "report_type",
        "status",
        "device",
        "model",
        "bootloader",
        "protocol_id",
        "transport_report_sha256",
        "evidence_root",
        "collection",
        "files",
        "precondition",
        "operator_observation",
        "recovery_evidence",
        "return_to_android",
        "stop_conditions",
        "host_partition_writes_performed",
        "partition_uploads",
        "pit_write_performed",
        "repartition_performed",
        "storage_immutability_claimed",
        "expected_incidental_metadata_effects",
        "attempt_count",
        "deployable",
        "explicit_device_write_authorization_recorded",
    }
    require_equal(
        reasons,
        "Recovery trigger report keys",
        set(report),
        expected_top_level_keys,
    )
    for field, expected in {
        "schema": 1,
        "report_type": "sm-t860-recovery-boot-trigger-drill",
        "status": "pass-no-partition-flash-recovery-trigger-drill",
        "device": "samsung-gts6lwifi",
        "model": "SM-T860",
        "bootloader": "T860XXS5DWH1",
        "protocol_id": RECOVERY_TRIGGER_PROTOCOL_ID,
        "host_partition_writes_performed": False,
        "partition_uploads": [],
        "pit_write_performed": False,
        "repartition_performed": False,
        "storage_immutability_claimed": False,
        "expected_incidental_metadata_effects": [
            "boot/recovery cause history",
            "Samsung param reset/update",
            "recovery log/cache or BCB maintenance",
        ],
        "attempt_count": 1,
        "deployable": False,
        "explicit_device_write_authorization_recorded": False,
    }.items():
        require_equal(reasons, f"Recovery trigger {field}", report.get(field), expected)

    transport_report = transport_gate.get("report")
    expected_transport_sha = (
        transport_report.get("sha256") if isinstance(transport_report, dict) else None
    )
    require_equal(
        reasons,
        "Recovery trigger transport report binding",
        report.get("transport_report_sha256"),
        expected_transport_sha,
    )

    evidence_root_value = report.get("evidence_root")
    evidence_root: Path | None = None
    if not isinstance(evidence_root_value, str):
        reasons.append("Recovery trigger report lacks an evidence_root")
    else:
        try:
            evidence_root = Path(evidence_root_value).expanduser().resolve()
        except (OSError, ValueError):
            reasons.append("Recovery trigger evidence_root is not a valid path")
            evidence_root = None
        if evidence_root is not None and not evidence_root.is_dir():
            reasons.append(
                f"Recovery trigger evidence root is missing: {evidence_root}"
            )

    collection_start: datetime | None = None
    collection_end: datetime | None = None
    collection = report.get("collection")
    if not isinstance(collection, dict) or set(collection) != {
        "started_at_utc",
        "completed_at_utc",
    }:
        reasons.append("Recovery trigger collection window has invalid keys")
    else:
        for field in ("started_at_utc", "completed_at_utc"):
            value = collection.get(field)
            if not isinstance(value, str):
                reasons.append(f"Recovery trigger collection lacks {field}")
                continue
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                reasons.append(f"Recovery trigger collection {field} is not ISO 8601")
                continue
            if parsed.tzinfo is None:
                reasons.append(f"Recovery trigger collection {field} lacks a timezone")
                continue
            if field == "started_at_utc":
                collection_start = parsed.astimezone(timezone.utc)
            else:
                collection_end = parsed.astimezone(timezone.utc)
        if collection_start is not None and collection_end is not None:
            if collection_end < collection_start:
                reasons.append("Recovery trigger collection window is reversed")
            elif collection_end - collection_start > timedelta(minutes=15):
                reasons.append("Recovery trigger collection window exceeds 15 minutes")

    required_evidence_markers = {
        "recovery_getprop": [
            "ro.boot.boot_recovery=1",
            "ro.product.model=SM-T860",
            "ro.boot.bootloader=T860XXS5DWH1",
            "sys.boot_completed=0",
            "ro.twrp.boot=1",
            "ro.twrp.version=",
        ],
        "android_getprop": [
            "ro.product.model=SM-T860",
            "ro.boot.bootloader=T860XXS5DWH1",
            "sys.boot_completed=1",
        ],
        "usb_enumeration": [
            "USB_VID_PID:04e8:685d",
            "UNIQUE_DOWNLOAD_DEVICE:true",
        ],
        "operator_transcript": [
            "PROTOCOL_ID:" + RECOVERY_TRIGGER_PROTOCOL_ID,
            "POWER_HELD_ACROSS_DISPLAY_BLACK_EDGE:true",
            "VOLUME_DOWN_RELEASED_BEFORE_VOLUME_UP_PRESSED:true",
            "BOTH_VOLUME_KEYS_ACTIVE:false",
            "ATTEMPT_COUNT:1",
        ],
    }
    files = report.get("files")
    if not isinstance(files, dict) or set(files) != set(required_evidence_markers):
        reasons.append("Recovery trigger evidence file ids do not match the fixed set")
    elif evidence_root is not None:
        for label, markers in required_evidence_markers.items():
            item = files.get(label)
            if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
                reasons.append(f"Recovery trigger {label} binding is invalid")
                continue
            relative = item.get("path")
            declared_hash = item.get("sha256")
            if not isinstance(relative, str) or Path(relative).is_absolute():
                reasons.append(f"Recovery trigger {label} path must be relative")
                continue
            if not valid_sha256(declared_hash):
                reasons.append(f"Recovery trigger {label} lacks a SHA-256")
            try:
                evidence_path = (evidence_root / relative).resolve()
            except (OSError, ValueError):
                reasons.append(f"Recovery trigger {label} path is invalid")
                continue
            if evidence_root not in evidence_path.parents or not evidence_path.is_file():
                reasons.append(f"Recovery trigger {label} path escapes or is missing")
                continue
            evidence_record = file_record(evidence_path)
            require_equal(
                reasons,
                f"Recovery trigger {label} local SHA-256",
                evidence_record["sha256"],
                declared_hash,
            )
            evidence_mtime = datetime.fromtimestamp(
                evidence_path.stat().st_mtime, timezone.utc
            )
            if (
                collection_start is not None
                and collection_end is not None
                and not (
                    collection_start - timedelta(seconds=5)
                    <= evidence_mtime
                    <= collection_end + timedelta(seconds=5)
                )
            ):
                reasons.append(
                    f"Recovery trigger {label} mtime is outside the collection window"
                )
            evidence_text = evidence_path.read_text(
                encoding="utf-8", errors="replace"
            )
            for marker in markers:
                if marker == "ro.twrp.version=":
                    if not re.search(r"(?m)^ro\.twrp\.version=\S+$", evidence_text):
                        reasons.append(
                            "Recovery trigger recovery_getprop lacks a nonempty TWRP version"
                        )
                elif marker not in evidence_text:
                    reasons.append(f"Recovery trigger {label} lacks marker: {marker}")

    precondition = report.get("precondition")
    expected_transport_log_sha: object = None
    expected_transport_pit_sha: object = None
    transport_log = transport_gate.get("current_session_log")
    transport_pit = transport_gate.get("current_session_pit")
    if isinstance(transport_log, dict):
        expected_transport_log_sha = transport_log.get("sha256")
    if isinstance(transport_pit, dict):
        expected_transport_pit_sha = transport_pit.get("sha256")
    require_equal(
        reasons,
        "Recovery trigger precondition",
        precondition,
        {
            "source_state": "download-mode-after-no-reboot",
            "protocol_end_state": "EndSession(false)",
            "transport_log_sha256": expected_transport_log_sha,
            "transport_pit_sha256": expected_transport_pit_sha,
            "usb_vid_pid": "04e8:685d",
            "host_flash_command_executed": False,
        },
    )

    require_equal(
        reasons,
        "Recovery trigger operator observation",
        report.get("operator_observation"),
        {
            "requires_human": True,
            "usb_connected": True,
            "power_held_across_display_black_edge": True,
            "volume_down_released_before_volume_up_pressed": True,
            "both_volume_keys_active": False,
            "transition_timing": "immediate-on-display-black-edge",
        },
    )
    require_equal(
        reasons,
        "Recovery trigger evidence",
        report.get("recovery_evidence"),
        {
            "adb_observed": True,
            "ro.boot.boot_recovery": "1",
            "ro.product.model": "SM-T860",
            "ro.boot.bootloader": "T860XXS5DWH1",
            "sys.boot_completed": "0",
            "twrp_boot": "1",
            "twrp_version_nonempty": True,
        },
    )
    require_equal(
        reasons,
        "Recovery trigger Android return evidence",
        report.get("return_to_android"),
        {
            "same_device_identity": True,
            "ro.product.model": "SM-T860",
            "ro.boot.bootloader": "T860XXS5DWH1",
            "sys.boot_completed": "1",
        },
    )
    stop_conditions = report.get("stop_conditions")
    if (
        not isinstance(stop_conditions, list)
        or not all(isinstance(item, str) for item in stop_conditions)
        or len(stop_conditions) != len(RECOVERY_TRIGGER_REQUIRED_STOP_CONDITIONS)
        or set(stop_conditions) != RECOVERY_TRIGGER_REQUIRED_STOP_CONDITIONS
    ):
        reasons.append(
            "Recovery trigger stop conditions do not match the fixed set"
        )
    if EXPECTED_RECOVERY_TRIGGER_REPORT_SHA256 is None:
        reasons.append(
            "no Recovery trigger report digest has been independently reviewed and pinned"
        )
    else:
        require_equal(
            reasons,
            "Recovery trigger report SHA-256",
            report_record_value["sha256"],
            EXPECTED_RECOVERY_TRIGGER_REPORT_SHA256,
        )
    return {
        "state": "pass" if not reasons else "fail",
        "path": str(report_path),
        "report": report_record_value,
        "protocol_id": RECOVERY_TRIGGER_PROTOCOL_ID,
        "reasons": reasons,
        "trust_boundary": (
            "A future pass may prove only a reviewed physical trigger from a "
            "post-EndSession(false) Download Mode state. It is not a UEFI boot "
            "result, a storage-immutability claim, or device-write authorization."
        ),
    }


def validate_windows_report(path: Path | None) -> dict[str, Any]:
    if path is None:
        return pending_gate("target ARM64 Windows media report was not supplied")
    report_path = path.resolve()
    report = load_json(report_path)
    reasons: list[str] = []
    for field, expected in {
        "schema": 2,
        "validation_profile": "sm-t860-windows-sd-media-v1",
        "device": "SM-T860",
        "status": "pass-windows-sd-boot-prerequisites",
        "architecture": "ARM64",
        "check_set_complete": True,
        "deployable": False,
        "media_writes_performed": False,
        "device_writes_performed": False,
    }.items():
        require_equal(reasons, f"Windows report {field}", report.get(field), expected)

    checks = report.get("checks")
    by_id: dict[str, dict[str, Any]] = {}
    if not isinstance(checks, list):
        reasons.append("Windows report checks must be a list")
    else:
        if len(checks) != len(WINDOWS_CHECK_IDS):
            reasons.append("Windows report must contain exactly the fixed 18 checks")
        for check in checks:
            if not isinstance(check, dict) or not isinstance(check.get("id"), str):
                reasons.append("every Windows check must be an object with a stable id")
                continue
            check_id = check["id"]
            if check_id in by_id:
                reasons.append(f"duplicate Windows check id: {check_id}")
            by_id[check_id] = check
    missing_ids = sorted(WINDOWS_CHECK_IDS - by_id.keys())
    unexpected_ids = sorted(by_id.keys() - WINDOWS_CHECK_IDS)
    if missing_ids:
        reasons.append(f"Windows report check ids missing: {missing_ids}")
    if unexpected_ids:
        reasons.append(f"Windows report has unexpected check ids: {unexpected_ids}")
    declared_ids = report.get("required_check_ids")
    if (
        not isinstance(declared_ids, list)
        or len(declared_ids) != len(WINDOWS_CHECK_IDS)
        or {item for item in declared_ids if isinstance(item, str)}
        != WINDOWS_CHECK_IDS
    ):
        reasons.append("Windows report required_check_ids do not match the fixed set")
    require_equal(reasons, "Windows report missing_check_ids", report.get("missing_check_ids"), [])
    require_equal(reasons, "Windows report unexpected_check_ids", report.get("unexpected_check_ids"), [])
    require_equal(reasons, "Windows report duplicate_check_ids", report.get("duplicate_check_ids"), [])
    require_equal(
        reasons,
        "Windows report validator SHA-256",
        report.get("validator_sha256"),
        EXPECTED_WINDOWS_VALIDATOR_SHA256,
    )
    for check_id in sorted(WINDOWS_CHECK_IDS & by_id.keys()):
        check = by_id[check_id]
        if set(check) != {"id", "pass", "reason", "evidence"}:
            reasons.append(f"Windows check keys do not match the fixed schema: {check_id}")
        if check.get("pass") is not True:
            reasons.append(f"Windows check did not pass: {check_id}")
        if check.get("reason") is not None:
            reasons.append(f"passing Windows check has a failure reason: {check_id}")
        if not isinstance(check.get("evidence"), dict):
            reasons.append(f"Windows check lacks structured evidence: {check_id}")
            check["evidence"] = {}

    for check_id in WINDOWS_PE_CHECK_IDS:
        evidence = by_id.get(check_id, {}).get("evidence", {})
        if str(evidence.get("machine")).lower() != "0xaa64":
            reasons.append(f"Windows PE check is not ARM64: {check_id}")
        if str(evidence.get("optional_header_magic")).lower() != "0x020b":
            reasons.append(f"Windows PE check is not PE32+: {check_id}")
        if not valid_sha256(evidence.get("sha256")):
            reasons.append(f"Windows PE check lacks a SHA-256: {check_id}")
        if not isinstance(evidence.get("bytes"), int) or evidence.get("bytes", 0) <= 0:
            reasons.append(f"Windows PE check lacks a positive size: {check_id}")

    same_disk = by_id.get("media.same_physical_disk", {}).get("evidence", {})
    if (
        not isinstance(same_disk.get("windows_disk_number"), int)
        or same_disk.get("windows_disk_number") != same_disk.get("esp_disk_number")
        or not isinstance(same_disk.get("windows_partition_number"), int)
        or not isinstance(same_disk.get("esp_partition_number"), int)
        or same_disk.get("windows_partition_number")
        == same_disk.get("esp_partition_number")
        or not isinstance(same_disk.get("disk_unique_id"), str)
        or not isinstance(same_disk.get("disk_bytes"), int)
        or same_disk.get("disk_bytes", 0) <= 0
    ):
        reasons.append("media report does not bind Windows and ESP to distinct partitions on one disk")
    target_safety = by_id.get("media.target_disk_safety", {}).get("evidence", {})
    if (
        str(target_safety.get("bus_type")).upper() not in ("USB", "SD", "MMC")
        or target_safety.get("disk_is_boot") is not False
        or target_safety.get("disk_is_system") is not False
        or target_safety.get("disk_has_boot_or_system_partition") is not False
        or not isinstance(target_safety.get("disk_partition_count"), int)
        or target_safety.get("disk_partition_count", 0) < 2
        or target_safety.get("windows_is_boot") is not False
        or target_safety.get("windows_is_system") is not False
        or target_safety.get("esp_is_boot") is not False
        or target_safety.get("esp_is_system") is not False
        or not isinstance(target_safety.get("host_system_drive"), str)
        or not target_safety.get("host_system_drive").strip()
    ):
        reasons.append("Windows media report does not prove a non-system USB/SD/MMC target")
    windows_media = by_id.get("media.windows_ntfs", {}).get("evidence", {})
    windows_letter = str(windows_media.get("drive_letter", "")).upper()
    if (
        str(windows_media.get("file_system")).upper() != "NTFS"
        or re.fullmatch(r"[A-Z]", windows_letter) is None
    ):
        reasons.append("Windows media evidence is not NTFS")
    esp_media = by_id.get("media.esp_fat32", {}).get("evidence", {})
    esp_letter = str(esp_media.get("drive_letter", "")).upper()
    if (
        str(esp_media.get("file_system")).upper() != "FAT32"
        or re.fullmatch(r"[A-Z]", esp_letter) is None
        or esp_letter == windows_letter
    ):
        reasons.append("ESP media evidence is not FAT32")
    expected_windows_root = f"{windows_letter}:\\"
    expected_esp_root = f"{esp_letter}:\\"
    require_equal(
        reasons,
        "Windows report windows_partition",
        str(report.get("windows_partition", "")).upper(),
        expected_windows_root,
    )
    require_equal(
        reasons,
        "Windows report efi_system_partition",
        str(report.get("efi_system_partition", "")).upper(),
        expected_esp_root,
    )
    esp_gpt = by_id.get("media.esp_gpt_type", {}).get("evidence", {})
    expected_esp_guid = "c12a7328-f81f-11d2-ba4b-00a0c93ec93b"
    if (
        str(esp_gpt.get("partition_style")).upper() != "GPT"
        or str(esp_gpt.get("gpt_type")).lower() != expected_esp_guid
        or str(esp_gpt.get("expected_gpt_type")).lower() != expected_esp_guid
    ):
        reasons.append("ESP evidence is not the GPT EFI System Partition type")

    efi_identity = by_id.get("efi.boot_files_identical", {}).get("evidence", {})
    efi_hashes = [
        efi_identity.get("source_sha256"),
        efi_identity.get("esp_boot_manager_sha256"),
        efi_identity.get("fallback_sha256"),
    ]
    if not all(valid_sha256(value) for value in efi_hashes) or len(set(efi_hashes)) != 1:
        reasons.append("Windows source, ESP boot manager, and BOOTAA64 are not hash-identical")
    for identity_field, pe_check_id in {
        "source_sha256": "pe.bootmgfw_source_arm64",
        "esp_boot_manager_sha256": "pe.bootmgfw_esp_arm64",
        "fallback_sha256": "pe.bootaa64_arm64",
    }.items():
        require_equal(
            reasons,
            f"EFI identity {identity_field} binding",
            efi_identity.get(identity_field),
            by_id.get(pe_check_id, {}).get("evidence", {}).get("sha256"),
        )

    inf_evidence = by_id.get("inf.qcom2466_mapping", {}).get("evidence", {})
    if not valid_sha256(inf_evidence.get("sha256")):
        reasons.append("sdbus.inf mapping check lacks a SHA-256")
    if not isinstance(inf_evidence.get("matching_line"), str) or not re.search(
        r"SDHostQualcomm8974Std\s*,\s*ACPI\\QCOM2466",
        inf_evidence.get("matching_line", ""),
        re.IGNORECASE,
    ):
        reasons.append("sdbus.inf check lacks the exact QCOM2466 mapping evidence")
    inf_section = inf_evidence.get("section")
    manufacturer_line = inf_evidence.get("manufacturer_decoration_line")
    declared_sections = inf_evidence.get("declared_arm64_sections")
    if (
        not isinstance(inf_section, str)
        or not isinstance(declared_sections, list)
        or inf_section not in declared_sections
        or not isinstance(manufacturer_line, str)
        or re.search(r"NTarm64(?:\.[0-9.]+)?", manufacturer_line, re.IGNORECASE)
        is None
    ):
        reasons.append(
            "sdbus.inf mapping is not bound to a Manufacturer-declared ARM64 model section"
        )

    qcom_manifest = by_id.get("manifest.sdbus_qcom2466", {}).get("evidence", {})
    if not valid_sha256(qcom_manifest.get("sha256")):
        reasons.append("ARM64 sdbus QCOM2466 manifest check lacks a SHA-256")
    if qcom_manifest.get("configuration") != "SDHostQualcomm8974Std":
        reasons.append("ARM64 sdbus manifest lacks the Qualcomm host configuration")
    if not isinstance(qcom_manifest.get("descriptor_key"), str) or not qcom_manifest.get(
        "descriptor_key", ""
    ).lower().endswith(r"\descriptors\acpi\qcom2466"):
        reasons.append("ARM64 sdbus manifest lacks the QCOM2466 descriptor key")
    if not isinstance(qcom_manifest.get("candidate_count"), int) or qcom_manifest.get(
        "candidate_count", 0
    ) < 1:
        reasons.append("ARM64 sdbus manifest check has no candidates")
    for check_id, service in (
        ("manifest.sdbus_bootflags", "sdbus"),
        ("manifest.sdstor_bootflags", "sdstor"),
    ):
        evidence = by_id.get(check_id, {}).get("evidence", {})
        if not valid_sha256(evidence.get("sha256")):
            reasons.append(f"{service} manifest check lacks a SHA-256")
        if str(evidence.get("boot_flags")).lower() not in ("0x8", "0x00000008", "8"):
            reasons.append(f"{service} manifest does not record BootFlags=0x8")
        if not isinstance(evidence.get("registry_key"), str) or not evidence.get(
            "registry_key", ""
        ).lower().endswith(rf"\services\{service}"):
            reasons.append(f"{service} manifest BootFlags are not bound to its service key")
    sdbus_boot_manifest = by_id.get(
        "manifest.sdbus_bootflags", {}
    ).get("evidence", {})
    if (
        not isinstance(qcom_manifest.get("path"), str)
        or not qcom_manifest.get("path")
        or qcom_manifest.get("path") != sdbus_boot_manifest.get("path")
        or qcom_manifest.get("sha256") != sdbus_boot_manifest.get("sha256")
    ):
        reasons.append("QCOM2466 descriptor and sdbus BootFlags are not bound to one manifest")

    bcd_regf = by_id.get("bcd.regf", {}).get("evidence", {})
    if bcd_regf.get("signature") != "regf" or not valid_sha256(bcd_regf.get("sha256")):
        reasons.append("BCD check lacks a valid regf signature and SHA-256")
    if not isinstance(bcd_regf.get("bytes"), int) or bcd_regf.get("bytes", 0) < 4096:
        reasons.append("BCD store is too small")
    bcd_semantic = by_id.get("bcd.semantic", {}).get("evidence", {})
    if (
        bcd_semantic.get("exit_code") != 0
        or bcd_semantic.get("bootmgr_exit_code") != 0
        or bcd_semantic.get("default_osloader_exit_code") != 0
        or bcd_semantic.get("bootmgr_has_bootmgfw_path") is not True
        or bcd_semantic.get("bootmgr_has_expected_esp_device") is not True
        or bcd_semantic.get("default_osloader_has_winload_path") is not True
        or bcd_semantic.get("default_osloader_has_expected_windows_device")
        is not True
        or bcd_semantic.get("default_osloader_has_expected_windows_osdevice")
        is not True
        or bcd_semantic.get("default_osloader_has_windows_systemroot") is not True
        or not re.fullmatch(
            r"partition=[A-Z]:",
            str(bcd_semantic.get("expected_esp_partition", "")),
        )
        or not re.fullmatch(
            r"partition=[A-Z]:",
            str(bcd_semantic.get("expected_windows_partition", "")),
        )
        or bcd_semantic.get("expected_esp_partition") != f"partition={esp_letter}:"
        or bcd_semantic.get("expected_windows_partition")
        != f"partition={windows_letter}:"
    ):
        reasons.append(
            "BCD semantic check is not bound to the audited ESP and Windows volumes"
        )

    return {
        "state": "pass" if not reasons else "fail",
        "path": str(report_path),
        "report": report_record(report_path),
        "reasons": reasons,
        "required_check_ids": sorted(WINDOWS_CHECK_IDS),
    }


def validate_stock_recovery(
    path: Path | None, critical_dir: Path | None
) -> dict[str, Any]:
    if path is None:
        return pending_gate("stock SM-T860 recovery report was not supplied")
    report_path = path.resolve()
    report = load_json(report_path)
    reasons: list[str] = []
    for field, expected in {
        "schema": 1,
        "model": "SM-T860",
        "region": "XAR",
        "firmware_version": STOCK_VERSION,
        "archive_bytes": STOCK_ARCHIVE_BYTES,
        "archive_sha256": STOCK_ARCHIVE_SHA256,
        "device_writes_performed": False,
        "status": "pass-stock-recovery-archive",
    }.items():
        require_equal(reasons, f"stock report {field}", report.get(field), expected)

    members = report.get("members")
    member_by_name: dict[str, dict[str, Any]] = {}
    if not isinstance(members, list) or len(members) != len(STOCK_MEMBERS):
        reasons.append("stock report must contain exactly the four expected tar.md5 members")
    else:
        for member in members:
            if not isinstance(member, dict) or not isinstance(member.get("name"), str):
                reasons.append("stock report member lacks a name")
                continue
            member_by_name[member["name"]] = member
    if set(member_by_name) != set(STOCK_MEMBERS):
        reasons.append("stock report member names do not match the fixed DWH1 archive")
    for name, expected_md5 in STOCK_MEMBERS.items():
        member = member_by_name.get(name, {})
        if member.get("status") != "pass":
            reasons.append(f"stock member did not pass: {name}")
        if member.get("embedded_tar_md5") != expected_md5:
            reasons.append(f"stock member embedded MD5 mismatch: {name}")

    archive_value = report.get("archive")
    archive_record: dict[str, Any] | None = None
    if not isinstance(archive_value, str):
        reasons.append("stock report does not name the local source archive")
    else:
        archive_path = Path(archive_value).expanduser().resolve()
        if not archive_path.is_file():
            reasons.append(f"stock source archive is missing: {archive_path}")
        else:
            archive_record = file_record(archive_path)
            require_equal(
                reasons,
                "stock source archive bytes",
                archive_record["bytes"],
                STOCK_ARCHIVE_BYTES,
            )
            require_equal(
                reasons,
                "stock source archive SHA-256",
                archive_record["sha256"],
                STOCK_ARCHIVE_SHA256,
            )

    critical_root = (
        critical_dir.resolve() if critical_dir is not None else report_path.parent / "critical"
    )
    critical_records: dict[str, Any] = {}
    for name, expected in STOCK_CRITICAL.items():
        artifact_path = critical_root / name
        if not artifact_path.is_file():
            reasons.append(f"stock critical artifact is missing: {artifact_path}")
            continue
        record = file_record(artifact_path)
        critical_records[name] = record
        require_equal(reasons, f"{name} bytes", record["bytes"], expected["bytes"])
        require_equal(reasons, f"{name} SHA-256", record["sha256"], expected["sha256"])

    container_records = {
        name: android_boot_record((critical_root / name).read_bytes())
        for name in ("boot.img", "recovery.img")
        if (critical_root / name).is_file()
    }
    for name, record in container_records.items():
        for field, expected in {
            "android_magic": True,
            "header_version": 1,
            "page_size": 4096,
            "second_bytes": 0,
            "samsung_signer_ver02_occurrences": 1,
            "avb_vbmeta_magic_occurrences": 1,
            "avb_footer_magic_occurrences": 1,
            "avb_footer_at_partition_end": True,
            "partition_tail_64_all_zero": False,
        }.items():
            require_equal(
                reasons,
                f"stock {name} {field}",
                record.get(field),
                expected,
            )

    return {
        "state": "pass" if not reasons else "fail",
        "path": str(report_path),
        "report": report_record(report_path),
        "archive": archive_record,
        "critical_directory": str(critical_root),
        "critical_artifacts": critical_records,
        "android_boot_container_records": container_records,
        "reasons": reasons,
    }


def validate_transport_report(path: Path | None) -> dict[str, Any]:
    if path is None:
        return pending_gate(
            "current-session read-only Download Mode drill report was not supplied; "
            "historical same-device transport evidence is documented separately"
        )
    report_path = path.resolve()
    report = load_json(report_path)
    historical_reasons: list[str] = []
    current_reasons: list[str] = []
    for field, expected in {
        "schema": 2,
        "report_type": "sm-t860-recovery-transport-evidence",
        "device": "samsung-gts6lwifi",
        "model": "SM-T860",
        "transport": "samsung-download-mode",
        "historical_transport_capability": "pass",
        "historical_status": "pass-historical-sm-t860-heimdall-transport",
        "deployable": False,
        "explicit_device_write_authorization_recorded": False,
    }.items():
        require_equal(
            historical_reasons,
            f"transport report {field}",
            report.get(field),
            expected,
        )

    evidence_root_value = report.get("evidence_root")
    if not isinstance(evidence_root_value, str):
        historical_reasons.append("transport report lacks an evidence_root")
        evidence_root = None
    else:
        evidence_root = Path(evidence_root_value).expanduser().resolve()
        if not evidence_root.is_dir():
            historical_reasons.append(
                f"transport evidence root is missing: {evidence_root}"
            )

    tool = report.get("tool")
    tool_record: dict[str, Any] | None = None
    if not isinstance(tool, dict) or evidence_root is None:
        historical_reasons.append("transport report tool must bind the local binary")
    else:
        require_equal(
            historical_reasons,
            "transport tool name",
            tool.get("name"),
            "Heimdall",
        )
        require_equal(
            historical_reasons,
            "transport tool version",
            tool.get("version"),
            "2.0.2",
        )
        require_equal(
            historical_reasons,
            "transport tool SHA-256",
            tool.get("sha256"),
            HISTORICAL_HEIMDALL_SHA256,
        )
        relative = tool.get("path")
        if not isinstance(relative, str) or Path(relative).is_absolute():
            historical_reasons.append(
                "transport tool path must be relative to evidence_root"
            )
        else:
            tool_path = (evidence_root / relative).resolve()
            if evidence_root not in tool_path.parents or not tool_path.is_file():
                historical_reasons.append(
                    "transport tool path escapes or is missing"
                )
            else:
                tool_record = file_record(tool_path)
                require_equal(
                    historical_reasons,
                    "local Heimdall SHA-256",
                    tool_record["sha256"],
                    HISTORICAL_HEIMDALL_SHA256,
                )

    historical = report.get("historical")
    if not isinstance(historical, dict):
        historical_reasons.append(
            "transport report historical evidence must be an object"
        )
        historical = {}
    for field, expected in {
        "same_device_evidence": True,
        "usb_vid_pid": "04e8:685d",
        "pit_download_tested": True,
        "pit_entry_count": 76,
        "pit_header": "COM_TAR2",
        "pit_cpu_bootloader_tag": "SM8150",
        "write_path_tested": True,
        "successful_partition_uploads": ["RECOVERY", "BOOT", "VBMETA"],
        "historical_device_writes_performed": True,
        "pit_flash_performed": False,
        "repartition_performed": False,
        "subsequent_android_boots_observed": True,
        "tool_source_traceable": False,
        "guarantees_future_recovery": False,
    }.items():
        require_equal(
            historical_reasons,
            f"historical transport {field}",
            historical.get(field),
            expected,
        )

    files = historical.get("files")
    verified_files: dict[str, Any] = {}
    if not isinstance(files, dict) or evidence_root is None:
        historical_reasons.append(
            "transport report must bind every fixed historical evidence file"
        )
    else:
        if set(files) != set(HISTORICAL_TRANSPORT_FILES):
            historical_reasons.append(
                "historical transport evidence file ids do not match the fixed set"
            )
        for label, expectation in HISTORICAL_TRANSPORT_FILES.items():
            item = files.get(label)
            if not isinstance(item, dict):
                historical_reasons.append(
                    f"transport report lacks {label} file binding"
                )
                continue
            expected_hash = expectation["sha256"]
            require_equal(
                historical_reasons,
                f"{label} declared SHA-256",
                item.get("sha256"),
                expected_hash,
            )
            relative = item.get("path")
            if not isinstance(relative, str) or Path(relative).is_absolute():
                historical_reasons.append(
                    f"{label} path must be relative to evidence_root"
                )
                continue
            file_path = (evidence_root / relative).resolve()
            if evidence_root not in file_path.parents or not file_path.is_file():
                historical_reasons.append(f"{label} path escapes or is missing")
                continue
            record = file_record(file_path)
            verified_files[label] = record
            require_equal(
                historical_reasons,
                f"{label} local SHA-256",
                record["sha256"],
                expected_hash,
            )
            if expectation["markers"]:
                text = file_path.read_text(encoding="utf-8", errors="replace")
                for marker in expectation["markers"]:
                    if marker not in text:
                        historical_reasons.append(
                            f"{label} lacks marker: {marker}"
                        )
            if label == "twrp_image":
                twrp_data = file_path.read_bytes()
                twrp_format = android_boot_record(twrp_data)
                verified_files[label]["android_boot_container"] = twrp_format
                require_equal(
                    historical_reasons,
                    "historical TWRP image bytes",
                    len(twrp_data),
                    HISTORICAL_TWRP_BYTES,
                )
                for field, expected in {
                    "android_magic": True,
                    "header_version": 1,
                    "page_size": 4096,
                    "second_bytes": 0,
                    "samsung_signer_ver02_occurrences": 0,
                    "avb_vbmeta_magic_occurrences": 0,
                    "avb_footer_magic_occurrences": 0,
                    "avb_footer_at_partition_end": False,
                    "partition_tail_64_all_zero": True,
                }.items():
                    require_equal(
                        historical_reasons,
                        f"historical TWRP {field}",
                        twrp_format.get(field),
                        expected,
                    )

    current = report.get("current_session")
    current_state = current.get("state") if isinstance(current, dict) else None
    current_record: dict[str, Any] | None = None
    current_pit_record: dict[str, Any] | None = None
    current_pit_structure: dict[str, Any] | None = None
    stock_pit_record: dict[str, Any] | None = None
    stock_pit_value = report.get("stock_pit")
    stock_pit_path: Path | None = None
    stock_pit_declared_hash: object = None
    if isinstance(stock_pit_value, dict):
        stock_pit_relative = stock_pit_value.get("path")
        stock_pit_declared_hash = stock_pit_value.get("sha256")
        if not isinstance(stock_pit_relative, str) or Path(
            stock_pit_relative
        ).is_absolute():
            historical_reasons.append(
                "transport stock PIT path must be relative to evidence_root"
            )
        elif evidence_root is not None:
            candidate = (evidence_root / stock_pit_relative).resolve()
            if evidence_root not in candidate.parents:
                historical_reasons.append("transport stock PIT path escapes evidence_root")
            else:
                stock_pit_path = candidate
    else:
        historical_reasons.append("transport report stock_pit must be an object")
    stock_pit_structure: dict[str, Any] | None = None
    if stock_pit_path is None or not stock_pit_path.is_file():
        historical_reasons.append(
            "transport report must bind a local stock PIT"
        )
    else:
        stock_pit_data = stock_pit_path.read_bytes()
        stock_pit_record = file_record(stock_pit_path, stock_pit_data)
        require_equal(
            historical_reasons,
            "declared stock PIT SHA-256",
            stock_pit_declared_hash,
            STOCK_CRITICAL["GTS6LWIFI_EUR_OPEN.pit"]["sha256"],
        )
        require_equal(
            historical_reasons,
            "stock PIT SHA-256",
            stock_pit_record["sha256"],
            STOCK_CRITICAL["GTS6LWIFI_EUR_OPEN.pit"]["sha256"],
        )
        stock_pit_structure = pit_structure_record(stock_pit_data)
        for field, expected in {
            "magic": "0x12349876",
            "entry_count": 76,
            "header": "COM_TAR2",
            "cpu_bootloader_tag": "SM8150",
            "logic_unit_count": 4,
            "entries_parsed": 76,
        }.items():
            require_equal(
                historical_reasons,
                f"stock PIT {field}",
                stock_pit_structure.get(field),
                expected,
            )
    if not isinstance(current, dict):
        current_reasons.append("transport report current_session must be an object")
    elif current_state == "not-run":
        for field in ("flash_attempted", "device_writes_performed"):
            if current.get(field) is not None:
                current_reasons.append(
                    f"not-run current session must record {field} as null"
                )
        for field in (
            "read_only_download_mode_drill_completed",
            "log",
            "pit",
        ):
            if current.get(field) is not None:
                current_reasons.append(
                    f"not-run current session must record {field} as null or omit it"
                )
        require_equal(
            current_reasons,
            "not-run current session current_transport_liveness",
            report.get("current_transport_liveness"),
            "pending",
        )
        require_equal(
            current_reasons,
            "not-run transport status",
            report.get("status"),
            "pending-current-session-read-only-download-mode-drill",
        )
    elif current_state == "completed":
        expected_current_pit_path: Path | None = None
        expected_current_command: list[str] | None = None
        if evidence_root is not None and tool_record is not None:
            tool_path = Path(tool_record["path"])
            expected_current_pit_path = (evidence_root / "current-session.pit").resolve()
            expected_current_command = [
                str(tool_path),
                "download-pit",
                "--output",
                str(expected_current_pit_path),
                "--no-reboot",
                "--stdout-errors",
            ]
        for field, expected in {
            "read_only_download_mode_drill_completed": True,
            "usb_vid_pid": "04e8:685d",
            "session_begun": True,
            "pit_download_successful": True,
            "pit_entry_count": 76,
            "pit_header": "COM_TAR2",
            "pit_cpu_bootloader_tag": "SM8150",
            "repartition_attempted": False,
            "flash_attempted": False,
            "device_writes_performed": False,
        }.items():
            require_equal(current_reasons, f"current session {field}", current.get(field), expected)
        require_equal(
            current_reasons,
            "current session command_argv",
            current.get("command_argv"),
            expected_current_command,
        )
        collection_start: datetime | None = None
        collection_end: datetime | None = None
        for field in ("started_at_utc", "completed_at_utc"):
            value = current.get(field)
            if not isinstance(value, str):
                current_reasons.append(f"current session lacks {field}")
                continue
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                current_reasons.append(f"current session {field} is not ISO 8601")
                continue
            if parsed.tzinfo is None:
                current_reasons.append(f"current session {field} lacks a timezone")
                continue
            if field == "started_at_utc":
                collection_start = parsed.astimezone(timezone.utc)
            else:
                collection_end = parsed.astimezone(timezone.utc)
        if collection_start is not None and collection_end is not None:
            if collection_end < collection_start:
                current_reasons.append("current session collection window is reversed")
            elif collection_end - collection_start > timedelta(minutes=15):
                current_reasons.append("current session collection window exceeds 15 minutes")
        require_equal(
            current_reasons,
            "completed current_transport_liveness",
            report.get("current_transport_liveness"),
            "pass",
        )
        require_equal(
            current_reasons,
            "completed transport status",
            report.get("status"),
            "pass-recovery-transport-drill",
        )
        current_log = current.get("log")
        if not isinstance(current_log, dict) or evidence_root is None:
            current_reasons.append("completed current session must bind its local log")
        else:
            relative = current_log.get("path")
            declared_hash = current_log.get("sha256")
            if not valid_sha256(declared_hash):
                current_reasons.append("current session log lacks a SHA-256")
            if not isinstance(relative, str) or Path(relative).is_absolute():
                current_reasons.append("current session log path must be relative")
            else:
                current_path = (evidence_root / relative).resolve()
                if evidence_root not in current_path.parents or not current_path.is_file():
                    current_reasons.append("current session log path escapes or is missing")
                else:
                    current_record = file_record(current_path)
                    current_mtime = datetime.fromtimestamp(
                        current_path.stat().st_mtime, timezone.utc
                    )
                    current_record["mtime_utc"] = current_mtime.isoformat()
                    if (
                        collection_start is not None
                        and collection_end is not None
                        and not (
                            collection_start - timedelta(seconds=5)
                            <= current_mtime
                            <= collection_end + timedelta(seconds=5)
                        )
                    ):
                        current_reasons.append(
                            "current session log mtime is outside the collection window"
                        )
                    require_equal(
                        current_reasons,
                        "current session local log SHA-256",
                        current_record["sha256"],
                        declared_hash,
                    )
                    current_text = current_path.read_text(
                        encoding="utf-8", errors="replace"
                    )
                    command_marker = "COMMAND_ARGV_JSON:" + json.dumps(
                        expected_current_command,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                    for marker in (
                        "Heimdall v2.0.2",
                        command_marker,
                        "USB_VID_PID:04e8:685d",
                        "Session begun.",
                        "PIT file download successful.",
                    ):
                        if marker not in current_text:
                            current_reasons.append(
                                f"current session log lacks marker: {marker}"
                            )
                    if re.search(
                        r"Uploading\s|upload successful|(?:^|\s)(?:flash|--repartition|--skip-size-check)(?:\s|=|$)|Repartition\s",
                        current_text,
                        re.IGNORECASE | re.MULTILINE,
                    ):
                        current_reasons.append(
                            "current session log contains a write/repartition marker"
                        )
        current_pit = current.get("pit")
        if not isinstance(current_pit, dict) or evidence_root is None:
            current_reasons.append(
                "completed current session must bind its downloaded PIT file"
            )
        else:
            pit_relative = current_pit.get("path")
            pit_declared_hash = current_pit.get("sha256")
            if not valid_sha256(pit_declared_hash):
                current_reasons.append("current PIT lacks a SHA-256")
            if not isinstance(pit_relative, str) or Path(pit_relative).is_absolute():
                current_reasons.append("current PIT path must be relative")
            else:
                current_pit_path = (evidence_root / pit_relative).resolve()
                if (
                    evidence_root not in current_pit_path.parents
                    or not current_pit_path.is_file()
                ):
                    current_reasons.append("current PIT path escapes or is missing")
                else:
                    current_pit_data = current_pit_path.read_bytes()
                    current_pit_record = file_record(
                        current_pit_path, current_pit_data
                    )
                    current_pit_mtime = datetime.fromtimestamp(
                        current_pit_path.stat().st_mtime, timezone.utc
                    )
                    current_pit_record["mtime_utc"] = current_pit_mtime.isoformat()
                    if (
                        collection_start is not None
                        and collection_end is not None
                        and not (
                            collection_start - timedelta(seconds=5)
                            <= current_pit_mtime
                            <= collection_end + timedelta(seconds=5)
                        )
                    ):
                        current_reasons.append(
                            "current PIT mtime is outside the collection window"
                        )
                    require_equal(
                        current_reasons,
                        "current PIT filename",
                        current_pit_path.name,
                        "current-session.pit",
                    )
                    if current_pit_path == stock_pit_path:
                        current_reasons.append(
                            "current PIT must be a distinct file downloaded during this session"
                        )
                    require_equal(
                        current_reasons,
                        "current PIT command output path",
                        current_pit_path,
                        expected_current_pit_path,
                    )
                    if stock_pit_path is not None and stock_pit_path.is_file():
                        current_stat = current_pit_path.stat()
                        stock_stat = stock_pit_path.stat()
                        if (
                            current_stat.st_dev == stock_stat.st_dev
                            and current_stat.st_ino == stock_stat.st_ino
                        ):
                            current_reasons.append(
                                "current PIT must not be the stock PIT inode"
                            )
                    require_equal(
                        current_reasons,
                        "current PIT local SHA-256",
                        current_pit_record["sha256"],
                        pit_declared_hash,
                    )
                    current_pit_structure = pit_structure_record(current_pit_data)
                    for field, expected in {
                        "magic": "0x12349876",
                        "entry_count": 76,
                        "header": "COM_TAR2",
                        "cpu_bootloader_tag": "SM8150",
                        "logic_unit_count": 4,
                        "entries_parsed": 76,
                    }.items():
                        require_equal(
                            current_reasons,
                            f"current PIT {field}",
                            current_pit_structure.get(field),
                            expected,
                        )
                    if stock_pit_structure is not None:
                        require_equal(
                            current_reasons,
                            "current PIT partition layout",
                            current_pit_structure.get("entries"),
                            stock_pit_structure.get("entries"),
                        )
    else:
        current_reasons.append(
            "transport current_session state must be not-run or completed"
        )

    historical_verified = not historical_reasons
    if historical_reasons or current_reasons:
        gate_state = "fail"
    elif current_state == "completed":
        gate_state = "pass"
    else:
        gate_state = "pending"
    return {
        "state": gate_state,
        "path": str(report_path),
        "report": report_record(report_path),
        "tool": tool_record,
        "tool_source_traceable": historical.get("tool_source_traceable") is True,
        "historical_transport_capability": (
            "pass" if historical_verified else "fail"
        ),
        "current_transport_liveness": (
            "pass" if gate_state == "pass" else "pending" if gate_state == "pending" else "fail"
        ),
        "verified_historical_files": verified_files,
        "current_session_log": current_record,
        "current_session_pit": current_pit_record,
        "current_session_pit_structure": current_pit_structure,
        "stock_pit": stock_pit_record,
        "stock_pit_structure": stock_pit_structure,
        "historical_reasons": historical_reasons,
        "current_session_reasons": current_reasons,
        "reasons": historical_reasons + current_reasons,
        "trust_boundary": (
            "This is historical evidence from the same device.  The Heimdall binary's "
            "origin is not traceable, and earlier successful writes and later Android "
            "boots do not guarantee that a future recovery attempt will succeed.  A "
            "historical pass never substitutes for a current read-only liveness drill."
        ),
    }


def validate_action_plan(
    path: Path | None,
    static_gate: dict[str, Any],
    windows_gate: dict[str, Any],
    stock_gate: dict[str, Any],
    transport_gate: dict[str, Any],
    execution_tool_gate: dict[str, Any],
    trigger_gate: dict[str, Any],
) -> dict[str, Any]:
    if path is None:
        return pending_gate("independently reviewed exact action plan was not supplied")
    report_path = path.resolve()
    report = load_json(report_path)
    reasons: list[str] = []
    expected_top_level_keys = {
        "schema",
        "report_type",
        "status",
        "device",
        "model",
        "first_boot_medium",
        "transport",
        "device_writes_performed",
        "deployable",
        "explicit_device_write_authorization_recorded",
        "firmware",
        "evidence_reports",
        "target",
        "stop_conditions",
        "reviewed_by",
        "reviewed_at_utc",
        "execution",
    }
    require_equal(
        reasons,
        "action plan top-level keys",
        set(report),
        expected_top_level_keys,
    )
    for dependency, gate in {
        "Windows media": windows_gate,
        "stock recovery": stock_gate,
        "recovery transport": transport_gate,
        "traceable execution tool": execution_tool_gate,
        "Recovery boot trigger": trigger_gate,
    }.items():
        if gate.get("state") != "pass":
            reasons.append(f"action plan cannot pass before {dependency} gate passes")
    for field, expected in {
        "schema": 2,
        "report_type": "sm-t860-first-boot-action-plan",
        "status": "pass-first-boot-action-plan-review",
        "device": "samsung-gts6lwifi",
        "model": "SM-T860",
        "first_boot_medium": "microSD",
        "transport": "samsung-download-mode",
        "device_writes_performed": False,
        "deployable": False,
        "explicit_device_write_authorization_recorded": False,
    }.items():
        require_equal(reasons, f"action plan {field}", report.get(field), expected)
    for authorization_field in (
        "authorized",
        "authorization",
        "device_write_authorized",
        "execution_authorized",
        "explicit_authorization",
        "write_authorized",
        "flash_authorized",
    ):
        if report.get(authorization_field) not in (None, False):
            reasons.append(
                f"action plan must not contain affirmative {authorization_field}"
            )

    artifacts = static_gate["artifacts"]
    firmware = report.get("firmware")
    expected_firmware = {
        "boot_image_bytes": artifacts["boot_image"]["bytes"],
        "boot_image_sha256": artifacts["boot_image"]["sha256"],
        "fd_bytes": artifacts["firmware"]["bytes"],
        "fd_sha256": artifacts["firmware"]["sha256"],
        "aml_sha256": artifacts["aml"]["sha256"],
    }
    require_equal(reasons, "action plan firmware binding", firmware, expected_firmware)

    evidence_reports = report.get("evidence_reports")
    if all(
        gate.get("state") == "pass"
        for gate in (
            windows_gate,
            stock_gate,
            transport_gate,
            execution_tool_gate,
            trigger_gate,
        )
    ):
        expected_reports = {
            "windows_media_sha256": windows_gate["report"]["sha256"],
            "stock_recovery_sha256": stock_gate["report"]["sha256"],
            "recovery_transport_sha256": transport_gate["report"]["sha256"],
            "execution_tool_provenance_sha256": execution_tool_gate["provenance"][
                "report"
            ]["sha256"],
            "execution_tool_liveness_sha256": execution_tool_gate["liveness"][
                "report"
            ]["sha256"],
            "recovery_trigger_sha256": trigger_gate["report"]["sha256"],
        }
        require_equal(
            reasons,
            "action plan evidence report bindings",
            evidence_reports,
            expected_reports,
        )

    target = report.get("target")
    if not isinstance(target, dict):
        reasons.append("action plan target must be an object")
    else:
        partition = target.get("partition")
        if partition != "RECOVERY":
            reasons.append("action plan target partition must be exactly RECOVERY")
        else:
            stock_name = "recovery.img"
            capacity = STOCK_CRITICAL[stock_name]["bytes"]
            for field, expected in {
                "image_bytes": artifacts["boot_image"]["bytes"],
                "image_sha256": artifacts["boot_image"]["sha256"],
                "partition_capacity_bytes": capacity,
                "restore_image": stock_name,
                "restore_image_bytes": STOCK_CRITICAL[stock_name]["bytes"],
                "restore_image_sha256": STOCK_CRITICAL[stock_name]["sha256"],
                "pit_sha256": STOCK_CRITICAL["GTS6LWIFI_EUR_OPEN.pit"]["sha256"],
            }.items():
                require_equal(reasons, f"action plan target {field}", target.get(field), expected)
            require_equal(
                reasons,
                "action plan target keys",
                set(target),
                {
                    "partition",
                    "image_bytes",
                    "image_sha256",
                    "partition_capacity_bytes",
                    "restore_image",
                    "restore_image_bytes",
                    "restore_image_sha256",
                    "pit_sha256",
                },
            )
            if artifacts["boot_image"]["bytes"] > capacity:
                reasons.append("UEFI boot image exceeds target partition capacity")

    required_stop_conditions = {
        "artifact-hash-mismatch",
        "target-partition-mismatch",
        "download-mode-unavailable",
        "host-loses-device",
        "boot-loop-or-no-observable-output",
    }
    stop_conditions = report.get("stop_conditions")
    if not isinstance(stop_conditions, list) or not required_stop_conditions.issubset(
        {item for item in stop_conditions if isinstance(item, str)}
    ):
        reasons.append(
            "action plan lacks one or more required machine-readable stop conditions"
        )
    if not isinstance(report.get("reviewed_by"), str) or not report.get("reviewed_by"):
        reasons.append("action plan lacks an independent reviewer identifier")
    if not isinstance(report.get("reviewed_at_utc"), str) or not report.get("reviewed_at_utc"):
        reasons.append("action plan lacks review time")
    else:
        try:
            reviewed_at = datetime.fromisoformat(
                report["reviewed_at_utc"].replace("Z", "+00:00")
            )
            if reviewed_at.tzinfo is None:
                reasons.append("action plan review time must include a timezone")
        except ValueError:
            reasons.append("action plan review time is not valid ISO 8601")

    execution = report.get("execution")
    if not isinstance(execution, dict):
        reasons.append("action plan execution must be an object")
    else:
        allowed_execution_keys = {
            "write_argv",
            "boot_trigger_argv",
            "boot_trigger",
            "restore_argv",
            "pit_flash_planned",
            "repartition_planned",
            "continuous_retry_allowed",
            "single_slot_device_acknowledged",
            "write_attempt_limit",
            "skip_size_check",
            "preserve_boot",
            "preserve_dtbo",
            "preserve_vbmeta",
            "preserve_pit",
        }
        if set(execution) != allowed_execution_keys:
            reasons.append("action plan execution keys do not match the fixed schema")
        heimdall_path = None
        execution_tool = execution_tool_gate.get("binary")
        if (
            execution_tool_gate.get("state") == "pass"
            and isinstance(execution_tool, dict)
            and execution_tool.get("path")
        ):
            heimdall_path = str(Path(execution_tool["path"]).resolve())
        current_image_path = str(Path(artifacts["boot_image"]["path"]).resolve())
        stock_recovery_record = stock_gate.get("critical_artifacts", {}).get(
            "recovery.img"
        )
        stock_recovery_path = (
            str(Path(stock_recovery_record["path"]).resolve())
            if isinstance(stock_recovery_record, dict)
            and stock_recovery_record.get("path")
            else None
        )
        expected_write_argv = (
            [heimdall_path, "flash", "--RECOVERY", current_image_path, "--no-reboot"]
            if heimdall_path is not None
            else None
        )
        # This is a human key transition, not a Heimdall reboot command.
        expected_boot_trigger_argv = None
        expected_boot_trigger = (
            {
                "method_id": RECOVERY_TRIGGER_PROTOCOL_ID,
                "kind": "human-key-transition",
                "requires_human": True,
                "usb_connected": True,
                "source_state": "download-mode-after-no-reboot",
                "transition_timing": "immediate-on-display-black-edge",
                "attempt_limit": 1,
                "evidence_sha256": trigger_gate["report"]["sha256"],
            }
            if trigger_gate.get("state") == "pass"
            and isinstance(trigger_gate.get("report"), dict)
            else None
        )
        expected_restore_argv = (
            [heimdall_path, "flash", "--RECOVERY", stock_recovery_path]
            if heimdall_path is not None and stock_recovery_path is not None
            else None
        )
        require_equal(
            reasons,
            "action plan exact write argv",
            execution.get("write_argv"),
            expected_write_argv,
        )
        require_equal(
            reasons,
            "action plan exact boot trigger argv",
            execution.get("boot_trigger_argv"),
            expected_boot_trigger_argv,
        )
        require_equal(
            reasons,
            "action plan exact boot trigger protocol",
            execution.get("boot_trigger"),
            expected_boot_trigger,
        )
        require_equal(
            reasons,
            "action plan exact restore argv",
            execution.get("restore_argv"),
            expected_restore_argv,
        )
        for field, expected in {
            "pit_flash_planned": False,
            "repartition_planned": False,
            "continuous_retry_allowed": False,
            "single_slot_device_acknowledged": True,
            "write_attempt_limit": 1,
            "skip_size_check": False,
            "preserve_boot": True,
            "preserve_dtbo": True,
            "preserve_vbmeta": True,
            "preserve_pit": True,
        }.items():
            require_equal(
                reasons,
                f"action plan execution {field}",
                execution.get(field),
                expected,
            )

    return {
        "state": "pass" if not reasons else "fail",
        "path": str(report_path),
        "report": report_record(report_path),
        "reasons": reasons,
        "trust_boundary": (
            "Passing this review only binds exact inputs and rollback data.  It is "
            "not, and cannot contain, device-write authorization."
        ),
    }


parser = argparse.ArgumentParser()
parser.add_argument("--firmware", type=Path, default=DEFAULT_FIRMWARE)
parser.add_argument("--boot-image", type=Path, default=DEFAULT_BOOT_IMAGE)
parser.add_argument("--aml", type=Path, default=DEFAULT_AML)
parser.add_argument("--source-report", type=Path, default=DEFAULT_SOURCE_REPORT)
parser.add_argument("--uefi-report", type=Path, default=DEFAULT_UEFI_REPORT)
parser.add_argument("--acpi-report", type=Path, default=DEFAULT_ACPI_REPORT)
parser.add_argument(
    "--windows-media-report",
    type=Path,
    help="JSON generated by the pinned Windows media validator",
)
parser.add_argument(
    "--stock-recovery-report",
    type=Path,
    help="Local DWH1 archive validation JSON (the archive is rehashed)",
)
parser.add_argument(
    "--stock-critical-dir",
    type=Path,
    help="Directory with extracted boot/recovery/dtbo/vbmeta/PIT; defaults beside stock report",
)
parser.add_argument(
    "--recovery-transport-report",
    type=Path,
    help=(
        "Strict historical evidence plus a current read-only Download Mode drill; "
        "not-run remains pending"
    ),
)
parser.add_argument(
    "--recovery-trigger-report",
    type=Path,
    help=(
        "Independently reviewed no-partition-flash Recovery trigger drill; "
        "no report digest is accepted in the current validator"
    ),
)
parser.add_argument(
    "--execution-tool-provenance-report",
    type=Path,
    help=(
        "Strict facts-only SourceHut v2.2.2 source/build/binary report; "
        "a candidate cannot self-approve its key, binary, or report digest"
    ),
)
parser.add_argument(
    "--execution-tool-liveness-report",
    type=Path,
    help=(
        "Separately authorized final-host read-only download-pit evidence for "
        "the exact execution binary; no report digest is currently accepted"
    ),
)
parser.add_argument(
    "--action-plan",
    type=Path,
    help="Independently reviewed exact-image/partition/rollback plan; never generated here",
)
parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
args = parser.parse_args()

for required in (
    args.firmware,
    args.boot_image,
    args.aml,
    args.source_report,
    args.uefi_report,
    args.acpi_report,
):
    if not required.resolve().is_file():
        raise SystemExit(f"validation failed: missing required input {required.resolve()}")

static_gate, static_pass = validate_static_reports_and_artifacts(
    args.firmware.resolve(),
    args.boot_image.resolve(),
    args.aml.resolve(),
    args.source_report.resolve(),
    args.uefi_report.resolve(),
    args.acpi_report.resolve(),
)
windows_gate = validate_windows_report(args.windows_media_report)
stock_gate = validate_stock_recovery(
    args.stock_recovery_report, args.stock_critical_dir
)
transport_gate = validate_transport_report(args.recovery_transport_report)
execution_tool_gate = validate_execution_tool_gate(
    args.execution_tool_provenance_report,
    args.execution_tool_liveness_report,
)
trigger_gate = validate_recovery_trigger_report(
    args.recovery_trigger_report, transport_gate
)
action_plan_gate = validate_action_plan(
    args.action_plan,
    static_gate,
    windows_gate,
    stock_gate,
    transport_gate,
    execution_tool_gate,
    trigger_gate,
)
external_gates = {
    "windows_media": windows_gate,
    "stock_recovery": stock_gate,
    "recovery_transport": transport_gate,
    "execution_tool": execution_tool_gate,
    "recovery_boot_trigger": trigger_gate,
    "exact_action_plan": action_plan_gate,
}
execution_prerequisites_ready = (
    static_pass
    and all(gate["state"] == "pass" for gate in external_gates.values())
)
supplied_gate_failed = any(
    gate["state"] == "fail" for gate in external_gates.values()
)
historical_authentication_support = (
    transport_gate.get("historical_transport_capability") == "pass"
    and "twrp_image" in transport_gate.get("verified_historical_files", {})
    and "unlocked_recovery_boot_log"
    in transport_gate.get("verified_historical_files", {})
)
static_gate["boot_container_compatibility_evidence"][
    "authentication_path_historically_supported_on_unlocked_device"
] = historical_authentication_support
static_gate["boot_container_compatibility_evidence"][
    "historical_unlocked_device_evidence_expected"
]["bound_by_transport_report"] = historical_authentication_support

result: dict[str, Any] = {
    "schema": 2,
    "validated_at_utc": datetime.now(timezone.utc).isoformat(),
    "device": "samsung-gts6lwifi",
    "status": (
        "offline_firmware_composition_pass"
        if static_pass
        else "offline_firmware_composition_fail"
    ),
    "execution_status": (
        "awaiting-explicit-device-write-authorization"
        if execution_prerequisites_ready
        else "blocked-first-boot-execution"
    ),
    "offline_firmware_composition_pass": static_pass,
    "boot_image_container_static_support": static_gate["artifacts"][
        "boot_image_container_static_support"
    ],
    "authentication_path_historically_supported_on_unlocked_device": (
        historical_authentication_support
    ),
    "exact_current_image_hardware_tested": False,
    "recovery_boot_trigger_validated": trigger_gate["state"] == "pass",
    "execution_prerequisites_ready": execution_prerequisites_ready,
    "external_evidence_trust": "local-self-attested-not-execution-authority",
    "deployable": False,
    "device_writes_performed": False,
    "explicit_device_write_authorization_recorded": False,
    "static_gate": static_gate,
    "external_gates": external_gates,
    "stop_conditions": [
        "Do not flash or reboot while any gate is pending or failed.",
        "Do not write the tablet until the user explicitly authorizes the exact image, partition, and recovery route.",
        "Never infer authorization from a JSON report or a static pass.",
        "A composition pass does not prove that the image boots on hardware.",
    ],
}

output = args.output.resolve()
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
print(json.dumps(result, indent=2))

# Missing external evidence is an expected, safe pending state.  A static
# failure or any explicitly supplied-but-invalid external report is an error.
if not static_pass or supplied_gate_failed:
    raise SystemExit(1)
