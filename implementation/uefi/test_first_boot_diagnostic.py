#!/usr/bin/env python3
from __future__ import annotations

import json
import gzip
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from first_boot_diagnostic_validation import validate_compressed_boot_image


SCRIPT = Path(__file__).with_name("prepare-first-boot-diagnostic.py")
DEVICE = Path("Platforms/SurfaceDuo1Pkg/Device/samsung-gts6lwifi")
UFS = (
    "SurfaceDuo1Pkg/Device/$(TARGET_DEVICE)/Binaries/"
    "QcomPkg/Drivers/UFSDxe/UFSDxe.inf"
)
SDCC = (
    "SurfaceDuo1Pkg/Device/$(TARGET_DEVICE)/Binaries/"
    "QcomPkg/Drivers/SdccDxe/SdccDxe.inf"
)
QCOM_WDOG = (
    "SurfaceDuo1Pkg/Device/$(TARGET_DEVICE)/Binaries/"
    "QcomPkg/Drivers/QcomWDogDxe/QcomWDogDxe.inf"
)
UEFI_WDOG = "MdeModulePkg/Universal/WatchdogTimerDxe/WatchdogTimer.inf"


class FirstBootDiagnosticPreparationTests(unittest.TestCase):
    def make_tree(self, root: Path) -> None:
        device = root / DEVICE
        device.mkdir(parents=True)
        for name in ("APRIORI.inc", "DXE.inc", "DXE.dsc.inc"):
            prefix = "INF " if name != "DXE.dsc.inc" else ""
            text = (
                f"{prefix}{SDCC}\n"
                f"{prefix}{UFS}\n"
                f"{prefix}{QCOM_WDOG}\n"
            )
            if name == "APRIORI.inc":
                text += f"INF {UEFI_WDOG}\n"
            (device / name).write_text(text, encoding="utf-8")
        (device / "Library/PlatformConfigurationMapLib").mkdir(parents=True)
        (device / "Library/PlatformConfigurationMapLib/PlatformConfigurationMapLib.c").write_text(
            '    {"EnableUfsIOC", 1},\n'
            '    {"UfsSmmuConfigForOtherBootDev", 1},\n',
            encoding="utf-8",
        )
        platform = root / "Platforms/SurfaceDuo1Pkg"
        (platform / "SurfaceDuo1.dsc").write_text(
            "  USE_SCREEN_FOR_SERIAL_OUTPUT    = 0\n",
            encoding="utf-8",
        )
        (platform / "SurfaceDuo1.fdf").write_text(
            f"  INF {UEFI_WDOG}\n",
            encoding="utf-8",
        )

    def run_prepare(self, root: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["python3", str(SCRIPT), str(root), "--report", str(root / "report.json")],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_prepares_observable_no_ufs_no_watchdog_tree(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_tree(root)
            result = self.run_prepare(root)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads((root / "report.json").read_text(encoding="utf-8"))
            controls = report["diagnostic_controls"]
            self.assertTrue(controls["screen_serial_output"])
            self.assertFalse(controls["ufs_driver_present"])
            self.assertFalse(controls["qcom_hardware_watchdog_present"])
            self.assertFalse(controls["uefi_watchdog_timer_present"])
            self.assertTrue(controls["upstream_fv_layout_preserved"])
            self.assertTrue(controls["upstream_gzip_boot_payload_preserved"])
            all_text = "\n".join(
                path.read_text(encoding="utf-8")
                for path in (root / DEVICE).glob("*.inc")
            )
            self.assertNotIn(f"INF {UFS}\n", all_text)
            self.assertNotIn(f"INF {QCOM_WDOG}\n", all_text)
            self.assertIn(SDCC, all_text)
            self.assertIn(
                "USE_SCREEN_FOR_SERIAL_OUTPUT    = 1",
                (root / "Platforms/SurfaceDuo1Pkg/SurfaceDuo1.dsc").read_text(
                    encoding="utf-8"
                ),
            )
            config = (
                root / DEVICE / "Library/PlatformConfigurationMapLib/PlatformConfigurationMapLib.c"
            ).read_text(encoding="utf-8")
            self.assertIn('{"EnableUfsIOC", 0}', config)
            self.assertIn('{"UfsSmmuConfigForOtherBootDev", 0}', config)

    def test_rejects_existing_bootpack_override(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_tree(root)
            (root / DEVICE / "bootpack.json").write_text("{}\n", encoding="utf-8")
            result = self.run_prepare(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unexpected device bootpack override", result.stderr)

    def test_rejects_missing_expected_ufs_reference(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_tree(root)
            path = root / DEVICE / "DXE.inc"
            path.write_text(
                path.read_text(encoding="utf-8").replace(f"INF {UFS}\n", ""),
                encoding="utf-8",
            )
            result = self.run_prepare(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("expected 1 active", result.stderr)


class FirstBootDiagnosticBootImageTests(unittest.TestCase):
    def make_image(self, firmware: bytes, *, include_dtb: bool = True) -> bytes:
        payload = b"BOOTSHIM" + firmware
        kernel = gzip.compress(payload, mtime=0)
        if include_dtb:
            kernel += b"SYNTHETIC-DTB"
        header = bytearray(4096)
        header[0:8] = b"ANDROID!"
        header[8:12] = len(kernel).to_bytes(4, "little")
        header[16:20] = (6).to_bytes(4, "little")
        header[36:40] = (4096).to_bytes(4, "little")
        header[40:44] = (0).to_bytes(4, "little")
        return bytes(header) + kernel

    def test_accepts_upstream_style_gzip_payload(self) -> None:
        firmware = b"FIRMWARE" * 128
        result = validate_compressed_boot_image(self.make_image(firmware), firmware)
        self.assertTrue(result["gzip_payload"])
        self.assertEqual(result["bootshim_bytes"], len(b"BOOTSHIM"))
        self.assertEqual(result["appended_dtb_bytes"], len(b"SYNTHETIC-DTB"))
        self.assertEqual(
            result["embedded_exact_firmware_occurrences_after_decompression"], 1
        )

    def test_rejects_missing_appended_dtb(self) -> None:
        firmware = b"FIRMWARE" * 128
        with self.assertRaisesRegex(ValueError, "lacks appended DTB"):
            validate_compressed_boot_image(
                self.make_image(firmware, include_dtb=False), firmware
            )

    def test_rejects_wrong_firmware_binding(self) -> None:
        firmware = b"FIRMWARE" * 128
        with self.assertRaisesRegex(ValueError, "exact firmware once"):
            validate_compressed_boot_image(self.make_image(firmware), b"OTHER-FD")


if __name__ == "__main__":
    unittest.main()
