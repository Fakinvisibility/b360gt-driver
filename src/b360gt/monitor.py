"""Read-only host telemetry collection and 480x480 dashboard overlays."""

from __future__ import annotations

import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

POSITIONS = {"top-left", "top-right", "bottom-left", "bottom-right"}
REFRESH_RATES = {0.5, 1.0, 2.0, 5.0}
GPU_REFRESH_SECONDS = 5.0


@dataclass(frozen=True)
class OverlayConfig:
    enabled: bool = True
    gpu_enabled: bool = True
    position: str = "top-left"
    refresh_seconds: float = 1.0

    @classmethod
    def parse(cls, value: dict[str, Any]) -> "OverlayConfig":
        config = cls(
            enabled=bool(value.get("enabled", True)),
            gpu_enabled=bool(value.get("gpu_enabled", True)),
            position=str(value.get("position", "top-left")),
            refresh_seconds=float(value.get("refresh_seconds", 1.0)),
        )
        if config.position not in POSITIONS:
            raise ValueError("未知数据显示位置")
        if config.refresh_seconds not in REFRESH_RATES:
            raise ValueError("刷新频率仅支持 0.5、1、2 或 5 秒")
        return config


@dataclass
class Telemetry:
    cpu_percent: float | None = None
    gpu_percent: float | None = None
    gpu_temperature_c: float | None = None
    memory_percent: float | None = None
    disk_percent: float | None = None
    network_up_bps: float | None = None
    network_down_bps: float | None = None
    sources: dict[str, str] = field(default_factory=dict)
    sampled_at: float = 0.0


class ReadOnlyMonitor:
    """Collect telemetry without opening device-control interfaces."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last_network: tuple[float, int, int] | None = None
        self._gpu_cache: tuple[float | None, float | None, str | None] = (
            None,
            None,
            None,
        )
        self._next_gpu_sample = 0.0
    def sample(self, *, include_gpu: bool = True) -> Telemetry:
        import psutil

        now = time.time()
        network = psutil.net_io_counters()
        up = down = None
        with self._lock:
            if self._last_network is not None:
                previous_time, previous_sent, previous_recv = self._last_network
                elapsed = max(now - previous_time, 0.001)
                up = max(0.0, (network.bytes_sent - previous_sent) / elapsed)
                down = max(0.0, (network.bytes_recv - previous_recv) / elapsed)
            self._last_network = (now, network.bytes_sent, network.bytes_recv)

        disk_root = Path.cwd().anchor or "/"
        gpu_use, gpu_temp, gpu_source = self._sample_gpu(include_gpu=include_gpu)
        sources = {
            "cpu_percent": "psutil",
            "memory_percent": "psutil",
            "disk_percent": "psutil",
            "network": "psutil",
        }
        if not include_gpu:
            sources["gpu"] = "disabled"
        elif gpu_source:
            sources["gpu"] = gpu_source
        return Telemetry(
            # A short interval is intentional: interval=None keeps baselines
            # per calling thread, while ThreadingHTTPServer may sample from a
            # new thread each time and would therefore repeatedly report 0%.
            cpu_percent=float(psutil.cpu_percent(interval=0.05)),
            gpu_percent=gpu_use,
            gpu_temperature_c=gpu_temp,
            memory_percent=float(psutil.virtual_memory().percent),
            disk_percent=float(psutil.disk_usage(disk_root).percent),
            network_up_bps=up,
            network_down_bps=down,
            sources=sources,
            sampled_at=now,
        )

    def _sample_gpu(
        self, *, include_gpu: bool
    ) -> tuple[float | None, float | None, str | None]:
        if not include_gpu:
            with self._lock:
                self._gpu_cache = (None, None, None)
                self._next_gpu_sample = 0.0
            return None, None, None

        now = time.monotonic()
        with self._lock:
            if now < self._next_gpu_sample:
                return self._gpu_cache
            # Reserve the interval before querying so concurrent preview and
            # playback threads cannot launch duplicate nvidia-smi processes.
            self._next_gpu_sample = now + GPU_REFRESH_SECONDS
        sample = _gpu_metrics()
        with self._lock:
            self._gpu_cache = sample
        return sample

def _gpu_metrics() -> tuple[float | None, float | None, str | None]:
    usage, temperature = _nvidia_metrics()
    if usage is not None or temperature is not None:
        return usage, temperature, "nvidia-smi (read-only query)"
    if sys.platform.startswith("linux"):
        usage, temperature = _linux_drm_metrics()
        if usage is not None or temperature is not None:
            return usage, temperature, "Linux DRM/hwmon sysfs (read-only)"
    return None, None, None


def _nvidia_metrics() -> tuple[float | None, float | None]:
    """Use NVIDIA's read-only query command when it is already installed."""
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu,temperature.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=1.5,
            check=False,
            shell=False,
            creationflags=(
                getattr(subprocess, "CREATE_NO_WINDOW", 0)
                if sys.platform == "win32"
                else 0
            ),
        )
        first = result.stdout.splitlines()[0].split(",")
        return float(first[0].strip()), float(first[1].strip())
    except (FileNotFoundError, IndexError, ValueError, subprocess.SubprocessError):
        return None, None


