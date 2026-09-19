# 示例预检与实际补读测试迁移

2026-09-19；所有权只涉及 examples/memory_evolution/demo.py 的 ScriptedTeacher 及 tests/test_memory_learning.py 两项旧补读测试和共同 fixture helper。未改 model/evidence/learning 实现、根代理的新 trajectory learning 测试、总纲或发布器；未调用模型、未 commit。

## 真实 RED 与原因

修改前执行：

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python -m unittest test_memory_learning.LearningTests.test_real_packet_expansion_is_finite_and_recorded test_memory_learning.LearningTests.test_more_evidence_request_after_limit_abstains test_memory_flow.FlowTests.test_generate_patch_publish_reuse_rollback_and_reopen -v
```

exit 1，三项失败分别是 `abstained != noop`、`0 != 2`、`['error','error'] != ['proposed','proposed']`。旧两项测试在调用 learn 前用旧全局 build_packet/expand_packet 猜好了引用，且长输入没有新阶段预算；示例缺少统一入口所需 preview。没有通过恢复旧学习入口使其转绿。

## 改动

- ScriptedTeacher.preview 委托真实 StructuredModel.preview，共用完整 renderer 与 counter；同步现有 scripted calls，preview 不消费调用、不进入 transport、不生成实测 token/费用。它仅是构造例子的纯预检，不能据此声称 scripted teacher 已产生 provider 成本。
- 两项测试保留原来源的长 episode，明确配置有界局部整理和累计 token。每次从实际 rendered summarize/extract 请求解析 evidence_packet；只从当前 extract 请求中的未读目录选择 read_request。
- 验收包含真实 summary 阶段、恰好两次 extract、第二次补读余额为 0、全部 usage 数量、原事件不变、补读后文本/raw_ref/raw_hash/byte range 与原索引一致。超过一次补读时停止且第二个引用不成为已读事实。
- 局部段上限显式为 2，因此断言 `mode=partial` 与 `segment_budget`，没有把部分处理改称全量摘要。迁移首轮对状态名称的误判（期望 summarized，实际 partial）经消费者源码核对后改为这个更严格的覆盖断言。

## GREEN

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python -m unittest test_memory_learning test_memory_flow -v
```

exit 0：`Ran 40 tests in 9.715s`，`OK`（36 learning + 4 flow）。官方变体恢复后再次执行上面的三项关联命令：exit 0，`Ran 3 tests in 2.754s`，`OK`。限定路径 diff --check 通过。

最终 SHA-256：

- demo.py：`baf22379261142e955174a6c782a92c15335efaa0a5653b286e19beae21da879`
- test_memory_learning.py：`421460bd54975aa2b8050c5f6df289ebf5132ae11057b5b8ef7087ab98275460`

## 官方执照

实施前 max_calls 真拒绝路径获得执照。收尾四项均由 mutation_license.py 执行并精确恢复：真实 renderer 委托、剩余调用数、preview 不变更状态，以及既有 max_calls 拒绝路径复验。未修改已冻结 model core 来杀这些变体。

| 变体 | exit | 恢复 hash 一致 |
| --- | --- | --- |
| same-render | 0 | 是 |
| remaining-calls | 0 | 是 |
| pure-preview | 0 | 是 |
| max-calls-repeat | 0 | 是 |

<details>
<summary>初始执照命令、退出和原始输出</summary>

```json
{
  "command": [
    "python3",
    "/home/kelong/ai-workbench/tools/mutation_license.py",
    "--tests",
    "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. .venv/bin/python -c 'from examples.memory_evolution.demo import ScriptedTeacher; t=ScriptedTeacher(); t.limits={**t.limits,\"max_calls\":1}; t.generate(\"maintain_experience_v1\",{});\ntry: t.generate(\"maintain_experience_v1\",{})\nexcept RuntimeError: print(\"scripted-call-cap rejected second attempt\")\nelse: raise AssertionError(\"second scripted attempt accepted\")'",
    "--target",
    "examples/memory_evolution/demo.py",
    "--mutate",
    "python3 -c 'from pathlib import Path; p=Path('\"'\"'examples/memory_evolution/demo.py'\"'\"'); s=p.read_text(); old=\"if self.calls > self.limits['\"'\"'max_calls'\"'\"']:\"; assert s.count(old)==1; p.write_text(s.replace(old,\"if False:\"))'"
  ],
  "before_sha256": "0f0e32f71240a5ba54a602f43968d373dc1035bac3cf85e675ebc4d507eeb4c9",
  "after_sha256": "0f0e32f71240a5ba54a602f43968d373dc1035bac3cf85e675ebc4d507eeb4c9",
  "exit_code": 0,
  "stdout": "✅ 执照发放:examples/memory_evolution/demo.py 注入错误时变红、按快照还原后回绿——该验收有资格存在。\n",
  "stderr": ""
}
```

