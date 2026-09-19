# 当前检查点

- 总纲：当前v1.8.1，目标v1.9.0；涉及N06/N09及EpisodeRecord来源，不改N10发布门。
- 允许路径：evaluation.py、lineage.py、engine.py；新拒绝学习测试/fixture；总纲/生成物；相关spec和本任务记录。
- 已完成：受控source kind、确定性Episode/Feedback投影、next_episode_ids和v1.9.0文档均实现；10项新验收、156项相关、401项完整回归、mutation和Store副本物理交接通过。
- 下一步：本地提交、归档。后续如需真实第二轮Teacher实验，必须单独冻结新模型预算/case协议；本任务未隐式执行。
- 金标提交：510e84d，产品起点b6dcad3；工作区开工前干净。
- 排除：pre-candidate补读改造、自动多轮调度、regression/final转训练、真实模型调用。
