#!/usr/bin/env python3
"""Collect LOCAL_ONLY Heimdall provenance from explicit offline inputs.

This collector never uses the network, installs software, accesses a USB
device, or executes the candidate Heimdall binary.  It emits facts for
validate-first-boot.py; it cannot approve an execution tool.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import stat
import struct
import subprocess
import sys
import tarfile
from pathlib import Path, PurePosixPath
from typing import Any


REPOSITORY = "https://git.sr.ht/~grimler/Heimdall"
TAG = "v2.2.2"
TAG_OBJECT = "2316fe346fece34726619498f34446b6d3df7c3a"
COMMIT = "d9554e7fa30a00abed7f0ac86b10e63c2c3b8e20"
TREE = "5ea9109a5005fbdc075443ebe16955b87d002ed5"
ARCHIVE_URL = "https://git.sr.ht/~grimler/Heimdall/archive/v2.2.2.tar.gz"
ARCHIVE_SHA256 = "7d01dd8bf9c2f93ea016ae8b059110c50cea49e78670e8a1333ebd5899cdaaa3"
SIGNING_FINGERPRINT = "2C7F29AE97891F6419A9E2CDB0076E490B71616B"
PUBLIC_BUNDLE_SHA256 = "33fecef855fbb956491dacabdbe3340f95256808a713eadd7596df6f00a7777c"
PUBLIC_ROOT = "public"
PUBLIC_PROVENANCE = f"{PUBLIC_ROOT}/PROVENANCE.json"
PUBLIC_ARTIFACT = f"{PUBLIC_ROOT}/artifact/heimdall-v2.2.2-macos-arm64"
PUBLIC_VERSION = f"{PUBLIC_ROOT}/inspection/build-1/version.stdout.log"
PUBLIC_DEPENDENCIES = f"{PUBLIC_ROOT}/inspection/build-1/otool-dependencies.txt"
PUBLIC_ENVIRONMENT = f"{PUBLIC_ROOT}/records/build-1/build.environment.txt"
PUBLIC_CONFIGURE_ARGV = f"{PUBLIC_ROOT}/records/build-1/configure.argv.txt"
PUBLIC_BUILD_ARGV = f"{PUBLIC_ROOT}/records/build-1/build.argv.txt"
PUBLIC_BUILD_STDOUT = f"{PUBLIC_ROOT}/records/build-1/build.stdout.log"
PUBLIC_BUILD_STDERR = f"{PUBLIC_ROOT}/records/build-1/build.stderr.log"
EXPECTED_BINARY_SHA256 = "15c7747eae890cc977d5759b838988585a418349c5fb0c5a02a41848c213875d"
EXPECTED_BINARY_BYTES = 146_552
EXPECTED_SIGNING_KEY_SHA256 = "f24de6a3e91aa19e0f18d92b1dc235b8066205784a0b17c6ec960e00906c40e9"
EXPECTED_SIGNING_KEY_BYTES = 4_922
EXPECTED_LIBUSB_SHA256 = "6f3528990c646b714a468bfdca1f24f68f66956392344ed52b2c16b929e791fa"
EXPECTED_LIBUSB_BYTES = 161_808
EXPECTED_LIBUSB_LOAD_PATH = "/opt/homebrew/opt/libusb/lib/libusb-1.0.0.dylib"
EXPECTED_LIBUSB_REAL_PATH = "/opt/homebrew/Cellar/libusb/1.0.30/lib/libusb-1.0.0.dylib"
EXPECTED_BINARY_LOAD_PATHS = [
    "/usr/lib/libobjc.A.dylib",
    "/System/Library/Frameworks/IOKit.framework/Versions/A/IOKit",
    "/System/Library/Frameworks/CoreFoundation.framework/Versions/A/CoreFoundation",
    EXPECTED_LIBUSB_LOAD_PATH,
    "/usr/lib/libc++.1.dylib",
    "/usr/lib/libSystem.B.dylib",
]
EXPECTED_LIBUSB_LOAD_PATHS = [
    "/usr/lib/libobjc.A.dylib",
    "/System/Library/Frameworks/IOKit.framework/Versions/A/IOKit",
    "/System/Library/Frameworks/CoreFoundation.framework/Versions/A/CoreFoundation",
    "/System/Library/Frameworks/Security.framework/Versions/A/Security",
    "/usr/lib/libSystem.B.dylib",
]
STATUS_PREFIX = "[GNUPG:] "
SIGNATURE_UNIX_TIMESTAMPS = {"tag": "1748250310", "commit": "1748250271"}
TERMINAL_SIGNATURE_KINDS = {
    "GOODSIG",
    "BADSIG",
    "EXPSIG",
    "EXPKEYSIG",
    "REVKEYSIG",
    "ERRSIG",
}
FORBIDDEN_HEIMDALL_ACTIONS = re.compile(
    r"(?:^|\s)(?:detect|download-pit|flash|print-pit|close-pc-screen)(?:\s|$)",
    re.IGNORECASE,
)


class CollectionError(RuntimeError):
    """A fail-closed provenance collection error."""


def fail(message: str) -> None:
    raise CollectionError(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def strict_json_bytes(data: bytes, label: str) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                fail(f"{label} contains duplicate JSON key {key!r}")
            value[key] = item
        return value

    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=reject_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        fail(f"cannot parse {label}: {exc}")
    if not isinstance(value, dict):
        fail(f"{label} must be a JSON object")
    return value


def reject_symlink_components(path: Path, label: str) -> None:
    absolute = path.expanduser().absolute()
    for component in (absolute, *absolute.parents):
        try:
            item = component.lstat()
        except OSError as exc:
            fail(f"cannot lstat {label} path component {component}: {exc}")
        if stat.S_ISLNK(item.st_mode):
            fail(f"{label} path contains a symbolic-link component: {component}")


def read_stable_input(path: Path, label: str) -> bytes:
    descriptor: int | None = None
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        before = os.fstat(descriptor)
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 8 * 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(descriptor)
    except OSError as exc:
        fail(f"cannot read {label} through a no-follow descriptor: {exc}")
    finally:
        if descriptor is not None:
            os.close(descriptor)
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ):
        fail(f"{label} changed while being read: {path}")
    return b"".join(chunks)


def safe_source_git_path(path: Path) -> Path:
    candidate = path.expanduser()
    reject_symlink_components(candidate, "git source")
    try:
        item = candidate.lstat()
    except OSError as exc:
        fail(f"cannot lstat git source: {exc}")
    if stat.S_ISLNK(item.st_mode):
        fail(f"git source must not be a symbolic link: {candidate}")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        fail(f"cannot resolve git source: {exc}")
    if not resolved.is_dir():
        fail(f"git source must be a directory: {resolved}")
    git_directory = resolved / ".git"
    try:
        git_stat = git_directory.lstat()
    except OSError as exc:
        fail(f"git source lacks a standalone .git directory: {exc}")
    if not stat.S_ISDIR(git_stat.st_mode) or stat.S_ISLNK(git_stat.st_mode):
        fail("git source .git must be a real directory, not a gitfile or symbolic link")
    return resolved


def run_checked(
    argv: list[str], *, cwd: Path | None = None, environment: dict[str, str]
) -> bytes:
    if not argv or any(not isinstance(item, str) or not item for item in argv):
        fail("invalid subprocess argv")
    try:
        completed = subprocess.run(
            argv,
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            env=environment,
        )
    except OSError as exc:
        fail(f"cannot execute {argv[0]}: {exc}")
    if completed.returncode != 0:
        stderr = completed.stderr.decode("utf-8", errors="replace").strip()
        fail(f"command failed ({completed.returncode}): {argv!r}: {stderr}")
    return completed.stdout


def git_environment(empty_home: Path) -> dict[str, str]:
    """Return a closed Git environment with no transport or ambient config."""

    return {
        "HOME": str(empty_home),
        "XDG_CONFIG_HOME": str(empty_home),
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "TZ": "UTC",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_NO_LAZY_FETCH": "1",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_ASKPASS": "/usr/bin/false",
        "SSH_ASKPASS": "/usr/bin/false",
        "GIT_SSH_COMMAND": "/usr/bin/false",
        "GIT_PROTOCOL_FROM_USER": "0",
        "GIT_ALLOW_PROTOCOL": "",
        "GIT_OPTIONAL_LOCKS": "0",
    }


def git_argv(source: Path, *arguments: str) -> list[str]:
    return [
        "/usr/bin/git",
        "--no-replace-objects",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "core.hooksPath=/dev/null",
        "-c",
        "maintenance.auto=false",
        "-c",
        "gc.auto=0",
        "-c",
        "protocol.allow=never",
        "-C",
        str(source),
        *arguments,
    ]


def git_bytes(
    source: Path, environment: dict[str, str], *arguments: str
) -> bytes:
    return run_checked(
        git_argv(source, *arguments), environment=environment
    )


def git_text(
    source: Path, environment: dict[str, str], *arguments: str
) -> str:
    return git_bytes(source, environment, *arguments).decode(
        "utf-8", errors="strict"
    )


def validate_local_git_layout(source: Path) -> None:
    """Reject repository features that can escape local immutable objects."""

    git_directory = source / ".git"
    for administrative_marker in ("commondir", "gitdir"):
        marker = git_directory / administrative_marker
        if marker.exists() or marker.is_symlink():
            fail(
                "Git source contains a forbidden linked-worktree marker: "
                f"{marker}"
            )
    for forbidden in (
        git_directory / "objects" / "info" / "alternates",
        git_directory / "objects" / "info" / "http-alternates",
        git_directory / "info" / "alternates",
        git_directory / "info" / "grafts",
    ):
        if forbidden.exists() or forbidden.is_symlink():
            fail(f"Git source uses a forbidden alternates file: {forbidden}")
    replace_root = git_directory / "refs" / "replace"
    if replace_root.exists() or replace_root.is_symlink():
        fail("Git source contains replace refs")
    packed_refs = git_directory / "packed-refs"
    if packed_refs.exists():
        packed_data = read_stable_input(packed_refs, "Git packed refs")
        if b"refs/replace/" in packed_data:
            fail("Git source packed refs contain replace refs")
    config = strict_git_config(git_directory / "config")
    forbidden_keys = {
        "core.fsmonitor",
        "core.hookspath",
        "extensions.objectformat",
        "extensions.partialclone",
    }
    for key in config:
        lowered = key.lower()
        if lowered in forbidden_keys or lowered.endswith(".promisor") \
                or lowered.endswith(".partialclonefilter"):
            fail(f"Git source contains forbidden repository config: {key}")


def strict_git_config(path: Path) -> dict[str, str]:
    """Parse enough local config to reject active/offline-unsafe features."""

    data = read_stable_input(path, "Git repository config")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        fail(f"Git repository config is not UTF-8: {exc}")
    if re.search(r"^\s*\[(?:include|includeIf)\b", text, re.IGNORECASE | re.MULTILINE):
        fail("Git repository config contains an include section")
    section = ""
    values: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", ";")):
            continue
        section_match = re.fullmatch(r'\[\s*([A-Za-z0-9.-]+)(?:\s+"[^"]*")?\s*\]', stripped)
        if section_match:
            section = section_match.group(1).lower()
            continue
        item_match = re.fullmatch(r"([A-Za-z0-9.-]+)\s*=\s*(.*)", stripped)
        if item_match is None or not section:
            fail(f"unsupported Git repository config line: {line!r}")
        full_key = f"{section}.{item_match.group(1).lower()}"
        if full_key in values:
            fail(f"Git repository config contains duplicate key: {full_key}")
        values[full_key] = item_match.group(2)
    passive_suffixes = {
        "core.repositoryformatversion",
        "core.filemode",
        "core.bare",
        "core.logallrefupdates",
        "core.ignorecase",
        "core.precomposeunicode",
    }
    unsupported = sorted(
        key
        for key in values
        if key not in passive_suffixes
        and not key.startswith("remote.")
        and not key.startswith("branch.")
    )
    if unsupported:
        fail(f"Git repository config contains unsupported keys: {unsupported}")
    for key in values:
        if key.startswith("remote.") and not key.endswith((".url", ".fetch")):
            fail(f"Git repository config contains unsupported remote key: {key}")
        if key.startswith("branch.") and not key.endswith((".remote", ".merge")):
            fail(f"Git repository config contains unsupported branch key: {key}")
    return values


def validate_git_source(
    source: Path, environment: dict[str, str]
) -> tuple[bytes, bytes]:
    validate_local_git_layout(source)
    if git_text(source, environment, "rev-parse", "--is-inside-work-tree").strip() != "true":
        fail("git source is not a work tree")
    if git_text(source, environment, "rev-parse", "--is-shallow-repository").strip() != "false":
        fail("git source must be a full, non-shallow repository")
    facts = {
        "tag_object": git_text(source, environment, "rev-parse", f"refs/tags/{TAG}").strip(),
        "commit": "",
        "tree": "",
    }
    if git_text(source, environment, "cat-file", "-t", TAG_OBJECT).strip() != "tag":
        fail("fixed tag object is absent or is not an annotated tag")
    tag_data = git_text(source, environment, "cat-file", "-p", TAG_OBJECT)
    tag_object_match = re.match(r"^object ([0-9a-f]{40})\n", tag_data)
    if tag_object_match is None:
        fail("fixed tag object lacks a canonical target object")
    facts["commit"] = tag_object_match.group(1)
    if git_text(source, environment, "cat-file", "-t", COMMIT).strip() != "commit":
        fail("fixed commit object is absent or is not a commit")
    commit_data = git_text(source, environment, "cat-file", "-p", COMMIT)
    commit_tree_match = re.match(r"^tree ([0-9a-f]{40})\n", commit_data)
    if commit_tree_match is None:
        fail("fixed commit object lacks a canonical tree")
    facts["tree"] = commit_tree_match.group(1)
    if git_text(source, environment, "cat-file", "-t", TREE).strip() != "tree":
        fail("fixed tree object is absent or is not a tree")
    expected = {"tag_object": TAG_OBJECT, "commit": COMMIT, "tree": TREE}
    if facts != expected:
        fail(f"git object identity mismatch: expected {expected}, found {facts}")
    if git_text(source, environment, "status", "--porcelain=v1", "--untracked-files=all"):
        fail("git source work tree is not clean")
    git_bytes(source, environment, "fsck", "--full", "--strict", "--no-dangling")
    manifest = git_bytes(source, environment, "ls-tree", "-r", "--full-tree", TREE)
    if not manifest or b"160000 commit " in manifest or b"120000 blob " in manifest:
        fail("git tree manifest is empty or contains a submodule/symbolic-link entry")
    source_export = git_bytes(source, environment, "archive", "--format=tar", TREE)
    if not source_export:
        fail("git archive source export is empty")
    return manifest, source_export


def validate_source_archive_against_git(
    archive_path: Path, source: Path, environment: dict[str, str]
) -> None:
    try:
        with tarfile.open(archive_path, mode="r:gz") as archive:
            members = archive.getmembers()
            regular: dict[str, tarfile.TarInfo] = {}
            for member in members:
                raw = member.name.rstrip("/")
                path = PurePosixPath(raw)
                if not raw or path.is_absolute() or ".." in path.parts:
                    fail(f"unsafe fixed-source archive member: {member.name!r}")
                if not path.parts or path.parts[0] != "Heimdall-v2.2.2":
                    fail(f"unexpected fixed-source archive root: {member.name!r}")
                if member.issym() or member.islnk() or member.isdev() or member.isfifo():
                    fail(f"unsupported fixed-source archive member type: {member.name!r}")
                if member.isfile():
                    relative = PurePosixPath(*path.parts[1:]).as_posix()
                    if not relative or relative in regular:
                        fail(f"duplicate/non-canonical fixed-source member: {member.name!r}")
                    regular[relative] = member

            git_entries: dict[str, tuple[str, str]] = {}
            manifest = git_text(source, environment, "ls-tree", "-r", "--full-tree", TREE)
            for line in manifest.splitlines():
                match = re.fullmatch(r"(100644|100755) blob ([0-9a-f]{40})\t(.+)", line)
                if match is None:
                    fail(f"unsupported Git tree entry in fixed source: {line!r}")
                mode, object_id, relative = match.groups()
                if relative in git_entries:
                    fail(f"duplicate Git tree path: {relative!r}")
                git_entries[relative] = (mode, object_id)
            if set(regular) != set(git_entries):
                missing = sorted(set(git_entries) - set(regular))[:5]
                extra = sorted(set(regular) - set(git_entries))[:5]
                fail(f"fixed-source archive/tree path mismatch: missing={missing}, extra={extra}")
            for relative, member in regular.items():
                mode, object_id = git_entries[relative]
                stream = archive.extractfile(member)
                if stream is None:
                    fail(f"cannot extract fixed-source member: {relative}")
                if stream.read() != git_bytes(source, environment, "cat-file", "blob", object_id):
                    fail(f"fixed-source content differs from Git blob: {relative}")
                archive_executable = bool(member.mode & 0o111)
                git_executable = mode == "100755"
                if archive_executable != git_executable:
                    fail(f"fixed-source executable mode differs from Git tree: {relative}")
    except (OSError, tarfile.TarError) as exc:
        fail(f"cannot validate fixed-source archive: {exc}")


def validate_git_object_status(path: Path) -> bytes:
    data = read_stable_input(path, "Git object status")
    if not data or b"\x00" in data:
        fail("Git object status is empty or binary")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        fail(f"Git object status is not UTF-8: {exc}")
    for marker in (TAG_OBJECT, COMMIT, TREE):
        if marker not in text:
            fail(f"Git object status lacks fixed object marker: {marker}")
    return data


def validate_native_gnupg_status(path: Path, label: str) -> bytes:
    data = read_stable_input(path, f"{label} native GnuPG status")
    if not data or b"\x00" in data:
        fail(f"{label} native GnuPG status is empty or binary")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        fail(f"{label} native GnuPG status is not UTF-8: {exc}")
    lines = text.splitlines()
    status_lines = [line for line in lines if line.startswith(STATUS_PREFIX)]
    if not status_lines:
        fail(f"{label} native GnuPG status contains no raw [GNUPG:] records")
    valid_signatures: list[tuple[str, str]] = []
    terminal_signatures: list[list[str]] = []
    for line in status_lines:
        fields = line.split()
        if len(fields) >= 2 and fields[1] == "VALIDSIG":
            if len(fields) != 12:
                fail(f"{label} native GnuPG status contains a malformed VALIDSIG record")
            if label not in SIGNATURE_UNIX_TIMESTAMPS:
                fail(f"unsupported native GnuPG status label: {label}")
            if fields[2].upper() != SIGNING_FINGERPRINT:
                fail(f"{label} native GnuPG VALIDSIG signing fingerprint mismatch")
            expected_tail = [
                "2025-05-26",
                SIGNATURE_UNIX_TIMESTAMPS[label],
                "0",
                "4",
                "0",
                "1",
                "10",
                "00",
                SIGNING_FINGERPRINT,
            ]
            if fields[3:] != expected_tail:
                fail(f"{label} native GnuPG VALIDSIG fixed fields mismatch")
            valid_signatures.append((fields[2].upper(), fields[11].upper()))
        if len(fields) >= 2 and fields[1] in TERMINAL_SIGNATURE_KINDS:
            terminal_signatures.append(fields)
    if len(valid_signatures) != 1:
        fail(f"{label} native GnuPG status must contain exactly one VALIDSIG record")
    for signer, primary in valid_signatures:
        if not re.fullmatch(r"[0-9A-F]{40}", signer):
            fail(f"{label} native GnuPG VALIDSIG signing fingerprint is malformed")
        if primary != SIGNING_FINGERPRINT:
            fail(f"{label} native GnuPG VALIDSIG primary fingerprint mismatch")
    expired = [fields for fields in terminal_signatures if fields[1] == "EXPKEYSIG"]
    if len(terminal_signatures) != 1 or len(expired) != 1:
        fail(
            f"{label} native GnuPG status must retain exactly one EXPKEYSIG terminal "
            "records and no other terminal signature status"
        )
    expected_signers = sorted(signer[-16:] for signer, _ in valid_signatures)
    expired_signers: list[str] = []
    for fields in expired:
        if len(fields) < 3 or not re.fullmatch(
            r"(?:[0-9A-F]{16}|[0-9A-F]{40})", fields[2].upper()
        ):
            fail(f"{label} native GnuPG EXPKEYSIG signing key ID is malformed")
        expired_signers.append(fields[2].upper()[-16:])
    if sorted(expired_signers) != expected_signers:
        fail(f"{label} native GnuPG EXPKEYSIG does not bind the VALIDSIG signing key")
    if not any(line.startswith(f"{STATUS_PREFIX}KEYEXPIRED ") for line in status_lines):
        fail(f"{label} native GnuPG status does not retain KEYEXPIRED")
    prohibited_failure_kinds = {"FAILURE", "ERROR", "NODATA", "NO_PUBKEY"}
    observed_failure_kinds = {
        fields[1]
        for line in status_lines
        if len((fields := line.split())) >= 2
        and fields[1] in prohibited_failure_kinds
    }
    if observed_failure_kinds:
        fail(
            f"{label} native GnuPG status contains failure records: "
            f"{sorted(observed_failure_kinds)}"
        )
    return data


def aggregate_native_gnupg_status(tag_data: bytes, commit_data: bytes) -> bytes:
    def with_newline(value: bytes) -> bytes:
        return value if value.endswith(b"\n") else value + b"\n"

    return (
        b"----- BEGIN UNMODIFIED TAG STATUS INPUT -----\n"
        + with_newline(tag_data)
        + b"----- END UNMODIFIED TAG STATUS INPUT -----\n"
        + b"----- BEGIN UNMODIFIED COMMIT STATUS INPUT -----\n"
        + with_newline(commit_data)
        + b"----- END UNMODIFIED COMMIT STATUS INPUT -----\n"
    )


def archive_members(bundle: Path) -> tuple[tarfile.TarFile, dict[str, tarfile.TarInfo]]:
    try:
        archive = tarfile.open(bundle, mode="r:gz")
        members = archive.getmembers()
    except (OSError, tarfile.TarError) as exc:
        fail(f"cannot read public bundle: {exc}")
    by_name: dict[str, tarfile.TarInfo] = {}
    for member in members:
        raw_name = member.name
        if raw_name.endswith("/"):
            raw_name = raw_name[:-1]
        name = str(PurePosixPath(raw_name))
        path = PurePosixPath(name)
        if (
            name in (".", "")
            or path.is_absolute()
            or ".." in path.parts
            or "\x00" in name
            or name != raw_name
        ):
            archive.close()
            fail(f"unsafe or non-canonical public-bundle member: {member.name!r}")
        if member.issym() or member.islnk() or member.isdev() or member.isfifo():
            archive.close()
            fail(f"unsupported public-bundle member type: {member.name!r}")
        if name in by_name:
            archive.close()
            fail(f"duplicate public-bundle member: {name}")
        by_name[name] = member
    return archive, by_name


def read_bundle_member(
    archive: tarfile.TarFile, members: dict[str, tarfile.TarInfo], name: str
) -> bytes:
    member = members.get(name)
    if member is None or not member.isfile():
        fail(f"required public-bundle member is missing: {name}")
    stream = archive.extractfile(member)
    if stream is None:
        fail(f"cannot extract public-bundle member: {name}")
    return stream.read()


def parse_recorded_argv(data: bytes, label: str) -> list[str]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        fail(f"{label} argv is not UTF-8: {exc}")
    values: list[str] = []
    for index, line in enumerate(text.splitlines()):
        match = re.fullmatch(r"(\d{4})\t'(.*)'", line)
        if match is None or int(match.group(1)) != index:
            fail(f"{label} argv record is malformed at element {index}")
        values.append(match.group(2).replace("'\\''", "'"))
    if not values or any(FORBIDDEN_HEIMDALL_ACTIONS.search(value) for value in values):
        fail(f"{label} argv is empty or contains a forbidden Heimdall action")
    return values


def canonical_host() -> dict[str, str]:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "darwin" and machine in ("arm64", "aarch64"):
        return {"os": "darwin", "architecture": "arm64", "binary_format": "Mach-O"}
    fail(f"the audited v3 public bundle requires a Darwin ARM64 collector host, found {system}/{machine}")


def macho_dylib_load_paths(data: bytes, label: str, expected_file_type: int) -> list[str]:
    if len(data) < 32 or data[:4] != b"\xcf\xfa\xed\xfe":
        fail(f"{label} is not a little-endian Mach-O 64-bit file")
    cpu_type, file_type, command_count, command_bytes = struct.unpack_from(
        "<I4xIII", data, 4
    )
    if cpu_type != 0x0100000C or file_type != expected_file_type:
        fail(f"{label} Mach-O type or ARM64 architecture mismatch")
    offset = 32
    command_end = offset + command_bytes
    if command_end > len(data):
        fail(f"{label} Mach-O load-command table is truncated")
    load_paths: list[str] = []
    dylib_commands = {
        0xC,  # LC_LOAD_DYLIB
        0x18 | 0x80000000,  # LC_LOAD_WEAK_DYLIB
        0x1F | 0x80000000,  # LC_REEXPORT_DYLIB
        0x20,  # LC_LAZY_LOAD_DYLIB (does not carry LC_REQ_DYLD)
        0x20 | 0x80000000,  # tolerate the defensive required-bit form
        0x23 | 0x80000000,  # LC_LOAD_UPWARD_DYLIB
    }
    for _ in range(command_count):
        if offset + 8 > command_end:
            fail(f"{label} Mach-O load command is truncated")
        command, command_size = struct.unpack_from("<II", data, offset)
        if command_size < 8 or offset + command_size > command_end:
            fail(f"{label} Mach-O load command has an invalid size")
        if command in dylib_commands:
            if command_size < 24:
                fail(f"{label} Mach-O dylib command is truncated")
            name_offset = struct.unpack_from("<I", data, offset + 8)[0]
            if name_offset < 24 or name_offset >= command_size:
                fail(f"{label} Mach-O dylib name offset is invalid")
            raw = data[offset + name_offset : offset + command_size].split(b"\x00", 1)[0]
            try:
                load_paths.append(raw.decode("utf-8"))
            except UnicodeDecodeError as exc:
                fail(f"{label} Mach-O dylib path is not UTF-8: {exc}")
        offset += command_size
    if offset != command_end:
        fail(f"{label} Mach-O load-command size does not match its header")
    return load_paths


def inspect_binary_bytes(data: bytes, host: dict[str, str]) -> list[str]:
    if len(data) != EXPECTED_BINARY_BYTES:
        fail(f"binary byte count mismatch: {len(data)}")
    if hashlib.sha256(data).hexdigest() != EXPECTED_BINARY_SHA256:
        fail("binary SHA-256 mismatch")
    if host != {"os": "darwin", "architecture": "arm64", "binary_format": "Mach-O"}:
        fail("binary host identity is not Darwin ARM64")
    paths = macho_dylib_load_paths(data, "binary", 2)
    if paths != EXPECTED_BINARY_LOAD_PATHS:
        fail(f"binary Mach-O dynamic-load allowlist mismatch: {paths!r}")
    return paths


def inspect_libusb(path: Path, host: dict[str, str]) -> bytes:
    data = read_stable_input(path, "libusb")
    if len(data) != EXPECTED_LIBUSB_BYTES or hashlib.sha256(data).hexdigest() != EXPECTED_LIBUSB_SHA256:
        fail("libusb byte count or SHA-256 mismatch")
    if host != {"os": "darwin", "architecture": "arm64", "binary_format": "Mach-O"}:
        fail("the audited v3 candidate is only bound to Darwin ARM64")
    paths = macho_dylib_load_paths(data, "libusb", 6)
    if paths != EXPECTED_LIBUSB_LOAD_PATHS:
        fail(f"libusb Mach-O dynamic-load allowlist mismatch: {paths!r}")
    return data


def write_exclusive(path: Path, data: bytes, mode: int = 0o600) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    except OSError as exc:
        fail(f"cannot create output file exclusively {path}: {exc}")
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def copy_exclusive(
    source: Path,
    destination: Path,
    expected: bytes | None = None,
    *,
    mode: int = 0o600,
) -> None:
    data = read_stable_input(source, "input copy")
    if expected is not None and data != expected:
        fail(f"explicit input disagrees with audited public bundle: {source}")
    write_exclusive(destination, data, mode)


def binding(root: Path, path: Path) -> dict[str, Any]:
    resolved = path.resolve(strict=True)
    relative = resolved.relative_to(root.resolve(strict=True))
    item = resolved.stat()
    if item.st_nlink != 1 or not stat.S_ISREG(item.st_mode):
        fail(f"staged evidence file is not a single-link regular file: {resolved}")
    return {
        "path": relative.as_posix(),
        "bytes": item.st_size,
        "sha256": sha256_file(resolved),
    }


def assert_distinct_inputs(inputs: dict[str, Path]) -> None:
    identities: dict[tuple[int, int], list[str]] = {}
    for name, path in inputs.items():
        item = path.stat()
        identities.setdefault((item.st_dev, item.st_ino), []).append(name)
    for names in identities.values():
        if len(names) > 1:
            fail(f"explicit inputs share an inode unexpectedly: {sorted(names)}")


def stage_explicit_inputs(
    raw_inputs: dict[str, Path], staging: Path
) -> tuple[dict[str, Path], dict[str, dict[str, Any]]]:
    """Take one no-follow descriptor snapshot of each file into private staging."""

    staged: dict[str, Path] = {}
    manifest: dict[str, dict[str, Any]] = {}
    seen: dict[tuple[int, int], str] = {}
    filenames = {
        "public_bundle": "public-bundle.tar.gz",
        "source_archive": "source-archive.tar.gz",
        "signing_key": "signing-key.asc",
        "git_object_status": "git-object-status.txt",
        "tag_signature_status": "tag-signature-status.raw.txt",
        "commit_signature_status": "commit-signature-status.raw.txt",
        "binary": "heimdall-v2.2.2-macos-arm64",
        "libusb": "libusb-1.0.0.dylib",
    }
    staging.mkdir(mode=0o700)
    for name, raw in raw_inputs.items():
        candidate = raw.expanduser().absolute()
        reject_symlink_components(candidate, name.replace("_", " "))
        descriptor: int | None = None
        try:
            descriptor = os.open(
                candidate, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
            )
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                fail(f"{name} must be a single-link regular file: {candidate}")
            identity = (before.st_dev, before.st_ino)
            if identity in seen:
                fail(f"explicit inputs {seen[identity]!r} and {name!r} share an inode")
            seen[identity] = name
            chunks: list[bytes] = []
            while True:
                chunk = os.read(descriptor, 8 * 1024 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
            after = os.fstat(descriptor)
        except OSError as exc:
            fail(f"cannot snapshot {name} through a no-follow descriptor: {exc}")
        finally:
            if descriptor is not None:
                os.close(descriptor)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            fail(f"{name} changed while being snapshotted")
        data = b"".join(chunks)
        destination = staging / filenames[name]
        write_exclusive(destination, data)
        staged[name] = destination
        manifest[name] = {
            "path": str(candidate),
            "source_device": before.st_dev,
            "source_inode": before.st_ino,
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }
    assert_distinct_inputs(staged)
    return staged, manifest


def stage_git_source(
    source: Path, destination: Path
) -> tuple[Path, dict[str, Any]]:
    """Snapshot a standalone Git work tree without following directory entries."""

    destination.mkdir(mode=0o700)
    seen: dict[tuple[int, int], str] = {}
    rows: list[str] = []
    file_count = 0
    try:
        walker = os.fwalk(source, topdown=True, follow_symlinks=False)
        for directory, names, files, directory_fd in walker:
            relative_directory = Path(directory).relative_to(source)
            output_directory = destination / relative_directory
            output_directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            for name in sorted(names):
                try:
                    item = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                except OSError as exc:
                    fail(f"cannot stat Git source directory entry {name!r}: {exc}")
                if not stat.S_ISDIR(item.st_mode):
                    fail(f"Git source contains a non-directory traversal entry: {directory}/{name}")
            for name in sorted(files):
                relative = (relative_directory / name).as_posix()
                descriptor: int | None = None
                try:
                    descriptor = os.open(
                        name,
                        os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                        dir_fd=directory_fd,
                    )
                    before = os.fstat(descriptor)
                    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                        fail(f"Git source entry is not a single-link regular file: {relative}")
                    identity = (before.st_dev, before.st_ino)
                    if identity in seen:
                        fail(f"Git source files share an inode: {seen[identity]!r}, {relative!r}")
                    seen[identity] = relative
                    chunks: list[bytes] = []
                    while True:
                        chunk = os.read(descriptor, 8 * 1024 * 1024)
                        if not chunk:
                            break
                        chunks.append(chunk)
                    after = os.fstat(descriptor)
                except OSError as exc:
                    fail(f"cannot snapshot Git source entry {relative!r}: {exc}")
                finally:
                    if descriptor is not None:
                        os.close(descriptor)
                if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
                    after.st_dev,
                    after.st_ino,
                    after.st_size,
                    after.st_mtime_ns,
                ):
                    fail(f"Git source entry changed while being snapshotted: {relative}")
                data = b"".join(chunks)
                executable = bool(before.st_mode & 0o111)
                write_exclusive(
                    output_directory / name, data, 0o700 if executable else 0o600
                )
                rows.append(
                    f"{'100755' if executable else '100644'}\t{len(data)}\t"
                    f"{hashlib.sha256(data).hexdigest()}\t{relative}\n"
                )
                file_count += 1
    except OSError as exc:
        fail(f"cannot traverse Git source snapshot: {exc}")
    if not file_count:
        fail("Git source snapshot is empty")
    manifest_data = "".join(sorted(rows)).encode("utf-8")
    return destination, {
        "path": str(source),
        "snapshot_files": file_count,
        "snapshot_manifest_sha256": hashlib.sha256(manifest_data).hexdigest(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public-bundle", type=Path, required=True)
    parser.add_argument("--source-archive", type=Path, required=True)
    parser.add_argument("--signing-key", type=Path, required=True)
    parser.add_argument("--source-git", type=Path, required=True)
    parser.add_argument("--git-object-status", type=Path, required=True)
    parser.add_argument("--tag-signature-status", type=Path, required=True)
    parser.add_argument("--commit-signature-status", type=Path, required=True)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--libusb", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()

    raw_inputs = {
        "public_bundle": args.public_bundle,
        "source_archive": args.source_archive,
        "signing_key": args.signing_key,
        "git_object_status": args.git_object_status,
        "tag_signature_status": args.tag_signature_status,
        "commit_signature_status": args.commit_signature_status,
        "binary": args.binary,
        "libusb": args.libusb,
    }
    source_git_input = safe_source_git_path(args.source_git)
    output_root = args.output_root.expanduser()
    if output_root.exists() or output_root.is_symlink():
        fail(f"output root already exists: {output_root}")
    reject_symlink_components(output_root.parent, "output parent")
    output_parent = output_root.parent.resolve(strict=True)
    output_root = output_parent / output_root.name

    # The absent private root is the trust boundary. Every file input is read
    # once from one O_NOFOLLOW descriptor, then all validation uses the staged
    # snapshot. The Git work tree is likewise snapshotted before any Git
    # process runs, then inspected only through the closed environment below.
    output_root.mkdir(mode=0o700)
    input_staging = output_root / "LOCAL_ONLY-input-staging"
    inputs, input_manifest = stage_explicit_inputs(raw_inputs, input_staging)
    source_git, source_git_manifest = stage_git_source(
        source_git_input, output_root / "LOCAL_ONLY-git-source-staging"
    )
    empty_home = output_root / "LOCAL_ONLY-empty-git-home"
    empty_home.mkdir(mode=0o700)
    git_env = git_environment(empty_home)

    if sha256_file(inputs["public_bundle"]) != PUBLIC_BUNDLE_SHA256:
        fail("audited public v3 bundle SHA-256 mismatch")
    if sha256_file(inputs["source_archive"]) != ARCHIVE_SHA256:
        fail("fixed source archive SHA-256 mismatch")
    if (
        inputs["signing_key"].stat().st_size != EXPECTED_SIGNING_KEY_BYTES
        or sha256_file(inputs["signing_key"]) != EXPECTED_SIGNING_KEY_SHA256
    ):
        fail("fixed signing-key byte count or SHA-256 mismatch")

    tree_manifest, source_export = validate_git_source(source_git, git_env)
    validate_source_archive_against_git(inputs["source_archive"], source_git, git_env)
    git_object_status = validate_git_object_status(inputs["git_object_status"])
    tag_signature_status = validate_native_gnupg_status(
        inputs["tag_signature_status"], "tag"
    )
    commit_signature_status = validate_native_gnupg_status(
        inputs["commit_signature_status"], "commit"
    )
    gnupg_status = aggregate_native_gnupg_status(
        tag_signature_status, commit_signature_status
    )
    host = canonical_host()

    archive, members = archive_members(inputs["public_bundle"])
    try:
        public_provenance_data = read_bundle_member(archive, members, PUBLIC_PROVENANCE)
        public_provenance = strict_json_bytes(public_provenance_data, "public provenance")
        public_binary = read_bundle_member(archive, members, PUBLIC_ARTIFACT)
        public_version = read_bundle_member(archive, members, PUBLIC_VERSION)
        public_dependencies = read_bundle_member(archive, members, PUBLIC_DEPENDENCIES)
        public_environment = read_bundle_member(archive, members, PUBLIC_ENVIRONMENT)
        configure_argv_data = read_bundle_member(archive, members, PUBLIC_CONFIGURE_ARGV)
        build_argv_data = read_bundle_member(archive, members, PUBLIC_BUILD_ARGV)
        build_stdout = read_bundle_member(archive, members, PUBLIC_BUILD_STDOUT)
        build_stderr = read_bundle_member(archive, members, PUBLIC_BUILD_STDERR)
    finally:
        archive.close()

    source_facts = public_provenance.get("source")
    output_facts = public_provenance.get("output")
    authorization = public_provenance.get("authorization")
    expected_source = {
        "canonical_url": REPOSITORY,
        "tag": TAG,
        "tag_object_sha1": TAG_OBJECT,
        "peeled_commit_sha1": COMMIT,
        "tree_sha1": TREE,
    }
    if not isinstance(source_facts, dict) or any(source_facts.get(k) != v for k, v in expected_source.items()):
        fail("public provenance source identity mismatch")
    if not isinstance(output_facts, dict) or output_facts.get("sha256") != EXPECTED_BINARY_SHA256:
        fail("public provenance binary identity mismatch")
    if authorization != {
        "deployable": False,
        "device_access_authorized": False,
        "device_write_authorized": False,
        "usb_or_adb_access_performed": False,
        "heimdall_device_actions_run": [],
    }:
        fail("public provenance authorization boundary mismatch")
    if sha256_file(inputs["binary"]) != hashlib.sha256(public_binary).hexdigest():
        fail("explicit binary is not byte-identical to the audited public v3 artifact")
    binary_load_paths = inspect_binary_bytes(public_binary, host)
    if host["binary_format"] != "Mach-O" or b"arm64" not in public_provenance_data:
        fail("audited public v3 host/architecture is not Darwin ARM64")

    dependencies_text = public_dependencies.decode("utf-8", errors="strict")
    if dependencies_text.count(EXPECTED_LIBUSB_LOAD_PATH) != 1:
        fail("dynamic-dependency record does not bind exactly one audited libusb load path")
    if binary_load_paths.count(EXPECTED_LIBUSB_LOAD_PATH) != 1:
        fail("binary does not directly bind exactly one audited libusb load path")
    libusb_real = inputs["libusb"]
    if input_manifest["libusb"]["path"] != EXPECTED_LIBUSB_REAL_PATH:
        fail(f"libusb input must be the audited file {EXPECTED_LIBUSB_REAL_PATH}")
    try:
        resolved_load_path = Path(EXPECTED_LIBUSB_LOAD_PATH).resolve(strict=True)
    except OSError as exc:
        fail(f"cannot resolve the binary's fixed libusb load path: {exc}")
    if str(resolved_load_path) != EXPECTED_LIBUSB_REAL_PATH:
        fail("binary libusb load path does not resolve to the explicit audited dependency")
    inspect_libusb(libusb_real, host)

    configure_argv = parse_recorded_argv(configure_argv_data, "configure")
    build_argv = parse_recorded_argv(build_argv_data, "build")
    if configure_argv[:2] != ["/opt/homebrew/bin/cmake", "-S"] or build_argv[:2] != [
        "/opt/homebrew/bin/cmake",
        "--build",
    ]:
        fail("audited public build argv is not the expected offline CMake recipe")
    environment_text = public_environment.decode("utf-8", errors="strict")
    if re.search(r"^(?:DYLD_|LD_)", environment_text, re.MULTILINE):
        fail("audited build environment contains a loader-injection variable")

    version_data = public_version
    if not re.search(rb"(?:Heimdall\s+)?v2\.2\.2(?:\s|$)", version_data):
        fail("version record lacks v2.2.2")

    records = output_root / "records"
    try:
        destinations = {
            "archive": records / "source-archive.tar.gz",
            "signing_key": records / "signing-key.asc",
            "git_object_status": records / "git-object-status.txt",
            "git_signature_status": records / "git-signature-status.raw.txt",
            "source_export": records / "git-source-export.tar",
            "tree_manifest": records / "git-tree-manifest.txt",
            "environment": records / "build-environment.txt",
            "toolchain_manifest": records / "public-provenance.json",
            "dependency_manifest": records / "libusb-1.0.0.dylib",
            "build_log": records / "build-log.txt",
            "artifact": records / "heimdall-v2.2.2-macos-arm64",
            "version_output": records / "version-output.txt",
            "dynamic_dependencies": records / "dynamic-dependencies.txt",
        }
        input_manifest["source_git"] = {
            **source_git_manifest,
            "tag_object": TAG_OBJECT,
            "commit": COMMIT,
            "tree": TREE,
        }
        input_manifest_path = output_root / "LOCAL_ONLY-input-manifest.json"
        write_exclusive(
            input_manifest_path,
            (
                json.dumps(input_manifest, indent=2, sort_keys=True, ensure_ascii=True)
                + "\n"
            ).encode("utf-8"),
        )
        copy_exclusive(inputs["source_archive"], destinations["archive"])
        copy_exclusive(inputs["signing_key"], destinations["signing_key"])
        copy_exclusive(
            inputs["git_object_status"],
            destinations["git_object_status"],
            git_object_status,
        )
        write_exclusive(destinations["git_signature_status"], gnupg_status)
        write_exclusive(destinations["source_export"], source_export)
        write_exclusive(destinations["tree_manifest"], tree_manifest)
        write_exclusive(destinations["environment"], public_environment)
        write_exclusive(destinations["toolchain_manifest"], public_provenance_data)
        copy_exclusive(inputs["libusb"], destinations["dependency_manifest"])
        write_exclusive(
            destinations["build_log"],
            b"configure.argv\n" + configure_argv_data + b"build.argv\n" + build_argv_data
            + b"build.stdout\n" + build_stdout + b"build.stderr\n" + build_stderr,
        )
        copy_exclusive(
            inputs["binary"], destinations["artifact"], public_binary, mode=0o700
        )
        write_exclusive(destinations["version_output"], version_data)
        write_exclusive(destinations["dynamic_dependencies"], public_dependencies)

        staged_identities = {
            (path.stat().st_dev, path.stat().st_ino) for path in destinations.values()
        }
        if len(destinations) != 13 or len(staged_identities) != 13:
            fail("staged provenance must contain exactly 13 distinct bound records")

        report = {
            "schema": 1,
            "report_type": "sm-t860-execution-tool-provenance",
            "device_writes_performed": False,
            "deployable": False,
            "explicit_device_write_authorization_recorded": False,
            "evidence_root": str(output_root.resolve(strict=True)),
            "source": {
                "repository": REPOSITORY,
                "tag": TAG,
                "tag_object": TAG_OBJECT,
                "commit": COMMIT,
                "tree": TREE,
                "archive_url": ARCHIVE_URL,
                "archive": binding(output_root, destinations["archive"]),
                "signing_key": {
                    **binding(output_root, destinations["signing_key"]),
                    "fingerprint": SIGNING_FINGERPRINT,
                },
                "git_object_status": binding(output_root, destinations["git_object_status"]),
                "git_signature_status": binding(output_root, destinations["git_signature_status"]),
            },
            "build": {
                "host": host,
                "patches": [],
                "source_export": binding(output_root, destinations["source_export"]),
                "tree_manifest": binding(output_root, destinations["tree_manifest"]),
                "cmake_argv": configure_argv,
                "build_argv": build_argv,
                "environment": binding(output_root, destinations["environment"]),
                "toolchain_manifest": binding(output_root, destinations["toolchain_manifest"]),
                "dependency_manifest": binding(output_root, destinations["dependency_manifest"]),
                "build_log": binding(output_root, destinations["build_log"]),
            },
            "binary": {
                "artifact": binding(output_root, destinations["artifact"]),
                "format": host["binary_format"],
                "architecture": host["architecture"],
                "version_output": binding(output_root, destinations["version_output"]),
                "dynamic_dependencies": binding(output_root, destinations["dynamic_dependencies"]),
            },
        }
        report_path = output_root / "execution-tool-provenance.json"
        write_exclusive(
            report_path,
            (json.dumps(report, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode("utf-8"),
        )
        print(
            json.dumps(
                {
                    "status": "collected-local-only-candidate",
                    "report": str(report_path),
                    "report_sha256": sha256_file(report_path),
                    "bound_record_count": 13,
                    "deployable": False,
                    "device_writes_performed": False,
                },
                sort_keys=True,
            )
        )
    except Exception:
        # Output was required to be absent at entry.  Preserve partial evidence
        # for diagnosis rather than deleting it or risking a destructive cleanup.
        raise
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CollectionError as exc:
        print(f"collection failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
