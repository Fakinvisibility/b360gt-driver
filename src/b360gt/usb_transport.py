"""Strictly scoped USB access for the B360GT display interface."""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from threading import Event

import usb.backend.libusb0
import usb.backend.libusb1
import usb.core
import usb.util

from .device_init import (
    HID_INTERFACE,
    disable_display,
    enable_after_first_frame,
    find_hid_interface,
    heartbeat,
    initialize_display,
    open_feature_channel,
)
from .protocol import FRAME_HEADER, FRAME_SIZE, FRAME_TRAILER

VID = 0x345F
PID = 0x9132
DISPLAY_INTERFACE = 3
DISPLAY_ENDPOINT = 0x04
USB_CHUNK_SIZE = 65536
MAX_REPEAT_RATE = 30.0
DISPLAY_PREROLL_FRAMES = 2


class DeviceSafetyError(RuntimeError):
    """Raised when the connected device does not match the verified interface."""


@dataclass(frozen=True)
class DeviceInfo:
    vid: int
    pid: int
    bus: int | None
    address: int | None
    interface_number: int
    endpoint_address: int
    endpoint_max_packet_size: int


def _backend():
    if os.name == "nt":
        system_root = os.environ.get("SystemRoot", r"C:\Windows")
        dll_path = os.path.join(system_root, "System32", "libusb0.dll")
        backend = usb.backend.libusb0.get_backend(find_library=lambda _: dll_path)
        if backend is None:
            raise RuntimeError(f"Could not load libusb-win32 backend from {dll_path}")
        return backend

    backend = usb.backend.libusb1.get_backend()
    if backend is None:
        raise RuntimeError("Could not load libusb-1.0")
    return backend


def _matching_devices() -> list[usb.core.Device]:
    devices: Iterable[usb.core.Device] = usb.core.find(
        find_all=True,
        idVendor=VID,
        idProduct=PID,
        backend=_backend(),
    )
    return list(devices)


def find_display() -> usb.core.Device:
    devices = _matching_devices()
    if not devices:
        raise DeviceSafetyError(f"B360GT display {VID:04X}:{PID:04X} was not found")
    if len(devices) != 1:
        raise DeviceSafetyError(
            f"Expected one B360GT display, found {len(devices)}; refusing ambiguous access"
        )
    return devices[0]


def validate_display_interface(device: usb.core.Device) -> DeviceInfo:
    if device.idVendor != VID or device.idProduct != PID:
        raise DeviceSafetyError("USB identity changed after discovery")

    configuration = device.get_active_configuration()
    if os.name != "nt":
        control_interface = usb.util.find_descriptor(
            configuration,
            bInterfaceNumber=HID_INTERFACE,
            bAlternateSetting=0,
        )
        if control_interface is None:
            raise DeviceSafetyError(
                f"Verified HID interface {HID_INTERFACE} is not present"
            )
        if control_interface.bInterfaceClass != 0x03:
            raise DeviceSafetyError(
                f"Interface {HID_INTERFACE} class is "
                f"0x{control_interface.bInterfaceClass:02X}, expected HID 0x03"
            )

    interface = usb.util.find_descriptor(
        configuration,
        bInterfaceNumber=DISPLAY_INTERFACE,
        bAlternateSetting=0,
    )
    if interface is None:
        raise DeviceSafetyError(
            f"Verified interface {DISPLAY_INTERFACE} is not present"
        )

    if interface.bInterfaceClass != 0xFF:
        raise DeviceSafetyError(
            f"Interface {DISPLAY_INTERFACE} class is 0x{interface.bInterfaceClass:02X}, "
            "expected vendor-specific 0xFF"
        )

    endpoint = usb.util.find_descriptor(
        interface,
        bEndpointAddress=DISPLAY_ENDPOINT,
    )
    if endpoint is None:
        raise DeviceSafetyError(
            f"Verified Bulk OUT endpoint 0x{DISPLAY_ENDPOINT:02X} is not present"
        )

    transfer_type = endpoint.bmAttributes & 0x03
    if transfer_type != usb.util.ENDPOINT_TYPE_BULK:
        raise DeviceSafetyError(
            f"Endpoint 0x{DISPLAY_ENDPOINT:02X} is not Bulk"
        )
    if usb.util.endpoint_direction(endpoint.bEndpointAddress) != usb.util.ENDPOINT_OUT:
        raise DeviceSafetyError(
            f"Endpoint 0x{DISPLAY_ENDPOINT:02X} is not OUT"
        )

    return DeviceInfo(
        vid=device.idVendor,
        pid=device.idProduct,
        bus=getattr(device, "bus", None),
        address=getattr(device, "address", None),
        interface_number=interface.bInterfaceNumber,
        endpoint_address=endpoint.bEndpointAddress,
        endpoint_max_packet_size=endpoint.wMaxPacketSize,
    )


