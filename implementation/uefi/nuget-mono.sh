#!/usr/bin/env bash
set -euo pipefail

readonly nuget_exe=/opt/t860-tools/nuget.exe
if [[ ! -f "$nuget_exe" ]]; then
    echo "error: pinned NuGet executable missing: $nuget_exe" >&2
    exit 2
fi
exec mono "$nuget_exe" "$@"
