# Research: Skill 初始集合、选择、修改和发布的实现审计

- Query: 对照 SkillSmith、SkillFlow 的固定源码，审计 N02/N07/N08/N09/N10；给出初始库、按任务检索、经验升为 Skill、受限修改、依赖/冲突/增长、候选验证和发布回滚的首版算法。
- Scope: mixed；只读项目/论文/公开源码，只写本研究文件。
- Date: 2026-09-18
- Authority checked: `docs/blueprint/project-contract.json` v1.0.0，源 SHA-256 `82b0c6aecfd718c352c32d17ca192bd28819bf2011a80b293b1bb0ad20cba4c8`。
- Decision status: 下文 OUR 为待主会话收敛的实现建议，不是已采纳契约或实测效果；所有数值默认值均是可调工程起点。
- Scope boundary: 独立可复用的经验学习系统；不重新定位为复现 SkillFlow，也不把先证明项目必要性作为开发前置条件。未改 HTML、总纲、产品代码或依赖，未运行模型/benchmark。

## Findings

### 1. 文件与当前代码事实

| 路径/入口 | 当前作用与证据边界 |
| --- | --- |
| `docs/blueprint/project-contract.json:221` | LibrarySnapshot 字段摘要；尚未给出规范化 hash 输入及资产闭包规则 |
| `docs/blueprint/project-contract.json:226` | ContextManifest；尚缺候选检索、排除原因和依赖补齐记录 |
| `docs/blueprint/project-contract.json:256` | 已区分依赖、声明冲突、共同使用和测得影响；方向正确 |
| `docs/blueprint/project-contract.json:266` | PatchCandidate 只有字段摘要，缺各操作载荷及可执行前置条件 |
| `docs/blueprint/project-contract.json:271` | ValidationRecord 摘要；需绑定完整候选与执行/评价配置 |
| `docs/blueprint/project-contract.json:325` | N02 已有两层选择与空上下文；缺选择算法、预算与交付语义 |
| `docs/blueprint/project-contract.json:508` | N07 已分类不同故障；缺“选择器/环境问题不误写成 Skill patch”的路由 |
| `docs/blueprint/project-contract.json:547` | N08 操作集合正确，具体 payload/原子性待补 |
| `docs/blueprint/project-contract.json:588` | N09 保留重复执行、依赖、成本；需首版判定规则和验证集使用记录 |
| `docs/blueprint/project-contract.json:629` | N10 唯一发布者和固定运行快照正确；缺 generation、锁/事务、幂等与恢复 |
| `src/types.ts:1`、`:9` | 目前只有 personal/project/evidence/session 等 MemoryItem；不是 SkillRevision 或 LibrarySnapshot |
| `src/store.ts:105`、`:173`、`:184` | Markdown 文件写入及 retrieval_count 增量；不能当作多资产事务或使用收益 |
| `src/controller.ts:48`、`:69`、`:87` | 现有维护策略/提议/结构评价对象，不能直接承担因果归因或学习收益验证 |
| `src/core.ts:209` | 现有 verifyCandidate 不是候选 Skill 在后续任务中的效益验收器 |

相关规范：`.trellis/spec/backend/contracts-and-storage.md`、`validation.md`、`architecture-current.md`，以及 `.trellis/spec/guides/system-boundaries.md`。本报告未加载 implement.jsonl/check.jsonl。

### 2. 主来源核对：哪些可借鉴，哪些不能直接声称

所有 GitHub 链接固定到同一已知提交。本轮通过 GitHub 只读 connector 重新读取关键文件；网页抓取 cache miss 和 shell DNS 失败后未作权限绕过。

**SkillSmith（paper 与公开实现分开）**

