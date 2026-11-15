from comfy_api.latest import io


class Pop(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="ICafePop",
            display_name="pop",
            category="工具",
            description="取出列表的第一个元素，并输出剩余列表。",
            inputs=[io.AnyType.Input("items", display_name="列表")],
            outputs=[
                io.AnyType.Output("first", display_name="第一个元素"),
                io.AnyType.Output("rest", display_name="剩余列表"),
            ],
            # Receive a ComfyUI output list (e.g. 文本展示) as one list instead of one call per element.
            is_input_list=True,
        )

    @classmethod
    def execute(cls, items) -> io.NodeOutput:
        # A single Python list value, e.g. a loop channel, arrives wrapped as [list].
        if len(items) == 1 and isinstance(items[0], (list, tuple)):
            items = items[0]
        if not items:
            raise ValueError("pop 的输入列表为空。请在上游判断列表长度后再调用 pop。")
        return io.NodeOutput(items[0], list(items[1:]))
