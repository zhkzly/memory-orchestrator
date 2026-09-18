# Trellis 与架构文档验证记录

日期：2026-09-18。范围仅为工具安装、项目配置与设计文档；未执行产品学习实验。

## 版本与恢复

- 安装来源：官方 `@mindfoldhq/trellis`，仓库 https://github.com/mindfold-ai/Trellis。
- 原版本 0.6.15；官方 registry 的 latest 元数据为 0.6.17。
- 官方 `trellis upgrade --tag 0.6.17` 完成，退出 0；`trellis --version` 实际返回 0.6.17。
- `trellis update --dry-run` 在 IPv4 优先的 Node 执行环境下返回 CLI/project/npm 均为 0.6.17，退出 0。
- 旧 CLI 备份：`/tmp/trellis-before-0.6.15-20260918.tar.gz`。
- 初始 79 文件的哈希记录：`/tmp/memory-orchestrator-before-trellis-20260918.json`。

## 项目检查

| 检查 | 结果与边界 |
| --- | --- |
| `trellis platforms` | Codex、Claude Code 两个平台已配置 |
| `get_context.py --mode packages` | 单仓库，backend 规范层；不适用的前端模板已删除 |
| `task.py validate 09-18-experience-learning-architecture` | implement/check 各 4 个有效上下文条目 |
| 模板升级 dry-run | 138 个受管文件未变；config.yaml 的关闭自动提交设置识别为本地修改；tasks/spec/workspace 保留 |
| 语法读取 | 34 个 Python 文件通过 AST 解析；4 个 JSON、4 个 TOML 成功解析 |
| Markdown 引用 | 6 个规范文件和 3 个规划文档共 9 文件，无失效本地 Markdown 链接或模板占位标记 |
| 原文件保护 | 升级/初始化前记录的 79 文件 SHA-256 全部一致 |
| `git diff --check` | 退出 0；产品源码及依赖声明未改 |

## Hook 检查的准确范围

本机 CLI：codex-cli 0.154.0，Claude Code 2.1.276。Codex features list 返回 hooks 为 stable/true，未修改用户全局配置。

手动向两份 UserPromptSubmit 脚本提供 cwd/prompt：
- Codex 脚本返回当前 `experience-learning-architecture (planning)`。
- Claude 脚本在没有对应 Claude 会话任务指针时返回 `no_task`，未借用 Codex 的活动任务。
- 两份脚本退出均为 0，返回合法 hook JSON。

最初探针错误地要求 hook 输出包含带日期的任务目录名；实际字段为 task.json 的 id。随后又错误要求 Claude 复用 Codex 指针；查明路径识别平台、按会话隔离的契约后改正检查。没有修改上游 hook 代码来迁就探针。

上述结果只验证脚本及当前会话归属，不证明新 Codex/Claude 原生会话已实际触发 hook。Trellis 初始化提示的原生 hook 批准步骤未在本轮交互执行；不声称已绕过或完成该批准。

## 状态

- 初始化规范任务已归档，使用 --no-commit，不创建提交。
- 架构任务保持 planning：PRD、design、implement 及两份 JSONL 上下文清单齐备。
- `session_auto_commit: false`，由项目配置明确禁用 journal/archive 自动提交。
- 本轮没有安装项目 npm 依赖；build/harness、模型调用、benchmark、实际跨 Agent 学习收益均未运行。
