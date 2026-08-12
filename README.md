# SM-T860 WoA UEFI offline build

这是 Samsung Galaxy Tab S6 Wi-Fi（SM-T860）WoA 实验的 Linux x86_64 UEFI 离线构建仓库。仓库固定引用 Project-Aloha `mu_aloha_platforms`，并提供专用于可恢复启动研究的 UFS-offline DSDT、注入/构建脚本和二进制验证器。

## 克隆

本仓库使用 Git submodule。首次使用：

```bash
git clone https://github.com/starlight4you/sm-t860-woa-uefi-build.git
cd sm-t860-woa-uefi-build
git submodule update --init research/repos/mu_aloha_platforms
```

固定的 UEFI commit 是 `96add763040d86d21f87a4a4022e094e17e6e3c6`。不要 `git pull` 或更新 submodule 指针来绕过构建问题。

## 环境

推荐 Ubuntu 24.04 x86_64、Python 3.12+、SSD、30 GiB 可用空间和可访问 GitHub/PyPI/NuGet 的网络。还需 Git、Mono/NuGet、build-essential、clang/LLVM/lld、AArch64 GCC、uuid-dev、iasl、nasm、gettext、curl 和 CA certificates。

## 构建

```bash
python3 implementation/uefi/validate.py
chmod +x implementation/uefi/build-gts6lwifi.sh
./implementation/uefi/build-gts6lwifi.sh
```

注意确认当前 LLVM 路径，并让 `CLANGPDB_BIN` 和 `CLANGPDB_AARCH64_PREFIX=aarch64-linux-gnu-` 在真正运行 `build_uefi.py` 的环境中生效。上游 `build_setup.sh` 面向 Ubuntu 24.04，但其中的 `export` 不会传回调用它的父 shell。

预期输出：

- `implementation/build/uefi/gts6lwifi-ufs-offline.fd`
- `implementation/build/uefi/gts6lwifi-ufs-offline.img`
- `implementation/build/uefi/build.log`
- `implementation/build/uefi/ufs-offline-validation.json`
- `implementation/build/uefi/ufs-offline-source-preparation.json`

构建脚本会把 UFS-offline AML 注入临时上游树，在 `APRIORI.inc`、`DXE.inc`、`DXE.dsc.inc` 中剔除有效 `UFSDxe` 引用，同时保留 `SdccDxe`。构建后固定安装 `uefi_firmware==1.16`，递归解析压缩 FV；二进制中不得存在 `UFSDxe` GUID/名称，必须存在 `SdccDxe`。验证状态应为 `pass-ufs-offline-uefi-build`，并确认 `.fd` 和 `.img` 都精确包含该 AML，boot image 精确包含一次 `.fd`。所有产物仍是 `deployable: false`。

`implementation/build/acpi-ufs-offline/validation.json` 记录 UFS0/UFS1 `_STA=0`、SDC2 `_STA=15`。这仅建立离线隔离证据，不代表镜像已经可启动或允许刷写。

## 安全边界

本仓库只授权离线构建和检查。严禁 `dd`、fastboot、ADB、Odin、Heimdall、写磁盘分区、刷写 boot/recovery/UFS 或重启 T860。

新 Codex 会话可直接使用 [NEW-SESSION-PROMPT.md](NEW-SESSION-PROMPT.md)。第三方来源见 [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md)。
