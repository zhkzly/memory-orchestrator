# 诊断候选拒绝后未补读的因果边界

## Goal

只读追踪extract补读决策与candidate验证拒绝的时序，区分LLM选择、框架循环和防止验证集泄漏的边界，提出最小可证伪修正。

## Requirements

- 复原局部摘要、extract补读、经验/候选、validation拒绝的真实时序。
- 检查当时可见目录、剩余补读预算、ExtractionDraft状态约束和learning分支。
- 检查比较轨迹是否进入Episode/Run并能否成为下一轮learn输入。
- 给出LLM选择、framework证据交接、单轮生命周期三者各自责任，不把推断写成观测事实。

## Acceptance Criteria

- [x] 能解释为什么本次LLM合法返回completed+missing_evidence+read_requests=[]。
- [x] 能说明它当时实际可以补读什么、不能补读什么。
- [x] 能说明候选拒绝为何不会触发同一轮补读或第二轮learn。
- [x] 明确当前是单次evolution链已完成，还是多轮自进化闭环已完成。
- [x] 提出最小、可证伪且不污染验证集的下一步，不直接实施。

## Notes

- 只读诊断任务，PRD-only；结论保存在research并向用户说明。
