"""从 harness 目录加载 agent 定义。目录结构见 README。"""
import ast
import importlib.util
import math
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

import yaml
from claude_agent_sdk import AgentDefinition, HookMatcher, SdkMcpTool
from dotenv import dotenv_values

PROJECT_ROOT = Path(__file__).resolve().parents[2]
HARNESS_ROOT = PROJECT_ROOT / "harnesses"
# 与 harness2 的 OpenCode 常驻文本上限一致。
ALWAYS_ON_LIMIT = 24000
ALWAYS_ON = [
    ("systemprompt.md", ""),
    ("guardrails.md", "# Operating Guardrails\n\n"),
    ("tool_guidance.md", ""),
    ("LongTermMEMORY.md", "# Long-Term Memory\n\n"),
]
SETTINGS = {
    "model": str,
    "max_turns": int,
    "timeout": (int, float),
    "max_budget_usd": (int, float),
    "prompt_mode": str,
    "tools": list,
    "disallowed_tools": list,
    "add_dirs": list,
    "output_format": dict,
}
HARNESS_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")
TOOL_NAME = re.compile(r"[A-Za-z0-9_-]+")
TOKEN = re.compile(r"\{\{\s*([A-Za-z0-9_]+)\s*\}\}")
COMMENT = re.compile(r"<!--.*?-->", re.S)
FRONTMATTER = re.compile(r"---\r?\n(.*?)\r?\n---\r?\n?(.*)", re.S)


@dataclass
class Harness:
    name: str
    path: Path
    model: str
    max_turns: int
    timeout: float
    max_budget_usd: float | None
    prompt_mode: str
    tools: list[str]
    disallowed_tools: list[str]
    add_dirs: list[str]
    output_format: dict | None
    always_on: str
    skills: dict[str, str]
    agents: dict[str, AgentDefinition]
    task: str


def list_harnesses():
    if not HARNESS_ROOT.is_dir():
        return []
    return sorted(
        path.name for path in HARNESS_ROOT.iterdir()
        if HARNESS_NAME.fullmatch(path.name) and (path / "harness.yaml").is_file()
    )


def resolve(name):
    """把下拉框的值解析为 HARNESS_ROOT 下的目录，拒绝越界路径。"""
    if not isinstance(name, str) or not HARNESS_NAME.fullmatch(name):
        raise ValueError(f"harness 名称无效：{name!r}")
    path = (HARNESS_ROOT / name).resolve()
    if path.parent != HARNESS_ROOT.resolve() or not (path / "harness.yaml").is_file():
        raise ValueError(f"{HARNESS_ROOT / name} 不是 harness 目录，目录中必须有 harness.yaml。")
    return path


def render(text, values):
    """替换 {{name}} 占位符，未知名称保留原样。"""
    return TOKEN.sub(lambda match: values.get(match.group(1), match.group(0)), text)


def read_text(path):
    return COMMENT.sub("", path.read_text(encoding="utf-8")).strip() if path.is_file() else ""


def read_frontmatter(path):
    match = FRONTMATTER.match(path.read_text(encoding="utf-8"))
    if not match:
        raise ValueError(f"{path} 缺少 YAML frontmatter。")
    meta = yaml.safe_load(match.group(1)) or {}
    if not isinstance(meta, dict):
        raise ValueError(f"{path} 的 frontmatter 必须是 YAML 映射。")
    description = meta.get("description")
    if not isinstance(description, str) or not description.strip():
        raise ValueError(f"{path} 的 frontmatter 必须包含非空 description。")
    return meta, match.group(2).strip()


def string_list(value, label):
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ValueError(f"{label} 必须是字符串列表，且每一项都不能为空。")
    return value


