# 恢复检查点

- contract：v1.10.0，SHA-256 `d39a35d4b9d111d35f341353b6401efc9a436f291fb48e67dea5b797d39f2ce8`；节点 N06、N09、N10、N11。
- 产品 commit：`1ad555f583e1d14a7b58372ae43850d94b70cf67`；GDPevo commit：`56d60ae4ae5e067d1ec0ee1f850622e69f422179`。
- 允许路径：本任务目录、实验/简历报告及由本轮发现更新的验证规范；禁止修改 `src/`、`tests/`、prompt/schema/evaluator、benchmark 数据和旧归档。
- 金标输入：上一轮 `study/calls-live/call_0006.start.json`、post-rewrite pilot 的 `prelearning-store`/`learning-input.json`、GDPevo task_group_007 官方 scorer。
- 已完成：readiness 1/1 通过；development 6/6 Teacher 请求返回，63,935 Token，生成 1 条 instance Experience 后 `needs_evidence`/abstained；0 Candidate/0 对照/0 Release。
- 已完成：138 事件覆盖审计确认实际分析 7 个事件；完整顺序中 inventory 首次位于第22段，当前四段选择无法支持失败归因。
- 已完成：将实际 planner 覆盖、修复调用容量和 test 文件级冻结边界写入 `.trellis/spec/backend/validation.md`。
- 下一步：核对报告和任务证据；不在本任务修改产品。轨迹选择修复需另开实现任务，随后重跑冻结 development。
