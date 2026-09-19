# 独立职责边界审查

> 本文保留首次未通过的证据。最新判定见末尾“同源共享修复后的复审”：产品边界复审通过，最终文档生成一致性由主代理收尾核对。

审查基线：HEAD `e1f3c15de024f3b63d144e11a7a91c173cfaa791` 加当前未提交 diff；总纲 v1.8.1，SHA `29e0e162784907e00bd3cf9889af715accfc4ad5fe262f39f4cb72e42a11939e`。审查时 `evidence.py` SHA256 为 `1e344f881f709fab6f7088d4dc514f61867e227e58ac7762ce8d4567a42172cd`。本报告对应双反馈正文仍独立参与选材的版本，不是后续修复的签字。

结论：**暂不通过，存在一个固定预算下的实际供证回归。** 字段来源、引用校验与显式容量修改守住了 LLM/framework 边界；但新增字段视图不应被当成第二份独立高优先级正文，挤掉已要求保留的工具证据。没有修改产品、测试、总纲或执行真实模型调用。

## Findings (fixed)

- 无。本次独占路径仅为本报告；设计和选材改动由主代理审定。

## Findings (not fixed)

### 必须修：双反馈正文占据两份选材容量，造成工具证据退化

- 位置：`src/memory_orchestrator/evidence.py:235` 新增 reason 记录；`:587` 将无 call_id 的两视图按不同 base_ref 分为两个单元；`:597` 同为 priority 0；`:627` 分别取得完整 fragment/role 宽度；`:692` 分别放入正文；`:703` 在真实总预算下拒绝被挤出的调用。
- 原有验收：`tests/test_gdpevo_context.py:92` 以真实旧索引重开和原 42,000 字符容量检查工具证据；`:133` 要求订单、产品与库存返回仍提供正文。主代理完整 GDPevo 检查实际得到 `{customers, products, inventory}`，订单返回消失；详见 `gdpevo-tests.txt`。
- 独立诊断复现同一真实 fixture、同一旧 failure_hint 索引、同一配置，只在内存索引中暂时移除新增 reason 视图作旧行为对照，未修改原文或产品文件：

| 首个订单调用组 observation_16/17 | 仅旧 full | 当前双视图 |
| --- | ---: | ---: |
| 拟放置包字符数 | 29,731 | 32,435 |
| 预留目录后的放置上限 | 31,500 | 31,500 |
| 正文放置 | 通过 | 拒绝 |
| 当前双视图的 locator fallback | — | 31,857，仍拒绝 |
| 后续零预留 locator 重试 | — | 42,010 > 42,000，拒绝 |

- 两份反馈各放入 1,800 字符正文；新增 reason fragment 的完整序列化为 2,703 字符，加分隔符恰为首差 2,704。原文编码便利的附加视图变成了第二个常驻材料，挤掉的是独立环境证据。当前最终包 39,757 字符不代表早先正文能通过 31,500 的预留检查，也不代表后续含来源及关系的 locator 能放进 42,000。
- 建议：保留两种独立 source 身份和旧全文回读能力，但在新包选材中把 full/reason 当成同一反馈的替代表示，避免两份重叠长正文常驻。可优先提供 reason 正文，并通过有界 full 原文字段片段或已有反馈元数据提供状态/来源；如两视图同时提供，应共享该来源的选材额度。**全部实际正文和来源元数据仍应照常计费，不得让重复文字免费，不得改引文结果或硬编码 orders 类别。** 具体表示选择属于本任务的设计判断，故本审查不直接修改。
- 验收建议：保留当前 `test_gdpevo_context` 42k 配置及工具类别断言，同时保留 full 旧引用可重读、reason 原文精确引用和无重复事件分母的检查。修复后才继续冻结实盘。

### 已核对的边界与剩余证据

- 来源：`evidence.py:232-240` 保留 full 的生成方式，reason 使用 `reason-text-v1`、独立 raw_ref/hash，正文严格复制原字符串；未解析内部 JSON 或规范化业务值。`:217` 的 adaptation 可见性检查发生在两个视图之前。
- 引用：`learning.py:82-123` 未改，仍检查本轮提供的 ref 和 exact substring；`evidence.py:1031-1078` 仍重验来源/hash/range/正文/结构/预算。新测试 `test_memory_feedback_text.py:88-174` 保留错 ref、伪造和篡改拒绝。
- 旧包与分母：`evidence.py:508-534` 仅从必需覆盖义务中排除附加 view，不能用它替代遗漏的原事件/full；`feedback_view` 在 `:1151-1164` 仍逐条原反馈聚合 refs。`:1003-1028` 的轨迹事件覆盖只计 source_event，新增 view 为 false。旧 inline/disk 包的复验和补读定向检查通过。
- 容量：`examples/gdpevo_pilot/run.py:35` 只将 summary 单次输入 8k 改为 12k。4 次调用、32k/4k 累计、全局限额、有限修复均未改；`model.py:141-183,374-383` 仍计完整请求并拒绝超限。
- 提示词：`prompts.json:9-26` / 总纲 `:11788-11804` 的 revision 3 只披露字段来源、同视图 ref 与不重复支持；没有替 LLM 决定摘要/经验/归因。原有 task/abstained 示例仍满足原文引用要求（总纲 `:13387-13409,13710-13721`）。`test_memory_summary_repair.py:16-32` 的自动转义只存在于明确标注的脚本测试响应中，未进入生产修复路径。
- 上述修复容量测试使用旧实盘输入和拒绝稿；只能证明当前 prompt/config 容纳该完整修复请求，不能证明真实模型会正确切换 reason ref，不能证明新的完整学习周期或 Skill 收益。

## disk/inline 等价测试的容量前提

