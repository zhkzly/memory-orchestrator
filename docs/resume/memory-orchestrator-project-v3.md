# Memory Orchestrator 简历项目表述 v3

> v3 新增 2026-09-20 完整 development benchmark。它补齐了 provider 稳定运行数据和轨迹覆盖诊断，但仍没有正向任务提分；v1/v2 保留。

## 推荐项目名称

**Memory Orchestrator：面向 LLM Agent 的证据驱动经验记忆与 Skill 演化框架**

项目链接：<https://github.com/zhkzly/memory-orchestrator/tree/codex/vault-controller-maintenance>

## 一页简历推荐版本

- 构建 Agent 长轨迹→结构化经验→Skill 候选→冻结对照→版本发布/回退的 Python 记忆演化框架，支持原文证据引用、局部摘要、按需补读、外部评分与全阶段成本记录。
- 设计 artifact-feedback 绑定、task/action-result/output/feedback 闭环及机器化 Skill 适用边界；缺少可复用证据时降为 instance 或弃权，避免失败分数直接演化成跨任务规则。
- 在 GDPevo 2 任务/4 次历史对照中拦截目标 **5/17→5/17** 且回归 **12/17→10/17** 的候选；完成 **383 项回归、22 次故障注入**，并用 138 事件真实轨迹 benchmark 定位长轨迹选择瓶颈。

## 平台／Agent 应用岗可展开

- v1.10 development benchmark 的 readiness 与 Teacher 链路 **7/7 请求返回**，共 **81,656 Token**；系统生成 1 条 instance 经验后以 `needs_evidence` 弃权，保持 **0 Candidate/0 发布**。
- 对轨迹处理做覆盖审计：138 个事件全部扫描，但当前配置仅让 Teacher 分析 7 个；inventory 证据位于完整分段的第 22 段，说明瓶颈位于上下文选择而非单纯窗口长度。

## 面试时如何解释效果

项目已有的任务级证据是“发布安全”：有害候选损害 train004 后未进入 active library。v1.10 的新证据是“经验粒度安全”和“可观测性”：证据不足时不生成 Skill，并能从完整 ledger 定位哪个上下文阶段阻止了学习。

项目尚未证明后续任务正向提分。当前 benchmark 没有 Candidate，因此 train001/train004 新对照和 test001 都未运行。下一步要先修复反馈相关轨迹片段的选择，再用相同冻结协议重新测量。

## 不要写

- “在 GDPevo 上提升 X%”；本轮没有新任务分数。
- “已验证未见任务泛化”；frozen test 未启动。
- “生成 Skill 并提升效果”；本轮 Experience 为 instance，Candidate 为 0。
