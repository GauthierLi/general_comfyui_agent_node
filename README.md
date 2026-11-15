# general_comfyui_agent_node

在 ComfyUI 工作流中运行 Claude Agent 的一组自定义节点。

本仓库提供两组 ComfyUI V3 节点和一套 harness 目录规范：

- **Agent 节点**：用 Claude Agent SDK 执行任务，支持系统提示词、guardrails、skills、subagents、MCP 工具和 hooks。
- **工具节点**：文本、参数、判断、列表、循环、分支、图像预览、手动继续等流程控制节点。

## 目录结构

```
general_comfyui_agent_node/
├── custom_nodes/
│   ├── general_cc_agent_node/   # Agent 节点（Claude Agent SDK）
│   └── tool_nodes/              # 工具节点与逻辑控件
├── harnesses/
│   └── example/                 # 完整 harness 示例
├── .gitignore
└── README.md
```

`harnesses/` 与 `custom_nodes/` 必须保持在仓库根目录的同一层级。Agent 节点通过包的真实路径定位 `harnesses/`，复制节点目录会改变查找位置。

## 环境要求

- Python 3.11 或更高版本。
- 支持 V3 节点 API（`comfy_api.latest`）的 ComfyUI。
- Agent 节点依赖：

  ```text
  claude-agent-sdk==0.2.174
  python-dotenv==1.2.4
  ```

- 工具节点的逻辑控件需要支持 V3 `DynamicCombo` 的 ComfyUI 和前端，无额外依赖。

## 安装

1. 克隆仓库：

   ```bash
   git clone git@github.com:GauthierLi/general_comfyui_agent_node.git general_comfyui_agent_node
   cd general_comfyui_agent_node
   ```

2. 用运行 ComfyUI 的 Python 安装 Agent 节点依赖：

   ```bash
   /path/to/comfyui/python -m pip install -r custom_nodes/general_cc_agent_node/requirements.txt
   ```

3. 让 ComfyUI 发现这两个节点包。推荐使用符号链接，以保留仓库布局：

   ```bash
   ln -s "$(pwd)/custom_nodes/general_cc_agent_node" /path/to/ComfyUI/custom_nodes/general_cc_agent_node
   ln -s "$(pwd)/custom_nodes/tool_nodes" /path/to/ComfyUI/custom_nodes/tool_nodes
   ```

   如果 ComfyUI 已检出在本仓库的 `ComfyUI/` 子目录中，把上面的 `/path/to/ComfyUI` 换成 `"$(pwd)/ComfyUI"` 即可。

4. 配置 harness 的 API 密钥。只把示例里的 `.env.example` 复制为 `.env`，然后填写自己的密钥：

   ```bash
   cp harnesses/example/.env.example harnesses/example/.env
   ```

   ```dotenv
   ANTHROPIC_API_KEY=''
   # 通过网关访问时填写，留空则使用 https://api.anthropic.com
   # ANTHROPIC_BASE_URL=''
   ```

   `.env` 已被 `.gitignore` 忽略，不要提交到仓库。

5. 重启 ComfyUI 并刷新浏览器。节点会出现在节点库的 `agent` 和“工具”分类下。

## 快速开始

1. 在 ComfyUI 中添加 `Agent` 节点（分类 `agent`）。
2. 在 `harness_dir` 下拉框选择 `harnesses/` 下的 harness，例如 `example`。
3. `task` 留空时使用该 harness 的 `task.md`；也可以直接填写任务，并用 `{{context_N}}` 引用上游数据。
4. 将上游数据接到 `context_1`、`context_2` 等输入。连接一个后会自动出现下一个，最多 100 个。
5. 从 `result`、`structured`、`session_id`、`trajectory` 输出取结果，或把 `session_id` 接回另一个 Agent 节点的 `resume_session` 继续会话。

节点下方的面板会显示 harness 概要、任务和实时 trajectory。标题栏左上角的 `↻` 按钮会重新扫描 `harnesses/`、重读 `.env` 并刷新模型列表。

## Agent 节点

节点 ID 为 `AgentNode`，显示名为 `Agent`。

| 输入 | 行为 |
| --- | --- |
| `harness_dir` | 下拉选择 harness。后端只接受 `harnesses/` 下的直接子目录 |
| `model` | `(harness 默认)` 使用 `harness.yaml` 的 `model`。其余选项来自 Anthropic `GET /v1/models` |
| `task` | 留空时使用 `task.md`。可用 `{{context_N}}` 引用上游数据，未连接的占位符保留原样 |
| `context_N` | 可选，非字符串值转为 JSON |
| `resume_session` | 可选，接上游 `session_id` 继续会话。只能接同一个 harness 的会话 |

| 输出 | 内容 |
| --- | --- |
| `result` | 最终回复 |
| `structured` | 配置 `output_format` 时的 JSON，否则为空字符串 |
| `session_id` | 会话 ID |
| `trajectory` | 第一行 `[TASK]` 是实际任务，之后是 `[ASSISTANT]`、`[THINKING]`、`[ACTION]`、`[OBSERVATION]`、`[ERROR]` 格式的轨迹 |

完整说明见 [`custom_nodes/general_cc_agent_node/README.md`](custom_nodes/general_cc_agent_node/README.md)。

## Harness

harness 放在 `harnesses/<名称>/`。只有包含 `harness.yaml` 的直接子目录会出现在下拉框中。`harnesses/example/` 是一个完整示例。

