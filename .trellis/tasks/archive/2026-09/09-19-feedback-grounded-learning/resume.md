# 恢复检查点

- contract: v1.10.0；节点 N02/N04/N06/N07/N08；问题 Q10/Q12/Q14/Q16/Q19/Q28。
- 允许路径：`src/memory_orchestrator/{evaluation,sampling,evidence,learning,context,candidates}.py`、packaged schema/prompt、相关 tests/fixtures、`docs/blueprint/*`、本任务与 DECISIONS/journal。
- 范围外：重写轨迹分层、增加 LLM 节点、GDPevo 专用评分、原生 Agent/CLI/MCP 接入、重新跑付费 benchmark。
- 已完成：反馈回流、artifact-feedback绑定、可复用证据门、Skill selector、总纲/源包/HTML、spec、定向mutation和383项完整回归。
- 金标：归档 `feedback/a9da7968...json`、`reports/ffb60696...json`、真实候选 fixture。
- 下一步：最终静态复核、回填 checklist/任务证据、提交；本机8317恢复后可另开一次真实Teacher回放，不属于本轮完成前提。
