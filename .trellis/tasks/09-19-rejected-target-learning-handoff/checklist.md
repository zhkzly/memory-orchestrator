# 原始要求检查

1. 被拒candidate的target执行是否生成可学习Episode并出现在`next_episode_ids`？
2. Episode是否精确保留公开task、candidate snapshot、原始事件、artifact与评价结果？
3. validation/selection/evaluation原记录是否保持不可变且可回查？
4. base、regression、transfer、accepted/selected、blocked/unknown是否不能转换？
5. 普通外部Episode是否仍不能伪装evaluation return绕过selection-only防护？
6. 相同拒绝结果重复处理是否幂等、不新增重复Episode/Feedback？
7. 下一次`learn()`能否直接消费返回ID，且不包含regression/final来源？
8. active snapshot/generation是否不变，当前轮仍为not_selected且release=null？
9. 是否没有自动模型重试、无限循环或未声明新任务执行？
10. 总纲/schema/包/文档和所有消费者是否同步，真实收益与机制检查是否分开？

## 最终核查

1. YES：真实rejected target candidate生成1个Episode，evolve返回其稳定ID。
2. YES：公开task、candidate snapshot、132原事件+宿主instruction/result、artifact、score/outcome和target_gain均精确投影。
3. YES：原EvaluationReturn/Result/Validation/Selection未修改；新记录只引用其ID和实际内容。
4. YES：同一真实plan中的base/regression排除；selected、unknown、blocked及regression-only拒绝分别验证为空。
5. YES：旧provided_material/execution_function改名路径仍被lineage拒绝；新source必须与framework重建Episode逐字相同。
6. YES：同一比较重复交接ID相同，Episode/Feedback数量不增加，也不新增执行返回。
7. YES：现有learn用scripted abstain消费新ID一次；requested_episode_ids精确匹配，regression未进入。
8. YES：active snapshot/generation不变，当前轮not_selected、release=null。
9. YES：engine中learner调用计数仍1；没有model factory、自动循环或新任务执行。
10. YES：v1.9.0源/包/HTML/context同步；401项全套、compile、自检和mutation通过。机制证据不表述为第二轮收益。
