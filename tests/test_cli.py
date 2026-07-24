import unittest
from unittest.mock import patch

from b360gt import cli


class CliTests(unittest.TestCase):
    def test_foreground_ui_prints_instructions(self):
        with (
            patch("sys.argv", ["b360gt", "ui", "--no-browser"]),
            patch("b360gt.web_ui.run_ui") as run_ui,
        ):
            self.assertEqual(cli.main(), 0)

        run_ui.assert_called_once_with(
            port=8765,
            open_browser=False,
            quiet=False,
            managed_background=False,
        )

    def test_managed_ui_is_quiet(self):
        with (
            patch(
                "sys.argv",
                [
                    "b360gt",
                    "ui",
                    "--no-browser",
                    "--managed-background",
                ],
            ),
            patch("b360gt.web_ui.run_ui") as run_ui,
        ):
            self.assertEqual(cli.main(), 0)

        run_ui.assert_called_once_with(
            port=8765,
            open_browser=False,
            quiet=True,
            managed_background=True,
        )


if __name__ == "__main__":
    unittest.main()
