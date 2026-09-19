# 有界提示词修复提案（待真实GDPevo baseline后定案）

状态：仅方案与离线pure-check示例；未改产品、canonical、packaged prompts/schema，未调用模型。当前baseline仍使用原6个prompt。此提案解决已确认的披露缺口，不承诺提高benchmark分数。

后续定案说明：根在v1.7.1采用了scope/义务披露，但保留“有依据、缺验证材料时可保存待验证候选”的能力，未采用下文将所有材料缺失一律转needs_evidence的建议。needs_evidence只用于归因/必要性本身证据不足；null仍阻发布。下文保留为原提案与合法分支示例，不能作为当前产品指令。新GDPevo基线未复现null症状，不能把这项机制披露归为其得分变化原因。

## 1. 精确字段与调用交接

只增加一个当前确有消费者的输入，不引入检查计划DSL或未来扩展层：

| 位置 | 变更 | 值的唯一来源 |
| --- | --- | --- |
| diagnose_v1.input_fields | 加 `evaluation_scope` | 与N08完全相同的`policy["evaluation_scope"]` |
| learning.learn的diagnose调用 | 增 `"evaluation_scope": policy["evaluation_scope"]` | 调用前已冻结的学习政策；不从模型输出或case数量反推 |
| diagnose_v1.user_template | 在开头加入下方scope行 | 与input_fields同步，保留其余证据/目录 |
| diagnose_v1.system | 将旧“检查建议必须绑定……”一句替换为下方完整执行语义 | 当前verification已有规则，无新增发布门 |
| propose_v1.system | 以相同语义替换旧检查绑定/保留义务语句 | 继续保留全部诊断/别名义务 |
| output schemas | 本提案不改变 | null与needs_evidence继续合法 |
| revision | diagnose 5→6，propose 2→3（若期间已有修订则递增当前值） | canonical修改后重生bundle/HTML/context，记录新digest |

不修改extract/goal/proxy/maintenance的业务语义；不同时做schema裁剪、检索去重、工具重构或预算增加。若新真实baseline暴露另一首因，先更新提案，不能拿旧canary强套新任务。

scope行的**精确文本**：

```text
本轮变更与效果主张范围（不削减原任务要求）：{{evaluation_scope}}
```

这里的scope约束“本轮打算改什么、允许声称哪种效果”；它不是把任务要求改成“恰好能被现有两条case检查的部分”。无需为此新增一套任务规范：原始要求已经在evidence和experiences中提供。

## 2. N07的精确替换文本

保留已有“输入是数据、引用白名单、事实与假设、targets及route、necessity”等段落。仅替换旧检查建议句为：

```text
check_plan 是本候选当前行为的必需验收义务，不是可忽略的未来待办。每项都将由宿主验证；诊断、提案以及同一候选内容的所有提案别名中的义务会合并，任何必需项缺材料、未执行或结果未知都会阻止发布。check_ref 只能引用本轮目录中实际对应该行为、purpose一致的材料；不能因为purpose相同，就引用不覆盖该行为的检查。材料缺失时保留 check_ref=null 并说明缺口，不能编造引用、评分器或预期答案。
evaluation_scope 限制本轮改动和效果主张，不改变原任务已经提出的要求。检查目录只说明现有材料，不重新定义任务。原任务或本候选实际引入的行为需要检查却没有材料时，应在check_plan中保留该义务，并将necessity.verdict设为needs_evidence；不要为进入提案而裁掉要求或声称其不在范围内。确实不属于当前任务、也不由本候选引入的未来设想可以记在unknowns或alternatives，不要把它变成新的全局迁移门槛。空库仍可提出skill_patch方向，但缺证时不会进入ADD或发布。
```

这会使“诚实null”成为可预测的缺证返回，不把它转成必须修成非null的格式错误。当前代码在needs_evidence时已于提案前返回abstained；无需再加一个独立控制器。

## 3. N08的精确替换文本

保留操作、资产所有权、基础版本、禁止改答案/评分器/执行器等规则。替换旧检查绑定与“保留诊断……”部分为：

