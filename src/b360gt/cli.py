"""Command-line interface for B360GT development tools."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

from .protocol import FRAME_SIZE, build_frame


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="b360gt",
        description="Experimental Valkyrie B360GT display utility",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    encode = subparsers.add_parser(
        "encode",
        help="convert an image into one captured-protocol frame",
    )
    encode.add_argument("image", type=Path)
    encode.add_argument("output", type=Path)

    subparsers.add_parser(
        "probe",
        help="read and validate the whitelisted USB display descriptors",
    )

    send = subparsers.add_parser(
        "send",
        help="encode and continuously stream an image to the display",
    )
    send.add_argument("image", type=Path)
    send.add_argument(
        "--seconds",
        type=float,
        help="stop after this many seconds (default: run until Ctrl+C)",
    )
    send.add_argument(
        "--fps",
        type=float,
        default=2.0,
        help="streaming frame rate (default: 2)",
    )

    play = subparsers.add_parser(
        "play",
        help="play an image, animated image, or video",
    )
    play.add_argument("media", type=Path)
    play.add_argument(
        "--seconds",
        type=float,
        help="stop after this many seconds (default: loop until Ctrl+C)",
    )

    ui = subparsers.add_parser(
        "ui",
        help="open the local browser control panel",
    )
    ui.add_argument(
        "--port",
        type=int,
        default=8765,
        help="local HTTP port (default: 8765; use 0 for automatic)",
    )
    ui.add_argument(
        "--no-browser",
        action="store_true",
        help="start the control panel without opening a browser",
    )
    ui.add_argument(
        "--managed-background",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    subparsers.add_parser("start", help="start the silent background service")
    subparsers.add_parser("stop", help="stop the background service")
    subparsers.add_parser("status", help="show the background service status")
    return parser


def main() -> int:
    args = build_parser().parse_args()

    if args.command == "encode":
        frame = build_frame(args.image)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(frame)
        print(f"Wrote {len(frame)} bytes to {args.output}")
        if len(frame) != FRAME_SIZE:
            return 1
        return 0

    if args.command == "probe":
        from .usb_transport import probe

        info = probe()
        print(
            f"Found {info.vid:04X}:{info.pid:04X}; "
            f"bus={info.bus}, address={info.address}, "
            f"interface={info.interface_number}, "
            f"endpoint=0x{info.endpoint_address:02X}, "
            f"max_packet={info.endpoint_max_packet_size}"
        )
        return 0

    if args.command == "send":
        from .usb_transport import stream_frame

        frame = build_frame(args.image)
        try:
            written = stream_frame(
                frame,
                duration_seconds=args.seconds,
                frame_rate=args.fps,
            )
        except KeyboardInterrupt:
            print("\nStopped by user; the display will return to its built-in logo.")
            return 0
        if args.seconds is None:
            print(f"Streamed {written} bytes to the B360GT display")
        else:
            print(
                f"Streamed {written} bytes to the B360GT display "
                f"for {args.seconds:g} seconds at {args.fps:g} fps"
            )
        return 0

    if args.command == "play":
        from .media import iter_media_frames
        from .usb_transport import stream_frames

        frames = iter_media_frames(args.media, loop=True)
        try:
            written = stream_frames(
                frames,
                duration_seconds=args.seconds,
                repeat_rate=2.0,
            )
        except KeyboardInterrupt:
            print("\nStopped by user; the display will return to its built-in logo.")
            return 0
        print(f"Playback completed after streaming {written} bytes")
        return 0

    if args.command == "ui":
        from .web_ui import run_ui

        run_ui(
            port=args.port,
            open_browser=not args.no_browser,
            quiet=args.managed_background,
            managed_background=args.managed_background,
        )
        return 0

    if args.command == "start":
        if os.name == "nt":
            from .windows_background import start_main
        elif sys.platform.startswith("linux"):
            from .linux_background import start_main
        else:
            print("启动失败：当前平台不支持后台控制台")
            return 1

        return start_main()

    if args.command == "stop":
        if os.name == "nt":
            from .windows_background import stop_main
        elif sys.platform.startswith("linux"):
            from .linux_background import stop_main
        else:
            print("停止失败：当前平台不支持后台控制台")
            return 1

        return stop_main()

    if args.command == "status":
        if os.name == "nt":
            from .windows_background import status_main
        elif sys.platform.startswith("linux"):
            from .linux_background import status_main
        else:
            print("B360GT 后台服务状态不受当前平台支持")
            return 1

        return status_main()

    raise AssertionError(f"Unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