def probe() -> DeviceInfo:
    """Read and validate descriptors without claiming or writing the interface."""
    find_hid_interface()
    return validate_display_interface(find_display())


def send_frame(frame: bytes, *, timeout_ms: int = 5000) -> int:
    """Send one verified protocol frame using the observed 64 KiB URB grouping."""
    device = find_display()
    validate_display_interface(device)

    claimed = False
    try:
        configuration = device.get_active_configuration()
        interface = usb.util.find_descriptor(
            configuration,
            bInterfaceNumber=DISPLAY_INTERFACE,
            bAlternateSetting=0,
        )
        if interface is None:
            raise DeviceSafetyError(
                f"Verified interface {DISPLAY_INTERFACE} disappeared before claim"
            )

        usb.util.claim_interface(device, interface)
        claimed = True
        return _write_frame(device, frame, timeout_ms)
    finally:
        if claimed:
            usb.util.release_interface(device, interface)
        usb.util.dispose_resources(device)


def stream_frame(
    frame: bytes,
    *,
    duration_seconds: float | None = None,
    frame_rate: float = 2.0,
    timeout_ms: int = 5000,
    stop_event: Event | None = None,
    progress_callback: Callable[[int], None] | None = None,
) -> int:
    """Initialize the controller and repeatedly display one frame."""
    if not 1.0 <= frame_rate <= MAX_REPEAT_RATE:
        raise ValueError(f"frame_rate must be between 1 and {MAX_REPEAT_RATE:g}")

    def repeated_frame() -> Iterable[tuple[bytes, float]]:
        while True:
            yield frame, 1.0 / frame_rate

    return stream_frames(
        repeated_frame(),
        duration_seconds=duration_seconds,
        repeat_rate=frame_rate,
        timeout_ms=timeout_ms,
        stop_event=stop_event,
        progress_callback=progress_callback,
    )


