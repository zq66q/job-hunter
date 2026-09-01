# Job Agent 项目框架说明

本项目为独立开发的开源求职自动化工具，目录与文件结构经过统一设计，并已全面确立 job-agent 品牌。

## 命名规范

- Python 包名：统一为 `jobagent`
- 其余目录名、文件名、前端组件、测试名均与 job-agent 品牌保持一致。

## 已跳过的内容

- `.git/`、`.idea/`、`chrome-profile/`、`edge-profile/`（IDE 与浏览器运行时数据）
- `assets/`（演示用图片/视频/动图）
- `node_modules/`、`__pycache__/`、`dist/`（依赖与构建产物）
- `.github/`（GitHub 协作元数据）
- `package-lock.json`（依赖锁定文件）
- `data/*.db`、`data/.star_hint_*`（运行时数据）
- `data/resumes/*.md`（个人简历原文，不复制，仅保留占位）

## 占位文件

所有源文件统一写一行占位注释（中/英文取决于源文件扩展名），
后续按模块规划后将逐文件替换为真实实现。
