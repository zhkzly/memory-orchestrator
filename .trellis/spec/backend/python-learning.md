# Python 经验记忆实现规范

Python 记忆核心范围由总纲 v1.10.0 和当前任务控制。M1–M3 是历史主线交付；完整机制证据见 docs/blueprint/implementation-evidence.md。机制、调用方责任与未测效果分别记录，归档或测试数量不能代替行为证据。此前 TS 规范用于理解保留的旧原型，不限制新核心语言。

- 使用 src/memory_orchestrator 普通函数与必要小类；字段对应总纲，不创建未来扩展层。
- root/path 显式传参，禁止用 chdir 或全局环境变量切换并发任务存储。
- JSON 持久化 UTF-8、稳定排序；不可变快照内容 hash；异常保留来源与错误码。
- 用户/项目 Markdown 支持旧 JSON frontmatter，读取不改元数据；scope 精确匹配。可见事实不等于学习效果认证。
- 模型输出使用 packaged JSON Schema，保持与总纲源同步；只接收已提供引用，未知/错误/预算耗尽分开。
- 核心组织采样/比较并固定请求；实际执行/评价通过明确函数提供。若后续具体提供方启动子进程，才适用 shell=False、显式 cwd/argv/stdin、超时及部分证据保留；不因此提前实现 native runner。
- 单写者发布比较版本与 generation，候选资产完整后再原子切指针；禁止未经重新检查自动 rebase。
- tests 使用 unittest 和临时真实文件/子进程。模型测试通过依赖注入，不把脚本假执行器包装成 Codex 的实际效果。
- 教学/构造 fixture 明确标记，不能当作真实学习收益；实际模型调用须声明配置/预算并记录，native 客户端接入暂缓。

- 纯schema/引用/目标语义检查在模型仍有修复预算时反馈；共享max_format_repairs与max_calls，校验回调无持久化副作用。候选应用/发布独立检查，不因模型自称修复而跳过。

- `lineage` 统一已知本地 run/产物/项目/修订事实；记录反馈不要求组闭合，进入学习和复用经验才检查实际计划/槽位/终态/回执。微批成员在执行前记录；父经历、相关检索、同内容合并不能另写更宽松规则。
- `outcomes` 统一终态解析和评分资格；默认政策在调用前显式保存。非完成执行可以留下可评价产物，但身份/格式错误不能供给已绑定评分。保留部分事件不表示任务成功。
- 证据包生成、补读和语义校验消费同一结构投影。已知调用/目标/父关系不能只停在索引；元数据也计预算，可补读目录不升格为已读正文。
- 提案是尝试，snapshot 是内容身份，validation 是准入决定。比较唯一内容但保留所有提案别名与费用；发布重新核对完整冻结映射。报告从原始结果读成绩，不依赖 ValidationRecord 是否已写。
- 存在内嵌与独立 JSON Schema 的同一记录时，两者必须等价；新增字段同时检查全体存储消费者。历史记录字段可缺，不由兼容读取虚构身份、批次或验收。

- `trace` 归档源与SQLite元数据/正文文件分开；原JSONL字节位置不等于解码文本范围。索引/片段/依赖/模型上下文各有预算；已知父来源的禁学检查不受正文回找预算豁免。
- `goals` 只用实际用户锚点产生旁注，不将Agent自说的计划改为用户目标；维护关系和必要性仍是模型判断，引用合法不证明语义正确。
- `feedback` 在执行前固定准则、权重、请求和反馈ID；缺项保留原分母。新记录按精确计划恢复，真正legacy才用唯一来源恢复；不能将有冻结指针的新记录伪装成legacy测试。
- `maintenance` 的关系只有完整提交且未撤回才参与后续检索；重复链接不能吞掉冲突/反例。ADD必须通过已有能力比较及行为差异约束，NOOP/缺证是正常结果。
- `verification` 汇集诊断与所有候选别名的义务。原质量case集合另行冻结，追加检查不得稀释目标/回归/迁移门；发布重新核对原集合和实际材料。
- `assets` 功能验证使用可信fixture并记录真实编译/执行；隔离能力不足返回unknown。`relations` 只用依赖完整视图执行有方向局部对照，相同视图不可辨识，测量结果按任务/修订/背景过滤后才供选择。
- started/return/派生记录分层。`resume_sampling`和`resume_comparison`复用原计划及稳定ID，未返回调用需有来源和证据的明确处置；本地互斥不冒充分布式exactly-once。
- transport明确费用只从外层usage传递；不得读模型生成正文，也不从token猜价格。失败/中断等待与本地维护分开，未知价格/未终结周期让完整费用保持unknown。
- `experiments` 在调用任何factory前复制全部有效配置和seed，后续只用冻结副本；各臂相同基线/预算，先测再学，final只报告。记录了配置副本但运行继续读调用方原对象仍属于冻结失效。

