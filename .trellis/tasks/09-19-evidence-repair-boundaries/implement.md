# 实施顺序

1. 完成只读责任/根因审查，冻结task/checklist/design；激活任务。
2. 从真实产物补回归并记录红灯；对将修改的源文件先用现有相关不变量验收领取mutation执照，再实现。
3. 独立实现反馈原文视图及参考容量校准；不得同时改归因/提案/选择/发布或失败停止策略。
4. 更新结构化总纲与生成视图，补足源码职责说明，运行新验收、相关回归和官方mutation，保留错误引用/预算拒绝路径。
5. 独立边界审查，完整Python检查与blueprint verify。冻结后在新study执行一次相同学习经历回放；实盘结论单列。
6. 记录根因、修复、真实到达阶段、用量与未知项；本地commit，归档当前task和会话；不推送未授权原始材料。

验收命令使用 `PYTHONPATH=src:tests .venv/bin/python -m unittest ...`；全套使用 `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p 'test_memory_*.py'`。不得将假transport的回归token当真实用量。

## 完成记录

- 初次新增reason双正文导致固定42k磁盘包orders返回被挤压；根据首差将两视图改为同源共享选材单位。保留业务断言和原预算，未改LLM语义或评分。
- 最终用 `-p 'test_*.py'` 连同GDPevo适配一起运行，391/391通过（85.055秒）。独立源码复审通过；总纲/包/生成视图一致。
- f2fda0c冻结后执行一次revised回放：同一旧学习经历、4次新对照、27次SDK调用，3摘要/1经验/1候选。选择keep_current，0发布。完整用量和门判定见research/replay-summary.json，语义边界见replay-teacher-audit.md。
- 本轮不继续调参或补跑；学习内容具体性与模型补读选择另作后续问题，不能用未经执行的建议冒充已修复。
