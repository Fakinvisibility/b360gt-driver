# Valkyrie B360GT 水冷屏驱动

适用于瓦尔基里 B360GT USB 圆形屏幕的非官方开源用户态驱动。项目可在
Linux 和 Windows 上显示图片、播放动画及视频，并通过仅监听本机的 Web
控制台管理媒体与监控叠加层。

> [!IMPORTANT]
> 本项目与瓦尔基里、Myth.cool 及相关厂商不存在隶属、赞助或背书关系。
> 产品名称和商标仅用于说明兼容性，相关权利归各自权利人所有。

> [!WARNING]
> 这是基于互操作性研究的实验性驱动。请先阅读
> [安全边界与风险说明](docs/safety.md)。程序不会升级固件，也不控制水泵、
> 风扇或 PWM，但未公开协议的实现无法保证零风险。

## 功能

- 自动识别唯一一台 `345F:9132` USB Display；
- 验证 HID 接口 0、显示接口 3 和 Bulk OUT 端点 `0x04`；
- 将图片缩放为 480×480 并编码为设备使用的 UYVY 帧；
- 显示 PNG、JPEG 等静态图片；
- 播放 GIF、APNG、MP4、MOV、MKV 和 WebM；
- 使用浏览器上传、预览、选择和安全删除持久化媒体；
- 叠加 CPU、GPU、内存和温度等监控信息；
- 在 Linux 上通过 systemd 用户服务管理后台控制台；
- 限定 USB/HID 写入范围，不提供任意原始命令或固件升级入口。

## 支持状态

| 环境 | 状态 | 说明 |
| --- | --- | --- |
| Arch Linux x86_64 | 已实机验证 | 提供 PKGBUILD、udev 规则和 systemd 用户服务 |
| Windows | 已实机验证 | 支持虚拟环境和便携版后台入口 |
| 其他 Linux 发行版 | 欢迎测试 | Python 核心可移植，安装与设备权限需要自行适配 |
| 其他 VID/PID 或硬件版本 | 不支持 | 程序只访问 `345F:9132`，描述符不符时会拒绝运行 |

当前发布候选版本为 `1.0.0rc2`。实机已验证静态图、GIF、MP4、Web
控制台和后台服务；项目尚未宣称为稳定版。

## Arch Linux 快速开始

### 1. 获取源码

```bash
git clone https://github.com/Fakinvisibility/b360gt-driver.git
cd b360gt-driver
```

### 2. 构建并安装

```bash
sudo pacman -S --needed \
  base-devel \
  python-build \
  python-installer

bash ./packaging/arch/prepare-source.sh
cd packaging/arch
makepkg -si
```

`makepkg` 会从 Arch 官方仓库解析运行依赖、构建软件包并执行自动测试。

### 3. 验证设备

确保 MythCool 和其他可能占用屏幕的程序已完全退出，然后执行：

```bash
b360gt probe
```

成功时会显示设备总线、地址、接口、端点和最大包长。该命令只读取并验证
USB 描述符，不发送画面。

### 4. 启动控制台

推荐使用后台模式：

```bash
b360gt start
b360gt status
```

