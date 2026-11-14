# readboy-g35s-lk2nd

为 **读书郎 ReadBoy G35S**（Qualcomm MSM8916 / 骁龙 410，8″ 800×1280 学生平板）
做 mainline Linux 移植的设备树与构建流水线。

全部编译在 GitHub Actions 上完成，本地只需要 `git`，不需要 Linux 环境。

---

## ⚠️ 项目状态：设备已不可启动

**本仓库记录的这台设备目前无法开机**，需要 EDL（9008）才能恢复。

原因是尝试用 DB410c 的 TZ 固件替换原厂 TZ 以启用 arm64 时，新 TZ 与 SBL1 不兼容，
在 TZ 初始化阶段挂住，导致引导链中断。

- 恢复方法与文件清单见 **[docs/RECOVERY.md](docs/RECOVERY.md)**
- arm64 为什么走不通的完整证据链见 **[docs/ARM64-INVESTIGATION.md](docs/ARM64-INVESTIGATION.md)**

**本仓库的构建产物（设备树、内核镜像、lk2nd、诊断版 lk2nd、qhypstub）都是可用且经过验证的**，
问题只出在最后一步的固件替换决策上。

---

## 背景

这台平板出厂是 Android 4.4（**32 位**），一次跨平台 ROM 移植把 `boot` 和 `system`
写坏了：内核还是原厂的，但 DTB 被换成了展锐平台的，`system` 被换成了三星 SM-T113NU 的。

`lk2nd` 是一个二级引导器，被打包成标准 Android boot 镜像刷进 `boot` 分区，
由原厂引导器加载，然后提供**通用 fastboot 接口**。有了它，刷内核、刷 rootfs
就都是标准流程。

## 硬件速查

| 项目 | 值 |
|---|---|
| SoC | MSM8916（4×Cortex-A53），PM8916 |
| 内存 / 存储 | 1 GiB / AJNB4R eMMC 14.56 GiB（HS200） |
| 屏幕 | 800×1280，MIPI DSI 4-lane，60Hz，24bpp |
| 触摸 | Goodix GT9xx @ I2C 0x5d，5 点 |
| 板型 | `msm-id 0xCE`，`board-id 0x1000B`（MTP 参考设计） |
| 分区 | GPT，27 个 |

完整清单（面板候选、时序参数、传感器、分区偏移）见 **[docs/HARDWARE.md](docs/HARDWARE.md)**。

---

## 仓库结构

```
.
├── LICENSE                                  BSD-3-Clause
├── README.md
├── docs/
│   ├── HARDWARE.md                          硬件清单（从原厂 DTB 提取）
│   └── ARM64-INVESTIGATION.md               arm64 不可行的完整排查记录
├── device/
│   ├── msm8916-readboy-g35s.dts             lk2nd 设备树
│   ├── kernel/msm8916-readboy-g35s.dts      mainline 内核设备树（最小化）
│   ├── init                                测试用 initramfs init
│   ├── mkbootimg.py                         Android boot 镜像打包器（支持 QCDT）
│   └── instrument_lk2nd.py                  给 lk2nd 注入调试埋点 + EL2 直切尝试
├── tools/
│   ├── dtb_dump.py                          从 boot 镜像提取 QCDT 并反编译 DTB
│   ├── fdtpatch.py                          FDT 属性原位等长修改
│   └── fdtpad.py                            给 DTB 加尾部空闲空间
└── .github/workflows/
    ├── build.yml                            lk2nd 构建
    ├── kernel.yml                           mainline 内核构建
    ├── lk2nd-debug.yml                      诊断版 lk2nd（带埋点）
    └── qhypstub.yml                         qhypstub 构建与签名
```

---

## 四个 workflow

### 1. `build.yml` — lk2nd

```
克隆 msm8916-mainline/lk2nd
  → 注入 device/msm8916-readboy-g35s.dts，往 rules.mk 的 QCDTBS 追加
  → make TOOLCHAIN_PREFIX=arm-none-eabi- lk2nd-msm8916
  → 上传 lk2nd.img
```

产物：`lk2nd-msm8916-readboy-g35s`（约 420 KB）

刷入方式：`fastboot flash lk2nd lk2nd.img`，或经 UMS 写到 `boot` 分区偏移 0。

> `fastboot flash boot` 在 lk2nd 里会写到 **+512 KiB 偏移**，避免覆盖 lk2nd 自身。

### 2. `kernel.yml` — mainline 内核

```
下载 msm8916-mainline/linux（tarball，不用 git clone）
  → 注入 device/kernel/*.dts，往 qcom/Makefile 追加 dtb 目标
  → make msm8916_defconfig + make Image dtbs
  → 用 busybox-static 生成测试 initramfs（device/init）
  → device/mkbootimg.py 打包成 boot-mainline-g35s.img（带 QCDT 封装）
```

产物：`mainline-g35s-boot`（含 `boot-mainline-g35s.img`、`Image`、全部 `msm8916-*.dtb`）

**为什么是未压缩的 `Image` 而不是 `Image.gz`**：
早期怀疑 lk2nd 解压有问题，后来证实不是，但未压缩更贴近原厂行为，
减少了一个变量，就一直保留了。

