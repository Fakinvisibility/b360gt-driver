"""Local-only browser control panel for the B360GT display."""

from __future__ import annotations

import json
import logging
import mimetypes
import os
import re
import signal
import threading
import tempfile
import time
import urllib.parse
import uuid
import webbrowser
from dataclasses import asdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from typing import Any

import psutil
import usb.core

from .library import MediaLibrary
from .media import (
    MediaInfo,
    inspect_media,
    iter_media_frames,
    iter_video_preview_jpegs,
    render_preview_jpeg,
)
from .media_policy import MAX_VIDEO_SIZE
from .monitor import OverlayConfig, OverlayRenderer
from .usb_transport import DeviceSafetyError, probe, stream_frames

MAX_UPLOAD_SIZE = MAX_VIDEO_SIZE
UPLOAD_CHUNK_SIZE = 1024 * 1024
DISPLAY_KEEPALIVE_RATE = 2.0
AUTO_RESUME_RETRY_INITIAL_SECONDS = 1.0
AUTO_RESUME_RETRY_MAX_SECONDS = 30.0
CHANNEL_BUSY_MESSAGE = (
    "显示通道已被其他程序占用；请关闭 Myth.Cool 或其他 B360GT 后端后重试"
)
CHANNEL_PERMISSION_MESSAGE = (
    "暂时没有权限访问显示设备；系统可能仍在初始化设备权限"
)
DEVICE_NOT_READY_MESSAGE = "暂时找不到水冷屏；请检查 USB 连接"
logger = logging.getLogger(__name__)
CHANNEL_CONFLICT_REFRESH_SECONDS = 3.0
_channel_conflict_lock = threading.Lock()
_channel_conflict_cache: list[str] = []
_channel_conflict_refreshing = False
_next_channel_conflict_refresh = 0.0


def _scan_channel_conflicts() -> list[str]:
    conflicts: set[str] = set()
    current_pid = os.getpid()
    own_processes = {current_pid}
    try:
        own_processes.update(parent.pid for parent in psutil.Process().parents())
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        pass
    for process in psutil.process_iter(("pid", "name", "cmdline")):
        try:
            if process.info["pid"] in own_processes:
                continue
            name = str(process.info.get("name") or "")
            command = " ".join(process.info.get("cmdline") or [])
        except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
            continue
        if name.casefold() in {"mythcool.exe", "mythcoollauncher.exe"}:
            conflicts.add("Myth.Cool")
        elif (
            ("python" in name.casefold() or name.casefold().startswith("b360gt"))
            and (
                "b360gt-ui" in command.casefold()
                or (
                    "b360gt" in command.casefold()
                    and (
                        " ui" in command.casefold()
                        or "web_ui" in command.casefold()
                    )
                )
            )
        ):
            conflicts.add("另一个 B360GT 后端")
    return sorted(conflicts)


def _refresh_channel_conflicts() -> None:
    global _channel_conflict_cache, _channel_conflict_refreshing
    try:
        conflicts = _scan_channel_conflicts()
    finally:
        with _channel_conflict_lock:
            if "conflicts" in locals():
                _channel_conflict_cache = conflicts
            _channel_conflict_refreshing = False


def channel_conflicts() -> list[str]:
    """Return cached conflicts and refresh the slow Windows scan in background."""
    global _channel_conflict_refreshing, _next_channel_conflict_refresh
    now = time.monotonic()
    with _channel_conflict_lock:
        if (
            now >= _next_channel_conflict_refresh
            and not _channel_conflict_refreshing
        ):
            _channel_conflict_refreshing = True
            _next_channel_conflict_refresh = (
                now + CHANNEL_CONFLICT_REFRESH_SECONDS
            )
            threading.Thread(
                target=_refresh_channel_conflicts,
                name="b360gt-channel-conflicts",
                daemon=True,
            ).start()
        return list(_channel_conflict_cache)