</details>

<details>
<summary>收尾四项命令、注入、退出和原始输出</summary>

```json
[
  {
    "name": "same-render",
    "command": [
      "python3",
      "/home/kelong/ai-workbench/tools/mutation_license.py",
      "--tests",
      "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests:. .venv/bin/python -c 'from copy import deepcopy\nfrom examples.memory_evolution.demo import ScriptedTeacher\nfrom memory_orchestrator.model import StructuredModel\nfrom test_memory_model import inputs\n\ndef forbidden(request): raise AssertionError(\"preview dispatched transport\")\nt=ScriptedTeacher(); t.calls=2\nvalue=inputs(); original=deepcopy(value); state=deepcopy(vars(t))\nreference=StructuredModel(forbidden,limits=deepcopy(t.limits)); reference.calls=t.calls\nobserved=t.preview(\"extract_v1\",value)\nassert observed==reference.preview(\"extract_v1\",value),(observed,reference.preview(\"extract_v1\",value))\nassert value==original and vars(t)==state\nassert observed[\"budget\"] is None\nassert observed[\"estimated_input_tokens\"]>0\nassert not any(key in observed for key in (\"usage\",\"provider_usage\",\"input_tokens\"))\nt.calls=t.limits[\"max_calls\"]\nassert t.preview(\"extract_v1\",value)[\"fits\"] is False\nprint(\"same renderer, explicit estimate, no transport/state/input mutation, remaining calls honored\")\n'",
      "--target",
      "examples/memory_evolution/demo.py",
      "--mutate",
      "python3 -c 'from pathlib import Path; p=Path('\"'\"'examples/memory_evolution/demo.py'\"'\"'); s=p.read_text(); old='\"'\"'return boundary.preview(prompt_id, inputs)'\"'\"'; assert s.count(old)==1; p.write_text(s.replace(old,'\"'\"'return {\"fits\": True}'\"'\"'))'"
    ],
    "old": "return boundary.preview(prompt_id, inputs)",
    "new": "return {\"fits\": True}",
    "before_sha256": "baf22379261142e955174a6c782a92c15335efaa0a5653b286e19beae21da879",
    "after_sha256": "baf22379261142e955174a6c782a92c15335efaa0a5653b286e19beae21da879",
    "exit_code": 0,
    "stdout": "✅ 执照发放:examples/memory_evolution/demo.py 注入错误时变红、按快照还原后回绿——该验收有资格存在。\n",
    "stderr": ""
  },
  {
    "name": "remaining-calls",
    "command": [
      "python3",
      "/home/kelong/ai-workbench/tools/mutation_license.py",
      "--tests",
      "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests:. .venv/bin/python -c 'from copy import deepcopy\nfrom examples.memory_evolution.demo import ScriptedTeacher\nfrom memory_orchestrator.model import StructuredModel\nfrom test_memory_model import inputs\n\ndef forbidden(request): raise AssertionError(\"preview dispatched transport\")\nt=ScriptedTeacher(); t.calls=2\nvalue=inputs(); original=deepcopy(value); state=deepcopy(vars(t))\nreference=StructuredModel(forbidden,limits=deepcopy(t.limits)); reference.calls=t.calls\nobserved=t.preview(\"extract_v1\",value)\nassert observed==reference.preview(\"extract_v1\",value),(observed,reference.preview(\"extract_v1\",value))\nassert value==original and vars(t)==state\nassert observed[\"budget\"] is None\nassert observed[\"estimated_input_tokens\"]>0\nassert not any(key in observed for key in (\"usage\",\"provider_usage\",\"input_tokens\"))\nt.calls=t.limits[\"max_calls\"]\nassert t.preview(\"extract_v1\",value)[\"fits\"] is False\nprint(\"same renderer, explicit estimate, no transport/state/input mutation, remaining calls honored\")\n'",
      "--target",
      "examples/memory_evolution/demo.py",
      "--mutate",
      "python3 -c 'from pathlib import Path; p=Path('\"'\"'examples/memory_evolution/demo.py'\"'\"'); s=p.read_text(); old='\"'\"'boundary.calls = self.calls'\"'\"'; assert s.count(old)==1; p.write_text(s.replace(old,'\"'\"'boundary.calls = 0'\"'\"'))'"
    ],
    "old": "boundary.calls = self.calls",
    "new": "boundary.calls = 0",
    "before_sha256": "baf22379261142e955174a6c782a92c15335efaa0a5653b286e19beae21da879",
    "after_sha256": "baf22379261142e955174a6c782a92c15335efaa0a5653b286e19beae21da879",
    "exit_code": 0,
    "stdout": "✅ 执照发放:examples/memory_evolution/demo.py 注入错误时变红、按快照还原后回绿——该验收有资格存在。\n",
    "stderr": ""
  },
  {
    "name": "pure-preview",
    "command": [
      "python3",
      "/home/kelong/ai-workbench/tools/mutation_license.py",
      "--tests",
      "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests:. .venv/bin/python -c 'from copy import deepcopy\nfrom examples.memory_evolution.demo import ScriptedTeacher\nfrom memory_orchestrator.model import StructuredModel\nfrom test_memory_model import inputs\n\ndef forbidden(request): raise AssertionError(\"preview dispatched transport\")\nt=ScriptedTeacher(); t.calls=2\nvalue=inputs(); original=deepcopy(value); state=deepcopy(vars(t))\nreference=StructuredModel(forbidden,limits=deepcopy(t.limits)); reference.calls=t.calls\nobserved=t.preview(\"extract_v1\",value)\nassert observed==reference.preview(\"extract_v1\",value),(observed,reference.preview(\"extract_v1\",value))\nassert value==original and vars(t)==state\nassert observed[\"budget\"] is None\nassert observed[\"estimated_input_tokens\"]>0\nassert not any(key in observed for key in (\"usage\",\"provider_usage\",\"input_tokens\"))\nt.calls=t.limits[\"max_calls\"]\nassert t.preview(\"extract_v1\",value)[\"fits\"] is False\nprint(\"same renderer, explicit estimate, no transport/state/input mutation, remaining calls honored\")\n'",
      "--target",
      "examples/memory_evolution/demo.py",
      "--mutate",
      "python3 -c 'from pathlib import Path; p=Path('\"'\"'examples/memory_evolution/demo.py'\"'\"'); s=p.read_text(); old='\"'\"'boundary.calls = self.calls'\"'\"'; assert s.count(old)==1; p.write_text(s.replace(old,'\"'\"'boundary.calls = self.calls\\n        self.calls += 1'\"'\"'))'"
    ],
    "old": "boundary.calls = self.calls",
    "new": "boundary.calls = self.calls\n        self.calls += 1",
    "before_sha256": "baf22379261142e955174a6c782a92c15335efaa0a5653b286e19beae21da879",
    "after_sha256": "baf22379261142e955174a6c782a92c15335efaa0a5653b286e19beae21da879",
    "exit_code": 0,
    "stdout": "✅ 执照发放:examples/memory_evolution/demo.py 注入错误时变红、按快照还原后回绿——该验收有资格存在。\n",
    "stderr": ""
  },
  {
    "name": "max-calls-repeat",
    "command": [
      "python3",
      "/home/kelong/ai-workbench/tools/mutation_license.py",
      "--tests",
      "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. .venv/bin/python -c 'from examples.memory_evolution.demo import ScriptedTeacher; t=ScriptedTeacher(); t.limits={**t.limits,\"max_calls\":1}; t.generate(\"maintain_experience_v1\",{});\ntry: t.generate(\"maintain_experience_v1\",{})\nexcept RuntimeError: print(\"scripted-call-cap rejected second attempt\")\nelse: raise AssertionError(\"second scripted attempt accepted\")'",
      "--target",
      "examples/memory_evolution/demo.py",
      "--mutate",
      "python3 -c 'from pathlib import Path; p=Path('\"'\"'examples/memory_evolution/demo.py'\"'\"'); s=p.read_text(); old=\"if self.calls > self.limits['\"'\"'max_calls'\"'\"']:\"; assert s.count(old)==1; p.write_text(s.replace(old,\"if False:\"))'"
    ],
    "before_sha256": "baf22379261142e955174a6c782a92c15335efaa0a5653b286e19beae21da879",
    "after_sha256": "baf22379261142e955174a6c782a92c15335efaa0a5653b286e19beae21da879",
    "exit_code": 0,
    "stdout": "✅ 执照发放:examples/memory_evolution/demo.py 注入错误时变红、按快照还原后回绿——该验收有资格存在。\n",
    "stderr": ""
  }
]
```

</details>

这些是构造的流程/预算/来源检查，不能推导真实模型摘要或经验学习收益。全项目验证由根代理统一完成。
