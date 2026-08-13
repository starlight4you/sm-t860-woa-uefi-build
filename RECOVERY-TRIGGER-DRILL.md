# SM-T860 Recovery 触发门禁

更新日期：2026-08-13。当前状态是 `pending`。本页定义未来一次“不刷分区”的 Recovery 触发演练；它不是刷写教程，也不包含本轮设备操作授权。

## 已知机制证据

同一台 SM-T860 的历史本机日志把候选路径收敛为明确的按键状态转换：Download/Odin 传输结束后，`KPDPWR_AND_RESIN` 触发硬复位；原厂 DTS 证明 `RESIN` 是 Volume Down。下一阶段先观察到 Power 保持、Volume Down 已释放，随后 ABL 采样 Power+Volume Up（`0x81`），选择 `BootMode=2` 与 `recovery` 分区。配对的 Recovery 日志记录 `RebootRecoveryWithKey`、`ro.boot.boot_recovery=1` 和 manual mode。

内部原始证据含潜在持久标识，不上传公开仓库；公开材料只记录文件哈希：

- `last_kernel-v0.4-real-firstboot-20260802.txt`：`5e6faabb822278edcebc699dc319bd02b52a41be035ff1dc815561a25ab5d01e`
- `last_kmsg-v0.4-recovery-entry-20260802.txt`：`c08bd1379b00f80f858b81031e87b299fe1c3280dcffcc9cb564b00e9fe3798b`
- 原厂 `pm6150.dtsi`：`12628093a7d8189fd0fb38d79ad648bf39619395a64c578e529894986fbfbcd9`
- 同机历史 `FLASHING_GUIDE.md`：`072867b1f425c1b9dcd77b4ceb79113b072d8973553d08998bb39cb3de3c7089`

Heimdall 的 `DownloadPitAction` 与 `FlashAction` 在 `--no-reboot` 时都以 `EndSession(false)` 结束。因此只读 `download-pit --no-reboot` 可用于建立相同的协议后置状态，而无需上传分区；它不证明两种操作的所有设备内部状态逐位相同，也不验证 UEFI payload。`close-pc-screen --resume` 只请求普通重启，2026-08-13 的实测结果是返回 Android，不能作为 Recovery trigger。

## 候选状态机

仅在用户对该次重启/人工按键演练另行明确授权后，才可按以下状态机采集证据：

1. `DOWNLOADER_HELD`：USB 全程连接；从 `EndSession(false)` 后的 Download Mode 按住 Power+Volume Down。
2. `DISPLAY_BLACK_EDGE`：显示屏首次变黑时，Power 始终不放；先释放 Volume Down。
3. `RECOVERY_SELECT`：在 Volume Down 已释放后立即按住 Volume Up，形成 Power+Volume Up。
4. `RELEASE`：只在出现 Recovery 专属证据后释放。

不把“约 7 秒”或任何毫秒窗口设为通过条件；现有证据只支持事件条件 `immediate-on-display-black-edge`。Power+Volume Down+Volume Up 的历史掩码 `0x83` 会重新进入 Odin/Download Mode，因此两个音量键重叠是立即停止条件。

演练的主机前置动作只能是一次固定 Heimdall `download-pit --no-reboot --stdout-errors`，输出到全新、唯一的 PIT 路径；不得上传分区、flash、写 PIT、重分区、跳过尺寸检查或自动重试。成功证据至少要绑定同一设备的脱敏身份、唯一 `04e8:685d` 枚举、前置命令与输出 PIT、Recovery ADB 的 `ro.boot.boot_recovery=1`、SM-T860 型号和 DWH1 bootloader；若为 TWRP，再要求 TWRP boot/version 属性。完整 `getprop` 不得公开。

这只能声明“没有主机发起的分区写入”，不能声称设备存储逐位不变：进入 Samsung Recovery 本身可能更新 PARAM、启动/恢复原因、cache 日志或 BCB。

## 代码门禁

聚合器的 `--recovery-trigger-report` 当前没有任何可接受的报告 SHA-256：缺失报告为 `pending`，提供任意报告均为 `fail`。代码里已有一版保守的 schema 草案，用于提前拒绝明显不完整的输入；它会绑定当前 transport 报告、PIT/日志哈希、采集窗口，以及 evidence root 中的 Recovery 属性、返回 Android 属性、唯一 Download USB 枚举和人工按键 transcript，并重算文件 SHA-256。该草案本身还不是未来现场证据的最终验收规范：正式采集前必须再补齐四类证据文件互异、完整行/冲突值检查、Recovery 与 Android 的共同脱敏设备标识，以及 transport 与 trigger 的连续时间链；`sys.boot_completed` 与 TWRP 条件也必须按实际原始属性定义，不能由采集器填造。这意味着不存在可手工翻转的布尔开关。未来现场演练完成并经独立复核后，必须在同一次代码审查中完成这些约束并固定精确报告哈希，才能让 `recovery_boot_trigger` 进入 `pass`。

动作计划使用 schema 2，把人工动作表示为 `boot_trigger` 对象，而不是伪装成 Heimdall argv；`boot_trigger_argv` 必须是 `null`。它必须绑定固定 method id、Recovery trigger 报告哈希、唯一 `RECOVERY` 分区、精确 UEFI 镜像和原厂 recovery 回退镜像。即使该门禁通过，也只可能进入 `awaiting-explicit-device-write-authorization`；它不能授权写入，也不能证明当前 UEFI 镜像能启动。
