from __future__ import annotations

import unittest
from unittest.mock import patch

from b360gt.device_init import HEARTBEAT_REPORT, issue_report
from b360gt.usb_transport import DeviceSafetyError, find_display


class FakeFeatureChannel:
    def __init__(self) -> None:
        self.writes: list[bytes] = []

    def set_feature(self, report: bytes) -> None:
        self.writes.append(report)

    def get_feature(self) -> bytes:
        return bytes(8)

    def close(self) -> None:
        pass


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


if __name__ == "__main__":
    unittest.main()