def _linux_drm_metrics(
    drm_root: Path = Path("/sys/class/drm"),
) -> tuple[float | None, float | None]:
    """Read the first GPU exposed by Linux DRM/hwmon, without writing sysfs."""
    if not drm_root.is_dir():
        return None, None
    for card in sorted(drm_root.glob("card[0-9]*")):
        device = card / "device"
        if not device.is_dir():
            continue
        usage = _read_number(device / "gpu_busy_percent")
        temperatures: list[float] = []
        for path in device.glob("hwmon/hwmon*/temp*_input"):
            value = _read_number(path)
            if value is not None:
                temperatures.append(value / 1000.0 if value > 1000 else value)
        temperature = max(temperatures) if temperatures else None
        if usage is not None or temperature is not None:
            return usage, temperature
    return None, None


def _read_number(path: Path) -> float | None:
    try:
        return float(path.read_text(encoding="ascii").strip())
    except (OSError, UnicodeError, ValueError):
        return None


class OverlayRenderer:
    def __init__(self, config: OverlayConfig | None = None) -> None:
        self._lock = threading.Lock()
        self._config = config or OverlayConfig()
        self._monitor = ReadOnlyMonitor()
        self._telemetry = Telemetry()
        self._next_sample = 0.0

    def config(self) -> dict[str, Any]:
        with self._lock:
            return asdict(self._config)

    def configure(self, value: dict[str, Any]) -> dict[str, Any]:
        config = OverlayConfig.parse(value)
        with self._lock:
            self._config = config
            self._next_sample = 0.0
        return asdict(config)

    def snapshot(self) -> dict[str, Any]:
        self._refresh_if_due()
        with self._lock:
            return asdict(self._telemetry)

    def apply(self, image: Image.Image) -> Image.Image:
        with self._lock:
            config = self._config
        if not config.enabled:
            return image
        self._refresh_if_due()
        with self._lock:
            telemetry = self._telemetry
        return render_overlay(image, telemetry, config)

    def _refresh_if_due(self) -> None:
        now = time.monotonic()
        with self._lock:
            if now < self._next_sample:
                return
            interval = self._config.refresh_seconds
            self._next_sample = now + interval
        with self._lock:
            include_gpu = self._config.gpu_enabled
        sample = self._monitor.sample(include_gpu=include_gpu)
        with self._lock:
            self._telemetry = sample


def render_overlay(
    image: Image.Image, telemetry: Telemetry, config: OverlayConfig
) -> Image.Image:
    canvas = image.convert("RGBA")
    lines = _dashboard_lines(telemetry)
    font = ImageFont.load_default(size=16)
    line_height = 22
    width = max(205, max(font.getlength(line) for line in lines) + 28)
    height = len(lines) * line_height + 24
    margin = 18
    x = margin if config.position.endswith("left") else canvas.width - width - margin
    y = margin if config.position.startswith("top") else canvas.height - height - margin
    # Keep the backing image transparent. Initializing it with the panel
    # colour would leave a translucent rectangle outside the rounded corners.
    panel = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    panel_draw = ImageDraw.Draw(panel)
    panel_draw.rounded_rectangle(
        (0, 0, width - 1, height - 1),
        radius=14,
        fill=(5, 10, 15, 210),
        outline=(104, 240, 194, 180),
        width=2,
    )
    for index, line in enumerate(lines):
        panel_draw.text((14, 12 + index * line_height), line, font=font, fill="white")
    canvas.alpha_composite(panel, (int(x), int(y)))
    return canvas.convert("RGB")


def _dashboard_lines(value: Telemetry) -> list[str]:
    fmt = lambda number, suffix: "N/A" if number is None else f"{number:.0f}{suffix}"
    return [
        f"CPU {fmt(value.cpu_percent, '%')}",
        f"GPU {fmt(value.gpu_percent, '%')}  {fmt(value.gpu_temperature_c, '°C')}",
        f"RAM {fmt(value.memory_percent, '%')}  DISK {fmt(value.disk_percent, '%')}",
        f"NET ↓{_rate(value.network_down_bps)} ↑{_rate(value.network_up_bps)}",
    ]


def _rate(value: float | None) -> str:
    if value is None:
        return "N/A"
    if value >= 1024 * 1024:
        return f"{value / 1024 / 1024:.1f}M/s"
    return f"{value / 1024:.0f}K/s"
