import asyncio
import json
import logging
from datetime import date
from pathlib import Path

import aiohttp
import folder_paths
import yaml
from aiohttp import web
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
    create_sdk_mcp_server,
)
from comfy_api.latest import ComfyExtension, io
from server import PromptServer

from .harness import (
    ALWAYS_ON_LIMIT,
    list_harnesses,
    load,
    load_env,
    load_hooks,
    load_tools,
    prepare_workspace,
    render,
    resolve,
)

WEB_DIRECTORY = "./js"
HARNESS_MODEL = "(harness 默认)"
LOAD_ERRORS = (ValueError, OSError, SyntaxError, yaml.YAMLError)
# 由 /agent/models 刷新，节点定义用它生成 model 下拉选项。
models = []


async def fetch_models(env):
    key = env.get("ANTHROPIC_API_KEY")
    if not key:
        raise ValueError("未设置 ANTHROPIC_API_KEY，请写入 harness 目录的 .env。")
    url = (env.get("ANTHROPIC_BASE_URL") or "https://api.anthropic.com").rstrip("/") + "/v1/models"
    headers = {"x-api-key": key, "anthropic-version": "2023-06-01"}
    # trust_env 使 HTTPS_PROXY 等代理变量生效。
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15), trust_env=True) as session:
        try:
            async with session.get(url, params={"limit": "1000"}, headers=headers) as response:
                if response.status != 200:
                    raise RuntimeError(f"查询模型失败：{url} 返回 HTTP {response.status}：{await response.text()}")
                data = await response.json()
        except TimeoutError as error:
            raise TimeoutError(f"查询模型超时：15 秒内无法连接 {url}，请检查网络或代理。") from error
    return [item["id"] for item in data["data"]]


def describe(message):
    """把 SDK 消息转换为 [ACTION]/[OBSERVATION] 格式的轨迹行。"""
    lines = []
    if isinstance(message, AssistantMessage):
        for block in message.content:
            if isinstance(block, TextBlock):
                lines.append(f"[ASSISTANT] {block.text}")
            elif isinstance(block, ThinkingBlock):
                lines.append(f"[THINKING] {block.thinking}")
            elif isinstance(block, ToolUseBlock):
                lines.append(f"[ACTION] {block.name} {json.dumps(block.input, ensure_ascii=False)}")
    elif isinstance(message, UserMessage) and isinstance(message.content, list):
        for block in message.content:
            if isinstance(block, ToolResultBlock):
                content = block.content if isinstance(block.content, str) else json.dumps(block.content, ensure_ascii=False)
                lines.append(f"[{'ERROR' if block.is_error else 'OBSERVATION'}] {content}")
    return lines


def wrap_hooks_for_trajectory(hooks, trajectory, node_id):
    """记录 hook 阻断反馈，并推送到 Agent 节点的 trajectory。"""
    for event_name, matchers in hooks.items():
        for matcher in matchers:
            wrapped = []
            for hook in matcher.hooks:
                async def callback(input_data, tool_use_id, context, _hook=hook, _event=event_name):
                    result = await _hook(input_data, tool_use_id, context)
                    if result and result.get("decision") == "block":
                        reason = (
                            result.get("reason")
                            or result.get("systemMessage")
                            or result.get("stopReason")
                            or "hook 阻止 Agent 结束。"
                        )
                        lines = [f"[HOOK][{_event}][BLOCK] {reason}"]
                        trajectory.extend(lines)
                        PromptServer.instance.send_sync(
                            "agent.trajectory",
                            {"node_id": node_id, "lines": lines, "reset": False},
                        )
                    return result
                wrapped.append(callback)
            matcher.hooks = wrapped
    return hooks