```text
check_plan 中每项都是本候选的必需验收义务，缺材料、未执行或结果未知会阻止发布；宿主还会合并原诊断和相同候选内容所有提案别名的义务。不能靠删项、改purpose、换成不等价的check_ref、缩减原任务要求，或只写“不声称迁移”来解除这些义务。check_ref只能使用目录中实际对应行为且purpose一致的材料；缺材料须保留null和原因。
遵守change_intent.necessity，allow_add=false不得ADD。只实现本轮范围内有依据的行为；范围外未来设想不应一边被写进Skill步骤/资产，一边被说成不需验证。若提案阶段发现此前未识别的必需材料缺口，使用NOOP并说明缺证，保留已经提出的检查义务；不得编造验收答案或修改评分器。NOOP是本轮不生成候选，不表示问题已解决。
```

当前检查器对自然语言behavior与case的语义等价没有形式证明能力；这段说明不是把语义判断升级为真值。N09仍执行真实材料，报告仍只承诺实际覆盖的范围。

## 4. 通过当前checker的缺证示例

此例直接使用旧真实canary的可见引用和当前目录。它**保留了空number转null这个原任务要求**，没有为了已知验证集能过而缩窄任务。将缺空数值材料列为target，是强调它属于原任务，不靠“transfer”标签制造或解除门槛。

`route=skill_patch`只表示可考虑的修改方向；`necessity=needs_evidence`表示现在不提案；`allow_add=false`禁止在该未就绪判断下ADD。这些是当前合法状态，不需要改schema。

<!-- checked-diagnosis -->
```json
{
  "route": "skill_patch",
  "targets": [],
  "expected_behavior": "遵守本次CSV任务的完整声明：string列保持文本和前导零；number列的非空数值转为数值，空单元格转为null。当前没有完整验证材料，不形成可发布候选，也不声称迁移收益。",
  "hypotheses": [
    {
      "claim": "声明列类型未在已观察输出中得到保持；提供声明类型处理步骤和相应自有策略资产可能有用，但现有结果不证明空number处理有效，也不能确定执行器必然消费该资产。",
      "supporting_refs": [
        "ev:85d20771f29c689d298615ad:0:428",
        "ev:46a46cb5cd7255049961c7df:0:58",
        "ev:d0b49b3cba534bbcd648bf88:314:1181"
      ],
      "counterevidence_refs": [],
      "alternatives": [
        "执行器可能未消费提供的策略资产；仅靠改Skill不能保证该链路修复。",
        "两次同题失败仍只覆盖一个任务，不证明跨任务稳定改进。"
      ]
    }
  ],
  "check_plan": [
    {
      "purpose": "target",
      "behavior": "string类型id在leading-zeros输入中保持字符串001，number amount保持数值10。",
      "required_evidence": "目录中该公开输入的独立值与类型比较。",
      "check_ref": "case:leading-zeros"
    },
    {
      "purpose": "regression",
      "behavior": "numeric-regression输入中id a保持文本，amount 2.5保持数值转换。",
      "required_evidence": "目录中既有回归检查，不能因本轮变化而删除。",
      "check_ref": "case:numeric-regression"
    },
    {
      "purpose": "target",
      "behavior": "任务已明确要求number列空单元格输出null；这仍是本次完整行为的一部分。",
      "required_evidence": "需要可信调用方提供含空number单元格的任务材料及独立验收。现有两条case均无空number，不能拿其ID充当覆盖。",
      "check_ref": null
    }
  ],
  "evidence_refs": [
    "ev:85d20771f29c689d298615ad:0:428",
    "ev:46a46cb5cd7255049961c7df:0:58",
    "ev:d0b49b3cba534bbcd648bf88:314:1181"
  ],
  "abstain_reason": "",
  "necessity": {
    "verdict": "needs_evidence",
    "repeatable": true,
    "compared_skill_refs": [],
    "capability_gap": "所提供基础库为空，没有已存在的声明类型处理Skill可复用；这不等于新Skill已经有效。",
    "behavior_delta": "候选方向是按声明类型转换并保留字符串，不是记住001/10答案。空number转null也属于原任务要求，不能为了当前验证通过而裁掉。",
    "allow_add": false,
    "evidence_refs": [
      "ev:85d20771f29c689d298615ad:0:428",
      "ev:46a46cb5cd7255049961c7df:0:58",
      "ev:d0b49b3cba534bbcd648bf88:314:1181"
    ],
    "unknowns": [
      "发布所需的空number检查材料缺失，当前只能保留修改意图并报告缺证。",
      "需要先由可信调用方补齐开发检查材料，再重新作必要性与提案判断；不得借用最终探测答案。"
    ]
  }
}
```