def load(name):
    path = resolve(name)
    settings = yaml.safe_load((path / "harness.yaml").read_text(encoding="utf-8")) or {}
    if not isinstance(settings, dict):
        raise ValueError(f"{path / 'harness.yaml'} 必须是 YAML 映射。")
    for key, value in settings.items():
        if key not in SETTINGS:
            raise ValueError(f"harness.yaml 含未知字段 {key}，只支持：{', '.join(SETTINGS)}。")
        if isinstance(value, bool) or not isinstance(value, SETTINGS[key]):
            raise ValueError(f"harness.yaml 字段 {key} 的类型错误。")
    max_turns = settings.get("max_turns", 30)
    timeout = float(settings.get("timeout", 600))
    prompt_mode = settings.get("prompt_mode", "append")
    if max_turns < 1:
        raise ValueError("harness.yaml 字段 max_turns 必须是正整数。")
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("harness.yaml 字段 timeout 必须是有限的正数，单位为秒。")
    if prompt_mode not in ("append", "replace"):
        raise ValueError("harness.yaml 字段 prompt_mode 只能是 append 或 replace。")
    tools = string_list(settings.get("tools", []), "harness.yaml 字段 tools")

    parts = []
    for filename, heading in ALWAYS_ON:
        text = read_text(path / filename)
        if text:
            parts.append(heading + text)
    scripts = []
    for script in sorted((path / "scripts").glob("*.py")):
        doc = ast.get_docstring(ast.parse(script.read_text(encoding="utf-8"))) or "无说明"
        scripts.append(f"- `python scripts/{script.name}`：{doc.splitlines()[0]}")
    if scripts:
        if "Bash" not in tools:
            raise ValueError("harness 含 scripts/，harness.yaml 的 tools 必须包含 Bash。")
        parts.append("# Helper scripts (run via Bash)\n\n" + "\n".join(scripts))
    always_on = "\n\n".join(parts)
    if len(always_on) > ALWAYS_ON_LIMIT:
        raise ValueError(f"常驻文本共 {len(always_on)} 字符，超过上限 {ALWAYS_ON_LIMIT}。")

    skills = {}
    for skill in sorted((path / "skills").glob("*/SKILL.md")):
        meta, _ = read_frontmatter(skill)
        if meta.get("name") != skill.parent.name:
            raise ValueError(f"{skill} 的 name 必须等于目录名 {skill.parent.name}。")
        skills[skill.parent.name] = meta["description"]

    agents = {}
    for agent in sorted((path / "sub_agents").glob("*/AGENT.md")):
        meta, body = read_frontmatter(agent)
        if not body:
            raise ValueError(f"{agent} 缺少正文。")
        model = meta.get("model")
        if model is not None and not isinstance(model, str):
            raise ValueError(f"{agent} 的 model 必须是字符串。")
        agent_tools = meta.get("tools")
        agents[agent.parent.name] = AgentDefinition(
            description=meta["description"],
            prompt=body,
            tools=None if agent_tools is None else string_list(agent_tools, f"{agent} 的 tools"),
            model=model,
        )

    return Harness(
        name=name,
        path=path,
        model=settings.get("model", ""),
        max_turns=max_turns,
        timeout=timeout,
        max_budget_usd=settings.get("max_budget_usd"),
        prompt_mode=prompt_mode,
        tools=tools,
        disallowed_tools=string_list(settings.get("disallowed_tools", []), "harness.yaml 字段 disallowed_tools"),
        add_dirs=string_list(settings.get("add_dirs", []), "harness.yaml 字段 add_dirs"),
        output_format=settings.get("output_format"),
        always_on=always_on,
        skills=skills,
        agents=agents,
        task=read_text(path / "task.md"),
    )


def load_env(path):
    """读取 harness 目录的 .env，忽略没有值的变量。"""
    return {key: value for key, value in dotenv_values(path / ".env").items() if value is not None}


def load_module(path, file):
    spec = importlib.util.spec_from_file_location(f"agent_harness.{path.name}.{file.parent.name}.{file.stem}", file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_tools(path):
    """收集 tools/*.py 中模块级的 SdkMcpTool。每次运行重新导入，修改后不需要重启。"""
    tools = []
    for file in sorted((path / "tools").glob("*.py")):
        tools += [value for value in vars(load_module(path, file)).values() if isinstance(value, SdkMcpTool)]
    names = set()
    for tool in tools:
        if not TOOL_NAME.fullmatch(tool.name) or tool.name in names:
            raise ValueError(f"MCP 工具名称无效或重复：{tool.name!r}")
        names.add(tool.name)
    return tools


def load_hooks(path):
    """合并 plugins/*.py 导出的 HOOKS，格式为 {事件名: [HookMatcher, ...]}。"""
    hooks = {}
    for file in sorted((path / "plugins").glob("*.py")):
        module_hooks = getattr(load_module(path, file), "HOOKS", None)
        if not isinstance(module_hooks, dict):
            raise ValueError(f"{file} 必须导出 HOOKS 字典。")
        for event, matchers in module_hooks.items():
            if not isinstance(matchers, list) or not all(isinstance(item, HookMatcher) for item in matchers):
                raise ValueError(f"{file} 的 HOOKS[{event!r}] 必须是 HookMatcher 列表。")
            hooks.setdefault(event, []).extend(matchers)
    return hooks


def prepare_workspace(harness, workspace):
    """把 skills 和 scripts 复制到工作区，CLI 从 .claude/skills 发现 skill。"""
    workspace.mkdir(parents=True, exist_ok=True)
    skills_dir = workspace / ".claude" / "skills"
    shutil.rmtree(skills_dir, ignore_errors=True)
    if harness.skills:
        shutil.copytree(harness.path / "skills", skills_dir)
    if (harness.path / "scripts").is_dir():
        shutil.copytree(harness.path / "scripts", workspace / "scripts", dirs_exist_ok=True)
