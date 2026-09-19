# 设计边界

## 最小行为差距和归属

差距位于N04/N06证据构造与StructuredModel调用边界，不在Actor工具、评分器、CLI或发布器。复用不可变原始日志、EvidencePacket、真实字节引用、goal关联和learn调用记录。

## 数据流

原始索引 → 确定性分类/投影及调用组 → 预算内局部证据包 → 局部事实/尝试/结果/未知摘要 → 原经验提取 → 既有诊断、Skill候选与独立验证。

角色是默认选择线索，不是固定真值权重。任务/纠正与反馈、工具调用和关键结果共同构成分析单元；普通回执/重复大正文可只留摘要/引用；模型可见分析只是意图或假设。原文片段与派生摘要必须不同类型，摘要的引用只能指向该次实际提供的原文。

## 预算

完整rendered messages计入预估；明确计数器/估算口径。新增局部整理与经验提取共享子预算，调用循环原总预算同时生效。每次调用预留输出，返回后根据可信transport usage结算；失败/缺失usage不得免费重试。预算不足保留部分覆盖或abstain，不能按角色排序截断后声称完整。

## 文件归属

- evidence.py（或经证据支持的相邻实现）：分类/调用组/有界原文投影，不改原日志。
- model.py：完整请求预算预检、输出预留及累计记账；所有调用统一经过现有边界。
- learning.py：局部整理与提取的实际编排、来源验证、持久化报告。
- project-contract.json及生成包：局部摘要Draft、prompt、N04/N06/N11语义与预算说明；HTML仅生成。
- tests与examples：真实fixture派生行为检查、实际配置消费；不启动新benchmark。

## 兼容与审查

已有短轨迹直接路径保留，不复制旧学习/发布实现。新的显式策略在示例中接通，缺少策略的旧调用保持可读并在文档写明。公共契约先更新版本再生成；配置、提示词、校验器必须同一含义。不能借机修改反馈粒度或放宽发布门。

接口与具体测试在只读勘察后追加；当前文件不授权扩大到未来通用插件层。

## 已确定的接口补充

- evidence.build_trajectory_plan(index, *, limits) 给出按绑定与调用组划分的局部EvidencePacket以及实际覆盖/省略统计；不能用focus排序冒充限定来源。
- StructuredModel保留generate签名，新增完整渲染共用的preview与显式token_counter；limits.token_budget含全局和按prompt_id的限额，预估与transport实测分开。按stage的累计限额相加约束局部整理+提取，无需新通用预算调度框架。
- summarize_trace_v1 / LocalSummaryDraft：局部observations分task/action/intention/observation/outcome，每项短叙述附非空原文quote与ref。宿主验证quote在该包已提供片段内，派生精确短原文范围；上层只引用这些实际正文，不接受摘要ID作为原始证据。
- EvidencePacket.trajectory_summaries是可选派生旁注；原fragments及其UTF-8字节校验不放松。短原文、摘要来源和未决项一起供后续extract/diagnose使用；仍不能证明语义真实或因果。
- 新路径受显式trajectory_processing策略控制并在示例中启用；旧调用/短输入不强制多次模型调用。未选/预算未处理部分显式记录。

规划审查：根代理已核对实际model.generate、learn.call、_save_experience、validate_packet/validate_citations消费者。摘要不得直接覆写原文，这一约束决定上述短引文方案；现有发布与适用范围策略不变。

## 用户收敛后的重写边界

以上可选包装方案被用户“直接重写这部分”取代：learn统一调用新的学习输入构造器，先生成角色分层、调用/目标分组的轨迹计划，完整且足够短的处理后表示直接提取；其余在阶段预算内局部整理并合并短引文。禁止保留“先旧全局抽样，再判断是否启用新路径”的入口。配置可覆盖参数，但不能切回旧学习算法。非学习消费者（目标关联/代理反馈等）仍可使用原文EvidencePacket工具。

独立review F01/F02作为重写验收：所有被舍弃正文要有明确覆盖/省略解释和有界回读目录；某段失败后保留之前的合法局部结果、真实usage/report和全部未处理段状态，不再把已完成工作丢掉或仍标planned。摘要引用的动作/返回对要由宿主补足可见短原文或明确缺口。
