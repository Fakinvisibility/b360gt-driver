"""Generate a small animated test pattern for physical display validation."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 480
FRAME_COUNT = 24


def main() -> None:
    frames: list[Image.Image] = []
    colors = ("#ff3155", "#00d084", "#2f80ff", "#ffd43b")

    for index in range(FRAME_COUNT):
        image = Image.new("RGB", (SIZE, SIZE), "#10131a")
        draw = ImageDraw.Draw(image)
        draw.ellipse((24, 24, SIZE - 24, SIZE - 24), outline="#ffffff", width=8)

        angle = index / FRAME_COUNT
        center = SIZE // 2
        radius = 180
        import math

        x = center + int(math.sin(angle * math.tau) * radius)
        y = center - int(math.cos(angle * math.tau) * radius)
        draw.line((center, center, x, y), fill=colors[index % 4], width=24)
        draw.ellipse((x - 24, y - 24, x + 24, y + 24), fill="#ffffff")
        draw.text((24, SIZE - 54), f"B360GT GIF  {index + 1:02d}/{FRAME_COUNT}", fill="#ffffff")
        frames.append(image)

    output = Path(__file__).resolve().parent.parent / "test-images" / "animation.gif"
    frames[0].save(
        output,
        save_all=True,
        append_images=frames[1:],
        duration=50,
        loop=0,
        optimize=False,
    )
    print(output)


if __name__ == "__main__":
    main()
