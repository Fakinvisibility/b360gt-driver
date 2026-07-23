from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from b360gt.library import MediaLibrary


class MediaLibraryTests(unittest.TestCase):
    def test_runtime_and_overlay_state_survive_selection_updates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "library"
            source = Path(directory) / "image.png"
            Image.new("RGB", (32, 32), "blue").save(source)
            library = MediaLibrary(root)
            item = library.add(source, display_name="image.png")

            library.remember_running(True)
            library.remember_overlay_config(
                {
                    "enabled": False,
                    "gpu_enabled": False,
                    "position": "bottom-right",
                    "refresh_seconds": 2.0,
                }
            )
            library.remember_selected(item.item_id)

            reopened = MediaLibrary(root)
            self.assertTrue(reopened.desired_running())
            self.assertEqual(reopened.selected_id(), item.item_id)
            self.assertEqual(
                reopened.overlay_config(),
                {
                    "enabled": False,
                    "gpu_enabled": False,
                    "position": "bottom-right",
                    "refresh_seconds": 2.0,
                },
            )

    def test_media_survives_library_reopen_and_can_be_deleted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "library"
            source = Path(directory) / "source.png"
            Image.new("RGB", (80, 40), "purple").save(source)

            library = MediaLibrary(root)
            item = library.add(source, display_name="我的图片.png")
            library.remember_selected(item.item_id)

            reopened = MediaLibrary(root)
            restored = reopened.selected_item()
            self.assertIsNotNone(restored)
            assert restored is not None
            self.assertEqual(restored.name, "我的图片.png")
            self.assertEqual(restored.media_info.kind, "image")
            self.assertTrue(restored.path.is_file())
            self.assertTrue(restored.preview_path.is_file())
            self.assertTrue(source.is_file())

            reopened.delete(restored.item_id)
            self.assertEqual(reopened.list_items(), [])
            self.assertIsNone(reopened.selected_id())

    def test_delete_refuses_item_directory_with_unknown_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "library"
            source = Path(directory) / "source.png"
            Image.new("RGB", (32, 32), "blue").save(source)
            library = MediaLibrary(root)
            item = library.add(source, display_name="source.png")
            unexpected = item.path.parent / "do-not-delete.txt"
            unexpected.write_text("user data", encoding="utf-8")

            with self.assertRaises(RuntimeError):
                library.delete(item.item_id)

            self.assertTrue(item.path.is_file())
            self.assertTrue(unexpected.is_file())


if __name__ == "__main__":
    unittest.main()
