# 执行步骤

1. 固定计划、预算、数据和代码；检查本地SDK凭据存在（不打印值）、数据checkout与源包一致。
2. 使用既有baseline入口执行一轮，持续记录真实状态；保留失败与unknown，不覆盖stage、不自动另起补跑。
3. 独立只读核查轨迹摘要、原文引用、Skill与比较产物，区分输入不足、模型输出、执行器能力、反馈和准入边界。
4. 汇总实际任务/调用/分数/用量与未执行项，写docs/experiments稳定报告；提交、归档记录。

## 执行结果

- 已执行一次新的 baseline，程序正常结束，evolution=abstained。实际仅 train001 一次：5/17，5 Actor 调用、68 工具调用、138 事件。
- 首次局部整理正常返回 JSON，四个评分引文因嵌套 JSON 转义形式不匹配被拒；修复完整输入估算 8649 > 单次 8000，因此没有第二次 SDK 请求。其余三段未分析，未进入提取/诊断/提案/对照/发布。
- 全 study 6 次 SDK 调用，输入 31699、输出 4752、合计 36451 token；未知调用用量 0，价格未知。累计 SDK 耗时 125.2676 秒。
- 28 个实现文件和总纲 hash 与冻结计划一致，104 份 JSON 可解析，6 个调用都有返回。独立审查见 research/independent-audit.md，逐次统计见 research/summary.json。
- 稳定报告 docs/experiments/gdpevo-post-rewrite-pilot.md 明确下一步建议，不在本次冻结实验内改变提示词/代码/门槛或补跑。
