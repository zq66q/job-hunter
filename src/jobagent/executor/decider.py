"""Agent decision layer - LLM-driven decisions for the monitor loop.

This is the Tier-1 agent upgrade of job-agent: instead of a hardcoded rule
cascade deciding what to do with each HR conversation, the situation (job
info + conversation transcript + interaction history) is presented to the
LLM, which chooses the next action. Python code only validates, guards,
and executes the decision.

Key design points:
- Config-gated: ``monitor.agent_decisions.enabled`` (default: false) keeps
  legacy rule-based behavior untouched when disabled.
- Whitelist + confidence: the LLM must answer with a strict JSON object whose
  ``action`` is one of the known actions and whose ``confidence`` meets
  ``monitor.agent_decisions.min_confidence`` (default: 0.6). Anything else is
  rejected and callers fall back to the legacy rule path.
- Decision trail: every executed decision is recorded into the ``history``
  table, so later decisions can see what was decided before (lightweight
  agent memory).
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from rich.console import Console

from jobagent.ai.credentials import (
    call_anthropic_text,
    call_openai_compatible_tool_call,
    get_ai_service,
)
from jobagent.cancellation import OperationCancelled, run_cancellable
from jobagent.db import get_db
from jobagent.executor.tools import DECISION_META_REQUIRED, build_conversation_registry

console = Console()

# Actions the conversation decider may choose from.
CONVERSATION_ACTIONS = ("auto_reply", "needs_resume", "mark_rejected", "skip")
# Actions the follow-up decider may choose from.
FOLLOW_UP_ACTIONS = ("follow_up", "skip")

DEFAULT_MIN_CONFIDENCE = 0.6


@dataclass
class DecisionResult:
    """A validated LLM decision."""

    action: str
    reason: str
    confidence: float
    # Tool-call arguments (Tier-2): optional parameters chosen by the LLM
    # alongside the action, e.g. {"tone": "正式"} for auto_reply.
    params: dict | None = None


def _agent_decisions_config(config: dict) -> dict:
    section = config.get("monitor", {}) if isinstance(config, dict) else {}
    value = section.get("agent_decisions", {}) if isinstance(section, dict) else {}
    return value if isinstance(value, dict) else {}


def agent_decisions_enabled(config: dict) -> bool:
    """Whether LLM-driven decisions are enabled for the monitor loop."""
    return bool(_agent_decisions_config(config).get("enabled", False))


def get_min_confidence(config: dict) -> float:
    raw = _agent_decisions_config(config).get("min_confidence", DEFAULT_MIN_CONFIDENCE)
    try:
        return max(0.0, min(float(raw), 1.0))
    except (TypeError, ValueError):
        return DEFAULT_MIN_CONFIDENCE


def function_calling_enabled(config: dict) -> bool:
    """Whether to ask the LLM to pick tools via OpenAI function calling.

    Only OpenAI-compatible providers (deepseek / doubao / custom) support this
    in the current implementation. Anthropic falls back to the JSON decision
    path even when this flag is true.
    """
    if not agent_decisions_enabled(config):
        return False
    flag = _agent_decisions_config(config).get("function_calling", False)
    return bool(flag) and get_ai_service(config) in {"deepseek", "doubao", "custom"}


def _call_llm(prompt: str, config: dict, max_tokens: int = 600) -> str | None:
    """Call the configured AI service; return None on any recoverable failure."""
    ai_cfg = config.get("ai", {}) if isinstance(config, dict) else {}
    try:
        return run_cancellable(
            lambda: call_anthropic_text(
                prompt,
                config,
                max_tokens,
                timeout=ai_cfg.get("timeout_seconds", 180),
                purpose="agent_decision",
            ),
            config,
        )
    except OperationCancelled:
        raise
    except Exception as exc:
        console.print(f"[red]决策调用失败: {exc}[/red]")
        return None


def _build_decision_prompt(job: dict, messages: list[dict]) -> str:
    """Prompt shared by JSON and function-calling decision paths."""
    return f"""你是一个求职 Agent 的决策中枢。请根据岗位信息、对话记录、交互历史，决定下一步动作。