| 路径 | 组件 | 用法 |
| --- | --- | --- |
| `harness.yaml` | 运行参数 | 支持 `model`、`max_turns`、`timeout`、`prompt_mode`、`tools`、`disallowed_tools`、`add_dirs`、`max_budget_usd`、`output_format` |
| `systemprompt.md` | 系统提示词 | 每次调用都在上下文中 |
| `guardrails.md` | Guardrails 提示词层 | 加标题 `# Operating Guardrails` 后进入上下文 |
| `tool_guidance.md` | 工具使用说明 | 每次调用都在上下文中 |
| `LongTermMEMORY.md` | Memory | 加标题 `# Long-Term Memory` 后进入上下文，运行期间只读 |
| `task.md` | 默认任务 | 节点 `task` 留空时使用 |
| `skills/<n>/SKILL.md` | Skills | frontmatter 必须有 `name`（等于目录名）和 `description` |
| `sub_agents/<n>/AGENT.md` | Subagents | frontmatter 必须有 `description`，可选 `tools`、`model` |
| `scripts/<n>.py` | 脚本 | 复制到工作区 `scripts/`，docstring 第一行写入常驻文本。要求 `tools` 包含 `Bash` |
| `tools/<n>.py` | MCP 工具 | 模块级 `@tool` 对象自动注册为 `mcp__harness__<name>` |
| `plugins/<n>.py` | Hooks | 导出 `HOOKS = {"PreToolUse": [HookMatcher(...)]}`，在工具循环中执行 |
| `.env` | 环境变量 | `ANTHROPIC_API_KEY` 和可选的 `ANTHROPIC_BASE_URL`，只传给本 harness 的 agent |

常驻文本按 `systemprompt.md`、`guardrails.md`、`tool_guidance.md`、`LongTermMEMORY.md`、脚本索引的顺序拼接，上限 24000 字符。文件中的 HTML 注释不进入上下文，可用占位符 `{{date}}` 和 `{{working_directory}}`。

`harness.yaml` 的完整字段说明见 [`harnesses/example/harness.yaml`](harnesses/example/harness.yaml)。

## 工具节点

工具节点位于独立的 `tool_nodes` 包，分类统一为“工具”。

| 节点 | 说明 |
| --- | --- |
| 文本展示 | 接收文本或 ComfyUI 输出列表，预览并输出 |
| 自定义参数 | 按 JSON 配置输出多组不同类型（`int`、`float`、`bool`、`str`）的参数 |
| 手动继续 | 暂停工作流，点击继续后原样输出输入值 |
| 判断 | 对 `int`、`float` 或 `str` 做比较，输出 `BOOLEAN` |
| pop | 取出列表第一个元素和剩余列表，适合在 While 中逐个处理 |
| accumulate | 把元素追加到列表末尾，适合在 While 中收集每轮结果 |
| list_string_transfer | 在列表和字符串之间转换，支持换行、逗号、空格分隔 |
| image_path_preview | 按图像路径读取并在节点上预览，无输出 |

此外还移植了 `ComfyUI-Easy-Use` 的 47 个逻辑节点，包括类型、数学、开关、索引开关、While/For 循环、分支、判断、转换、数组、输出和工具节点。节点 ID 和显示名都不带 `easy` 前缀，使用旧 ID 保存的工作流无法加载这些节点。

循环与各节点的详细用法见 [`custom_nodes/tool_nodes/README.md`](custom_nodes/tool_nodes/README.md)。

## 运行与隔离

- 工作区为 ComfyUI 输出目录下的 `agent/<harness 名称>/`，同一 harness 的多次运行共用工作区。
- 每次运行前重新复制 `skills/` 到工作区 `.claude/skills/`，并复制 `scripts/`。
- 节点不读取运行用户的 `~/.claude` 配置；有 skill 时只加载工作区的 project 配置。
- `harness.yaml` 的 `tools` 内建工具全部自动放行。有 skill 时自动加入 `Skill`，有 subagent 时自动加入 `Agent`。
- `.env` 的变量只传给本次运行的 CLI 子进程，不写入 ComfyUI 进程环境。
- `tools/`、`plugins/` 的 Python 代码在 ComfyUI 进程内以相同权限运行，每次运行重新导入。使用第三方 harness 前必须审查这些代码。
- 工具允许列表和 hook 不是操作系统沙箱。`timeout` 取消整个会话，但忽略取消的同步代码和工具另起的进程不能保证按时停止。

## 测试

工具节点测试需要已安装 ComfyUI 依赖的 Python 3.12 环境。在仓库根目录运行：

```bash
PYTHONPATH=ComfyUI python3.12 -m unittest discover -s custom_nodes/tool_nodes -p 'test_*.py' -v
node custom_nodes/tool_nodes/test_custom_parameters.cjs
node custom_nodes/tool_nodes/test_logic_flow.cjs
```

Agent 节点测试：

```bash
cd ComfyUI
/path/to/comfyui/python -I ../custom_nodes/general_cc_agent_node/tests/test_node.py
```

测试使用真实 SDK 类型、ComfyUI V3 API 和本地模拟服务，不请求真实模型，不能替代界面验收。

## 文档

- [Agent 节点说明](custom_nodes/general_cc_agent_node/README.md)
- [工具节点说明](custom_nodes/tool_nodes/README.md)
- [harness 示例](harnesses/example/)
- [harness.yaml 字段](harnesses/example/harness.yaml)
