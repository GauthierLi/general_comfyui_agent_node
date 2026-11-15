"""Comparison contracts using the installed ComfyUI V3 API."""
import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from comfy_api.latest import io
from comfy_api.latest._io import build_nested_inputs, parse_class_inputs

spec = importlib.util.spec_from_file_location("compare_node", Path(__file__).with_name("compare_node.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
Compare = module.Compare


class CompareTest(unittest.TestCase):
    def test_numeric_operators(self):
        for kind, values in [("int", (-3, 0, 2**53 - 1, 2**80)),
                             ("float", (-1.25, 0.0, 2.5, 1e100))]:
            for left in values:
                for right in values:
                    expected = {"==": left == right, "!=": left != right,
                                ">": left > right, ">=": left >= right,
                                "<": left < right, "<=": left <= right}
                    for symbol, result in expected.items():
                        with self.subTest(kind=kind, left=left, right=right, symbol=symbol):
                            output = Compare.execute(dict(value_type=kind, left=left, right=right, operator=symbol))
                            self.assertIs(output.result[0], result)

    def test_string_exact_match(self):
        for left, right, equal in [
            ("", "", True), ("中文", "中文", True), ("A", "a", False),
            (" a", "a", False), ("a ", "a", False), ("\t", " ", False),
            ("a\n", "a", False), ("{a|b}", "{a|b}", True),
        ]:
            for symbol, expected in [("==", equal), ("!=", not equal)]:
                with self.subTest(left=left, right=right, symbol=symbol):
                    self.assertIs(Compare.execute(dict(
                        value_type="str", left=left, right=right, operator=symbol)).result[0], expected)

    def test_invalid_types_and_operators(self):
        for kind, left, right, symbol in [
            *[("str", "a", "b", op) for op in (">", ">=", "<", "<=")],
            ("int", 1, 2, "unknown"), ("bool", True, False, "=="),
            ("int", 1.5, 1, "=="), ("int", 1, True, "=="),
            ("int", "1", 1, "=="), ("float", True, 1.0, "=="),
            ("float", 1.0, "1", "=="), ("str", 1, "1", "=="),
            ("str", "", None, "=="),
        ]:
            with self.subTest(kind=kind, left=left, right=right, symbol=symbol):
                with self.assertRaises(ValueError):
                    Compare.execute(dict(value_type=kind, left=left, right=right, operator=symbol))

    def test_float_semantics(self):
        for left, right, symbol, expected in [
            (1, 1.0, "==", True), (0.1 + 0.2, 0.3, "==", False),
            (float("nan"), float("nan"), "==", False),
            (float("nan"), 0.0, "!=", True),
            (float("inf"), 1e300, ">", True), (-0.0, 0.0, "==", True),
        ]:
            with self.subTest(left=left, right=right, symbol=symbol):
                self.assertIs(Compare.execute(dict(
                    value_type="float", left=left, right=right, operator=symbol)).result[0], expected)

    def test_real_schema_and_dynamic_execution(self):
        schema = Compare.GET_SCHEMA()
        self.assertEqual(schema.node_id, "ICafeCompare")
        self.assertIsInstance(schema.outputs[0], io.Boolean.Output)
        info = Compare.GET_NODE_INFO_V1()
        json.dumps(info, allow_nan=False)
        selector = schema.inputs[0]
        self.assertEqual([option.key for option in selector.options], ["int", "float", "str"])
        for option, field, value in zip(selector.options, (io.Int, io.Float, io.String), (0, 0.0, "")):
            left, symbol, right = option.inputs
            self.assertIsInstance(left, field.Input)
            self.assertIsInstance(right, field.Input)
            self.assertEqual((left.display_name, right.display_name), ("左操作数", "右操作数"))
            self.assertEqual(symbol.default, "==")
            self.assertEqual(set(symbol.options),
                             {"==", "!="} if option.key == "str" else {"==", "!=", ">", ">=", "<", "<="})
            if option.key == "int":
                self.assertEqual((left.min, left.max), (-(2**53 - 1), 2**53 - 1))
            if option.key == "str":
                self.assertFalse(left.dynamic_prompts)
                self.assertFalse(right.dynamic_prompts)
            live = {"value_type": option.key, "value_type.left": value,
                    "value_type.operator": "==", "value_type.right": value}
            expanded = {"required": {}, "optional": {}, "hidden": {}, "dynamic_paths": {}}
            parse_class_inputs(expanded, live, Compare.INPUT_TYPES())
            nested = build_nested_inputs(live, expanded)
            self.assertEqual(nested["value_type"]["value_type"], option.key)
            self.assertIs(Compare.execute(**nested).result[0], True)

    def test_extension_registration(self):
        # Isolate existing pause/server integrations; import the real package entrypoint.
        package_name = "_tool_nodes_registration_test"
        pause = types.ModuleType(f"{package_name}.pause_node")
        pause.ManualContinue = type("ManualContinue", (), {})
        pause.continue_pause = pause.pending_pauses = None
        server = types.ModuleType("server")
        server.PromptServer = object
        package_spec = importlib.util.spec_from_file_location(
            package_name, Path(__file__).with_name("__init__.py"),
            submodule_search_locations=[str(Path(__file__).parent)])
        package = importlib.util.module_from_spec(package_spec)
        with patch.dict(sys.modules, {
            package_name: package, f"{package_name}.pause_node": pause, "server": server,
        }):
            package_spec.loader.exec_module(package)
            extension = asyncio.run(package.comfy_entrypoint())
            nodes = asyncio.run(extension.get_node_list())
            ids = [node.GET_SCHEMA().node_id for node in nodes if issubclass(node, io.ComfyNode)]
            self.assertEqual(ids.count("ICafeCompare"), 1)
            self.assertIn(package.Compare, nodes)


if __name__ == "__main__":
    unittest.main()
