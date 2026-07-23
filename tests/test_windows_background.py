import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from b360gt import windows_background


class WindowsBackgroundTests(unittest.TestCase):
    def test_runs_ui_silently_and_writes_log_under_local_appdata(self):
        with tempfile.TemporaryDirectory() as temporary:
            with (
                patch.dict(os.environ, {"LOCALAPPDATA": temporary}),
                patch.object(
                    windows_background,
                    "_acquire_instance_mutex",
                    return_value=object(),
                ),
                patch.object(windows_background, "_release_instance_mutex"),
                patch.object(windows_background, "run_ui") as run_ui,
            ):
                result = windows_background.main()

            self.assertEqual(result, 0)
            kwargs = run_ui.call_args.kwargs
            self.assertEqual(kwargs["port"], 8765)
            self.assertFalse(kwargs["open_browser"])
            self.assertTrue(kwargs["quiet"])
            self.assertIsNotNone(kwargs["shutdown_event"])
            log = Path(temporary) / "b360gt" / "logs" / "background.log"
            self.assertTrue(log.is_file())
            self.assertIn("Starting B360GT", log.read_text(encoding="utf-8"))

    def test_returns_failure_and_logs_startup_error(self):
        with tempfile.TemporaryDirectory() as temporary:
            with (
                patch.dict(os.environ, {"LOCALAPPDATA": temporary}),
                patch.object(
                    windows_background,
                    "_acquire_instance_mutex",
                    return_value=object(),
                ),
                patch.object(windows_background, "_release_instance_mutex"),
                patch.object(
                    windows_background,
                    "run_ui",
                    side_effect=RuntimeError("port unavailable"),
                ),
            ):
                result = windows_background.main()

            self.assertEqual(result, 1)
            log = Path(temporary) / "b360gt" / "logs" / "background.log"
            self.assertIn("port unavailable", log.read_text(encoding="utf-8"))

    def test_stop_reports_when_service_is_not_running(self):
        with tempfile.TemporaryDirectory() as temporary:
            with patch.dict(os.environ, {"LOCALAPPDATA": temporary}):
                self.assertFalse(windows_background.request_stop())

    def test_status_reports_when_service_is_not_running(self):
        with tempfile.TemporaryDirectory() as temporary:
            with patch.dict(os.environ, {"LOCALAPPDATA": temporary}):
                self.assertEqual(windows_background.status(), (False, None))

    def test_duplicate_launcher_exits_without_starting_another_ui(self):
        with tempfile.TemporaryDirectory() as temporary:
            pid = Path(temporary) / "b360gt" / "background.pid"
            pid.parent.mkdir(parents=True)
            pid.write_text("existing-instance", encoding="utf-8")
            with (
                patch.dict(os.environ, {"LOCALAPPDATA": temporary}),
                patch.object(
                    windows_background,
                    "_acquire_instance_mutex",
                    return_value=None,
                ),
                patch.object(windows_background, "run_ui") as run_ui,
            ):
                result = windows_background.main()

            self.assertEqual(result, 0)
            run_ui.assert_not_called()
            self.assertEqual(pid.read_text(encoding="utf-8"), "existing-instance")

    def test_only_pid_owner_removes_background_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            pid = Path(temporary) / "b360gt" / "background.pid"
            pid.parent.mkdir(parents=True)
            pid.write_text("existing-instance", encoding="utf-8")
            existing = type("Process", (), {"pid": 12345})()
            mutex = object()
            with (
                patch.dict(os.environ, {"LOCALAPPDATA": temporary}),
                patch.object(
                    windows_background,
                    "_acquire_instance_mutex",
                    return_value=mutex,
                ),
                patch.object(
                    windows_background,
                    "_release_instance_mutex",
                ) as release,
                patch.object(
                    windows_background,
                    "_running_process",
                    return_value=existing,
                ),
                patch.object(windows_background.os, "getpid", return_value=54321),
                patch.object(windows_background, "run_ui") as run_ui,
            ):
                result = windows_background.main()

            self.assertEqual(result, 0)
            run_ui.assert_not_called()
            release.assert_called_once_with(mutex)
            self.assertEqual(pid.read_text(encoding="utf-8"), "existing-instance")


if __name__ == "__main__":
    unittest.main()