- 有界证据不能把全部action放到普通result之前，再用相同排序构造补读目录。按同episode/call_id保持动作/返回端点可达，覆盖不同本地阶段；catalog给出真正可补读的返回和重要续段。端点可达不代表正文已读，也不保证业务实体关联完整。
- 失败文本定位是检索提示；customer_exception等业务标识、error:null等空字段不应成为错误锚点。旧派生hint在使用前重验，不改原始日志或旧checkpoint。
- 评价范围在诊断产生义务前提供。所有check_plan项的必需/并集/null后果须向模型披露，但验收材料暂缺不等于知识证据不足：有依据的待验证候选仍可保存，发布门保持。
- 运行时剩余预算是动态上下文；只提供初始上限不足以保证模型安排最后一步。显式提供当前状态，计入输入预算；到限时保留真实不完整结果，不能由宿主补答案。
- 业务验收、研究性归因补证和内部过程遵从须区分。合法引用/足量token不能替代完整决策证据；先解决同一错误输出与相关输入/工具值/反馈的关联，再讨论经验是否有稳定收益。

- N06统一使用角色分层/调用组计划构造学习输入；短视图可直提，长视图在显式阶段token预算内局部整理。不保留旧全局抽样的可选旁路。用户控制前缀不被其引用材料中的错误锚点替换；段级择取先于段数截断。
- 局部摘要叙述是派生解释，原文quote必须来自该次提供范围。宿主计算UTF-8子范围并保留行动/返回短上下文；上层只可引用实际短原文，不能引用摘要ID或目录作为已读事实。只引用助手分析的条目保持intention身份。
- 完整render后计预算，包括schema、system及修复消息。token_counter预估、额度预留和provider实测分别保存；失败/缺用量不能退款为零。每阶段/实例总限额同时生效，preview不预留后续阶段且不能冒充跨进程预算。
- 计划选择覆盖、局部分析完成、上层实际引文分别记录；局部后续失败保留已完成结果，未处理段不得标completed。直接路径同样保留有界续读目录，不能把目录覆盖当正文完整。
- Feedback.reason可作为固定原始字段视图，使用独立reason-text-v1身份与feedback:<check_id>#/reason来源；其范围/hash针对原字段UTF-8字符串，不解析/重排内容。旧完整Feedback身份、正文与范围保持；模型引用不能跨视图，也不由宿主自动补转义。附加视图不新增反馈/事件分母，不能替代原完整来源让coverage虚假complete，实际正文和元数据照常计预算。
- 同一反馈的full/reason视图是一个选材单元，共享原反馈正文额度；默认full仅给reason前的元数据原文，元数据超过半额度时缩为outcome的精确原文，额度再小时优先reason并保留full目录。字段位置来自原文，不硬编码实例字符数。单视图allowed_refs不能拉入另一视图；额外引用元数据仍计实际包大小，不能把两份同源表示变成两份最高优先级长正文。
- 区分语义任务与机械约束：摘要/经验/归因/必要性/候选内容由模型提出；引用、容量、受限修改和准入由代码检查。真实修复容量必须用原请求、拒绝稿、诊断及当前限制一起计数；不能只确认第一次输入装得下。显式单次限额可按证据校准，累计和调用次数不随失败自动放宽。
- 比较磁盘与内存轨迹的分组语义时，明确容量足以容纳二者不同的来源元数据；相同紧字节额度不保证正文选择相同。保留独立的紧预算与按需读取验收，不能为了等价断言删除实际来源计费。
- 被拒候选不在原validation内自动重试。只有candidate+target、Validation rejected且target_gain失败、Selection keep_current、执行/评分完整时，framework可将EvaluationReturn确定性投影为source.kind=rejected_target_evaluation的Episode及adaptation Feedback。base/regression/transfer/final/unknown不投影，普通外部导入不能改名绕过。evolve只返回next_episode_ids；下一轮由调用方用新StructuredModel、预算和案例协议显式启动，active不变。

