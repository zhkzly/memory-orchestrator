# Memory Orchestrator 简历项目表述 v2

> v2 在 v1 基础上新增 2026-09-20 真实 Teacher 重放。v1 保留，不覆盖。新实验提供安全性行为数据，但仍没有正向任务分数提升。

## 推荐项目名称

**Memory Orchestrator：面向 LLM Agent 的证据驱动经验记忆与 Skill 演化框架**

项目链接：<https://github.com/zhkzly/memory-orchestrator/tree/codex/vault-controller-maintenance>

## 平台／Agent 应用岗三条

- 构建 Python Agent 经验记忆核心，将百级事件轨迹按任务、action/result 和外部反馈分层，通过局部摘要、按需补读与累计 Token 预算提取可追溯经验，并支持 Experience/Skill 检索复用。
- 实现不可变候选快照、外部可执行评分、base-candidate 对照、Selection、原子发布/回退；在 GDPevo 2 个任务、4 次对照中拦截目标 0 增益且回归 **12/17→10/17** 的候选。
- 针对通用 checklist 跨任务误注入，增加 artifact-feedback 绑定、可复用经验证据门和机器化 Skill 适用边界；完成 **383 项回归、22 次故障注入**，真实 Teacher 重放中将不完整证据限制为 instance 经验并保持 0 Candidate/0 发布。

## 算法／研究岗三条

- 将记忆演化形式化为 `Episode → Evidence → Experience → Skill Candidate → Validation → Release`，区分工作记忆、情景经验、程序性 Skill 与模型参数，支持单轨迹发现和版本化演化。
- 设计 evidence-grounded 准入：task-family 经验必须闭合任务、完整 action/result、同版本被评输出和 Feedback；缺证时补读、降为 instance 或弃权，避免仅凭失败分数生成泛化规则。
- 构建冻结任务/评分器/预算的真实实验链：历史候选在 train001 **5/17→5/17**、train004 **12/17→10/17** 后被拒；v1.10 两次真实 Teacher study 共 **11 次请求、71,076 个已知 Token**，成功产生 1 条 instance 经验，但 provider 中断前未生成候选，因而不声明性能提升。

## 一页简历最推荐版本

- 构建 Agent 长轨迹→结构化经验→Skill 候选→冻结对照→版本发布/回退的记忆演化框架，支持证据引用、依赖/冲突、成本记录和失败恢复。
- 设计 artifact-feedback 绑定与任务族经验证据门，缺少完整 action/result 时自动补读、降级或弃权；结合机器适用边界避免 Skill 跨任务误注入。
- 在 GDPevo 2 任务/4 对照中拦截 0 增益且回归 **12/17→10/17** 的候选；完成 **383 项回归与22次故障注入**，真实 Teacher 重放验证缺证经验被限制为 instance 级。

## 面试时如何解释“效果”

项目目前证明的是两类效果：

1. **发布安全效果**：候选没有目标收益且损害回归任务时，系统保持旧版本；
2. **经验粒度效果**：v1.10 真实 Teacher 在缺少执行闭环时不再生成 task-family Skill，而是保存 instance 经验。

尚未证明第三类效果——后续任务正向提分。面试时应主动说明，并把下一实验设计讲清楚：稳定 provider 后完成 Candidate，再对 target/regression 多次重复，冻结后测未参与更新的同族任务，并统计完整 Teacher+Actor+Evaluator 成本。

## 新实验数字边界

- 两次 study 共 11 次请求，其中 8 次有 usage、3 次失败调用 usage 未知；已知 Token 为 71,076，不能当作完整总 Token。
- 首轮产生 1 条 instance Experience；第二轮在 extract 前后受 provider 错误影响。
- Candidate、Actor 对照、Release 均为 0，因此没有新的任务分数，不能把“0 发布”描述为性能提升。
