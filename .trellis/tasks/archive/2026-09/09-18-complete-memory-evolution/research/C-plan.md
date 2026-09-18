# C：检查计划、组合对照和脚本验证的完整消费者链

状态：有界调查与接口建议；产品未改。依据 PRD O06/O07/O08、总纲 v1.6 的 K07/K09/K10/K12、Q16/Q18–21、N07–N10。

## 1. 当前断点及修正位置

| 义务 | 当前事实 | 必须闭合的交接 |
| --- | --- | --- |
| O06 | learning 保存 DiagnosisDraft.check_plan；candidates 保存 PatchDraft.check_plan；engine 仍直接把外部 case_set 交给 compare，后者不读这些计划 | 诊断/提案义务 → 可信材料绑定 → 冻结验证安排 → 实际结果覆盖 → 发布复核 |
| O07 | co_used 已产生；measured_effect 只有存储/选择消费分支，没有受控实验生产者 | 有范围/版本的相关组合 → 保留依赖的实际干预 → 每题重复结果 → measured_effect → root 的版本/场景过滤与选择 |
| O08 | assets 目前只有路径、所有者、完整性、内容 hash 检查 | 候选真实文件 → 编译记录 → 独立功能检查 → 准入/发布；缺材料不是通过 |

现有普通 case_set/execute/evaluate、快照、计划/原始结果/Validation/Selection 分离和提案别名继续使用。下面的新增记录只服务于这些已经存在的消费者，不引入插件注册器或策略语言。

## 2. O06：让 check_plan 决定执行安排

### 可信材料与模型输出分工

自然语言的 `behavior/required_evidence` 不能被程序安全地等同于任意一个同 split 的 case。因此不能用“有一条 target 测试”自动宣称覆盖所有 target 检查。

建议为调用方材料增加一个普通 JSON `verification` 输入：

```text
verification = {
  id, version,
  checks: [{check_ref, purpose, description, evidence_kind,
            case_ids, asset_test_ids}],
  asset_tests: [可信脚本输入/预期输出/环境要求],
  relation_case_ids: [用于局部组合检查的既有 case ID]
}
```

- `checks/asset_tests` 由调用方或固定数据集提供；LLM 不能写入预期答案、测试程序、评分器或判定阈值。
- 新版 diagnose/propose 收到公开 `verification_catalog`，只能引用已存在的 `check_ref`，或明确 `check_ref=null` 表示所需检查材料不存在。目录包含验收意图和材料类型，不包含 private criteria、gold 或隐藏测试正文。
- 保留现有 `purpose/behavior/required_evidence`，增加 `check_ref: string|null`。宿主给每项分配 `requirement_id=digest(source_record + item)`，模型不生成主键。
- `check_ref` 的可用性/项目/用途/证据类型由代码校验；自然语言映射正确性仍是模型假设和调用方材料的语义责任，报告列出实际运行了哪份检查，不宣称自动证明唯一根因。
- 若现有 case_set 没有额外目录，宿主可将每条 case 投影为 `case:<id>` 的公开材料项，描述来自公开任务及可选 `check_description`，评分依据仍留在原 case.criteria/evaluator。新模型提示词实际使用这些引用。
- 对旧存档自由文本 check_plan，不按关键词猜测已覆盖。只有明确的调用方绑定（requirement_id→check_ref）或旧项已有可信引用才继续；其余返回 needs_evidence。这是安全的输入兼容，不是静默跳过旧计划。

### 执行和准入

