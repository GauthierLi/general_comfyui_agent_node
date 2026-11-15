from comfy_api.latest import io

SEPARATORS = {"换行": "\n", "逗号": ",", "空格": " "}


class ListStringTransfer(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="ICafeListStringTransfer",
            display_name="list_string_transfer",
            category="工具",
            description="输入列表时，按分隔符拼成字符串。输入字符串时，按分隔符切分成 Python 列表。",
            inputs=[
                io.AnyType.Input("value", display_name="输入"),
                io.Combo.Input("separator", options=list(SEPARATORS), display_name="分隔符"),
            ],
            outputs=[io.AnyType.Output("output", display_name="输出")],
            # Receive a ComfyUI output list (e.g. case_ids) as one list instead of one call per element.
            is_input_list=True,
        )

    @classmethod
    def execute(cls, value, separator) -> io.NodeOutput:
        separator = SEPARATORS[separator[0]]
        # A single Python list value, e.g. the accumulate output, arrives wrapped as [list].
        if len(value) == 1 and isinstance(value[0], (list, tuple)):
            value = value[0]
        elif len(value) == 1 and isinstance(value[0], str):
            return io.NodeOutput([item.strip() for item in value[0].split(separator) if item.strip()])
        return io.NodeOutput(separator.join(str(item) for item in value))
