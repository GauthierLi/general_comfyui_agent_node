from comfy_api.latest import io


class Accumulate(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="ICafeAccumulate",
            display_name="accumulate",
            category="工具",
            description="把输入追加到已有列表末尾，并输出新列表。",
            inputs=[
                io.AnyType.Input("item", display_name="元素"),
                io.AnyType.Input("items", display_name="已有列表", optional=True),
            ],
            outputs=[io.AnyType.Output("list", display_name="列表")],
            # Receive a ComfyUI output list as one list instead of one call per element.
            is_input_list=True,
        )

    @classmethod
    def execute(cls, item, items=None) -> io.NodeOutput:
        # An unconnected loop channel arrives as [None]; a single Python list value arrives as [list].
        if items is None or len(items) == 1 and items[0] is None:
            items = []
        elif len(items) == 1 and isinstance(items[0], (list, tuple)):
            items = items[0]
        return io.NodeOutput(list(items) + list(item))
