# 当前代码架构

核对日期：2026-09-18。以下描述实际原型；经验学习的目标架构在 [设计任务](../../tasks/09-18-experience-learning-architecture/design.md)，不能混作已实现能力。

## 模块与消费者

| 模块 | 当前职责与调用关系 |
| --- | --- |
| `src/cli.ts` | 命令参数、CLI 流程、Agent 启动、内嵌 review UI；调用 core/config/identity/kb/controller |
| `src/core.ts` | 候选采集、分类、验证、会话摘要、上下文构造、rubric 与清理 |
| `src/store.ts` | Markdown 读写、元数据解析、引用哈希、检索计数 |
| `src/config.ts`、`src/identity.ts` | 配置/记忆根目录与项目/会话身份解析 |
| `src/types.ts`、`src/schemas.ts` | MemoryItem 静态类型及 Zod 输入形状 |
| `src/mcp.ts` | MCP 工具入口；通过 schemas 校验后调用同一 core |
| `src/kb.ts` | 外部知识库注册、关联、检索与读取 |
| `src/controller.ts` | vault 维护建议、结构检查、风险/可逆性判断及提案日志 |
| `skills/`、`examples/` | 产品工作流指导与 Codex/Claude wrapper；不是独立策略所有者 |
| `scripts/harness.mjs` | 隔离临时目录、mock Agent 和 CLI 行为检查 |

依据：[core](../../../src/core.ts)、[store](../../../src/store.ts)、[CLI](../../../src/cli.ts)、[MCP](../../../src/mcp.ts)、[controller](../../../src/controller.ts)、[README](../../../README.md)。

## 当前能力的精确边界

- `summarizeSessionTranscript` 调用 `extractSessionSections`，按 Decision/TODO/Evidence 等标记行提取；尚不能据此声称解析了原生工具轨迹。
- `verifyCandidate` 主要依据记忆种类和 evidence 条数返回状态；`verified` 在该路径不等于语义真值已被独立验证。
- `buildContextPack` 按 personal/project/session/evidence 等层提供内容，并使用条目数上限；不等于已实现模型 tokenizer 驱动的上下文预算。
- `buildContextPack` 会调用 `touchMemoryFiles` 写回计数/时间。它不是无副作用读取；检索计数不证明模型已读取、采用或受益。
- `spawnAgent` 设置 `MEMORY_ORCHESTRATOR_CONTEXT` 等环境变量并启动 CLI；这不独立证明原生模型消费了上下文。
- controller 的 `evaluateProposal` 使用风险、目标、可逆性等结构条件；它没有测量 Skill 更新后的任务成功率。
- 当前 `MemoryKind` 为 personal/project/evidence/session。新的 Episode、GoalRevision、SkillSnapshot 等尚未实现。

## 修改位置

对当前记忆策略的修改应保持 CLI 和 MCP 共用核心行为。配置解析复用 config/identity；持久化操作保持可追踪，不在 wrapper 中另写后台治理。新实验模块可以增量接入，但必须先确定新旧数据语义及消费者，不能仅把旧字段改名为新能力。
