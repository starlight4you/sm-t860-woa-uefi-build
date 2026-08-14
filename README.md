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

2026-08-14 的首次真机测试已经证明原 UFS-offline 镜像会在首屏后复位到
Download mode；随后仅恢复 DWH1 RECOVERY，Android 已正常启动。该失败镜像不得
原样重刷，精确结果见 [FIRST-BOOT-FAILURE-2026-08-14.md](FIRST-BOOT-FAILURE-2026-08-14.md)。

修复后的诊断构建使用独立输出目录：

```bash
./implementation/uefi/build-gts6lwifi.sh --profile first-boot-diagnostic
```

它恢复上游压缩 FV/gzip boot payload 布局，同步关闭 UFSDxe、UFS IOC 和 UFS
SMMU 初始化，保留 SdccDxe，打开 framebuffer DEBUG，并仅在诊断版中移除
Qualcomm/UEFI 两层 watchdog。预期输出位于
`implementation/build/uefi-first-boot-diagnostic/`，仍为 `deployable: false`；
若固件卡住，因 watchdog 已关闭，可能需要长按按键强制重启。本机构建环境
不符合 Linux x86_64 门禁时，可从 GitHub Actions 手动运行
`Build SM-T860 first-boot diagnostic`；工作流只保留三天的 non-deployable
诊断证据，不创建 Release。

该诊断镜像已于 2026-08-15 在单独授权下完成一次 RECOVERY-only 真机测试：
它短暂显示 `UEFI Firmware` 后黑屏并反复复位。随后已经再次恢复固定 DWH1
RECOVERY。该结果否定了“镜像仅因两层 watchdog 超时而跳回 Download”的假设，
也证明当前 2026 `main` 构建不能继续作为首启候选。下一步是先对照测试官方
Project Aloha `2412.74` 的原始 `samsung-gts6lwifi_NOSB.img`，以区分上游端口
本身的兼容问题和 2412.74 之后的源码/组件回归；精确哈希与门禁记录在
[FIRST-BOOT-FAILURE-2026-08-14.md](FIRST-BOOT-FAILURE-2026-08-14.md)。

注意确认当前 LLVM 路径。构建脚本会创建临时 Python venv，并在运行 `build_uefi.py` 前显式导出 `CLANGPDB_BIN` 和 `CLANGPDB_AARCH64_PREFIX=aarch64-linux-gnu-`。它不会调用带有 `sudo apt` 和浮动 NuGet 下载的上游 `build_setup.sh`；宿主依赖必须按“环境”一节预先安装。

预期输出：

- `implementation/build/uefi/gts6lwifi-ufs-offline.fd`
- `implementation/build/uefi/gts6lwifi-ufs-offline.img`
- `implementation/build/uefi/build.log`
- `implementation/build/uefi/ufs-offline-validation.json`
- `implementation/build/uefi/ufs-offline-source-preparation.json`

构建脚本会把 UFS-offline AML 注入临时上游树，在 `APRIORI.inc`、`DXE.inc`、`DXE.dsc.inc` 中剔除有效 `UFSDxe` 引用，同时保留 `SdccDxe`。为了让安全输入可独立按原始字节核验，临时树还会把 ACPI freeform 文件从 LZMA 内层 `FVMAIN` 移到未压缩的外层 `FVMAIN_COMPACT`，并以设备级 `bootpack.json` 关闭 boot payload gzip；这两个改动只作用于 T860 的临时构建树，不改固定 submodule。

构建后固定安装 `uefi_firmware==1.16`，递归解析压缩 FV；二进制中不得存在 `UFSDxe` GUID/名称，必须存在 `SdccDxe`。验证状态应为 `pass-ufs-offline-uefi-build`，并确认 `.fd` 和 `.img` 都精确包含该 AML，boot image 精确包含一次 `.fd`。所有产物仍是 `deployable: false`。

提交 `cbe1074` 中的 `dist-gts6lwifi-ufs-offline/` 是首个通过上述静态门槛的参考产物。它已经在真机首屏后失败并完成原厂 RECOVERY 回滚，只能作为失败证据，不是可刷写发布包。

