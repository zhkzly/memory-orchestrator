# 项目总纲与文档收敛契约
目标：把已确认的关键节点收敛成一个形式化来源、离线 HTML 视图及可恢复任务入口。
不变量：K01–K14 保留或显式记录修订；不回退为先验证项目必要性。
不变量：原研究材料保留；历史设计可回查，不再默认作为执行指令。
不变量：HTML 与面向 Agent 的摘要由同一来源生成，不能独立维护多套口径。
范围外：不实现产品学习运行时，不运行模型或 benchmark，不提交或推送。
依据：用户确认节点及整体流程，并要求宏观约束、形式化、HTML 和持久保存。

## 追加

- 总纲采用 docs/blueprint/project-contract.json；人读 HTML，Agent 读生成摘要及按节点提取的契约。
- 旧 design、requirements-ledger 与 system-boundaries 已按原字节保存到 docs/history/2026-09-18-pre-blueprint/，附 SHA-256。
- 文档一致性检查只验证字段、引用、权威来源和状态声明；实现正确性仍需对应行为检查。
