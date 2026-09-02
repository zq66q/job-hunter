"""Tests for the Tier-2 function-calling decision path."""

from unittest.mock import MagicMock, patch

import pytest

from jobagent.executor import decider as decider_module
from jobagent.executor.decider import (
    DecisionResult,
    decide_conversation_action,
    function_calling_enabled,
)


def _config(
    enabled=True,
    min_confidence=0.6,
    function_calling=True,
    service="deepseek",
    provider="openai_compatible",
):
    return {
        "ai": {"service": service, "provider": provider},
        "monitor": {
            "agent_decisions": {
                "enabled": enabled,
                "min_confidence": min_confidence,
                "function_calling": function_calling,
            }
        },
    }


class TestFunctionCallingEnabled:
    def test_disabled_when_agent_decisions_off(self):
        assert function_calling_enabled(_config(enabled=False)) is False

    def test_disabled_when_flag_false(self):
        assert function_calling_enabled(_config(function_calling=False)) is False

    def test_enabled_for_deepseek(self):
        assert function_calling_enabled(_config(service="deepseek")) is True

    def test_enabled_for_doubao(self):
        assert function_calling_enabled(_config(service="doubao")) is True

    def test_enabled_for_custom(self):
        assert function_calling_enabled(_config(service="custom")) is True

    def test_disabled_for_anthropic(self):
        assert function_calling_enabled(_config(service="anthropic")) is False


class TestDecideWithTools:
    def test_valid_tool_call_parsed_with_params(self, monkeypatch):
        monkeypatch.setattr(
            decider_module,
            "call_openai_compatible_tool_call",
            lambda prompt, config, tools, max_tokens, **kwargs: {
                "name": "auto_reply",
                "arguments": {
                    "reason": "HR在问薪资期望",
                    "confidence": 0.92,
                    "tone": "正式",
                },
            },
        )
        result = decider_module._decide_with_tools(
            {"id": "j1", "title": "后端", "company": "X"},
            [{"sender": "hr", "text": "期望薪资多少"}],
            _config(),
        )
        assert result == DecisionResult(
            action="auto_reply",
            reason="HR在问薪资期望",
            confidence=0.92,
            params={"tone": "正式"},
        )

    def test_no_tool_call_returns_none(self, monkeypatch):
        monkeypatch.setattr(
            decider_module,
            "call_openai_compatible_tool_call",
            lambda prompt, config, tools, max_tokens, **kwargs: None,
        )
        assert (
            decider_module._decide_with_tools(
                {"id": "j1"},
                [],
                _config(),
            )
            is None
        )

    def test_low_confidence_rejected(self, monkeypatch):
        monkeypatch.setattr(
            decider_module,
            "call_openai_compatible_tool_call",
            lambda prompt, config, tools, max_tokens, **kwargs: {
                "name": "auto_reply",
                "arguments": {"reason": "猜的", "confidence": 0.3},
            },
        )
        assert (
            decider_module._decide_with_tools(
                {"id": "j1"},
                [],
                _config(),
            )
            is None
        )

    def test_unknown_action_rejected(self, monkeypatch):
        monkeypatch.setattr(
            decider_module,
            "call_openai_compatible_tool_call",
            lambda prompt, config, tools, max_tokens, **kwargs: {
                "name": "hack",
                "arguments": {"reason": "x", "confidence": 0.9},
            },
        )
        assert (
            decider_module._decide_with_tools(
                {"id": "j1"},
                [],
                _config(),
            )
            is None
        )

    def test_call_failure_returns_none(self, monkeypatch):
        def _raise(*args, **kwargs):
            raise RuntimeError("network")

        monkeypatch.setattr(decider_module, "call_openai_compatible_tool_call", _raise)
        assert (
            decider_module._decide_with_tools(
                {"id": "j1"},
                [],
                _config(),
            )
            is None
        )


class TestDecideConversationActionToolPath:
    def test_uses_tool_path_when_enabled(self, monkeypatch):
        tool_result = DecisionResult(
            action="needs_resume",
            reason="HR要简历",
            confidence=0.95,
            params={"send_online_resume": False},
        )
        monkeypatch.setattr(decider_module, "_decide_with_tools", lambda *args, **kwargs: tool_result)
        monkeypatch.setattr(decider_module, "_call_llm", lambda *args, **kwargs: "should not be called")

        result = decide_conversation_action(
            {"id": "j1", "title": "后端", "company": "X"},
            [{"sender": "hr", "text": "请发简历"}],
            _config(),
        )
        assert result == tool_result

    def test_falls_back_to_json_when_tool_path_disabled(self, monkeypatch):
        monkeypatch.setattr(decider_module, "_decide_with_tools", lambda *args, **kwargs: None)
        monkeypatch.setattr(
            decider_module,
            "_call_llm",
            lambda *args, **kwargs: '{"action": "skip", "reason": "x", "confidence": 0.8}',
        )

        result = decide_conversation_action(
            {"id": "j1", "title": "后端", "company": "X"},
            [{"sender": "hr", "text": "x"}],
            _config(function_calling=False),
        )
        assert result is not None
        assert result.action == "skip"
