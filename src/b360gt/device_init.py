"""Display-controller initialization captured from a normal MythCool startup."""

from __future__ import annotations

import time
from typing import Protocol


VID = 0x345F
PID = 0x9132
HID_INTERFACE = 0


class FeatureChannel(Protocol):
    def set_feature(self, report: bytes) -> None: ...

    def get_feature(self) -> bytes: ...

    def close(self) -> None: ...


def find_hid_interface() -> dict:
    """Return the one verified HID interface without opening or writing it."""
    try:
        import hid
    except ImportError as exc:
        raise RuntimeError(
            "Display initialization requires the 'hidapi' Python package"
        ) from exc

    entries = hid.enumerate(VID, PID)
    matches = [
        entry
        for entry in entries
        if entry.get("interface_number") == HID_INTERFACE
        and entry.get("usage_page") in (None, 0, 0xFF00)
    ]
    if not matches:
        matches = [
            entry
            for entry in entries
            if entry.get("interface_number") == HID_INTERFACE
        ]
    if len(matches) != 1:
        raise RuntimeError(
            f"Expected one HID interface for {VID:04X}:{PID:04X}, "
            f"found {len(matches)}"
        )
    return matches[0]


class HidApiFeatureChannel:
    """Cross-platform feature-report transport through HIDAPI."""

    def __init__(self) -> None:
        import hid

        self._device = hid.device()
        self._device.open_path(find_hid_interface()["path"])

    def set_feature(self, report: bytes) -> None:
        # HIDAPI includes the report ID in its buffer. This device has no
        # numbered reports, so report ID zero precedes the captured 8 bytes.
        packet = b"\x00" + report
        written = self._device.send_feature_report(packet)
        if written != len(packet):
            raise IOError(f"Short HID feature write: {written}/{len(packet)} bytes")

    def get_feature(self) -> bytes:
        result = bytes(self._device.get_feature_report(0, 9))
        if len(result) == 9 and result[0] == 0:
            result = result[1:]
        if len(result) != 8:
            raise IOError(f"Unexpected HID feature read length: {len(result)}")
        return result

    def close(self) -> None:
        self._device.close()


def open_feature_channel(device) -> FeatureChannel:
    # Keep the PyUSB device argument so callers can use one platform-neutral
    # factory. HIDAPI intentionally owns interface 0 while PyUSB owns interface 3.
    del device
    return HidApiFeatureChannel()


