"""list_string_transfer contracts using the installed ComfyUI V3 API."""
import importlib.util
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
spec = importlib.util.spec_from_file_location("list_string_node", Path(__file__).with_name("list_string_node.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
Transfer = module.ListStringTransfer


class ListStringTransferTest(unittest.TestCase):
    def test_list_to_string(self):
        for value, separator, expected in [
            (["917930", "916465"], "换行", "917930\n916465"),
            ([["917930", "916465"]], "逗号", "917930,916465"),
            ([("a", 1)], "空格", "a 1"),
            ([1, 2], "逗号", "1,2"),
            ([[]], "换行", ""),
        ]:
            with self.subTest(value=value, separator=separator):
                self.assertEqual(Transfer.execute(value, [separator]).result, (expected,))

    def test_string_to_list(self):
        for text, separator, expected in [
            ("917930\n916465\n", "换行", ["917930", "916465"]),
            ("917930, 916465,,", "逗号", ["917930", "916465"]),
            ("a  b c", "空格", ["a", "b", "c"]),
            ("a b", "换行", ["a b"]),
            ("", "逗号", []),
        ]:
            with self.subTest(text=text, separator=separator):
                self.assertEqual(Transfer.execute([text], [separator]).result, (expected,))

    def test_round_trip(self):
        ids = ["917930", "916465", "906347"]
        text = Transfer.execute(ids, ["逗号"]).result[0]
        self.assertEqual(Transfer.execute([text], ["逗号"]).result, (ids,))

    def test_schema(self):
        inputs = Transfer.INPUT_TYPES()["required"]
        self.assertEqual(inputs["separator"][1]["options"], ["换行", "逗号", "空格"])
        self.assertTrue(Transfer.INPUT_IS_LIST)


if __name__ == "__main__":
    unittest.main()
