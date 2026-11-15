"""Isolated backend contract tests without importing tool integrations."""
import ast
import json
from pathlib import Path
import types
import unittest


class CustomParametersTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tree = ast.parse(Path(__file__).with_name("text_nodes.py").read_text())
        tree.body = [node for node in tree.body if not isinstance(node, ast.ImportFrom)]
        field = types.SimpleNamespace(Input=lambda *a, **kw: kw, Output=lambda *a, **kw: kw)
        io = types.SimpleNamespace(
            ComfyNode=object, String=field, Int=field, AnyType=field,
            Schema=lambda **kw: kw, NodeOutput=lambda *values: values,
        )
        namespace = {"io": io}
        exec(compile(tree, "text_nodes.py", "exec"), namespace)
        cls.node = namespace["CustomParameters"]

    def test_schema_and_rows(self):
        self.assertEqual(len(self.node.define_schema()["outputs"]), 1)
        rows = [{"key": "int", "value": str(i)} for i in range(1000)]
        self.assertEqual(self.node.execute(json.dumps(rows), 999), (999,))
        self.assertEqual(self.node.execute("[]"), (None,))
        for kind, value, expected in [
            ("str", "", ""), ("int", "-42", -42),
            ("bool", " TRUE ", True), ("float", "1.25", 1.25),
        ]:
            self.assertEqual(self.node.execute(json.dumps([dict(key=kind, value=value)])), (expected,))

    def test_errors(self):
        for parameters, index in [
            ("invalid", 0), ("{}", 0), ("[]", 1), ("[]", -1), ("[]", True),
            ('[{}]', 0), ('[{"key":"int","value":true}]', 0),
            ('[{"key":"float","value":"inf"}]', 0),
            ('[{"key":"bool","value":"yes"}]', 0),
            ('[{"key":"str","value":1}]', 0),
        ]:
            with self.subTest(parameters=parameters, index=index), self.assertRaises(ValueError):
                self.node.execute(parameters, index)


if __name__ == "__main__":
    unittest.main()
