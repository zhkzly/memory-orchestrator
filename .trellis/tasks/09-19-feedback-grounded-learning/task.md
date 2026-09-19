# 反馈闭环与 Skill 适用性优化
目标：保留既有分层轨迹入口，使可复用经验由闭合执行证据产生，并让 Skill 适用边界在选择时生效。
不变量：原始事件、调用组、局部摘要、原文引用与累计预算语义不变。
不变量：外部评分仍由调用方提供；系统不内置 GDPevo 业务答案或评分逻辑。
不变量：证据不足允许补读、实例级记录或弃权，不能为了产出 Skill 填充泛化清单。
不做：不增加新的 LLM 节点、字段级归因算法、多候选搜索或原生 Agent 适配。
金标：真实坏提取报告 `.../reports/ffb60696...json` 仅引用任务与评分；真实候选及 train_001/train_004 在 `tests/fixtures/gdpevo_rejected_target_evaluation.json`。
金标：原始细粒度评分来自归档 store 的 `feedback/a9da7968...json`，不是手写期望答案。

## 追加

- 选择：复用 `supporting_refs` 和现有 packet relations 计算证据角色，不新增模型填写的 evidence-chain 字段。
- 备选：增加一套字段级归因 schema；当前组级 scorer 无法可靠填充，且会扩大实现。
- 翻案证据：若后续 evaluator 能稳定提供字段/实体级 diff，再单独设计更细的归因记录。
- 选择：artifact resource 同时写入 Host 终态事件，并由索引对旧内存 Episode 做 digest 校验后补充 sidecar；原始正文不改。
- 选择：构造 demo 的 packet 从 28k字/16k估算token 调至 40k字/20k，expanded 调至 50k/28k；这是新增提示词后两轮真实预检所需的最小已测档位。
- 备选：让无累计预算的 scripted teacher 走局部摘要；它没有摘要响应，且会改变该测试的目标。
- 翻案证据：若后续精简 prompt 后 28k/16k 可稳定容纳两轮完整请求，可回调示例预算。
