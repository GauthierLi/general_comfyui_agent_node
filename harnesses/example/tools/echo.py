from typing import Any

from claude_agent_sdk import tool


@tool(
    "echo",
    "返回输入的 text 字符串，不访问文件或网络。",
    {
        "type": "object",
        "properties": {"text": {"type": "string", "description": "需要原样返回的文本"}},
        "required": ["text"],
        "additionalProperties": False,
    },
)
async def echo(args: dict[str, Any]) -> dict[str, Any]:
    """输入 {"text": "你好"}，返回 {"content": [{"type": "text", "text": "你好"}]}。"""
    return {"content": [{"type": "text", "text": args["text"]}]}
