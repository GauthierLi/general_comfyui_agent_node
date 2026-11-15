"""拦截包含 rm -rf 的 Bash 命令。"""
from claude_agent_sdk import HookMatcher


async def block_rm(input_data, tool_use_id, context):
    if "rm -rf" not in input_data["tool_input"].get("command", ""):
        return {}
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": "guardrail 禁止执行 rm -rf。",
        }
    }


HOOKS = {"PreToolUse": [HookMatcher(matcher="Bash", hooks=[block_rm])]}
