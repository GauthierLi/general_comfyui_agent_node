"""离线测试：使用真实 SDK 类型、ComfyUI V3 API 和 aiohttp 本地服务，模型客户端与 PromptServer 使用替身。"""
import asyncio
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

from aiohttp import web
from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock, ToolResultBlock, ToolUseBlock, UserMessage

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT.parents[1]
sys.path.insert(0, str(PROJECT / "ComfyUI"))

import folder_paths  # noqa: E402

progress = []
events = []
server = ModuleType("server")
server.PromptServer = SimpleNamespace(instance=SimpleNamespace(
    send_progress_text=lambda text, node_id: progress.append((text, node_id)),
    send_sync=lambda event, data: events.append((event, data)),
))
spec = importlib.util.spec_from_file_location("general_cc_agent_node", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)])
node = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {"server": server, spec.name: node}):
    spec.loader.exec_module(node)
harness = node.harness
Agent = node.AgentNode


def result(**changes):
    fields = dict(subtype="success", duration_ms=1, duration_api_ms=1, is_error=False, num_turns=1, session_id="s1", result="完成")
    fields.update(changes)
    return ResultMessage(**fields)


class Client:
    def __init__(self, options, messages=(), wait=False):
        self.options = options
        self.messages = messages
        self.wait = wait
        self.closed = False
        self.prompt = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.closed = True

    async def query(self, prompt):
        self.prompt = prompt

    async def receive_response(self):
        if self.wait:
            await asyncio.Event().wait()
        for message in self.messages:
            yield message


class AgentTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.root = self.tmp / "harnesses"
        shutil.copytree(PROJECT / "harnesses" / "example", self.root / "example")
        (self.root / "example" / ".env").write_text("ANTHROPIC_API_KEY=local\n", encoding="utf-8")
        for target, name, value in [
            (harness, "HARNESS_ROOT", self.root),
            (Agent, "hidden", SimpleNamespace(unique_id="7", dynprompt=SimpleNamespace(get_display_node_id=lambda node_id: f"display-{node_id}"))),
        ]:
            patcher = patch.object(target, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch.object(folder_paths, "get_output_directory", return_value=str(self.tmp / "output"))
        patcher.start()
        self.addCleanup(patcher.stop)
        progress.clear()
        events.clear()

    def edit(self, relative, text):
        path = self.root / "example" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    async def run_agent(self, messages, **inputs):
        clients = []

        def factory(options):
            clients.append(Client(options, messages))
            return clients[-1]

        values = dict(harness_dir="example", model=node.HARNESS_MODEL, task="", context={"context_1": "卡片正文"}) | inputs
        with patch.object(node, "ClaudeSDKClient", side_effect=factory):
            output = await Agent.execute(**values)
        return output, clients[0]

    async def test_example_harness_options_and_outputs(self):
        messages = [
            AssistantMessage(content=[TextBlock("开始"), ToolUseBlock("t1", "mcp__harness__echo", {"text": "x"})], model="m"),
            UserMessage(content=[ToolResultBlock("t1", "x")]),
            result(structured_output={"label": "ok"}),
        ]
        output, client = await self.run_agent(messages)
        workspace = self.tmp / "output" / "agent" / "example"
        prompt = client.prompt
        task = f"[TASK] {prompt}"
        self.assertEqual(output.result, ("完成", '{"label": "ok"}', "s1", f'{task}\n[ASSISTANT] 开始\n[ACTION] mcp__harness__echo {{"text": "x"}}\n[OBSERVATION] x'))
        self.assertIn("卡片正文", client.prompt)
        self.assertNotIn("{{context_1}}", client.prompt)
        options = client.options
        self.assertEqual(options.tools, ["Read", "Write", "Bash", "Agent", "Skill"])
        self.assertEqual(options.allowed_tools, ["Read", "Write", "Bash", "Agent", "mcp__harness__echo"])
        self.assertEqual(options.setting_sources, ["project"])
        self.assertEqual(options.skills, ["summarize"])
        self.assertEqual(list(options.agents), ["reviewer"])
        self.assertEqual(options.agents["reviewer"].tools, ["Read"])
        self.assertEqual(len(options.hooks["PreToolUse"]), 1)
        self.assertEqual(len(options.hooks["Stop"]), 1)
        self.assertTrue(options.strict_mcp_config)
        self.assertIsNone(options.model)
        self.assertEqual((options.max_turns, options.cwd), (30, workspace))
        self.assertEqual(options.env, {"ANTHROPIC_API_KEY": "local"})
        append = options.system_prompt["append"]
        self.assertEqual(options.system_prompt["preset"], "claude_code")
        for text in [str(workspace), "# Operating Guardrails", "word_count.py", "`echo`"]:
            self.assertIn(text, append)
        # LongTermMEMORY.md 只有 HTML 注释，渲染时跳过。
        self.assertNotIn("# Long-Term Memory", append)
        self.assertNotIn("{{date}}", append)
        self.assertTrue((workspace / ".claude" / "skills" / "summarize" / "SKILL.md").is_file())
        self.assertTrue((workspace / "scripts" / "word_count.py").is_file())
        self.assertEqual(progress, [("工具调用 1 · mcp__harness__echo", "7")])
        # 每条产生轨迹行的消息推送一次，ResultMessage 不产生轨迹行。
        self.assertEqual(events, [
            ("agent.trajectory", {"node_id": "display-7", "lines": [task], "reset": True}),
            ("agent.trajectory", {"node_id": "display-7", "lines": ["[ASSISTANT] 开始", '[ACTION] mcp__harness__echo {"text": "x"}'], "reset": False}),
            ("agent.trajectory", {"node_id": "display-7", "lines": ["[OBSERVATION] x"], "reset": False}),
        ])
        self.assertTrue(client.closed)

    async def test_task_model_and_replace_mode(self):
        self.edit("harness.yaml", "model: harness-model\nprompt_mode: replace\ntools: [Read, Bash]\n")
        _, client = await self.run_agent([result()], task="改写 {{context_1}} {{unknown}}", resume_session="s0")
        self.assertEqual(client.prompt, "改写 卡片正文 {{unknown}}")
        self.assertIsInstance(client.options.system_prompt, str)
        self.assertEqual(client.options.model, "harness-model")
        self.assertEqual(client.options.resume, "s0")
        _, client = await self.run_agent([result()], model="picked-model", context={"context_1": ["a", 1]})
        self.assertEqual(client.options.model, "picked-model")
        self.assertIn('["a", 1]', client.prompt)

    async def test_minimal_harness_is_isolated(self):
        self.edit("../bare/harness.yaml", "")
        self.edit("../bare/task.md", "做事")
        _, client = await self.run_agent([result()], harness_dir="bare", context=None)
        options = client.options
        self.assertEqual((options.tools, options.allowed_tools, options.skills, options.setting_sources), ([], [], [], []))
        self.assertEqual((options.mcp_servers, options.agents, options.hooks), ({}, None, None))
        self.assertEqual(options.system_prompt, {"type": "preset", "preset": "claude_code"})
        self.assertEqual(client.prompt, "做事")

    async def test_validate_inputs(self):
        self.assertIs(Agent.validate_inputs("example", node.HARNESS_MODEL, ""), True)
        self.assertIs(Agent.validate_inputs("example", "m", "自定义任务"), True)
        self.assertIn("model", Agent.validate_inputs("example", " ", "x"))
        for name in ["../example", "missing", "", ".hidden"]:
            self.assertIsInstance(Agent.validate_inputs(name, "m", "x"), str)
        (self.root / "example" / "task.md").unlink()
        self.assertIn("task.md", Agent.validate_inputs("example", "m", " "))
        self.assertIs(Agent.validate_inputs("example", "m", "自定义任务"), True)

    async def test_harness_errors(self):
        cases = [
            ("harness.yaml", "temperature: 1\n", "未知字段"),
            ("harness.yaml", "max_turns: true\n", "类型错误"),
            ("harness.yaml", "prompt_mode: merge\n", "prompt_mode"),
            ("harness.yaml", "tools: [Read]\n", "Bash"),
            ("skills/summarize/SKILL.md", "---\nname: other\ndescription: x\n---\n", "目录名"),
            ("sub_agents/reviewer/AGENT.md", "没有 frontmatter", "frontmatter"),
            ("systemprompt.md", "x" * (harness.ALWAYS_ON_LIMIT + 1), "超过上限"),
        ]
        for relative, text, error in cases:
            with self.subTest(relative=relative, error=error):
                original = (self.root / "example" / relative).read_text(encoding="utf-8")
                self.edit(relative, text)
                with self.assertRaisesRegex(ValueError, error):
                    harness.load("example")
                self.edit(relative, original)
        self.edit("plugins/bad.py", "HOOKS = {'PreToolUse': ['x']}\n")
        with self.assertRaisesRegex(ValueError, "HookMatcher"):
            harness.load_hooks(self.root / "example")
        shutil.copy(self.root / "example" / "tools" / "echo.py", self.root / "example" / "tools" / "echo2.py")
        with self.assertRaisesRegex(ValueError, "重复"):
            harness.load_tools(self.root / "example")

    async def test_block_rm_plugin(self):
        hook = harness.load_hooks(self.root / "example")["PreToolUse"][0].hooks[0]
        denied = await hook({"tool_input": {"command": "rm -rf /tmp/x"}}, "t1", None)
        self.assertEqual(denied["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertEqual(await hook({"tool_input": {"command": "ls"}}, "t1", None), {})

    async def test_pathcheck_plugin(self):
        hooks = harness.load_hooks(self.root / "example")
        hook = hooks["Stop"][0].hooks[0]
        existing = self.tmp / "result.json"
        existing.write_text("{}", encoding="utf-8")
        self.assertEqual(
            await hook({"last_assistant_message": f"结果文件：{existing}"}, None, None),
            {"decision": "block", "reason": "最终输出校验失败：最终回答必须是绝对路径，例如 /tmp/result.png。 请修正后只输出完整路径。"},
        )
        self.assertEqual(
            await hook({"last_assistant_message": "参考 https://example.com/a/b"}, None, None),
            {"decision": "block", "reason": "最终输出校验失败：最终回答必须是绝对路径，例如 /tmp/result.png。 请修正后只输出完整路径。"},
        )
        self.assertEqual(await hook({"last_assistant_message": f"\n{existing}\n"}, None, None), {})
        denied = await hook(
            {"last_assistant_message": "/tmp/agent-result-missing.json"},
            None,
            None,
        )
        self.assertEqual(denied["decision"], "block")
        self.assertIn("/tmp/agent-result-missing.json", denied["reason"])

    async def test_hook_feedback_is_added_to_trajectory(self):
        trajectory = ["[TASK] 输出路径"]
        hooks = harness.load_hooks(self.root / "example")
        hooks = node.wrap_hooks_for_trajectory(hooks, trajectory, "display-7")
        denied = await hooks["Stop"][0].hooks[0](
            {"last_assistant_message": "说明文字"},
            None,
            None,
        )
        self.assertEqual(denied["decision"], "block")
        self.assertEqual(len(trajectory), 2)
        self.assertTrue(trajectory[-1].startswith("[HOOK][Stop][BLOCK]"))
        self.assertEqual(events[-1], (
            "agent.trajectory",
            {
                "node_id": "display-7",
                "lines": [trajectory[-1]],
                "reset": False,
            },
        ))

    async def test_failed_and_missing_results(self):
        for messages, error in [
            ([result(is_error=True)], "执行失败"),
            ([result(subtype="error_max_turns", result=None, errors=["turn limit"])], "turn limit"),
            ([result(result=None)], "缺少 result"),
            ([], "未收到 ResultMessage"),
        ]:
            with self.subTest(error=error), self.assertRaisesRegex(RuntimeError, error):
                await self.run_agent(messages)

    async def test_timeout_and_cancellation_cleanup(self):
        self.edit("harness.yaml", "timeout: 0.01\ntools: [Bash]\n")
        client = Client(None, wait=True)
        with patch.object(node, "ClaudeSDKClient", return_value=client), self.assertRaises(TimeoutError):
            await Agent.execute("example", node.HARNESS_MODEL, "x")
        self.assertTrue(client.closed)
        self.edit("harness.yaml", "tools: [Bash]\n")
        client = Client(None, wait=True)
        with patch.object(node, "ClaudeSDKClient", return_value=client):
            task = asyncio.create_task(Agent.execute("example", node.HARNESS_MODEL, "x"))
            await asyncio.sleep(0.05)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertTrue(client.closed)

    async def test_routes_and_model_query(self):
        seen = {}

        async def models_api(request):
            seen.update(headers=dict(request.headers), query=dict(request.query))
            return web.json_response({"data": [{"id": "claude-a"}, {"id": "claude-b"}], "has_more": False})

        app = web.Application()
        app.router.add_get("/v1/models", models_api)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        self.addAsyncCleanup(runner.cleanup)
        port = site._server.sockets[0].getsockname()[1]
        self.edit(".env", f"ANTHROPIC_API_KEY=local\nANTHROPIC_BASE_URL=http://127.0.0.1:{port}\n")

        response = await node.models_route(SimpleNamespace(query={"harness": "example"}))
        self.assertEqual(json.loads(response.body), ["claude-a", "claude-b"])
        self.assertEqual(node.models, ["claude-a", "claude-b"])
        self.assertEqual((seen["headers"]["x-api-key"], seen["headers"]["anthropic-version"]), ("local", "2023-06-01"))
        self.assertEqual(seen["query"], {"limit": "1000"})
        (self.root / "example" / ".env").unlink()
        response = await node.models_route(SimpleNamespace(query={"harness": "example"}))
        self.assertEqual(response.status, 502)
        self.assertIn("ANTHROPIC_API_KEY", json.loads(response.body)["error"])
        response = await node.models_route(SimpleNamespace(query={}))
        self.assertIn("harness 名称无效", json.loads(response.body)["error"])

        info = json.loads((await node.harness_info_route(SimpleNamespace(query={"name": "example"}))).body)
        self.assertEqual((info["skills"], info["subagents"], info["mcp_tools"], info["plugins"]), (["summarize"], ["reviewer"], ["echo"], ["block_rm", "pathcheck"]))
        self.assertEqual(info["env"], {"ANTHROPIC_API_KEY": False, "ANTHROPIC_BASE_URL": False})
        self.assertIn("{{context_1}}", info["task"])
        self.assertEqual((await node.harness_info_route(SimpleNamespace(query={"name": "../x"}))).status, 400)
        self.assertEqual(json.loads((await node.harnesses_route(None)).body), ["example"])

    async def test_schema(self):
        inputs = Agent.INPUT_TYPES()
        self.assertEqual(inputs["required"]["harness_dir"][1]["options"], ["example"])
        self.assertEqual(inputs["required"]["model"][1]["options"][0], node.HARNESS_MODEL)
        self.assertIn("resume_session", inputs["optional"])
        self.assertEqual(list(Agent.RETURN_NAMES), ["result", "structured", "session_id", "trajectory"])
        self.assertTrue(Agent.fingerprint_inputs() != Agent.fingerprint_inputs())


if __name__ == "__main__":
    unittest.main(verbosity=2)
