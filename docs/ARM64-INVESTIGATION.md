# 为什么这台机器的 arm64 走不通

一份完整的排查记录。结论：**本机固件（TZ/QSEE）是 32 位-only 构建，拒绝执行
32→64 位切换，因此无法启动任何 AArch64 内核**。

如果你手上有另一台"固件老旧的 MSM8916 设备"，大概率会撞到同一堵墙，这份文档能
帮你少走弯路。

---

## 症状

`fastboot boot` 一个已知可用的 arm64 mainline 内核后：

- 全程无任何新 USB 设备（没有 `1d6b:0104`）
- 约 **26–28 秒**后设备复位，回到 fastboot
- 换成上游 `msm8916-mtp.dtb` / `apq8016-sbc.dtb` 行为完全相同
- 换成 gzip 内核 / 未压缩内核、改 `kernel_addr`、给 memory 补大小 —— 全部无变化

## 排查方法：往 RAM 写埋点

设备没有 UART、没有可用显示，lk2nd 在跳转内核前就停了 fastboot，
所以唯一的观测手段是让 lk2nd 把进度写进内存，复位后再用
`fastboot oem debug readl <addr>` 读回来。

埋点写在 `0x9FF80000`（lk2nd scratch 区尾部 512 KiB，ramoops 用不到时是空的）。

### 需要的两个补丁

1. `app/aboot/aboot.c`：在 `update_device_tree()` 前后写标记
2. `platform/msm_shared/scm.c`：在 `scm_elexec_call()` 里写标记，
   并在原逻辑基础上增加"两种 SCM 约定互备"

实现见本仓库 `device/instrument_lk2nd.py`。

### 埋点实测结果

| 地址 | 值 | 含义 |
|---|---|---|
| `+0x10` | `0xB0070010` | `update_device_tree` 已进入 |
| `+0x14` | `0x00000000` | 返回值 **0 = 成功**，DTB 完全没问题 |
| `+0x18` | `0xB0070001` | 已进入 `scm_elexec_call` |
| `+0x1C` | `0x80000000` | kernel_entry 正确 |
| `+0x20` | `0x81E00000` | dtb 地址正确 |
| `+0x04` | `0x00000000` | `is_scm_armv8_support()` = false（选旧式约定） |
| `+0x0C` | `0xFFFFFFFC` | 旧式 `scm_call` 返回 **-4** |
| `+0x08` | `0x00000000` | `scm_call2` 返回 0 但没有发生切换 |
| `+0x00` | `0xB0070BAD` | 两种约定都返回了 → 落到 `ASSERT(0)` |
| `+0x24` | `0x60000193` | CPSR |
| `+0x28` | `0x00000013` | CPSR mode = **SVC = EL1** |

## 三个独立证据，指向同一个结论

### ① 内核从未被执行

内核 BSS 区在 `0x81226000–0x81290000`。如果 CPU 执行过内核，
`__create_page_tables` 必定会往那里写页表。启动前后各读一次：

```
0x81227000  0x00000000  →  0x00000000
0x81250000  0x00000400  →  0x00000400
0x81280000  0x00000000  →  0x00000000
（八个采样点全部一字未变）
```

同时 `0x80000000` = `0xd503201f`（arm64 内核第一条指令 `nop`），
证明内核**确实被 memmove 到位了**，只是没被执行。

### ② 失败点在 `scm_elexec_call`，不在 DTB

`update_device_tree` 返回 0（成功），说明设备树更新完全正常。

做对照实验进一步确认：用**原厂 32 位内核 + 我们的 mainline DTB** 启动。
32 位内核走 `boot_linux()` 的 `entry()` 分支，**完全绕过 SCM**：

| 组合 | 结果 |
|---|---|
| mainline 内核（arm64） | 28 秒静默复位（`ASSERT(0)` 自旋被看门狗咬） |
| 原厂内核（arm32）+ 我们的 DTB | **永久挂死，不再复位** |

后者行为完全不同，说明 DTB 更新成功、内核真的被跳转进去了。

### ③ lk2nd 运行在 EL1，无法自救

`CPSR = 0x60000193`，mode 字段 `0x13` = SVC = **EL1**。

AArch32 的 EL1 **无法**跳转到 AArch64——这是 ARM 架构的硬性规定，
只有 EL2/EL3 能做执行状态切换。

逐条排除了"EL 是后来被降下来的"：

| 跳转前的操作 | 是否改 EL |
|---|---|
| `platform_uninit()`（msm8916）= 仅 `qtimer_uninit()` | 否 |
| `target_uninit()` = eMMC 休眠 + crypto 清理 | 否 |
| `arch_disable_cache()` / `arch_disable_mmu()` | 否 |
| `enter_critical_section()` = 关中断 | 否 |

lk2nd 是被 aboot 用 `entry()` **直接跳转**过来的（不改 EL），所以 aboot 也在 EL1。

## 相关代码

`platform/msm_shared/scm.c`：