`implementation/build/acpi-ufs-offline/validation.json` 记录 UFS0/UFS1 `_STA=0`、SDC2 `_STA=15`。这仅建立离线隔离证据，不代表镜像已经可启动或允许刷写。

进一步的 microSD/USB 候选启动链、Windows `ACPI\QCOM2466` 跨设备驱动证据、恢复门槛和可重复检查命令见 [FIRST-BOOT-READINESS.md](FIRST-BOOT-READINESS.md)；Recovery 人工按键路径的历史证据与未来现场门禁见 [RECOVERY-TRIGGER-DRILL.md](RECOVERY-TRIGGER-DRILL.md)。`implementation/uefi/validate-first-boot.py` 会直接绑定最终 `.fd/.img/AML`、三份本地报告、关键模块名称/GUID 和固定 UEFI gitlink/HEAD；外部 Windows、原厂恢复、历史传输、未来 execution tool、Recovery 触发与精确动作计划按严格 schema 聚合。所有 JSON 全局拒绝重复键；新的 execution provenance/liveness schema 还会逐层拒绝未知键，不能只凭 `status` 或自报布尔值通过。它不会操作设备，也不会生成现场报告或动作计划。

历史 transport schema 2 与来源不明的 Heimdall 2.0.2 证据原样保留，只能证明历史能力，永远不会成为未来动作计划的 binary。未来 execution tool 固定到 SourceHut Heimdall `v2.2.2` 的 tag object、commit、tree、archive SHA-256 和签名 key fingerprint；但当前公钥文件、最终宿主 binary、provenance report 和 liveness report 的预期 SHA-256 都故意未固定，且 pass 验证实现还有独立的 `False` 硬阻断。因而缺报告为 `pending`，结构正确的 Linux x86_64 或 macOS ARM64 离线构建也只会是候选；不得通过机械填哈希解除阻断。后续必须先补齐真实二进制/依赖解析、签名验证、源码到产物绑定、固定 collector/watchdog 和无 TOCTOU 的 executor，再在最终执行宿主上对完全相同 binary SHA-256 另行授权只读 `download-pit` liveness。当前聚合器硬性保持 `execution_prerequisites_ready: false`。静态通过只记为 `offline_firmware_composition_pass`：当前 header v0/4096/empty-ramdisk 容器与已测 gts6l 上游 packer 一致，同机 unlocked ABL 也有允许无 Samsung/AVB 尾部 TWRP recovery 的历史证据；当前精确诊断镜像已经实机失败并完成 stock RECOVERY 回滚，仍然不是可刷写发布物。所有输出始终保持 `deployable: false` 和未授权状态。

[`implementation/uefi/collect-execution-tool-provenance.py`](implementation/uefi/collect-execution-tool-provenance.py) 可将明确提供的本地 v3 构建包、固定源码/Git/GnuPG 原始状态、binary 与 libusb 整理为 13 个独立绑定文件；详细输入和安全边界见 [`COLLECT-EXECUTION-TOOL-PROVENANCE.md`](implementation/uefi/COLLECT-EXECUTION-TOOL-PROVENANCE.md)。它完全离线且绝不运行 Heimdall，不会产生 liveness 或 pass；现有 schema 对 tag/commit 仍只有聚合状态槽，此限制也被明确保留。

经用户对该次动作单独授权，2026-08-13 的当前会话只读 Download Mode/PIT 演练已通过；设备随后正常返回 Android。现场 PIT 的脱敏摘要、规范化日志和比较结果见 [`evidence/download-mode-readonly-20260813/`](evidence/download-mode-readonly-20260813/)。该结果只关闭 transport liveness 缺口，不解除 Windows 介质、Recovery 首启触发或明确写入授权门槛。

## 安全边界

本仓库只授权离线构建和检查。严禁 `dd`、fastboot、ADB、Odin、Heimdall、写磁盘分区、刷写 boot/recovery/UFS 或重启 T860。

上面的 2026-08-13 演练是用户针对一次明确、只读动作给出的单独授权记录，不扩大本仓库的常规权限，也不授权后续设备操作。

新 Codex 会话可直接使用 [NEW-SESSION-PROMPT.md](NEW-SESSION-PROMPT.md)。第三方来源见 [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md)。
