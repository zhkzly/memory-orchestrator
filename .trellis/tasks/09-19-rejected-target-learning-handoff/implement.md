# 实施顺序

1. 从归档实盘机械复制最小评价闭包fixture；补正路径及边界变体，先观察新验收红灯。
2. 对evaluation.py、lineage.py、engine.py分别用现有绿测领取修改前mutation执照。
3. 实现确定性Episode/Feedback投影与授权解析，再接engine的next_episode_ids；逐单元跑红→绿。
4. 更新总纲/schema/生成视图和Python规范；prompt、评价门、sampling保持字节不变。
5. 对正路径、每项隔离边、幂等、直接learn消费分别做官方postmutation；跑相关和完整Python回归、compile、总纲自检。
6. 使用真实归档Store的副本做无模型物理交接；若确定性闭环通过，再决定是否单独授权新一轮真实Teacher实验。本任务不隐式发起。
7. 独立审查、提交、归档；不公开push。

## 完成记录

- 真实fixture红灯、三目标修改前许可后实施；没有先写产品再补验收。
- 新source/投影/engine交接已完成，下一轮仍为显式调用；旧selection-only防护保持。
- 初次失败的EvaluationResult过滤和非法测试形状均按五镜头先修认知，再修实现/测试，没有放宽schema。
- 10项新验收、156项相关回归、401项完整回归、compile、总纲自检和postmutation通过；真实Store副本物理交接幂等且active不变。
- 未调用模型、benchmark或test001；未实现pre-candidate补读改造，未宣称第二轮收益。