## Scenario: 可复用经验的反馈闭环与 Skill 机器边界

### 1. Scope / Trigger

- 当 `reuse_level` 为 `task_family`/`cross_family`、`necessity.verdict=proceed`，或提案包含 `ADD` Skill 时适用。
- 原角色分层、调用组、局部摘要、原文引用与累计预算保持唯一入口；不要另建轨迹压缩器。

### 2. Signatures

- `_check_reusable_extraction(extraction, packet)`：纯检查；缺闭环抛 `reusable_evidence_incomplete`。
- `_check_necessity(diagnosis, view, packet, limits)`：`proceed` 复用同一闭环，缺项进入现有模型修复预算。
- `SkillContent.scope.retrieval = {require_any: string[1..], exclude_any: string[]}`；新 ADD 和显式 scope 重写必须提供。
- `select_context(...)`：`exclude_any` 命中先排除，`require_any` 至少命中一项后才进入原排名/依赖/预算。

### 3. Contracts

- 可复用指导的 `supporting_refs` 必须覆盖 task、同一完整 call 的 action/result、可信 Feedback，以及通过相同 `evaluated-state:<artifact_digest>` resource 与该 Feedback 绑定的 result/observation。
- rejected-target 回流若原 TaskAssessment 存在，必须用原 FeedbackPlan/callback 复验并保留 criterion reason；仅真正缺少整个旧 assessment 时可退化到聚合结果并记录 gap。
- `applies_when/exclusions` 保留人类/模型说明；只有 `scope.retrieval` 是机器筛选输入。旧 Skill 缺 selector 时走 legacy 路径。

### 4. Validation & Error Matrix

- task + score，无 call pair/output link → `reusable_evidence_incomplete`，提示 cite/read/downgrade/abstain。
- `necessity.proceed` 缺闭环 → `necessity_invalid`，只能补引用、`needs_evidence` 或 abstain。
- ADD 或 scope 重写缺 `retrieval.require_any` → `scope_selector`，在同一 format/semantic repair 预算内修复。
- `exclude_any` 命中 → ContextManifest exclusion `scope_exclusion` + `matched_terms`；正向短语全未命中 → `scope_requirement`。
- 原 assessment 存在但其 plan/feedback/callback 被篡改或缺失 → 阻止回流，不能静默降级为总分。

### 5. Good / Base / Bad Cases

- Good：任务、相关 action/result、最终 artifact 和外部反馈同版本闭合，仍只作为待验证行为假设。
- Base：instance 经验可保存局部观察；旧 Skill 无 selector 继续 legacy 检索。
- Bad：只因多个评分组失败就生成“逐字段仔细检查”Skill；自然语言写了“不适用于 transfer”却仍依赖宽泛 task_family 注入。

### 6. Tests Required

- 真实 GDPevo 坏提取必须因缺 action/result 与 evaluated output 被拒；补齐文本但无 artifact-feedback link 仍拒绝。
- 真实 rejected target 必须保留原 criterion scoring points，并拒绝被篡改反馈。
- train_001 命中显式 selector；train_004 因 allocation/transfer 排除。
- inline 与磁盘 Host 终态都保留 artifact resource；完整 `test_memory_*.py` 回归通过。

### 7. Wrong vs Correct

Wrong：`task requirement + outcome=fail -> task_family checklist -> task_family lexical match`。

Correct：`task -> paired action/result -> digest-bound artifact/feedback -> reusable hypothesis -> ADD selector -> exclude/require -> existing ranking`。
