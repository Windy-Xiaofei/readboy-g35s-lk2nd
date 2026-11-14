# 从"设备不枚举"状态恢复

适用场景：刷入不兼容的 `tz` / `hyp`（或 `sbl1` / `aboot`）之后，设备完全不出现在 USB 上
——既没有 fastboot，也没有 9006 下载模式。

> 背景与原理见 [ARM64-INVESTIGATION.md](ARM64-INVESTIGATION.md)。
> 简而言之：SBL 加载 TZ 时挂住 → 加载不到 aboot → 没有 fastboot；
> SBL 自己的下载模式也到不了 → 没有 9006；PBL 早已交棒 → 不会自动回 9008。

## 唯一可行路径：EDL（9008）

EDL 由 **PBL（芯片内只读 ROM）** 提供，绕过 SBL 和 TZ，所以不受上述问题影响。
PBL 物理上不可损坏，所以只要有办法触发它，设备一定能救回来。

### 触发 EDL 的方式（按成功率排序）

1. **短接 EDL 测试点**（成功率最高）
   主板上两个相邻的裸露小焊盘，丝印可能是 `EDL` / `USB_BOOT` / `FORCE_DL` / `TP*`。
   用镊子短接两点，**保持短接的同时插 USB**。

2. **断开电池 + 组合键**
   拔掉电池排线 → 按住电源 15 秒 → **先按住「音量加 + 音量减」** → 接回电池 → 插 USB。

3. **纯按键组合**（本机无效，但其他机型可能有效）
   音量加 / 音量减 / 双音量 + 电源，在插 USB 或上电时保持按住。

进入成功后设备以 `VID_05C6&PID_9008` 出现（`qcser.inf` 已覆盖，免驱）。

## 进入 EDL 之后

需要三个东西：

- **firehose 编程器** `prog_emmc_firehose_8916.mbn`（msm8916 通用）
- **EDL 工具**：推荐 [qedl](https://github.com/baiyao105/qedl-rs) 或
  [bkerler/edl](https://github.com/bkerler/edl)
- **要写回的分区镜像**

```bash
qedl devices                       # 确认 9008 在线
qedl --loader prog_emmc_firehose_8916.mbn write tz     tz.img
qedl --loader prog_emmc_firehose_8916.mbn write tzbak  tz.img
qedl --loader prog_emmc_firehose_8916.mbn write hyp    hyp.img
qedl --loader prog_emmc_firehose_8916.mbn write hypbak hyp.img
qedl reboot
```

⚠️ `tz` 和 `hyp` **必须一起写回**。DB410c 的 tz 配原厂 hyp（或反过来）会导致变砖。

## 如果 EDL 也进不去

整盘镜像（如果事先做过位对位备份）是最后的手段：把 eMMC 拆下来，
用 eMMC 读卡器（Easy JTAG / eMMC 转接座 / SD 卡转接）接到电脑，整盘回写。

## 预防

**在改动 `tz` / `hyp` / `sbl1` / `aboot` 之前，先验证 EDL 可达。**

验证方法：在设备还正常的时候，用 `fastboot oem reboot-edl`（lk2nd 支持）进入 EDL，
确认电脑能识别 `05C6:9008`，然后再退出（`qedl reboot`）。
花两分钟，能避免整台设备变成只能拆机的状态。
