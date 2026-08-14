#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "$0")" && pwd)"
workspace="$(cd "$script_dir/../.." && pwd)"
uefi_source="$workspace/research/repos/mu_aloha_platforms"
expected_uefi_revision="96add763040d86d21f87a4a4022e094e17e6e3c6"
aml="$workspace/implementation/build/acpi-ufs-offline/DSDT.aml"

profile="ufs-offline"
if [[ $# -eq 2 && "$1" == "--profile" ]]; then
    profile="$2"
elif [[ $# -ne 0 ]]; then
    echo "usage: $0 [--profile ufs-offline|first-boot-diagnostic]" >&2
    exit 2
fi

case "$profile" in
    ufs-offline)
        output_dir="$workspace/implementation/build/uefi"
        preparation="$script_dir/prepare-ufs-offline.py"
        preparation_report="$output_dir/ufs-offline-source-preparation.json"
        artifact_stem="gts6lwifi-ufs-offline"
        ;;
    first-boot-diagnostic)
        output_dir="$workspace/implementation/build/uefi-first-boot-diagnostic"
        preparation="$script_dir/prepare-first-boot-diagnostic.py"
        preparation_report="$output_dir/first-boot-diagnostic-source-preparation.json"
        artifact_stem="gts6lwifi-first-boot-diagnostic"
        ;;
    *)
        echo "error: unsupported profile: $profile" >&2
        exit 2
        ;;
esac

host_os="$(uname -s)"
host_arch="$(uname -m)"
if [[ "$host_os" != "Linux" || "$host_arch" != "x86_64" ]]; then
    echo "error: mu_aloha_platforms requires Linux x86_64; this host is $host_os $host_arch" >&2
    echo "The AML integration preflight is still available via implementation/uefi/validate.py." >&2
    exit 2
fi

python3 - <<'PY'
import sys
if sys.version_info < (3, 12):
    raise SystemExit("error: Python 3.12 or newer is required by mu_aloha_platforms")
PY

for command in git mono nuget clang; do
    if ! command -v "$command" >/dev/null 2>&1; then
        echo "error: required command not found: $command" >&2
        exit 2
    fi
done
if ! python3 -m pip --version >/dev/null 2>&1; then
    echo "error: Python pip module is unavailable" >&2
    exit 2
fi

if ! git -C "$uefi_source" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "error: UEFI source repository missing: $uefi_source" >&2
    exit 2
fi
actual_uefi_revision="$(git -C "$uefi_source" rev-parse HEAD)"
if [[ "$actual_uefi_revision" != "$expected_uefi_revision" ]]; then
    echo "error: UEFI source revision is $actual_uefi_revision" >&2
    echo "expected: $expected_uefi_revision" >&2
    exit 2
fi
if [[ ! -f "$aml" ]]; then
    echo "error: build the safety ACPI artifact first: ./implementation/acpi/build-ufs-offline.sh" >&2
    exit 2
fi

if [[ "$profile" == "first-boot-diagnostic" && -e "$output_dir" ]]; then
    echo "error: refuse existing output directory: $output_dir" >&2
    echo "Use a fresh checkout or move the previous evidence aside before building." >&2
    exit 2
fi
mkdir -p "$output_dir"
worktree="$(mktemp -d "${TMPDIR:-/tmp}/t860-uefi-build.XXXXXX")"
cleanup() {
    if [[ "$worktree" == "${TMPDIR:-/tmp}/t860-uefi-build."* && -d "$worktree" ]]; then
        rm -rf "$worktree"
    fi
}
trap cleanup EXIT

git clone --local --recurse-submodules "$uefi_source" "$worktree/mu_aloha_platforms"
build_root="$worktree/mu_aloha_platforms"
build_venv="$worktree/venv"
target_aml="$build_root/Platforms/SurfaceDuo1Pkg/Device/samsung-gts6lwifi/ACPI/DSDT.aml"
install -m 0644 "$aml" "$target_aml"
python3 "$preparation" "$build_root" --report "$preparation_report"
python3 -m venv "$build_venv"

clang_binary="$(command -v clang)"
clang_binary="$(readlink -f "$clang_binary")"
clang_dir="${CLANGPDB_BIN:-$(dirname "$clang_binary")}"
export CLANGPDB_BIN="${clang_dir%/}/"
export CLANGPDB_AARCH64_PREFIX="${CLANGPDB_AARCH64_PREFIX:-aarch64-linux-gnu-}"
if [[ ! -x "${CLANGPDB_BIN%/}/clang" ]]; then
    echo "error: CLANGPDB_BIN does not contain clang: $CLANGPDB_BIN" >&2
    exit 2
fi
if ! command -v "${CLANGPDB_AARCH64_PREFIX}gcc" >/dev/null 2>&1; then
    echo "error: AArch64 GCC prefix is unavailable: $CLANGPDB_AARCH64_PREFIX" >&2
    exit 2
fi
echo "CLANGPDB_BIN=$CLANGPDB_BIN"
echo "CLANGPDB_AARCH64_PREFIX=$CLANGPDB_AARCH64_PREFIX"

(
    cd "$build_root"
    source "$build_venv/bin/activate"
    chmod +x ./timebuild.sh
    ./timebuild.sh
    python -m pip install --upgrade -r pip-requirements.txt 'uefi_firmware==1.16'
    python ./build_uefi.py --init
    python ./build_uefi.py -d samsung-gts6lwifi
) 2>&1 | tee "$output_dir/build.log"

if [[ "$profile" == "first-boot-diagnostic" ]]; then
    if ! grep -q -- '-DUSE_SCREEN_FOR_SERIAL_OUTPUT=1' "$output_dir/build.log"; then
        echo "error: diagnostic build log does not prove framebuffer serial output" >&2
        exit 1
    fi
    if grep -q -- '-DUSE_SCREEN_FOR_SERIAL_OUTPUT=0' "$output_dir/build.log"; then
        echo "error: diagnostic build log contains a screen-serial-disabled compile" >&2
        exit 1
    fi
fi

firmware="$(find "$build_root/Build/SurfaceDuo1Pkg" -type f -name 'SM8150_EFI.fd' -print -quit)"
boot_image="$build_root/Build/SurfaceDuo1Pkg/samsung-gts6lwifi.img"
if [[ -z "$firmware" || ! -s "$firmware" || ! -s "$boot_image" ]]; then
    echo "error: UEFI build command returned without both expected artifacts" >&2
    exit 1
fi

install -m 0644 "$firmware" "$output_dir/$artifact_stem.fd"
install -m 0644 "$boot_image" "$output_dir/$artifact_stem.img"
"$build_venv/bin/python" "$script_dir/validate.py" \
    --profile "$profile" \
    --firmware "$output_dir/$artifact_stem.fd" \
    --boot-image "$output_dir/$artifact_stem.img"

echo "$profile UEFI artifacts were built and verified offline. They remain non-deployable."
