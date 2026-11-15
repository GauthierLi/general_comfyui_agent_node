from comfy_api.latest import ComfyExtension, io
from server import PromptServer

from .accumulate_node import Accumulate
from .compare_node import Compare
from .image_preview_node import ImagePathPreview
from .list_string_node import ListStringTransfer
from .logic_nodes import NODE_CLASS_MAPPINGS as LOGIC_NODES
from .pause_node import ManualContinue, continue_pause, pending_pauses
from .pop_node import Pop
from .text_nodes import CustomParameters, ShowText

WEB_DIRECTORY = "./js"


class ToolNodesExtension(ComfyExtension):
    async def on_load(self):
        PromptServer.instance.routes.get("/icafe/pause")(pending_pauses)
        PromptServer.instance.routes.post("/icafe/pause/{token}/continue")(continue_pause)

    async def get_node_list(self) -> list[type[io.ComfyNode]]:
        return [ShowText, CustomParameters, ManualContinue, Compare, Pop, Accumulate, ListStringTransfer, ImagePathPreview] + list(LOGIC_NODES.values())


async def comfy_entrypoint() -> ToolNodesExtension:
    return ToolNodesExtension()
