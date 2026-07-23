from __future__ import annotations

import unittest

from PIL import Image

from b360gt.protocol import (
    FRAME_HEADER,
    FRAME_SIZE,
    FRAME_TRAILER,
    HEIGHT,
    PIXEL_PAYLOAD_SIZE,
    WIDTH,
    build_frame,
    encode_uyvy,
)


class ProtocolTests(unittest.TestCase):
    def test_pure_red_matches_capture(self) -> None:
        image = Image.new("RGB", (WIDTH, HEIGHT), (255, 0, 0))
        payload = encode_uyvy(image)

        self.assertEqual(len(payload), PIXEL_PAYLOAD_SIZE)
        self.assertEqual(payload[:4], bytes.fromhex("5A 51 EF 51"))
        self.assertEqual(payload, bytes.fromhex("5A 51 EF 51") * (WIDTH * HEIGHT // 2))

    def test_complete_frame_markers_and_size(self) -> None:
        image = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
        frame = build_frame(image)

        self.assertEqual(len(frame), FRAME_SIZE)
        self.assertEqual(frame[:8], FRAME_HEADER)
        self.assertEqual(frame[-8:], FRAME_TRAILER)


if __name__ == "__main__":
    unittest.main()