`tests/test_memory_trajectory.py:202-227` 仅在语义等价检查中显式提供非绑定容量，保留禁止整文读取、分组顺序及原文相等检查。这一调整本身合理：磁盘来源定位器必须真实计费，等字节限额并不保证相同的正文选择。

独立探针结果：

| 配置 | inline/disk 段数 | 正文 event/range/text/顺序 | 最大 inline/disk 包字符 |
| --- | --- | --- | --- |
| 42k 字符 / 24k 估算 token | 13 / 13 | 不相同 | 31,135 / 33,942 |
| 80k 字符 / 40k 估算 token | 13 / 13 | 全部相同 | 31,135 / 34,519 |

80k 配置的放置字符阈值为 69,200，远高于实际包大小。但这个结果**不能豁免上面的固定预算工具证据回归**；两项测试回答不同问题。不得继续通过扩容或删断言让 `test_gdpevo_context` 变绿。

## Verification

- Tests（本审查执行）：`test_memory_feedback_text`、`test_memory_summary_repair`、disk/inline 等价方法，共 **20/20 通过，5.445 秒**。
- Tests（主代理结果，已读日志）：GDPevo **32/33 通过，1 项失败**；独立诊断复现其首个容量拒绝点，暂不签字通过。
- `git diff --check`：通过。
- `node docs/blueprint/build.mjs verify`：通过，v1.8.1 / 上述 SHA。
- Lint：仓库未配置本次 Python 独立 lint 入口，未宣称通过。
- TypeCheck：仓库未配置 Python 静态类型检查入口，未宣称通过；完整 Python 检查由主代理执行。
- 探针首跑遗漏临时 Store 的 context fixture，被 `NOT_FOUND` 正常拒绝；补齐 fixture 后完成，不是产品缺陷。
- 没有重复全套检查、执行 mutation、调用模型、访问网络或读取 test001/gold。

## 同源共享修复后的复审

本节追加于相同任务，不删除或改写前述失败事实。复审源码 `evidence.py` SHA256：`e868f0c07faa39c3e91496df9a2cebe57a293600ba4d6e58e1f6a4d6c073764b`；反馈测试 SHA256：`e9aabef565bbbbd8bfc7e949ad862ba3af5f5c48b6eba8db74197cd70e0c77ef`。

**新判定：产品职责边界复审通过，未发现该冻结源码中需要继续修复的问题。** 这仅确认本次框架供证修复的范围和行为，不表示真实模型学习周期、候选收益或发布成功。

### Findings (fixed)

- 前述重复高优先级正文问题由实施者修复，本审查未改源代码。`evidence.py:585-614` 按 `(episode_id,event_id)` 将 full/reason 组成一个 feedback 单元；普通调用仍沿原 `(episode_id,call_id)` 分组与成员查找分支，不引入业务类别排名。
- `evidence.py:686-706` 仅对已选中的同源 full/reason 二元组共享一次 `_role_width`。full 默认提供实际 `,"reason":` 字段前的原文；若超过一半额度，则改取原有 outcome 字段的精确子范围，不替换或重造它的值。它使用已由 Feedback schema 保证存在的固定 outcome 枚举 `pass/fail/unknown`，不是读取 reason 内部业务 JSON 作归因。
- 字符额度再小时，`:699-706` 给 reason 留下正宽度；`:722-728` 只在独立目录容量允许时提供 full 的原始 locator；`:747` 跳过无法形成正文的 full 占位。没有插入空正文、免费目录或伪造完整覆盖。
- `allowed_refs` 在候选选择和单元成员处继续过滤（`:650-663,682-683,599-600`）。只允许单一视图时不进入二视图共享分支，既不暗拉 sibling，也不改变该视图原来的片段算法。
- 原索引 full/reason 的身份、原文、hash 和回读保持。所有追加 fragment/catalog 来源元数据仍进入 `_fits` 的真实序列化长度及 token 估计，旧包复验、原事件分母、精确引文拒绝保持。

### Findings (not fixed)

- **无新增产品缺陷。** 前版订单证据缺失已由原 42k 验收恢复证明；未扩容该检查或减少类别断言。
- 收尾文档同步属于主代理待完成项：复审当时总纲 JSON 仍保留 `integration-pending` 及首次订单回归说明，尚未写入新共享选材规则；backend spec 与当前 task design 已同步。主代理已安排将新规则与最终机制验收回填权威 JSON、重新生成并 `verify`。不能只更新 generated HTML 或覆盖旧失败历史；本审查不改总纲。
- 12k 容量、quote 精确性及选材回归通过，仍不能推导实盘模型会正确引用或生成有用 Skill。真实回放结果需另报。

### Verification

- 本次独立执行 `PYTHONPATH=src:tests .venv/bin/python -m unittest test_memory_feedback_text test_gdpevo_context -q`：**26/26 通过，8.435 秒**。其中 21 项反馈边界覆盖共享宽度、角色上限、长元数据、半额边界、1 字符宽度/零目录、单视图限制及旧来源；5 项 GDPevo 供证检查保留原预算及断言。
- `git diff --check`：通过。
- 复审中的 `node docs/blueprint/build.mjs verify`：通过，v1.8.1，JSON SHA `d1c013c91e7d034ede56d838fa553733d19ee8320942805cf235d69e025226d3`。该 SHA 是最终状态回填前的生成一致性检查；主代理须对最终 JSON 再 verify。
- 主代理随后报告完整 `test_*.py` **391/391 通过，85.055 秒**；本审查未重复全套，也未将其记为自己执行。
- Lint/TypeCheck：仍无仓库声明的 Python 独立入口，不把 unittest、compile 或 diff 检查称为静态类型检查通过。
- 本次没有源代码、测试、总纲修改，没有 mutation、网络或真实模型调用。
