# 记忆演化核心实施契约（2026-09-18 开工后冻结）
目标：按已审查的 M1–M3 实现 Python 记忆演化核心；用户在就绪说明后明确“继续吧”。
不变量：经历/反馈→证据/经验→归因/候选→比较/选择→发布/复用完整；未知不伪造。
不变量：事实纠正与 reward 学习分开；候选、发布库与运行快照分开。
不变量：发布绑定项目、完整资产、协议、被选候选及 base/generation，失败保留旧版。
范围：src/memory_orchestrator/、tests/test_memory_*.py、examples/memory_evolution/、pyproject.toml，以及必要的总纲/任务/规范同步。
不做：旧 TS 重建或删除、原生客户端/CLI/MCP/插件/目录同步、未声明预算的 benchmark、推送。
金标来源：src/store.ts 与 scripts/harness.mjs 的真实消费者；docs/blueprint/project-contract.json 的现有 schema/examples 作为设计 fixture，不能当效果证据。
验收：checklist.md 的 10 项与 implement.md 的阶段行为检查；真实运行、构造测试、学习效果分别记录。

## 追加

- 2026-09-18：用户已允许实施，旧暂停条件由本次开工取代。阶段状态升为 v1.4.1，N01–N11 行为契约不变。
- 选择：新文件先记录缺失行为的红测试，最小实现回绿后用官方 mutation_license.py 证明验收；工具要求目标已存在且基线绿，不能虚构实现前执照。备选是拿旧不相关文件领照，拒绝这种无效证据；若工具支持新文件前置验收，再调整顺序。
