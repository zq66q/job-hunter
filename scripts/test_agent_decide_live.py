# -*- coding: utf-8 -*-
"""
agent_decisions 决策层 · 自己动手实测脚本
===========================================

跑法（在 D:/job-agent 目录打开终端）:
    .venv/Scripts/python.exe scripts/test_agent_decide_live.py

这个脚本会用你 config.yaml 里的真实 LLM（DeepSeek），
对下面几段"假 HR 对话"逐一做决策，验证:
  1. 决策链路通不通（配置 -> prompt -> LLM -> JSON解析 -> 白名单/置信度校验）
  2. LLM 对典型场景判断准不准

想自己加场景: 往下翻到 SCENARIOS，照格式加一行即可。
本脚本只临时开启决策开关，不会改动你的 config.yaml。

四条路怎么选:
  路1 单元测试（不花钱不联网）:  .venv/Scripts/python.exe -m pytest tests/test_agent_decider.py -v
  路2 本脚本（真实LLM，每次约几厘钱）: 就是你现在跑的
  路3 真实 monitor（需要 HR 真回消息）: config.yaml 开开关 + jobagent monitor
"""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

from jobagent.config import load_config
from jobagent.executor.decider import decide_conversation_action, agent_decisions_enabled

# ---------- 1. 加载配置（脚本临时强制开启决策，不改你的 config.yaml）----------
cfg = load_config(Path(r"D:\job-agent\config.yaml"))
cfg.setdefault("monitor", {}).setdefault("agent_decisions", {})["enabled"] = True
print(f"[配置] 决策开关(临时) = {agent_decisions_enabled(cfg)}  -> 已强制开启，config.yaml 未改动")

# ---------- 2. 假岗位信息（决策 prompt 会用到，字段越全判断越准）----------
JOB = {
    "id": "self-test-001",
    "title": "Python 后端开发工程师",
    "company": "某互联网科技公司（测试数据）",
    "salary": "25-40K·14薪",
    "status": "applied",
}

# ---------- 3. 测试场景：想自己玩，就照这个格式加/改一行 ----------
# (场景名, HR消息文本, 期望动作, 备注)
# 期望动作只能是4选1: auto_reply(正常沟通要回) / needs_resume(要简历)
#                    mark_rejected(明确拒绝) / skip(无需处理)
SCENARIOS = [
    ("A. HR 索要简历", "您好，看您简历不错，方便发一份简历过来看看吗？", "needs_resume", ""),
    ("B. HR 婉拒", "不好意思啊，这个岗位我们已经招到合适的人了，祝您早日找到更合适的工作。", "mark_rejected", ""),
    ("C. HR 约面试/沟通", "你好，看到你的项目经历挺匹配的，请问现在还在找机会吗？明天下午方便电话聊一下吗？", "auto_reply", ""),
    ("D. 系统通知", "[系统通知] 您关注的职位有新的动态，点击查看详情。", "skip", ""),
    ("E. 模糊开场(在吗)", "在吗？", "auto_reply", "歧义场景：LLM 也可能选 skip，理由合理即可"),
    ("F. 条件不符的拒绝", "看了您的简历，我们这个岗位要求统招本科以上，您的情况不太符合，抱歉。", "mark_rejected", ""),
]

# ---------- 4. 开跑 ----------
print()
passed = 0
for name, hr_text, expected, note in SCENARIOS:
    sender = "system" if hr_text.startswith("[") else "hr"
    messages = [{"sender": sender, "text": hr_text}]
    print("-" * 66)
    print(f"{name}    期望: {expected}")
    print(f"消息: {hr_text}")
    result = decide_conversation_action(JOB, messages, cfg)
    if result is None:
        print(">>> 无结果（LLM 调用失败/解析失败/低于置信度门槛 -> 调用方正常回退旧规则）")
        continue
    if result.action == expected:
        passed += 1
        tag = "PASS"
    else:
        tag = "DIFF"
    print(f">>> action={result.action}  confidence={result.confidence:.2f}  [{tag}]")
    print(f"    理由: {result.reason}")
    if result.action != expected and note:
        print(f"    注: {note}（DIFF 不一定是错，理由说得通即可）")

print()
print("-" * 66)
print(f"汇总: {passed}/{len(SCENARIOS)} 个场景与期望完全一致")
print("判断标准: 全 PASS 最好；有 DIFF 就看理由和置信度，理由合理、置信度>=0.6 就算正常。")
