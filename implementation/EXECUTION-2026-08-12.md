# SM-T860 WoA 离线 MVP 执行记录（2026-08-12）

## 当前结论

本轮已经从“可行性研究”进入“可复现离线实现”。结论是：**值得继续到可逆、外置介质的 Windows 启动验证，但现在还不能刷写或部署。** 2026-08-13 的 UFS-offline Linux 构建已达到 `pass-ufs-offline-uefi-build`，参考产物位于 `dist-gts6lwifi-ufs-offline/`，但 `deployable` 仍为 `false`。

值得继续的依据不是参考机相似，而是 T860 官方源码、当前 Android 实机和既有 Windows 资产已经形成闭环：

- 官方 r06 DTS 给出了 IC12/IC15 的 QUP、MMIO、中断、GPIO、I2C 地址和板级坐标；
- 连接设备 `SM-T860 / T860XXS5DWH1` 的 `i2c_geni` GSI 388、618 和 GPIO5 `sec_epen_irq` 均有实际活动；
- 既有 Tab S6 UEFI DSDT 可以规范化后由 ACPICA 重新编译；
- 现有 `qci2c8150.sys`、Wacom 源码和 SM5705 源码足以组成一个 I2C/read-mostly MVP。

这还不等于完整 BSP。GPU、WLAN、UFS 安全策略、显示接管、触控、充电、睡眠和音频仍不在本轮通过范围。

## 已实现并验证

| 层级 | 本轮产物 | 状态 |
|---|---|---|
| ACPI | IC12 + `SMF5705`，IC15 + `WCP9021`，PEP 时钟/总线/TLMM | ACPICA 20260408：0 errors；67 个警告为原表基线债务 |
| I2C | 为 ACPI UID 12/15 增加 qci2c 实例，首测固定 FIFO | INF 已暂存；必须在 WDK 上重新验签 |
| Wacom | T860 r06 坐标/翻转/换轴、GPIO5 IRQ、GPIO68 3.3 V enable | 源码与 INF 已改；角点和源码不变量测试通过 |
| Fuel gauge | 合法项目 HID `SMF5705`，I2C 0x71；不公开 IRQ | 仅只读遥测；未暴露 charger/MUIC；源码需 WDK 构建 |
| OEM | 三包 MVP FeatureManifest 和明确的非部署清单 | `pass-source-stage`；缺少两个源驱动二进制符合预期 |
| Windows 构建 | Wacom/SM5705 ARM64 构建、PE 校验、InfVerif、Inf2Cat、可选测试签名脚本 | 已准备，当前 macOS 主机不能执行 WDK 阶段 |
| UEFI 集成 | 临时 clone 注入 AML、剔除 UFSDxe、保留 SdccDxe、构建后递归解析 FV | Linux x86_64 构建与静态校验通过；仍不可部署 |

AML 产物为 `360474` 字节，SHA-256：

`3127d563379cc34c1ed1b7ef59eff139ca602a9ad657bf976ab2eb8b8cf239dd`

本轮未执行 ADB 写入、分区操作、刷机、重启或 Windows 驱动安装。

## 为什么仍不能上机

当前 `implementation/build/oem` 故意保持 `deployable: false`，原因如下：

1. Wacom 与 SM5705 的 ARM64 `.sys` 尚未由 Windows 11 WDK 实际构建；三份改过的 INF 也没有新 catalog/test signature。
2. AML 已集成进 UFS-offline 参考 UEFI 并通过静态校验，但尚未证明 T860 能从可逆路径执行它，也未证明失败后的恢复链。
3. qci2c 的 UID 12/15 注册值虽有 DTS 和现有驱动格式依据，但是否能在 FIFO 模式 Code 0 必须用 Windows PnP/ETW/KD 验证。
4. Wacom GPIO68 在 Android 是 boot-on、active-high 的 3.3 V regulator enable。现驱动会做受控 low/high 上电序列；时序仍需真机日志验证。
5. SM5705 包只读取 fuel-gauge 寄存器。它不能控制主 charger、MUIC 或 S2MM005，也不能据此允许无人值守充电。
6. 原 DSDT 的 67 个警告尚未清零；它们没有阻止本轮构建，但在固件集成前必须建立逐项基线和回归策略。

## 下一阶段的精确入口

在装有 Visual Studio 2022 与 Windows 11 WDK 的 Windows 主机上，从仓库根目录运行：

```powershell
.\implementation\windows\build-packages-arm64.ps1
```

脚本会编译两个源码驱动，确认三个 `.sys` 都是 ARM64，运行 InfVerif 和 Inf2Cat，并生成带哈希的 `manifest.json`。只有安装了专用测试证书后，才传入 `-CertificateThumbprint`；脚本本身不会部署驱动。

WDK 阶段通过后，真机顺序必须是：

1. 把 AML 集成到可恢复、外置启动路径；禁止 Windows 自动联机内部 UFS。
2. 先只装 qci2c，确认 `ACPI\QCOM0511\12` 和 `\15` 为 Code 0，并采集 ETW/KD。
3. 安装 SM5705，只核对 device ID、SOC、电压、温度、电流；仍禁用 charger/MUIC/PD。
4. 最后安装 Wacom，检查 startup query、GPIO5 IRQ、四角、倾斜、擦除和睡眠唤醒。
5. 任一步出现 I2C 总线锁死、持续中断风暴或 UFS 被联机，立即停止并回到 Android/恢复路径。

固件可在 Linux x86_64 主机复现：

```sh
./implementation/uefi/build-gts6lwifi.sh
```

参考构建固定 `mu_aloha_platforms` revision `96add763040d86d21f87a4a4022e094e17e6e3c6`。构建脚本在临时树中将安全 ACPI 放入未压缩外层 FV，并关闭 boot payload gzip，以便对最终 FD/IMG 做精确字节验证；不会改写固定 submodule。当前 macOS/arm64 主机只进行产物和脚本的离线审计，不在本机伪造 Linux 构建结果。

## 继续价值与止损条件

建议继续的目标是“实验型平板 MVP”，不是日用或商业产品。下一笔投入最有价值的是 WDK 构建和一次可恢复启动，因为它能直接回答 PEP/qci2c/驱动链是否真实成立。

以下任一情况应重新评估：

- IC12 与 IC15 在 ACPI/PEP/FIFO 已完整的前提下仍稳定 Code 10，且 ETW/KD 显示现有 `qci2c8150.sys` 不支持对应路由；
- 可恢复 UEFI 无法保持内部 UFS 离线，或显示/USB 恢复路径不稳定；
- Hana 的 GPU/WLAN 在核对 PIL、固件和内存契约后仍无可用路径。

在上述止损条件出现前，继续价值为中等偏高：关键资源已从猜测变成可编译、可测试的实现；主要不确定性已经转移到 Windows WDK 与真机运行时，而不是硬件拓扑本身。
