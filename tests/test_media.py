from __future__ import annotations

import tempfile
import unittest
from io import BytesIO
from itertools import islice
from pathlib import Path

from PIL import Image

from b360gt.media import (
    MAX_VIDEO_FPS,
    STATIC_FRAME_DURATION,
    inspect_media,
    iter_media_frames,
    iter_video_preview_jpegs,
    render_preview_jpeg,
)
from b360gt.protocol import FRAME_SIZE


class MediaTests(unittest.TestCase):
    def test_still_image_yields_one_frame_without_looping(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "still.png"
            Image.new("RGB", (32, 24), "red").save(path)

            frames = list(iter_media_frames(path, loop=False))
            info = inspect_media(path)

        self.assertEqual(len(frames), 1)
        self.assertEqual(len(frames[0][0]), FRAME_SIZE)
        self.assertGreater(frames[0][1], 0)
        self.assertEqual(frames[0][1], STATIC_FRAME_DURATION)
        self.assertEqual(info.kind, "image")
        self.assertEqual((info.width, info.height), (32, 24))
        self.assertEqual(info.output_fps, 2.0)

    def test_browser_preview_is_a_square_jpeg(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "wide.png"
            Image.new("RGB", (80, 40), "purple").save(path)

            preview = render_preview_jpeg(path)
            with Image.open(BytesIO(preview)) as decoded:
                result = (decoded.format, decoded.size)

        self.assertEqual(result, ("JPEG", (480, 480)))

    def test_gif_preserves_frame_durations(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "animated.gif"
            images = [
                Image.new("RGB", (32, 32), "red"),
                Image.new("RGB", (32, 32), "blue"),
            ]
            images[0].save(
                path,
                save_all=True,
                append_images=images[1:],
                duration=[50, 120],
                loop=0,
            )

            frames = list(iter_media_frames(path, loop=False))
            info = inspect_media(path)

        self.assertEqual(len(frames), 2)
        self.assertEqual([round(item[1], 2) for item in frames], [0.05, 0.12])
        self.assertTrue(all(len(item[0]) == FRAME_SIZE for item in frames))
        self.assertEqual(info.kind, "animated_image")
        self.assertEqual(info.frame_count, 2)

    def test_sixty_fps_video_is_identified_and_capped_by_dropping_frames(self) -> None:
        import av

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fast.mp4"
            container = av.open(str(path), mode="w")
            stream = container.add_stream("mpeg4", rate=60)
            stream.width = 32
            stream.height = 32
            stream.pix_fmt = "yuv420p"
            for index in range(12):
                image = Image.new("RGB", (32, 32), (index * 20, 0, 0))
                frame = av.VideoFrame.from_image(image)
                frame.pts = index
                for packet in stream.encode(frame):
                    container.mux(packet)
            for packet in stream.encode():
                container.mux(packet)
            container.close()

            info = inspect_media(path)
            frames = list(iter_media_frames(path, loop=False))
            previews = list(islice(iter_video_preview_jpegs(path), 3))

        self.assertEqual(info.kind, "video")
        self.assertAlmostEqual(info.source_fps or 0, 60.0)
        self.assertEqual(info.output_fps, MAX_VIDEO_FPS)
        self.assertLessEqual(len(frames), 7)
        self.assertGreaterEqual(len(frames), 5)
        self.assertTrue(all(len(item[0]) == FRAME_SIZE for item in frames))
        self.assertEqual(len(previews), 3)
        self.assertTrue(all(jpeg.startswith(b"\xff\xd8") for jpeg, _ in previews))


if __name__ == "__main__":
    unittest.main()
