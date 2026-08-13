# SM-T860 可恢复首启门禁

更新日期：2026-08-13。本页只记录离线固件组合证据与继续实验前的门槛；它不是刷写教程，不证明精确镜像已能在实机启动，也不授权重启或写入设备。

## 当前结论

最终 UFS-offline 产物形成了值得继续验证的 microSD 候选启动路径，但还没有达到实机执行条件：

- `.fd` 的递归 FV 清单同时按 UI 名称和 FFS GUID 确认 `BdsDxe`、`MsBootPolicy`、`SdccDxe`、`DiskIoDxe`、`PartitionDxe`、`Fat`；`QcomBds` 和 `UFSDxe` 的名称与 GUID 均不存在。
- 固件还包含 `XhciDxe`、`UsbBusDxe`、`UsbMassStorageDxe`。这只证明 USB 存储组件已编入，不证明 T860 的 USB PHY、供电或实机枚举已工作。
- 父仓库 gitlink 和 submodule HEAD 都固定在 `96add763040d86d21f87a4a4022e094e17e6e3c6`。该版本注册 `SDD` 后注册 `USB`，正常启动序列是 HDD 后 USB，并取消了拒绝 SD 设备路径的逻辑。
- 最终 AML 在 `.fd` 和 Android boot `.img` 中各精确出现一次；完整 `.fd` 在 `.img` 中也精确出现一次。UFS0/UFS1 `_STA=0`，SDC2 `_STA=15`，SDC2 的硬件 ID 是 `ACPI\QCOM2466`。这是 UFS 离线的静态证据，不是运行时证明。
- 同类 Qualcomm Samsung ARM64 资料把 `ACPI\QCOM2466` 映射到 Microsoft `sdbus.inf/sdbus.sys` 的 `SDHostQualcomm8974Std`，并有 `sdbus/sdstor BootFlags=0x8` 样本。这是跨设备参考，不替代目标 Windows ARM64 介质审计或 T860 运行时验证。

Android boot 容器的结论需要准确降调。DWH1 原厂 `boot.img/recovery.img` 是 header v1、4096-byte page，并各含一份 Samsung signer、AVB vbmeta 与分区末 footer；当前 `gts6lwifi-ufs-offline.img` 是 header v0、4096-byte page、6-byte empty ramdisk，不含上述尾部。但这不构成一个已证实的“鉴权硬失败”：

- Project-Aloha 在 gts6l Windows/SD 实机支持时的 commit `9ff4c1f9202b19ef53e68214f25c58718dc6d1f2` 明确使用 header v0、4096-byte page、empty ramdisk和 UEFI+DTB payload。当前固定 builder 沿用该容器路线；本构建仅在临时工作树关闭 payload gzip，以便独立核验 FD/AML 原始字节。
- 同一台 SM-T860 历史上启动过 TWRP header v1 镜像；该镜像不含 Samsung signer、`AVB0`或分区末 `AVBf`。ABL 日志在 unlocked/orange 路径明确记录 `AUTHENTICATE fail but allow Recovery binary: recovery`，随后进入 ExitBootServices。

因此静态结论是 `boot_image_container_static_support: true`，而不是“当前精确镜像已能通过实机鉴权”。只有当严格 transport 报告绑定本地 TWRP 和 bootloader 日志时，聚合结果才记录 `authentication_path_historically_supported_on_unlocked_device: true`；`exact_current_image_hardware_tested` 始终是 `false`。当前 `.img` 仍然不是可刷写发布物。

## 继续研究的价值与 UFS 硬边界

Project-Aloha PR #239 作者报告 SM-T860 的 SD card 和 touch 在 Windows 中工作，但同一评论警告：Windows 自动修复把除 SDA 外未修复 GPT 的其他 UFS LUN 全部联机后损坏了设备。后续 T860 专属 commit `b36a8226` 的提交信息还记录，测试中关闭 MLVM 后 Windows 仍能启动。这两条上游证据同时支持两个结论：microSD 路线值得继续，UFS0/UFS1 离线则是不可弱化的安全边界。它们不证明本仓库的精确产物可启动。

PR #746 移除的是 LTE `samsung-gts6l`，其说明明确 Wi-Fi `samsung-gts6lwifi` 不受影响；这不改变本项目的目标。

## 可重复门禁

Linux 主机安装固定解析器并运行：

```bash
python3 -m venv .venv-first-boot
. .venv-first-boot/bin/activate
python3 -m pip install uefi_firmware==1.16
python3 implementation/uefi/validate-first-boot.py
```

默认输出 `implementation/build/uefi/first-boot-readiness.json`。当前预期为：

