from __future__ import annotations

import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from b360gt.monitor import (
    OverlayConfig,
    ReadOnlyMonitor,
    Telemetry,
    _linux_drm_metrics,
    _nvidia_metrics,
    render_overlay,
)


class MonitorTests(unittest.TestCase):
    def test_config_rejects_unknown_position_and_refresh(self) -> None:
        with self.assertRaises(ValueError):
            OverlayConfig.parse({"position": "center"})
        with self.assertRaises(ValueError):
            OverlayConfig.parse({"refresh_seconds": 0.01})

    def test_overlay_preserves_display_dimensions(self) -> None:
        image = Image.new("RGB", (480, 480), "navy")
        telemetry = Telemetry(
            cpu_percent=25,
            memory_percent=50,
            disk_percent=33,
        )
        result = render_overlay(
            image,
            telemetry,
            OverlayConfig(enabled=True, position="bottom-right"),
        )
        self.assertEqual(result.size, (480, 480))
        self.assertEqual(result.mode, "RGB")
        self.assertNotEqual(result.getpixel((455, 455)), image.getpixel((455, 455)))

    def test_overlay_keeps_pixels_outside_rounded_corners_transparent(self) -> None:
        image = Image.new("RGB", (480, 480), (12, 34, 56))
        result = render_overlay(
            image,
            Telemetry(cpu_percent=25),
            OverlayConfig(enabled=True, position="top-left"),
        )

        # Panel starts at margin (18, 18); its exact top-left corner is
        # outside the rounded shape and must retain the source image.
        self.assertEqual(result.getpixel((18, 18)), (12, 34, 56))
        self.assertNotEqual(result.getpixel((32, 32)), (12, 34, 56))

    def test_contract_contains_no_control_fields(self) -> None:
        keys = Telemetry().__dict__.keys()
        forbidden = {
            "pump",
            "pwm",
            "target_rpm",
            "firmware",
            "cpu_temperature_c",
            "cpu_frequency_mhz",
            "fan_rpm",
            "sensor_backend_status",
        }
        self.assertTrue(forbidden.isdisjoint(keys))

    def test_linux_drm_metrics_are_read_from_sysfs_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            device = root / "card0" / "device"
            hwmon = device / "hwmon" / "hwmon0"
            hwmon.mkdir(parents=True)
            (device / "gpu_busy_percent").write_text("37\n", encoding="ascii")
            (hwmon / "temp1_input").write_text("46500\n", encoding="ascii")

            usage, temperature = _linux_drm_metrics(root)

        self.assertEqual(usage, 37)
        self.assertEqual(temperature, 46.5)

    def test_gpu_query_is_cached_and_can_be_disabled(self) -> None:
        monitor = ReadOnlyMonitor()
        with patch(
            "b360gt.monitor._gpu_metrics",
            return_value=(12.0, 44.0, "test GPU"),
        ) as query:
            first = monitor._sample_gpu(include_gpu=True)
            second = monitor._sample_gpu(include_gpu=True)
            disabled = monitor._sample_gpu(include_gpu=False)

        self.assertEqual(first, second)
        self.assertEqual(query.call_count, 1)
        self.assertEqual(disabled, (None, None, None))

    def test_nvidia_query_never_opens_a_windows_console(self) -> None:
        completed = type(
            "Completed",
            (),
            {"stdout": "12, 44\n"},
        )()
        with (
            patch("b360gt.monitor.sys.platform", "win32"),
            patch(
                "b360gt.monitor.subprocess.CREATE_NO_WINDOW",
                0x08000000,
                create=True,
            ),
            patch(
                "b360gt.monitor.subprocess.run",
                return_value=completed,
            ) as run,
        ):
            self.assertEqual(_nvidia_metrics(), (12.0, 44.0))

        self.assertEqual(
            run.call_args.kwargs["creationflags"],
            0x08000000,
        )