1. `evolve` 在 `learn` 前投影材料目录，传给 N07/N08；B 保留诊断→提案关联，C 读取两者的 check_plan。
2. `prepare_verification` 归集每个候选快照**所有 proposal aliases 的检查义务并集**，不能从同内容提案里只挑最容易通过的计划。
3. 保留协议原有 target/regression/transfer 保护集。check_plan 指定的 case 或脚本检查加入执行安排；可选材料中未被要求的项不冒充已经检查。
4. 冻结 `VerificationPlan`：义务、可信材料内容 hash、case/test 绑定、执行/评价身份、预算、候选/base/项目/代次。重复引用同一实际请求可共享结果，但费用按唯一调用记录计。
5. 普通任务检查复用现有 comparison 执行/评分边界。区分性检查可以使用调用方提供的区分性 case；不能把一段 LLM 解释当作已经执行该检查。
6. 每项义务形成 pass/fail/unknown/missing-material 状态及实际结果引用。缺引用、材料不完整、调用未执行、结果错对象均阻止 accepted；已完成的其他结果照常保存和报告。
7. N10 重新读取计划、覆盖记录及其实际结果。普通总体均分提升不能覆盖遗漏的必需检查。

“增加检查”真正改变 requests；“缺检查”真正阻发布。不是仅在 candidate 上增加一个未被使用的 check_plan 字段。

## 3. O07：实际局部组合对照与 measured_effect

### 选择与依赖

- 优先取 changed Skill 与有效 co_used 邻居、诊断指定目标和直接依赖相关的局部组合；排序、选取上限、重复数、案例集合和预算均在执行前固定。
- 诊断明确要求的组合不能被预算截断静默删除；不足则记录缺证。自动探索的局部邻域可按明确策略限额，报告实际范围，不声称穷举整个库。
- 不生成悬空的 ablation 库，不修改真实发布快照。由完整候选派生只读 `ExecutionView`，其所提供 Skill 和资产始终包含完整依赖闭包。
- 采用**有方向的条件增量**，不把它命名为普遍协同因果：对于 `A | B`，在同一背景/案例上比较 `closure(background ∪ {B})` 与 `closure(background ∪ {A,B})`。
- 若 B 依赖 A，两个合法视图相同，不能报告测得增量 0：记录 not_identifiable。若有效视图存在声明冲突，记录结构不兼容，不执行违法组合。反方向可独立判断是否可测。
- 必要依赖因此不会被当作“移除后还能运行”的独立因子。测量结论针对实际提供的整个闭包；不把相关依赖资产的效应归成某条规则的唯一作用。

### 必需的执行能力

原 execute 接收完整快照，不能仅修改一个标签就声称模型没看到某个 Skill。建议增加一个当前有实际消费者的 `execute_view(request, view, public_case)` 能力：

```text
ExecutionView = {
  view_id/hash, project_id, source_snapshot_digest,
  selected_skill_refs: [{skill_id, revision}],
  skills, assets, dependency_closure, background_skill_refs
}
```

`view` 只包含本实验臂实际提供的内容；不把删减后的对象挂在原 snapshot_id 下冒充完整快照。普通 execute 接口保持原样。提供方负责真实环境和视图执行；系统创建视图、安排所有请求并核对返回身份。没有可控视图执行能力时，必需组合检查为 unknown，不能回退到完整快照执行后声称已消融。

完整默认 evolve 在形成适用局部对后自动调用 `measure_relations`；初始空库/没有可测相关组合会有明确 not_applicable，而不是省略整个消费者。演示和新集成提供真实本地 `execute_view`，验证选择差异确实改变任务执行。

### 记录、统计与消费

- 每个方向、case、arm、repeat 先写固定请求，再实际执行/evaluate；全部结果、终态、未知和费用保留。
- `value = mean_case(mean_repeat(score_with) - mean_repeat(score_without))`。有未知/缺结果不产生数值关系奖励；保存测量的 unknown/not_identifiable 记录。
- 完成测量才写 `kind=measured_effect`；与 co_used 分开。强度是有限条件下的观测增量，不是校准概率或普遍因果结论。
- 候选未发布时，该关系只能支持相同版本的分析；root 的默认召回依据 Skill/依赖修订、背景集合和 task_family/task_id 过滤后才应用，不因库里存在记录就生效。
- 根代理拥有 context 的实际过滤/选择与 report 展示；C 提供下面的准确形状和跨模块验收用例。

