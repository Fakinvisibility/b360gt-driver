"""Frame encoding for the Valkyrie B360GT USB display."""

from __future__ import annotations

from pathlib import Path
from typing import Union

import numpy as np
from PIL import Image, ImageOps

WIDTH = 480
HEIGHT = 480

FRAME_HEADER = bytes.fromhex("FF 00 00 00 00 1E 01 E0")
FRAME_TRAILER = bytes.fromhex("FF C0 00 00 00 00 00 00")
PIXEL_PAYLOAD_SIZE = WIDTH * HEIGHT * 2
FRAME_SIZE = len(FRAME_HEADER) + PIXEL_PAYLOAD_SIZE + len(FRAME_TRAILER)

ImageSource = Union[str, Path, Image.Image]


def prepare_image(source: ImageSource) -> Image.Image:
    """Load an image and crop/resize it to the display's 480×480 canvas."""
    if isinstance(source, Image.Image):
        image = source.convert("RGB")
    else:
        with Image.open(source) as opened:
            image = opened.convert("RGB")

    return ImageOps.fit(
        image,
        (WIDTH, HEIGHT),
        method=Image.Resampling.LANCZOS,
        centering=(0.5, 0.5),
    )


def encode_uyvy(source: ImageSource) -> bytes:
    """Encode an image as 480×480 BT.601 limited-range UYVY."""
    image = prepare_image(source)
    rgb = np.asarray(image, dtype=np.int32)
    red = rgb[:, :, 0]
    green = rgb[:, :, 1]
    blue = rgb[:, :, 2]

    # Integer form matching the values observed in MythCool captures:
    # pure red (255, 0, 0) -> Y=81, U=90, V=239.
    y = (257 * red + 504 * green + 98 * blue) // 1000 + 16
    u = (-148 * red - 291 * green + 439 * blue) // 1000 + 128
    v = (439 * red - 368 * green - 71 * blue) // 1000 + 128

    y = np.clip(y, 16, 235).astype(np.uint8)
    u = np.clip(u, 16, 240)
    v = np.clip(v, 16, 240)

    # UYVY shares one U and V sample between each horizontal pair.
    u_pair = ((u[:, 0::2] + u[:, 1::2]) // 2).astype(np.uint8)
    v_pair = ((v[:, 0::2] + v[:, 1::2]) // 2).astype(np.uint8)

    packed = np.empty((HEIGHT, WIDTH // 2, 4), dtype=np.uint8)
    packed[:, :, 0] = u_pair
    packed[:, :, 1] = y[:, 0::2]
    packed[:, :, 2] = v_pair
    packed[:, :, 3] = y[:, 1::2]
    payload = packed.tobytes()

    if len(payload) != PIXEL_PAYLOAD_SIZE:
        raise AssertionError(
            f"Unexpected payload size {len(payload)}; expected {PIXEL_PAYLOAD_SIZE}"
        )
    return payload


def build_frame(source: ImageSource) -> bytes:
    """Build one complete USB frame, including its 8-byte markers."""
    frame = FRAME_HEADER + encode_uyvy(source) + FRAME_TRAILER
    if len(frame) != FRAME_SIZE:
        raise AssertionError(f"Unexpected frame size {len(frame)}; expected {FRAME_SIZE}")
    return frame
