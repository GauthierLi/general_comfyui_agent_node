# 通用 Agent 节点

节点 `Agent`（ID `AgentNode`，分类 `agent`）从一个 harness 目录加载 agent 定义，用 Claude Agent SDK 执行任务。
harness 的组件划分来自论文 Harness²（arXiv 2610.14224）和 `personal-code/harness2`。
一个工作流可以放多个 `Agent` 节点，每个节点选择各自的 harness。

运行环境要求 Python 3.11 或更高版本，以及支持 V3 的 ComfyUI。

## 安装

1. 用户用运行 ComfyUI 的 Python 安装本目录的 `requirements.txt`。
2. 用户把 `harnesses/<名称>/.env.example` 复制为同目录的 `.env`，并填写 `ANTHROPIC_API_KEY`。
3. 用户重启 ComfyUI，并刷新浏览器。

```bash
/path/to/comfyui/python -m pip install -r /root/ComateProjects/chats/baidu/personal-code/icafe-autolabel/custom_nodes/general_cc_agent_node/requirements.txt
```

## harness 目录

harness 放在 `icafe-autolabel/harnesses/<名称>/`。只有包含 `harness.yaml` 的子目录会出现在下拉框中。
`harnesses/example/` 是完整示例。

| 路径 | 组件 | 用法 |
| --- | --- | --- |
| `harness.yaml` | 运行参数 | 字段与说明见 `harnesses/example/harness.yaml` |
| `systemprompt.md` | 系统提示词 | 每次调用都在上下文中 |
| `guardrails.md` | Guardrails 提示词层 | 加标题 `# Operating Guardrails` 后进入上下文 |
| `tool_guidance.md` | 工具使用说明 | 每次调用都在上下文中 |
| `LongTermMEMORY.md` | Memory | 加标题 `# Long-Term Memory` 后进入上下文。运行期间只读 |
| `task.md` | 默认任务 | 节点 `task` 留空时使用 |
| `skills/<n>/SKILL.md` | Skills | frontmatter 必须有 `name`（等于目录名）和 `description`。模型调用 `Skill` 工具时才加载正文 |
| `sub_agents/<n>/AGENT.md` | Subagents | frontmatter 必须有 `description`，可选 `tools`、`model`。正文是 subagent 的提示词 |
| `scripts/<n>.py` | 脚本 | 复制到工作区 `scripts/`，docstring 第一行写入常驻文本。要求 `tools` 包含 `Bash` |
| `tools/<n>.py` | MCP 工具 | 模块级 `@tool` 对象自动注册为 `mcp__harness__<name>` |
| `plugins/<n>.py` | Plugins（hook） | 导出 `HOOKS = {"PreToolUse": [HookMatcher(...)]}`，在工具循环中执行 |
| `.env` | 环境变量 | 包括 `ANTHROPIC_API_KEY` 和可选的 `ANTHROPIC_BASE_URL`。只传给本 harness 的 agent |

常驻文本按 `systemprompt.md`、`guardrails.md`、`tool_guidance.md`、`LongTermMEMORY.md`、脚本索引的顺序拼接，上限 24000 字符。
文件中的 HTML 注释不进入上下文。常驻文本可用占位符 `{{date}}` 和 `{{working_directory}}`。
`prompt_mode: append` 把常驻文本追加到 Claude Code 默认系统提示词，`replace` 则完全替换。

## 节点输入与输出

| 输入 | 行为 |
| --- | --- |
| `harness_dir` | 下拉选择 harness。后端只接受 `harnesses/` 下的直接子目录 |
| `model` | `(harness 默认)` 使用 `harness.yaml` 的 `model`。其余选项来自 Anthropic `GET /v1/models` |
| `task` | 留空时使用 `task.md`。可用 `{{context_N}}` 引用上游数据，未连接的占位符保留原样 |
| `context_N` | 可选，连接一个后自动出现下一个。非字符串值转为 JSON |
| `resume_session` | 可选，接上游 `session_id` 继续会话。只能接同一个 harness 的会话 |

| 输出 | 内容 |
| --- | --- |
| `result` | 最终回复 |
| `structured` | `harness.yaml` 配置 `output_format` 时的 JSON，否则为空字符串 |
| `session_id` | 会话 ID |
| `trajectory` | 第一行 `[TASK]` 是实际发给 agent 的任务（占位符已替换），之后是 `[ASSISTANT]`、`[THINKING]`、`[ACTION]`、`[OBSERVATION]`、`[ERROR]` 格式的轨迹 |

节点下方的只读面板显示 harness 概要和校验结果。`task` 留空时，灰色占位文字显示 `task.md` 内容。
节点下方三个文本框依次为“任务 task”“harness 概要”“实时 trajectory”，每个文本框上方有标题和分界线。
用户拖动 `task` 和概要面板的下边缘（光标变为上下箭头）可以调整各自高度，trajectory 面板占用剩余高度。高度随工作流保存。
节点标题栏左上角的 `↻` 按钮重新扫描 `harnesses/`，重新读取当前 harness 和它的 `.env`，并重新查询模型。
打开工作流后，前端用第一个 `Agent` 节点所选 harness 的 `.env` 查询一次模型。查询失败时只能选 `(harness 默认)` 和工作流中已保存的值。
运行时节点显示工具调用次数和最近一次调用的工具名。
节点底部的只读面板实时显示 trajectory，每条 SDK 消息到达时追加一次。新一次运行开始时清空。
后端通过 WebSocket 事件 `agent.trajectory` 广播到所有打开的页面，运行中刷新页面会丢失已显示的行。
下游节点仍在运行结束后才收到完整的 `trajectory` 输出。

## 运行与隔离

- 工作区为 ComfyUI 输出目录下的 `agent/<harness 名称>/`。同一 harness 的多次运行共用工作区。
- 每次运行前，节点重新复制 `skills/` 到工作区 `.claude/skills/`，并复制 `scripts/`。
- 节点不读取运行用户的 `~/.claude` 配置。有 skill 时只加载工作区的 project 配置。
- `tools` 中的内建工具全部自动放行。有 skill 时自动加入 `Skill`，有 subagent 时自动加入 `Agent`。
- `strict_mcp_config` 只允许 harness 自己的 MCP 工具。
- `.env` 的变量只传给本次运行的 CLI 子进程，不写入 ComfyUI 进程环境。面板只显示变量是否已设置。
- `tools/`、`plugins/` 的 Python 代码在 ComfyUI 进程内以相同权限运行，每次运行重新导入。用户必须审查这些代码。
- 工具允许列表和 hook 不是操作系统沙箱。
- `timeout` 取消整个会话。忽略取消的同步代码和工具另起的进程不能保证按时停止。

## 离线测试

```bash
cd /root/ComateProjects/chats/baidu/personal-code/icafe-autolabel/ComfyUI
/root/ComateProjects/chats/baidu/personal-code/icafe-autolabel/tests/.venv/bin/python -I ../custom_nodes/general_cc_agent_node/tests/test_node.py
```

测试使用真实 SDK 类型、ComfyUI V3 API 和本地 aiohttp 服务模拟 `/v1/models`。
模型客户端与 `PromptServer` 使用替身，不请求网络模型，不能替代真实界面验收。
