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
python3 implementation/uefi/validate.py --profile ufs-offline
chmod +x implementation/uefi/build-gts6lwifi.sh
./implementation/uefi/build-gts6lwifi.sh
```

注意确认当前 LLVM 路径。构建脚本会创建临时 Python venv，并在运行 `build_uefi.py` 前显式导出 `CLANGPDB_BIN` 和 `CLANGPDB_AARCH64_PREFIX=aarch64-linux-gnu-`。它不会调用带有 `sudo apt` 和浮动 NuGet 下载的上游 `build_setup.sh`；宿主依赖必须按“环境”一节预先安装。

预期输出：

- `implementation/build/uefi/gts6lwifi-ufs-offline.fd`
- `implementation/build/uefi/gts6lwifi-ufs-offline.img`
- `implementation/build/uefi/build.log`
- `implementation/build/uefi/ufs-offline-validation.json`
- `implementation/build/uefi/ufs-offline-source-preparation.json`

构建脚本会把 UFS-offline AML 注入临时上游树，在 `APRIORI.inc`、`DXE.inc`、`DXE.dsc.inc` 中剔除有效 `UFSDxe` 引用，同时保留 `SdccDxe`。为了让安全输入可独立按原始字节核验，临时树还会把 ACPI freeform 文件从 LZMA 内层 `FVMAIN` 移到未压缩的外层 `FVMAIN_COMPACT`，并以设备级 `bootpack.json` 关闭 boot payload gzip；这两个改动只作用于 T860 的临时构建树，不改固定 submodule。

构建后固定安装 `uefi_firmware==1.16`，递归解析压缩 FV；二进制中不得存在 `UFSDxe` GUID/名称，必须存在 `SdccDxe`。验证状态应为 `pass-ufs-offline-uefi-build`，并确认 `.fd` 和 `.img` 都精确包含该 AML，boot image 精确包含一次 `.fd`。所有产物仍是 `deployable: false`。

提交 `cbe1074` 中的 `dist-gts6lwifi-ufs-offline/` 是首个通过上述静态门槛的参考产物。它仍然只用于离线分析，不是可刷写发布包。

`implementation/build/acpi-ufs-offline/validation.json` 记录 UFS0/UFS1 `_STA=0`、SDC2 `_STA=15`。这仅建立离线隔离证据，不代表镜像已经可启动或允许刷写。

进一步的 microSD/USB 候选启动链、Windows `ACPI\QCOM2466` 跨设备驱动证据、恢复门槛和可重复检查命令见 [FIRST-BOOT-READINESS.md](FIRST-BOOT-READINESS.md)。`implementation/uefi/validate-first-boot.py` 会直接绑定最终 `.fd/.img/AML`、三份本地报告、关键模块名称/GUID 和固定 UEFI gitlink/HEAD；外部 Windows、原厂恢复、传输与精确动作计划按严格 schema 聚合，不能只凭 `status` 字符串通过。它不会操作设备，也不会生成传输或动作计划。本地报告属于可复核但可改写的自证材料，不是执行授权；而且当前尚无经验证的精确 Recovery 首启触发方式，因此聚合器硬性保持 `execution_prerequisites_ready: false`。静态通过只记为 `offline_firmware_composition_pass`：当前 header v0/4096/empty-ramdisk 容器与已测 gts6l 上游 packer 一致，同机 unlocked ABL 也有允许无 Samsung/AVB 尾部 TWRP recovery 的历史证据；但当前精确镜像从未实机测试，仍然不是可刷写发布物。所有输出始终保持 `deployable: false` 和未授权状态。

## 安全边界

本仓库只授权离线构建和检查。严禁 `dd`、fastboot、ADB、Odin、Heimdall、写磁盘分区、刷写 boot/recovery/UFS 或重启 T860。

新 Codex 会话可直接使用 [NEW-SESSION-PROMPT.md](NEW-SESSION-PROMPT.md)。第三方来源见 [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md)。
