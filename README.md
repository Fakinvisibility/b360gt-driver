# 瓦尔基里 B360GT Linux 屏幕驱动（实验性）

> [!IMPORTANT]
> 这是独立开发的非官方开源项目，与瓦尔基里、Myth.cool 及相关厂商不存在
> 隶属、赞助或背书关系。产品名称和商标仅用于说明兼容性，相关权利归各自
> 权利人所有。

当前已经在 Windows 上完成第一阶段协议验证：

- 识别 `345F:9132` 的屏幕设备；
- 通过 HID 接口 0 执行已抓包验证的正常屏幕初始化；
- 将图片缩放为 480×480 并编码为 UYVY；
- 通过接口 3、Bulk OUT 端点 `0x04` 持续显示图片。
- 使用 Pillow 播放 GIF/APNG，使用 PyAV 播放 MP4/WebM 等视频。

本项目不会发送固件升级流量，也不会访问其他 VID/PID。

## 互操作性研究说明

协议资料来自对合法持有设备与官方软件之间正常 USB 通信的观察。项目代码为
独立实现，不包含或分发厂商驱动、固件、安装包、密钥或其他专有文件。仓库也
不包含原始整机 USB 抓包、设备序列号或研究机器的硬件报告。

本软件按 MIT 许可证以“原样”提供，不附带任何明示或暗示的担保。使用实验性
驱动存在设备异常、显示中断或数据丢失等风险，请先阅读
[`docs/safety.md`](docs/safety.md)。

## Windows 验证命令

以下命令会持续运行并显示图片；需要停止时，请在终端按 `Ctrl+C`：

```powershell
.\.venv\Scripts\python.exe -m b360gt send .\test-images\orientation-pattern.png
```

限定时间和帧率：

```powershell
.\.venv\Scripts\python.exe -m b360gt send .\test-images\orientation-pattern.png --seconds 15 --fps 2
```

循环播放 GIF 或视频，直到按 `Ctrl+C`：

```powershell
.\.venv\Scripts\python.exe -m b360gt play .\test-images\animation.gif
.\.venv\Scripts\python.exe -m b360gt play .\test-images\animation.mp4
```

也可以限定播放时间：

```powershell
.\.venv\Scripts\python.exe -m b360gt play .\example.mp4 --seconds 30
```

启动本机图形控制台：

```powershell
.\.venv\Scripts\python.exe -m b360gt ui
```

Windows 日常使用可启动无终端窗口、不会自动打开浏览器的后台入口：

```powershell
.\.venv\Scripts\b360gt-background.exe
```

For everyday use, activate the virtual environment once and use the short
service commands:

```powershell
.\.venv\Scripts\Activate.ps1
b360gt start
b360gt status
b360gt stop
```

`b360gt stop` shuts down gracefully, including playback and USB cleanup.

The Windows portable release also includes `添加到命令行PATH.cmd` and
`从命令行PATH移除.cmd`. Adding the portable directory to the current user's
PATH is optional and does not require administrator privileges. Open a new
PowerShell window after adding or removing it.

启动后可关闭 PowerShell，随后手动访问
[`http://127.0.0.1:8765/`](http://127.0.0.1:8765/)。后台错误日志保存在
`%LOCALAPPDATA%\b360gt\logs\background.log`。安装新版本后需要重新执行
`python -m pip install -e .`，以更新后台入口。

控制台只监听 `127.0.0.1`，支持永久媒体库、拖放上传与安全删除，可在播放中
直接切换图片、GIF、MP4/WebM。视频预览由后端解码为动态画面，不依赖浏览器
是否支持源视频编码。

媒体导入按实际探测和解码结果校验，而不是信任扩展名。静态图片最大 50 MiB，
动态图片最大 200 MiB；视频最大 256 MiB、最长 15 分钟，仅允许
MP4/MOV/MKV/WebM，源视频最大 3840×2160（8,294,400 像素）和 120 FPS。
导入完成后必须至少保留 1 GiB 可用磁盘空间。

Myth.cool 必须完全退出（包括后台进程），否则两个程序会争用屏幕。
发送进程停止后，屏幕会先黑屏再回到内置 Logo；这是设备看门狗的正常行为。

## 当前进度

第一阶段“显示图片”和第二阶段“播放 GIF/视频”的核心功能均已在实机
验证成功。Arch Linux 的 udev 权限、原生软件包和 systemd 用户服务也已
准备好；安装与首次实机测试见 [`docs/arch-linux.md`](docs/arch-linux.md)。

USB 写入边界、同型号自动识别方式和残余风险见
[`docs/safety.md`](docs/safety.md)。

UI 媒体识别、自动帧率和预览恢复规则见
[`docs/ui-behavior.md`](docs/ui-behavior.md)。

## 测试素材

`test-images/` 中的纯色图、方向图、GIF 和 MP4 均由本项目
`tools/generate_test_images.ps1`、`tools/generate_demo_gif.py` 和
`tools/generate_demo_video.py` 生成，可用于功能测试。

## 许可证

项目代码和随仓库提供的自制测试素材采用 [MIT License](LICENSE)。
