from __future__ import annotations

import tempfile
import threading
import unittest
from importlib.resources import files
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from b360gt.media import inspect_media, render_preview_jpeg
from b360gt.web_ui import (
    CHANNEL_BUSY_MESSAGE,
    PlaybackController,
    SwitchableMediaFrames,
    _playback_error_message,
    channel_conflicts,
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
        self.assertEqual(status["selection_revision"], 1)
        self.assertTrue((controller.selected_preview() or b"").startswith(b"\xff\xd8"))

    def test_external_path_cannot_be_started(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "preview.png"
            Image.new("RGB", (64, 48), "green").save(path)
            controller = PlaybackController()
            controller.select_media(path)

            with self.assertRaises(ValueError):
                controller.start_selected()

    def test_cached_library_metadata_avoids_reprocessing_on_select(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "preview.png"
            Image.new("RGB", (64, 48), "green").save(path)
            controller = PlaybackController()
            info = controller.select_media(path)
            preview = controller.selected_preview()

            with (
                patch("b360gt.web_ui.inspect_media") as inspect,
                patch("b360gt.web_ui.render_preview_jpeg") as render,
            ):
                controller.select_media(
                    path,
                    library_id="a" * 32,
                    media_info=info,
                    preview_jpeg=preview,
                )

            inspect.assert_not_called()
            render.assert_not_called()

    def test_switchable_frames_move_directly_to_latest_media(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            first_path = Path(directory) / "first.png"
            second_path = Path(directory) / "second.png"
            Image.new("RGB", (32, 32), "red").save(first_path)
            Image.new("RGB", (32, 32), "blue").save(second_path)
            source = SwitchableMediaFrames(first_path, None)
            frames = iter(source)

            first_frame, _ = next(frames)
            source.switch(second_path)
            second_frame, _ = next(frames)

            self.assertNotEqual(first_frame, second_frame)
            self.assertFalse(source.changed.is_set())

    def test_stopping_frame_source_skips_further_media_decoding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "still.png"
            Image.new("RGB", (32, 32), "red").save(path)
            stop_event = threading.Event()
            source = SwitchableMediaFrames(path, None, stop_event)
            frames = iter(source)
            next(frames)

            stop_event.set()

            with self.assertRaises(StopIteration):
                next(frames)

    def test_channel_conflict_scan_returns_cache_without_blocking(self) -> None:
        with (
            patch(
                "b360gt.web_ui._channel_conflict_cache",
                ["Myth.Cool"],
            ),
            patch(
                "b360gt.web_ui._channel_conflict_refreshing",
                False,
            ),
            patch(
                "b360gt.web_ui._next_channel_conflict_refresh",
                0.0,
            ),
            patch("b360gt.web_ui.threading.Thread") as thread,
        ):
            self.assertEqual(channel_conflicts(), ["Myth.Cool"])

        thread.return_value.start.assert_called_once()

    def test_active_media_switch_reuses_the_playback_thread(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            first_path = Path(directory) / "first.png"
            second_path = Path(directory) / "second.png"
            Image.new("RGB", (32, 32), "red").save(first_path)
            Image.new("RGB", (32, 32), "blue").save(second_path)
            controller = PlaybackController()
            controller.select_media(
                first_path,
                library_id="a" * 32,
            )
            started = threading.Event()

            def hold_usb_session(
                _frames,
                *,
                stop_event,
                progress_callback,
                **_kwargs,
            ):
                progress_callback(1)
                started.set()
                stop_event.wait(2)
                return 1

            with patch("b360gt.web_ui.stream_frames", side_effect=hold_usb_session):
                controller.start_selected()
                self.assertTrue(started.wait(1))
                original_thread = controller._thread
                cached_info = inspect_media(second_path)
                cached_preview = render_preview_jpeg(second_path)

                info, resumed = controller.switch_media(
                    second_path,
                    library_id="b" * 32,
                    media_info=cached_info,
                    preview_jpeg=cached_preview,
                )

                self.assertTrue(resumed)
                self.assertIs(info, cached_info)
                self.assertIs(controller._thread, original_thread)
                self.assertTrue(original_thread is not None and original_thread.is_alive())
                self.assertEqual(controller.status()["library_id"], "b" * 32)
                controller.close()

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
        self.assertIn('id="playbackEnabled"', html)
        self.assertNotIn('id="playbackToggleHint"', html)
        self.assertNotIn('id="startButton"', html)
        self.assertNotIn('id="stopButton"', html)
        self.assertIn('api("/api/playback"', script)
        self.assertIn("playbackUpdatePending", script)
        self.assertIn("mediaSelectionPending", script)
        self.assertNotIn("mediaSelectionQueue", script)
        self.assertIn("MEDIA_SELECTION_DEBOUNCE_MS = 140", script)
        self.assertIn("pendingMediaSelection", script)
        self.assertIn("mediaSelectionInFlight", script)
        self.assertIn("latestSelectionRevision", script)
        self.assertIn('info.kind === "image"', script)
        self.assertIn("`/api/preview?v=", script)
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
        self.assertIn("gap: clamp(18px, 2.8vh, 32px)", css)
        self.assertIn("margin: 0 2px 12px", css)
        self.assertIn(".ghost-button {", css)
        self.assertIn(".monitor-controls {", css)
        self.assertNotIn("margin-top: 72px", css)
        self.assertIn("position: relative", css)
        self.assertIn("position: absolute", css)
        self.assertIn("top: 2px", css)
        self.assertIn("left: 2px", css)
        self.assertIn("font-size: 12px", css)
        self.assertIn("font-size: 21px", css)
        self.assertIn("font: 700 11px ui-monospace, monospace", css)
        self.assertIn("font: 600 12px/1 ui-monospace, monospace", css)
