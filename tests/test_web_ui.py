from __future__ import annotations

import tempfile
import unittest
from importlib.resources import files
from pathlib import Path

from PIL import Image

from b360gt.web_ui import (
    CHANNEL_BUSY_MESSAGE,
    PlaybackController,
    _playback_error_message,
)


class WebUiTests(unittest.TestCase):
    def test_selected_media_is_retained_for_page_restore(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "preview.png"
            Image.new("RGB", (64, 48), "green").save(path)
            controller = PlaybackController()

            info = controller.select_media(path, display_name="my-preview.png")
            status = controller.status()

        self.assertEqual(info.kind, "image")
        self.assertEqual(status["media_name"], "my-preview.png")
        self.assertEqual(status["media_info"]["width"], 64)
        self.assertEqual(status["media_info"]["height"], 48)
        self.assertEqual(status["state"], "idle")
        self.assertTrue((controller.selected_preview() or b"").startswith(b"\xff\xd8"))

    def test_external_path_cannot_be_started(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "preview.png"
            Image.new("RGB", (64, 48), "green").save(path)
            controller = PlaybackController()
            controller.select_media(path)

            with self.assertRaises(ValueError):
                controller.start_selected()

    def test_permission_error_is_reported_as_channel_occupancy(self) -> None:
        self.assertEqual(
            _playback_error_message(PermissionError("access denied")),
            CHANNEL_BUSY_MESSAGE,
        )

    def test_page_omits_redundant_heading_and_external_path_controls(self) -> None:
        html = files("b360gt").joinpath("web", "index.html").read_text(encoding="utf-8")
        script = files("b360gt").joinpath("web", "app.js").read_text(encoding="utf-8")

        self.assertNotIn("永久媒体库", html)
        self.assertNotIn("外部路径", html)
        self.assertNotIn('id="pathInput"', html)
        self.assertIn("拖入媒体文件", html)
        self.assertIn("已保存媒体", html)
        self.assertIn("Windows + Linux USB Display Controller", html)
        self.assertNotIn("Valkyrie Linux Display Driver", html)
        self.assertIn('title="点击重新检测"', html)
        self.assertIn('text.textContent = "水冷屏已连接"', script)
        self.assertIn("minimumFeedbackMs = 450", script)
        self.assertIn('text.textContent = "正在检测…"', script)
        self.assertIn('id="screenOverlay"', html)
        self.assertIn("renderScreenOverlay(config, telemetry)", script)
        self.assertIn("仅采集操作系统及显卡厂商只读接口数据", html)
        self.assertIn("仅采集操作系统及显卡厂商只读接口数据", script)
        self.assertIn('id="channelWarning"', html)
        self.assertIn("显示通道为独占资源", html)
        self.assertIn("status.channel_conflicts", script)
        self.assertIn('playing: "媒体显示中"', script)
        self.assertNotIn('playing: "播放中"', script)
        self.assertIn('idle: "未显示内容"', script)
        self.assertIn('<strong id="playbackState">未显示内容</strong>', html)
        self.assertIn("<span>水冷屏状态</span>", html)
        self.assertIn("<span>媒体属性</span>", html)
        self.assertNotIn('id="overlayTemplate"', html)
        self.assertNotIn("config.template", script)
        self.assertNotIn("cpu_temperature_c", script)
        self.assertNotIn("cpu_frequency_mhz", script)
        self.assertNotIn("fan_rpm", script)
        self.assertNotIn("LibreHardwareMonitor", script)
        self.assertNotIn('id="systemTelemetry"', html)
        self.assertNotIn('$("#systemTelemetry")', script)
        self.assertIn("采集 GPU 数据（可能唤醒独显）", html)
        self.assertIn('title="最多每 5 秒查询一次"', html)
        self.assertIn('"媒体切换中"', script)
        self.assertNotIn('"媒体已切换"', script)

    def test_library_list_has_room_for_six_items(self) -> None:
        css = files("b360gt").joinpath("web", "style.css").read_text(encoding="utf-8")

        self.assertIn("max-height: 439px", css)
        self.assertIn("font-size: 13px", css)
        self.assertIn("font: 600 11px/1 ui-monospace, monospace", css)
        self.assertIn("justify-content: center", css)
        self.assertIn("margin: 72px 2px 12px", css)
        self.assertIn(".ghost-button {", css)
        self.assertIn(".monitor-controls {", css)
        self.assertIn("margin-top: 72px", css)
        self.assertIn("position: relative", css)
        self.assertIn("position: absolute", css)
        self.assertIn("top: 2px", css)
        self.assertIn("left: 2px", css)
        self.assertIn("font-size: 12px", css)
        self.assertIn("font-size: 21px", css)
        self.assertIn("font: 700 11px ui-monospace, monospace", css)
        self.assertIn("font: 600 12px/1 ui-monospace, monospace", css)
