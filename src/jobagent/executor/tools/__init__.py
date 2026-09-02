"""Agent tool layer (Tier-2): Tool base class, ToolRegistry, conversation tools.

Usage:
    from jobagent.executor.tools import build_conversation_registry, dispatch_conversation_tool

    registry = build_conversation_registry()
    registry.schemas()  # -> OpenAI function-calling schemas for the LLM
    dispatch_conversation_tool("auto_reply", job=..., config=..., ...)
"""

from jobagent.executor.tools.base import (
    DECISION_META_PROPERTIES,
    DECISION_META_REQUIRED,
    Tool,
    ToolContext,
    ToolRegistry,
)
from jobagent.executor.tools.conversation_tools import (
    AutoReplyTool,
    MarkRejectedTool,
    NeedsResumeTool,
    SkipTool,
    build_conversation_registry,
    dispatch_conversation_tool,
)

__all__ = [
    "DECISION_META_PROPERTIES",
    "DECISION_META_REQUIRED",
    "Tool",
    "ToolContext",
    "ToolRegistry",
    "AutoReplyTool",
    "NeedsResumeTool",
    "MarkRejectedTool",
    "SkipTool",
    "build_conversation_registry",
    "dispatch_conversation_tool",
]