在浏览器访问 [http://127.0.0.1:8765/](http://127.0.0.1:8765/)。
使用完毕后：

```bash
b360gt stop
```

也可以使用前台调试模式：

```bash
b360gt ui
```

前台模式会保留终端输出，按 `Ctrl+C` 停止。后台模式由 systemd 管理，应使用
`b360gt stop`。

## 基本命令

发送一张图片 15 秒：

```bash
b360gt send ./test-images/orientation-pattern.png --seconds 15
```

循环播放 GIF 或视频，直到按 `Ctrl+C`：

```bash
b360gt play ./test-images/animation.gif
b360gt play ./test-images/animation.mp4
```

限定播放时间：

```bash
b360gt play ./example.mp4 --seconds 30
```

设置登录后自动启动 Web 控制台：

```bash
systemctl --user enable --now b360gt-ui.service
```

项目还提供 `b360gt.service`，用于循环播放
`~/.config/b360gt/media` 指向的固定媒体。详细配置见
[Arch Linux 安装与硬件测试](docs/arch-linux.md)。

## Windows 开发运行

在 PowerShell 中创建虚拟环境并安装项目：

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

运行控制台：

```powershell
.\.venv\Scripts\python.exe -m b360gt ui
```

日常后台控制：

```powershell
.\.venv\Scripts\Activate.ps1
b360gt start
b360gt status
b360gt stop
```

Windows 后台日志位于
`%LOCALAPPDATA%\b360gt\logs\background.log`。便携版还提供 PATH 添加和移除
脚本。

## 媒体与数据

控制台只监听 `127.0.0.1`，不会直接对局域网或互联网开放。上传媒体默认保存
在：

- Linux：`~/.local/share/b360gt/media`
- Windows：`%LOCALAPPDATA%\b360gt\media`

媒体库会跨重启保留。静态图片最大 50 MiB，动态图片最大 200 MiB；视频最大
256 MiB、最长 15 分钟，源视频上限为 3840×2160、120 FPS。导入完成后必须
至少保留 1 GiB 可用磁盘空间。

不要将 `B360GT_MEDIA_DIR` 指向普通照片或视频目录。控制台只删除由自身创建并
验证过的媒体项目目录。

## 更新

如果是从源码构建的 Arch 包：

```bash
cd /path/to/b360gt-driver
git switch main
git pull
bash ./packaging/arch/prepare-source.sh
cd packaging/arch
makepkg -si
```

升级不会删除 `~/.config/b360gt` 或持久媒体库。正在运行后台控制台时，安装后
执行一次：

```bash
b360gt stop
b360gt start
```

## 常见问题

### `Access denied (insufficient permissions)`

确认软件包已经安装 udev 规则，然后重新触发设备：

```bash
sudo udevadm control --reload
sudo udevadm trigger --subsystem-match=usb
sudo udevadm trigger --subsystem-match=hidraw
```

必要时注销并重新登录。所有正常命令都不应使用 `sudo`。

### 找不到设备

```bash
lsusb -d 345f:9132
b360gt probe
```

检查屏幕 USB 线缆和供电。如果连接了两台同型号设备，程序会因选择不明确而
拒绝运行。

### 端口被占用或存在通道冲突

```bash
b360gt status
journalctl --user -u b360gt-ui.service
```

不要同时运行前台 `b360gt ui`、后台 `b360gt start` 或 MythCool。

### 停止后屏幕回到内置 Logo

这是设备看门狗的正常行为。停止帧传输后，屏幕会短暂黑屏并恢复内置 Logo。

## 开发与贡献

欢迎提交问题、测试其他 Linux 发行版、改善文档、补充测试或实现经过安全审查
的功能。开始前请阅读 [贡献指南](CONTRIBUTING.md)。

基本开发流程：

```bash
git switch main
git pull
git switch -c feature/short-description

python -m venv .venv
./.venv/bin/python -m pip install -e .
./.venv/bin/python -m unittest discover -s tests -v
```

提交 Pull Request 时请说明测试平台、硬件 VID/PID、验证过的命令以及是否进行
了实机测试。不要上传固件、厂商安装包、设备序列号、整机 USB 抓包或其他人的
版权材料。

## 文档

- [Arch Linux 安装与硬件测试](docs/arch-linux.md)
- [安全边界与设备兼容性](docs/safety.md)
- [设备接口](docs/device.md)
- [显示协议](docs/protocol.md)
- [Web UI 行为](docs/ui-behavior.md)
- [监控叠加层](docs/monitoring-overlay.md)

## 互操作性研究说明

协议资料来自对合法持有设备与官方软件之间正常 USB 通信的观察。项目代码为
独立实现，不包含或分发厂商驱动、固件、安装包、密钥或其他专有文件。仓库也
不包含原始整机 USB 抓包、设备序列号或研究机器的硬件报告。

## 许可证

项目代码和随仓库提供的自制测试素材采用 [MIT License](LICENSE)。
