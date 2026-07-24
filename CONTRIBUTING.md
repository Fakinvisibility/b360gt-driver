# 贡献指南

感谢你帮助改善 B360GT 驱动。这个项目会直接与 USB 设备通信，因此代码质量、
可验证性和安全边界与功能本身同样重要。

## 开始之前

- 搜索现有 Issue 和 Pull Request，避免重复工作；
- 对较大的功能或协议变化，建议先创建 Issue 讨论范围；
- 不要提交厂商固件、安装包、密钥或其他专有文件；
- 不要提交设备序列号、整机 USB 抓包或包含无关设备流量的资料；
- 不要扩大支持的 VID/PID、HID 报告或 USB 写入范围而不说明验证依据。

## 开发环境

项目需要 Python 3.10 或更高版本：

```bash
git clone https://github.com/Fakinvisibility/b360gt-driver.git
cd b360gt-driver
python -m venv .venv
./.venv/bin/python -m pip install -e .
```

Windows 请使用：

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

## 分支与提交

从最新的 `main` 创建目标明确的分支：

```bash
git switch main
git pull
git switch -c feature/short-description
```

建议每个提交只处理一组相关修改，并使用清楚的提交说明，例如：

```text
feat: add Linux background UI service
fix: handle missing USB permissions
docs: improve Arch installation guide
test: cover ambiguous device selection
```

不要提交 `.venv`、构建产物、原始抓包或机器本地配置。

## 测试

每次提交前运行：

```bash
./.venv/bin/python -m unittest discover -s tests -v
```

如果修改 Arch 打包：

```bash
bash ./packaging/arch/prepare-source.sh
cd packaging/arch
makepkg
```

涉及 USB、播放或 UI 的修改应在条件允许时进行实机验证。测试时必须确保
MythCool 和其他显示进程已经退出。

## Pull Request

Pull Request 应包含：

- 修改目的和用户可见行为；
- 自动测试结果；
- 操作系统与 Python 版本；
- 涉及硬件时的 VID/PID 和实机验证结果；
- 已知限制、风险或尚未测试的路径；
- UI 变化的截图或简短录屏（如适用）。

维护者可能会要求缩小范围、补测试或进一步说明协议依据。这是保护用户设备和
维持项目可维护性的正常过程。

## 报告问题

Issue 中请提供：

- 操作系统、内核或 Windows 版本；
- 安装方式和 `b360gt` 版本；
- 执行的完整命令；
- 完整错误文本；
- `b360gt probe` 输出；
- 是否同时运行 MythCool 或其他相关软件。

发布日志前请移除用户名、设备序列号、路径中的隐私信息和无关硬件资料。