- `status: offline_firmware_composition_pass`
- `offline_firmware_composition_pass: true`
- `boot_image_container_static_support: true`
- `authentication_path_historically_supported_on_unlocked_device: false`（默认未提供历史证据报告，不是反证）
- `exact_current_image_hardware_tested: false`
- `recovery_boot_trigger_validated: false`
- `execution_status: blocked-first-boot-execution`
- Windows 介质、原厂恢复、当前会话历史工具恢复传输、新 execution tool、Recovery 触发和精确动作计划六项为 `pending`
- `external_evidence_trust: local-self-attested-not-execution-authority`
- `deployable: false`
- `explicit_device_write_authorization_recorded: false`

缺失外部证据是安全的 `pending`，退出码为 0，表示离线组合复核成功；它不表示可执行。任一静态检查失败，或任一已提供的外部报告不满足严格 schema 时，退出码为 1。

聚合器直接读取并相互绑定：

- 最终 `.fd/.img/AML` 与 source-preparation、UEFI、ACPI 三份报告的固定大小和 SHA-256；
- `ANDROID!` 头、header/page/ramdisk 字段、完整 FD 与 AML 精确嵌入次数；
- 最终固件的关键名称/GUID 对、固定 UEFI gitlink/HEAD、固定上游/pinned PostBuild 源码哈希与启动策略源码；
- Windows schema 2 报告的固定 validator SHA-256 和完整 18 项检查集，包括目标整盘不得是 host boot/system 的 `media.target_disk_safety`、NTFS/ESP 卷盘符与顶层根路径及 BCD 的交叉绑定、三份 EFI 一致性哈希与对应 ARM64 PE 检查的交叉绑定；
- DWH1 原厂 ZIP、四个 tar.md5 成员和本地五个 critical 文件，并直接记录原厂 boot/recovery 容器结构；
- 同机历史 transport 的 Heimdall 二进制、PIT/上传日志、后续 Android 启动、TWRP readback、TWRP 镜像结构与 ABL 解锁日志；
- 当前会话的只读 Download Mode 日志。这一项与历史证据分层，不会被历史成功自动放行。
- 未来 execution tool 的独立 provenance/liveness：provenance 只接收可复算的源码、签名原始输出、构建和二进制事实；liveness 必须由最终宿主用完全相同的 binary SHA-256 重新采集。两者都不复用 Heimdall 2.0.2 历史演练。

这些本地 JSON、日志与文件哈希用于发现过期产物、错盘、错架构和不完整检查，属于可复核但可由本机管理员改写的自证材料，不是可信执行证明、签名证明或授权载体。聚合器因此不会仅凭这些材料把本项目提升为可执行状态。

`--execution-tool-provenance-report` 和 `--execution-tool-liveness-report` 当前只是严格 collector schema；本仓库没有会操作 USB 的 collector，也没有自动安装依赖或运行 Heimdall 的 builder。离线构建器若后续加入，只能导出源码、构建并采集原始事实，不能产生 pass。实际 executor 还必须避免 pathname 校验后替换的 TOCTOU：应以已打开的只读文件描述符或受控不可变 staging 运行刚复核的 binary，并清理 `LD_*`/`DYLD_*` 等动态加载注入变量；validator 本身不会执行它。

## 实机执行前的全部门槛

### 2026-08-13 当前会话只读演练

用户单独授权进入 Download Mode 后，本机已完成一次严格限制的只读
`download-pit --no-reboot --stdout-errors` 演练。主机只在唯一 Samsung
`04e8:685d` 枚举出现后运行固定 Heimdall；命令 exit 0，现场 PIT 解析为
`COM_TAR2`、`SM8150`、4 LUN、76 项，且 76 项全部字段与 DWH1 原厂 PIT
一致。原厂 PIT 的完整 10,572 字节（含末尾 512 字节 Samsung trailer）是
现场文件的精确前缀；多出的 5,812 字节全为零填充。独立
`close-pc-screen --resume` 成功请求默认
重启，约一分钟后同一设备返回 ADB，`sys.boot_completed=1`。全程没有执行
上传、flash、PIT 写入或重分区。

脱敏证据见
[`evidence/download-mode-readonly-20260813/`](evidence/download-mode-readonly-20260813/)。
严格 transport gate 现可记为 `pass-recovery-transport-drill`；但本地报告仍
属于自证材料，Windows 介质门禁仍未提供，而且精确 Recovery 首启触发仍
未建立。因此 `recovery_boot_trigger_validated=false`、
`execution_prerequisites_ready=false` 和 `deployable=false` 均不改变。

