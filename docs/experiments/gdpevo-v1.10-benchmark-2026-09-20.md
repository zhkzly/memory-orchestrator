# GDPevo v1.10 development benchmark

日期：2026-09-20

## 结果

固定 Memory Orchestrator v1.10、GDPevo task_group_007、`gpt-5.6-terra`、prompt、评分器与门槛后，本轮 readiness 与 development 共 **7/7** 次模型请求正常返回，合计 **81,656 Token**，无 unknown usage。

系统从归档 train001 失败 Episode 中提取 1 条 `instance` pitfall。Diagnosis 返回 `necessity=needs_evidence`，没有生成 Candidate，因此结果为：

- Candidate：0
- 新 Actor base-candidate 对照：0
- Release：0
- Active generation：0
- 重复评价与 frozen test：未启动

旧 Episode 的 train001 分数为 5/17，只是学习输入，不是本轮新跑的 base 分数。本轮没有测得任务性能差值。

## 轨迹覆盖发现

原轨迹包含 138 个事件。系统扫描了全部元数据，但当前有界选择只投影 11 个事件、让 Teacher 实际分析 7 个事件；126 个事件未进入投影视图。4 次 summary 调用生成 3 个合法摘要，第四个计划片段因阶段调用预算未执行。

对相同 Episode 做确定性覆盖审计，完整事件需要 36 个片段；inventory 查询从第 22 段开始，shipping quote 从第 32 段开始，submit 位于第 36 段。当前四段选择主要包含模板、备忘录、最终 artifact 和最早订单查询，没有把失败反馈对应的 inventory/decision 证据提到前面，也没有将未选片段暴露为可补读目录。

因此本轮首先暴露的是长轨迹上下文选择问题。Teacher 的 instance 降级与弃权是合理行为；仅增加少量 Token 或修改 prompt 不能解决证据不可见。

## 证据边界

- 这是 development 小批实验，不是官方 GDPevo 总榜。
- test001 的 prompt、payload、notes、output 和 evaluator 未打开、未执行；设置阶段查看过 group manifest 与文件名。
- 没有 Candidate，所以没有正向效果数字，也不将未执行请求记为 0 分。
- 货币价格未由 provider 返回，成本保持 unknown。

完整 ledger、Teacher 输入、Store、机器摘要和报告位于 Trellis 任务 `09-20-gdpevo-v110-benchmark`。

核对结果：实验一致性断言通过，相关 GDPevo/轨迹学习测试 21/21 通过，产品代码相对冻结 commit 无差异。
