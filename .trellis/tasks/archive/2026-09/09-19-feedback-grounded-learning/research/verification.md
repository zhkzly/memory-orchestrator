# v1.10.0 验证记录

## 结论

原始轨迹分层没有重写。修复位于其上层：被拒目标保留原 criterion feedback；artifact 与 Feedback 以相同 digest 关联；task-family/cross-family 经验和 `necessity.proceed` 必须引用闭合执行证据；新 ADD Skill 必须提供机器 selector，选择时 exclusion 优先。

## 真实金标

- `gdpevo_bad_task_family_extraction.json`：复制真实 `extract_v1/diagnose_v1` 返回及其 packet。原 task-family 草稿只引用 task 与 scoring text；当前分别以 `reusable_evidence_incomplete` / `necessity_invalid` 拒绝。
- 同一 packet 补齐 task、完整 action/result 和 environment output，但不提供 artifact-feedback resource link 时仍拒绝；加入同版本 link 后通过结构充分性检查。通过不代表语义或因果正确。
- `gdpevo_original_criterion_feedback.json`：复制真实 frozen plan、callback return、criterion Feedback 与 TaskAssessment。回流后保留五个原失败评分组；篡改 score 触发 `feedback_binding`。
- 真实候选 Skill 派生 selector：train_001 命中；train_004 同时命中 `allocation desk` 和 `transfer`，以 `scope_exclusion` 排除。selector 是本次修复后的显式字段，不声称旧模型当时已经生成。

## Framework 与 LLM 分工

| 环节 | Framework 已执行 | LLM 仍负责 |
|---|---|---|
| 反馈 | 复验原 assessment/criterion、保存原 reason、绑定 artifact digest | 解读评分细项与轨迹含义 |
| 证据 | 验证 task、完整 call pair、digest-bound output/feedback 与引用白名单 | 选择语义相关的调用，提出观察和假设 |
| 经验/归因 | 不完整链进入同一修复预算；允许 instance/needs_evidence/abstain | 决定经验内容、适用范围、行为差异和替代解释 |
| Skill | ADD/scope重写必须有 selector；选择器执行 exclude/require | 给出有区分度的短语及 Skill 步骤 |
| 效果 | 仍由冻结 case/evaluator/发布门判断 | 不允许自评替代结果 |

## 执行证据

- 新行为定向检查：真实坏提取、诊断、criterion 回流、artifact 关系、selector 与修复回路均通过。
- 完整回归：`PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p 'test_memory_*.py' -q` → **383/383，79.807s，exit 0**。
- `python3 -m compileall -q src/memory_orchestrator examples/memory_evolution` → exit 0。
- 总纲 v1.10.0 `check/render/verify` → exit 0；packaged prompt/schema 与源精确一致。
- 最终总纲 SHA-256：`d39a35d4b9d111d35f341353b6401efc9a436f291fb48e67dea5b797d39f2ce8`；HTML 370575 bytes，context 17095 bytes。
- 官方 mutation license：22 次成功覆盖 evaluation、evidence、learning extraction/diagnosis/repair/link、context include/exclude、candidate selector、sampling inline/disk、demo 与 contract；另有 4 次被拒的旧验收保留，随后换用能区分错误的检查。
- `git diff --check` → exit 0。

## 未完成的效果证据

本轮没有新的真实 Teacher 或 benchmark 数字。首次沙箱探测返回 `Operation not permitted`；按规则在允许环境重试后，`localhost:8317` 明确 `Could not connect to server`，说明当时无服务监听，不是产品失败。未切换到其它模型或网络端点。

因此可以声称：旧坏草稿会被拒绝/补证、反馈细项不再丢失、声明的机器排除边界会执行。不能声称：新 prompt 已由真实模型稳定遵守、生成 Skill 已提升 GDPevo，或已定位 train001 各订单的隐藏正确规则。
