# 系统边界阅读指南

正式边界来自 [项目总纲](../../../docs/blueprint/project-contract.json)，本页只规定如何使用它。

## 开工与恢复

- 先读 [生成摘要](../../../docs/blueprint/context.md) 与当前任务的 resume.md。
- 明确总纲版本、当前节点 Nxx、允许修改路径、范围外事项和最后通过的检查。
- 用 `node docs/blueprint/build.mjs node Nxx` 按需读取输入输出、前后置条件、未知处理及相关 K/I。
- 当前代码事实以 [当前架构](../backend/architecture-current.md) 和源码为准，不能把目标设计当成已实现能力。

## 范围变化

- 局部澄清更新任务与检查点；改变公共契约时更新总纲版本、来源和受影响节点，再同步任务。
- 用户明确的新方向可以修改总纲；不能用旧文档拒绝新要求，也不能默默改写旧决定。
- 文献和历史方案按需读取，不默认注入为当前执行指令。
- 检查及渲染命令、错误行为见 [总纲文档契约](../backend/project-contract.md)。