- 论文附录 D.2 给各 benchmark 规定相同的初始 Skill/工具集合；公开 [`ensure_base()`](https://github.com/yangforever17/SkillSmith/blob/2cbbd37c5293c3c06f1f5efc5709382639763cfa/src/skillsmith/store.py#L32) 则创建空 skills/tools 目录。因此“Skill 演化必须先自动生成完整初始库”不成立。[论文](https://arxiv.org/html/2606.01314v1)
- [`SkillOp/BundlePlan`](https://github.com/yangforever17/SkillSmith/blob/2cbbd37c5293c3c06f1f5efc5709382639763cfa/src/skillsmith/schemas.py#L10) 有 create/edit/retire 及配套工具操作；不是我们的 rule-level patch schema。作者 [`apply_bundle`](https://github.com/yangforever17/SkillSmith/blob/2cbbd37c5293c3c06f1f5efc5709382639763cfa/src/skillsmith/store.py#L381) 写完整 Skill 文本，retire 删除候选目录。它没有给我们所需的依赖兼容删除证明。
- [`_load_relevant_skills/_rank_skills`](https://github.com/yangforever17/SkillSmith/blob/2cbbd37c5293c3c06f1f5efc5709382639763cfa/src/skillsmith/agent.py#L400) 从当前状态按文本相关性选至多 5 项，两个生态权重均为 0 时只作文本排序；[`config.py`](https://github.com/yangforever17/SkillSmith/blob/2cbbd37c5293c3c06f1f5efc5709382639763cfa/src/skillsmith/config.py#L101) 默认正是 0。不能声称公开默认检索已实现论文全部生态机制。
- [`AgentResult`](https://github.com/yangforever17/SkillSmith/blob/2cbbd37c5293c3c06f1f5efc5709382639763cfa/src/skillsmith/agent.py#L45) 的 activated_skills 来自模型字段，缺省时回退检索建议；trace 含生成的解释、回答末尾和证据，不是完整的可信工具使用日志。
- [`ecology.py:46`](https://github.com/yangforever17/SkillSmith/blob/2cbbd37c5293c3c06f1f5efc5709382639763cfa/src/skillsmith/ecology.py#L46) 用类别残差和共同激活记录估计 utility/synergy。类别校正、EMA 都不消除任务难度/检索选择/版本变化等混杂，也不能将自报使用变成真实因果效应。
- [`loop.py:98`](https://github.com/yangforever17/SkillSmith/blob/2cbbd37c5293c3c06f1f5efc5709382639763cfa/src/skillsmith/loop.py#L98) 当前选 best_state，不能表述为公开实现始终使用论文的加权父代采样。目标改善、capability holdout、验证回归均有配置门；holdout 无可用样本时函数返回 None，不等于存在未见证据。[门控](https://github.com/yangforever17/SkillSmith/blob/2cbbd37c5293c3c06f1f5efc5709382639763cfa/src/skillsmith/loop.py#L164)、[holdout 空集行为](https://github.com/yangforever17/SkillSmith/blob/2cbbd37c5293c3c06f1f5efc5709382639763cfa/src/skillsmith/loop.py#L520)
- [`evaluate_examples`](https://github.com/yangforever17/SkillSmith/blob/2cbbd37c5293c3c06f1f5efc5709382639763cfa/src/skillsmith/validator.py#L239) 可以用线程池并行评测列表，证明并行执行与外层演化并不冲突；这段代码本身不能证明多个写同一环境的 native Agent 是隔离的。

**SkillFlow**

- [`prepare_shared_skills_dir`](https://github.com/ZhangZi-a/SkillFlow/blob/7b49ff5a7e26cd7706e959bfa0dba4746d18440d/iterative_shared_skills_runner.py#L461) 可为空库，也可复制外部模板；论文空库实验与 runner 的模板能力要分开记录。
- [`patcher.py:320`](https://github.com/ZhangZi-a/SkillFlow/blob/7b49ff5a7e26cd7706e959bfa0dba4746d18440d/libs/skill_evolution/patcher.py#L320) 要求优先修改已有能力、限制文档结构、无可复用改变时返回空补丁；载荷是 summary/upsert_files/delete_paths，并不等价于通过机器验证的“最小语义编辑”。
- [`on_trial_ended_hook_sync`](https://github.com/ZhangZi-a/SkillFlow/blob/7b49ff5a7e26cd7706e959bfa0dba4746d18440d/iterative_shared_skills_runner.py#L630) 将完成记录、轨迹和当前库交给 patcher 后直接应用。我们要求的候选重跑、发布/回滚不是该默认回调已有的保证。
- [`build_group_job_config`](https://github.com/ZhangZi-a/SkillFlow/blob/7b49ff5a7e26cd7706e959bfa0dba4746d18440d/iterative_shared_skills_runner.py#L487) 强制同组 n_concurrent_trials=1，以保住逐题更新语义；不能直接将它设成并行并声称仍是同一在线协议。

**补充的一项实际来源：验证集选择偏差**

[Cawley & Talbot, JMLR 2010](https://jmlr.org/papers/v11/cawley10a.html) 说明有限样本上的模型选择准则也会被过拟合。此处借用的是一般评估边界：反复用于候选选择的 validation/holdout 已参与优化，不能再当最终未见测试。它不提供“重复 3 次就安全”的阈值。

### 3. 逐项问题与首版决策：不要压缩成一个 N02 或 N08 标签

| 独立问题 | v1.0.0 的缺口/风险 | OUR 首版可执行决策 |
| --- | --- | --- |
| L01 初始库从哪来 | 空库允许，但 seeded 起点无数据契约 | 默认受管库 S0=∅；可导入显式种子包，来源/完整 hash/范围冻结 |
| L02 执行器自带 Skill 如何算 | 空受管库容易被误说成 Agent 完全没有知识/Skill | 记录 native 内置、项目既有、用户全局和本项目受管资产的可见配置；区分托管集合与全部上下文 |
| L03 库版本怎么选 | “最新”容易混入未发布候选 | 使用 profile 的 active 指针；运行开始固定 snapshot+generation；默认不做历史版本 bandit |
| L04 库内怎么选 | 未规定相关性、适用性、预算、依赖 | 显式兼容过滤→确定性文本排序→依赖闭包→冲突/预算检查；可返回空集合 |
| L05 初始集合与任务检索是否相同 | “预生成集合”与选择当前任务指令容易混淆 | 初始化决定有哪些长期资产；N02 决定此次给哪些资产及哪些层级 |
| L06 一条经验何时值得成为 Skill | 容易设置“失败就 ADD”或无根据的次数门槛 | 单例可生成候选；要求触发条件、可执行规则、验收行为及证据。现有能力覆盖则 PATCH/NOOP；正式复用由 N09 控制 |
| L07 改谁 | 缺统一的修复路由 | 内容/触发描述可修改；选择算法 bug、环境故障、评价失真要生成诊断工单/NOOP，不伪造 Skill 规则去补偿 |
| L08 PATCH 的原子性 | “最小修改”只是一句话 | 绑定 base_snapshot、expected_revision、声明修改字段；程序计算真实 diff，超范围拒绝 |
| L09 新增/合并/拆分如何表达 | 容易无限追加操作种类 | 外层只有 ADD/PATCH/RETIRE/NOOP；合并=PATCH 保留项+RETIRE 被吸收项+必要依赖更新，作为一包验证 |
| L10 依赖如何保护 | 删除/禁用 Skill 可能破坏其他 Skill | 校验结果快照依赖闭包；缺失/修订不兼容即拒绝，不静默 cascade |
| L11 冲突和共同使用如何判断 | 共现差不等于因果相互伤害 | 静态声明、共现和对照效应分库存；自动选择只用明确冲突，统计信号用于安排实验 |
| L12 库如何防膨胀 | 只限制选入 tokens 仍会积累重复资产 | 先找覆盖者；每候选默认一项主能力；重复检查+库/单资产预算；低频不自动删除 |
| L13 怎么证明有用 | 内容格式正确容易变成发布依据 | 完整候选快照用相同执行/评价协议重跑；target、transfer、regression 分角色 |
| L14 怎么处理随机成功 | 单次 rescue 容易直接升为规则 | 保存全部 trial；以 task 为统计单元，多次执行估计该题稳定性；不以 reviewer 投票代替运行 |
| L15 怎么处理适应验证集 | validation 一直循环使用 | 开发验收集公开记账，限制候选尝试预算；另留最终冻结集，只在冻结版本上出最终数字 |
| L16 并行发布怎么避免混乱 | 只有“唯一 N10”还没有运行时锁 | 批次内冻结 active；候选可并行，发布有独占锁/事务和 expected_generation 比较；失配候选重新生成/验证 |
| L17 回滚是否真的可用 | 只存 SKILL.md 不够恢复脚本/关系 | 保留所有资产和依赖的不可变快照；回滚检查当前交付环境兼容性并产生新的 release event |
| L18 效果等价候选如何处理 | 几乎每次措辞变化都可能发布 | 没有测得质量/成本目标收益则默认保留 active；NOOP 是正常成功分支 |

### 4. 初始化和 N02：具体选择算法

#### 4.1 初始库

默认受管 S0 为空；它是带 manifest 的真实空快照，而不是缺目录。首条可靠经历经过 N06/N07 后可以产生 ADD 候选，因此不需要在见到任务前制造一整套猜测 Skill。

种子模式可选：导入人工写好的项目流程或明确授权的既有 Skill；记录 origin=seed、原始来源/许可、资产 hash、适用环境。导入后的格式、依赖与交付检查只代表能加载，不把它改写为效果已验证。所有实验组使用相同 S0，报告受管增益。不要从最终测试任务/答案预生成种子。

执行器固有工具、系统提示、用户全局 Skill 不是 S0 自动覆盖的范围。受控运行须记录它们是否可见；只有已验证的隔离适配器才能声称严格排除了外部资产。先做可解释记录，不修改用户的全局配置。

#### 4.2 两层选择的首版算法（OUR）

```text
profile = resolve_delivery_profile(task.environment, executor_config)
(snapshot_id, generation) = read_active(profile)       # 一次固定
snapshot = read_immutable_snapshot(snapshot_id)
eligible = filter_by_explicit_scope_and_compatibility(snapshot, task)
rank = lexical_rank(task, eligible.name+description+triggers)
for root in rank with score > 0, stable tie break by skill_id:
    closure = dependency_closure(root, snapshot)
    if closure has missing/revision mismatch: record excluded, continue
    if closure conflicts with selected: record excluded, continue
    if complete closure cannot fit budget: record excluded, continue
    select root and missing dependencies
    stop after max_root_skills
return immutable manifest, or valid empty manifest
```

首版文本排序可用 BM25；中文按 Unicode 规范化后的汉字二元片段、英文标识符分词，字段固定，算法版本入 manifest。不把任意相关性分数解释成匹配概率。先不引入 LLM reranker 或未经校准的生态权重。语义漏召回是已知不足，后续可替换排序器而不改变 manifest/发布契约。

建议配置起点：max_root_skills=3、context_budget_tokens=4096、单 Skill 正文目标不超过 1200 tokens；依赖额外计入同一总预算。它们是方便观察成本的工程默认值，不是论文证明的最优值。tokenizer/估算器及版本须明确；若模型 tokenizer 不可得，标记 estimated，不声称精确 token。

不能截掉 Skill 尾部依赖/验收条款后仍说提供了完整 Skill；不够预算时跳过根 Skill 或换更小集合。references/scripts 默认仅交付可访问文件，是否全文进入 prompt、是否被读取分别记录。为了可比较，最初可直接将选中的短 Skill 正文注入受控执行器；native progressive disclosure 作为另一 delivery_mode 单独记录和验证。

建议 SelectionManifest 最小形状：

```json
{
  "schema_version": "selection/1",
  "run_id": "run-17-1",
  "task_revision": "task-17@2",
  "profile_id": "coding-python-v1",
  "snapshot_id": "sha256:<library>",
  "active_generation": 8,
  "selector": {"policy_version": "lexical-v1", "config_hash": "sha256:<config>"},
  "selected": [
    {"skill_id": "csv-schema-preservation", "revision": "sha256:<revision>", "reason": "task_match", "required_by": []}
  ],
  "excluded": [{"skill_id": "pdf-layout", "reason": "no_relevant_terms"}],
  "delivery": {"mode": "injected_text", "content_hash": "sha256:<actual_bytes>", "asset_manifest_hash": "sha256:<files>"},
  "budget": {"limit": 4096, "used_estimate": 720, "estimator": "configured-estimator-v1"},
  "unmanaged_context_ref": "runtime-baseline-manifest.json"
}
```

selection ≠ delivery ≠ observed_read ≠ demonstrated_effect。后三者写后续事件，不能由这个 manifest 自动补齐。

### 5. 经验升格、归因和操作选择

经验池可以保存一次任务的事实、困难、反例和不确定解释；Skill 要提供跨实例可执行的行为。是否生成候选与是否允许发布必须是两道判断。

首版 N07：用失败信号、工具/资产名和任务族检索最多 5 条相关经历与最多 5 个已有 Skill；优先加入相同问题的成功对照及反例，数量不足原样记录。调用一次结构化诊断模型，输出 observed_problem、candidate_causes、evidence_refs、counterevidence、target_rule_refs、repair_route、expected_behavior、check_plan。代码检查引用存在、目标修订匹配。模型解释默认 status=hypothesis；只有带具体对照执行记录才能标为 tested_hypothesis，也不自动提升为普适因果结论。

不要求先有多轨迹才能开始学习：单例能发现缺口，重复执行帮助判断该题稳定性，不同任务帮助检验可复用范围。不能将同题 10 次执行记成 10 个独立任务，也不能将 10 个 LLM reviewer 当成 10 次环境执行。

| 观察到的情况 | N07 路由/首选操作 | 必须补充的证据或约束 |
| --- | --- | --- |
| 已有正确 Skill 未进入清单 | 先诊断 scope/trigger 与 selector；可 PATCH 触发描述，算法 bug 则 NOOP+issue | 对比 selection/exclusion；没有读取事件不能反推未提供 |
| Skill 已提供但未观察到使用 | 保留消费未知；检查交付和任务条件 | 不能立即改内容或打“无效”标签 |
| 某条明确规则与可靠验收冲突 | PATCH 该 rule，含反例和更窄条件 | 实际规则修订及失败产物；区分相关与因果 |
| 存在可复用能力缺口且库内无覆盖 | ADD | trigger+步骤+校验+范围，不能只把任务答案封装成 Skill |
| 一次性路径/具体客户值/用户事实 | NOOP（保留适当记忆） | 不把私人事实升级成通用程序规则 |
| 新经历重复已有规则且没有新边界 | NOOP，链接证据 | 不制造“第二个同义 Skill” |
| 两条规则互相干扰 | 先缩窄条件/PATCH；必要时合并+RETIRE | 限定配置的共同使用证据及合法组合对照 |
| helper 的接口/实现错误 | 与对应说明一起 PATCH 资产包；原生工具缺陷在边界外则 issue | 测试代码与调用者必须匹配；不靠多写提示掩盖工具 bug |
| 确认重复、已替代或有害 Skill | RETIRE，必要时同包 PATCH 依赖者 | 结果依赖闭包、替代者与回归；低检索量单独不足 |
| 环境暂时异常、评价器矛盾或缺证据 | NOOP/保留诊断 | 不自动硬编码重试经验或把 unknown 改成失败 |

### 6. 最小 Skill 和 patch 数据结构

这是 OUR 内部结构，不声称是某客户端官方 frontmatter schema。内部元数据不全部塞入 SKILL.md。由交付适配器生成客户端可读的 `name/description` 及正文，保留渲染器版本和完整内容 hash。

```json
{
  "schema_version": "skill/1",
  "skill_id": "csv-schema-preservation",
  "revision": "sha256:<computed-by-host>",
  "name": "csv-schema-preservation",
  "description": "处理带 schema 的 CSV 转换时，保持标识符和数值字段的类型语义。",
  "applicability": {
    "scope": ["python-csv-transformation"],
    "triggers": ["csv", "schema", "identifier"],
    "exclusions": ["schema 要求把该字段转换为数值"],
    "required_capabilities": ["read_files", "execute_python"]
  },
  "rules": {
    "R1": {"when": "开始转换前", "instruction": "读取字段 schema，区分标识符与数值。", "check": "每个输出字段有对应类型约束。"},
    "R2": {"when": "字段声明为字符串或标识符", "instruction": "按字符串读取并保留前导零；只对明确声明为数值的字段转换。", "check": "用前导零标识符与数值字段各做一个输出检查。"}
  },
  "dependencies": [],
  "declared_conflicts": [],
  "assets": [{"path": "references/schema-example.json", "role": "reference", "sha256": "<asset>", "content_ref": "objects/<asset>"}],
  "evidence_refs": ["exp-17", "exp-18"],
  "counterevidence_refs": ["exp-numeric-field"],
  "origin": {"kind": "learned", "proposal_id": "p-9"}
}
```

`revision` 由程序对规范化内容及资产清单计算，模型不能自行宣布 hash。`rules` 用稳定键而非数组位置，才能在下一版指向 R2。first implementation 的依赖可直接锁到 `skill_id + exact_revision`；这会增加更新依赖者的工作，但不假装能从自然语言判断兼容。若依赖组件修订变化，结果包必须更新依赖者并一起检查，或继续保留旧依赖；未来再添加明确接口兼容范围。

初始导入既有 Markdown 时保留原文资产；归一化为结构化规则是一次可审阅的转换，不能偷偷改变正文后仍沿用种子 hash。首版默认空库可避免先实现通用 Markdown 理解器。

PatchCandidate 示例：

```json
{
  "schema_version": "skill-patch/1",
  "proposal_id": "p-9",
  "base_snapshot": "sha256:<base>",
  "expected_active_generation": 8,
  "profile_id": "coding-python-v1",
  "intent_ref": "intent-9",
  "operations": [
    {
      "op": "PATCH",
      "skill_id": "csv-schema-preservation",
      "expected_revision": "sha256:<old-revision>",
      "replacement": "<complete Skill content object; host computes new revision>",
      "declared_changed_paths": ["rules.R2"],
      "evidence_refs": ["exp-17", "exp-18"]
    }
  ],
  "expected_behavior": "带前导零的标识符不被数值推断破坏，合法数值字段仍可计算。",
  "check_plan_ref": "validation-plan-9"
}
```

示例中 replacement 占位是为了展示整体接口；实现 schema 必须用完整 Skill 内容对象，不能接受字符串占位。

可编码的判别联合如下；`SkillContent` 是上方对象去掉程序计算的 `revision` 字段，`EvidenceRef`/`RevisionHash` 是在 Host 中可解析、可核对的引用，而非 LLM 自行认证的值。

```typescript
type Op =
  | { op: "ADD"; skill_id: string; expected_absent: true;
      content: SkillContent; evidence_refs: EvidenceRef[] }
  | { op: "PATCH"; skill_id: string; expected_revision: RevisionHash;
      replacement: SkillContent; declared_changed_paths: string[];
      evidence_refs: EvidenceRef[] }
  | { op: "RETIRE"; skill_id: string; expected_revision: RevisionHash;
      reason: string; replacement_skill_id: string | null;
      evidence_refs: EvidenceRef[] }
  | { op: "NOOP"; reason: string; evidence_refs: EvidenceRef[];
      next_evidence_needed: string[] };
```

JSON schema/Zod 的运行校验应拒绝未知字段，并校验 `skill_id == content.skill_id`、非空理由、引用存在、NOOP 独占及操作集合内目标冲突。Host 计算真实 changed_paths 后再比较，不能仅检查模型声称改了哪些字段。

| 操作 | 最小载荷 | 程序强制前置条件 | 结果 |
| --- | --- | --- | --- |
| ADD | new skill_id、完整 content、assets、evidence_refs | ID 在 base 不存在；路径合法；依赖在同包结果中可解析；覆盖者检索记录存在 | 新修订加入候选库 |
| PATCH | skill_id、expected_revision、完整 replacement、declared_changed_paths | base 含该修订；程序真实 diff 与声明一致；只改允许字段；路径/操作预算满足 | 产生新修订；旧修订不可变 |
| RETIRE | skill_id、expected_revision、reason、replacement_skill_id 可空、evidence_refs | 目标存在；结果无悬空依赖；必要依赖者显式同包修改/退役；有相关回归计划 | 从候选活跃集合移除，历史保留 |
| NOOP | reason、evidence_refs、next_evidence_needed 可空 | 必须为唯一操作；不含资产写入 | 只保存决定，不生成新 active/库版本 |

不让模型输出任意宿主路径、Git diff 或命令作为操作授权。资产使用相对路径和内容对象；禁止路径逃逸/跨根写入。新增/修订脚本只属于受管 Skill bundle，并由同一候选检查；原生工具循环和 Trellis 开发资产不在作用域内。

首版建议：每候选一项主要行为假设、max_operations=4（含依赖更新）、最多 1 个 ADD。真实 diff 检查和字符/token 上限能限制修改面，不能证明语义改动“小”。复杂合并超过上限时拆成保持依赖合法的多个候选，或显式修改配置；不能先提交坏的中间版本。

### 7. 关系、组合与膨胀

关系存四种，不压成一个 synergy 数字：

1. `depends_on`：强依赖，精确 revision 和来源；选择、禁用、退役都必须检查。
2. `declared_conflict`：明确不应共同执行的指令/条件，并记录适用上下文；选择时排除冲突集合。
3. `co_used`：只记录在何种证据等级下共同提供/读取/报告使用，带 run IDs，不直接驱动删除。
4. `measured_effect`：某个对照协议下的局部效果，记录 task set、两个合法配置、重复执行、指标及不确定性；不能作为全局永久标签。

组合归因可比较无 i/j、i、j、i+j，但只在这四种配置都合法时成立。如果 i 依赖 j，`i without j` 是损坏配置，不能用于证明 j 无用。此时比较 `j` 与 `closure(i)` 的增量，或者整体组件闭包；交付 manifest 和其他上下文固定。修改触发描述时，还要独立跑一次正常 selector，避免只在强制加载时有效。

膨胀控制的首版规则：ADD 前检索已有覆盖者；保存“为什么不能 PATCH”的解释；同义候选优先 NOOP/合并；单资产和选入上下文设预算；受管 active 根 Skill 数量建议先设 32 的软上限，超过时阻止新的无替代 ADD 并提出整理候选。32 只是容量管理起点，不能宣传成效果最优点。引用/脚本不是无成本垃圾桶，统计全文大小和加载成本。

不因长期未检索就自动 retire：可能是低频但必要的能力。可以降为未默认选择的候选或提出人工/任务证据检查，但产品内部“自动禁用”若改变交付集合，本质也是受控快照变更，必须经 N09/N10。即使不物理删除文件，依赖者仍可能失效。

保留退休记录 `(skill_id, revision, reason, evidence, replacement, scope)`；近似反模式匹配只提示重犯风险，不作跨场景永久 veto。否则旧环境下失败的方案会阻止新工具/新环境下合理重试。

### 8. N09：实际退化控制，而不是“通过留出集就保证不退化”

检查对象必须是 `(candidate_snapshot_hash, base_snapshot_hash, profile/config hashes, validation_protocol_hash)`。不能只检验某个生成的 SKILL.md 再发布包含其他文件变化的目录。

**分层执行顺序（OUR）**

1. 静态契约：操作前置条件、路径、规则引用、所有资产 hash、依赖闭包/冲突、预算、客户端渲染格式；失败即拒绝。
2. 资产可执行性：若修改脚本，运行相应测试；生成者提供的测试只能补充，不能替代既有独立验收。测试缺失时结果为不足，不把“没有测试”当做行为正确。
3. target：重跑触发修改的任务，检查具体问题是否得到改善。这是修复证据，不是未见泛化。
4. transfer：选未用于本候选提议的同族新实例，确认不是记住原答案。开始时只有一条经历也能产候选；缺此类任务时先保留候选，不伪造 transfer 通过。
5. regression：选择旧版已能完成的任务及依赖者、近邻冲突 Skill 的任务；包含必要的反例。
6. cost/stability：记录全部执行和各阶段用量，评价前规定阈值，不看到结果后调门槛。

首版受控任务配置示例：target 最多 2 题、transfer 2 题、regression 4 题；base/candidate 各 3 次独立执行，因此最多 48 个 task trials。它是一个可执行预算示例而非最低科学样本量，实际任务太贵时应显式缩小评估配置、保留证据不足状态或选择轻量任务，不能把同样门控偷偷降成一次 judge。所有 trial 可以在隔离环境内并行，同组固定模型/预算/环境初态，顺序随机或交错以减小时间漂移；相同 seed 不能保证远端模型的完全可重复性。

建议默认判定：

- 所有硬性完整性/确定性保护条件通过；runtime 错误、缺测和未知不得丢掉后算平均分。
- 质量改进类候选：target 平均分严格改善，transfer 不低于 base 且至少一题改善；regression 平均分不降，预先标记的 must-preserve 题不得从 base 稳定成功变成候选不稳定。
- 成本改进类候选：质量满足预设非劣界限，且达到预先规定的成本改善目标。不能临时用“更短”解释一个没有质量提升的新 Skill。
- 首版零容忍回归和零非劣界限是偏保守的发布策略，不是统计证明。3 次执行无法保证总体成功率没有下降；保存区间/方差与样本数，报告为“在这组已测任务和配置下通过”。
- 预算单列：candidate 执行成本约束、单候选学习/验证费用上限、整批累计费用上限。失败提案和重试都计入，不能只报发布后推理节约。

目标/transfer/regression 是用途标记，不保证永远独立：某题的失败内容一旦进入下一轮提案，它就成为开发材料。为每题记录 seen_by_generator、selection_count、last_used_at；所有候选次数和失败候选留存。限制同一任务集上的候选搜索次数有助于控预算，但不是统计修复。

最终报告另外使用冻结测试集；在库/选择器/模型/协议冻结后测一次，不把结果用于继续选择同一版后还称为“未见测试”。这避免将反复使用的 SkillSmith 风格 validation/frontier 分数误写成独立泛化分数。

### 9. N10：完整快照、并发与回滚

**推荐第一版采用批次冻结+串行发布。** task 的多个重复执行、多个 task、同 base 的多个候选验证可以并行；所有运行各有独立可写工作目录/Agent home/产物目录，共享只读 Skill 快照。不能让它们同时修改用户的原始代码目录或共享可变 Skill 目录。

批次协议：固定 `(base_hash, active_generation)`→并行收集→归集证据/提出有限候选→并行检查不可变候选→按预先规则选一个→N10 发布一次。下一批看到新版。批内任务不会相互学习，报告为批次更新；不能声称等价于逐题在线更新。

LibrarySnapshot 的 hash 闭包至少包括：skill_id→revision、全部 SKILL.md 渲染字节、脚本/引用/模板资产、依赖锁、关系声明、兼容声明与导出器版本。外部可变数据不在 snapshot 内时，必须由 RunBundle 的环境/输入证据另外定位，不声称完全可重放。

推荐发布伪代码：

```text
assert validation.status == accepted
assert validation.candidate_hash == candidate.hash
assert validation.base_hash == candidate.base_hash
assert all candidate assets exist and hashes match
assert delivery profile matches the validated profile
write immutable candidate snapshot completely
lock(profile.active_writer):
    current = read_active(profile)
    if current.hash != expected_base or current.generation != expected_generation:
        return stale_base                     # 不是自动成功，也不强行覆盖
    if release_id already committed:
        return existing release              # 幂等
    commit release metadata and next active pointer as one transaction/journal step
    # 文件方案须在锁内比较+原子替换，并有写前记录和崩溃恢复；rename 单独不提供 CAS
return published
```

generation 防止 A→B→A 后旧候选误以为仍是原先的 A。运行开始 pin 的 snapshot 不改；“发布最新版”只影响后续运行。候选 B 在候选 A 发布后变成 stale：可以归档，也可以基于新 active 重新应用并重新验证，不能认为 A/B 分别通过就代表合并后通过。

回滚是新 release event，指向旧的完整快照并增加 generation；不是改写历史。检查旧快照资产齐全且兼容当前 runtime/tool profile。若外部工具已升级不兼容，不能宣称只回退 Skill 即恢复；返回 incompatible 并保留诊断，按事先配置选择兼容版本或停用该交付 profile。回滚不删除造成问题的轨迹和经验。

### 10. 一个贯穿节点的具体例子（设计样例，未运行）

任务是把 CSV 转成符合 schema 的 JSON。schema 声明 customer_id 是字符串，输入包含 00123；现有 `csv-schema-preservation@r1` 的 R2 笼统要求自动数值推断，导致标识符变为 123。

1. N02 固定 snapshot L8，manifest 表示向执行器提供 r1；有读取事件时记录 observed_read。仅“提供”不声称 Agent 实际服从 R2。
2. N03 的事件记录原始读取、转换命令、输出文件 hash；N05 独立 schema/值校验指出 `/customers/0/id` 值不符，而命令退出码为 0。这是任务失败证据，不是每个工具调用都失败。
3. N06 只提取与字段类型相关的事件窗口及检查结果，保存原事件 refs；另检索一条同族成功经历，其中显式使用字符串 dtype；保留“数值字段仍需计算”的反例。
4. N07 给出内容缺陷假设，定位 r1.R2，并列出备选解释“后续序列化转型”。读取中间产物可帮助区分，不能只凭失败文本宣布因果已证实。
5. N08 优先 PATCH R2，增加条件：声明为字符串或标识符时保留原文本，只有明确数值字段参与数值转换。它不新增一个几乎相同的 Skill，也不硬编码 customer_id 或 00123。若 S0 为空，则这一能力可成为 ADD 候选，仍走同一后续门控。
6. N09 分别检查原任务、其他标识符字段的新任务、正常整数/小数任务及依赖此转换的任务；base/candidate 同环境多次运行。若改成“所有字段永远字符串”导致数值计算退化，拒绝候选。
7. 只有检查结果满足事先协议，N10 才发布完整 L9。若发布锁内发现 active 已从 L8 变化，返回 stale_base，不能覆盖。
8. N11 报告首次任务结果、旧/新版本逐题变化、样本数、全部学习和验证成本；此样例当前没有这些执行数字，不能写成已经提升。

### 11. 对总纲和 HTML 的最小修改建议

不要再新增一套与 JSON 平行的设计正文。将以下内容加入权威 JSON，再由模板生成 HTML：

- 每节点新增 algorithm_steps、implementation_defaults、prompt_contract（仅模型节点）、input/output schema_ref、failure_states、evidence_boundary。
- L01–L18 保留为可单独检查的设计问题；映射到节点并标明 resolved/proposed/open，避免标题折叠后丢掉关键区别。
- N02 展示“初始化 S0 → active profile → 按任务选择”的三段关系，以及一份 SelectionManifest。
- N07 展示上述修复路由表、证据等级和待验证假设；不将原因字段命名成已证实 root_cause。
- N08 展示四种操作各自 payload、前置条件、diff 预算和依赖完整性；候选→active 不允许捷径。
- N09 展示 target/transfer/regression/frozen-test 的访问权限、重复执行和 all-cost；“schema 通过”与“行为通过”独立。
- N10 展示 candidate hash、expected generation、锁/事务、幂等、stale、rollback incompatible 等状态。
- 提供空库 ADD 和现有库 PATCH 两条同流程样例；每个示例明确“设计样例/真实执行”身份。

这些变更是为了让实现有确定输入输出和错误分支，不能把 HTML 当作运行时执行器。执行器实现、模型调用、学习/验证运行和学习效果数字仍是后续工作。

## Caveats / Not Found

- 本报告没有运行论文实验、模型调用或本项目学习闭环；数值默认、容量、选择算法和门控都是未验证的设计起点。
- 没有依赖 SkillSmith 的生态公式建立普适因果结论；没有发现它能替代干预对照和独立测试的证据。
- 两个固定实现提供参考代码，不提供我们的并发安全、完整资产发布、跨 Agent 兼容、日常会话目标变化或长期无退化保证。
- 静态 source audit 不足以证明 native Codex/Claude 确实读取并使用某个 Skill；必须由接入记录和任务行为另行支持。
- 初始 seed 的合法性、许可及真实含量需具体导入时记录；未复用上游源码进本仓库。
- 本地 MEMORY.md 的相关检索没有命中可用项目决策；本报告未以旧的“复现”记忆作为依据。
- 每个候选只有限测试，无法保证未来任务永不退化；可以保证证据绑定、变化有界、拒绝已知回归和可恢复性，不能保证未观察结果。
