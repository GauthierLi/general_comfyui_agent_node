"""image_path_preview contracts using the installed ComfyUI V3 API."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "ComfyUI"))
import folder_paths  # noqa: E402

spec = importlib.util.spec_from_file_location("image_preview_node", Path(__file__).with_name("image_preview_node.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
Preview = module.ImagePathPreview


class ImagePathPreviewTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        # RGBA PNG 和 RGB JPEG 尺寸不同，验证逐张预览。
        Image.new("RGBA", (4, 3), (255, 0, 0, 128)).save(root / "a.png")
        Image.new("RGB", (2, 5), "blue").save(root / "b.jpg")
        self.images = [str(root / "a.png"), str(root / "b.jpg")]
        self.temp_dir = root / "temp"
        patcher = patch.object(folder_paths, "get_temp_directory", return_value=str(self.temp_dir))
        patcher.start()
        self.addCleanup(patcher.stop)

    def preview(self, path):
        return Preview.execute(path).ui.as_dict()["images"]

    def test_output_list_and_list_value(self):
        for path in (self.images, [self.images], [f" {self.images[0]} ", ""] + self.images[1:]):
            with self.subTest(path=path):
                images = self.preview(path)
                self.assertEqual(len(images), 2)
                self.assertTrue(all(item["type"] == "temp" for item in images))
                for item in images:
                    self.assertTrue((self.temp_dir / item["subfolder"] / item["filename"]).is_file())
        self.assertEqual(len(self.preview([self.images[0]])), 1)

    def test_missing_and_empty(self):
        with self.assertRaisesRegex(FileNotFoundError, "不存在"):
            Preview.execute(["/no/such/image.png"])
        for path in ([""], [[]]):
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "为空"):
                Preview.execute(path)


if __name__ == "__main__":
    unittest.main()
