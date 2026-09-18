# CLI 与记忆核心开发规范

适用范围：`src/`、`scripts/harness.mjs`、`schema.json`、`tools.md` 及产品自带的 `skills/memory-*/`。本项目是单仓库 TypeScript CLI/MCP 原型；当前没有 React/Vue 组件层。内嵌 review UI 位于 `src/cli.ts`，不据此创建独立前端架构。

## Pre-Development Checklist

- 阅读 [当前代码架构](architecture-current.md)，区分实际行为与目标设计。
- 涉及数据形状或持久化时，阅读 [契约与存储](contracts-and-storage.md)。
- 涉及执行结果、测试或效果声明时，阅读 [验证与证据](validation.md)。
- 阅读 [系统职责边界](../guides/system-boundaries.md) 和当前任务的 PRD/design/implement。
- 用 `rg` 确认调用方；不要让 CLI、MCP、wrapper 各自实现一套记忆策略。

## Guidelines

| 文档 | 内容 |
| --- | --- |
| [architecture-current.md](architecture-current.md) | 当前模块、调用关系、能力限制 |
| [contracts-and-storage.md](contracts-and-storage.md) | TypeScript/Zod/持久化契约与兼容边界 |
| [validation.md](validation.md) | 当前检查入口与证据层级 |
| [project-contract.md](project-contract.md) | 总纲来源、生成命令、文档一致性与恢复规则 |
| [python-learning.md](python-learning.md) | 当前 Python 记忆演化核心的存储、模型与验证规范 |

## Quality Check

- 当前行为有源代码引用，目标行为有任务设计引用。
- 数据契约变更覆盖所有消费者；未执行的检查不声明通过。
- 结构评分、检索次数和模型评价不包装成真实任务收益。
- 产品实施范围以当前任务与总纲为准；旧 TS 和新的 Python 核心分别遵守对应规范。