class AgentNode(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="AgentNode",
            display_name="Agent",
            category="agent",
            description="从 harness 目录加载 agent 定义，并执行 task。",
            inputs=[
                io.Combo.Input("harness_dir", options=list_harnesses()),
                io.Combo.Input("model", options=[HARNESS_MODEL, *models]),
                io.String.Input("task", default="", multiline=True, placeholder="留空则使用 harness 目录中的 task.md"),
                io.Autogrow.Input("context", template=io.Autogrow.TemplateNames(
                    input=io.AnyType.Input("context"), names=[f"context_{i}" for i in range(1, 101)], min=0,
                )),
                io.String.Input("resume_session", optional=True, force_input=True),
            ],
            outputs=[
                io.String.Output("result"),
                io.String.Output("structured"),
                io.String.Output("session_id"),
                io.String.Output("trajectory"),
            ],
            hidden=[io.Hidden.unique_id, io.Hidden.dynprompt],
            is_output_node=True,
            not_idempotent=True,
        )

    @classmethod
    def fingerprint_inputs(cls, **kwargs):
        return float("nan")

    @classmethod
    def validate_inputs(cls, harness_dir, model, task):
        # model 选项随 /agent/models 变化，由这里代替 ComfyUI 的下拉值校验。
        try:
            harness = load(harness_dir)
        except LOAD_ERRORS as error:
            return str(error)
        if not isinstance(model, str) or not model.strip():
            return "model 不能为空。"
        if not task.strip() and not harness.task:
            return f"未指定任务：task 为空，且 {harness.path / 'task.md'} 不存在或为空。"
        return True

    @classmethod
    async def execute(cls, harness_dir, model, task, context=None, resume_session=None):
        harness = load(harness_dir)
        workspace = Path(folder_paths.get_output_directory()) / "agent" / harness.name
        prepare_workspace(harness, workspace)
        values = {
            name: value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
            for name, value in (context or {}).items()
        }
        prompt = render(task if task.strip() else harness.task, values)
        system_text = render(harness.always_on, {"date": date.today().isoformat(), "working_directory": str(workspace)})
        if harness.prompt_mode == "replace":
            system_prompt = system_text
        else:
            system_prompt = {"type": "preset", "preset": "claude_code"} | ({"append": system_text} if system_text else {})
        # 轨迹第一行是实际发给 agent 的任务，占位符已替换。
        trajectory = [f"[TASK] {prompt}"]
        tool_calls = 0
        node_id = str(cls.hidden.dynprompt.get_display_node_id(cls.hidden.unique_id))
        PromptServer.instance.send_sync("agent.trajectory", {"node_id": node_id, "lines": list(trajectory), "reset": True})
        tools = list(harness.tools)
        if harness.agents and "Agent" not in tools:
            tools.append("Agent")
        allowed_tools = list(tools)
        if harness.skills and "Skill" not in tools:
            tools.append("Skill")
        mcp_tools = load_tools(harness.path)
        hooks = wrap_hooks_for_trajectory(load_hooks(harness.path), trajectory, node_id)
        options = ClaudeAgentOptions(
            tools=tools,
            allowed_tools=allowed_tools + [f"mcp__harness__{tool.name}" for tool in mcp_tools],
            disallowed_tools=harness.disallowed_tools,
            mcp_servers={"harness": create_sdk_mcp_server(name="harness", tools=mcp_tools)} if mcp_tools else {},
            strict_mcp_config=True,
            # 只加载工作区内复制的 skill，不读取运行用户的 ~/.claude 配置。
            setting_sources=["project"] if harness.skills else [],
            skills=list(harness.skills),
            agents=harness.agents or None,
            hooks=hooks or None,
            system_prompt=system_prompt,
            model=(harness.model or None) if model == HARNESS_MODEL else model,
            max_turns=harness.max_turns,
            max_budget_usd=harness.max_budget_usd,
            output_format=harness.output_format,
            permission_mode="default",
            cwd=workspace,
            add_dirs=harness.add_dirs,
            env=load_env(harness.path),
            resume=resume_session or None,
        )
        # timeout 位于会话外层，使取消先经过客户端的异步清理。
        async with asyncio.timeout(harness.timeout):
            async with ClaudeSDKClient(options=options) as client:
                await client.query(prompt=prompt)
                async for message in client.receive_response():
                    lines = describe(message)
                    if lines:
                        trajectory += lines
                        PromptServer.instance.send_sync("agent.trajectory", {"node_id": node_id, "lines": lines, "reset": False})
                    if isinstance(message, AssistantMessage):
                        for block in message.content:
                            if isinstance(block, ToolUseBlock):
                                tool_calls += 1
                                PromptServer.instance.send_progress_text(f"工具调用 {tool_calls} · {block.name}", cls.hidden.unique_id)
                    if isinstance(message, ResultMessage):
                        if message.is_error or message.subtype != "success":
                            raise RuntimeError(
                                f"Agent 执行失败（{message.subtype}）："
                                f"{message.result or '; '.join(message.errors or []) or 'SDK 未返回错误正文。'}"
                            )
                        if message.result is None:
                            raise RuntimeError("Agent 成功消息缺少 result 正文。")
                        structured = "" if message.structured_output is None else json.dumps(message.structured_output, ensure_ascii=False)
                        return io.NodeOutput(message.result, structured, message.session_id, "\n".join(trajectory))
                raise RuntimeError("Agent 会话结束，但未收到 ResultMessage。")


async def harnesses_route(request):
    return web.json_response(list_harnesses())


async def harness_info_route(request):
    try:
        harness = load(request.query.get("name", ""))
        mcp_tools = [tool.name for tool in load_tools(harness.path)]
    except (*LOAD_ERRORS, ImportError) as error:
        return web.json_response({"error": str(error)}, status=400)
    env = load_env(harness.path)
    return web.json_response({
        "model": harness.model,
        "max_turns": harness.max_turns,
        "timeout": harness.timeout,
        "prompt_mode": harness.prompt_mode,
        "tools": harness.tools,
        "mcp_tools": mcp_tools,
        "plugins": [file.stem for file in sorted((harness.path / "plugins").glob("*.py"))],
        "skills": list(harness.skills),
        "subagents": list(harness.agents),
        "always_on_chars": len(harness.always_on),
        "always_on_limit": ALWAYS_ON_LIMIT,
        "task": harness.task,
        "env": {name: bool(env.get(name)) for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL")},
    })


async def models_route(request):
    try:
        ids = await fetch_models(load_env(resolve(request.query.get("harness", ""))))
    except (aiohttp.ClientError, TimeoutError, ValueError, RuntimeError) as error:
        logging.warning("Agent 节点查询模型失败：%s: %s", type(error).__name__, error)
        return web.json_response({"error": f"{type(error).__name__}: {error}"}, status=502)
    models[:] = ids
    return web.json_response(ids)


class AgentExtension(ComfyExtension):
    async def on_load(self):
        PromptServer.instance.routes.get("/agent/harnesses")(harnesses_route)
        PromptServer.instance.routes.get("/agent/harness_info")(harness_info_route)
        PromptServer.instance.routes.get("/agent/models")(models_route)

    async def get_node_list(self):
        return [AgentNode]


async def comfy_entrypoint():
    return AgentExtension()
