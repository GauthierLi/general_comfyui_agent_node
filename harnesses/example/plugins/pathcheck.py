"""强制最终回复只包含一个存在的本地文件路径。"""
from pathlib import Path

from claude_agent_sdk import HookMatcher


def _validate_output(message):
    """校验最终回答是否严格为一个存在的绝对文件路径。"""
    if not isinstance(message, str):
        return "最终回答不是文本。"
    output = message.strip()
    if not output:
        return "最终回答为空，请只输出图像文件的绝对路径。"
    if len(output.splitlines()) != 1:
        return "最终回答必须只有一行，并且这一行只能是图像文件的绝对路径。"
    path = Path(output)
    if not path.is_absolute():
        return "最终回答必须是绝对路径，例如 /tmp/result.png。"
    if not path.is_file():
        return f"最终回答中的文件不存在：{path}"
    return ""


async def check_paths(input_data, tool_use_id, context):
    message = input_data.get("last_assistant_message", "")
    error = _validate_output(message)
    if not error:
        return {}
    return {
        "decision": "block",
        "reason": f"最终输出校验失败：{error} 请修正后只输出完整路径。",
    }


HOOKS = {"Stop": [HookMatcher(hooks=[check_paths])]}
