#!/usr/bin/env python3
"""Pure validation helpers for the SM-T860 first-boot diagnostic profile."""

from __future__ import annotations

import zlib


def guid_string(value: object) -> str:
    if not isinstance(value, bytes) or len(value) != 16:
        return ""
    first = int.from_bytes(value[0:4], "little")
    second = int.from_bytes(value[4:6], "little")
    third = int.from_bytes(value[6:8], "little")
    tail = value[8:].hex()
    return f"{first:08x}-{second:04x}-{third:04x}-{tail[:4]}-{tail[4:]}"


def walk_objects(value: object, seen: set[int] | None = None):
    if seen is None:
        seen = set()
    if id(value) in seen:
        return
    seen.add(id(value))
    yield value
    attributes = vars(value) if hasattr(value, "__dict__") else {}
    for child in attributes.values():
        if isinstance(child, list):
            for item in child:
                if hasattr(item, "__dict__"):
                    yield from walk_objects(item, seen)
        elif (
            hasattr(child, "__dict__")
            and child.__class__.__module__.startswith("uefi_firmware")
        ):
            yield from walk_objects(child, seen)


def validate_compressed_boot_image(
    boot_data: bytes, firmware_data: bytes
) -> dict[str, object]:
    if len(boot_data) < 4096 or not boot_data.startswith(b"ANDROID!"):
        raise ValueError("diagnostic boot image lacks a v0 header")
    kernel_size = int.from_bytes(boot_data[8:12], "little")
    ramdisk_size = int.from_bytes(boot_data[16:20], "little")
    page_size = int.from_bytes(boot_data[36:40], "little")
    header_version = int.from_bytes(boot_data[40:44], "little")
    if header_version != 0 or page_size != 4096 or ramdisk_size != 6:
        raise ValueError(
            "diagnostic boot image is not the expected v0/4096/empty-ramdisk container"
        )
    kernel_end = page_size + kernel_size
    if kernel_size < 1 or kernel_end > len(boot_data):
        raise ValueError("diagnostic kernel range is invalid")
    kernel = boot_data[page_size:kernel_end]
    decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
    try:
        payload = decompressor.decompress(kernel) + decompressor.flush()
    except zlib.error as exc:
        raise ValueError("diagnostic kernel gzip is invalid") from exc
    if not decompressor.eof:
        raise ValueError("diagnostic kernel gzip is truncated")
    dtb = decompressor.unused_data
    if not dtb:
        raise ValueError("diagnostic kernel lacks appended DTB")
    if payload.count(firmware_data) != 1 or not payload.endswith(firmware_data):
        raise ValueError(
            "decompressed diagnostic payload must end with the exact firmware once"
        )
    bootshim_bytes = len(payload) - len(firmware_data)
    if bootshim_bytes < 1 or bootshim_bytes > 1024 * 1024:
        raise ValueError("diagnostic BootShim length is implausible")
    return {
        "android_header_version": header_version,
        "page_size": page_size,
        "ramdisk_size": ramdisk_size,
        "kernel_size": kernel_size,
        "gzip_payload": True,
        "decompressed_payload_bytes": len(payload),
        "bootshim_bytes": bootshim_bytes,
        "appended_dtb_bytes": len(dtb),
        "embedded_exact_firmware_occurrences_after_decompression": 1,
    }