def _playback_error_message(exc: Exception) -> str:
    text = str(exc).casefold()
    if isinstance(exc, PermissionError) or any(
        token in text for token in ("access", "denied", "permission")
    ):
        return CHANNEL_PERMISSION_MESSAGE
    if any(token in text for token in ("not found", "found 0")):
        return DEVICE_NOT_READY_MESSAGE
    if isinstance(exc, usb.core.USBError) and any(
        token in text for token in ("busy", "claim_interface", "resource")
    ):
        return CHANNEL_BUSY_MESSAGE
    return f"{type(exc).__name__}: {exc}"


def _is_retryable_display_error(exc: Exception) -> bool:
    """Return whether an automatic resume may succeed after devices settle."""
    if isinstance(exc, (PermissionError, DeviceSafetyError, usb.core.USBError)):
        return True
    if type(exc).__module__.partition(".")[0] == "hid":
        return True
    text = str(exc).casefold()
    return any(
        token in text
        for token in (
            "access",
            "busy",
            "claim_interface",
            "denied",
            "found 0",
            "not found",
            "permission",
            "resource",
        )
    )


def _upload_directory() -> Path:
    configured = os.environ.get("B360GT_UPLOAD_DIR")
    root = Path(configured) if configured else Path(tempfile.gettempdir())
    directory = root / "b360gt-uploads"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


class SwitchableMediaFrames:
    """Yield frames from the latest media without reopening the USB session."""

    def __init__(
        self,
        media: str | Path,
        image_transform,
        stop_event: threading.Event | None = None,
    ) -> None:
        self._lock = threading.Lock()
        self._path = Path(media).resolve()
        self._revision = 0
        self._image_transform = image_transform
        self._stop_event = stop_event
        self.changed = threading.Event()

    def switch(self, media: str | Path) -> None:
        path = Path(media).resolve()
        with self._lock:
            self._path = path
            self._revision += 1
            self.changed.set()

    def __iter__(self):
        while True:
            with self._lock:
                path = self._path
                revision = self._revision
                self.changed.clear()
            frames = iter_media_frames(
                path,
                loop=True,
                image_transform=self._image_transform,
            )
            iterator = iter(frames)
            while True:
                if self._stop_event is not None and self._stop_event.is_set():
                    return
                with self._lock:
                    if revision != self._revision:
                        break
                try:
                    frame = next(iterator)
                except StopIteration:
                    break
                yield frame


