"""Pop contracts using the installed ComfyUI V3 API."""
import importlib.util
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
spec = importlib.util.spec_from_file_location("pop_node", Path(__file__).with_name("pop_node.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
Pop = module.Pop


class PopTest(unittest.TestCase):
    def test_output_list_and_list_value(self):
        for items, first, rest in [
            (["a", "b", "c"], "a", ["b", "c"]),
            ([["a", "b", "c"]], "a", ["b", "c"]),
            ([("a",)], "a", []),
            (["a"], "a", []),
            ([1, [2]], 1, [[2]]),
        ]:
            with self.subTest(items=items):
                self.assertEqual(Pop.execute(items).result, (first, rest))

    def test_empty(self):
        for items in ([], [[]]):
            with self.subTest(items=items), self.assertRaises(ValueError):
                Pop.execute(items)


if __name__ == "__main__":
    unittest.main()
