"""Tool layer foundation - the Tier-2 agent upgrade of job-agent.

A "tool" is a named, schema-described capability the agent can choose to
invoke (send a reply, hand off a resume, mark a rejection...). The decision
layer (decider) picks a tool - optionally via LLM function calling - and the
monitor loop dispatches execution through the ToolRegistry.

Design points (mirrors the Tier-1 philosophy):
- Tools are thin wrappers: all heavyweight logic stays in the existing
  monitor handler functions; tools only describe + delegate.
- Safety stays in Python: idempotency checks, rejection detection, and
  confidence gating are enforced by callers, not by the LLM.
- Every tool schema is injected with standard decision metadata parameters
  (``reason`` + ``confidence``) so the LLM must justify each call.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

# Standard decision-metadata parameters merged into every tool schema. The
# LLM must provide them for each call; Python validates them afterwards.
DECISION_META_PROPERTIES = {
    "reason": {
        "type": "string",
        "description": "简短理由（50字内），说明为什么选择这个动作",
    },
    "confidence": {
        "type": "number",
        "description": "对本次判断的置信度，0.0 到 1.0",
    },
}
DECISION_META_REQUIRED = ("reason", "confidence")


@dataclass
class ToolContext:
    """Everything a tool needs to execute one agent decision."""

    job: dict
    config: dict
    target_id: str
    messages: list
    conversation: dict | None = None
    params: dict = field(default_factory=dict)


class Tool(ABC):
    """A single agent capability with an OpenAI-compatible function schema."""

    #: Unique tool name (also the action name used by the decision layer).
    name: str = ""
    #: One-line description shown to the LLM inside the function schema.
    description: str = ""
    #: Tool-specific parameters (JSON-schema ``properties``). Decision
    #: metadata (reason/confidence) is merged in automatically.
    parameters: dict = {}
    #: Tool-specific required parameter names.
    required: tuple = ()

    def schema(self) -> dict:
        """Build the OpenAI ``tools=[...]`` function schema for this tool."""
        properties = dict(self.parameters)
        properties.update(DECISION_META_PROPERTIES)
        required = list(self.required) + list(DECISION_META_REQUIRED)
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }

    @abstractmethod
    def execute(self, ctx: ToolContext) -> str:
        """Run the tool; returns the monitor action string."""


class ToolRegistry:
    """Registry of available tools; the agent's "hands and feet" catalogue."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if not tool.name:
            raise ValueError("工具必须有 name")
        if tool.name in self._tools:
            raise ValueError(f"工具重复注册: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return list(self._tools.keys())

    def schemas(self) -> list[dict]:
        """All tool schemas in OpenAI function-calling format."""
        return [tool.schema() for tool in self._tools.values()]
