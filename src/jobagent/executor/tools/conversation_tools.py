"""Conversation tools - agent capabilities for handling HR replies.

Each tool delegates to the existing monitor handler functions (imported
lazily inside ``execute`` to avoid circular imports: monitor dispatches
through these tools, these tools call back into monitor's handlers).

Tool-specific parameters (e.g. reply tone) flow from the LLM's function
call arguments into the handlers, which is the whole point of the tool
layer: decisions carry parameters, not just an action name.
"""

from __future__ import annotations

from jobagent.executor.tools.base import Tool, ToolContext

# Reused by every tool via lazy monitor imports.


class AutoReplyTool(Tool):
    """Reply to a normal HR message (question / info request / scheduling)."""

    name = "auto_reply"
    description = (
        "HR 正常沟通（提问、索要信息、约时间等），生成一条自然回复。"
        "tone 参数控制回复语气风格。"
    )
    parameters = {
        "tone": {
            "type": "string",
            "enum": ["自然", "正式", "简短"],
            "description": "回复语气：自然=口语化像真人（默认）；正式=礼貌书面；简短=尽量精炼",
        },
    }

    def execute(self, ctx: ToolContext) -> str:
        from jobagent.executor import monitor

        # Respect previously dismissed reply suggestions (safety stays in Python).
        db = monitor.get_db()
        dismissed = monitor._has_dismissed_pending_reply(db, ctx.job["id"], ctx.messages)
        db.close()
        if dismissed:
            monitor.console.print("[dim]    该回复建议已放弃，跳过本轮[/dim]")
            monitor.close_tab(ctx.target_id)
            return "skipped_dismissed_reply"

        tone = str(ctx.params.get("tone") or "自然").strip() or "自然"
        return monitor._handle_auto_reply(
            ctx.job,
            ctx.target_id,
            ctx.messages,
            ctx.conversation,
            ctx.config,
            tone=tone,
        )


class NeedsResumeTool(Tool):
    """HR explicitly asked for a resume/portfolio: run the resume flow."""

    name = "needs_resume"
    description = (
        "HR 明确要求简历/作品集，走简历流程：生成定制简历并在合适时发送在线简历链接。"
        "send_online_resume 参数控制是否自动发送在线简历链接。"
    )
    parameters = {
        "send_online_resume": {
            "type": "boolean",
            "description": "是否自动发送在线简历链接（默认 true；HR 已明确只要附件时可设为 false）",
        },
    }

    def execute(self, ctx: ToolContext) -> str:
        from jobagent.executor import monitor

        send_online = ctx.params.get("send_online_resume")
        if not isinstance(send_online, bool):
            send_online = True
        return monitor._handle_resume_request(
            ctx.job,
            ctx.target_id,
            ctx.messages,
            ctx.config,
            send_online_resume=send_online,
        )


class MarkRejectedTool(Tool):
    """HR clearly rejected the candidate: mark and stop tracking."""

    name = "mark_rejected"
    description = (
        "HR 明确拒绝（不合适/已招到/岗位关闭），标记岗位为 rejected 并停止跟踪。"
    )

    def execute(self, ctx: ToolContext) -> str:
        from jobagent.executor import monitor

        if monitor.stop_requested(ctx.config):
            monitor.close_tab(ctx.target_id)
            return "stopped"
        monitor.console.print("[dim]    HR已拒绝，标记并停止跟踪[/dim]")
        db = monitor.get_db()
        monitor.update_job_status(db, ctx.job["id"], "rejected")
        monitor.add_history(db, ctx.job["id"], "rejected", "HR回复拒绝")
        db.close()
        monitor.close_tab(ctx.target_id)
        return "rejected"


class SkipTool(Tool):
    """Nothing to do this round (system notice / ad card / unclear)."""

    name = "skip"
    description = "消息无需处理（系统通知/广告卡片/无法判断语义），本轮跳过。"

    def execute(self, ctx: ToolContext) -> str:
        from jobagent.executor import monitor

        monitor.console.print("[dim]    Agent决定本轮跳过[/dim]")
        monitor.close_tab(ctx.target_id)
        return "skipped_agent_decision"


def build_conversation_registry() -> "ToolRegistry":
    """Assemble the standard registry of conversation-handling tools."""
    from jobagent.executor.tools.base import ToolRegistry

    registry = ToolRegistry()
    registry.register(AutoReplyTool())
    registry.register(NeedsResumeTool())
    registry.register(MarkRejectedTool())
    registry.register(SkipTool())
    return registry


def dispatch_conversation_tool(
    action: str,
    *,
    job: dict,
    config: dict,
    target_id: str,
    messages: list,
    conversation: dict | None = None,
    params: dict | None = None,
    registry=None,
) -> str | None:
    """Execute one action through the tool registry.

    Returns the monitor action string, or None when the action is not a
    registered tool (callers decide how to fall back).
    """
    resolved = registry if registry is not None else build_conversation_registry()
    tool = resolved.get(action)
    if tool is None:
        return None
    ctx = ToolContext(
        job=job,
        config=config,
        target_id=target_id,
        messages=messages,
        conversation=conversation,
        params=params or {},
    )
    return tool.execute(ctx)
