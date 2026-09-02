"""Tests for the Tier-2 tool layer: Tool / ToolRegistry / conversation tools."""

from unittest.mock import MagicMock, patch

import pytest

from jobagent.executor.tools import (
    AutoReplyTool,
    MarkRejectedTool,
    NeedsResumeTool,
    SkipTool,
    Tool,
    ToolContext,
    ToolRegistry,
    build_conversation_registry,
    dispatch_conversation_tool,
)
from jobagent.executor.tools.base import DECISION_META_PROPERTIES, DECISION_META_REQUIRED


class DummyTool(Tool):
    name = "dummy"
    description = "A dummy tool for testing."
    parameters = {"foo": {"type": "string", "description": "A parameter"}}
    required = ("foo",)

    def execute(self, ctx: ToolContext) -> str:
        return f"executed:{ctx.params.get('foo')}"


def test_tool_schema_includes_decision_metadata():
    schema = DummyTool().schema()
    assert schema["type"] == "function"
    fn = schema["function"]
    assert fn["name"] == "dummy"
    props = fn["parameters"]["properties"]
    assert "foo" in props
    assert "reason" in props
    assert "confidence" in props
    assert set(fn["parameters"]["required"]) == {"foo", "reason", "confidence"}


def test_registry_register_and_schemas():
    registry = ToolRegistry()
    registry.register(DummyTool())
    assert registry.names() == ["dummy"]
    schemas = registry.schemas()
    assert len(schemas) == 1
    assert schemas[0]["function"]["name"] == "dummy"


def test_registry_duplicate_registration_raises():
    registry = ToolRegistry()
    registry.register(DummyTool())
    with pytest.raises(ValueError, match="重复注册"):
        registry.register(DummyTool())


def test_build_conversation_registry_has_expected_tools():
    registry = build_conversation_registry()
    assert set(registry.names()) == {"auto_reply", "needs_resume", "mark_rejected", "skip"}
    schemas = {s["function"]["name"]: s["function"] for s in registry.schemas()}
    assert "tone" in schemas["auto_reply"]["parameters"]["properties"]
    assert "send_online_resume" in schemas["needs_resume"]["parameters"]["properties"]


def test_dispatch_conversation_tool_runs_tool():
    result = dispatch_conversation_tool(
        "dummy",
        job={"id": "j1"},
        config={},
        target_id="t1",
        messages=[],
        params={"foo": "bar"},
        registry=_make_dummy_registry(),
    )
    assert result == "executed:bar"


def test_dispatch_unknown_action_returns_none():
    result = dispatch_conversation_tool(
        "unknown",
        job={"id": "j1"},
        config={},
        target_id="t1",
        messages=[],
        registry=_make_dummy_registry(),
    )
    assert result is None


def test_dispatch_uses_default_registry_when_none_provided():
    # MarkRejectedTool requires no params; it will hit stop_requested and close_tab.
    with patch("jobagent.executor.monitor.stop_requested", return_value=True):
        with patch("jobagent.executor.monitor.close_tab") as mock_close:
            result = dispatch_conversation_tool(
                "skip",
                job={"id": "j1"},
                config={},
                target_id="t1",
                messages=[],
                params={},
            )
            assert result == "skipped_agent_decision"
            mock_close.assert_called_once_with("t1")


def test_auto_reply_tool_checks_dismissed_suggestion():
    tool = AutoReplyTool()
    ctx = ToolContext(
        job={"id": "j1"},
        config={},
        target_id="t1",
        messages=[],
        params={"tone": "正式"},
    )
    with patch("jobagent.executor.monitor._has_dismissed_pending_reply", return_value=True):
        with patch("jobagent.executor.monitor.close_tab") as mock_close:
            assert tool.execute(ctx) == "skipped_dismissed_reply"
            mock_close.assert_called_once_with("t1")


def test_auto_reply_tool_passes_tone_to_handler():
    tool = AutoReplyTool()
    ctx = ToolContext(
        job={"id": "j1"},
        config={},
        target_id="t1",
        messages=[{"sender": "hr", "text": "hi"}],
        params={"tone": "简短"},
    )
    with patch("jobagent.executor.monitor._has_dismissed_pending_reply", return_value=False):
        with patch("jobagent.executor.monitor._handle_auto_reply", return_value="auto_reply_sent") as mock_handler:
            assert tool.execute(ctx) == "auto_reply_sent"
            assert mock_handler.call_args.kwargs["tone"] == "简短"


def test_needs_resume_tool_defaults_send_online_to_true():
    tool = NeedsResumeTool()
    ctx = ToolContext(
        job={"id": "j1"},
        config={},
        target_id="t1",
        messages=[],
        params={},
    )
    with patch("jobagent.executor.monitor._handle_resume_request", return_value="needs_resume") as mock_handler:
        assert tool.execute(ctx) == "needs_resume"
        assert mock_handler.call_args.kwargs["send_online_resume"] is True


def test_needs_resume_tool_can_disable_online_resume():
    tool = NeedsResumeTool()
    ctx = ToolContext(
        job={"id": "j1"},
        config={},
        target_id="t1",
        messages=[],
        params={"send_online_resume": False},
    )
    with patch("jobagent.executor.monitor._handle_resume_request", return_value="needs_resume") as mock_handler:
        assert tool.execute(ctx) == "needs_resume"
        assert mock_handler.call_args.kwargs["send_online_resume"] is False


def test_mark_rejected_tool_respects_stop_request():
    tool = MarkRejectedTool()
    ctx = ToolContext(job={"id": "j1"}, config={}, target_id="t1", messages=[], params={})
    with patch("jobagent.executor.monitor.stop_requested", return_value=True):
        with patch("jobagent.executor.monitor.close_tab") as mock_close:
            assert tool.execute(ctx) == "stopped"
            mock_close.assert_called_once_with("t1")


def _make_dummy_registry():
    registry = ToolRegistry()
    registry.register(DummyTool())
    return registry
