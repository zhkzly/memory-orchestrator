# Python 记忆演化核心

这是独立的 Python 库。调用方提供任务执行和评价函数，核心负责固定记忆版本、组织采样、提炼经验、生成候选、比较、选择和发布。已有经历可以直接导入；用户／项目事实通过显式输入保存和纠正。

## 运行本地示例

```bash
uv venv .venv  # 首次克隆时创建环境；已有环境可跳过
uv pip install --python .venv/bin/python -e .
.venv/bin/python examples/memory_evolution/demo.py
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p 'test_memory_*.py' -v
```

`demo.py` 使用临时目录，不修改已有记忆。两轮依次展示：CSV 任务失败 → 从空库新增 Skill → 比较和发布 → 下一次任务使用新版 → 修改同一个 Skill → 再次发布 → 回退到历史版本。

CSV 处理、评分、文件存储和版本切换都实际执行。默认 teacher 是明确标注的脚本替身，用于稳定检查完整交接；示例的通过率不能作为模型学习或泛化收益。输入、评分标准和参数都是构造的教学场景；`references/csv-policy.json` 是本例执行器会读取的声明式设置，不是通用 Agent 工具格式。

## 调用顺序

```python
from memory_orchestrator.store import Store
from memory_orchestrator.context import select_context
from memory_orchestrator.sampling import sample_tasks
from memory_orchestrator.engine import evolve
from memory_orchestrator.learning import learn
from memory_orchestrator.evaluation import compare_candidates
from memory_orchestrator.release import publish, rollback
from memory_orchestrator.report import report
```

1. `Store(root)` 显式指定存储根目录。`remember()` 保存事实，`add_episode()` 导入经历，`add_feedback()` 追加迟到反馈；已知身份必须一致，未知字段可以为空。随经历带来的反馈可通过 `feedback_records` 同包导入。
2. `select_context()` 固定库版本，再按任务选择 Skill 和依赖；提供清单记录实际披露内容。默认读取 active，比较时可显式传入候选快照。字符预算和估算 token 均保留计量方式。
3. `sample_tasks()` 在调用前保存全部计划与输入。支持同题多次和固定快照微批；每次执行、取消、异常和未知都计入分母。回调负责环境重置与硬超时，核心的线程池不提供进程隔离。
4. `learn()` 读取经历及可用于学习的反馈，构造有界原文证据包，有限补读，再调用提取、归因与提案模型。事实记忆不由 reward 改写。返回的 `candidate_ids` 是 proposal ID，可用 `store.get('candidates', id)` 读取完整候选。
5. `compare_candidates()` 先固定案例、协议和候选集合，再调用执行／评价函数；所有结果和费用入账。`ValidationRecord` 表示是否通过，`SelectionRecord` 表示最终选择，二者分开。
6. `publish()` 核对项目、完整资产、确切候选、验证／选择关系和 base/generation 后切换 active。`rollback()` 只回到同项目的已提交发布历史，并产生新代次。下一次召回使用新的 active；正在执行的任务仍用原快照。

完整参数和可运行调用见 [demo.py](demo.py)。采样次数、候选数、准入门槛、模型及证据预算均来自显式配置；本例数值不是库的全局默认。

调用方可直接使用 `evolve()` 串起步骤 4–6，由核心选择并发布通过的候选；无需自己重写演化决策。只需积累候选、暂缺评价材料时使用 `learn()`。

## 执行与反馈接口

```python
execute(request, snapshot, public_case) -> {
    "artifact": ...,  # JSON 数据，可为 null
    "events": [...],  # 可选：可观察操作／返回，不包含隐藏推理
    "execution_status": "completed",  # 也可 cancelled/timeout/budget_exhausted/adapter_error
    "usage": ...,
}
evaluate(request, execution, full_case) -> {
    "outcome": "pass",  # pass/fail/unknown
    "score": 1.0,       # unknown 时为 null
    "source": "executable",  # executable/human/llm_proxy
    "evidence": [...],
    "usage": ...,
}
```

私有评价标准不传给 `execute`。若回调回传 request/case/snapshot 身份，核心核对是否一致；原始返回和错误另行保存。标量分数和 `llm_proxy` 标签不会自行变成独立真值，实际评价依据由调用方提供。

`events` 可保留 `event_id`、`parent_event_id`、`task_revision`、`goal_id`、`call_id` 和已知来源角色。采样器统一映射本地事件与父引用；缺失、重复或循环关系保留在原文并标记派生缺口，不补造。

可选 `consumption_events=[{"skill_id": "...", "event_id": "..."}]` 必须关联已提供 Skill 和实际返回的 tool/environment 事件，才记录共用统计；仅提供 Skill 不算使用。共用统计能辅助选择，不能解释为因果收益。未知隔离和消费情况会明确保留。

用量统一为 `tokens={input_tokens,output_tokens,total_tokens}`、`monetary_cost`、`currency`；未知值为 `null`。报告去重计入执行、评分和学习调用，按币种保留已知小计与缺失数，未完成计划不能声称成本完整。

## 接入实际模型

```python
from memory_orchestrator.model import StructuredModel, make_openai_call

model = StructuredModel(
    make_openai_call(model="gpt-5.6-terra", base_url="http://localhost:8317/v1", timeout=30),
    limits={
        "max_input_chars": 100000, "max_output_chars": 16000,
        "max_output_tokens": 4000, "max_total_input_chars": 500000,
        "max_calls": 12, "max_format_repairs": 1,
    },
)
# OPENAI_API_KEY 由环境提供；不要把密钥写入任务或存储。
# learn(store, episode_ids, model, policy=explicit_learning_policy)
```

模型模板与 Schema 从总纲精确打包；SDK 不进行隐式重试，格式和纯引用／目标语义修复共用显式额度。原始输出、失败、实际 token 与未知费用保留在账本。测试替身、真实 SDK 接线、真实学习调用及 benchmark 效果是四种不同证据。

代码当前实现的是本地文件版本和函数边界。CLI、MCP、原生会话自动采集、Codex／Claude 适配与 Skill 目录同步仍属后续范围；旧 TS 保留。
