# Offline execution-tool provenance collection

`collect-execution-tool-provenance.py` converts explicit, already-audited local
Heimdall v2.2.2 inputs into the strict provenance schema consumed by
`validate-first-boot.py`. It is a `LOCAL_ONLY` evidence collector, not a build
script, liveness collector, executor, or release generator.

The collector performs no network access, package installation, USB discovery,
ADB action, reboot, PIT download, or partition operation. It never executes the
candidate Heimdall binary; the version record is copied from the fixed v3
bundle and remains evidence about that earlier audited build, not a new run.

## Required explicit inputs

- the exact sanitized v3 public bundle, SHA-256
  `33fecef855fbb956491dacabdbe3340f95256808a713eadd7596df6f00a7777c`;
- the fixed SourceHut archive, signing key, and a clean, full Git repository at
  tag `v2.2.2`;
- separate unmodified native GnuPG `--status-fd` captures for tag and commit,
  plus the original Git object-status record;
- the exact macOS ARM64 candidate binary and its exact Homebrew libusb 1.0.30
  dynamic library.

Each raw GnuPG capture must retain the currently observed expired-key semantics:
exactly one `EXPKEYSIG` terminal record, one matching `VALIDSIG` record bound to
primary fingerprint `2C7F29AE97891F6419A9E2CDB0076E490B71616B`, and at
least one `KEYEXPIRED`. Do not filter, normalize, reorder, synthesize, or copy
status lines into a new file. The collector validates both raw inputs. For the
existing aggregate schema, it concatenates their byte-identical contents with
fixed, non-`[GNUPG:]` boundary lines. `LOCAL_ONLY-input-manifest.json` records
the original absolute paths, sizes, and hashes.

Example (all paths are local and must already exist; the output must not):

```sh
python3 implementation/uefi/collect-execution-tool-provenance.py \
  --public-bundle /LOCAL_ONLY/heimdall-v3-public.tar.gz \
  --source-archive /LOCAL_ONLY/Heimdall-v2.2.2.tar.gz \
  --signing-key /LOCAL_ONLY/2C7F29AE97891F6419A9E2CDB0076E490B71616B.asc \
  --source-git /LOCAL_ONLY/Heimdall.git \
  --git-object-status /LOCAL_ONLY/git-object-status.txt \
  --tag-signature-status /LOCAL_ONLY/tag-gpg-status.raw.txt \
  --commit-signature-status /LOCAL_ONLY/commit-gpg-status.raw.txt \
  --binary /LOCAL_ONLY/heimdall-v2.2.2-macos-arm64 \
  --libusb /opt/homebrew/Cellar/libusb/1.0.30/lib/libusb-1.0.0.dylib \
  --output-root /LOCAL_ONLY/execution-tool-provenance
```

The output has exactly 13 distinct single-link records plus
`execution-tool-provenance.json`. Additional unbound `LOCAL_ONLY-*` entries are
private input snapshots, an empty Git home, and a path/hash manifest; they are
not validator records and must remain local. Each explicit file and the full
standalone Git work tree are copied once through no-follow descriptors into
that newly created private root before validation. All Git processes use the
snapshot, fixed object IDs, an empty home, no system/global config, hooks or
fsmonitor, no replace objects/lazy fetch/transport, and rejected
replace/alternates/promisor/partial-clone repository state. The collector fails
closed for an existing output root, symlink path components, hard-linked inputs
or outputs, object/tree or archive-content mismatch, dirty/shallow Git source,
wrong source/key/binary hashes, wrong Mach-O architecture/load allowlist, or a
binary/libusb dependency mismatch. A failed run is retained as a partial
diagnostic directory; the collector never deletes or reuses it.

Feed the resulting JSON to the aggregate validator with
`--execution-tool-provenance-report`. A structurally valid report still yields
`pending-source-provenance`: the signing-key, binary, and report review digests
remain unset, `EXECUTION_TOOL_PASS_VALIDATION_IMPLEMENTED` remains `False`, no
liveness report is created, and readiness/deployment/authorization remain
false.

## Schema limitation

The current provenance schema has one aggregate `git_object_status` file and
one aggregate `git_signature_status` file. It cannot independently bind tag
and commit argv, exit code, object, and status captures. This collector therefore
checks both fixed objects and the exact two-signature status shape, but it does
not claim separate per-operation provenance. The schema must be versioned and
split into separate tag/commit records before any pass-capable validator can be
considered.
