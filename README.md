# job-agent

端到端自动化求职 Agent：浏览器自动化 + AI 能力，跑通「搜索岗位 → AI 评分 → 生成招呼语 → 人工确认 → 自动投递 → 监听 HR 回复 → 定制简历」完整求职流水线，并附带一个 Web 工作台用于配置与实时看板。

> 本项目为独立开发的开源求职自动化 Agent，已形成完整独立的品牌与代码体系。

## 功能特性

- **多平台采集**：支持 BOSS直聘 / 智联招聘 / 51job / 猎聘 四个招聘平台的岗位采集
- **AI 智能评分**：基于 LLM 对岗位与简历匹配度打分，自动排除不符合硬性条件（薪资下限、排除词、实习岗）的岗位
- **自动招呼语**：AI 根据岗位描述与你的简历生成个性化打招呼文案
- **人工确认闸门**：发送前必须人工确认，防止"偷跑"
- **回复监听**：后台监控 HR 消息，第一时间发现面试邀约
- **定制简历**：针对目标岗位生成定制化简历文件
- **Web 工作台**：浏览器看板 —— 工作台（漏斗/趋势/岗位表）、岗位池、监测执行、配置 四个页面
- **防封号保护**：请求限速、平台安全策略、Chrome 独立配置目录

## 架构总览

```
┌─────────────────────────────────────────────────────┐
│                Web 工作台 (React + Vite)             │
│        工作台 / 岗位池 / 监测执行 / 配置               │
└──────────────────────┬──────────────────────────────┘
                       │ HTTP (bottle, :8686)
┌──────────────────────▼──────────────────────────────┐
│                 web/server.py 后端 API               │
└──────────────────────┬──────────────────────────────┘
┌──────────────────────▼──────────────────────────────┐
│                 pipeline.py 流水线编排                │
│  scrape → score → confirm → greet → send → monitor  │
└──────┬──────────┬──────────┬──────────┬─────────────┘
       │          │          │          │
┌──────▼───┐ ┌────▼────┐ ┌───▼────┐ ┌──▼──────────┐
│collection│ │   ai    │ │executor│ │   browser   │
│ 平台采集  │ │评分/预筛 │ │发送/监听│ │ CDP 浏览器   │
└──────────┘ └─────────┘ └────────┘ └─────────────┘
```

## 环境要求

- Python 3.10+
- Node.js 18+（仅前端开发时需要）
- Chrome / Edge 浏览器（用于远程调试采集）

## 安装

```bash
# 1. 创建虚拟环境并安装
python -m venv .venv
.venv\Scripts\pip install -e .

# 2. 复制配置模板并修改
copy config.example.yaml config.yaml
#    编辑 config.yaml：填写 AI API Key、简历路径、目标城市/关键词等

# 3.（可选）安装前端依赖
cd src/jobagent/web/frontend
npm install
```

## 快速开始

```bash
# 1. 启动 Chrome 远程调试（默认 9222 端口）
.venv\Scripts\jobagent.exe connect

# 2. 跑一次完整求职流水线
.venv\Scripts\jobagent.exe run

# 3. 启动 Web 工作台（http://127.0.0.1:8686）
.venv\Scripts\jobagent.exe web
```

更详细的说明见 [docs/QUICKSTART.md](docs/QUICKSTART.md)。

## CLI 命令

| 命令 | 作用 |
|---|---|
| `jobagent run` | 跑完整流水线 |
| `jobagent scrape` | 仅采集岗位 |
| `jobagent score` | 对已采集岗位评分 |
| `jobagent confirm` | 人工确认发送清单 |
| `jobagent greet` | 生成招呼语 |
| `jobagent send` | 发送招呼/投递 |
| `jobagent monitor` | 监听 HR 回复 |
| `jobagent resume` | 定制简历 |
| `jobagent status` | 查看任务状态 |
| `jobagent connect` | 连接浏览器 |
| `jobagent web` | 启动 Web 工作台 |
| `jobagent ai-status` | 查看 AI 服务状态 |

完整命令说明见 [docs/CLI.md](docs/CLI.md)。

## 配置说明

所有配置集中在 `config.yaml`：

- `profile`：简历路径、期望薪资、排除关键词
- `search`：搜索关键词、目标城市
- `platforms`：各招聘平台开关
- `ai`：模型服务商、API Key、模型名称
- `browser`：Chrome 远程调试端口、独立配置目录

完整字段说明见 [docs/CONFIGURATION.md](docs/CONFIGURATION.md)。

## 运行测试

```bash
.venv\Scripts\pytest
```

## 项目结构

```
job-agent/
├── src/jobagent/
│   ├── main.py            # CLI 入口
│   ├── pipeline.py        # 流水线编排
│   ├── config.py          # 配置读取
│   ├── db.py              # SQLite 存储
│   ├── ai/                # 评分 / 预筛 / 招呼语 / 简历
│   ├── browser/           # CDP 浏览器控制
│   ├── collection/        # 平台采集器
│   ├── executor/          # 发送 / 监听
│   ├── scraper/           # 页面解析
│   ├── tracker/           # 状态跟踪
│   ├── dedup/             # 岗位去重
│   ├── ui/                # 命令行确认界面
│   └── web/               # 后端 API + React 前端
├── tests/                 # pytest 测试
├── docs/                  # 文档
└── scripts/windows/       # Windows 启动脚本
```

## 免责声明

本项目仅供个人学习与研究使用。自动投递行为可能违反招聘平台的服务条款，请谨慎使用、控制频率，使用者需自行承担相应风险。

## License

[MIT](LICENSE)
