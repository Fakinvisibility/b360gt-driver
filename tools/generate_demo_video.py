"""Encode the generated GIF as a short MP4 for playback validation."""

from __future__ import annotations

from pathlib import Path

import av
from PIL import Image


def main() -> None:
    project = Path(__file__).resolve().parent.parent
    source = project / "test-images" / "animation.gif"
    output = project / "test-images" / "animation.mp4"

    container = av.open(str(output), mode="w")
    stream = container.add_stream("mpeg4", rate=20)
    stream.width = 480
    stream.height = 480
    stream.pix_fmt = "yuv420p"
    stream.bit_rate = 2_000_000

    with Image.open(source) as animated:
        for index in range(animated.n_frames):
            animated.seek(index)
            image = animated.convert("RGB")
            frame = av.VideoFrame.from_image(image)
            frame.pts = index
            for packet in stream.encode(frame):
                container.mux(packet)

    for packet in stream.encode():
        container.mux(packet)
    container.close()
    print(output)


if __name__ == "__main__":
    main()
