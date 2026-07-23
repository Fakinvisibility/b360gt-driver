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
                patch.object(windows_background, "run_ui") as run_ui,
            ):
                result = windows_background.main()

            self.assertEqual(result, 0)
            run_ui.assert_called_once_with(
                port=8765,
                open_browser=False,
                quiet=True,
            )
            log = Path(temporary) / "b360gt" / "logs" / "background.log"
            self.assertTrue(log.is_file())
            self.assertIn("Starting B360GT", log.read_text(encoding="utf-8"))

    def test_returns_failure_and_logs_startup_error(self):
        with tempfile.TemporaryDirectory() as temporary:
            with (
                patch.dict(os.environ, {"LOCALAPPDATA": temporary}),
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


if __name__ == "__main__":
    unittest.main()
