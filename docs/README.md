# 项目文档入口

日常只从这里进入，避免在旧方案之间来回切换。

当前 v1.4 完成演化契约对齐：完整学习/比较/发布流程保留，具体 CLI/MCP/客户端适配暂缓。**产品实现仍暂停**；文档完成不意味着可以按旧任务状态继续写代码。

| 用途 | 入口 |
| --- | --- |
| 人读宏观设计 | [项目总纲 HTML](blueprint/index.html) |
| 核对之前的关键思考 | [28 项问题与实现决定](blueprint/index.html#questions) |
| 看并行、reward、提取和发布 | [执行与评价](blueprint/index.html#runtime) |
| 改目标架构 | [唯一结构化来源](blueprint/project-contract.json) |
| Agent 恢复任务 | [总纲摘要](blueprint/context.md) → [当前检查点](../.trellis/tasks/09-18-experience-learning-architecture/resume.md) |
| 看具体交付顺序 | [实施清单](../.trellis/tasks/09-18-experience-learning-architecture/implement.md) |
| 查当前已有代码 | [当前代码规范](../.trellis/spec/backend/index.md) |

## 按需资料

- [论文与源码参考](references/README.md)：背景证据，不自动覆盖当前总纲。
- [历史研究与方案](research/2026-09-17-agent-improvement/)：保留探索过程，不能从早期建议重新推断当前目标。
- [总纲收敛前快照](history/2026-09-18-pre-blueprint/README.md)：原设计字节与哈希。
- [总纲 v1.0 来源快照](history/2026-09-18-blueprint-v1/project-contract.json)：节点细化前的结构化设计。
- [本轮对齐前快照](history/2026-09-18-before-evolution-alignment/manifest.json)：保留修订前的总纲和相互冲突的任务材料，可追溯此次调整。
- [旧流程图](diagrams/agent-learning-workflow.html)：历史概览；当前节点和边以总纲为准。

生成页面和摘要：`node docs/blueprint/build.mjs render`；检查同步：`node docs/blueprint/build.mjs verify`。
