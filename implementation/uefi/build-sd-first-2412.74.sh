#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "$0")" && pwd)"
workspace="$(cd "$script_dir/../.." && pwd)"
output_dir="$workspace/implementation/build/uefi-sdcc-vreg-event-2412.74"
preparation="$script_dir/prepare-sd-first-2412.74.py"

source_url="https://github.com/Project-Aloha/mu_aloha_platforms.git"
source_commit="994c2a064372aa56213f8ad79bda02d8b8e81c75"
mu_plus_commit="2521ce72f8d630b63337daf0482faee234b15e43"

if [[ "$(uname -s)" != "Linux" || "$(uname -m)" != "x86_64" ]]; then
    echo "error: this build requires Linux x86_64" >&2
    exit 2
fi
for command in git mono clang sha256sum; do
    command -v "$command" >/dev/null 2>&1 || { echo "error: missing $command" >&2; exit 2; }
done
python3 - <<'PY'
import sys
if sys.version_info < (3, 10):
    raise SystemExit("error: Python 3.10 or newer is required")
PY

if [[ -e "$output_dir" ]]; then
    echo "error: refuse existing output directory: $output_dir" >&2
    exit 2
fi
mkdir -p "$output_dir"

worktree="$(mktemp -d "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/t860-sd-first.XXXXXX")"
cleanup() {
    if [[ "$worktree" == "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/t860-sd-first."* && -d "$worktree" ]]; then
        rm -rf "$worktree"
    fi
}
trap cleanup EXIT

build_root="$worktree/mu_aloha_platforms"
git clone --filter=blob:none --no-checkout "$source_url" "$build_root"
git -C "$build_root" fetch --force origin "$source_commit"
git -C "$build_root" checkout --detach "$source_commit"
test "$(git -C "$build_root" rev-parse HEAD)" = "$source_commit"
git -C "$build_root" submodule sync --recursive
git -C "$build_root" submodule update --init --recursive --jobs 8
test "$(git -C "$build_root/Common/MU" rev-parse HEAD)" = "$mu_plus_commit"
python3 "$preparation" "$build_root" --report "$output_dir/source-preparation.json"

build_venv="$worktree/venv"
python3 -m venv "$build_venv"
clang_binary="$(readlink -f "$(command -v clang)")"
export CLANGPDB_BIN="${CLANGPDB_BIN:-$(dirname "$clang_binary")/}"
export CLANGPDB_AARCH64_PREFIX="${CLANGPDB_AARCH64_PREFIX:-aarch64-linux-gnu-}"
command -v "${CLANGPDB_AARCH64_PREFIX}gcc" >/dev/null 2>&1 || {
    echo "error: missing ${CLANGPDB_AARCH64_PREFIX}gcc" >&2
    exit 2
}

(
    cd "$build_root"
    source "$build_venv/bin/activate"
    python -m pip install --upgrade \
        'setuptools==70.3.0' 'uefi_firmware==1.16' \
        -r pip-requirements.txt
    python ./build_uefi.py -d samsung-gts6lwifi
) 2>&1 | tee "$output_dir/build.log"

firmware="$(find "$build_root/Build/SurfaceDuo1Pkg" -type f -name 'SM8150_EFI.fd' -print -quit)"
boot_image="$build_root/Build/SurfaceDuo1Pkg/samsung-gts6lwifi.img"
if [[ -z "$firmware" || ! -s "$firmware" || ! -s "$boot_image" ]]; then
    echo "error: build returned without expected FD and Android boot image" >&2
    exit 1
fi

install -m 0644 "$firmware" "$output_dir/gts6lwifi-2412.74-sdcc-vreg-event.fd"
install -m 0644 "$boot_image" "$output_dir/gts6lwifi-2412.74-sdcc-vreg-event.img"
(
    cd "$output_dir"
    sha256sum build.log gts6lwifi-2412.74-sdcc-vreg-event.fd gts6lwifi-2412.74-sdcc-vreg-event.img > SHA256SUMS.txt
    sha256sum -c SHA256SUMS.txt
)

cat >"$output_dir/PROVENANCE.txt" <<EOF
source_url=$source_url
source_commit=$source_commit
mu_plus_commit=$mu_plus_commit
preparation_sha256=$(sha256sum "$preparation" | cut -d' ' -f1)
purpose=enable the already-2960mV PMIC_C/PM8150L LDO9 and LDO6 rails without reprogramming voltage, retain the native T860 SdccDxe, signal Qualcomm external-SD event group b7972c36-8a4c-4a56-8b02-1159b52d4bfb, report register/storage state, and boot only a root startup.nsh volume; never fall back to internal UFS
native_sdcc_sha256=7a8104ad2d939fc61247421211f4e408b61301b3c726239119de56e86e137f8e
comparison_mtp_sdcc_sha256=3a47429a719b4aae1eee72fee1c352c54b50237e7de14e834efb8981dbd16e64
direct_diagnostic_mmio_scope=read-only: 0x03960000/4, 0x00114004/8/c/10, 0x08804024/28/2c/30/40/44/fe
runtime_effect=diagnostic explicitly enables the two T860 SD rails, then the event invokes native SdccDxe, which may change SDCC/GCC/TLMM state and read removable media; no filesystem or partition writes are requested
scope=RECOVERY-only diagnostic; non-deployable
EOF
echo "built T860 SD-rail plus SdccDxe event 2412.74 diagnostic; non-deployable"
