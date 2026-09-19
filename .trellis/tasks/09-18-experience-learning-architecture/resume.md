# 架构恢复检查点

- 当前总纲v1.7.0，K01–K14/Q01–Q28/N01–N11保留；既定Python记忆演化机制已完整接通。稳定入口：docs/blueprint/implementation-evidence.md、examples/memory_evolution/README.md。
- 最新完整实现任务：09-18-complete-memory-evolution，完成后存archive/2026-09；完整义务、独立审查、故障注入和真实SDK记录见其research/verification.md。
- 最终268项检查通过；官方68/68故障变体被检测且恢复原hash。实际CSV/脚本/组合/恢复/发布的构造执行与真实模型调用分开记录。
- 真实SDK一轮4调用产生候选；两项必需检查缺可信材料，unknown且0发布。正式benchmark、未见任务/语义准确率/净维护收益未测。
- Python函数接口独立，具体执行环境/评分依据由提供方负责。CLI/MCP/原生客户端/目录同步按原决定暂缓，旧TS和用户数据保留。
- 历史163项边界修复位于archive/2026-09/09-18-memory-core-boundary-repair；M1–M3是早期主线，不再作为当前完整覆盖的唯一依据。
- 后续开发先读当前总纲与证据，不恢复旧“待接通多标准/轨迹/检查/关系/seed/报告”的过期清单，也不自动开始benchmark或原生接入。

- 2026-09-19真实小批量发现并修复上下文节点缺陷；当前v1.7.1。2任务/9执行/51SDK、0发布，收益未证。剩余问题及解决方向见docs/experiments/gdpevo-context-pilot.md，不把框架已实现说成模型学习质量已成熟。
