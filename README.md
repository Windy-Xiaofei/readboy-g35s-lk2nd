# readboy-g35s-lk2nd

为 **读书郎 ReadBoy G35S**（高通 MSM8916 / 骁龙 410，8" 800×1280）构建 `lk2nd.img`。

用 GitHub Actions 编译，本机不需要任何 Linux 环境，只需要 `git`。

---

## 这套东西是干什么的

G35S 目前的 `boot` 分区里是损坏的镜像（内核是原厂的，但 DTB 被换成了展锐的）。
`lk2nd` 是一个二级引导器，被打包成标准 Android boot 镜像刷进 `boot` 分区，
由原厂引导器加载，然后提供一个**通用的 fastboot 接口**。

有了 fastboot，后面刷内核、刷 rootfs 就都是标准流程了。

---

## 使用方法

### 1. 在 GitHub 上建一个空仓库

名字随意，比如 `readboy-g35s-lk2nd`。
**不要勾选** "Add a README file" / .gitignore / license，要一个全新空仓库。

### 2. 本地推送

目标仓库：<https://github.com/Windy-Xiaofei/readboy-g35s-lk2nd>

这个目录已经 `git init`、`git add` 并配好 `origin` 了，只差一次 commit + push。

先确认 git 身份（本机还没配，只需一次）：

```bash
git config --global user.name  "Windy-Xiaofei"
git config --global user.email "你的邮箱"
```

然后：

```bash
cd /d/ReadBoyG35S/gh/lk2nd-build
git commit -m "lk2nd device tree for ReadBoy G35S (MSM8916)"
git push -u origin main
```

> `git push` 会通过 Git Credential Manager 弹出浏览器让你登录 GitHub 授权，
> 登录一次之后就会记住。不需要手动生成 token。

> 推送时会要求认证。用 **Personal Access Token** 当密码（GitHub 已不支持账号密码），
> 或者提前配置好 SSH / Git Credential Manager。

### 3. 等 CI 跑完

打开仓库页面的 **Actions** 标签，会看到 `Build lk2nd for ReadBoy G35S` 正在跑，
大约 2–4 分钟。

成功后进入这次 run 的页面，最下方 **Artifacts** 里下载：

```
lk2nd-msm8916-readboy-g35s.zip
```

解压得到 `lk2nd.img`（应该在 100–300 KB 之间）。

### 4. 把 lk2nd.img 拿回来

放到 `D:\ReadBoyG35S\gh\` 下面，告诉我路径，我来做下一步。

---

## 仓库结构

```
.
├── .github/workflows/build.yml           CI：克隆 lk2nd 上游 → 注入设备树 → 编译
└── device/
    └── msm8916-readboy-g35s.dts          设备树（第一版，最小化）
```

CI 做的事：

1. `git clone https://github.com/msm8916-mainline/lk2nd`
2. 把 `device/msm8916-readboy-g35s.dts` 拷进 `lk2nd/device/dts/msm8916/`
3. 往同目录 `rules.mk` 的 `QCDTBS` 列表追加一条
4. `make TOOLCHAIN_PREFIX=arm-none-eabi- lk2nd-msm8916`
5. 上传 `build-lk2nd-msm8916/lk2nd.img`

---

## 第一版 DTS 为什么这么简单

```dts
qcom,msm-id   = <0xce 0x0>, <0xf8 0x0>, <0xf9 0x0>, <0xfa 0x0>;
qcom,board-id = <0x1000b 0x41>, <0x1000b 0x42>, <0x1000b 0x88>;
```

这两个值是从原厂 DTB 里逐字节抄出来的，用于让 lk2nd 认出这台机器。

**刻意没写** `lk2nd,match-panel` 和 `lk2nd,dtb-files`：

- `match-panel` 要求面板节点名与 lk2nd 显示驱动里的 ID 完全一致。
  原厂用的是 `qcom,mdss_dsi_video_kd080d34` 这类名字，lk2nd 现有设备用的是
  `qcom,mdss_dsi_nt35521_800x1280_video` 这类名字，**对不上**。
  名字写错会导致 lk2nd 启动失败。
- 第一阶段的目标是「lk2nd 能起来 + fastboot 可用」，屏幕亮不亮不影响刷机。

面板支持留到第二阶段，等确认 lk2nd 能跑起来再加。

---

## 如果失败了

| 现象 | 原因 | 处理 |
|---|---|---|
| `make: *** No rule to make target 'lk2nd-msm8916'` | 目标名变了 | 看 lk2nd 仓库 `.github/workflows/lk2nd.yml` 里的 `project-platform` |
| `dtc` 报语法错 | DTS 写错 | 把报错发我，我改 |
| `arm-none-eabi-gcc: not found` | apt 包没装上 | 看 "Install build dependencies" 步骤日志 |
| Upload 步骤报 action 版本不支持 | v4 被弃用 | 把 `@v4` 改成 `@v7`（上游 CI 用的是 v7） |
| 编译通过但 `lk2nd.img` 缺失 | 输出目录名不对 | 检查 `build-lk2nd-msm8916/` 是否存在 |

把失败那一步的日志贴给我就行。

---

## 后续（第二阶段）

拿到可用的 fastboot 之后：

1. 用 UMS 通道把 `lk2nd.img` 写进 `boot` 分区起始位置
2. 重启，设备应以 fastboot 设备出现（`VID_18D1&PID_4EE0`，Google 驱动直接支持）
3. 然后才处理内核 + 面板 + rootfs

⚠ 注意：刷入 lk2nd 会改变设备当前"启动失败回落到 9006/UMS"的行为。
写之前我们已经有整盘备份和原厂 `boot.img`，可以回滚。
