# 外部验收反馈：SkillFlow、Evo-Harness 与 GRASP

日期：2026-09-18。此稿由主线程根据阅读分支已回报取证、既有论文阅读及本轮再次读取的冻结源码收束；原阅读分支被自动策略拦截后中断，没有成功交付独立最终稿。

## 证据覆盖与执行边界

- SkillFlow：冻结提交 `7b49ff5a7e26cd7706e959bfa0dba4746d18440d`，核对 runner、trajectory compactor、结果抽取和更新提示词。
- Evo-Harness：冻结提交 `3c7c7b8c62a3f07da1d4407aa03f0ca079954bcf`，核对 CL 分支的 rubric 反馈加工、原上下文反思与批次整理。结论不扩展为五套 benchmark 实现完全相同。
- GRASP：本稿只采用已读论文的反馈/探针协议；中断分支所报具体 benchmark POST/GET 实现细节没有在主线程完成全部独立复核，不作为本稿确定结论。
- SkillFlow 的逐任务 verifier 位于另外发布的数据集中。本轮该下载被自动策略拒绝，随后阅读分支终止；系统仅提示可能违反策略，未给出更具体原因。没有重试被拒下载，不能声称已核验逐任务验收细节。
- 本轮没有执行模型或基准，也没有修改产品。

## 1. 同一张接口对照表

| 系统 | 结果/反馈来源 | 真正送给更新器的材料 | 不能作出的推断 |
| --- | --- | --- | --- |
| SkillFlow | Harbor trial 的 verifier reward、result.json、verifier/ctrf.json；具体判定依任务而定 | 任务名、来源、reward、失败测试、异常、精简轨迹、当前 Skill 文件快照 | 不是只有布尔值；也不是完整原始轨迹毫无损失地传给模型 |
| Evo-Harness CL | bench.evaluate 得到逐 rubric 满足情况；再选择反馈粒度 | 原 Solver 会话用于失败后反思；Level 2 把未满足 rubric 改写成自然语言；批次 Curator 另读候选与现有库 | 改写反馈不产生新的独立事实；评分可含模型评审，不能笼统称全部确定性验收 |
| GRASP | benchmark 的分数、失败记录与任务/环境相关诊断；候选通过成对 probe 比较选择 | 用失败与可用诊断提案，再让当前库与候选在平衡的开发 probe 上执行 | 不是所有场景都公开 gold 给修改器；probe 选择也不是最终未见测试成绩 |

来源：[SkillFlow runner](https://github.com/ZhangZi-a/SkillFlow/blob/7b49ff5a7e26cd7706e959bfa0dba4746d18440d/iterative_shared_skills_runner.py#L630)、[Evo-Harness CL](https://github.com/A-EVO-Lab/a-evolve/blob/3c7c7b8c62a3f07da1d4407aa03f0ca079954bcf/evo_harness/cl_bench.py#L1101)、[GRASP §2](https://arxiv.org/html/2605.29668v1#S2)。

## 2. SkillFlow 的关键数据损失

`TrajectoryCompactor.compact()` 读取 ATIF steps。它只对 source=agent 的步骤保存消息、工具参数和 observation。即使保留了 source=user 的第一步，该函数也没有复制原任务正文；任务名不能自动替代完整任务要求。

字符串参数只保留前100字符，复杂 dict/list 参数变为摘要，观测也有字符上限。因此一份“有轨迹”的输入，仍可能丢失关键参数或早期约束。新项目应保留原文引用和缺失信息，不能照搬截断后宣称无损。

`extract_trial_outcome()` 从结果和 CTRF 提取测试/异常；runner 又以其取得的 TrialResult reward 覆盖 outcome 中的 reward 与 verifier_passed。必须核对实际控制流，不能只按函数注释理解标签来源。

来源：[compactor 与 outcome](https://github.com/ZhangZi-a/SkillFlow/blob/7b49ff5a7e26cd7706e959bfa0dba4746d18440d/libs/skill_evolution/patcher.py#L106)、[覆盖位置](https://github.com/ZhangZi-a/SkillFlow/blob/7b49ff5a7e26cd7706e959bfa0dba4746d18440d/iterative_shared_skills_runner.py#L685)。

## 3. Evo-Harness CL：反馈加工与反馈判定是两次不同的工作

`build_feedback_detail()` 的实质路径：读取 task.metadata.rubrics 和 feedback.raw.requirement_status，找出未通过项，交给另一次模型调用，改写为自然用户口吻。该改写调用并没有重新运行任务，也没有凭自己取得额外环境事实。

实际 return 与注释需区分：Level 1 返回 FAIL；默认 Level 2 返回 FAIL 加改写文本；Level 3 才增加满足比例与逐项状态。失败后的 Skill 提案使用 Solver 原会话上下文；所以反馈字段简短，不表示反思器没有执行过程。

没有 benchmark rubric 的日常任务，不能原样复制这条链后假定仍能得到同等信息。可替代来源是已有测试、明确 review，或公开标明为估计的模型评审。

来源：[反馈构造](https://github.com/A-EVO-Lab/a-evolve/blob/3c7c7b8c62a3f07da1d4407aa03f0ca079954bcf/evo_harness/cl_bench.py#L1101)、[原上下文提案](https://github.com/A-EVO-Lab/a-evolve/blob/3c7c7b8c62a3f07da1d4407aa03f0ca079954bcf/evo_harness/cl_bench.py#L1187)。

## 4. 对实现的直接启示

先定义所能观察和检查的事实，再决定评分与诊断。执行器的 accepted、退出码和最终回复只证明各自接口约定，不能脱离环境实现将其解释为真实业务状态已改变。论文中的模拟/日志验收与真实工具执行需要分开。

更新器输入应同时有原任务、过程证据、结果/反馈来源和当前资产；反馈即使只是一个二值信号，也不能代替其余上下文。最后保留独立效果评价，避免把反馈生成器的自信当作新能力已被证实。