class PlaybackController:
    def __init__(self, overlay: OverlayRenderer | None = None) -> None:
        self._lock = threading.Lock()
        self._stop_event: threading.Event | None = None
        self._thread: threading.Thread | None = None
        self._frame_source: SwitchableMediaFrames | None = None
        self._preview_jpeg: bytes | None = None
        self.overlay = overlay or OverlayRenderer()
        self._status: dict[str, Any] = {
            "state": "idle",
            "media": None,
            "media_name": None,
            "media_info": None,
            "library_id": None,
            "selection_revision": 0,
            "bytes_streamed": 0,
            "error": None,
        }

    def status(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._status)

    def select_media(
        self,
        media: str | Path,
        *,
        display_name: str | None = None,
        library_id: str | None = None,
        media_info: MediaInfo | None = None,
        preview_jpeg: bytes | None = None,
    ) -> MediaInfo:
        path = Path(media).expanduser().resolve()
        if not path.is_file():
            raise ValueError(f"找不到媒体文件：{path}")
        info = media_info or inspect_media(path)
        prepared_preview = (
            preview_jpeg if preview_jpeg is not None else render_preview_jpeg(path)
        )

        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                raise RuntimeError("屏幕正在播放，请先停止当前任务")
            selection_revision = int(
                self._status.get("selection_revision", 0)
            ) + 1
            self._status.update(
                {
                    "media": str(path),
                    "media_name": display_name or path.name,
                    "media_info": asdict(info),
                    "library_id": library_id,
                    "selection_revision": selection_revision,
                    "bytes_streamed": 0,
                    "error": None,
                }
            )
            self._preview_jpeg = prepared_preview
        return info

    def selected_media(self) -> Path | None:
        with self._lock:
            media = self._status.get("media")
        if not media:
            return None
        path = Path(media)
        return path if path.is_file() else None

    def selected_preview(self) -> bytes | None:
        with self._lock:
            return self._preview_jpeg

    def start(
        self,
        media: str,
        *,
        retry_transient_errors: bool = True,
    ) -> None:
        path = Path(media).expanduser().resolve()

        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                raise RuntimeError("屏幕正在播放，请先停止当前任务")
            previous_media = self._status.get("media")
            previous_name = self._status.get("media_name")
            previous_library_id = self._status.get("library_id")
            selection_revision = int(
                self._status.get("selection_revision", 0)
            )
            previous_info = self._status.get("media_info")
            if previous_media == str(path) and isinstance(previous_info, dict):
                info = MediaInfo(**previous_info)
                preview_jpeg = self._preview_jpeg
            else:
                info = None
                preview_jpeg = None

        if info is None:
            info = inspect_media(path)
        if preview_jpeg is None:
            preview_jpeg = render_preview_jpeg(path)

        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                raise RuntimeError("屏幕正在播放，请先停止当前任务")
            stop_event = threading.Event()
            frame_source = SwitchableMediaFrames(
                path,
                self.overlay.apply,
                stop_event,
            )
            self._stop_event = stop_event
            self._frame_source = frame_source
            self._status = {
                "state": "starting",
                "media": str(path),
                "media_name": (
                    previous_name
                    if previous_media == str(path) and previous_name
                    else path.name
                ),
                "media_info": asdict(info),
                "library_id": (
                    previous_library_id if previous_media == str(path) else None
                ),
                "selection_revision": selection_revision,
                "bytes_streamed": 0,
                "error": None,
            }
            self._preview_jpeg = preview_jpeg
            self._thread = threading.Thread(
                target=self._play_worker,
                args=(frame_source, stop_event, retry_transient_errors),
                name="b360gt-playback",
                daemon=True,
            )
            self._thread.start()

    def start_selected(self, *, retry_transient_errors: bool = True) -> None:
        with self._lock:
            media = self._status.get("media")
            library_id = self._status.get("library_id")
        if not media or not library_id:
            raise ValueError("请先从媒体库选择或上传文件")
        self.start(
            str(media),
            retry_transient_errors=retry_transient_errors,
        )

    def switch_media(
        self,
        media: str | Path,
        *,
        display_name: str | None = None,
        library_id: str | None = None,
        media_info: MediaInfo | None = None,
        preview_jpeg: bytes | None = None,
    ) -> tuple[MediaInfo, bool]:
        path = Path(media).expanduser().resolve()
        if not path.is_file():
            raise ValueError(f"找不到媒体文件：{path}")
        info = media_info or inspect_media(path)
        prepared_preview = (
            preview_jpeg if preview_jpeg is not None else render_preview_jpeg(path)
        )
        with self._lock:
            active = self._thread is not None and self._thread.is_alive()
            frame_source = self._frame_source
            if active and frame_source is not None:
                selection_revision = int(
                    self._status.get("selection_revision", 0)
                ) + 1
                self._status.update(
                    {
                        "state": "starting",
                        "media": str(path),
                        "media_name": display_name or path.name,
                        "media_info": asdict(info),
                        "library_id": library_id,
                        "selection_revision": selection_revision,
                        "error": None,
                    }
                )
                self._preview_jpeg = prepared_preview
            else:
                frame_source = None

        if frame_source is not None:
            frame_source.switch(path)
            return info, True

        info = self.select_media(
            path,
            display_name=display_name,
            library_id=library_id,
            media_info=info,
            preview_jpeg=prepared_preview,
        )
        return info, False

    def _play_worker(
        self,
        frame_source: SwitchableMediaFrames,
        stop_event: threading.Event,
        retry_transient_errors: bool = True,
    ) -> None:
        total_written = 0
        retry_delay = AUTO_RESUME_RETRY_INITIAL_SECONDS
        try:
            while not stop_event.is_set():
                session_written = 0

                def update_progress(written: int) -> None:
                    nonlocal session_written
                    session_written = written
                    with self._lock:
                        self._status["state"] = "playing"
                        self._status["bytes_streamed"] = total_written + written
                        self._status["error"] = None

                try:
                    written = stream_frames(
                        frame_source,
                        repeat_rate=DISPLAY_KEEPALIVE_RATE,
                        stop_event=stop_event,
                        frame_change_event=frame_source.changed,
                        progress_callback=update_progress,
                    )
                except Exception as exc:
                    total_written += session_written
                    if not (
                        retry_transient_errors
                        and _is_retryable_display_error(exc)
                        and not stop_event.is_set()
                    ):
                        with self._lock:
                            self._status["state"] = "error"
                            self._status["bytes_streamed"] = total_written
                            self._status["error"] = _playback_error_message(exc)
                        return

                    message = _playback_error_message(exc)
                    logger.warning(
                        "Automatic display resume failed; retrying in %.1fs: %s: %s",
                        retry_delay,
                        type(exc).__name__,
                        exc,
                    )
                    with self._lock:
                        self._status["state"] = "starting"
                        self._status["bytes_streamed"] = total_written
                        self._status["error"] = (
                            f"{message}；将在 {retry_delay:g} 秒后自动重试"
                        )
                    if stop_event.wait(retry_delay):
                        break
                    retry_delay = min(
                        retry_delay * 2,
                        AUTO_RESUME_RETRY_MAX_SECONDS,
                    )
                    continue
                else:
                    total_written += max(written, session_written)
                    break

            with self._lock:
                self._status["state"] = "idle"
                self._status["bytes_streamed"] = total_written
                self._status["error"] = None
        finally:
            with self._lock:
                self._stop_event = None
                self._frame_source = None

    def stop(self) -> None:
        with self._lock:
            if self._stop_event is not None:
                self._status["state"] = "stopping"
                self._stop_event.set()
                if self._frame_source is not None:
                    self._frame_source.changed.set()

    def stop_and_wait(self) -> None:
        self.stop()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=8)
        if thread is not None and thread.is_alive():
            raise RuntimeError("播放任务未能在安全时限内停止")

    def clear_if_selected(self, media: str | Path) -> None:
        path = str(Path(media).resolve())
        with self._lock:
            selected = self._status.get("media") == path
        if not selected:
            return
        self.stop_and_wait()
        with self._lock:
            selection_revision = int(
                self._status.get("selection_revision", 0)
            ) + 1
            self._status = {
                "state": "idle",
                "media": None,
                "media_name": None,
                "media_info": None,
                "library_id": None,
                "selection_revision": selection_revision,
                "bytes_streamed": 0,
                "error": None,
            }
            self._preview_jpeg = None

    def close(self) -> None:
        self.stop()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=8)


class UiServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int]) -> None:
        super().__init__(address, UiHandler)
        self._preview_condition = threading.Condition()
        self._preview_streams: set[threading.Event] = set()
        self.library = MediaLibrary()
        saved_overlay = self.library.overlay_config()
        try:
            overlay_config = (
                OverlayConfig.parse(saved_overlay)
                if saved_overlay is not None
                else OverlayConfig()
            )
        except (TypeError, ValueError):
            overlay_config = OverlayConfig()
        self.overlay = OverlayRenderer(overlay_config)
        self.playback = PlaybackController(self.overlay)
        selected = self.library.selected_item()
        if selected is not None:
            self.playback.select_media(
                selected.path,
                display_name=selected.name,
                library_id=selected.item_id,
                media_info=selected.media_info,
                preview_jpeg=selected.preview_path.read_bytes(),
            )
            if self.library.desired_running():
                self.playback.start_selected(retry_transient_errors=True)
        elif self.library.desired_running():
            self.library.remember_running(False)

    def register_preview_stream(self) -> threading.Event:
        event = threading.Event()
        with self._preview_condition:
            self._preview_streams.add(event)
        return event

    def unregister_preview_stream(self, event: threading.Event) -> None:
        with self._preview_condition:
            self._preview_streams.discard(event)
            self._preview_condition.notify_all()

    def stop_preview_streams(self, *, timeout: float = 2.0) -> None:
        deadline = time.monotonic() + timeout
        with self._preview_condition:
            for event in self._preview_streams:
                event.set()
            while self._preview_streams:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._preview_condition.wait(remaining)


