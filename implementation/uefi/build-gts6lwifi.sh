#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "$0")" && pwd)"
workspace="$(cd "$script_dir/../.." && pwd)"
uefi_source="$workspace/research/repos/mu_aloha_platforms"
aml="$workspace/implementation/build/acpi-ufs-offline/DSDT.aml"
output_dir="$workspace/implementation/build/uefi"

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

for command in git pip mono clang; do
    if ! command -v "$command" >/dev/null 2>&1; then
        echo "error: required command not found: $command" >&2
        exit 2
    fi
done

if [[ ! -d "$uefi_source/.git" ]]; then
    echo "error: UEFI source repository missing: $uefi_source" >&2
    exit 2
fi
if [[ ! -f "$aml" ]]; then
    echo "error: build the safety ACPI artifact first: ./implementation/acpi/build-ufs-offline.sh" >&2
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
target_aml="$build_root/Platforms/SurfaceDuo1Pkg/Device/samsung-gts6lwifi/ACPI/DSDT.aml"
install -m 0644 "$aml" "$target_aml"
python3 "$script_dir/prepare-ufs-offline.py" "$build_root" \
    --report "$output_dir/ufs-offline-source-preparation.json"

(
    cd "$build_root"
    ./build_setup.sh
    python3 -m pip install --upgrade -r pip-requirements.txt 'uefi_firmware==1.16'
    ./build_uefi.py --init
    ./build_uefi.py -d samsung-gts6lwifi
) 2>&1 | tee "$output_dir/build.log"

firmware="$(find "$build_root/Build/SurfaceDuo1Pkg" -type f -name 'SM8150_EFI.fd' -print -quit)"
boot_image="$build_root/Build/SurfaceDuo1Pkg/samsung-gts6lwifi.img"
if [[ -z "$firmware" || ! -s "$firmware" || ! -s "$boot_image" ]]; then
    echo "error: UEFI build command returned without both expected artifacts" >&2
    exit 1
fi

install -m 0644 "$firmware" "$output_dir/gts6lwifi-ufs-offline.fd"
install -m 0644 "$boot_image" "$output_dir/gts6lwifi-ufs-offline.img"
python3 "$script_dir/validate.py" \
    --profile ufs-offline \
    --firmware "$output_dir/gts6lwifi-ufs-offline.fd" \
    --boot-image "$output_dir/gts6lwifi-ufs-offline.img"

echo "UFS-offline UEFI artifacts were built and verified offline. They remain non-deployable."
