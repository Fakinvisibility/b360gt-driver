# 只读系统监控叠加层

监控叠加层在媒体帧完成裁切后、编码为 USB 显示帧前合成，因此原有图片、
GIF/APNG 和视频播放模式保持不变。关闭叠加层时不会改变媒体画面。

可显示 CPU 使用率、GPU 使用率与温度，以及内存、磁盘和网络状态。CPU 温度、
CPU 频率和风扇转速不采集、不显示。

## 数据来源与跨平台行为

| 指标 | Windows | Linux |
|---|---|---|
| CPU 使用率 | `psutil`（Windows 性能计数器） | `psutil`（`/proc`、内核 CPU 统计） |
| GPU 使用率、温度（NVIDIA） | `nvidia-smi` 只读查询 | 优先 `nvidia-smi` 只读查询 |
| GPU 使用率、温度（AMD/Intel） | 当前无稳定的通用来源，显示 `N/A` | `/sys/class/drm/card*/device/gpu_busy_percent` 与 hwmon |
| 内存、磁盘、网络 | `psutil` | `psutil`（`/proc`、文件系统统计） |

Linux 能否读到 GPU 使用率和温度，取决于内核驱动是否向 DRM/hwmon sysfs
公开相应节点，以及运行用户是否有读取权限。采集器不会提升权限、加载内核模块
或尝试绕过权限。接口未提供时返回 `N/A`，不影响媒体播放。

项目不依赖 LibreHardwareMonitor 或其他第三方主板传感器服务。控制台采用单一
仪表盘布局，支持左上/右上/左下/右下位置以及 0.5、1、2、5 秒刷新周期。

GPU 采集与画面刷新解耦：无论画面刷新多快，`nvidia-smi` 或 Linux DRM
GPU 查询最多每 5 秒执行一次，其间复用缓存。控制台提供独立的“采集 GPU 数据”
开关；关闭后不会执行 GPU 查询。由于只读查询仍可能让独显短暂退出低功耗状态，
界面会明确提示这一点。

## 安全边界

- 采集器只读取 `psutil` 暴露的系统统计信息。
- NVIDIA 数据仅通过 `nvidia-smi --query-gpu` 查询。
- Linux AMD/Intel GPU 仅读取 DRM/hwmon sysfs 文件。
- 不读取 CPU 温度、CPU 频率或风扇转速。
- 不提供水泵、风扇、PWM、目标 RPM、固件升级或任意设备写入接口。
- USB 写入仍只用于已验证的 B360GT 屏幕初始化和显示帧传输。
