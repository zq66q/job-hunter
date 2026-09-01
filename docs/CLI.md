# job-agent CLI 命令

## 常用命令

| 命令 | 用途 |
|---|---|
| `jobagent web` | 打开本地配置面板和工作台 |
| `jobagent connect` | 检查 Browser Runtime 与 Chrome 连接 |
| `jobagent ai-status` | 安全检查 AI 服务连接，不显示完整 Key |
| `jobagent run` | 运行完整流程 |
| `jobagent status` | 查看简要统计 |
| `jobagent status --full` | 查看完整状态仪表盘 |

## 分步执行

```bash
jobagent scrape -k "Python开发"   # 采集岗位
jobagent score                    # AI 评分
jobagent confirm                  # 人工确认投递清单
jobagent greet                    # 为已确认岗位生成招呼语
jobagent send                     # 发送已生成的招呼语
```

`jobagent scrape` 还支持 `--limit` / `-l` 限制本次最多采集的岗位数。`jobagent score --rescore-filtered` 可以重新评分此前被 AI 判为低分的岗位。

## 回复监听

```bash
jobagent monitor                 # 按配置间隔持续检查
jobagent monitor --once          # 只检查一次
jobagent monitor --interval 20   # 指定检查间隔，单位为分钟
```

监听能力仅用于允许自动发送和监听的平台。外部只读平台不会进入自动监听流程。

## 定制简历

```bash
jobagent resume --job-id JOB_ID
```

该命令为指定岗位生成定制简历 PDF。简历请求仍应由用户检查后手动处理。

## Web 面板参数

```bash
jobagent web --port 8686
jobagent web --no-open
```

如需查看当前版本的完整参数，以本地帮助为准：

```bash
jobagent --help
jobagent COMMAND --help
```
