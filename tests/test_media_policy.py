from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from b360gt.media import MediaInfo
from b360gt.media_policy import (
    GIB,
    MAX_ANIMATED_IMAGE_SIZE,
    MAX_STATIC_IMAGE_SIZE,
    MAX_VIDEO_SIZE,
    MediaPolicyError,
    validate_media_import,
)


def video_info(**overrides) -> MediaInfo:
    values = {
        "kind": "video",
        "width": 1920,
        "height": 1080,
        "source_fps": 60.0,
        "output_fps": 30.0,
        "frame_count": 300,
        "duration_seconds": 10.0,
        "container_format": "mov,mp4,m4a,3gp,3g2,mj2",
    }
    values.update(overrides)
    return MediaInfo(**values)


class MediaPolicyTests(unittest.TestCase):
    def _source(self, directory: str, size: int = 1) -> Path:
        path = Path(directory) / "media.bin"
        with path.open("wb") as output:
            output.truncate(size)
        return path

    def _validate(self, path: Path, info: MediaInfo) -> None:
        disk = SimpleNamespace(total=GIB * 10, used=GIB * 5, free=GIB * 5)
        with patch("b360gt.media_policy.shutil.disk_usage", return_value=disk):
            validate_media_import(path, info, library_root=path.parent)

    def test_accepts_daily_use_video(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self._validate(self._source(directory), video_info())

    def test_kind_controls_size_limit_not_extension(self) -> None:
        cases = [
            (
                MAX_STATIC_IMAGE_SIZE + 1,
                MediaInfo("image", 10, 10, None, 2.0, 1),
            ),
            (
                MAX_ANIMATED_IMAGE_SIZE + 1,
                MediaInfo("animated_image", 10, 10, 10.0, 10.0, 2),
            ),
            (MAX_VIDEO_SIZE + 1, video_info()),
        ]
        with tempfile.TemporaryDirectory() as directory:
            for size, info in cases:
                with self.subTest(kind=info.kind), self.assertRaises(MediaPolicyError):
                    self._validate(self._source(directory, size), info)

    def test_rejects_video_content_limits(self) -> None:
        invalid = [
            video_info(container_format="avi"),
            video_info(duration_seconds=901.0),
            video_info(duration_seconds=None),
            video_info(width=4096, height=2160),
            video_info(width=3000, height=3000),
            video_info(source_fps=121.0),
            video_info(source_fps=None),
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = self._source(directory)
            for info in invalid:
                with self.subTest(info=info), self.assertRaises(MediaPolicyError):
                    self._validate(path, info)

    def test_requires_one_gib_free_after_copy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self._source(directory, 1024)
            disk = SimpleNamespace(total=GIB * 2, used=GIB, free=GIB + 1023)
            with patch("b360gt.media_policy.shutil.disk_usage", return_value=disk):
                with self.assertRaises(MediaPolicyError):
                    validate_media_import(
                        path, video_info(), library_root=path.parent
                    )

    def test_same_filesystem_move_does_not_double_count_source_size(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self._source(directory, 1024)
            disk = SimpleNamespace(total=GIB * 2, used=GIB, free=GIB)
            with patch("b360gt.media_policy.shutil.disk_usage", return_value=disk):
                validate_media_import(
                    path,
                    video_info(),
                    library_root=path.parent,
                    move=True,
                )


if __name__ == "__main__":
    unittest.main()
