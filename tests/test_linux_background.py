import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from b360gt import linux_background


def result(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(
        args=["systemctl"],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


class LinuxBackgroundTests(unittest.TestCase):
    def test_packaged_ui_service_follows_graphical_session(self):
        service = (
            Path(__file__).parents[1]
            / "packaging"
            / "arch"
            / "b360gt-ui.service"
        ).read_text(encoding="utf-8")

        self.assertIn("After=graphical-session.target", service)
        self.assertIn("PartOf=graphical-session.target", service)
        self.assertIn("WantedBy=graphical-session.target", service)
        self.assertNotIn("WantedBy=default.target", service)

    def test_status_reports_active_service_pid(self):
        with patch.object(
            linux_background,
            "_systemctl",
            side_effect=[result(), result(stdout="1234\n")],
        ) as systemctl:
            self.assertEqual(linux_background.status(), (True, 1234))

        self.assertEqual(
            [call.args for call in systemctl.call_args_list],
            [
                ("is-active", "--quiet"),
                ("show", "--property=MainPID", "--value"),
            ],
        )

    def test_status_reports_inactive_service(self):
        with patch.object(
            linux_background,
            "_systemctl",
            return_value=result(returncode=3),
        ):
            self.assertEqual(linux_background.status(), (False, None))

    def test_start_starts_inactive_service(self):
        with (
            patch.object(
                linux_background,
                "status",
                side_effect=[(False, None), (True, 4321)],
            ),
            patch.object(
                linux_background,
                "_systemctl",
                return_value=result(),
            ) as systemctl,
        ):
            self.assertEqual(linux_background.start(), (True, 4321))

        systemctl.assert_called_once_with("start")

    def test_start_returns_existing_service_without_restart(self):
        with (
            patch.object(
                linux_background,
                "status",
                return_value=(True, 2468),
            ),
            patch.object(linux_background, "_systemctl") as systemctl,
        ):
            self.assertEqual(linux_background.start(), (False, 2468))

        systemctl.assert_not_called()

    def test_start_surfaces_systemd_error(self):
        with (
            patch.object(
                linux_background,
                "status",
                return_value=(False, None),
            ),
            patch.object(
                linux_background,
                "_systemctl",
                return_value=result(returncode=5, stderr="unit not found\n"),
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "unit not found"):
                linux_background.start()

    def test_stop_stops_active_service(self):
        with (
            patch.object(
                linux_background,
                "status",
                return_value=(True, 1357),
            ),
            patch.object(
                linux_background,
                "_systemctl",
                return_value=result(),
            ) as systemctl,
        ):
            self.assertTrue(linux_background.request_stop())

        systemctl.assert_called_once_with("stop")

    def test_stop_is_successful_when_service_is_inactive(self):
        with (
            patch.object(
                linux_background,
                "status",
                return_value=(False, None),
            ),
            patch.object(linux_background, "_systemctl") as systemctl,
        ):
            self.assertFalse(linux_background.request_stop())

        systemctl.assert_not_called()


if __name__ == "__main__":
    unittest.main()