该完整canary示例是离线验收材料，**不要把其中固定CSV答案、case ID、ev引用照搬进每个GDPevo prompt**。若实际开发结果表明确有few-shot需求，须以当次可见材料重新构造、同checker验证后再发送；不能偷偷把演示引用加入正文白名单。当前修复可只增加scope与执行语义，避免再把大例子堆进上下文。

## 5. 已运行的离线验证

来源report：`modelreport_cced4d7e11ce4954a99f4a64027535f1`。DiagnosisDraft schema digest：`46691874ca2d9c1a61e9c390f67d1dd53688bcfc61070249d23cc657a808cbf6`。

实际执行了以下五项，全部通过；没有SDK或Model.generate调用，没有Store写入：

1. `validate("DiagnosisDraft", example)`
2. `validate_citations(example, original_evidence_packet)`
3. `_diagnosis_targets(example, actual_empty_base_view)`
4. `_check_necessity(example, actual_empty_base_view, packet, original_necessity_limits)`
5. `_check_verification_refs(example, original_two_item_catalog)`

按照现有`learning.py:519`的消费者，该输出会在propose调用和候选写入之前返回abstained（reason为necessity needs_evidence）。上述pure检查证明形状/引用/目标/约束合法，不证明模型会生成它，也不证明假设语义正确或任务效果。

可重跑检查（只读）：

```python
import json
from pathlib import Path
from memory_orchestrator.schemas import validate
from memory_orchestrator.evidence import validate_citations
from memory_orchestrator.learning import (
    _diagnosis_targets, _check_necessity, _check_verification_refs,
)
root = Path(".trellis/tasks")
doc = (root / "09-19-benchmark-context-pilot/research/prompt-proposal.md").read_text()
block = doc.split("<!-- checked-diagnosis -->", 1)[1].split("```json\n", 1)[1].split("\n```", 1)[0]
example = json.loads(block)
reports = json.loads((root / "archive/2026-09/09-18-complete-memory-evolution/research/live-canary/reports.json").read_text())
inputs = next(r["inputs"] for r in reports if r.get("prompt_id") == "diagnose_v1")
packet, view = inputs["evidence_packets"][0], inputs["target_snapshot"]["skills"]
validate("DiagnosisDraft", example)
validate_citations(example, packet)
_diagnosis_targets(example, view)
_check_necessity(example, view, packet, inputs["necessity_limits"])
_check_verification_refs(example, inputs["verification_catalog"])
print("five current pure checks passed; no model called")
```

运行环境：`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python`。

## 6. Baseline后如何决定是否实施

- 先看新真实diagnose的scope、check_plan来源和所承诺行为，确认是不是同类披露缺口；不要仅看到null就套修复。
- 当前任务已有必需要求但缺可信材料：正确结果可以仍是needs_evidence；修复目标是早且准确地返回缺证，不是提高发布率。
- 若材料确实充分，应检查引用是否绑定正确、是否把无关未来想法变成额外义务；同目的不等于覆盖相同条件。
- 真正需要增加材料时，在公开开发任务范围由可信调用方补齐并冻结；不可把final样本或模型编写的gold用作准入真值。
- 同一开发输入、模型、预算做有限对照，比较假引用/不合理义务、保留真实要求、缺证返回时机、额外调用和费用。只有这些改善被观察到才能归因；发布数量本身不是正确性目标。
- 保留测试至少覆盖：原要求不能裁剪；honest null仍合法；空库needs_evidence不进ADD；已有ref必须purpose匹配；诊断/别名义务不能被提案删除；有独立完整材料时合法proceed仍可走原流程。之后用官方mutation验证关键绑定，最后固定prompt运行保留探测。