## 4. O08：脚本编译与独立功能检查

1. `prepare_verification` 从确切候选快照枚举 `scripts/` 下的脚本及其所有者、引用/模板等依赖资产。不得只测试原 patch 中的一小段而发布另一个完整包。
2. materialize 到独立临时工作目录，核对文件内容 hash/路径/所有者。测试期间不修改持久快照。
3. 提供真实 Python 编译默认实现（目标代码编译但不执行顶层），保存编译器身份、源码/资产 hash、退出状态和诊断。其他语言必须有明确编译能力；未知支持不能返回 pass。
4. 由可信 `asset_tests` 提供 argv/stdin/fixture files 和预期输出/预期文件/独立检查器。实际运行脚本并由固定检查器或调用方的 asset evaluator 判定；只运行 `--help`、只看 exit=0 或只做 LLM 审查不算功能验证。
5. 默认 Python 功能运行器使用明确 argv、临时 cwd、环境白名单、输出限额、超时和完整进程组清理。必须明确其可用隔离能力；不能把临时目录冒充 OS 沙箱。需要更强隔离的环境通过实际提供的执行能力完成，缺少所需能力保留 unknown，不绕过要求执行。
6. 修改了脚本依赖的 references/templates，也会触发相应脚本功能检查。退休脚本的验收由绑定的替代行为/回归检查承担，不对已移除文件伪造编译成功。
7. 脚本没有功能材料、编译失败、超时、工具不可用、结果绑定不全均形成明确记录并影响准入。脚本检查是 evolve 默认路径的一部分，不要求调用方另起维护脚本“记得去跑”。

无脚本的候选可记录 asset validation 的 not_applicable；存在脚本而没有材料则需要证据。脚本功能执行使用真实预置材料；模型生成的自测可以附加保存，但不能替代外部检查或放宽通过条件。

## 5. 建议的实际调用链和 API

```text
evolve(..., case_set, protocol, execute, evaluate,
       verification=None, execute_view=None, asset_runner=None)
  → 公共材料目录（从verification或现有case_set投影）
  → learn(..., verification_catalog)
  → prepare_verification(base, proposals, diagnosis, materials, explicit_policy)
  → compile/check assets + 按计划的普通比较 + 必需局部组合对照
  → 完整覆盖/质量门 → SelectionRecord → publish
  → 后续context使用受范围/版本约束的measured_effect
```

- `verification=None` 不意味着不验证：旧 case_set 仍提供任务检查材料；系统仍收集检查义务、自动检测脚本/组合需求，缺材料则 needs_evidence。
- 默认 Python asset runner 可直接使用；`asset_runner` 仅供实际需要的其他执行环境实现同一明确任务，不建设运行器注册框架。
- `execute_view` 是组合实验实际需要的受控输入边界，不重写 Agent。无适用组合时不要求它；有必需组合而不具备能力时不谎称测量。
- `compare_candidates` 直接调用也走同一个 prepare/coverage 路径；不能通过绕过 evolve 跳过 check_plan/资产义务。
- 旧 case_set 的 private criteria 一直只给 evaluator；公开 catalog 不泄漏它。旧已发布历史不改写；旧未发布候选没有新验证证据时需补验，不能直接豁免。

## 6. 请 root 统一的字段/Schema/提示词交接