def stream_frames(
    frames: Iterable[tuple[bytes, float]],
    *,
    duration_seconds: float | None = None,
    repeat_rate: float = 2.0,
    timeout_ms: int = 5000,
    stop_event: Event | None = None,
    frame_change_event: Event | None = None,
    progress_callback: Callable[[int], None] | None = None,
) -> int:
    """Initialize the display and play timed frames.

    Each item is ``(complete_usb_frame, display_duration_seconds)``. Frames are
    repeated at ``repeat_rate`` while held so the device watchdog stays active.
    """
    if duration_seconds is not None and duration_seconds <= 0:
        raise ValueError("duration_seconds must be positive")
    if not 1.0 <= repeat_rate <= MAX_REPEAT_RATE:
        raise ValueError(f"repeat_rate must be between 1 and {MAX_REPEAT_RATE:g}")

    iterator = iter(frames)
    try:
        first_frame, first_duration = next(iterator)
    except StopIteration as exc:
        raise ValueError("frames must contain at least one item") from exc

    device = find_display()
    validate_display_interface(device)
    control = open_feature_channel(device)
    claimed = False
    detached_kernel_driver = False
    display_enabled = False
    try:
        initialize_display(control)

        configuration = device.get_active_configuration()
        interface = usb.util.find_descriptor(
            configuration,
            bInterfaceNumber=DISPLAY_INTERFACE,
            bAlternateSetting=0,
        )
        if interface is None:
            raise DeviceSafetyError(
                f"Verified interface {DISPLAY_INTERFACE} disappeared before claim"
            )

        if os.name != "nt":
            try:
                if device.is_kernel_driver_active(DISPLAY_INTERFACE):
                    device.detach_kernel_driver(DISPLAY_INTERFACE)
                    detached_kernel_driver = True
            except (NotImplementedError, usb.core.USBError):
                # Most B360GT systems have no kernel driver bound to the
                # vendor-specific display interface.
                pass

        usb.util.claim_interface(device, interface)
        claimed = True
        # The controller can expose its green initial framebuffer if display
        # enable follows the first transfer immediately. Preloading the same
        # complete target frame twice lets the controller latch stable content
        # before the captured display-enable reports are sent.
        total = 0
        for _ in range(DISPLAY_PREROLL_FRAMES):
            total += _write_frame(device, first_frame, timeout_ms)
            if progress_callback is not None:
                progress_callback(total)
        enable_after_first_frame(control)
        display_enabled = True

        start = time.monotonic()
        deadline = None if duration_seconds is None else start + duration_seconds
        repeat_interval = 1.0 / repeat_rate
        next_heartbeat = start + 0.5
        timeline = start
        first_already_sent = True

        def all_frames():
            yield first_frame, first_duration
            yield from iterator

        source_changed = False
        for frame, frame_duration in all_frames():
            if stop_event is not None and stop_event.is_set():
                return total
            if frame_change_event is not None and frame_change_event.is_set():
                source_changed = True
                continue
            if frame_duration <= 0:
                raise ValueError("frame durations must be positive")
            if source_changed:
                # Frame decoding happens before the loop body. Reset the
                # timeline after that work so the first frame from a newly
                # selected source is always transmitted immediately.
                timeline = time.monotonic()
                source_changed = False
            timeline += frame_duration
            already_sent = first_already_sent
            first_already_sent = False

            while True:
                if stop_event is not None and stop_event.is_set():
                    return total
                now = time.monotonic()
                if deadline is not None and now >= deadline:
                    return total
                if now >= timeline:
                    break

                if not already_sent:
                    total += _write_frame(device, frame, timeout_ms)
                    if progress_callback is not None:
                        progress_callback(total)
                    already_sent = True

                now = time.monotonic()
                if now >= next_heartbeat:
                    heartbeat(control)
                    while next_heartbeat <= now:
                        next_heartbeat += 0.5

                wake_at = min(timeline, now + repeat_interval)
                if deadline is not None:
                    wake_at = min(wake_at, deadline)
                delay = wake_at - time.monotonic()
                if delay > 0:
                    if frame_change_event is not None:
                        if frame_change_event.wait(delay):
                            source_changed = True
                            break
                    else:
                        time.sleep(delay)
                already_sent = False
        return total
    finally:
        if display_enabled:
            disable_display(control)
        if claimed:
            usb.util.release_interface(device, interface)
        if detached_kernel_driver:
            try:
                device.attach_kernel_driver(DISPLAY_INTERFACE)
            except (NotImplementedError, usb.core.USBError):
                pass
        control.close()
        usb.util.dispose_resources(device)


def _write_frame(device: usb.core.Device, frame: bytes, timeout_ms: int) -> int:
    if (
        len(frame) != FRAME_SIZE
        or not frame.startswith(FRAME_HEADER)
        or not frame.endswith(FRAME_TRAILER)
    ):
        raise ValueError("Refusing to send data that is not a verified B360GT frame")

    total = 0
    for offset in range(0, len(frame), USB_CHUNK_SIZE):
        chunk = frame[offset : offset + USB_CHUNK_SIZE]
        written = device.write(DISPLAY_ENDPOINT, chunk, timeout=timeout_ms)
        if written != len(chunk):
            raise IOError(
                f"Short USB write at offset {offset}: {written}/{len(chunk)} bytes"
            )
        total += written
    return total
