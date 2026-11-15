import json
import math
import re

from comfy_api.latest import io, ui


class CustomParameters(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="ICafeCustomParameters",
            display_name="自定义参数",
            category="工具",
            description="每组 key 选择类型，value 填写值。每组独立输出，运行时按连接拆分。",
            inputs=[
                io.String.Input("parameters", default='[{"key":"str","value":""}]'),
                io.Int.Input("output_index", default=0, min=0, optional=True),
            ],
            outputs=[io.AnyType.Output("parameter")],
        )

    @classmethod
    def execute(cls, parameters: str, output_index: int = 0) -> io.NodeOutput:
        try:
            rows = json.loads(parameters)
        except (TypeError, ValueError):
            raise ValueError("参数配置必须为 JSON 数组。") from None
        if not isinstance(rows, list):
            raise ValueError("参数配置必须为 JSON 数组。")
        if type(output_index) is not int or output_index < 0:
            raise ValueError("output_index 必须为非负整数。")
        if not rows and output_index == 0:
            return io.NodeOutput(None)
        if output_index >= len(rows):
            raise ValueError(f"参数输出索引 {output_index} 超出 {len(rows)} 组参数范围，请检查连接或上游参数。")
        index, row = output_index + 1, rows[output_index]
        if not isinstance(row, dict) or "key" not in row or "value" not in row:
            raise ValueError(f"第 {index} 组参数缺少 key 或 value。")
        kind, value = row["key"], row["value"]
        if kind == "str":
            if not isinstance(value, str):
                raise ValueError(f"第 {index} 组参数的 value 必须为字符串。")
        elif kind == "bool":
            if isinstance(value, str) and value.strip().lower() in ("true", "false"):
                value = value.strip().lower() == "true"
            if type(value) is not bool:
                raise ValueError(f"第 {index} 组参数的 value 必须为 true 或 false。")
        elif kind == "int":
            if type(value) is not int:
                if not isinstance(value, str) or not re.fullmatch(r"[+-]?[0-9]+", value.strip()):
                    raise ValueError(f"第 {index} 组参数的 value 必须为整数。")
                value = int(value)
        elif kind == "float":
            if type(value) not in (str, int, float):
                raise ValueError(f"第 {index} 组参数的 value 必须为有限浮点数。")
            try:
                value = float(value)
            except (ValueError, OverflowError):
                raise ValueError(f"第 {index} 组参数的 value 必须为有限浮点数。") from None
            if not math.isfinite(value):
                raise ValueError(f"第 {index} 组参数的 value 必须为有限浮点数。")
        else:
            raise ValueError(f"第 {index} 组参数的 key 只支持 int、float、bool、str。")
        return io.NodeOutput(value)


class ShowText(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="ShowText",
            display_name="文本展示",
            category="工具",
            inputs=[io.String.Input("text", force_input=True)],
            outputs=[io.String.Output("text", is_output_list=True)],
            is_input_list=True,
            is_output_node=True,
        )

    @classmethod
    def execute(cls, text) -> io.NodeOutput:
        if isinstance(text, str):
            value = text
        elif isinstance(text, list) and all(isinstance(item, str) for item in text):
            value = "\n".join(text)
        else:
            value = str(text)
        return io.NodeOutput(text if isinstance(text, list) else [text], ui=ui.PreviewText(value))