**为什么 initramfs 要起 USB gadget**：
这台机器没有可用显示、没有串口引出。内核起来后唯一能观察到的信号就是 USB。
initramfs 通过 configfs 挂 `1d6b:0104` 的 CDC-ACM 设备：

- 主机出现新串口 → 内核成功启动
- 什么都没出现、fastboot 又回来了 → 内核早期崩溃

> 注意：`msm8916_defconfig` 默认**没有** `CONFIG_USB_CONFIGFS`，
> workflow 里用 `scripts/config -e USB_CONFIGFS` 补上了。没有这个，gadget 根本不会生效。

### 3. `lk2nd-debug.yml` — 诊断版 lk2nd

在 `scm_elexec_call()` 和 `update_device_tree()` 里插入 RAM 埋点
（写到 `0x9FF80000`），复位后用 `fastboot oem debug readl` 读回，
用于定位"内核为什么没起来"。

产物：`lk2nd-debug-msm8916-readboy-g35s`

另外它还给 `scm_elexec_call()` 加了**两种 SCM 约定互备**：
旧式 `scm_call` 返回后自动改用 `scm_call2` 重试（成功的话永远不会返回，所以重试零代价）。

### 4. `qhypstub.yml` — hyp 替换件

```
克隆 qhypstub + qtestsign
  → make CROSS_COMPILE=aarch64-linux-gnu-
  → 自动签名（qtestsign 用测试密钥）
```

产物：`qhypstub-msm8916`（`qhypstub-test-signed.mbn`、`qhypstub.bin`）

⚠️ 只有**固件安全启动未开启**的设备才能用签名后的版本。
刷之前务必确认能进 EDL。

---

## 设备树说明

### lk2nd 设备树

```dts
qcom,msm-id   = <0xce 0x0>, <0xf8 0x0>, <0xf9 0x0>, <0xfa 0x0>;
qcom,board-id = <0x1000b 0x41>, <0x1000b 0x42>, <0x1000b 0x88>;
```

这两个值是从原厂 DTB 逐字节抄出来的，让 lk2nd 认出这台机器。

**刻意没写** `lk2nd,match-panel` 和 `lk2nd,dtb-files`：面板节点名必须与 lk2nd
显示驱动里的 ID 完全一致，原厂用的是 `qcom,mdss_dsi_video_kd080d34` 这类名字，
lk2nd 现有设备用的是 `qcom,mdss_dsi_nt35521_800x1280_video`，对不上。
名字写错会导致 lk2nd 启动失败。

实测结果：lk2nd 能起来并提供 fastboot，但日志报
`Failed to find matching lk2nd device node: -1`（走了通用路径，功能正常）。

### 内核设备树

只启用三样：UART2 控制台、eMMC（`sdhc_1`）、USB peripheral。

**刻意关掉**：显示、触摸、GPIO 按键、WiFi/BT、音频、摄像头、传感器。

面板驱动（NT35521 等）mainline 里**没有**，这是移植中真正的技术缺口。
先把"内核能起来"验证掉，再一个一个加。

另外 **没有覆盖任何 regulator 电压** —— 电压设错是能烧硬件的，而参考设计
`msm8916-pm8916.dtsi` 的值是经过验证的，直接用。

---

## 踩过的坑（供参考）

| 现象 | 原因 | 解法 |
|---|---|---|
| `FAILED (remote: 'dtb not found')` | lk2nd 的 `copy_dtb()` 要求 dt 区是 **QCDT 容器**，不是裸 FDT | `mkbootimg.py` 默认把 dtb 包成 QCDT |
| 内核起来但主机看不到 USB | `msm8916_defconfig` 缺 `CONFIG_USB_CONFIGFS` | CI 里 `scripts/config -e USB_CONFIGFS` |
| `git clone` 内核仓库超时 | 完整仓库太大 | 改下载 tarball |
| `fastboot boot` 后 26 秒复位 | 内核根本没执行，卡在 `scm_elexec_call` 的 `ASSERT(0)` | 见 `docs/ARM64-INVESTIGATION.md` |
| DTB 修改静默失败 | dtc 输出的 blob **没有空闲空间**，`fdt_add_subnode` 全部失败 | `tools/fdtpad.py` 加填充 |
| initramfs 里 busybox 是 7 字节 | `cp` 复制了符号链接而不是实体 | `cp -L`，并加体积断言 |

---

## 测试纪律

```
fastboot boot <img>      ← 只加载到内存，不写 flash，失败断电重来
        ↓ 连续多次稳定
fastboot flash boot      ← 这时才落盘
```

lk2nd 在没有显示时**不会停在菜单**，会直接引导 `boot` 分区 +512 KiB 处的镜像。
那里放一个会卡死的内核，每次上电都会自动引导它卡住，fastboot 就没了。
`fastboot boot` 完全规避这个。

**更重要的：动引导链固件（tz / hyp / sbl1 / aboot）之前，必须先验证 EDL（9008）可达。**
本项目就是栽在这一步。

---

## 许可证

[BSD 3-Clause](LICENSE)。

`device/kernel/msm8916-readboy-g35s.dts` 采用 `GPL-2.0-only OR BSD-3-Clause`，
与 Linux 设备树的惯例一致，便于向上游提交。
设备树源文件派生自 [msm8916-mainline](https://github.com/msm8916-mainline) 项目，
保留原有许可。