```c
void scm_elexec_call(paddr_t kernel_entry, paddr_t dtb_offset)
{
    ...
    if (!is_scm_armv8_support()) {
        scm_call(svc_id, cmd_id, cmd_buf, cmd_len, NULL, 0);
    } else {
        scm_arg.x0 = MAKE_SIP_SCM_CMD(SCM_SVC_MILESTONE_32_64_ID,
                                      SCM_SVC_MILESTONE_CMD_ID);
        ...
        scm_call2(&scm_arg, NULL);
    }

    /* Assert if execution ever reaches here */
    dprintf(CRITICAL, "Failed to jump to kernel\n");
    ASSERT(0);      /* ← 死循环，28 秒后被看门狗复位 */
}
```

`SCM_SVC_MILESTONE_32_64_ID = 0x1`、`SCM_SVC_MILESTONE_CMD_ID = 0xF`。
`scm_call` 返回的是 `smc()` 的原始返回值，所以 `-4` 是 TZ 的直接应答：
它听懂了请求，但拒绝执行。

## TZ 固件核查

| 项目 | 值 |
|---|---|
| `tz` 与 `tzbak` | **逐字节相同**（没被写坏） |
| ELF | `class=1`（32 位）、`machine=0x28`（ARM）、`entry=0x86500000` |
| 可读字符串 | 1174 条，其中**没有** `milestone` / `elexec` / `32_64` 任何痕迹 |

对比 DB410c 的 `tz.mbn`：`class=2`（**ELF64**）、483,468 字节——
这才是有 32→64 服务的版本。

## 为什么 qhypstub 救不了

qhypstub 的 README 里写过"用 HVC 直接跳 AArch64"，但同文档也说明了它**是坏的**：

> This would be really nice and simple ... but unfortunately it does not work properly,
> as you can see for CPU1.

原因是 TZ 的 PSCI 实现有 bug：如果不走那个 32→64 的 SMC，其他 CPU 核会被
以 aarch32 状态启动。

qhypstub 实际采用的是"异常级乒乓"：

1. 打开 stage-2 地址转换，把 EL1 能访问的内存全部禁掉
2. 发起 **TZ 的 32→64 SMC**
3. TZ 返回 EL1 后立刻 Instruction Abort，弹回 EL2
4. qhypstub 以 EL2 AArch64 跳内核

**第 2 步仍然必须成功。** 所以 qhypstub 只能配合 TZ，不能替代 TZ。

（另外：lk2nd 主线源码里**没有** qhypstub 运行时加载的实现，
qhypstub README 中 `fastboot flash qhypstub` 那段描述已经过时。）

## 唯一的 arm64 出路：换 TZ

社区成熟做法（华为 Ascend G7 是几乎一样的案例）：

- `tz` ← DB410c 的 `tz.mbn`
- `hyp` ← qhypstub（或 DB410c 的 `hyp.mbn`）

**硬约束**：两者必须**一起换**，只换一个就重启会变砖
（DB410c tz + 原厂 hyp 不兼容）。

本机在这条路上失败了——刷入后 SBL 加载 TZ 时挂住，导致：

```
PBL（只读 ROM）→ SBL1 → 加载并启动 TZ ← 卡在这里
                          ↓ 本该继续加载 aboot
                      fastboot / 9006 下载模式
```

TZ 一挂，SBL 无法继续，于是既没有 aboot（无 fastboot），
也到不了 SBL 自己的下载模式（无 9006），PBL 早已交棒不会自动回 9008。
**只能靠 EDL（9008）恢复**，而 EDL 需要物理手段触发。

## 对同类机型的建议

MSM8916 存在两类机型，mainline 官方也是这么分组的：

**arm32 组**（`arch/arm/boot/dts/qcom/`，固件不支持 32→64）
```
qcom-msm8916-samsung-e5 / e7 / fortunaltezt / grandmax / heatqlte / serranove
```

**arm64 组**（`arch/arm64/boot/dts/qcom/`，固件支持 32→64）
```
msm8916-samsung-a3u / a5u / j5 / gt510 / gprimelte / motorola-osprey / asus-z00l …
```

**判断方法**：如果原厂系统是 32 位 Android 4.4 且 TZ 是 32 位 ELF，
基本可以确定属于 arm32 组。这种情况下：

- 想跑 Linux → 用 **arm32** 内核（mainline 支持，`entry()` 引导，不经 TZ）
- 想跑 arm64 → 必须先换 TZ，而换 TZ 有变砖风险，**务必先确认能进 EDL**

## 教训

1. **刷引导链固件前，必须先验证 EDL（9008）可达。** 这是第一原则。
2. 不要用未确认语法的命令向设备发请求，尤其是在"校验"这种非必要环节。
3. `tzbak` / `hypbak` 要不要一起刷，取决于 SBL 是否会用备份分区——
   一起刷能保证一致性，但也断掉了"坏了一个还有另一个"的退路。
