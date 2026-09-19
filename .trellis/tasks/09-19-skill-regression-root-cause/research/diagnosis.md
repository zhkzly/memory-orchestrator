# 候选Skill无增益与回归根因

## 结论

候选Skill确实被注入两个candidate执行的上下文（3877字符），不是“生成后没用上”。但它只提供了逐字段核对流程，没有库存/调拨/最终决策/order rollup的具体计算与优先级规则。Actor本来已经能读取全部业务数据，因此Skill没有增加新信息或动作能力，只增加了上下文和检查步骤。

- train001：候选改变了SO-70014的final_decision/next_action及summary，但库存、SKU、决策、动作、汇总这些评分组仍整体失败，分数保持5/17。
- train004：候选拥有全部三仓库存数据，却对多line action订单采用`mixed_actions`；base采用`has_backorder`/`needs_transfer`并匹配benchmark。两个rollup错误使SP7整组2分丢失，12/17→10/17。

直接失分已经定位；单次无seed实验不能证明Skill必然导致回归。模型随机性、额外上下文和多一次模型调用仍是替代解释。

## Skill是否真正进入Actor

candidate的ContextManifest在train001/train004都选中`skill_3847...`，supplied_text为3877字符。所有candidate SDK消息包含标题`Verify Northwind Dispatch-Control Fields Independently`和evidence worksheet步骤；base消息不含。

`consumption_events=[]`不是没有提供Skill：该字段只记录`load_skill_asset`工具读取，当前Skill正文直接注入prompt、没有资产。证据支持“模型看到了Skill”，不证明模型逐条遵守或某个输出变化由Skill唯一造成。

## train001为什么0增益

工具覆盖几乎相同：base 68次、candidate 66次。候选没有补充新的工具或业务规则。artifact只有9处差异，核心是SO-70014：

- base：backorder / create_backorder；
- candidate：manual_review / send_account_review；
- summary相应由4个backorder、2个manual_review变为3和3。

官方评分中，两臂都只通过订单集合、客户异常和运输报价；库存/缺货、inactive/low-stock、最终决策、下一步动作和summary都失败。评分组为全组布尔匹配，因此只改一个订单但仍未让全组正确，分数仍为5/17。

候选总token为44613，base为29405，增加15208（+51.7%）；候选用了6次模型调用，base为5次。它增加了成本与上下文，没有产生新的可验证业务推导。

## train004为什么少2分

最初“candidate少查库存导致缺数据”的假设被实际结果否定：

- base按22个SKU×3仓分别查询，inventory调用66次；
- candidate按SKU查询22次，每次返回NORTH/CENTRAL/WEST三个仓库记录；
- candidate虽然工具调用从106降到62，但库存覆盖相同，不是数据缺失。

最终artifact有7处差异。SP7直接相关的是：

- SO-70036包含ship+backorder：base rollup=`has_backorder`，candidate=`mixed_actions`；
- SO-70050包含ship+transfer：base rollup=`needs_transfer`，candidate=`mixed_actions`；
- blocked_orders完全相同。

官方评分显示base的SP7为true、candidate为false，权重2，因此总分12→10。

公开answer_template允许`ready_to_ship/needs_transfer/has_backorder/manual_review/mixed_actions`，但没有定义多action时的优先级；allocation memo只定义line action，也没有order rollup聚合规则。候选把“多种动作”直译为mixed_actions是可理解但不匹配benchmark答案。生成的Skill同样没有补上优先级规则，只要求“独立核对字段”。

另有line级差异：候选将若干transfer的primary_reason写成`insufficient_effective_stock`，并为NW-1042选择WH_NORTH而非base的WH_CENTRAL；但SP4 transfer set在两臂本来都失败，不是本次新增2分差距的直接来源。

候选总token36339，base33084，增加3255（+9.8%）；候选多用1次模型调用，工具调用减少41.5%。这说明候选查询更紧凑，但推导规则没有更准确。

## 因果层级

### 已观察

- Skill被提供给candidate两题；base没有。
- candidate获取了所需库存数据。
- 两个rollup字段变化与SP7由true→false精确对应。
- Skill没有提供rollup优先级或具体库存/决策公式。

### 有支持的解释

经验提取只从评分组和局部轨迹生成了通用checklist，没有形成“遇到多action订单时如何rollup”的行为差异。对已有能力很强的Actor，这类文字增加上下文，却不能稳定纠正具体计算。

### 尚不能证明

- Skill必然导致回归：每条件只运行一次，无可控seed。
- base所有字段都正确：base仍有5分对应的失败项。
- benchmark的rollup语义在公开输入中充分披露：当前观察到的memo/template未写优先级。

## 最小后续改进

下一轮不应继续扩写通用“仔细核对”Skill。应让拒绝target Episode进入已有补读/归因流程，要求经验给出可执行行为差异；若公开材料不能确定rollup规则，经验应保持unknown/abstain，而不是从gold结果倒推隐藏规则。对跨任务Skill，需至少多个相关task证据或明确任务族规则，避免单轨迹泛化。

## 简历安全表述

推荐：

> 实现Agent执行轨迹→证据摘要→经验/Skill候选→版本对照→拒绝轨迹回流的记忆演化管线，使用外部可执行评分隔离LLM自评；401项回归通过。

> 在GDPevo小批真实实验（2任务、4次对照、27次SDK调用）中识别checklist型Skill的目标0增益与回归12/17→10/17，系统保留原版本；进一步定位为经验缺少任务级聚合规则，并将被拒target轨迹投影为下一轮可学习Episode。

不能写：

- “Skill使任务成功率提升”；
- “证明Skill导致回归”；
- “实现通用自动评分器”；
- “在未见测试集验证泛化”。
