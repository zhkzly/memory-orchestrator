# 架构恢复检查点

- 审查基线：[2026-09-18 审查报告](research/implementation-coverage-audit-20260918/README.md) 保留 3 个 P1、6 个 P2 的原反例及终态政策澄清，不覆盖历史证据。
- 最新修复：[根因与责任边界](../archive/2026-09/09-18-memory-core-boundary-repair/design.md)、[恢复点](../archive/2026-09/09-18-memory-core-boundary-repair/resume.md)、[验收记录](../archive/2026-09/09-18-memory-core-boundary-repair/research/verification.md)。F02–F10 及同因采样中断点已修，F01评分政策已澄清；最终163项、构造闭环、官方故障注入与独立复核通过。只完成本轮修复，父任务的剩余设计义务继续保留。
- contract_version：1.6.0；保留既定 N01–N11、K01–K14、Q01–Q28。HTML 每项 coverage 分开列机制、剩余义务、外部职责和效果证据，取消笼统 11/11 与全体暂停标注。
- 文档对齐和清理已完成；本次完成的子任务：.trellis/tasks/archive/2026-09/09-18-python-experience-memory。
- 原子任务记录 M1–M3 的交付与既有测试；后续修复应以上述审查清单核对缺口，不能仅依赖原归档清单的完成勾选。
- 总纲 current_delivery 已允许实现；CLI/MCP/具体客户端/目录同步继续暂缓；旧 TS 和用户数据保留。
- 所有节点完成情况依赖实际证据，结构检查与构造用例不能代替学习效果。
- 仍保留的后续能力：多标准聚合、自动执行 check_plan、流式/依赖链索引、关系适用范围与 measured_effect 实验、seed 初始实验臂、完整维护成本和纵向报告。此轮没有用删除这些要求来取得“完成”。
