"""Content-based safety limits for media imported into the library."""

from __future__ import annotations

import shutil
from pathlib import Path

from .media import MediaInfo

MIB = 1024 * 1024
GIB = 1024 * MIB

MAX_STATIC_IMAGE_SIZE = 50 * MIB
MAX_ANIMATED_IMAGE_SIZE = 200 * MIB
MAX_VIDEO_SIZE = 256 * MIB
MAX_VIDEO_DURATION = 15 * 60.0
MAX_VIDEO_WIDTH = 3840
MAX_VIDEO_HEIGHT = 2160
MAX_VIDEO_PIXELS = 8_294_400
MAX_SOURCE_VIDEO_FPS = 120.0
MAX_IMAGE_WIDTH = 8192
MAX_IMAGE_HEIGHT = 8192
MAX_IMAGE_PIXELS = 50_000_000
MIN_FREE_SPACE_AFTER_IMPORT = GIB

ALLOWED_VIDEO_FORMAT_NAMES = frozenset({"mov", "mp4", "matroska", "webm"})


class MediaPolicyError(ValueError):
    """Raised when decoded media exceeds an import safety limit."""


def validate_media_import(
    source: str | Path,
    info: MediaInfo,
    *,
    library_root: str | Path,
    move: bool = False,
) -> None:
    path = Path(source)
    size = path.stat().st_size

    if info.kind == "image":
        _require_size(size, MAX_STATIC_IMAGE_SIZE, "静态图片")
        _require_dimensions(
            info, MAX_IMAGE_WIDTH, MAX_IMAGE_HEIGHT, MAX_IMAGE_PIXELS, "图片"
        )
    elif info.kind == "animated_image":
        _require_size(size, MAX_ANIMATED_IMAGE_SIZE, "动态图片")
        _require_dimensions(
            info, MAX_IMAGE_WIDTH, MAX_IMAGE_HEIGHT, MAX_IMAGE_PIXELS, "动态图片"
        )
    elif info.kind == "video":
        _require_size(size, MAX_VIDEO_SIZE, "视频")
        _validate_video(info)
    else:
        raise MediaPolicyError(f"不支持的媒体类型：{info.kind}")

    root = Path(library_root)
    free = shutil.disk_usage(root).free
    same_filesystem_move = (
        move and path.stat().st_dev == root.stat().st_dev
    )
    additional_space = 0 if same_filesystem_move else size
    required = additional_space + MIN_FREE_SPACE_AFTER_IMPORT
    if free < required:
        raise MediaPolicyError(
            "媒体库磁盘空间不足：导入完成后必须至少保留 1 GiB 可用空间"
        )


def _require_size(actual: int, maximum: int, label: str) -> None:
    if actual > maximum:
        raise MediaPolicyError(
            f"{label}文件过大：最大允许 {maximum // MIB} MiB"
        )


def _require_dimensions(
    info: MediaInfo,
    max_width: int,
    max_height: int,
    max_pixels: int,
    label: str,
) -> None:
    if info.width <= 0 or info.height <= 0:
        raise MediaPolicyError(f"{label}尺寸无效")
    if (
        info.width > max_width
        or info.height > max_height
        or info.width * info.height > max_pixels
    ):
        raise MediaPolicyError(
            f"{label}分辨率过高：最大边长 {max_width}×{max_height}，"
            f"单帧最多 {max_pixels:,} 像素"
        )


def _validate_video(info: MediaInfo) -> None:
    formats = {
        value.strip()
        for value in (info.container_format or "").split(",")
        if value.strip()
    }
    if not formats.intersection(ALLOWED_VIDEO_FORMAT_NAMES):
        raise MediaPolicyError("视频容器仅支持 MP4、MOV、MKV 和 WebM")
    _require_dimensions(
        info,
        MAX_VIDEO_WIDTH,
        MAX_VIDEO_HEIGHT,
        MAX_VIDEO_PIXELS,
        "视频",
    )
    if info.duration_seconds is None:
        raise MediaPolicyError("无法确定视频时长，拒绝导入")
    if info.duration_seconds <= 0 or info.duration_seconds > MAX_VIDEO_DURATION:
        raise MediaPolicyError("视频时长必须大于 0 且不超过 15 分钟")
    if info.source_fps is None:
        raise MediaPolicyError("无法确定源视频帧率，拒绝导入")
    if info.source_fps <= 0 or info.source_fps > MAX_SOURCE_VIDEO_FPS:
        raise MediaPolicyError("源视频帧率必须大于 0 且不超过 120 FPS")
