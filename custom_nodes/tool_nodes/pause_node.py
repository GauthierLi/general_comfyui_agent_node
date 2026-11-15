import asyncio
import threading
import uuid

from aiohttp import web
from comfy_api.latest import io
from comfy.model_management import throw_exception_if_processing_interrupted
from server import PromptServer


# Only active wait handles live here; input data stays in execute().
_pending = {}
_lock = threading.Lock()


async def pending_pauses(request):
    with _lock:
        waits = [{"token": token, "node_id": node_id} for token, (node_id, _) in _pending.items()]
    return web.json_response(waits)


async def continue_pause(request):
    token = request.match_info["token"]
    with _lock:
        pending = _pending.get(token)
        if pending is None:
            return web.json_response({"error": "等待已结束，请刷新节点状态。"}, status=409)
        pending[1].set()
    return web.json_response({"ok": True})


class ManualContinue(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        template = io.MatchType.Template("value_type")
        return io.Schema(
            node_id="ICafeManualContinue",
            display_name="手动继续",
            category="工具",
            description="等待点击继续后原样输出输入值。列表输入整体只等待一次。只阻塞依赖此输出的下游。",
            # Take the whole list so an empty upstream list (e.g. End Loop with zero iterations)
            # still reaches execute(), and a list of N items waits once instead of N times.
            is_input_list=True,
            inputs=[io.MatchType.Input("value", template=template)],
            outputs=[io.MatchType.Output(template=template, display_name="value", is_output_list=True)],
            hidden=[io.Hidden.unique_id, io.Hidden.dynprompt],
            not_idempotent=True,
        )

    @classmethod
    def fingerprint_inputs(cls, **kwargs):
        return float("nan")

    @classmethod
    async def execute(cls, value):
        node_id = str(cls.hidden.dynprompt.get_display_node_id(cls.hidden.unique_id))
        token = uuid.uuid4().hex
        ready = threading.Event()
        with _lock:
            _pending[token] = (node_id, ready)
        try:
            PromptServer.instance.send_sync(
                "icafe.pause", {"node_id": node_id, "token": token, "waiting": True},
            )
            while not ready.is_set():
                throw_exception_if_processing_interrupted()
                await asyncio.sleep(0.1)
            throw_exception_if_processing_interrupted()
            return io.NodeOutput(value)
        finally:
            with _lock:
                _pending.pop(token, None)
            PromptServer.instance.send_sync(
                "icafe.pause", {"node_id": node_id, "token": token, "waiting": False},
            )
