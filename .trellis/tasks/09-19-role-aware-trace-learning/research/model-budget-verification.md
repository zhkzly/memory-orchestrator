# 模型累计预算实现证据

本轮所有权：`src/memory_orchestrator/model.py`、`tests/test_memory_model_budget.py`。仅使用注入计数器和 FakeCall；真实输入派生自 `tests/fixtures/gdpevo_context_train001.json`。没有真实模型、网络、benchmark 或 commit。

## 初始 RED

命令：

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python -m unittest test_memory_model_budget.ModelBudgetTests.test_zero_input_token_quota_rejects_before_any_transport test_memory_model_budget.ModelBudgetTests.test_zero_output_quota_rejects_before_any_transport -v
```

退出码 `1`，2 项实际拒绝路径均失败：

```text
test_zero_input_token_quota_rejects_before_any_transport ... FAIL
test_zero_output_quota_rejects_before_any_transport ... FAIL
AssertionError: DomainError not raised
Ran 2 tests in 0.116s
FAILED (failures=2)
```

输入使用真实136事件fixture经现有 `index_episodes/build_packet/feedback_view` 构造的提取材料。两个失败分别证明现有构造器丢弃 `token_budget` 后，累计输入/输出设为0仍实际进入 transport，未以预期的预算错误拒绝。不是因为调用未实现的新方法而得到假红。

按五镜头核对：View/Prompt 已存在真实提取输入；Skill 不涉及本确定性拒绝；Code 是预算字段未消费；Feedback 测试明确点名了未拒绝。修改边界仍限模型统一调用层，新局部整理编排由根代理消费。

## 实现与恢复后 GREEN

- 保留 `generate(prompt_id, inputs, *, check=None)`；新增可注入计数器及与真实调用共用 `_render` 的纯 `preview`。
- 全局和按 prompt_id 的单次/累计输入、累计输出、调用数共同准入。输出 cap 与实际 transport 参数一致；输出先预留，输入/输出分别按合法 provider 报告结算。未知维度保留预留而不填进实测 usage。
- 估计偏低但实际仍在已配置额度内时正常结算；真正超过额度才记 overrun 并阻止后续调用。这个决策修正了勘察稿中过于严格的“高于预留即停止”表述，已与根代理确认。
- 追加验收找到并修复“修复前 counter 失败丢掉上次 usage”：先出现 `KeyError: usage`（单项 exit 1），后统一错误封装保存已有 attempts/usage，再恢复 GREEN。

恢复后命令：

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python -m unittest test_memory_model_budget test_memory_model -v
```

退出码 0，原始结束输出：

```text
Ran 40 tests in 0.346s
OK
```

25 个新增预算用例与 15 个原模型回归通过；两个文件 AST.parse 均通过，限定文件 git diff --check exit 0。此处没有运行/声明全仓回归。

最终源码 SHA-256：

- model.py：`ebeca19f47c1f887861c9f0ed1acc0bc63cf3f3ca89ed2a6834e40d61084c356`
- test_memory_model_budget.py：`aea04b30e4dd789be3ba3f95cb631e93f13ae7c1b21304f63200e8a7f1815aff`

## 官方 mutation 证据

实施前用已有累计字符拒绝路径获得 model.py 执照。实施后 18 条独立绑定逐项执行官方 `/home/kelong/ai-workbench/tools/mutation_license.py`；每项原样→注错→恢复分别为 GREEN→RED→GREEN，全部 exit 0、所有目标文件逐字节 hash 恢复。测试只读已冻结 fixture 和契约；变体窗口由根代理协调，无并行依赖突变。

| 绑定 | 官方退出码 | 精确恢复 |
| --- | --- | --- |
| global-input | 0 | 是 |
| global-output | 0 | 是 |
| request-input | 0 | 是 |
| stage-request-input | 0 | 是 |
| stage-input | 0 | 是 |
| stage-output | 0 | 是 |
| stage-calls | 0 | 是 |
| transport-output-cap | 0 | 是 |
| repair-full-input | 0 | 是 |
| full-default-input | 0 | 是 |
| unknown-not-zero | 0 | 是 |
| reconcile-known | 0 | 是 |
| actual-overrun | 0 | 是 |
| measurement-separation | 0 | 是 |
| missing-stage | 0 | 是 |
| repair-error-usage | 0 | 是 |
| unknown-budget-key | 0 | 是 |
| frozen-budget-config | 0 | 是 |

下面保留全部命令、实际注入、退出码、原始 stdout/stderr 与三阶段测试输出，便于复跑。初始执照也保留原始命令和恢复 hash。

<details>
<summary>初始执照原始记录</summary>

```json
{
  "command": [
    "python3",
    "/home/kelong/ai-workbench/tools/mutation_license.py",
    "--tests",
    "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python -m unittest test_memory_model.ModelTests.test_cumulative_budget_and_missing_fields_fail_before_network -v",
    "--target",
    "src/memory_orchestrator/model.py",
    "--mutate",
    "python3 -c 'from pathlib import Path; p=Path('\"'\"'src/memory_orchestrator/model.py'\"'\"'); s=p.read_text(); a='\"'\"'self.input_chars + count > self.limits[\"max_total_input_chars\"]'\"'\"'; assert s.count(a)==1; p.write_text(s.replace(a,'\"'\"'False'\"'\"'))'"
  ],
  "before_sha256": "d3b8184116485e541c8a6cf85005426aafd1c3cde6742a37ea6723904927aef0",
  "after_sha256": "d3b8184116485e541c8a6cf85005426aafd1c3cde6742a37ea6723904927aef0",
  "exit_code": 0,
  "stdout": "✅ 执照发放:src/memory_orchestrator/model.py 注入错误时变红、按快照还原后回绿——该验收有资格存在。\n",
  "stderr": ""
}
```

</details>

<details>
<summary>18 条独立绑定执照原始记录</summary>

