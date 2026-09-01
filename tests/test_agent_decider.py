"""Tests for the agent decision layer (jobagent.executor.decider)."""

import pytest

from jobagent.executor.decider import (
    CONVERSATION_ACTIONS,
    DecisionResult,
    agent_decisions_enabled,
    decide_conversation_action,
    decide_follow_up,
    get_min_confidence,
    record_decision,
)
from jobagent.executor import decider as decider_module


def _config(enabled=True, min_confidence=0.6):
    return {
        "monitor": {
            "agent_decisions": {
                "enabled": enabled,
                "min_confidence": min_confidence,
            }
        }
    }


class TestAgentDecisionsEnabled:
    def test_disabled_by_default(self):
        assert agent_decisions_enabled({}) is False
        assert agent_decisions_enabled({"monitor": {}}) is False

    def test_enabled(self):
        assert agent_decisions_enabled(_config()) is True

    def test_malformed_sections(self):
        assert agent_decisions_enabled({"monitor": None}) is False
        assert agent_decisions_enabled({"monitor": {"agent_decisions": "yes"}}) is False


class TestGetMinConfidence:
    def test_default(self):
        assert get_min_confidence({}) == 0.6

    def test_custom(self):
        assert get_min_confidence(_config(min_confidence=0.9)) == 0.9

    def test_invalid_falls_back(self):
        assert get_min_confidence({"monitor": {"agent_decisions": {"min_confidence": "bad"}}}) == 0.6

    def test_clamped(self):
        assert get_min_confidence({"monitor": {"agent_decisions": {"min_confidence": 5}}}) == 1.0


class TestParseDecisionResponse:
    def test_valid_json(self):
        result = decider_module._parse_decision_response(
            '{"action": "auto_reply", "reason": "HR在问薪资期望", "confidence": 0.9}',
            CONVERSATION_ACTIONS,
            0.6,
        )
        assert result == DecisionResult("auto_reply", "HR在问薪资期望", 0.9)

    def test_json_in_code_fence(self):
        result = decider_module._parse_decision_response(
            '```json\n{"action": "skip", "reason": "广告卡片", "confidence": 0.8}\n```',
            CONVERSATION_ACTIONS,
            0.6,
        )
        assert result is not None
        assert result.action == "skip"

    def test_none_text(self):
        assert decider_module._parse_decision_response(None, CONVERSATION_ACTIONS, 0.6) is None

    def test_not_json(self):
        assert decider_module._parse_decision_response("我认为应该回复", CONVERSATION_ACTIONS, 0.6) is None

    def test_unknown_action(self):
        assert (
            decider_module._parse_decision_response(
                '{"action": "delete_everything", "reason": "x", "confidence": 1.0}',
                CONVERSATION_ACTIONS,
                0.6,
            )
            is None
        )

    def test_low_confidence_rejected(self):
        assert (
            decider_module._parse_decision_response(
                '{"action": "auto_reply", "reason": "猜的", "confidence": 0.3}',
                CONVERSATION_ACTIONS,
                0.6,
            )
            is None
        )

    def test_missing_confidence_rejected(self):
        assert (
            decider_module._parse_decision_response(
                '{"action": "auto_reply", "reason": "x"}',
                CONVERSATION_ACTIONS,
                0.6,
            )
            is None
        )

    def test_long_reason_truncated(self):
        result = decider_module._parse_decision_response(
            '{"action": "auto_reply", "reason": "' + "长" * 300 + '", "confidence": 0.9}',
            CONVERSATION_ACTIONS,
            0.6,
        )
        assert result is not None
        assert len(result.reason) <= 201


class TestDecideConversationAction:
    def test_disabled_returns_none(self):
        assert decide_conversation_action({"id": "j1"}, [], _config(enabled=False)) is None

    def test_unavailable_llm_returns_none(self, monkeypatch):
        monkeypatch.setattr(decider_module, "_call_llm", lambda prompt, config, max_tokens=600: None)
        assert decide_conversation_action({"id": "j1", "title": "t"}, [], _config()) is None

    def test_valid_decision(self, monkeypatch):
        monkeypatch.setattr(
            decider_module,
            "_call_llm",
            lambda prompt, config, max_tokens=600: '{"action": "needs_resume", "reason": "HR要简历", "confidence": 0.95}',
        )
        monkeypatch.setattr(decider_module, "_get_job_history_summary", lambda job_id, limit=6: "无")
        result = decide_conversation_action({"id": "j1", "title": "后端", "company": "X"}, [{"sender": "hr", "text": "发份简历看看"}], _config())
        assert result is not None
        assert result.action == "needs_resume"


class TestDecideFollowUp:
    def test_disabled_returns_none(self):
        assert decide_follow_up({"id": "j1"}, _config(enabled=False)) is None

    def test_follow_up_allowed(self, monkeypatch):
        monkeypatch.setattr(
            decider_module,
            "_call_llm",
            lambda prompt, config, max_tokens=600: '{"action": "follow_up", "reason": "匹配度高", "confidence": 0.85}',
        )
        monkeypatch.setattr(decider_module, "_get_job_history_summary", lambda job_id, limit=6: "无")
        result = decide_follow_up({"id": "j1", "title": "t", "company": "c"}, _config())
        assert result is not None
        assert result.action == "follow_up"

    def test_conversation_action_not_allowed_in_follow_up(self, monkeypatch):
        """auto_reply must not be accepted by the follow-up decider (whitelist)."""
        monkeypatch.setattr(
            decider_module,
            "_call_llm",
            lambda prompt, config, max_tokens=600: '{"action": "auto_reply", "reason": "x", "confidence": 1.0}',
        )
        assert decide_follow_up({"id": "j1"}, _config()) is None