1. 在 Windows 主机用固定 `validate-windows-media.ps1` 只读检查实际 Windows 分区和 ESP。报告必须证明两分区位于同一 GPT 可移除物理盘，整盘及其任一分区都不是 host boot/system；且 ARM64 PE、三份 EFI 哈希一致性、QCOM2466 映射、同一 sdbus manifest 中的 descriptor/BootFlags、sdstor BootFlags 和绑定实际盘符的 BCD 语义都通过。
2. 用 `--stock-recovery-report` 提供 DWH1 本地报告。聚合器重新散列 6.7 GB ZIP 和 `boot.img`、`recovery.img`、`dtbo.img`、`vbmeta.img`、PIT。PIT 只用于分区映射与容量核对，不得刷写或重分区。
3. 只有单独获得“进入 Download Mode/重启”授权后，才可运行当前会话的只识别、不刷写 drill。未运行时 `current_session.state` 必须是 `not-run`，`flash_attempted` 和 `device_writes_performed` 必须是 `null`，总门禁保持 `pending-current-session-read-only-download-mode-drill`。完成态必须把 `command_argv` 精确绑定到固定 Heimdall 二进制、`download-pit`、唯一输出路径和只读参数；同时绑定当次日志与独立 inode 的 `current-session.pit`，重算 SHA-256，验证 `COM_TAR2`/`SM8150`/76 项结构与固定原厂 PIT 分区布局一致，且日志无上传/flash/重分区标记，才可进入 `pass-recovery-transport-drill`。
4. 前三项通过后，仍需先建立并单独复核“从 `EndSession(false)` 后的 Download Mode 让这台单槽设备可靠进入 `RECOVERY`”的精确触发方式。`heimdall close-pc-screen --resume` 只保证退出 PC screen/重启，不能证明进入 Recovery；手写 reviewer、时间或命令字符串也不能补足这个缺口。当前独立 `recovery_boot_trigger` 门禁没有任何已固定的可接受报告 SHA-256，缺失为 `pending`、任意自填报告为 `fail`，不存在可以直接翻转的布尔开关。候选按键状态机和未来无主机分区写入演练边界见 [RECOVERY-TRIGGER-DRILL.md](RECOVERY-TRIGGER-DRILL.md)。未来若有实机证据，必须通过新的代码审查固定报告哈希，再绑定四份外部报告、`.img/.fd/AML` 哈希、唯一目标分区 `RECOVERY`、原厂 `recovery.img` 回退镜像和机器可读停止条件。
5. 当前历史 Heimdall 2.0.2 二进制来源不可追溯，只能用于已有 schema 2 证据和只读研究；动作计划不再读取该 gate 的工具路径。新的 `execution_tool` 外部门禁固定到 SourceHut `v2.2.2`：tag object `2316fe346fece34726619498f34446b6d3df7c3a`、commit `d9554e7fa30a00abed7f0ac86b10e63c2c3b8e20`、tree `5ea9109a5005fbdc075443ebe16955b87d002ed5`、archive SHA-256 `7d01dd8bf9c2f93ea016ae8b059110c50cea49e78670e8a1333ebd5899cdaaa3`、签名 key fingerprint `2C7F29AE97891F6419A9E2CDB0076E490B71616B`。报告不得包含 `signature_valid`、`source_verified`、`tool_source_traceable` 等自报结论；validator 只接受逐层 exact-key 的事实和本地重算文件记录。
6. 当前固定公钥文件、最终 binary、provenance report 和 liveness report 的预期 SHA-256 均为 `None`，而且 `EXECUTION_TOOL_PASS_VALIDATION_IMPLEMENTED` 固定为 `False`。因此缺 provenance 为 `pending-source-provenance`；来源事实成立但尚未固定公钥/binary 为 `pending-source-provenance` 或 `pending-binary-review`；同一 binary 尚未在最终宿主复核为 `pending-execution-tool-liveness`；即使未来四个哈希都已完成独立审查，当前实现仍只能到 `pending-validator-hardening`。不得仅填哈希或翻转该常量来获得 pass；在可能启用 `pass-traceable-execution-transport` 前，必须先由代码直接解析实际 Mach-O/ELF/PE 与架构、固定并核验 libusb 等动态依赖、执行真实的 tag/commit 签名验证、建立固定源码到构建产物的关系、把 collector/watchdog 收紧为完整 exact-array allowlist，并由最终 executor 以无 symlink 的不可变 staging 或已打开文件描述符消除路径 TOCTOU。Linux x86_64 build 只是 Linux 候选，不能替代 macOS ARM64 或其他最终宿主。
7. Heimdall v2.2.2 的 `download-pit --wait` 语义存在已知反转；未来 collector 必须先外部确认唯一 `04e8:685d`、不传 `--wait`/`--resume`，使用外部 watchdog、全新不存在的 PIT 路径、单次尝试，并记录无 `LD_*`/`DYLD_*` 注入的环境。liveness 仍会 claim/reset USB、BeginSession/EndSession；“只读”只表示没有主机请求分区写入，并不表示设备状态绝对不变。任何现场采集仍须单独授权。
8. 因此当前即使其余外部报告在结构上全部通过，`execution_prerequisites_ready` 仍硬性保持 `false`，`execution_status` 保持 `blocked-first-boot-execution`。未来完成触发路径与可追溯工具链的独立代码审查后，状态最多只能变为 `awaiting-explicit-device-write-authorization`；用户仍须针对精确镜像、分区、命令和恢复路线另行明确授权。JSON、静态 pass 和“继续”都不能代替该授权。