## 岗位信息
- 职位：{job.get('title', '')}
- 公司：{job.get('company', '')}
- 薪资：{job.get('salary', '')}
- 当前状态：{job.get('status', '')}

## 最近对话记录（HR 有新回复，等待处理）
{_format_messages_for_prompt(messages)}

## 交互历史（最近的动作记录）
{_get_job_history_summary(job.get('id', ''))}

## 判断原则
- 以对话内容为准，历史记录仅作参考
- 不确定时选择 skip，宁可少做不要做错
- 谨慎判断拒绝：只有明确拒绝才选 mark_rejected
- 选择工具时给出置信度和简短理由"""


def _decide_with_tools(
    job: dict,
    messages: list[dict],
    config: dict,
) -> DecisionResult | None:
    """Use OpenAI function calling to pick a tool and its parameters.

    Returns None when the model makes no tool call or the call fails validation;
    callers fall back to the legacy JSON decision path.
    """
    tools = build_conversation_registry().schemas()
    if not tools:
        return None

    prompt = _build_decision_prompt(job, messages)
    ai_cfg = config.get("ai", {}) if isinstance(config, dict) else {}
    try:
        call = run_cancellable(
            lambda: call_openai_compatible_tool_call(
                prompt,
                config,
                tools,
                max_tokens=600,
                timeout=ai_cfg.get("timeout_seconds", 180),
                purpose="agent_decision",
            ),
            config,
        )
    except OperationCancelled:
        raise
    except Exception as exc:
        console.print(f"[red]工具调用决策失败: {exc}[/red]")
        return None

    if not isinstance(call, dict):
        return None

    action = str(call.get("name") or "").strip()
    if action not in CONVERSATION_ACTIONS:
        return None

    args = call.get("arguments") if isinstance(call.get("arguments"), dict) else {}
    try:
        confidence = float(args.get("confidence", 0.0))
    except (TypeError, ValueError):
        return None
    min_confidence = get_min_confidence(config)
    if confidence < min_confidence:
        return None

    reason = str(args.get("reason", "")).strip()
    if len(reason) > 200:
        reason = reason[:200] + "…"

    # Everything except the standard decision metadata is passed as tool params
    # to the executor (e.g. tone for auto_reply, send_online_resume for needs_resume).
    params = {k: v for k, v in args.items() if k not in DECISION_META_REQUIRED}
    return DecisionResult(action=action, reason=reason, confidence=confidence, params=params)


def _parse_decision_response(
    text: str | None,
    allowed_actions: tuple[str, ...],
    min_confidence: float,
) -> DecisionResult | None:
    """Parse and validate the LLM decision response.

    Returns None when the response is not usable (callers fall back to the
    legacy rule-based path).
    """
    if not text:
        return None
    # Tolerate code fences around the JSON.
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.lower().startswith("json"):
            stripped = stripped[4:]
        stripped = stripped.strip()
    try:
        data = json.loads(stripped)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    action = data.get("action")
    if action not in allowed_actions:
        return None
    try:
        confidence = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        return None
    if confidence < min_confidence:
        return None
    reason = str(data.get("reason", "")).strip()
    if len(reason) > 200:
        reason = reason[:200] + "…"
    return DecisionResult(action=action, reason=reason, confidence=confidence)


def _get_job_history_summary(job_id: str, limit: int = 6) -> str:
    """Recent history actions for a job, as compact prompt context."""
    db = get_db()
    try:
        rows = db.execute(
            "SELECT action, created_at FROM history WHERE job_id = ? ORDER BY id DESC LIMIT ?",
            (job_id, limit),
        ).fetchall()
    except Exception:
        rows = []
    finally:
        db.close()
    if not rows:
        return "（无历史记录，首次交互）"
    parts = []
    for row in rows:
        action = row["action"] if isinstance(row, dict) else row[0]
        created = row["created_at"] if isinstance(row, dict) else row[1]
        parts.append(f"{action}({created})")
    return "、".join(parts)


def _format_messages_for_prompt(messages: list[dict], limit: int = 400) -> str:
    """Render the tail of a conversation transcript for the prompt."""
    lines = []
    for msg in messages[-12:]:
        sender = msg.get("sender") or msg.get("role") or "unknown"
        text = str(msg.get("text") or msg.get("content") or "").strip()
        if not text:
            continue
        if len(text) > limit:
            text = text[:limit] + "…"
        lines.append(f"[{sender}] {text}")
    return "\n".join(lines) if lines else "（无可读消息）"


def decide_conversation_action(
    job: dict,
    messages: list[dict],
    config: dict,
) -> DecisionResult | None:
    """Ask the LLM what to do with an HR conversation that has a new reply.

    Tier-2 tool layer: when ``monitor.agent_decisions.function_calling`` is
    enabled and the provider is OpenAI-compatible, the LLM picks a registered
    tool (and its parameters, e.g. reply tone) through function calling.
    Otherwise the original JSON decision path is used.

    Returns None when disabled, unavailable, or the response fails validation;
    callers must then fall back to the legacy rule-based cascade.
    """
    if not agent_decisions_enabled(config):
        return None

    if function_calling_enabled(config):
        return _decide_with_tools(job, messages, config)

    prompt = _build_decision_prompt(job, messages) + """

