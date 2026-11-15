import operator

from comfy_api.latest import io


class Compare(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        options = []
        for kind, field, settings in [
            ("int", io.Int, dict(default=0, min=-(2**53 - 1), max=2**53 - 1, step=1)),
            ("float", io.Float, dict(default=0.0, min=-1.7976931348623157e308,
                                    max=1.7976931348623157e308, round=False)),
            ("str", io.String, dict(default="", dynamic_prompts=False)),
        ]:
            options.append(io.DynamicCombo.Option(kind, [
                field.Input("left", display_name="左操作数", **settings),
                io.Combo.Input("operator", display_name="运算符", default="==",
                               options=["==", "!="] if kind == "str" else ["==", "!=", ">", ">=", "<", "<="]),
                field.Input("right", display_name="右操作数", **settings),
            ]))
        return io.Schema(
            node_id="ICafeCompare",
            display_name="判断",
            category="工具",
            description="比较左操作数与右操作数。字符串区分大小写并保留空白。",
            inputs=[io.DynamicCombo.Input("value_type", display_name="类型", options=options)],
            outputs=[io.Boolean.Output("result", display_name="判断结果")],
        )

    @classmethod
    def execute(cls, value_type: io.DynamicCombo.Type) -> io.NodeOutput:
        kind = value_type["value_type"]
        if kind not in ("int", "float", "str"):
            raise ValueError("类型只支持 int、float、str。")
        left, right = value_type["left"], value_type["right"]
        allowed_types = {"int": (int,), "float": (int, float), "str": (str,)}[kind]
        for name, value in (("左操作数", left), ("右操作数", right)):
            if type(value) not in allowed_types:
                raise ValueError(f"{name}必须符合 {kind} 类型，不支持隐式字符串转换或布尔值。")
        symbol = value_type["operator"]
        operations = {"==": operator.eq, "!=": operator.ne}
        if kind != "str":
            operations.update({">": operator.gt, ">=": operator.ge, "<": operator.lt, "<=": operator.le})
        if symbol not in operations:
            raise ValueError(f"{kind} 类型不支持运算符 {symbol!r}。")
        return io.NodeOutput(operations[symbol](left, right))
