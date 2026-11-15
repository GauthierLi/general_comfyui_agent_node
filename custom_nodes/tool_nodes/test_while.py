"""Easy-Use logic nodes port: real CPU PromptExecutor behaviour tests."""

import copy
import logging
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "ComfyUI"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from comfy.cli_args import args
args.cpu = True

import nodes
from comfy.model_management import interrupt_current_processing
from execution import PromptExecutor

import logic_nodes as module
from accumulate_node import Accumulate
from pop_node import Pop


class Work:
    calls = []

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"value": ("INT",), "limit": ("INT",)}}

    RETURN_TYPES = ("INT", "BOOLEAN")
    FUNCTION = "execute"

    def execute(self, value, limit):
        self.calls.append(value)
        return value + 1, value + 1 < limit


class Constant:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"value": ("INT",)}}

    RETURN_TYPES = ("INT",)
    FUNCTION = "execute"

    def execute(self, value):
        return (value,)


class Capture:
    calls = []

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"value": ("*",)}}

    RETURN_TYPES = ("*",)
    FUNCTION = "execute"
    OUTPUT_NODE = True
    INPUT_IS_LIST = True
    OUTPUT_IS_LIST = (True,)

    def execute(self, value):
        self.calls.append(value)
        return (value,)


class Server:
    client_id = None

    def send_sync(self, *args, **kwargs):
        pass


class WhileLoopTest(unittest.TestCase):
    def setUp(self):
        self.addCleanup(logging.disable, logging.root.manager.disable)
        logging.disable(logging.CRITICAL)
        self.registry = patch.dict(nodes.NODE_CLASS_MAPPINGS, {
            "whileLoopStart": module.WhileLoopStart,
            "whileLoopEnd": module.WhileLoopEnd,
            "TestWork": Work, "TestConstant": Constant, "TestCapture": Capture,
        })
        self.registry.start()
        self.addCleanup(self.registry.stop)
        self.addCleanup(interrupt_current_processing, False)
        Work.calls.clear()
        Capture.calls.clear()

    def prompt(self, limit=3, start_condition=True):
        return {
            "const": {"class_type": "TestConstant", "inputs": {"value": 0}},
            "start": {"class_type": "whileLoopStart", "inputs": {
                "condition": start_condition, "initial_value0": ["const", 0],
            }},
            "work": {"class_type": "TestWork", "inputs": {
                "value": ["start", 1], "limit": limit,
            }},
            "end": {"class_type": "whileLoopEnd", "inputs": {
                "flow": ["start", 0], "condition": ["work", 1], "initial_value0": ["work", 0],
            }},
            "capture": {"class_type": "TestCapture", "inputs": {"value": ["end", 0]}},
        }

    def run_prompt(self, prompt):
        executor = PromptExecutor(Server(), cache_type=False, cache_args={"ram": 0, "ram_inactive": 0})
        executor.execute(copy.deepcopy(prompt), "while-loop-test", execute_outputs=["capture"])
        return executor

    def test_repeats_until_condition_false(self):
        executor = self.run_prompt(self.prompt())
        self.assertTrue(executor.success, executor.status_messages)
        self.assertEqual(Work.calls, [0, 1, 2])
        self.assertEqual(Capture.calls, [[3]])

    def test_stop_immediately(self):
        executor = self.run_prompt(self.prompt(limit=1))
        self.assertTrue(executor.success, executor.status_messages)
        self.assertEqual(Work.calls, [0])
        self.assertEqual(Capture.calls, [[1]])

    def test_start_condition_false_skips_body(self):
        executor = self.run_prompt(self.prompt(start_condition=False))
        self.assertTrue(executor.success, executor.status_messages)
        self.assertEqual(Work.calls, [])
        self.assertEqual(Capture.calls, [])


