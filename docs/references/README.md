# RSI 与 Context Engineering 参考文献

归档日期：2026-09-17。用户提供的两篇收藏正文保存在 OpenViking；此处只保留阅读入口。它们是参考资料，不是本项目的运行时记忆或已完成能力声明。

- [RSI 自进化分类综述：完整收藏正文](viking://resources/ai-engineering/references/rsi-context-engineering-20260917/rsi-taxonomy.user-provided.md)
- [Context Engineering：完整收藏正文](viking://resources/ai-engineering/references/rsi-context-engineering-20260917/context-engineering.user-provided.md)
- [来源、阅读批注、源码对照与候选实验](viking://resources/ai-engineering/references/rsi-context-engineering-20260917/README.md)
- [Foundry 与 Agent 自进化：六篇论文对照](foundry-rsi-paper-review-20260917.md)
- [六篇公开论文阅读索引（OpenViking）](viking://resources/ai-engineering/references/rsi-context-engineering-20260917/six-paper-reading-index-20260917.md)
- [现成 Coding Agent 的 Skill 演化：源码复现方案](skill-evolution-replication-20260917.md)
- [复现方案的固定提交与源码索引](skill-evolution-sources-20260917.json)
- [后续立项审查：动机、Gap 与三位 Agent 的质疑](../research/2026-09-17-agent-improvement/decision.md)（替代“以复现作为项目目标”的建议）
- [最新工程项目提案：仓库级经验维护](../research/2026-09-17-agent-improvement/project-proposal.md)（按用户明确的真实问题与实验标准）
- [从原生 Agent 轨迹到经验：数据与最小实现](../research/2026-09-17-agent-improvement/trajectory-learning-walkthrough.md)
- [SkillSmith 独立论文全文精读](skillsmith-paper-independent-20260918.md)
- [SkillSmith 源码深读与确定性样例核查](skillsmith-code-deep-review-20260918.md)
- [轨迹与反馈：跨论文综合及实现边界](feedback-cross-paper-synthesis-20260918.md)
- [轨迹与反馈：公开文献比较（OpenViking）](viking://resources/ai-engineering/references/rsi-context-engineering-20260917/trajectory-feedback-comparison-20260918.md)
- [ReasoningBank / Reflexion：自评与真实测试反馈](feedback-selfjudge-comparison-20260918.md)
- [SkillEvo / SkillTriage：人工参考、执行差分与归因](feedback-attribution-comparison-20260918.md)
- [SkillFlow / Evo-Harness / GRASP：外部验收反馈](feedback-external-comparison-20260918.md)（中断阅读分支的已完成取证由主线程收束，保留未核验范围）
- [GEPA：轨迹和丰富反馈的接口责任](feedback-optimizer-comparison-20260918.md)

两篇正文保留本次对话实际提供的文字、来源链接、收藏日期和 SHA-256，并已回读核对。部分图片、公式和完整微信公众号链接未包含在用户提供的文本中。原文实验数字未逐项核验；检索索引由 OpenViking 异步生成。

## 一手资料入口

- [ReasoningBank: Scaling Agent Self-Evolving with Reasoning Memory](https://arxiv.org/abs/2509.25140)
- [Darwin Gödel Machine: Open-Ended Evolution of Self-Improving Agents](https://arxiv.org/abs/2505.22954)
- [Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- [Awesome RSI 文献导航](https://github.com/Prism-Shadow/awesome-rsi)

## 当前项目定位

本项目已包含分层记忆、上下文构造、会话记录与记忆库维护。controller 的结构评分与提案安全检查不能替代 Agent 下游任务效果评测。

若继续探索记忆驱动的自进化，待补证据是：任务反馈如何产生可复用的更新，更新如何进入后续模型输入，以及在独立任务上是否改善成功率、成本或稳定性。具体候选实验见 OpenViking 阅读说明；尚未实施。
