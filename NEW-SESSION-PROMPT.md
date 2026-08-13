# 新会话提示词

把下面内容粘贴到位于本仓库根目录的新 Codex 会话：

```text
你现在位于 Linux x86_64 UEFI 专用构建机上的 sm-t860-woa-uefi-build 仓库根目录。阅读 README.md、implementation/EXECUTION-2026-08-12.md、THIRD-PARTY-NOTICES.md、implementation/uefi/build-gts6lwifi.sh 和 implementation/uefi/validate.py，然后直接开始执行，不要只给操作建议。

目标：仅完成 samsung-gts6lwifi 的 UFS-offline 离线 UEFI 构建与可复现验证。先初始化固定的 research/repos/mu_aloha_platforms submodule；把 implementation/build/acpi-ufs-offline/DSDT.aml 注入其临时工作树；让脚本移除 APRIORI.inc、DXE.inc、DXE.dsc.inc 中三处有效 UFSDxe 引用并保留 SdccDxe；把 ACPI freeform 文件从 LZMA 内层 FVMAIN 移到未压缩的外层 FVMAIN_COMPACT；通过设备级 bootpack.json 设置 kernel_compressed=false；构建 SM8150_EFI.fd 和 samsung-gts6lwifi.img；归档为 implementation/build/uefi/gts6lwifi-ufs-offline.fd 与 gts6lwifi-ufs-offline.img。最终状态必须是 pass-ufs-offline-uefi-build，同时 deployable 保持 false。

先做只读检查：记录发行版、uname、CPU 架构、Python、Git、Mono、clang/LLVM、AArch64 GCC 和磁盘空间；用 sha256sum -c INPUTS.sha256 核对输入；运行 git submodule update --init research/repos/mu_aloha_platforms；确认 submodule HEAD 为 96add763040d86d21f87a4a4022e094e17e6e3c6；先运行 python3 implementation/uefi/validate.py --profile ufs-offline。不要 git pull、rebase 或改变 submodule 指针；允许按上游锁定 revision 初始化其内部 submodule 和下载编译依赖。

如果缺依赖，识别发行版后安装所需构建包。特别检查实际 LLVM/clang 目录；正式脚本会在真正执行 build_uefi.py 的环境中设置 CLANGPDB_BIN 和 CLANGPDB_AARCH64_PREFIX=aarch64-linux-gnu-，并验证 clang 与 AArch64 GCC 存在。正式脚本不调用带 sudo apt 和浮动 NuGet 下载的上游 build_setup.sh。

执行：
  chmod +x implementation/uefi/build-gts6lwifi.sh
  ./implementation/uefi/build-gts6lwifi.sh
若失败，继续定位依赖、submodule、工具链、脚本或上游目标问题，进行最小修复并重试；不要更新到未锁定上游版本来掩盖问题。记录任何修改的原因和 diff。

完成标准：脚本成功退出；gts6lwifi-ufs-offline.fd 和 gts6lwifi-ufs-offline.img 均存在且非空；ufs-offline-validation.json 状态为 pass-ufs-offline-uefi-build；firmware 与 boot_image 的 embedded_aml_occurrences 都 >= 1；boot image 的 embedded_exact_firmware_occurrences 为 1；firmware_driver_inventory 必须显示 uefi_firmware 1.16、ufs_driver_present=false、sdcc_driver_present=true。最后报告工具版本、产物绝对路径/大小/SHA-256、submodule revision、重要警告、修改文件和剩余阻塞项。不要把“离线构建成功”表述为“已经可启动或可刷写”。

严格禁止：dd、mount/写入真实磁盘分区、ADB、fastboot、Odin、Heimdall、刷写 boot/recovery/UFS、重启 T860 或改动任何连接设备。即使检测到 T860，也不要访问或更改它。
```