| 位置 | 增量字段/约定 | 真实消费者 |
| --- | --- | --- |
| DiagnosisDraft.check_plan / PatchDraft.check_plan | `check_ref:string|null`；宿主另给 requirement_id，不让模型造ID | verification材料绑定与覆盖 |
| diagnose/propose inputs | `verification_catalog`（公开说明、用途、证据种类、已存在引用；不含gold） | B更新提示词并传入，C安排请求 |
| candidate envelope | `diagnosis_ref`/诊断内容hash或共享 `intent_ref`，保证原诊断义务不能只被提案改写后消失 | prepare_verification + 发布复核 |
| VerificationPlan | id/project/base/candidate/generation/aliases、requirement记录、trusted material hashes、job/case/arm/repeat计划、缺材料、provider/config与预算hash | 执行、覆盖检查、N10 |
| VerificationRecord | plan_ref/hash、逐义务结果/实际证据refs、complete/failed/needs_evidence、usage_refs | Validation覆盖门及N10 |
| EvaluationPlan/ValidationRecord | verification_plan_ref/hash、verification_record_ref（适用时） | 防止普通质量通过绕过缺检查 |
| ExecutionView | 上节完整字段；来源库和实际提供视图身份分开 | execute_view 与对照结果绑定 |
| AssetCheckRecord | candidate/bundle/material hashes、owner/path/runtime、compile/function kind、实际退出/输出/检查证据、pass/fail/unknown、usage/time refs | 准入及报告 |
| ContrastPlan/Result | source_snapshot、方向A\|B、实际arm view refs、case/repeat/provider/protocol、结果/未知、费用 | measured_effect生产及报告 |
| measured_effect relation | 下方精确字段 | root.context实际范围过滤与排序 |

建议关系字段：

```text
{relation_id, project_id, kind:'measured_effect', from, to,
 metric:'conditional_marginal_gain', value,
 skill_revisions:{skill_id:revision},
 dependency_revisions:{skill_id:revision},
 background_skill_refs:[{skill_id,revision}],
 applicable_context:{task_family:string|null, task_ids:[string], case_set_hash},
 source_snapshot_digest, contrast_plan_ref, supporting_refs,
 known_task_count, repeats, evidence_level:'executed_local_contrast'}
```

任务族没有明确材料时只限定已测 task_ids，不自动扩大作用范围。`skill_revisions` 包含from/to；依赖和背景单列。root.selector必须消费这些约束，并且不把旧字段不全的 measured_effect 默认用于当前版本。

## 7. 验收与计量

1. 同一普通case_set，新 check_ref 增加实际请求；未知检查引用/缺区分性材料返回needs_evidence并保持active。
2. 只满足总体质量而遗漏一个必需check/脚本检查仍不能publish；同快照不同proposal的义务取并集。
3. 私有criteria/gold不进入诊断材料目录；生成者提供的答案不能替代外部材料。
4. 独立Skill A/B产生实际两臂差异与有方向measured_effect；相同视图记录not_identifiable，不能填0。
5. A依赖B时每个有效实验臂依赖完整；不靠删除依赖来获得对照。
6. unknown/缺请求保留原计划分母，不产生关系奖励；正确测量后，root.context在匹配版本/场景改变排序，错版本/错场景完全不消费。
7. 实际Python语法错误编译失败；能编译但功能错误的脚本被独立fixture拒绝；正确脚本形成完整证据并可发布。
8. 配套配置文件改变会触发功能检查；篡改已验证脚本、fixture或完整candidate后发布拒绝。
9. 两个旧普通case_set调用和现有无脚本示例继续用同一入口；新的脚本/组合集成从默认evolve自动触发，不另调用孤立演示函数。
10. 失败、超时、缺工具/缺材料、重复aliases共享执行的全部费用均可追溯，不能为通过验证少报成本。

计时使用 root 的 telemetry.measure_stage：计划/绑定/准入/本地编译为 validate_overhead；publish/recover对应阶段。实际execute/evaluate保持唯一usage，同步外部等待通过meter.exclude扣除，不能把整轮并行wall算成独占维护时间。

## 8. 待主会话确认后实施

建议边界：C owns verification/asset/relations及evaluation/release/engine/candidates接线和测试；root owns context过滤/计分、report、experiments、Schema/目录/文档；B owns learn/diagnose/propose目录输入及intent关联；A继续负责存储、反馈、采样事实。需要的记录集合由A和root统一登记。

本文件提供机制和精确交接建议，不把这些内容标成已实现或已测效果。没有提出削减O06/O07/O08；没有运行模型/benchmark，也没有改产品。
