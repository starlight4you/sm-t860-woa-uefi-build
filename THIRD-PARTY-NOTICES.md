# Third-party provenance and notices

- UEFI sources are referenced as a Git submodule from [Project-Aloha/mu_aloha_platforms](https://github.com/Project-Aloha/mu_aloha_platforms) at commit `96add763040d86d21f87a4a4022e094e17e6e3c6`. The upstream repository identifies its license as BSD-2-Clause and contains additional component-specific notices.
- The future execution-tool provenance gate identifies Heimdall from its current canonical [SourceHut repository](https://git.sr.ht/~grimler/Heimdall), signed tag `v2.2.2` (commit `d9554e7fa30a00abed7f0ac86b10e63c2c3b8e20`). Heimdall is distributed under the MIT License; consult the upstream `LICENSE` file. This repository does not currently redistribute its source, public key, or binary, and identifying a candidate source does not approve it for device execution.
- `implementation/build/acpi/DSDT.aml` is an experimental adaptation derived from device firmware/ACPI work. It is supplied for interoperability research and must not be treated as a vendor firmware release.

No blanket license is asserted over third-party or vendor-derived material. The repository is not a deployable firmware release and carries no warranty.
