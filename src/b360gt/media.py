"""Decode still images, animated images, and videos into timed USB frames."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, Callable

from PIL import Image, UnidentifiedImageError

from .protocol import build_frame, prepare_image

TimedFrame = tuple[bytes, float]

MIN_FRAME_DURATION = 0.02
DEFAULT_FRAME_DURATION = 0.05
STATIC_FRAME_DURATION = 0.5
MAX_VIDEO_FPS = 30.0
BROWSER_PREVIEW_FPS = 12.0
AV_TIME_BASE = 1_000_000


@dataclass(frozen=True)
class MediaInfo:
    kind: str
    width: int
    height: int
    source_fps: float | None
    output_fps: float | None
    frame_count: int | None
    duration_seconds: float | None = None
    container_format: str | None = None


class MediaError(RuntimeError):
    """Raised when a media file cannot provide displayable video frames."""


def inspect_media(source: str | Path) -> MediaInfo:
    """Identify a media file without trusting its extension."""
    path = Path(source)
    if not path.is_file():
        raise MediaError(f"Media file does not exist: {path}")

    try:
        with Image.open(path) as image:
            animated = bool(getattr(image, "is_animated", False))
            frame_count = int(getattr(image, "n_frames", 1))
            if not animated:
                return MediaInfo(
                    kind="image",
                    width=image.width,
                    height=image.height,
                    source_fps=None,
                    output_fps=1.0 / STATIC_FRAME_DURATION,
                    frame_count=1,
                    container_format=(image.format or "").lower() or None,
                )

            durations_ms: list[float] = []
            for index in range(frame_count):
                image.seek(index)
                durations_ms.append(float(image.info.get("duration", 100)))
            positive_durations = [value for value in durations_ms if value > 0]
            source_fps = (
                1000.0 / (sum(positive_durations) / len(positive_durations))
                if positive_durations
                else None
            )
            return MediaInfo(
                kind="animated_image",
                width=image.width,
                height=image.height,
                source_fps=source_fps,
                output_fps=source_fps,
                frame_count=frame_count,
                duration_seconds=sum(max(value, 0.0) for value in durations_ms) / 1000.0,
                container_format=(image.format or "").lower() or None,
            )
    except UnidentifiedImageError:
        pass

    try:
        import av
    except ImportError as exc:
        raise MediaError(
            "Video inspection requires PyAV; install the project dependencies first"
        ) from exc

    try:
        container = av.open(str(path))
    except av.error.FFmpegError as exc:
        raise MediaError(f"Could not open media file: {path}") from exc

    with container:
        if not container.streams.video:
            raise MediaError(f"Media contains no video stream: {path}")
        stream = container.streams.video[0]
        source_fps = float(stream.average_rate) if stream.average_rate else None
        duration_seconds = _video_duration_seconds(container, stream)
        output_fps = (
            min(source_fps, MAX_VIDEO_FPS)
            if source_fps is not None
            else MAX_VIDEO_FPS
        )
        frame_count = int(stream.frames) if stream.frames else None
        return MediaInfo(
            kind="video",
            width=stream.width,
            height=stream.height,
            source_fps=source_fps,
            output_fps=output_fps,
            frame_count=frame_count,
            duration_seconds=duration_seconds,
            container_format=(container.format.name or "").lower() or None,
        )


def _video_duration_seconds(container: Any, stream: Any) -> float | None:
    if stream.duration is not None and stream.time_base is not None:
        duration = float(stream.duration * stream.time_base)
        if duration >= 0:
            return duration
    if container.duration is not None:
        duration = float(container.duration) / AV_TIME_BASE
        if duration >= 0:
            return duration
    return None


def iter_media_frames(
    source: str | Path,
    *,
    loop: bool = True,
    image_transform: Callable[[Image.Image], Image.Image] | None = None,
) -> Iterator[TimedFrame]:
    """Yield encoded frames and their display durations.

    Pillow handles still images and animated formats such as GIF/APNG. Other
    inputs are passed to PyAV for video decoding.
    """
    path = Path(source)
    if not path.is_file():
        raise MediaError(f"Media file does not exist: {path}")

    try:
        with Image.open(path) as image:
            animated = bool(getattr(image, "is_animated", False))
    except UnidentifiedImageError:
        animated = False
    else:
        if not animated:
            while True:
                with Image.open(path) as still:
                    rendered = still.convert("RGBA")
                if image_transform:
                    rendered = image_transform(prepare_image(rendered))
                frame = build_frame(rendered)
                yield frame, STATIC_FRAME_DURATION
                if not loop:
                    return
        else:
            yield from _iter_animated_image(
                path, loop=loop, image_transform=image_transform
            )
            return

    yield from _iter_video(path, loop=loop, image_transform=image_transform)


def render_preview_jpeg(source: str | Path) -> bytes:
    """Render a browser-safe first-frame preview matching the display crop."""
    path = Path(source)
    if not path.is_file():
        raise MediaError(f"Media file does not exist: {path}")

    try:
        with Image.open(path) as image:
            preview = prepare_image(image)
    except UnidentifiedImageError:
        try:
            import av
        except ImportError as exc:
            raise MediaError(
                "Video preview requires PyAV; install the project dependencies first"
            ) from exc

        try:
            container = av.open(str(path))
        except av.error.FFmpegError as exc:
            raise MediaError(f"Could not open media file: {path}") from exc

        with container:
            if not container.streams.video:
                raise MediaError(f"Media contains no video stream: {path}")
            decoded = next(container.decode(container.streams.video[0]), None)
            if decoded is None:
                raise MediaError(f"Video stream contains no decodable frames: {path}")
            preview = prepare_image(decoded.to_image())

    return _encode_preview_jpeg(preview, quality=88, optimize=True)


def iter_video_preview_jpegs(
    source: str | Path,
    *,
    loop: bool = True,
    max_fps: float = BROWSER_PREVIEW_FPS,
) -> Iterator[tuple[bytes, float]]:
    """Decode a video into browser-independent JPEG preview frames."""
    if not 1.0 <= max_fps <= BROWSER_PREVIEW_FPS:
        raise ValueError(
            f"max_fps must be between 1 and {BROWSER_PREVIEW_FPS:g}"
        )

    path = Path(source)
    if not path.is_file():
        raise MediaError(f"Media file does not exist: {path}")

    try:
        import av
    except ImportError as exc:
        raise MediaError(
            "Video preview requires PyAV; install the project dependencies first"
        ) from exc

    minimum_interval = 1.0 / max_fps
    while True:
        try:
            container = av.open(str(path))
        except av.error.FFmpegError as exc:
            raise MediaError(f"Could not open media file: {path}") from exc

        decoded_any = False
        emitted_any = False
        last_emitted_time: float | None = None
        decoded_index = 0
        with container:
            if not container.streams.video:
                raise MediaError(f"Media contains no video stream: {path}")
            stream = container.streams.video[0]
            source_rate = float(stream.average_rate) if stream.average_rate else 20.0

            for decoded in container.decode(stream):
                decoded_any = True
                timestamp = (
                    float(decoded.time)
                    if decoded.time is not None
                    else decoded_index / source_rate
                )
                decoded_index += 1
                if (
                    last_emitted_time is not None
                    and timestamp - last_emitted_time + 1e-9 < minimum_interval
                ):
                    continue

                preview = prepare_image(decoded.to_image())
                yield (
                    _encode_preview_jpeg(preview, quality=78, optimize=False),
                    minimum_interval,
                )
                last_emitted_time = timestamp
                emitted_any = True

        if not decoded_any or not emitted_any:
            raise MediaError(f"Video stream contains no decodable frames: {path}")
        if not loop:
            return


def _encode_preview_jpeg(
    image: Image.Image,
    *,
    quality: int,
    optimize: bool,
) -> bytes:
    output = BytesIO()
    image.save(output, format="JPEG", quality=quality, optimize=optimize)
    return output.getvalue()


def _iter_animated_image(
    path: Path,
    *,
    loop: bool,
    image_transform: Callable[[Image.Image], Image.Image] | None = None,
) -> Iterator[TimedFrame]:
    while True:
        with Image.open(path) as image:
            frame_count = getattr(image, "n_frames", 1)
            for index in range(frame_count):
                image.seek(index)
                rendered = image.convert("RGBA")
                if image_transform:
                    rendered = image_transform(prepare_image(rendered))
                duration = max(
                    float(image.info.get("duration", 100)) / 1000.0,
                    MIN_FRAME_DURATION,
                )
                yield build_frame(rendered), duration
        if not loop:
            return


def _iter_video(
    path: Path,
    *,
    loop: bool,
    image_transform: Callable[[Image.Image], Image.Image] | None = None,
) -> Iterator[TimedFrame]:
    try:
        import av
    except ImportError as exc:
        raise MediaError(
            "Video playback requires PyAV; install the project dependencies first"
        ) from exc

    while True:
        try:
            container = av.open(str(path))
        except av.error.FFmpegError as exc:
            raise MediaError(f"Could not open media file: {path}") from exc

        decoded_any = False
        with container:
            video_streams = container.streams.video
            if not video_streams:
                raise MediaError(f"Media contains no video stream: {path}")
            stream = video_streams[0]
            source_rate = float(stream.average_rate) if stream.average_rate else 20.0
            output_rate = min(source_rate, MAX_VIDEO_FPS)
            fallback_duration = max(1.0 / output_rate, MIN_FRAME_DURATION)
            minimum_output_interval = 1.0 / MAX_VIDEO_FPS

            previous_image = None
            previous_time: float | None = None
            decoded_index = 0
            for decoded in container.decode(stream):
                decoded_any = True
                image = decoded.to_image()
                timestamp = (
                    float(decoded.time)
                    if decoded.time is not None
                    else decoded_index / source_rate
                )
                decoded_index += 1

                if previous_image is None:
                    previous_image = image
                    previous_time = timestamp
                    continue

                assert previous_time is not None
                elapsed = timestamp - previous_time
                if elapsed + 1e-9 < minimum_output_interval:
                    continue

                rendered = prepare_image(previous_image)
                if image_transform:
                    rendered = image_transform(rendered)
                yield build_frame(rendered), max(elapsed, MIN_FRAME_DURATION)
                previous_image = image
                previous_time = timestamp

            if previous_image is not None:
                rendered = prepare_image(previous_image)
                if image_transform:
                    rendered = image_transform(rendered)
                yield build_frame(rendered), fallback_duration

        if not decoded_any:
            raise MediaError(f"Video stream contains no decodable frames: {path}")
        if not loop:
            return
