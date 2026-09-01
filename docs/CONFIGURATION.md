# job-agent 配置指南

推荐运行 `jobagent web`，在 `http://127.0.0.1:8686` 的本地面板完成配置。需要手动编辑时，可复制仓库根目录的 [`config.example.yaml`](../config.example.yaml) 为 `config.yaml`。

## 核心配置

| 配置段 | 关键字段 | 说明 |
|---|---|---|
| `profile` | `resume_path`, `salary_min/max`, `deal_breakers` | 简历、期望薪资与排除条件 |
| `search` | `keywords`, `cities`, `max_pages` | 默认搜索策略 |
| `platforms` | `boss`, `zhilian`, `51job` | 各平台开关与独立搜索条件 |
| `collection` | `daily_search_page_limit`, `risk_pause_*` | 采集额度与风险暂停策略 |
| `scoring` | `threshold`, `max_candidates` | 评分阈值与候选数量 |
| `throttle` | `daily_limit`, `interval_min/max`, `send_windows` | 低频发送策略 |
| `ai` | `service`, `provider`, `model`, `api_key`, `base_url` | AI 服务与接口 |
| `monitor` | `interval`, `max_resume_sends_per_cycle`, `agent_decisions` | 回复监听设置 |
| `follow_up` | `enabled`, `interval_hours`, `skip_weekends` | 跟进策略 |
| `browser` | `chrome_ports`, `proxy_port` | Chrome 与本地代理连接 |

完整字段、默认值和注释以 [`config.example.yaml`](../config.example.yaml) 为准。

## Agent 决策模式（实验性）

在 `config.yaml` 中开启 `monitor.agent_decisions.enabled: true` 后，监测循环由 **LLM 决策驱动**：

- 每个有新回复的对话，会把岗位信息、最近对话内容、交互历史交给 LLM，由它决定下一步动作（自动回复 / 走简历流程 / 标记拒绝 / 跳过）；
- 无回复的过期岗位，也由 LLM 判断是否值得跟进；
- 每次决策（动作、理由、置信度）都会写入历史记录，供后续决策参考；
- `min_confidence`（默认 0.6）以下的低置信度决策、无法解析的输出，以及所有幂等/安全检查（已回复跳过、重复消息去重、规则检测到拒绝的强制兜底）仍由代码保证。

关闭该开关（默认）时，行为与旧版规则判断完全一致。

## 平台配置边界

- BOSS 直聘：支持采集、AI 处理，以及人工确认后的低频发送和回复监听。
- 智联招聘：支持只读采集和 AI 处理，不进入自动发送、简历发送或监听。
- 前程无忧 51job：支持只读采集和 AI 处理，不进入自动发送、简历发送或监听。

外部只读平台应通过岗位池打开经域名校验的原平台链接，人工投递后再标记“已发送”。

## AI 服务

配置页可选择 Claude、DeepSeek、豆包或其他 OpenAI 兼容接口：

- Claude / Anthropic：Anthropic Messages，可通过 `ANTHROPIC_API_KEY` 提供 Key。
- DeepSeek：OpenAI Chat Completions，可通过 `DEEPSEEK_API_KEY` 提供 Key。
- 豆包 / 火山方舟：OpenAI Chat Completions，可通过 `ARK_API_KEY` 提供 Key。
- 其他 OpenAI 兼容接口：填写服务商提供的 Base URL 和模型 ID，可通过 `OPENAI_API_KEY` 提供 Key。

不要把真实 Key 写入示例、Issue、聊天或 Git 提交。job-agent 不读取 Codex、Claude Code、ChatGPT 等工具自身的 OAuth、Cookie 或登录凭证。

保存后运行：

```bash
jobagent ai-status
```

只有检测通过后再运行完整流程。

## 简历

配置项 `profile.resume_path` 必须指向本人的真实简历。支持 Markdown（`.md`）、Word（`.docx`）和带文字层的 PDF（`.pdf`）；加密、损坏、扫描版或无文字层 PDF 无法直接解析，扫描件应先进行 OCR。旧版二进制 `.doc` 暂不支持。

## 推荐的保守设置

- 保持合理的 `daily_limit` 和随机发送间隔。
- 限定 `send_windows`，避免长时间连续运行。
- 不关闭人工确认。
- 不提高默认访问频率，也不要尝试绕过验证码、登录墙或平台限制。
