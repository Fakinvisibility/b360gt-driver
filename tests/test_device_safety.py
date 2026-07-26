from __future__ import annotations

import unittest
from threading import Event
from unittest.mock import patch

import usb.core

from b360gt.device_init import (
    DISPLAY_DISABLE_REPORT,
    HEARTBEAT_REPORT,
    disable_display,
    issue_report,
)
from b360gt.usb_transport import DeviceSafetyError, find_display, stream_frames


class FakeFeatureChannel:
    def __init__(self) -> None:
        self.writes: list[bytes] = []

    def set_feature(self, report: bytes) -> None:
        self.writes.append(report)

    def get_feature(self) -> bytes:
        return bytes(8)

    def close(self) -> None:
        pass


class FakeDisplay:
    def get_active_configuration(self):
        return object()

    def is_kernel_driver_active(self, _interface: int) -> bool:
        return False


class DeviceSafetyTests(unittest.TestCase):
    def test_one_matching_unit_is_selected_without_serial_or_address(self) -> None:
        unit = object()
        with patch(
            "b360gt.usb_transport._matching_devices",
            return_value=[unit],
        ):
            self.assertIs(find_display(), unit)

    def test_no_matching_unit_is_rejected(self) -> None:
        with patch(
            "b360gt.usb_transport._matching_devices",
            return_value=[],
        ):
            with self.assertRaises(DeviceSafetyError):
                find_display()

    def test_multiple_matching_units_are_rejected_as_ambiguous(self) -> None:
        with patch(
            "b360gt.usb_transport._matching_devices",
            return_value=[object(), object()],
        ):
            with self.assertRaises(DeviceSafetyError):
                find_display()

    def test_verified_heartbeat_report_is_allowed(self) -> None:
        channel = FakeFeatureChannel()
        issue_report(channel, HEARTBEAT_REPORT)
        self.assertEqual(channel.writes, [HEARTBEAT_REPORT])

    def test_unknown_hid_report_is_rejected_before_usb_write(self) -> None:
        channel = FakeFeatureChannel()
        with self.assertRaises(ValueError):
            issue_report(channel, bytes.fromhex("0102030405060708"))
        self.assertEqual(channel.writes, [])

    def test_display_disable_uses_captured_allowlisted_report(self) -> None:
        channel = FakeFeatureChannel()

        disable_display(channel)

        self.assertEqual(channel.writes, [DISPLAY_DISABLE_REPORT])

    def test_frame_source_switch_keeps_one_usb_session(self) -> None:
        changed = Event()
        sent: list[bytes] = []
        first = b"first"
        stale = b"stale"
        latest = b"latest"

        def frames():
            yield first, 0.01
            changed.set()
            yield stale, 0.01
            changed.clear()
            yield latest, 0.01

        channel = FakeFeatureChannel()
        interface = object()
        with (
            patch("b360gt.usb_transport.os.name", "posix"),
            patch("b360gt.usb_transport.find_display", return_value=FakeDisplay()),
            patch("b360gt.usb_transport.validate_display_interface"),
            patch("b360gt.usb_transport.open_feature_channel", return_value=channel),
            patch("b360gt.usb_transport.initialize_display") as initialize,
            patch(
                "b360gt.usb_transport.enable_after_first_frame",
                side_effect=lambda _control: sent.append(b"enabled"),
            ),
            patch(
                "b360gt.usb_transport.disable_display",
                side_effect=lambda _control: sent.append(b"disabled"),
            ),
            patch("b360gt.usb_transport.usb.util.find_descriptor", return_value=interface),
            patch("b360gt.usb_transport.usb.util.claim_interface") as claim,
            patch("b360gt.usb_transport.usb.util.release_interface"),
            patch("b360gt.usb_transport.usb.util.dispose_resources"),
            patch(
                "b360gt.usb_transport._write_frame",
                side_effect=lambda _device, frame, _timeout: (
                    sent.append(frame) or len(frame)
                ),
            ),
        ):
            stream_frames(
                frames(),
                repeat_rate=2,
                frame_change_event=changed,
            )

        self.assertEqual(initialize.call_count, 1)
        self.assertEqual(claim.call_count, 1)
        self.assertEqual(sent[:3], [first, first, b"enabled"])
        self.assertIn(first, sent)
        self.assertIn(latest, sent)
        self.assertNotIn(stale, sent)
        self.assertEqual(sent[-1], b"disabled")

    def test_usb_reset_cleanup_does_not_mask_transfer_error(self) -> None:
        channel = FakeFeatureChannel()
        interface = object()
        transfer_error = usb.core.USBError("No such device")

        with (
            patch("b360gt.usb_transport.os.name", "posix"),
            patch("b360gt.usb_transport.find_display", return_value=FakeDisplay()),
            patch("b360gt.usb_transport.validate_display_interface"),
            patch("b360gt.usb_transport.open_feature_channel", return_value=channel),
            patch("b360gt.usb_transport.initialize_display"),
            patch("b360gt.usb_transport.usb.util.find_descriptor", return_value=interface),
            patch("b360gt.usb_transport.usb.util.claim_interface"),
            patch(
                "b360gt.usb_transport.usb.util.release_interface",
                side_effect=usb.core.USBError(
                    "did not claim interface 3 before use"
                ),
            ),
            patch("b360gt.usb_transport.usb.util.dispose_resources"),
            patch(
                "b360gt.usb_transport._write_frame",
                side_effect=transfer_error,
            ),
            self.assertLogs("b360gt.usb_transport", level="WARNING"),
        ):
            with self.assertRaises(usb.core.USBError) as raised:
                stream_frames([(b"frame", 0.01)])

        self.assertIs(raised.exception, transfer_error)


if __name__ == "__main__":
    unittest.main()