`deployable`、`device_writes_performed` 和 `explicit_device_write_authorization_recorded` 在聚合结果中始终为 `false`。

示例命令（路径按实际主机调整）：

```bash
python3 implementation/uefi/validate-first-boot.py \
  --windows-media-report /path/to/windows-media-validation.json \
  --stock-recovery-report /path/to/SM-T860-XAR-DWH1/validation.json \
  --recovery-transport-report /path/to/recovery-transport-evidence.json \
  --execution-tool-provenance-report /path/to/execution-tool-provenance.json \
  --execution-tool-liveness-report /path/to/execution-tool-liveness.json \
  --recovery-trigger-report /path/to/reviewed-recovery-trigger-report.json \
  --action-plan /path/to/reviewed-first-boot-action-plan.json
```

## 恢复能力的已知证据与局限

本机历史证据已能证明“从未验证过 transport”的说法不准确：同序列号 SM-T860 的 Heimdall 2.0.2 日志包含 `Session begun`、PIT 下载成功，以及 RECOVERY、BOOT、VBMETA 上传成功；之后有 Android 完成启动、user 0 `RUNNING_UNLOCKED` 与固定 TWRP prefix readback 证据。因此严格绑定后可记为 `pass-historical-sm-t860-heimdall-transport`。

这个 pass 只是历史能力：当时 Heimdall 二进制的来源不可追溯，历史写入和后续 Android 启动不保证当前 USB/设备状态，也不保证未来恢复一定成功。当前会话报告同样只是本地自证材料；它不会替代独立授权或自动产生 action-ready 状态。

microSD 是当前优先研究的 Windows 系统介质，ESP 应包含标准 ARM64 fallback `\EFI\BOOT\BOOTAA64.EFI`。USB Mass Storage 只是固件组合里存在的备用研究方向，不是已验证启动通道。

把精确 UEFI 镜像写入 `RECOVERY` 会覆盖当前 recovery；写入 `BOOT` 则会改变 Android 正常启动路径，因此本项目的 action plan 不允许把 `BOOT` 作为目标。当前精确哈希仍未实机验证。任何计划都不得修改 `BOOT`/`DTBO`/`VBMETA`/PIT，不得重分区、跳过尺寸检查或连续试刷；哈希不符、分区不符、Download Mode 不可用、黑屏/重启循环或主机丢失设备时必须停止。

## 证据来源

- ARM64 Samsung Qualcomm 设备驱动清单：<https://github.com/potassium-os/NP545XLA-kernel/blob/main/docs/dump/NP545XLA-hw-dump/qualcomm-drivers.txt>
- Windows `sdbus` 组件清单样本：<https://github.com/colorsci/nickel-x64/blob/b3f8c9549e49f2a92b401b3809b210d5f78190ba/WinSxS/Manifests/amd64_dual_sdbus.inf_31bf3856ad364e35_10.0.22621.1_none_31441826756cc490.manifest>
- Project-Aloha PR #239 的 T860 SD/touch 与 UFS 损坏风险报告：<https://github.com/Project-Aloha/mu_aloha_platforms/pull/239#issuecomment-1986944283>
- T860 关闭 MLVM 后仍启动的专属提交：<https://github.com/Project-Aloha/mu_aloha_platforms/commit/b36a8226b684e698ff8f9a45172d62db8485a044>
- 上游 gts6l Android boot v0 packer：<https://github.com/Project-Aloha/mu_aloha_platforms/blob/9ff4c1f9202b19ef53e68214f25c58718dc6d1f2/Platforms/SurfaceDuo1Pkg/PythonLibs/PostBuild.py>
- 只移除 LTE `samsung-gts6l`、Wi-Fi 版本不受影响的 PR #746：<https://github.com/Project-Aloha/mu_aloha_platforms/pull/746>
- 官方 SM-T860 TWRP 页面：<https://twrp.me/samsung/samsunggalaxytabs6qcomwifi.html>
- 固定 UEFI 源码：`research/repos/mu_aloha_platforms` commit `96add763040d86d21f87a4a4022e094e17e6e3c6`

跨设备资料、上游报告和历史本机日志只用于建立路线与风险边界；最终判断仍必须以 SM-T860 的最终 ACPI/固件、目标 Windows ARM64 介质和经单独授权采集的当前会话证据为准。