## 可选动作（只能选一个）
1. auto_reply — HR 正常沟通（提问/索要信息/约时间等），应当回复消息
2. needs_resume — HR 明确要求简历/作品集，应当走简历流程
3. mark_rejected — HR 明确拒绝（不合适/已招到/岗位关闭），应当标记拒绝并停止跟踪
4. skip — 消息无需处理（系统通知/广告卡片/无法判断语义），本轮跳过

## 输出要求
只输出一个 JSON 对象，不要加任何其他文字：
{"action": "auto_reply|needs_resume|mark_rejected|skip", "reason": "简短理由（50字内）", "confidence": 0.0到1.0的数字}"""

    response = _call_llm(prompt, config)
    return _parse_decision_response(response, CONVERSATION_ACTIONS, get_min_confidence(config))


def decide_follow_up(job: dict, config: dict) -> DecisionResult | None:
    """Ask the LLM whether a stale (no-reply) job is worth following up.

    Returns None when disabled/unvalidated; callers fall back to the legacy
    behavior of always following up.
    """
    if not agent_decisions_enabled(config):
        return None

    follow_up_cfg = config.get("follow_up", {}) if isinstance(config, dict) else {}
    interval_hours = follow_up_cfg.get("interval_hours", 48)

    prompt = f"""你是一个求职 Agent 的决策中枢。以下岗位此前已发送招呼消息，但超过 {interval_hours} 小时无 HR 回复。请判断是否值得跟进。

## 岗位信息
- 职位：{job.get('title', '')}
- 公司：{job.get('company', '')}
- 薪资：{job.get('salary', '')}
- 状态更新时间：{job.get('updated_at', '')}

## 交互历史
{_get_job_history_summary(job.get('id', ''))}

## 可选动作（只能选一个）
1. follow_up — 值得跟进（岗位匹配度高/HR 活跃/发送时间尚短）
2. skip — 不值得跟进（已跟进过/岗位可能已关闭/公司异常/间隔太久已无意义）

## 输出要求
只输出一个 JSON 对象，不要加任何其他文字：
{{"action": "follow_up|skip", "reason": "简短理由（50字内）", "confidence": 0.0到1.0的数字}}"""

    response = _call_llm(prompt, config)
    return _parse_decision_response(response, FOLLOW_UP_ACTIONS, get_min_confidence(config))


def record_decision(job_id: str, decision: DecisionResult) -> None:
    """Persist an executed decision into history (agent memory trail)."""
    if not job_id:
        return
    db = get_db()
    try:
        from jobagent.db import add_history

        add_history(
            db,
            job_id,
            "agent_decision",
            f"{decision.action} | 置信度{decision.confidence:.2f} | {decision.reason}",
        )
    finally:
        db.close()