class LogicNodeTest(unittest.TestCase):
    def setUp(self):
        self.addCleanup(logging.disable, logging.root.manager.disable)
        logging.disable(logging.CRITICAL)
        self.registry = patch.dict(nodes.NODE_CLASS_MAPPINGS, {
            "mathInt": module.mathIntOperation,
            "mathFloat": module.mathFloatOperation,
            "compare": module.Compare,
            "ifElse": module.IfElse,
            "stringToIntList": module.stringToIntList,
            "string": module.String,
            "ab": module.ab,
            "int": module.Int,
            "lengthAnything": module.lengthAnything,
            "whileLoopStart": module.WhileLoopStart,
            "whileLoopEnd": module.WhileLoopEnd,
            "ICafePop": Pop,
            "ICafeAccumulate": Accumulate,
            "TestCapture": Capture,
        })
        self.registry.start()
        self.addCleanup(self.registry.stop)
        Capture.calls.clear()

    def run_prompt(self, prompt, outputs):
        executor = PromptExecutor(Server(), cache_type=False, cache_args={"ram": 0, "ram_inactive": 0})
        executor.execute(copy.deepcopy(prompt), "logic-node-test", execute_outputs=outputs)
        return executor

    def test_math_int_operations(self):
        for operation, a, b, expected in [
            ("add", 2, 3, 5), ("subtract", 5, 3, 2), ("multiply", 4, 3, 12),
            ("divide", 7, 2, 3), ("modulo", 7, 3, 1), ("power", 2, 8, 256),
        ]:
            with self.subTest(operation=operation):
                prompt = {"math": {"class_type": "mathInt", "inputs": {
                    "a": a, "b": b, "operation": operation,
                }}}
                executor = self.run_prompt(prompt, ["math"])
                self.assertTrue(executor.success, executor.status_messages)
                self.assertEqual(executor.caches.outputs.get_local("math").outputs[0], [expected])

    def test_if_else_selects_branch(self):
        prompt = {
            "a": {"class_type": "string", "inputs": {"value": "yes"}},
            "b": {"class_type": "string", "inputs": {"value": "no"}},
            "pick": {"class_type": "ifElse", "inputs": {
                "boolean": True, "on_true": ["a", 0], "on_false": ["b", 0],
            }},
            "capture": {"class_type": "TestCapture", "inputs": {"value": ["pick", 0]}},
        }
        executor = self.run_prompt(prompt, ["capture"])
        self.assertTrue(executor.success, executor.status_messages)
        self.assertEqual(Capture.calls, [["yes"]])

    def test_string_to_int_list(self):
        prompt = {"list": {"class_type": "stringToIntList", "inputs": {"string": "1, 2, 3"}}}
        executor = self.run_prompt(prompt, ["list"])
        self.assertTrue(executor.success, executor.status_messages)
        self.assertEqual(executor.caches.outputs.get_local("list").outputs[0], [[1, 2, 3]])

    def test_pop_in_while_loop(self):
        prompt = {
            "list": {"class_type": "stringToIntList", "inputs": {"string": "1, 2, 3"}},
            "start": {"class_type": "whileLoopStart", "inputs": {"condition": True, "initial_value0": ["list", 0]}},
            "pop": {"class_type": "ICafePop", "inputs": {"items": ["start", 1]}},
            "first": {"class_type": "TestCapture", "inputs": {"value": ["pop", 0]}},
            "length": {"class_type": "lengthAnything", "inputs": {"any": ["pop", 1]}},
            "zero": {"class_type": "int", "inputs": {"value": 0}},
            "more": {"class_type": "compare", "inputs": {"a": ["length", 0], "b": ["zero", 0], "comparison": "a > b"}},
            "end": {"class_type": "whileLoopEnd", "inputs": {
                "flow": ["start", 0], "condition": ["more", 0], "initial_value0": ["pop", 1]}},
            "rest": {"class_type": "TestCapture", "inputs": {"value": ["end", 0]}},
        }
        executor = self.run_prompt(prompt, ["first", "rest"])
        self.assertTrue(executor.success, executor.status_messages)
        self.assertEqual(Capture.calls, [[1], [2], [3], [[]]])

    def test_accumulate_values(self):
        for item, items, expected in [
            (["a"], None, ["a"]),
            (["a", "b"], None, ["a", "b"]),
            (["c"], [None], ["c"]),
            (["c"], [["a", "b"]], ["a", "b", "c"]),
            ([["x"]], [["a"]], ["a", ["x"]]),
        ]:
            with self.subTest(item=item, items=items):
                self.assertEqual(Accumulate.execute(item, items).result, (expected,))

    def test_accumulate_in_while_loop(self):
        prompt = {
            "list": {"class_type": "stringToIntList", "inputs": {"string": "1, 2, 3"}},
            "start": {"class_type": "whileLoopStart", "inputs": {"condition": True, "initial_value0": ["list", 0]}},
            "pop": {"class_type": "ICafePop", "inputs": {"items": ["start", 1]}},
            "acc": {"class_type": "ICafeAccumulate", "inputs": {"item": ["pop", 0], "items": ["start", 2]}},
            "length": {"class_type": "lengthAnything", "inputs": {"any": ["pop", 1]}},
            "zero": {"class_type": "int", "inputs": {"value": 0}},
            "more": {"class_type": "compare", "inputs": {"a": ["length", 0], "b": ["zero", 0], "comparison": "a > b"}},
            "end": {"class_type": "whileLoopEnd", "inputs": {
                "flow": ["start", 0], "condition": ["more", 0],
                "initial_value0": ["pop", 1], "initial_value1": ["acc", 0]}},
            "result": {"class_type": "TestCapture", "inputs": {"value": ["end", 1]}},
        }
        executor = self.run_prompt(prompt, ["result"])
        self.assertTrue(executor.success, executor.status_messages)
        self.assertEqual(Capture.calls, [[[1, 2, 3]]])

    def test_ab_blocks_unselected_output(self):
        prompt = {
            "text": {"class_type": "string", "inputs": {"value": "x"}},
            "split": {"class_type": "ab", "inputs": {"A or B": True, "in": ["text", 0]}},
            "a": {"class_type": "TestCapture", "inputs": {"value": ["split", 0]}},
            "b": {"class_type": "TestCapture", "inputs": {"value": ["split", 1]}},
        }
        executor = self.run_prompt(prompt, ["a", "b"])
        self.assertTrue(executor.success, executor.status_messages)
        self.assertEqual(Capture.calls, [["x"]])


if __name__ == "__main__":
    unittest.main()
