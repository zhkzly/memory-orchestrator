# 角色分层轨迹入口重写：交付证据

状态：实现与验收完成；原始需求、追加决策与检查项见本任务task/checklist/design。用户要求直接重写轨迹→学习输入，已删除旧全局build_packet之后再可选包装的入口。没有重写Skill版本/候选/准入/发布，没有改评分器、旧TS或具体客户端接入。

最终完整回归366/366通过（84.252秒，full-suite-verified.txt）。随后按用户明确要求放宽参考预算，42项预算/实际输入/probe检查通过（2.012秒），算法未修改。最终收尾官方变体66项均检测并精确恢复：evidence原18+dependency8、model18、root17+真实完整反馈容量1、demo4；初始执照与历史复验不另计入这66个最终义务。容量变体命令与结果见profile-capacity-license.json。

## 实际数据流

learn → build_trajectory_plan（类型、绑定、调用组、段优先级）→ 短视图直接提取或有预算的局部整理 → 精确短引文＋派生旁注 → extract → 原有诊断/候选/验证。局部整理和提取都走同一StructuredModel；删除了extract请求内重复的readable_ref_catalog投影。

原始136事件fixture用于输入路径、预算和引用检查；测试的Teacher响应是明确的脚本替身，未发真实SDK请求。派生的中文前缀、self-report、资源写入/检查等边界用例不是原始pilot发生过的事实，不用作学习收益。

## 当前证据

- 模型边界：25项新预算检查＋15项旧检查通过；初始官方执照及18项收尾变体检出且精确恢复。见model-budget-verification.md。
- 角色投影/调用与目标分组：用户前缀、晚期失败优先、普通结果折叠、原始UTF-8范围、磁盘等价等检查通过；18项收尾变体检出。见evidence-implementation.md与evidence-mutation-results.json。
- 上层实际消费：局部摘要先于提取、引文身份/字节范围、assistant自述、局部失败保留、短路径目录、预算不足提前停止、参考配置启用、报告不混入预留等14项通过；16项收尾变体检出。后追加的依赖消费回归最初RED，必须接通后才关闭。
- 示例/旧测试迁移：同源纯preview与旧补读测试40项通过；demo4项收尾变体检出。磁盘轨迹旧消费者另迁移并加强真实JSONL/range/hash检查，TraceTests 10项通过。
- 完整回归初跑：356项、81.550秒，仅上述旧磁盘消费者的流程假设错误；原始失败保留full-suite.txt，最终结果另存，不覆盖。
- 文档：v1.8.0、7 prompts、43 schemas、22说明性例；check/verify/self-test通过（37个派生负例、6个生成视图检查）。最终状态仍等完整回归后同步，不用结构检查冒充模型效果。

## 独立审查及处理

- learning-review.md：F01计划外可读来源丢失、F02局部失败丢掉已完成结果、F03弃权分类、F04直提目录丢失、None配置未拒绝，均已有修复和实际输入回归。
- evidence-review.md：E01用户前缀被引用日志的ERROR挤走已修复；E02额外元数据读取未消除，选择扫描限额与真实read_stats分开披露。
- budget-integration-review.md：完整render、前检后重检、修复/补读、unknown预留与provider实测分离有六个区分探针。低全局预算可在摘要后不足以提取：没有越额调用，仍会安全弃权；初始preview不预留后续额度，该效率边界未宣称修复。
- 最后旧能力复核：新计划器一度未消费dependency_lookup，真实开关实验同样缺少写入者。修复限定为复用原邻域回找并共享新增事件余额，不新建图层；实际模型输入必须包含可达的来源才能验收。

## 收尾变更与完整检查记录

- 依赖消费已关闭：原真实fixture的合法资源变体从不开启→开启，先前写入者实际进入summary和extract正文/可读目录；新增深度、共享余额、免费复用、跨scope及放不下的缺口检查通过。
- full-suite-final.txt是第二轮失败记录：重复目录输入已从prompt删掉，但预算测试唯一输入夹具尚保留旧字段，因严格prompt_input_mismatch触发关联失败；只迁移夹具，未放松输入校验或恢复重复投影，模型40项和18个变体复验后再跑全套。
- 原6k提取草案上限低于真实反馈完整请求的6435估计值。先校准形状，随后按用户“上限可以高一点”放宽为局部8k/1k、提取16k/3k，两阶段累计64k/10k，全Teacher12次/160k输入/24k输出。参考配置可调，既有SDK实验记录不改。
- python compileall、git diff --check、总纲check/render/verify/self-test与source/schema/example一致性均完成；本项目没有独立Python lint/type命令，不虚构对应检查。HTML未宣称浏览器视觉验收。

checklist十项已逐项核对：用户前缀/目标边界见trajectory tests；调用与分析身份见trajectory+learning tests；低信息处理和真实分层消费见实际payload测试；预算见model tests；部分覆盖/补读见learning/report；原学习准入/发布边界由全套回归覆盖；独立review与mutation见同目录原始记录；源/包/生成视图由同源检查覆盖。

## 不外推的结论

本轮没有真实模型调用或新的benchmark分数，不覆盖原51次SDK实验。默认计数器是完整消息UTF-8 JSON字节/3估计，不是tokenizer实测或输入数学上界；已报超额阻止后续调用。预算仅单model实例，非跨进程或账号总额。摘要语义、真实归因与净收益仍未测；来源/格式检查不能证明这些。
