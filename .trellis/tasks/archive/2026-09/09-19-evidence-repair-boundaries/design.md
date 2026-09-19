# 确定性呈现与模型语义的最小修复

## 职责与首因

见 research/responsibilities.md。LLM负责选择有价值观察、提炼经验、归因和编写候选；框架负责提供材料、引用/预算/版本约束。原校验器及单次预算拒绝均正确，不删除检查，也不修改模型生成的业务内容使其通过。

## 反馈文本

保留既有整份 Feedback 序列化证据（旧base/text/hash/range不变）；另提供固定字段 `reason` 的原始字符串视图。新视图使用独立身份种子 `reason-text-v1`，`raw_ref=feedback:<check_id>#/reason`；text严格等于原Feedback.reason，不解析其JSON内容、不归一化业务值。range/hash只针对该原始字符串。namespace仍feedback，event_id仍check_id，既有feedback_view按反馈身份聚合；不添加无消费者的接口字段。

该附加视图不是新事件或另一条反馈，不能重复计反馈分母，也不能改变旧完整包的覆盖语义。原记录继续可引用/回读；新增字段正文计入同样packet/role/token限制。模型必须使用所提供reason片段的独立ref，旧ref配新文本仍拒绝。没有reason正文时仍保留原整份反馈；非adaptation反馈两个视图均不提供。

不建设通用JSON投影层，不迁移旧记录，不让宿主自动修正quote。必要的固定字段来源说明同步到summary提示词和总纲；其语义任务、输出schema、有限修复流程不变。

## 容量配置

StructuredModel完整render/预检/计量机制保持。GDPevo参考配置summary单次输入由8000调为12000，以实际8649-token修复请求及完整字段视图为容量证据；累计32000输入/4000输出、4次调用和全局限额保持。用已归档输入与拒绝稿做回归：现上限必须在第二次dispatch前拒绝，新上限允许模型修复；低额配置仍拒绝，不能把额度当无限承诺。

## 修改文件边界

- `src/memory_orchestrator/evidence.py`：固定reason字段索引、选择和覆盖归属；只有在直接消费者需要时才改同函数反馈聚合。
- `tests/test_memory_feedback_text.py`：来源、引用、回读、历史视图、预算与可见性回归；由现有真实GDPevo fixture派生。
- `examples/gdpevo_pilot/run.py`：仅summary单次input参考限额；Actor/评分/协议/SDK传输默认不改。
- `tests/test_memory_summary_repair.py`、`tests/fixtures/gdpevo_summary_repair_train001.json`及fixtures说明：真实拒绝与修复容量回归，不当模型效果证据。
- `docs/blueprint/project-contract.json`及其生成HTML/context/packaged contracts：v1.8.1、固定字段来源披露、summary提示词revision3、对应预算；不修改归因/提案/准入。
- 源码职责与运行证据文档、backend spec、本任务记录。

`learning.py/model.py/engine.py/evaluation.py/release.py`不预设修改。若发现新根因超出上述边界，先记录并重审，不直接继续逐例打补丁。

经首差实测补充：允许只修改 `tests/test_memory_trajectory.py` 的disk/inline语义等价测试容量前提。两种表示的真实source_record开销不同，不能要求在恰好触发预算裁剪时仍选出相同正文。该方法两侧使用同一明确非绑定容量，其余有限扫描、禁止整文读取和紧预算验收不变；不调整任何生产选择策略。

### 集成首差后的必要修订

上述“不改选择”决定在固定42k业务供证回归失败后翻案。相同反馈的full和reason是两种表示，被当作两个独立最高优先级来源重复占据正文额度；新增2704字符直接挤走orders返回及目录。保留该原始测试和预算。

只在evidence中将同一反馈的两个视图合并为一个选择单元，共享原反馈正文上限。默认full取reason之前的精确元数据前缀，reason使用剩余正文额度；元数据过长时退为outcome的精确短原文，优先保留reason。头长度按真实字段位置计算，禁止硬编码fixture的650字符，禁止解析reason业务内容。简单内部额度规则不增加公共配置或通用投影层。full原索引和所有旧范围不改，补读目录继续可用；显式allowed_refs仍严格限制提供范围。正文与额外来源元数据全部真实计费，不能因“同源”免去开销。

实施者补同源共享、超长metadata和单视图显式选择回归，再跑原固定预算GDPevo供证验收。这个框架选材修复不改变LLM摘要/经验语义，也不修改后续归因/Skill/发布。

## 实盘验证

测试后冻结新版，复制上次prelearning-store和learning-input到本任务新study，使用既有revised入口。复用相同train001经历，最多新增4次开发对照、36次物理调用、300万输入字符、单次120秒、transport retries0；Teacher仍原总预算。仅一次回放，不在失败后隐式追加运行。无候选/未选中/未发布均有效保留。test001不执行，不读取私有答案用于诊断。