```json
[
  {
    "name": "global-input",
    "target": "src/memory_orchestrator/model.py",
    "old": "(\"global\", \"input_tokens\", self._token_spent[\"input\"], estimated, config[\"max_total_input_tokens\"])",
    "new": "(\"global\", \"input_tokens\", self._token_spent[\"input\"], estimated, 10**20)",
    "test": "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python -m unittest test_memory_model_budget.ModelBudgetTests.test_global_input_cumulative_limit_and_preview_are_rechecked -v",
    "command": [
      "python3",
      "/home/kelong/ai-workbench/tools/mutation_license.py",
      "--tests",
      "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python -m unittest test_memory_model_budget.ModelBudgetTests.test_global_input_cumulative_limit_and_preview_are_rechecked -v >> /tmp/model-budget-mutations/global-input.tests.txt 2>&1",
      "--target",
      "src/memory_orchestrator/model.py",
      "--mutate",
      "python3 -c 'from pathlib import Path; p=Path('\"'\"'src/memory_orchestrator/model.py'\"'\"'); s=p.read_text(); old='\"'\"'(\"global\", \"input_tokens\", self._token_spent[\"input\"], estimated, config[\"max_total_input_tokens\"])'\"'\"'; assert s.count(old)==1; p.write_text(s.replace(old,'\"'\"'(\"global\", \"input_tokens\", self._token_spent[\"input\"], estimated, 10**20)'\"'\"'))'"
    ],
    "before_sha256": "ebeca19f47c1f887861c9f0ed1acc0bc63cf3f3ca89ed2a6834e40d61084c356",
    "after_sha256": "ebeca19f47c1f887861c9f0ed1acc0bc63cf3f3ca89ed2a6834e40d61084c356",
    "exit_code": 0,
    "stdout": "✅ 执照发放:src/memory_orchestrator/model.py 注入错误时变红、按快照还原后回绿——该验收有资格存在。\n",
    "stderr": "",
    "test_output": "test_global_input_cumulative_limit_and_preview_are_rechecked (test_memory_model_budget.ModelBudgetTests.test_global_input_cumulative_limit_and_preview_are_rechecked) ... ok\n\n----------------------------------------------------------------------\nRan 1 test in 0.113s\n\nOK\ntest_global_input_cumulative_limit_and_preview_are_rechecked (test_memory_model_budget.ModelBudgetTests.test_global_input_cumulative_limit_and_preview_are_rechecked) ... FAIL\n\n======================================================================\nFAIL: test_global_input_cumulative_limit_and_preview_are_rechecked (test_memory_model_budget.ModelBudgetTests.test_global_input_cumulative_limit_and_preview_are_rechecked)\n----------------------------------------------------------------------\nTraceback (most recent call last):\n  File \"/home/kelong/orca/workspaces/memory-orchestrator/codex-add-vault-maintenance-controller/tests/test_memory_model_budget.py\", line 109, in test_global_input_cumulative_limit_and_preview_are_rechecked\n    self.assertFalse(model.preview(\"extract_v1\", self.extract_inputs)[\"fits\"])\n    ~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\nAssertionError: True is not false\n\n----------------------------------------------------------------------\nRan 1 test in 0.114s\n\nFAILED (failures=1)\ntest_global_input_cumulative_limit_and_preview_are_rechecked (test_memory_model_budget.ModelBudgetTests.test_global_input_cumulative_limit_and_preview_are_rechecked) ... ok\n\n----------------------------------------------------------------------\nRan 1 test in 0.116s\n\nOK\n"
  },
  {
    "name": "global-output",
    "target": "src/memory_orchestrator/model.py",
    "old": "(\"global\", \"output_tokens\", self._token_spent[\"output\"], cap, config[\"max_total_output_tokens\"])",
    "new": "(\"global\", \"output_tokens\", self._token_spent[\"output\"], cap, 10**20)",
    "test": "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python -m unittest test_memory_model_budget.ModelBudgetTests.test_global_output_reservation_survives_unknown_usage -v",
    "command": [
      "python3",
      "/home/kelong/ai-workbench/tools/mutation_license.py",
      "--tests",
      "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python -m unittest test_memory_model_budget.ModelBudgetTests.test_global_output_reservation_survives_unknown_usage -v >> /tmp/model-budget-mutations/global-output.tests.txt 2>&1",
      "--target",
      "src/memory_orchestrator/model.py",
      "--mutate",
      "python3 -c 'from pathlib import Path; p=Path('\"'\"'src/memory_orchestrator/model.py'\"'\"'); s=p.read_text(); old='\"'\"'(\"global\", \"output_tokens\", self._token_spent[\"output\"], cap, config[\"max_total_output_tokens\"])'\"'\"'; assert s.count(old)==1; p.write_text(s.replace(old,'\"'\"'(\"global\", \"output_tokens\", self._token_spent[\"output\"], cap, 10**20)'\"'\"'))'"
    ],
    "before_sha256": "ebeca19f47c1f887861c9f0ed1acc0bc63cf3f3ca89ed2a6834e40d61084c356",
    "after_sha256": "ebeca19f47c1f887861c9f0ed1acc0bc63cf3f3ca89ed2a6834e40d61084c356",
    "exit_code": 0,
    "stdout": "✅ 执照发放:src/memory_orchestrator/model.py 注入错误时变红、按快照还原后回绿——该验收有资格存在。\n",
    "stderr": "",
    "test_output": "test_global_output_reservation_survives_unknown_usage (test_memory_model_budget.ModelBudgetTests.test_global_output_reservation_survives_unknown_usage) ... ok\n\n----------------------------------------------------------------------\nRan 1 test in 0.114s\n\nOK\ntest_global_output_reservation_survives_unknown_usage (test_memory_model_budget.ModelBudgetTests.test_global_output_reservation_survives_unknown_usage) ... FAIL\n\n======================================================================\nFAIL: test_global_output_reservation_survives_unknown_usage (test_memory_model_budget.ModelBudgetTests.test_global_output_reservation_survives_unknown_usage)\n----------------------------------------------------------------------\nTraceback (most recent call last):\n  File \"/home/kelong/orca/workspaces/memory-orchestrator/codex-add-vault-maintenance-controller/tests/test_memory_model_budget.py\", line 127, in test_global_output_reservation_survives_unknown_usage\n    with self.assertRaises(DomainError): model.generate(\"extract_v1\", self.extract_inputs)\n         ~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^\nAssertionError: DomainError not raised\n\n----------------------------------------------------------------------\nRan 1 test in 0.114s\n\nFAILED (failures=1)\ntest_global_output_reservation_survives_unknown_usage (test_memory_model_budget.ModelBudgetTests.test_global_output_reservation_survives_unknown_usage) ... ok\n\n----------------------------------------------------------------------\nRan 1 test in 0.113s\n\nOK\n"
  },
  {
    "name": "request-input",
    "target": "src/memory_orchestrator/model.py",
    "old": "(\"request\", \"input_tokens\", 0, estimated, config[\"max_input_tokens\"])",
    "new": "(\"request\", \"input_tokens\", 0, estimated, 10**20)",
    "test": "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python -m unittest test_memory_model_budget.ModelBudgetTests.test_global_single_request_token_limit_includes_full_input -v",
    "command": [
      "python3",
      "/home/kelong/ai-workbench/tools/mutation_license.py",
      "--tests",
      "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python -m unittest test_memory_model_budget.ModelBudgetTests.test_global_single_request_token_limit_includes_full_input -v >> /tmp/model-budget-mutations/request-input.tests.txt 2>&1",
      "--target",
      "src/memory_orchestrator/model.py",
      "--mutate",
      "python3 -c 'from pathlib import Path; p=Path('\"'\"'src/memory_orchestrator/model.py'\"'\"'); s=p.read_text(); old='\"'\"'(\"request\", \"input_tokens\", 0, estimated, config[\"max_input_tokens\"])'\"'\"'; assert s.count(old)==1; p.write_text(s.replace(old,'\"'\"'(\"request\", \"input_tokens\", 0, estimated, 10**20)'\"'\"'))'"
    ],
    "before_sha256": "ebeca19f47c1f887861c9f0ed1acc0bc63cf3f3ca89ed2a6834e40d61084c356",
    "after_sha256": "ebeca19f47c1f887861c9f0ed1acc0bc63cf3f3ca89ed2a6834e40d61084c356",
    "exit_code": 0,
    "stdout": "✅ 执照发放:src/memory_orchestrator/model.py 注入错误时变红、按快照还原后回绿——该验收有资格存在。\n",
    "stderr": "",
    "test_output": "test_global_single_request_token_limit_includes_full_input (test_memory_model_budget.ModelBudgetTests.test_global_single_request_token_limit_includes_full_input) ... ok\n\n----------------------------------------------------------------------\nRan 1 test in 0.110s\n\nOK\ntest_global_single_request_token_limit_includes_full_input (test_memory_model_budget.ModelBudgetTests.test_global_single_request_token_limit_includes_full_input) ... FAIL\n\n======================================================================\nFAIL: test_global_single_request_token_limit_includes_full_input (test_memory_model_budget.ModelBudgetTests.test_global_single_request_token_limit_includes_full_input)\n----------------------------------------------------------------------\nTraceback (most recent call last):\n  File \"/home/kelong/orca/workspaces/memory-orchestrator/codex-add-vault-maintenance-controller/tests/test_memory_model_budget.py\", line 116, in test_global_single_request_token_limit_includes_full_input\n    self.assertFalse(model.preview(\"extract_v1\", self.extract_inputs)[\"fits\"])\n    ~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\nAssertionError: True is not false\n\n----------------------------------------------------------------------\nRan 1 test in 0.108s\n\nFAILED (failures=1)\ntest_global_single_request_token_limit_includes_full_input (test_memory_model_budget.ModelBudgetTests.test_global_single_request_token_limit_includes_full_input) ... ok\n\n----------------------------------------------------------------------\nRan 1 test in 0.111s\n\nOK\n"
  },
  {
    "name": "stage-request-input",
    "target": "src/memory_orchestrator/model.py",
    "old": "(\"stage_request\", \"input_tokens\", 0, estimated, stage[\"max_input_tokens\"])",
    "new": "(\"stage_request\", \"input_tokens\", 0, estimated, 10**20)",
    "test": "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python -m unittest test_memory_model_budget.ModelBudgetTests.test_repair_recounts_original_rejected_output_and_diagnostics -v",
    "command": [
      "python3",
      "/home/kelong/ai-workbench/tools/mutation_license.py",
      "--tests",
      "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python -m unittest test_memory_model_budget.ModelBudgetTests.test_repair_recounts_original_rejected_output_and_diagnostics -v >> /tmp/model-budget-mutations/stage-request-input.tests.txt 2>&1",
      "--target",
      "src/memory_orchestrator/model.py",
      "--mutate",
      "python3 -c 'from pathlib import Path; p=Path('\"'\"'src/memory_orchestrator/model.py'\"'\"'); s=p.read_text(); old='\"'\"'(\"stage_request\", \"input_tokens\", 0, estimated, stage[\"max_input_tokens\"])'\"'\"'; assert s.count(old)==1; p.write_text(s.replace(old,'\"'\"'(\"stage_request\", \"input_tokens\", 0, estimated, 10**20)'\"'\"'))'"
    ],
    "before_sha256": "ebeca19f47c1f887861c9f0ed1acc0bc63cf3f3ca89ed2a6834e40d61084c356",
    "after_sha256": "ebeca19f47c1f887861c9f0ed1acc0bc63cf3f3ca89ed2a6834e40d61084c356",
    "exit_code": 0,
    "stdout": "✅ 执照发放:src/memory_orchestrator/model.py 注入错误时变红、按快照还原后回绿——该验收有资格存在。\n",
    "stderr": "",
    "test_output": "test_repair_recounts_original_rejected_output_and_diagnostics (test_memory_model_budget.ModelBudgetTests.test_repair_recounts_original_rejected_output_and_diagnostics) ... ok\n\n----------------------------------------------------------------------\nRan 1 test in 0.112s\n\nOK\ntest_repair_recounts_original_rejected_output_and_diagnostics (test_memory_model_budget.ModelBudgetTests.test_repair_recounts_original_rejected_output_and_diagnostics) ... FAIL\n\n======================================================================\nFAIL: test_repair_recounts_original_rejected_output_and_diagnostics (test_memory_model_budget.ModelBudgetTests.test_repair_recounts_original_rejected_output_and_diagnostics)\n----------------------------------------------------------------------\nTraceback (most recent call last):\n  File \"/home/kelong/orca/workspaces/memory-orchestrator/codex-add-vault-maintenance-controller/tests/test_memory_model_budget.py\", line 165, in test_repair_recounts_original_rejected_output_and_diagnostics\n    with self.assertRaises(DomainError) as caught: model.generate(\"extract_v1\", self.extract_inputs)\n         ~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^\nAssertionError: DomainError not raised\n\n----------------------------------------------------------------------\nRan 1 test in 0.110s\n\nFAILED (failures=1)\ntest_repair_recounts_original_rejected_output_and_diagnostics (test_memory_model_budget.ModelBudgetTests.test_repair_recounts_original_rejected_output_and_diagnostics) ... ok\n\n----------------------------------------------------------------------\nRan 1 test in 0.108s\n\nOK\n"
  },
  {
    "name": "stage-input",
    "target": "src/memory_orchestrator/model.py",
    "old": "(\"stage\", \"input_tokens\", spent[\"input\"], estimated, stage[\"max_total_input_tokens\"])",
    "new": "(\"stage\", \"input_tokens\", spent[\"input\"], estimated, 10**20)",
    "test": "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python -m unittest test_memory_model_budget.ModelBudgetTests.test_stage_input_total_cannot_borrow_other_stage_allowance -v",
    "command": [
      "python3",
      "/home/kelong/ai-workbench/tools/mutation_license.py",
      "--tests",
      "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python -m unittest test_memory_model_budget.ModelBudgetTests.test_stage_input_total_cannot_borrow_other_stage_allowance -v >> /tmp/model-budget-mutations/stage-input.tests.txt 2>&1",
      "--target",
      "src/memory_orchestrator/model.py",
      "--mutate",
      "python3 -c 'from pathlib import Path; p=Path('\"'\"'src/memory_orchestrator/model.py'\"'\"'); s=p.read_text(); old='\"'\"'(\"stage\", \"input_tokens\", spent[\"input\"], estimated, stage[\"max_total_input_tokens\"])'\"'\"'; assert s.count(old)==1; p.write_text(s.replace(old,'\"'\"'(\"stage\", \"input_tokens\", spent[\"input\"], estimated, 10**20)'\"'\"'))'"
    ],
    "before_sha256": "ebeca19f47c1f887861c9f0ed1acc0bc63cf3f3ca89ed2a6834e40d61084c356",
    "after_sha256": "ebeca19f47c1f887861c9f0ed1acc0bc63cf3f3ca89ed2a6834e40d61084c356",
    "exit_code": 0,
    "stdout": "✅ 执照发放:src/memory_orchestrator/model.py 注入错误时变红、按快照还原后回绿——该验收有资格存在。\n",
    "stderr": "",
    "test_output": "test_stage_input_total_cannot_borrow_other_stage_allowance (test_memory_model_budget.ModelBudgetTests.test_stage_input_total_cannot_borrow_other_stage_allowance) ... ok\n\n----------------------------------------------------------------------\nRan 1 test in 0.116s\n\nOK\ntest_stage_input_total_cannot_borrow_other_stage_allowance (test_memory_model_budget.ModelBudgetTests.test_stage_input_total_cannot_borrow_other_stage_allowance) ... ERROR\n\n======================================================================\nERROR: test_stage_input_total_cannot_borrow_other_stage_allowance (test_memory_model_budget.ModelBudgetTests.test_stage_input_total_cannot_borrow_other_stage_allowance)\n----------------------------------------------------------------------\nTraceback (most recent call last):\n  File \"/home/kelong/orca/workspaces/memory-orchestrator/codex-add-vault-maintenance-controller/tests/test_memory_model_budget.py\", line 142, in test_stage_input_total_cannot_borrow_other_stage_allowance\n    model.generate(\"diagnose_v1\", inputs(\"diagnose_v1\"))\n    ~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\n  File \"/home/kelong/orca/workspaces/memory-orchestrator/codex-add-vault-maintenance-controller/src/memory_orchestrator/model.py\", line 267, in generate\n    fail(\"model_budget_exhausted\", \"Call or input/output budget exhausted before the next attempt.\",\n    ~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\n         requested_input_chars=count, limits=copy.deepcopy(self.limits), preview=inspected)\n         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\n  File \"/home/kelong/orca/workspaces/memory-orchestrator/codex-add-vault-maintenance-controller/src/memory_orchestrator/model.py\", line 255, in fail\n    raise DomainError(code, message, {\"prompt_id\": prompt_id, \"usage\": copy.deepcopy(usage),\n        \"attempts\": copy.deepcopy(attempts), \"calls_consumed\": self.calls,\n        \"input_chars_consumed\": self.input_chars, **details})\nmemory_orchestrator.schemas.DomainError: Call or input/output budget exhausted before the next attempt.\n\n----------------------------------------------------------------------\nRan 1 test in 0.115s\n\nFAILED (errors=1)\ntest_stage_input_total_cannot_borrow_other_stage_allowance (test_memory_model_budget.ModelBudgetTests.test_stage_input_total_cannot_borrow_other_stage_allowance) ... ok\n\n----------------------------------------------------------------------\nRan 1 test in 0.115s\n\nOK\n"
  },
  {
    "name": "stage-output",
    "target": "src/memory_orchestrator/model.py",
    "old": "(\"stage\", \"output_tokens\", spent[\"output\"], cap, stage[\"max_total_output_tokens\"])",
    "new": "(\"stage\", \"output_tokens\", spent[\"output\"], cap, 10**20)",
    "test": "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python -m unittest test_memory_model_budget.ModelBudgetTests.test_stage_output_total_counts_unknown_completion -v",
    "command": [
      "python3",
      "/home/kelong/ai-workbench/tools/mutation_license.py",
      "--tests",
      "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python -m unittest test_memory_model_budget.ModelBudgetTests.test_stage_output_total_counts_unknown_completion -v >> /tmp/model-budget-mutations/stage-output.tests.txt 2>&1",
      "--target",
      "src/memory_orchestrator/model.py",
      "--mutate",
      "python3 -c 'from pathlib import Path; p=Path('\"'\"'src/memory_orchestrator/model.py'\"'\"'); s=p.read_text(); old='\"'\"'(\"stage\", \"output_tokens\", spent[\"output\"], cap, stage[\"max_total_output_tokens\"])'\"'\"'; assert s.count(old)==1; p.write_text(s.replace(old,'\"'\"'(\"stage\", \"output_tokens\", spent[\"output\"], cap, 10**20)'\"'\"'))'"
    ],
    "before_sha256": "ebeca19f47c1f887861c9f0ed1acc0bc63cf3f3ca89ed2a6834e40d61084c356",
    "after_sha256": "ebeca19f47c1f887861c9f0ed1acc0bc63cf3f3ca89ed2a6834e40d61084c356",
    "exit_code": 0,
    "stdout": "✅ 执照发放:src/memory_orchestrator/model.py 注入错误时变红、按快照还原后回绿——该验收有资格存在。\n",
    "stderr": "",
    "test_output": "test_stage_output_total_counts_unknown_completion (test_memory_model_budget.ModelBudgetTests.test_stage_output_total_counts_unknown_completion) ... ok\n\n----------------------------------------------------------------------\nRan 1 test in 0.111s\n\nOK\ntest_stage_output_total_counts_unknown_completion (test_memory_model_budget.ModelBudgetTests.test_stage_output_total_counts_unknown_completion) ... FAIL\n\n======================================================================\nFAIL: test_stage_output_total_counts_unknown_completion (test_memory_model_budget.ModelBudgetTests.test_stage_output_total_counts_unknown_completion)\n----------------------------------------------------------------------\nTraceback (most recent call last):\n  File \"/home/kelong/orca/workspaces/memory-orchestrator/codex-add-vault-maintenance-controller/tests/test_memory_model_budget.py\", line 155, in test_stage_output_total_counts_unknown_completion\n    with self.assertRaises(DomainError): model.generate(\"extract_v1\", self.extract_inputs)\n         ~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^\nAssertionError: DomainError not raised\n\n----------------------------------------------------------------------\nRan 1 test in 0.115s\n\nFAILED (failures=1)\ntest_stage_output_total_counts_unknown_completion (test_memory_model_budget.ModelBudgetTests.test_stage_output_total_counts_unknown_completion) ... ok\n\n----------------------------------------------------------------------\nRan 1 test in 0.112s\n\nOK\n"
  },
  {
    "name": "stage-calls",
    "target": "src/memory_orchestrator/model.py",
    "old": "(\"stage\", \"calls\", spent[\"calls\"], 1, stage[\"max_calls\"])",
    "new": "(\"stage\", \"calls\", spent[\"calls\"], 1, 10**20)",
    "test": "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python -m unittest test_memory_model_budget.ModelBudgetTests.test_stage_call_limit_counts_repeated_generate -v",
    "command": [
      "python3",
      "/home/kelong/ai-workbench/tools/mutation_license.py",
      "--tests",
      "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python -m unittest test_memory_model_budget.ModelBudgetTests.test_stage_call_limit_counts_repeated_generate -v >> /tmp/model-budget-mutations/stage-calls.tests.txt 2>&1",
      "--target",
      "src/memory_orchestrator/model.py",
      "--mutate",
      "python3 -c 'from pathlib import Path; p=Path('\"'\"'src/memory_orchestrator/model.py'\"'\"'); s=p.read_text(); old='\"'\"'(\"stage\", \"calls\", spent[\"calls\"], 1, stage[\"max_calls\"])'\"'\"'; assert s.count(old)==1; p.write_text(s.replace(old,'\"'\"'(\"stage\", \"calls\", spent[\"calls\"], 1, 10**20)'\"'\"'))'"
    ],
    "before_sha256": "ebeca19f47c1f887861c9f0ed1acc0bc63cf3f3ca89ed2a6834e40d61084c356",
    "after_sha256": "ebeca19f47c1f887861c9f0ed1acc0bc63cf3f3ca89ed2a6834e40d61084c356",
    "exit_code": 0,
    "stdout": "✅ 执照发放:src/memory_orchestrator/model.py 注入错误时变红、按快照还原后回绿——该验收有资格存在。\n",
    "stderr": "",
    "test_output": "test_stage_call_limit_counts_repeated_generate (test_memory_model_budget.ModelBudgetTests.test_stage_call_limit_counts_repeated_generate) ... ok\n\n----------------------------------------------------------------------\nRan 1 test in 0.113s\n\nOK\ntest_stage_call_limit_counts_repeated_generate (test_memory_model_budget.ModelBudgetTests.test_stage_call_limit_counts_repeated_generate) ... FAIL\n\n======================================================================\nFAIL: test_stage_call_limit_counts_repeated_generate (test_memory_model_budget.ModelBudgetTests.test_stage_call_limit_counts_repeated_generate)\n----------------------------------------------------------------------\nTraceback (most recent call last):\n  File \"/home/kelong/orca/workspaces/memory-orchestrator/codex-add-vault-maintenance-controller/tests/test_memory_model_budget.py\", line 148, in test_stage_call_limit_counts_repeated_generate\n    with self.assertRaises(DomainError): model.generate(\"extract_v1\", self.extract_inputs)\n         ~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^\nAssertionError: DomainError not raised\n\n----------------------------------------------------------------------\nRan 1 test in 0.113s\n\nFAILED (failures=1)\ntest_stage_call_limit_counts_repeated_generate (test_memory_model_budget.ModelBudgetTests.test_stage_call_limit_counts_repeated_generate) ... ok\n\n----------------------------------------------------------------------\nRan 1 test in 0.111s\n\nOK\n"
  },
  {
    "name": "transport-output-cap",
    "target": "src/memory_orchestrator/model.py",
    "old": "\"max_output_tokens\": inspected[\"effective_output_cap\"]",
    "new": "\"max_output_tokens\": self.limits[\"max_output_tokens\"]",
    "test": "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python -m unittest test_memory_model_budget.ModelBudgetTests.test_stage_output_cap_is_enforced_in_actual_transport -v",
    "command": [
      "python3",
      "/home/kelong/ai-workbench/tools/mutation_license.py",
      "--tests",
      "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python -m unittest test_memory_model_budget.ModelBudgetTests.test_stage_output_cap_is_enforced_in_actual_transport -v >> /tmp/model-budget-mutations/transport-output-cap.tests.txt 2>&1",
      "--target",
      "src/memory_orchestrator/model.py",
      "--mutate",
      "python3 -c 'from pathlib import Path; p=Path('\"'\"'src/memory_orchestrator/model.py'\"'\"'); s=p.read_text(); old='\"'\"'\"max_output_tokens\": inspected[\"effective_output_cap\"]'\"'\"'; assert s.count(old)==1; p.write_text(s.replace(old,'\"'\"'\"max_output_tokens\": self.limits[\"max_output_tokens\"]'\"'\"'))'"
    ],
    "before_sha256": "ebeca19f47c1f887861c9f0ed1acc0bc63cf3f3ca89ed2a6834e40d61084c356",
    "after_sha256": "ebeca19f47c1f887861c9f0ed1acc0bc63cf3f3ca89ed2a6834e40d61084c356",
    "exit_code": 0,
    "stdout": "✅ 执照发放:src/memory_orchestrator/model.py 注入错误时变红、按快照还原后回绿——该验收有资格存在。\n",
    "stderr": "",
    "test_output": "test_stage_output_cap_is_enforced_in_actual_transport (test_memory_model_budget.ModelBudgetTests.test_stage_output_cap_is_enforced_in_actual_transport) ... ok\n\n----------------------------------------------------------------------\nRan 1 test in 0.113s\n\nOK\ntest_stage_output_cap_is_enforced_in_actual_transport (test_memory_model_budget.ModelBudgetTests.test_stage_output_cap_is_enforced_in_actual_transport) ... FAIL\n\n======================================================================\nFAIL: test_stage_output_cap_is_enforced_in_actual_transport (test_memory_model_budget.ModelBudgetTests.test_stage_output_cap_is_enforced_in_actual_transport)\n----------------------------------------------------------------------\nTraceback (most recent call last):\n  File \"/home/kelong/orca/workspaces/memory-orchestrator/codex-add-vault-maintenance-controller/tests/test_memory_model_budget.py\", line 226, in test_stage_output_cap_is_enforced_in_actual_transport\n    self.assertEqual(call.calls[0][\"max_output_tokens\"], 50)\n    ~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\nAssertionError: 3000 != 50\n\n----------------------------------------------------------------------\nRan 1 test in 0.114s\n\nFAILED (failures=1)\ntest_stage_output_cap_is_enforced_in_actual_transport (test_memory_model_budget.ModelBudgetTests.test_stage_output_cap_is_enforced_in_actual_transport) ... ok\n\n----------------------------------------------------------------------\nRan 1 test in 0.111s\n\nOK\n"
  },
  {
    "name": "repair-full-input",
    "target": "src/memory_orchestrator/model.py",
    "old": "estimated = self._count_tokens(copy.deepcopy(messages))",
    "new": "estimated = self._count_tokens(copy.deepcopy(messages[:2]))",
    "test": "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python -m unittest test_memory_model_budget.ModelBudgetTests.test_repair_recounts_original_rejected_output_and_diagnostics -v",
    "command": [
      "python3",
      "/home/kelong/ai-workbench/tools/mutation_license.py",
      "--tests",
      "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python -m unittest test_memory_model_budget.ModelBudgetTests.test_repair_recounts_original_rejected_output_and_diagnostics -v >> /tmp/model-budget-mutations/repair-full-input.tests.txt 2>&1",
      "--target",
      "src/memory_orchestrator/model.py",
      "--mutate",
      "python3 -c 'from pathlib import Path; p=Path('\"'\"'src/memory_orchestrator/model.py'\"'\"'); s=p.read_text(); old='\"'\"'estimated = self._count_tokens(copy.deepcopy(messages))'\"'\"'; assert s.count(old)==1; p.write_text(s.replace(old,'\"'\"'estimated = self._count_tokens(copy.deepcopy(messages[:2]))'\"'\"'))'"
    ],
    "before_sha256": "ebeca19f47c1f887861c9f0ed1acc0bc63cf3f3ca89ed2a6834e40d61084c356",
    "after_sha256": "ebeca19f47c1f887861c9f0ed1acc0bc63cf3f3ca89ed2a6834e40d61084c356",
    "exit_code": 0,
    "stdout": "✅ 执照发放:src/memory_orchestrator/model.py 注入错误时变红、按快照还原后回绿——该验收有资格存在。\n",
    "stderr": "",
    "test_output": "test_repair_recounts_original_rejected_output_and_diagnostics (test_memory_model_budget.ModelBudgetTests.test_repair_recounts_original_rejected_output_and_diagnostics) ... ok\n\n----------------------------------------------------------------------\nRan 1 test in 0.110s\n\nOK\ntest_repair_recounts_original_rejected_output_and_diagnostics (test_memory_model_budget.ModelBudgetTests.test_repair_recounts_original_rejected_output_and_diagnostics) ... FAIL\n\n======================================================================\nFAIL: test_repair_recounts_original_rejected_output_and_diagnostics (test_memory_model_budget.ModelBudgetTests.test_repair_recounts_original_rejected_output_and_diagnostics)\n----------------------------------------------------------------------\nTraceback (most recent call last):\n  File \"/home/kelong/orca/workspaces/memory-orchestrator/codex-add-vault-maintenance-controller/tests/test_memory_model_budget.py\", line 165, in test_repair_recounts_original_rejected_output_and_diagnostics\n    with self.assertRaises(DomainError) as caught: model.generate(\"extract_v1\", self.extract_inputs)\n         ~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^\nAssertionError: DomainError not raised\n\n----------------------------------------------------------------------\nRan 1 test in 0.112s\n\nFAILED (failures=1)\ntest_repair_recounts_original_rejected_output_and_diagnostics (test_memory_model_budget.ModelBudgetTests.test_repair_recounts_original_rejected_output_and_diagnostics) ... ok\n\n----------------------------------------------------------------------\nRan 1 test in 0.110s\n\nOK\n"
  },
  {
    "name": "full-default-input",
    "target": "src/memory_orchestrator/model.py",
    "old": "len(_json(messages).encode(\"utf-8\"))",
    "new": "len(_json(messages[-1:]).encode(\"utf-8\"))",
    "test": "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python -m unittest test_memory_model_budget.ModelBudgetTests.test_default_estimate_is_declared_and_does_not_replace_provider_usage -v",
    "command": [
      "python3",
      "/home/kelong/ai-workbench/tools/mutation_license.py",
      "--tests",
      "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python -m unittest test_memory_model_budget.ModelBudgetTests.test_default_estimate_is_declared_and_does_not_replace_provider_usage -v >> /tmp/model-budget-mutations/full-default-input.tests.txt 2>&1",
      "--target",
      "src/memory_orchestrator/model.py",
      "--mutate",
      "python3 -c 'from pathlib import Path; p=Path('\"'\"'src/memory_orchestrator/model.py'\"'\"'); s=p.read_text(); old='\"'\"'len(_json(messages).encode(\"utf-8\"))'\"'\"'; assert s.count(old)==1; p.write_text(s.replace(old,'\"'\"'len(_json(messages[-1:]).encode(\"utf-8\"))'\"'\"'))'"
    ],
    "before_sha256": "ebeca19f47c1f887861c9f0ed1acc0bc63cf3f3ca89ed2a6834e40d61084c356",
    "after_sha256": "ebeca19f47c1f887861c9f0ed1acc0bc63cf3f3ca89ed2a6834e40d61084c356",
    "exit_code": 0,
    "stdout": "✅ 执照发放:src/memory_orchestrator/model.py 注入错误时变红、按快照还原后回绿——该验收有资格存在。\n",
    "stderr": "",
    "test_output": "test_default_estimate_is_declared_and_does_not_replace_provider_usage (test_memory_model_budget.ModelBudgetTests.test_default_estimate_is_declared_and_does_not_replace_provider_usage) ... ok\n\n----------------------------------------------------------------------\nRan 1 test in 0.115s\n\nOK\ntest_default_estimate_is_declared_and_does_not_replace_provider_usage (test_memory_model_budget.ModelBudgetTests.test_default_estimate_is_declared_and_does_not_replace_provider_usage) ... FAIL\n\n======================================================================\nFAIL: test_default_estimate_is_declared_and_does_not_replace_provider_usage (test_memory_model_budget.ModelBudgetTests.test_default_estimate_is_declared_and_does_not_replace_provider_usage)\n----------------------------------------------------------------------\nTraceback (most recent call last):\n  File \"/home/kelong/orca/workspaces/memory-orchestrator/codex-add-vault-maintenance-controller/tests/test_memory_model_budget.py\", line 98, in test_default_estimate_is_declared_and_does_not_replace_provider_usage\n    self.assertEqual(preview[\"estimated_input_tokens\"], math.ceil(len(serialized.encode(\"utf-8\")) / 3))\n    ~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\nAssertionError: 21912 != 22514\n\n----------------------------------------------------------------------\nRan 1 test in 0.113s\n\nFAILED (failures=1)\ntest_default_estimate_is_declared_and_does_not_replace_provider_usage (test_memory_model_budget.ModelBudgetTests.test_default_estimate_is_declared_and_does_not_replace_provider_usage) ... ok\n\n----------------------------------------------------------------------\nRan 1 test in 0.113s\n\nOK\n"
  },
  {
    "name": "unknown-not-zero",
    "target": "src/memory_orchestrator/model.py",
    "old": "actual = entry[side + \"_tokens\"]",
    "new": "actual = entry[side + \"_tokens\"] or 0",
    "test": "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python -m unittest test_memory_model_budget.ModelBudgetTests.test_partial_and_invalid_usage_cannot_refund_missing_dimensions -v",
    "command": [
      "python3",
      "/home/kelong/ai-workbench/tools/mutation_license.py",
      "--tests",
      "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python -m unittest test_memory_model_budget.ModelBudgetTests.test_partial_and_invalid_usage_cannot_refund_missing_dimensions -v >> /tmp/model-budget-mutations/unknown-not-zero.tests.txt 2>&1",
      "--target",
      "src/memory_orchestrator/model.py",
      "--mutate",
      "python3 -c 'from pathlib import Path; p=Path('\"'\"'src/memory_orchestrator/model.py'\"'\"'); s=p.read_text(); old='\"'\"'actual = entry[side + \"_tokens\"]'\"'\"'; assert s.count(old)==1; p.write_text(s.replace(old,'\"'\"'actual = entry[side + \"_tokens\"] or 0'\"'\"'))'"
    ],
    "before_sha256": "ebeca19f47c1f887861c9f0ed1acc0bc63cf3f3ca89ed2a6834e40d61084c356",
    "after_sha256": "ebeca19f47c1f887861c9f0ed1acc0bc63cf3f3ca89ed2a6834e40d61084c356",
    "exit_code": 0,
    "stdout": "✅ 执照发放:src/memory_orchestrator/model.py 注入错误时变红、按快照还原后回绿——该验收有资格存在。\n",
    "stderr": "",
    "test_output": "test_partial_and_invalid_usage_cannot_refund_missing_dimensions (test_memory_model_budget.ModelBudgetTests.test_partial_and_invalid_usage_cannot_refund_missing_dimensions) ... ok\n\n----------------------------------------------------------------------\nRan 1 test in 0.122s\n\nOK\ntest_partial_and_invalid_usage_cannot_refund_missing_dimensions (test_memory_model_budget.ModelBudgetTests.test_partial_and_invalid_usage_cannot_refund_missing_dimensions) ... \n  test_partial_and_invalid_usage_cannot_refund_missing_dimensions (test_memory_model_budget.ModelBudgetTests.test_partial_and_invalid_usage_cannot_refund_missing_dimensions) (tokens={'input_tokens': 1.5, 'output_tokens': True, 'total_tokens': 10}) ... FAIL\n  test_partial_and_invalid_usage_cannot_refund_missing_dimensions (test_memory_model_budget.ModelBudgetTests.test_partial_and_invalid_usage_cannot_refund_missing_dimensions) (tokens={'total_tokens': 10}) ... FAIL\n  test_partial_and_invalid_usage_cannot_refund_missing_dimensions (test_memory_model_budget.ModelBudgetTests.test_partial_and_invalid_usage_cannot_refund_missing_dimensions) (tokens={'output_tokens': 7}) ... FAIL\n\n======================================================================\nFAIL: test_partial_and_invalid_usage_cannot_refund_missing_dimensions (test_memory_model_budget.ModelBudgetTests.test_partial_and_invalid_usage_cannot_refund_missing_dimensions) (tokens={'input_tokens': 1.5, 'output_tokens': True, 'total_tokens': 10})\n----------------------------------------------------------------------\nTraceback (most recent call last):\n  File \"/home/kelong/orca/workspaces/memory-orchestrator/codex-add-vault-maintenance-controller/tests/test_memory_model_budget.py\", line 199, in test_partial_and_invalid_usage_cannot_refund_missing_dimensions\n    self.assertEqual(entry[\"budget\"][\"input_debit\"], 100)\n    ~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\nAssertionError: 0 != 100\n\n======================================================================\nFAIL: test_partial_and_invalid_usage_cannot_refund_missing_dimensions (test_memory_model_budget.ModelBudgetTests.test_partial_and_invalid_usage_cannot_refund_missing_dimensions) (tokens={'total_tokens': 10})\n----------------------------------------------------------------------\nTraceback (most recent call last):\n  File \"/home/kelong/orca/workspaces/memory-orchestrator/codex-add-vault-maintenance-controller/tests/test_memory_model_budget.py\", line 199, in test_partial_and_invalid_usage_cannot_refund_missing_dimensions\n    self.assertEqual(entry[\"budget\"][\"input_debit\"], 100)\n    ~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\nAssertionError: 0 != 100\n\n======================================================================\nFAIL: test_partial_and_invalid_usage_cannot_refund_missing_dimensions (test_memory_model_budget.ModelBudgetTests.test_partial_and_invalid_usage_cannot_refund_missing_dimensions) (tokens={'output_tokens': 7})\n----------------------------------------------------------------------\nTraceback (most recent call last):\n  File \"/home/kelong/orca/workspaces/memory-orchestrator/codex-add-vault-maintenance-controller/tests/test_memory_model_budget.py\", line 199, in test_partial_and_invalid_usage_cannot_refund_missing_dimensions\n    self.assertEqual(entry[\"budget\"][\"input_debit\"], 100)\n    ~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\nAssertionError: 0 != 100\n\n----------------------------------------------------------------------\nRan 1 test in 0.121s\n\nFAILED (failures=3)\ntest_partial_and_invalid_usage_cannot_refund_missing_dimensions (test_memory_model_budget.ModelBudgetTests.test_partial_and_invalid_usage_cannot_refund_missing_dimensions) ... ok\n\n----------------------------------------------------------------------\nRan 1 test in 0.121s\n\nOK\n"
  },
  {
    "name": "reconcile-known",
    "target": "src/memory_orchestrator/model.py",
    "old": "difference = actual - record[side + \"_debit\"]",
    "new": "difference = 0",
    "test": "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python -m unittest test_memory_model_budget.ModelBudgetTests.test_known_output_releases_only_unused_reservation -v",
    "command": [
      "python3",
      "/home/kelong/ai-workbench/tools/mutation_license.py",
      "--tests",
      "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python -m unittest test_memory_model_budget.ModelBudgetTests.test_known_output_releases_only_unused_reservation -v >> /tmp/model-budget-mutations/reconcile-known.tests.txt 2>&1",
      "--target",
      "src/memory_orchestrator/model.py",
      "--mutate",
      "python3 -c 'from pathlib import Path; p=Path('\"'\"'src/memory_orchestrator/model.py'\"'\"'); s=p.read_text(); old='\"'\"'difference = actual - record[side + \"_debit\"]'\"'\"'; assert s.count(old)==1; p.write_text(s.replace(old,'\"'\"'difference = 0'\"'\"'))'"
    ],
    "before_sha256": "ebeca19f47c1f887861c9f0ed1acc0bc63cf3f3ca89ed2a6834e40d61084c356",
    "after_sha256": "ebeca19f47c1f887861c9f0ed1acc0bc63cf3f3ca89ed2a6834e40d61084c356",
    "exit_code": 0,
    "stdout": "✅ 执照发放:src/memory_orchestrator/model.py 注入错误时变红、按快照还原后回绿——该验收有资格存在。\n",
    "stderr": "",
    "test_output": "test_known_output_releases_only_unused_reservation (test_memory_model_budget.ModelBudgetTests.test_known_output_releases_only_unused_reservation) ... ok\n\n----------------------------------------------------------------------\nRan 1 test in 0.114s\n\nOK\ntest_known_output_releases_only_unused_reservation (test_memory_model_budget.ModelBudgetTests.test_known_output_releases_only_unused_reservation) ... ERROR\n\n======================================================================\nERROR: test_known_output_releases_only_unused_reservation (test_memory_model_budget.ModelBudgetTests.test_known_output_releases_only_unused_reservation)\n----------------------------------------------------------------------\nTraceback (most recent call last):\n  File \"/home/kelong/orca/workspaces/memory-orchestrator/codex-add-vault-maintenance-controller/tests/test_memory_model_budget.py\", line 133, in test_known_output_releases_only_unused_reservation\n    second = model.generate(\"extract_v1\", self.extract_inputs)\n  File \"/home/kelong/orca/workspaces/memory-orchestrator/codex-add-vault-maintenance-controller/src/memory_orchestrator/model.py\", line 267, in generate\n    fail(\"model_budget_exhausted\", \"Call or input/output budget exhausted before the next attempt.\",\n    ~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\n         requested_input_chars=count, limits=copy.deepcopy(self.limits), preview=inspected)\n         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\n  File \"/home/kelong/orca/workspaces/memory-orchestrator/codex-add-vault-maintenance-controller/src/memory_orchestrator/model.py\", line 255, in fail\n    raise DomainError(code, message, {\"prompt_id\": prompt_id, \"usage\": copy.deepcopy(usage),\n        \"attempts\": copy.deepcopy(attempts), \"calls_consumed\": self.calls,\n        \"input_chars_consumed\": self.input_chars, **details})\nmemory_orchestrator.schemas.DomainError: Call or input/output budget exhausted before the next attempt.\n\n----------------------------------------------------------------------\nRan 1 test in 0.114s\n\nFAILED (errors=1)\ntest_known_output_releases_only_unused_reservation (test_memory_model_budget.ModelBudgetTests.test_known_output_releases_only_unused_reservation) ... ok\n\n----------------------------------------------------------------------\nRan 1 test in 0.113s\n\nOK\n"
  },
  {
    "name": "actual-overrun",
    "target": "src/memory_orchestrator/model.py",
    "old": "if actual > maximum:",
    "new": "if False:",
    "test": "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python -m unittest test_memory_model_budget.ModelBudgetTests.test_reported_overrun_keeps_actual_tokens_and_stops_later_calls -v",
    "command": [
      "python3",
      "/home/kelong/ai-workbench/tools/mutation_license.py",
      "--tests",
      "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python -m unittest test_memory_model_budget.ModelBudgetTests.test_reported_overrun_keeps_actual_tokens_and_stops_later_calls -v >> /tmp/model-budget-mutations/actual-overrun.tests.txt 2>&1",
      "--target",
      "src/memory_orchestrator/model.py",
      "--mutate",
      "python3 -c 'from pathlib import Path; p=Path('\"'\"'src/memory_orchestrator/model.py'\"'\"'); s=p.read_text(); old='\"'\"'if actual > maximum:'\"'\"'; assert s.count(old)==1; p.write_text(s.replace(old,'\"'\"'if False:'\"'\"'))'"
    ],
    "before_sha256": "ebeca19f47c1f887861c9f0ed1acc0bc63cf3f3ca89ed2a6834e40d61084c356",
    "after_sha256": "ebeca19f47c1f887861c9f0ed1acc0bc63cf3f3ca89ed2a6834e40d61084c356",
    "exit_code": 0,
    "stdout": "✅ 执照发放:src/memory_orchestrator/model.py 注入错误时变红、按快照还原后回绿——该验收有资格存在。\n",
    "stderr": "",
    "test_output": "test_reported_overrun_keeps_actual_tokens_and_stops_later_calls (test_memory_model_budget.ModelBudgetTests.test_reported_overrun_keeps_actual_tokens_and_stops_later_calls) ... ok\n\n----------------------------------------------------------------------\nRan 1 test in 0.113s\n\nOK\ntest_reported_overrun_keeps_actual_tokens_and_stops_later_calls (test_memory_model_budget.ModelBudgetTests.test_reported_overrun_keeps_actual_tokens_and_stops_later_calls) ... FAIL\n\n======================================================================\nFAIL: test_reported_overrun_keeps_actual_tokens_and_stops_later_calls (test_memory_model_budget.ModelBudgetTests.test_reported_overrun_keeps_actual_tokens_and_stops_later_calls)\n----------------------------------------------------------------------\nTraceback (most recent call last):\n  File \"/home/kelong/orca/workspaces/memory-orchestrator/codex-add-vault-maintenance-controller/tests/test_memory_model_budget.py\", line 213, in test_reported_overrun_keeps_actual_tokens_and_stops_later_calls\n    with self.assertRaises(DomainError) as caught: model.generate(\"extract_v1\", self.extract_inputs)\n         ~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^\nAssertionError: DomainError not raised\n\n----------------------------------------------------------------------\nRan 1 test in 0.112s\n\nFAILED (failures=1)\ntest_reported_overrun_keeps_actual_tokens_and_stops_later_calls (test_memory_model_budget.ModelBudgetTests.test_reported_overrun_keeps_actual_tokens_and_stops_later_calls) ... ok\n\n----------------------------------------------------------------------\nRan 1 test in 0.112s\n\nOK\n"
  },
  {
    "name": "measurement-separation",
    "target": "src/memory_orchestrator/model.py",
    "old": "overrun = self._settle(entry)",
    "new": "overrun = self._settle(entry)\n            if \"budget\" in entry: entry[\"input_tokens\"] = entry[\"budget\"][\"estimated_input_tokens\"]",
    "test": "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python -m unittest test_memory_model_budget.ModelBudgetTests.test_default_estimate_is_declared_and_does_not_replace_provider_usage -v",
    "command": [
      "python3",
      "/home/kelong/ai-workbench/tools/mutation_license.py",
      "--tests",
      "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python -m unittest test_memory_model_budget.ModelBudgetTests.test_default_estimate_is_declared_and_does_not_replace_provider_usage -v >> /tmp/model-budget-mutations/measurement-separation.tests.txt 2>&1",
      "--target",
      "src/memory_orchestrator/model.py",
      "--mutate",
      "python3 -c 'from pathlib import Path; p=Path('\"'\"'src/memory_orchestrator/model.py'\"'\"'); s=p.read_text(); old='\"'\"'overrun = self._settle(entry)'\"'\"'; assert s.count(old)==1; p.write_text(s.replace(old,'\"'\"'overrun = self._settle(entry)\\n            if \"budget\" in entry: entry[\"input_tokens\"] = entry[\"budget\"][\"estimated_input_tokens\"]'\"'\"'))'"
    ],
    "before_sha256": "ebeca19f47c1f887861c9f0ed1acc0bc63cf3f3ca89ed2a6834e40d61084c356",
    "after_sha256": "ebeca19f47c1f887861c9f0ed1acc0bc63cf3f3ca89ed2a6834e40d61084c356",
    "exit_code": 0,
    "stdout": "✅ 执照发放:src/memory_orchestrator/model.py 注入错误时变红、按快照还原后回绿——该验收有资格存在。\n",
    "stderr": "",
    "test_output": "test_default_estimate_is_declared_and_does_not_replace_provider_usage (test_memory_model_budget.ModelBudgetTests.test_default_estimate_is_declared_and_does_not_replace_provider_usage) ... ok\n\n----------------------------------------------------------------------\nRan 1 test in 0.114s\n\nOK\ntest_default_estimate_is_declared_and_does_not_replace_provider_usage (test_memory_model_budget.ModelBudgetTests.test_default_estimate_is_declared_and_does_not_replace_provider_usage) ... FAIL\n\n======================================================================\nFAIL: test_default_estimate_is_declared_and_does_not_replace_provider_usage (test_memory_model_budget.ModelBudgetTests.test_default_estimate_is_declared_and_does_not_replace_provider_usage)\n----------------------------------------------------------------------\nTraceback (most recent call last):\n  File \"/home/kelong/orca/workspaces/memory-orchestrator/codex-add-vault-maintenance-controller/tests/test_memory_model_budget.py\", line 100, in test_default_estimate_is_declared_and_does_not_replace_provider_usage\n    self.assertEqual(entry[\"input_tokens\"], 11)\n    ~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^\nAssertionError: 22514 != 11\n\n----------------------------------------------------------------------\nRan 1 test in 0.114s\n\nFAILED (failures=1)\ntest_default_estimate_is_declared_and_does_not_replace_provider_usage (test_memory_model_budget.ModelBudgetTests.test_default_estimate_is_declared_and_does_not_replace_provider_usage) ... ok\n\n----------------------------------------------------------------------\nRan 1 test in 0.114s\n\nOK\n"
  },
  {
    "name": "missing-stage",
    "target": "src/memory_orchestrator/model.py",
    "old": "reason = {\"scope\": \"stage\", \"dimension\": \"unconfigured_stage\", \"prompt_id\": prompt_id}",
    "new": "reason = None",
    "test": "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python -m unittest test_memory_model_budget.ModelBudgetTests.test_missing_stage_is_not_unlimited_and_config_is_copied -v",
    "command": [
      "python3",
      "/home/kelong/ai-workbench/tools/mutation_license.py",
      "--tests",
      "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python -m unittest test_memory_model_budget.ModelBudgetTests.test_missing_stage_is_not_unlimited_and_config_is_copied -v >> /tmp/model-budget-mutations/missing-stage.tests.txt 2>&1",
      "--target",
      "src/memory_orchestrator/model.py",
      "--mutate",
      "python3 -c 'from pathlib import Path; p=Path('\"'\"'src/memory_orchestrator/model.py'\"'\"'); s=p.read_text(); old='\"'\"'reason = {\"scope\": \"stage\", \"dimension\": \"unconfigured_stage\", \"prompt_id\": prompt_id}'\"'\"'; assert s.count(old)==1; p.write_text(s.replace(old,'\"'\"'reason = None'\"'\"'))'"
    ],
    "before_sha256": "ebeca19f47c1f887861c9f0ed1acc0bc63cf3f3ca89ed2a6834e40d61084c356",
    "after_sha256": "ebeca19f47c1f887861c9f0ed1acc0bc63cf3f3ca89ed2a6834e40d61084c356",
    "exit_code": 0,
    "stdout": "✅ 执照发放:src/memory_orchestrator/model.py 注入错误时变红、按快照还原后回绿——该验收有资格存在。\n",
    "stderr": "",
    "test_output": "test_missing_stage_is_not_unlimited_and_config_is_copied (test_memory_model_budget.ModelBudgetTests.test_missing_stage_is_not_unlimited_and_config_is_copied) ... ok\n\n----------------------------------------------------------------------\nRan 1 test in 0.113s\n\nOK\ntest_missing_stage_is_not_unlimited_and_config_is_copied (test_memory_model_budget.ModelBudgetTests.test_missing_stage_is_not_unlimited_and_config_is_copied) ... FAIL\n\n======================================================================\nFAIL: test_missing_stage_is_not_unlimited_and_config_is_copied (test_memory_model_budget.ModelBudgetTests.test_missing_stage_is_not_unlimited_and_config_is_copied)\n----------------------------------------------------------------------\nTraceback (most recent call last):\n  File \"/home/kelong/orca/workspaces/memory-orchestrator/codex-add-vault-maintenance-controller/tests/test_memory_model_budget.py\", line 237, in test_missing_stage_is_not_unlimited_and_config_is_copied\n    self.assertFalse(model.preview(\"extract_v1\", self.extract_inputs)[\"fits\"])\n    ~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\nAssertionError: True is not false\n\n----------------------------------------------------------------------\nRan 1 test in 0.111s\n\nFAILED (failures=1)\ntest_missing_stage_is_not_unlimited_and_config_is_copied (test_memory_model_budget.ModelBudgetTests.test_missing_stage_is_not_unlimited_and_config_is_copied) ... ok\n\n----------------------------------------------------------------------\nRan 1 test in 0.112s\n\nOK\n"
  },
  {
    "name": "repair-error-usage",
    "target": "src/memory_orchestrator/model.py",
    "old": "fail(exc.code, exc.message, **exc.details)",
    "new": "raise",
    "test": "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python -m unittest test_memory_model_budget.ModelBudgetTests.test_counter_failure_during_repair_preserves_the_prior_attempt_usage -v",
    "command": [
      "python3",
      "/home/kelong/ai-workbench/tools/mutation_license.py",
      "--tests",
      "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python -m unittest test_memory_model_budget.ModelBudgetTests.test_counter_failure_during_repair_preserves_the_prior_attempt_usage -v >> /tmp/model-budget-mutations/repair-error-usage.tests.txt 2>&1",
      "--target",
      "src/memory_orchestrator/model.py",
      "--mutate",
      "python3 -c 'from pathlib import Path; p=Path('\"'\"'src/memory_orchestrator/model.py'\"'\"'); s=p.read_text(); old='\"'\"'fail(exc.code, exc.message, **exc.details)'\"'\"'; assert s.count(old)==1; p.write_text(s.replace(old,'\"'\"'raise'\"'\"'))'"
    ],
    "before_sha256": "ebeca19f47c1f887861c9f0ed1acc0bc63cf3f3ca89ed2a6834e40d61084c356",
    "after_sha256": "ebeca19f47c1f887861c9f0ed1acc0bc63cf3f3ca89ed2a6834e40d61084c356",
    "exit_code": 0,
    "stdout": "✅ 执照发放:src/memory_orchestrator/model.py 注入错误时变红、按快照还原后回绿——该验收有资格存在。\n",
    "stderr": "",
    "test_output": "test_counter_failure_during_repair_preserves_the_prior_attempt_usage (test_memory_model_budget.ModelBudgetTests.test_counter_failure_during_repair_preserves_the_prior_attempt_usage) ... ok\n\n----------------------------------------------------------------------\nRan 1 test in 0.112s\n\nOK\ntest_counter_failure_during_repair_preserves_the_prior_attempt_usage (test_memory_model_budget.ModelBudgetTests.test_counter_failure_during_repair_preserves_the_prior_attempt_usage) ... ERROR\n\n======================================================================\nERROR: test_counter_failure_during_repair_preserves_the_prior_attempt_usage (test_memory_model_budget.ModelBudgetTests.test_counter_failure_during_repair_preserves_the_prior_attempt_usage)\n----------------------------------------------------------------------\nTraceback (most recent call last):\n  File \"/home/kelong/orca/workspaces/memory-orchestrator/codex-add-vault-maintenance-controller/tests/test_memory_model_budget.py\", line 260, in test_counter_failure_during_repair_preserves_the_prior_attempt_usage\n    self.assertEqual(len(caught.exception.details[\"usage\"]), 1)\n                         ~~~~~~~~~~~~~~~~~~~~~~~~^^^^^^^^^\nKeyError: 'usage'\n\n----------------------------------------------------------------------\nRan 1 test in 0.111s\n\nFAILED (errors=1)\ntest_counter_failure_during_repair_preserves_the_prior_attempt_usage (test_memory_model_budget.ModelBudgetTests.test_counter_failure_during_repair_preserves_the_prior_attempt_usage) ... ok\n\n----------------------------------------------------------------------\nRan 1 test in 0.113s\n\nOK\n"
  },
  {
    "name": "unknown-budget-key",
    "target": "src/memory_orchestrator/model.py",
    "old": "or value.keys() - required - {\"counter_id\", \"count_kind\"}",
    "new": "or False",
    "test": "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python -m unittest test_memory_model_budget.ModelBudgetTests.test_token_configuration_rejects_unknown_fields_and_ambiguous_counter_identity -v",
    "command": [
      "python3",
      "/home/kelong/ai-workbench/tools/mutation_license.py",
      "--tests",
      "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python -m unittest test_memory_model_budget.ModelBudgetTests.test_token_configuration_rejects_unknown_fields_and_ambiguous_counter_identity -v >> /tmp/model-budget-mutations/unknown-budget-key.tests.txt 2>&1",
      "--target",
      "src/memory_orchestrator/model.py",
      "--mutate",
      "python3 -c 'from pathlib import Path; p=Path('\"'\"'src/memory_orchestrator/model.py'\"'\"'); s=p.read_text(); old='\"'\"'or value.keys() - required - {\"counter_id\", \"count_kind\"}'\"'\"'; assert s.count(old)==1; p.write_text(s.replace(old,'\"'\"'or False'\"'\"'))'"
    ],
    "before_sha256": "ebeca19f47c1f887861c9f0ed1acc0bc63cf3f3ca89ed2a6834e40d61084c356",
    "after_sha256": "ebeca19f47c1f887861c9f0ed1acc0bc63cf3f3ca89ed2a6834e40d61084c356",
    "exit_code": 0,
    "stdout": "✅ 执照发放:src/memory_orchestrator/model.py 注入错误时变红、按快照还原后回绿——该验收有资格存在。\n",
    "stderr": "",
    "test_output": "test_token_configuration_rejects_unknown_fields_and_ambiguous_counter_identity (test_memory_model_budget.ModelBudgetTests.test_token_configuration_rejects_unknown_fields_and_ambiguous_counter_identity) ... ok\n\n----------------------------------------------------------------------\nRan 1 test in 0.110s\n\nOK\ntest_token_configuration_rejects_unknown_fields_and_ambiguous_counter_identity (test_memory_model_budget.ModelBudgetTests.test_token_configuration_rejects_unknown_fields_and_ambiguous_counter_identity) ... FAIL\n\n======================================================================\nFAIL: test_token_configuration_rejects_unknown_fields_and_ambiguous_counter_identity (test_memory_model_budget.ModelBudgetTests.test_token_configuration_rejects_unknown_fields_and_ambiguous_counter_identity)\n----------------------------------------------------------------------\nTraceback (most recent call last):\n  File \"/home/kelong/orca/workspaces/memory-orchestrator/codex-add-vault-maintenance-controller/tests/test_memory_model_budget.py\", line 267, in test_token_configuration_rejects_unknown_fields_and_ambiguous_counter_identity\n    with self.assertRaises(DomainError): StructuredModel(FakeCall([]), limits=config)\n         ~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^\nAssertionError: DomainError not raised\n\n----------------------------------------------------------------------\nRan 1 test in 0.110s\n\nFAILED (failures=1)\ntest_token_configuration_rejects_unknown_fields_and_ambiguous_counter_identity (test_memory_model_budget.ModelBudgetTests.test_token_configuration_rejects_unknown_fields_and_ambiguous_counter_identity) ... ok\n\n----------------------------------------------------------------------\nRan 1 test in 0.109s\n\nOK\n"
  },
  {
    "name": "frozen-budget-config",
    "target": "src/memory_orchestrator/model.py",
    "old": "result = copy.deepcopy(value)",
    "new": "result = value",
    "test": "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python -m unittest test_memory_model_budget.ModelBudgetTests.test_missing_stage_is_not_unlimited_and_config_is_copied -v",
    "command": [
      "python3",
      "/home/kelong/ai-workbench/tools/mutation_license.py",
      "--tests",
      "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python -m unittest test_memory_model_budget.ModelBudgetTests.test_missing_stage_is_not_unlimited_and_config_is_copied -v >> /tmp/model-budget-mutations/frozen-budget-config.tests.txt 2>&1",
      "--target",
      "src/memory_orchestrator/model.py",
      "--mutate",
      "python3 -c 'from pathlib import Path; p=Path('\"'\"'src/memory_orchestrator/model.py'\"'\"'); s=p.read_text(); old='\"'\"'result = copy.deepcopy(value)'\"'\"'; assert s.count(old)==1; p.write_text(s.replace(old,'\"'\"'result = value'\"'\"'))'"
    ],
    "before_sha256": "ebeca19f47c1f887861c9f0ed1acc0bc63cf3f3ca89ed2a6834e40d61084c356",
    "after_sha256": "ebeca19f47c1f887861c9f0ed1acc0bc63cf3f3ca89ed2a6834e40d61084c356",
    "exit_code": 0,
    "stdout": "✅ 执照发放:src/memory_orchestrator/model.py 注入错误时变红、按快照还原后回绿——该验收有资格存在。\n",
    "stderr": "",
    "test_output": "test_missing_stage_is_not_unlimited_and_config_is_copied (test_memory_model_budget.ModelBudgetTests.test_missing_stage_is_not_unlimited_and_config_is_copied) ... ok\n\n----------------------------------------------------------------------\nRan 1 test in 0.114s\n\nOK\ntest_missing_stage_is_not_unlimited_and_config_is_copied (test_memory_model_budget.ModelBudgetTests.test_missing_stage_is_not_unlimited_and_config_is_copied) ... FAIL\n\n======================================================================\nFAIL: test_missing_stage_is_not_unlimited_and_config_is_copied (test_memory_model_budget.ModelBudgetTests.test_missing_stage_is_not_unlimited_and_config_is_copied)\n----------------------------------------------------------------------\nTraceback (most recent call last):\n  File \"/home/kelong/orca/workspaces/memory-orchestrator/codex-add-vault-maintenance-controller/tests/test_memory_model_budget.py\", line 239, in test_missing_stage_is_not_unlimited_and_config_is_copied\n    with self.assertRaises(DomainError): model.generate(\"extract_v1\", self.extract_inputs)\n         ~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^\nAssertionError: DomainError not raised\n\n----------------------------------------------------------------------\nRan 1 test in 0.117s\n\nFAILED (failures=1)\ntest_missing_stage_is_not_unlimited_and_config_is_copied (test_memory_model_budget.ModelBudgetTests.test_missing_stage_is_not_unlimited_and_config_is_copied) ... ok\n\n----------------------------------------------------------------------\nRan 1 test in 0.112s\n\nOK\n"
  }
]
```

</details>

## 已知边界与交接

- 默认 `utf8-json-bytes-div3-v1` 是完整消息的字节启发式估计，不是 tokenizer 实测或输入 token 数学上界；provider 实际量可能使首次超额在返回后才被发现。
- token 账本属于本 model 实例，未新增进程重启/整个实验臂的持久预算恢复。已有实际外层调用记录与本层预算不得混称。
- 报告中的 provider token 和金钱费用继续来自原 transport；预留不等于真实 token 或价格。未知不补零，不采集隐藏推理。
- 本轮没有改 learning/evidence/schema/发布/实验入口。根代理负责新单一轨迹→学习输入链及真实配置消费；实例未启用 token_budget 的字符语义继续兼容。
- 没有真实模型效果、摘要准确性或学习收益证据。本次证据只支持预算机制和失败边界。
