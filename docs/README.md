# 项目文档入口

日常只从这里进入，避免在旧方案之间来回切换。

当前总纲为 v1.7.0：既定Python记忆演化机制已逐义务接通；每个节点与问题分别列出实际消费者、行为证据及效果边界。具体 CLI/MCP/客户端适配暂缓。实际运行记录见当前检查点，不能从历史暂停状态或旧的全部完成标注推断当前进度。

| 用途 | 入口 |
| --- | --- |
| 使用 Python 核心 | [调用方式与本地闭环示例](../examples/memory_evolution/README.md) |
| 核对完整交付 | [16项实现与证据](blueprint/implementation-evidence.md) |
| 人读宏观设计 | [项目总纲 HTML](blueprint/index.html) |
| 核对之前的关键思考 | [28 项问题与实现决定](blueprint/index.html#questions) |
| 看并行、reward、提取和发布 | [执行与评价](blueprint/index.html#runtime) |
| 改目标架构 | [唯一结构化来源](blueprint/project-contract.json) |
| Agent 恢复任务 | [总纲摘要](blueprint/context.md) → [当前检查点](../.trellis/tasks/09-18-experience-learning-architecture/resume.md) |
| 看具体交付顺序 | [实施清单](../.trellis/tasks/09-18-experience-learning-architecture/implement.md) |
| 查当前已有代码 | [当前代码规范](../.trellis/spec/backend/index.md) |

## 按需资料

- [论文与源码参考](references/README.md)：背景证据，不自动覆盖当前总纲。
- [轨迹与动态目标研究材料](research/2026-09-17-agent-improvement/)：保留当前仍引用的数据说明和研究依据。
- [总纲收敛前快照](history/2026-09-18-pre-blueprint/README.md)：原设计字节与哈希。
- [总纲 v1.0 来源快照](history/2026-09-18-blueprint-v1/project-contract.json)：节点细化前的结构化设计。
- [本轮对齐前快照](history/2026-09-18-before-evolution-alignment/manifest.json)：保留修订前的总纲和相互冲突的任务材料，可追溯此次调整。

旧流程图、过期立项/复现执行提案和未采用的 Python 测试草稿已清理；原文可从 Git 检查点 `db20db8` 回查。旧 TS 产品仍保留。当前 Python 实施不包含迁移、重建旧 CLI/MCP。

生成页面和摘要：`node docs/blueprint/build.mjs render`；检查同步：`node docs/blueprint/build.mjs verify`。