class UiHandler(BaseHTTPRequestHandler):
    server: UiServer

    def log_message(self, format: str, *args) -> None:
        return

    def _json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length > 1024 * 1024:
            raise ValueError("JSON 请求过大")
        data = self.rfile.read(length)
        return json.loads(data.decode("utf-8")) if data else {}

    def _origin_allowed(self) -> bool:
        host = self.headers.get("Host", "")
        allowed_hosts = {
            f"127.0.0.1:{self.server.server_port}",
            f"localhost:{self.server.server_port}",
        }
        if host not in allowed_hosts:
            return False
        origin = self.headers.get("Origin")
        return origin is None or origin in {
            f"http://127.0.0.1:{self.server.server_port}",
            f"http://localhost:{self.server.server_port}",
        }

    def do_GET(self) -> None:
        parsed = urllib.parse.urlsplit(self.path)
        path = parsed.path
        if path.startswith("/api/") and not self._origin_allowed():
            self._json(HTTPStatus.FORBIDDEN, {"error": "拒绝非本机请求"})
            return
        if path == "/api/status":
            status = self.server.playback.status()
            status["enabled"] = self.server.library.desired_running()
            status["channel_conflicts"] = channel_conflicts()
            self._json(HTTPStatus.OK, status)
            return
        if path == "/api/monitor":
            self._json(
                HTTPStatus.OK,
                {
                    "config": self.server.overlay.config(),
                    "telemetry": self.server.overlay.snapshot(),
                },
            )
            return
        if path == "/api/media":
            self._serve_selected_media()
            return
        if path == "/api/preview":
            self._serve_selected_preview()
            return
        if path == "/api/preview-stream":
            self._serve_preview_stream()
            return
        if path == "/api/library":
            items = [
                item.public_dict() for item in self.server.library.list_items()
            ]
            self._json(
                HTTPStatus.OK,
                {
                    "items": items,
                    "selected_id": self.server.playback.status().get("library_id"),
                },
            )
            return
        if path == "/api/library/thumbnail":
            query = urllib.parse.parse_qs(parsed.query)
            self._serve_library_thumbnail(query.get("id", [""])[0])
            return
        if path == "/favicon.ico":
            self.send_response(HTTPStatus.NO_CONTENT)
            self.end_headers()
            return

        assets = {
            "/": ("index.html", "text/html; charset=utf-8"),
            "/app.js": ("app.js", "text/javascript; charset=utf-8"),
            "/style.css": ("style.css", "text/css; charset=utf-8"),
        }
        asset = assets.get(path)
        if asset is None:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        name, content_type = asset
        content = files("b360gt").joinpath("web", name).read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def do_HEAD(self) -> None:
        path = urllib.parse.urlsplit(self.path).path
        if path.startswith("/api/") and not self._origin_allowed():
            self.send_response(HTTPStatus.FORBIDDEN)
            self.end_headers()
            return
        if path == "/api/media":
            self._serve_selected_media(head_only=True)
            return
        if path == "/api/preview":
            self._serve_selected_preview(head_only=True)
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        if not self._origin_allowed():
            self._json(HTTPStatus.FORBIDDEN, {"error": "拒绝非本机请求"})
            return
        path = urllib.parse.urlsplit(self.path).path
        try:
            if path == "/api/probe":
                info = asdict(probe())
                self._json(HTTPStatus.OK, {"device": info})
                return
            if path == "/api/monitor/config":
                config = self.server.overlay.configure(self._read_json())
                self.server.library.remember_overlay_config(config)
                self._json(HTTPStatus.OK, {"config": config})
                return
            if path == "/api/playback":
                enabled = self._read_json().get("enabled")
                if not isinstance(enabled, bool):
                    raise ValueError("enabled 必须是布尔值")
                if enabled:
                    self.server.playback.start_selected(
                        retry_transient_errors=True
                    )
                    self.server.library.remember_running(True)
                else:
                    self.server.library.remember_running(False)
                    # Do not acknowledge "off" while the old USB recovery
                    # session is still alive.  Otherwise a quick off/on after
                    # resume races start_selected() against that stale worker
                    # and the user cannot force a fresh enumeration.
                    self.server.playback.stop_and_wait()
                self._json(HTTPStatus.ACCEPTED, {"ok": True, "enabled": enabled})
                return
            if path == "/api/play":
                self.server.playback.start_selected(
                    retry_transient_errors=True
                )
                self.server.library.remember_running(True)
                self._json(HTTPStatus.ACCEPTED, {"ok": True})
                return
            if path == "/api/library/select":
                request = self._read_json()
                item = self.server.library.get(str(request.get("id", "")))
                self.server.stop_preview_streams()
                info, resumed = self.server.playback.switch_media(
                    item.path,
                    display_name=item.name,
                    library_id=item.item_id,
                    media_info=item.media_info,
                    preview_jpeg=item.preview_path.read_bytes(),
                )
                self.server.library.remember_selected(item.item_id)
                self._json(
                    HTTPStatus.OK,
                    {
                        "item": item.public_dict(),
                        "media": self.server.playback.status(),
                        "media_info": asdict(info),
                        "resumed": resumed,
                    },
                )
                return
            if path == "/api/library/delete":
                request = self._read_json()
                item = self.server.library.get(str(request.get("id", "")))
                if self.server.playback.selected_media() == item.path:
                    self.server.stop_preview_streams()
                    self.server.library.remember_running(False)
                self.server.playback.clear_if_selected(item.path)
                deleted = self.server.library.delete(item.item_id)
                self._json(
                    HTTPStatus.OK,
                    {"deleted": deleted.public_dict()},
                )
                return
            if path == "/api/stop":
                self.server.library.remember_running(False)
                self.server.playback.stop()
                self._json(HTTPStatus.ACCEPTED, {"ok": True})
                return
            if path == "/api/upload":
                self._handle_upload()
                return
            self._json(HTTPStatus.NOT_FOUND, {"error": "接口不存在"})
        except Exception as exc:
            self._json(
                HTTPStatus.BAD_REQUEST,
                {"error": f"{type(exc).__name__}: {exc}"},
            )

    def _handle_upload(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            raise ValueError("文件为空")
        if length > MAX_UPLOAD_SIZE:
            raise ValueError("文件超过 256 MiB 上传限制")

        original = urllib.parse.unquote(self.headers.get("X-Filename", "media"))
        safe_name = re.sub(r"[^A-Za-z0-9._\-\u4e00-\u9fff]", "_", Path(original).name)
        destination = _upload_directory() / f"{uuid.uuid4().hex[:12]}-{safe_name}"
        temporary = destination.with_suffix(destination.suffix + ".part")

        remaining = length
        try:
            with temporary.open("wb") as output:
                while remaining:
                    chunk = self.rfile.read(min(remaining, UPLOAD_CHUNK_SIZE))
                    if not chunk:
                        raise IOError("上传中断")
                    output.write(chunk)
                    remaining -= len(chunk)
            temporary.replace(destination)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        try:
            item = self.server.library.add(
                destination,
                display_name=original,
                move=True,
            )
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        self.server.stop_preview_streams()
        info, resumed = self.server.playback.switch_media(
            item.path,
            display_name=item.name,
            library_id=item.item_id,
            media_info=item.media_info,
            preview_jpeg=item.preview_path.read_bytes(),
        )
        self.server.library.remember_selected(item.item_id)

        self._json(
            HTTPStatus.CREATED,
            {
                "path": str(item.path),
                "name": item.name,
                "size": item.size,
                "item": item.public_dict(),
                "media_info": asdict(info),
                "media": self.server.playback.status(),
                "resumed": resumed,
            },
        )

    def _serve_selected_preview(self, *, head_only: bool = False) -> None:
        preview = self.server.playback.selected_preview()
        if preview is None:
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(preview)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if not head_only:
            self.wfile.write(preview)

    def _serve_preview_stream(self) -> None:
        media = self.server.playback.selected_media()
        status = self.server.playback.status()
        if media is None or (status.get("media_info") or {}).get("kind") != "video":
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        boundary = b"b360gt-preview"
        self.send_response(HTTPStatus.OK)
        self.send_header(
            "Content-Type",
            f"multipart/x-mixed-replace; boundary={boundary.decode('ascii')}",
        )
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()

        stop_event = self.server.register_preview_stream()
        try:
            for jpeg, duration in iter_video_preview_jpegs(media, loop=True):
                if stop_event.is_set():
                    break
                started = time.monotonic()
                self.wfile.write(b"--" + boundary + b"\r\n")
                self.wfile.write(b"Content-Type: image/jpeg\r\n")
                self.wfile.write(
                    f"Content-Length: {len(jpeg)}\r\n\r\n".encode("ascii")
                )
                self.wfile.write(jpeg)
                self.wfile.write(b"\r\n")
                self.wfile.flush()
                delay = duration - (time.monotonic() - started)
                if delay > 0:
                    time.sleep(delay)
        except (
            BrokenPipeError,
            ConnectionAbortedError,
            ConnectionResetError,
        ):
            return
        finally:
            self.server.unregister_preview_stream(stop_event)

    def _serve_library_thumbnail(self, item_id: str) -> None:
        try:
            item = self.server.library.get(item_id)
        except ValueError:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content = item.preview_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "private, max-age=86400")
        self.end_headers()
        self.wfile.write(content)

    def _serve_selected_media(self, *, head_only: bool = False) -> None:
        path = self.server.playback.selected_media()
        if path is None:
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        size = path.stat().st_size
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        start = 0
        end = size - 1
        partial = False
        range_header = self.headers.get("Range")
        if range_header:
            match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header.strip())
            if match is None:
                self.send_error(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                return
            if match.group(1):
                start = int(match.group(1))
            if match.group(2):
                end = min(int(match.group(2)), size - 1)
            if start > end or start >= size:
                self.send_error(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                return
            partial = True

        length = end - start + 1
        self.send_response(
            HTTPStatus.PARTIAL_CONTENT if partial else HTTPStatus.OK
        )
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "no-store")
        if partial:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()

        if head_only:
            return

        with path.open("rb") as media:
            media.seek(start)
            remaining = length
            while remaining:
                chunk = media.read(min(remaining, UPLOAD_CHUNK_SIZE))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)


