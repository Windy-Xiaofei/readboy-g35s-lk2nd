# ReadBoy G35S 硬件清单

全部信息来自**原厂 DTB 反编译**（`msm8916-readboy-g35s.dtb`，905 个节点）和
**eMMC 整盘备份**的实际读取，不是从网上抄的。

## SoC / 平台

| 项目 | 值 |
|---|---|
| SoC | Qualcomm MSM8916（Snapdragon 410），4×Cortex-A53 @ 1.2GHz |
| 制程 / 年份 | 28nm，2014 年发布；本机为 2017 年机型 |
| 平台类型 | MTP 参考设计衍生（QSOC） |
| `qcom,msm-id` | `<0xCE 0>`, `<0xF8 0>`, `<0xF9 0>`, `<0xFA 0>` |
| `qcom,board-id` | `<0x1000B 0x41>`, `<0x1000B 0x42>`, `<0x1000B 0x88>` |
| DTB `model` | `Allwinner Technologies, Inc. MSM8916 ARD Loong`（ODM 遗留串，实际是高通板） |
| PMIC | PM8916 |
| 引导链 | `sbl1 → aboot → (lk2nd) → kernel`，无 `xbl/abl`，属早期平台 |

`0x1000B` 就是 `QCOM_BOARD_ID_MTP`，说明这块板子定制度很低，DTS 可以大量沿用 MTP。

## 存储

| 项目 | 值 |
|---|---|
| eMMC 型号 | **AJNB4R** |
| 容量 | 15,634,268,160 字节（14.56 GiB） |
| 总线模式 | HS200 |
| 分区表 | GPT，27 个分区 |
| Manufacturer ID | 15 |

### 分区布局（关键项）

| 分区 | 偏移 | 大小 |
|---|---|---|
| `modem` | 67,108,864 | 64 MiB |
| `sbl1` / `sbl1bak` | 134,217,728 | 512 KiB |
| `aboot` / `abootbak` | 135,266,304 | 1 MiB |
| `rpm` / `rpmbak` | 137,363,456 | 512 KiB |
| `tz` / `tzbak` | 138,412,032 | 512 KiB |
| `hyp` / `hypbak` | 139,460,608 | 512 KiB |
| `misc` | 144,703,488 | 1 MiB |
| `splash` | — | 10 MiB |
| `boot` | 202,948,608 | 16 MiB |
| `system` | 219,725,824 | 3.5 GiB |
| `recovery` | — | 16 MiB |
| `userdata` | — | 10.9 GiB |

## 显示

| 项目 | 值 |
|---|---|
| 分辨率 | **800 × 1280**（竖屏） |
| 显示接口 | MIPI DSI，4 lane，burst mode |
| 色深 | 24 bpp |
| 刷新率 | 60 Hz |
| 推导 pixel clock | ≈ 67.84 MHz（单 lane ≈ 407 Mbps） |
| 水平时序 | hfp / hbp / hpw = 18 / 18 / 18 |
| 垂直时序 | vfp / vbp / vpw = 30 / 10 / 4 |
| reset 时序 | `<1 10 0 5 1 120>` |

### 面板候选（原厂 DTB 里 6 个）

| 面板节点 | 说明 |
|---|---|
| `nt35521` | Novatek |
| `nt35521_c8` | Novatek 变体，由 `dsi-pref-prim-str-1001` 选择 |
| `kd080d34` | 由 `dsi-pref-prim-str-1110` 选择，参数已完整提取 |
| `boe` | 京东方 |
| `djn8ich` | — |
| `68200` | — |

**背光**：`bl_ctrl_pwm`，PMIC PWM 100Hz，GPIO 0x45。

> 注意：`lk2nd` 的显示代码里已有 `qcom,mdss_dsi_nt35521_800x1280_video`
> （华硕 ZenPad 8.0 P024 在用），所以 `nt35521` 这一支在 lk2nd 阶段大概率能点亮。

## 触摸

| 项目 | 值 |
|---|---|
| 型号 | **Goodix GT9xx** |
| 节点 | `goodix@5d` |
| 总线 | I2C，地址 `0x5d` |
| 触点数 | 5 |
| 分辨率 | 0x320 × 0x500（800×1280） |
| 固件 | `gtp_fw.bin` |
| 备选 | `focaltech,fts` |
| mainline 驱动 | ✅ `drivers/input/touchscreen/goodix.c` 覆盖 |

> 原厂 DTB 里**没有任何指纹节点**——这台机器没有指纹硬件。

## 传感器

| 类别 | 型号 | mainline 支持 |
|---|---|---|
| 加速度计 | Bosch BMA2x2 | ✅ |
| 光线/距离 | Liteon LTR507 | ⚠ 需确认 |
| 飞行时间 | ST VL6180 | ⚠ 需确认 |

## 原厂系统

| 项目 | 值 |
|---|---|
| Android 版本 | 4.4.x（`BOOTCLASSPATH` 仍用 `core.jar`） |
| 位数 | **32 位**（内核是 ARM32 zImage，magic `0x016f2818`） |
| 内核 | 高通下游 3.10，kernel 区 6,754,072 字节 |
| boot ramdisk | 530,542 字节 |
| boot 分区 QCDT | 4 MiB，12 条 entry，全部指向同一 DTB |

`boot` 分区的 QCDT 条目元数据（`msm8916-mainline` 打包时可直接复用）：

```
entry0: platform_id=0xCE  variant_id=0x0001000B  soc_rev=0x41  ...  offset=0x800  size=0x2A800
12 条覆盖 platform {0xCE, 0xF8, 0xF9, 0xFA} × subtype {0x41, 0x42, 0x88}
```

## 中文标识

机身背面标签：`学生平板 G35S`、`电源 5.5V-2A`、
`采用 Qualcomm 骁龙处理器`、`中山市读书郎电子有限公司`、`CMIIT ID: 2017AP2901`。
