#!/usr/bin/env python3
"""Negative tests for offline provenance collector path separation."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


COLLECTOR_PATH = Path(__file__).with_name("collect-execution-tool-provenance.py")
SPEC = importlib.util.spec_from_file_location(
    "collect_execution_tool_provenance", COLLECTOR_PATH
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"cannot load collector: {COLLECTOR_PATH}")
collector = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = collector
SPEC.loader.exec_module(collector)


class OutputPathSeparationTests(unittest.TestCase):
    def test_normalized_overlap_relations(self) -> None:
        root = Path("/normalized-test-root")
        source = root / "source"
        self.assertTrue(collector.paths_overlap(source, source))
        self.assertTrue(collector.paths_overlap(source / "output", source))
        self.assertTrue(collector.paths_overlap(root, source))
        self.assertFalse(collector.paths_overlap(root / "source-copy", source))
        self.assertFalse(collector.paths_overlap(root / "sibling", source))

    def test_existing_directory_identity_ancestry(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(strict=True)
            source = root / "source"
            nested = source / "nested"
            sibling = root / "source-copy"
            nested.mkdir(parents=True)
            sibling.mkdir()
            self.assertTrue(collector.directory_is_same_or_below(source, source))
            self.assertTrue(collector.directory_is_same_or_below(nested, source))
            self.assertFalse(collector.directory_is_same_or_below(sibling, source))

    def test_case_alias_is_rejected_on_case_insensitive_volume(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(strict=True)
            source = root / "CaseSensitiveProbe"
            nested = source / "nested"
            nested.mkdir(parents=True)
            alias = root / "casesensitiveprobe" / "nested"
            if not alias.exists():
                self.skipTest("temporary volume is case-sensitive")
            self.assertTrue(collector.directory_is_same_or_below(alias, source))

    def test_explicit_evidence_overlap_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(strict=True)
            source = root / "source"
            source.mkdir()
            evidence_root = root / "evidence"
            evidence_root.mkdir()
            evidence = evidence_root / "input.bin"
            evidence.write_bytes(b"input")
            with self.assertRaisesRegex(
                collector.CollectionError, "output root overlaps public bundle"
            ):
                collector.reject_output_input_overlap(
                    evidence_root, source, {"public_bundle": evidence}
                )

    def test_source_nested_output_fails_before_creation_or_staging(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(strict=True)
            source = root / "source"
            (source / ".git").mkdir(parents=True)
            raw_inputs: dict[str, Path] = {}
            for name in (
                "public-bundle",
                "source-archive",
                "signing-key",
                "git-object-status",
                "tag-signature-status",
                "commit-signature-status",
                "binary",
                "libusb",
            ):
                path = root / name
                path.write_bytes(name.encode("ascii"))
                raw_inputs[name] = path
            output = source / "must-not-be-created"
            argv = [
                str(COLLECTOR_PATH),
                "--public-bundle",
                str(raw_inputs["public-bundle"]),
                "--source-archive",
                str(raw_inputs["source-archive"]),
                "--signing-key",
                str(raw_inputs["signing-key"]),
                "--source-git",
                str(source),
                "--git-object-status",
                str(raw_inputs["git-object-status"]),
                "--tag-signature-status",
                str(raw_inputs["tag-signature-status"]),
                "--commit-signature-status",
                str(raw_inputs["commit-signature-status"]),
                "--binary",
                str(raw_inputs["binary"]),
                "--libusb",
                str(raw_inputs["libusb"]),
                "--output-root",
                str(output),
            ]
            with mock.patch.object(sys, "argv", argv), mock.patch.object(
                collector,
                "stage_explicit_inputs",
                side_effect=AssertionError("staging must not be reached"),
            ), mock.patch.object(
                collector,
                "stage_git_source",
                side_effect=AssertionError("Git traversal must not be reached"),
            ):
                with self.assertRaisesRegex(
                    collector.CollectionError, "output root overlaps git source"
                ):
                    collector.main()
            self.assertFalse(output.exists())

    def test_stage_git_source_defense_fails_before_mkdir_or_walk(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary).resolve(strict=True) / "source"
            source.mkdir()
            destination = source / "must-not-be-created"
            with mock.patch.object(
                collector.os,
                "fwalk",
                side_effect=AssertionError("Git traversal must not be reached"),
            ):
                with self.assertRaisesRegex(
                    collector.CollectionError,
                    "Git staging destination overlaps source",
                ):
                    collector.stage_git_source(source, destination)
            self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