def run_ui(
    *,
    port: int = 8765,
    open_browser: bool = True,
    quiet: bool = False,
    shutdown_event: threading.Event | None = None,
    managed_background: bool = False,
) -> None:
    try:
        server = UiServer(("127.0.0.1", port))
    except OSError as exc:
        if getattr(exc, "winerror", None) == 10048 or exc.errno in {48, 98}:
            raise RuntimeError(
                f"B360GT 后端已运行，或本机端口 {port} 已被占用"
            ) from exc
        raise
    url = f"http://127.0.0.1:{server.server_port}/"
    previous_sigterm_handler = None
    if managed_background:
        def request_shutdown(_signum: int, _frame: object) -> None:
            threading.Thread(target=server.shutdown, daemon=True).start()

        previous_sigterm_handler = signal.getsignal(signal.SIGTERM)
        signal.signal(signal.SIGTERM, request_shutdown)
    if not quiet:
        print(f"B360GT 控制台：{url}")
        print("按 Ctrl+C 关闭控制台。")
    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    if shutdown_event is not None:
        def watch_shutdown() -> None:
            shutdown_event.wait()
            server.shutdown()

        threading.Thread(
            target=watch_shutdown,
            name="b360gt-shutdown-watcher",
            daemon=True,
        ).start()
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.stop_preview_streams()
        server.playback.close()
        server.server_close()
        if previous_sigterm_handler is not None:
            signal.signal(signal.SIGTERM, previous_sigterm_handler)