# (milliseconds from first report, 8-byte HID feature report)
# Captured only from an ordinary MythCool startup. Firmware-upgrade traffic was
# never captured and is intentionally outside this project.
STARTUP_REPORTS = (
    (0.000, "a603030000000000"),
    (21.837, "b5c5580000000000"),
    (27.258, "b6deee0100000000"),
    (30.239, "a607010200000000"),
    (147.011, "b5c4540000000000"),
    (152.241, "a605000000000000"),
    (177.346, "b5c5550000000000"),
    (183.259, "b5f0040000000000"),
    (189.276, "b6f0046d00000000"),
    (192.239, "f5001fe000000000"),
    (198.236, "f5001fe800000000"),
    (204.243, "f5001ff000000000"),
    (210.241, "f5001ff800000000"),
    (216.233, "b5c4240000000000"),
    (222.230, "b5c6500000000000"),
    (228.239, "b5c30f0000000000"),
    (234.238, "b5ff000000000000"),
    (240.290, "b5f0000000000000"),
    (246.257, "b500310000000000"),
    (252.254, "b500300000000000"),
    (270.632, "b500320000000000"),
    (1262.877, "b500320000000000"),
    (1278.596, "b5c0000000000000"),
    (1284.263, "b5c0040000000000"),
    (1290.266, "b5c0080000000000"),
    (1296.260, "b5c00c0000000000"),
    (1302.277, "b5c0100000000000"),
    (1308.275, "b5c0140000000000"),
    (1314.273, "b5c0180000000000"),
    (1320.267, "b5c01c0000000000"),
    (1326.310, "b5c0200000000000"),
    (1332.273, "b5c0240000000000"),
    (1338.269, "b5c0280000000000"),
    (1344.275, "b5c02c0000000000"),
    (1350.267, "b5c0300000000000"),
    (1356.273, "b5c0340000000000"),
    (1362.265, "b5c0380000000000"),
    (1368.285, "b5c03c0000000000"),
    (1374.269, "b5c0400000000000"),
    (1380.343, "b5c0440000000000"),
    (1386.272, "b5c0480000000000"),
    (1392.274, "b5c04c0000000000"),
    (1398.274, "b5c0500000000000"),
    (1404.265, "b5c0540000000000"),
    (1410.274, "b5c0580000000000"),
    (1416.265, "b5c05c0000000000"),
    (1422.307, "b5c0600000000000"),
    (1428.268, "b5c0640000000000"),
    (1434.268, "b5c0680000000000"),
    (1440.273, "b5c06c0000000000"),
    (1446.266, "b5c0700000000000"),
    (1452.269, "b5c0740000000000"),
    (1458.271, "b5c0780000000000"),
    (1464.277, "b5c07c0000000000"),
    (1472.005, "f5001fe000000000"),
    (1477.268, "f5001fe800000000"),
    (1483.277, "f5001ff000000000"),
    (1489.317, "f5001ff800000000"),
    (1495.275, "b500320000000000"),
    (1512.517, "a605000000000000"),
    (1525.644, "b5c5550000000000"),
    (1531.284, "b5f0050000000000"),
    (1537.289, "b6f0050000000000"),
    (1540.264, "a604000000000000"),
    (1554.062, "b5c5550000000000"),
    (1682.472, "b500320000000000"),
    (1688.327, "a603030000000000"),
    (1713.905, "b5c5580000000000"),
    (1719.281, "a60101e001e02200"),
    (1745.227, "b5c5550000000000"),
    (1750.285, "a6028f0001e001e0"),
    (1776.715, "b5c5570000000000"),
    (1791.946, "b5c5570000000000"),
    (1807.475, "b5c5570000000000"),
    (1823.209, "b5c5570000000000"),
    (1838.572, "b5c5570000000000"),
    (1844.276, "a604010000000000"),
    (1869.866, "b5c5550000000000"),
    (2010.816, "b6f24e0000000000"),
    (2181.958, "b500320000000000"),
    (2524.434, "b5f2420000000000"),
)

POST_FIRST_FRAME_REPORTS = (
    "b5f0050000000000",
    "b6f0051000000000",
    "a605010000000000",
    "b5c5550000000000",
)

HEARTBEAT_REPORT = bytes.fromhex("b500320000000000")
DISPLAY_DISABLE_REPORT = bytes.fromhex("a605000000000000")

SAFE_FEATURE_REPORTS = frozenset(
    bytes.fromhex(report_hex)
    for _, report_hex in STARTUP_REPORTS
) | frozenset(
    bytes.fromhex(report_hex)
    for report_hex in POST_FIRST_FRAME_REPORTS
) | {HEARTBEAT_REPORT}


def set_feature(channel: FeatureChannel, report: bytes) -> None:
    if len(report) != 8:
        raise ValueError(f"Feature report must be 8 bytes, got {len(report)}")
    if report not in SAFE_FEATURE_REPORTS:
        raise ValueError("Refusing HID report outside the verified display allowlist")
    channel.set_feature(report)


def get_feature(channel: FeatureChannel) -> bytes:
    return channel.get_feature()


def issue_report(channel: FeatureChannel, report: bytes) -> bytes | None:
    set_feature(channel, report)
    # B5/F5 requests are followed by GET_REPORT in the MythCool capture.
    if report[0] in (0xB5, 0xF5):
        return get_feature(channel)
    return None


def initialize_display(channel: FeatureChannel) -> None:
    start = time.monotonic()
    for target_ms, report_hex in STARTUP_REPORTS:
        remaining = target_ms / 1000.0 - (time.monotonic() - start)
        if remaining > 0:
            time.sleep(remaining)
        issue_report(channel, bytes.fromhex(report_hex))


def enable_after_first_frame(channel: FeatureChannel) -> None:
    for report_hex in POST_FIRST_FRAME_REPORTS:
        issue_report(channel, bytes.fromhex(report_hex))
        time.sleep(0.003)


def disable_display(channel: FeatureChannel) -> None:
    """Disable host-frame display using the captured counterpart to A6 05 01."""
    issue_report(channel, DISPLAY_DISABLE_REPORT)


def heartbeat(channel: FeatureChannel) -> None:
    issue_report(channel, HEARTBEAT_REPORT)
