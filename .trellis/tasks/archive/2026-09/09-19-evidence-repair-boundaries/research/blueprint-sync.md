# v1.8.1 总纲与生成包同步证据

日期：2026-09-19。范围：`docs/blueprint/project-contract.json`、其生成 HTML/context，以及从同源生成的 `src/memory_orchestrator/prompts.json` / `schemas.json`。未修改 Python 产品代码、输出 schema、其它提示词或验证/发布准入；没有模型、benchmark、浏览器、提交或推送操作。

## 官方 mutation 执照

在修改源 JSON 前执行；当时原总纲为 v1.8.0，生成视图已同步。突变仅将源 `meta.version` 改为 `0.0.0`，不改其它文件。官方工具随后按原始字节快照恢复目标文件。

实际命令（等价 shell 分行，仅便于阅读）：

```bash
python3 /home/kelong/ai-workbench/tools/mutation_license.py \
  --tests 'node docs/blueprint/build.mjs check && node docs/blueprint/build.mjs verify' \
  --target docs/blueprint/project-contract.json \
  --mutate 'python3 -c '\''import json; from pathlib import Path; p=Path("docs/blueprint/project-contract.json"); c=json.loads(p.read_text()); c["meta"]["version"]="0.0.0"; p.write_text(json.dumps(c,ensure_ascii=False,indent=2)+"\n")'\'''
```

外层退出码：**0**。工具关键输出：

```text
✅ 执照发放:docs/blueprint/project-contract.json 注入错误时变红、按快照还原后回绿——该验收有资格存在。
```

这份执照验证文档来源/生成视图的一致性验收能发现改变；不代表固定 reason 字段、跨视图引用或学习效果已经通过行为验收。生成物没有重复创建独立 mutation 执照。

## 本轮源修改

- 版本更新为 **1.8.1**。
- N04/N06 说明旧完整 Feedback 视图保留，附加原 `Feedback.reason` 字符串固定视图；来源为 `feedback:<check_id>#/reason`，有独立引用/hash及字段 UTF-8 坐标，同一反馈不重复计事件或反馈分母。
- `summarize_trace_v1` revision **3** 披露精确 quote 只匹配所给 `fragment.text`；不能跨视图借文字配 ref，也不能解析/重新序列化 reason 后伪造原文。输入字段和输出 schema 保持。
- 参考 summary 单次输入上限为 **12000**；4 calls、累计输入 32000/输出 4000 及其它上限保持。
- 原有 LLM 摘要/经验/归因/必要性/提案职责与准入保持。新增义务仍标 **partial / in_progress**，此前 v1.8.0 证据不被冒充为本次通过证据。

## 同步窗口与检查

源编辑后先运行 `node docs/blueprint/build.mjs check`：**exit 0**，版本 1.8.1，保留 Q28/K14/N11、30 records、17 invariants、7 prompts、43 schemas、22 examples、7 paper sources。

生成包之前已通知根代理；根代理确认自己没有 mutation 在运行，并通知 evidence worker 暂缓新 mutation 后才开始同步。按既有 source stamp 格式生成两个 packaged JSON，再执行下列命令：

| 命令 | 实际结果 |
| --- | --- |
| `node docs/blueprint/build.mjs render` | exit 0；生成 `index.html` 与 `context.md` |
| `node docs/blueprint/build.mjs verify` | exit 0；源/模板与生成视图一致 |
| `PYTHONPATH=src:tests .venv/bin/python -m unittest test_memory_store.StoreTests.test_packaged_contracts_exactly_match_current_source -v` | exit 0；1/1 通过，0.030s；包括 source version/hash、schema/prompt 内容和源中示例校验 |

该次同步源 SHA-256：

```text
29e0e162784907e00bd3cf9889af715accfc4ad5fe262f39f4cb72e42a11939e
```

生成产物：HTML **356605 bytes**，context **15101 bytes**。同步结束后立即通知根代理恢复其它测试/mutation。

## 当前证据边界

本文件只记录已执行的文档和生成包检查。根代理随后告知 evidence 新 14 项通过，但旧跨 disk/inline 选择一致性仍有 1 项失败正在取证；本文件没有据此标记机制完成，也没有继续修改总纲状态。待根代理提供完整实施证据后，才进行状态更新及再次同源生成。真实模型学习到哪一步、是否产生可用候选及效果，均另由运行证据说明。

## 后续回填与新集成回归

后续已读取 `all-tests.txt` 的 **memory_* 352/352，74.798s**、`feedback-text-implementation.md` 的 **新反馈15/15** 与 `summary-repair-green.txt` 的 **修复容量4/4**；这些集合有重叠，不相加。按根代理指令曾完成 N04/N06 机制状态回填，源指纹为 `5b93dd83796d97362d6d171e6ab7354926aeb5e9fbd5e61ce41b39417b08fed5`，当次 render/verify/sourcepack 一致检查均 exit 0。

根代理随后报告：GDPevo 适配 33 项出现 **1 项实质证据选择回归，磁盘包缺 orders 类别**，需重审双反馈正文对预算的挤占；此项不同于此前容量前提不一致的等价测试。收到纠正后立即将 N04/N06 本次义务恢复 **partial**，保留已通过的单项机制证据，明确“整体集成未通过、真实回放暂停”。没有修改 prompt/schema 或放松验证。

纠正后的 render、verify、sourcepack 一致测试均 **exit 0**；一致测试 1/1，0.031s。当前源指纹：

```text
d1c013c91e7d034ede56d838fa553733d19ee8320942805cf235d69e025226d3
```

当前 HTML **358679 bytes**，context **15835 bytes**。这只是部分完成状态的同源同步通过，不是集成问题关闭或真实学习成功。

## 最终共享额度修正与状态同步

随后按源码及 `feedback-text-implementation.md` 核对了一般性修复：同 episode/check_id 的 full/reason 合并为一个 selection unit，共享原单条反馈正文额度；full 控制正文最多占一半，过长时取精确 outcome 原文，极小时 reason 优先并有界保留 full 目录。reason 使用剩余额度，实际 metadata、目录及正文继续计入原总预算；显式单视图不拉入兄弟，未新增配置或改业务断言。

已读取 `all-tests-final.txt`：**test_*.py 391/391，85.055s，OK**。实施记录另含新增反馈 **21/21**、原 42k GDPevo 业务断言恢复，以及 **7 个共享额度 post-mutation** 通过。各集合重叠，不相加。此前的 orders 选择回归已经由共享预算机制修复，历史失败和取证过程保留在上节及实施报告中。

据此将 N04/N06 本次机制状态最终更新为 implemented，清空当前阻塞项，保留真实学习流程、模型语义和收益需独立运行证据的边界。summary revision 3、其它 prompt、schema 及准入未变。render、verify、sourcepack 一致测试均 **exit 0**；sourcepack 1/1，0.030s。

在根代理确认无其它测试/模型调用的窗口内，再次执行上文完全相同的官方 source JSON mutation 命令，作为修改后复验：**exit 0**，工具再次报告“注入错误时变红、按快照还原后回绿”。随后 `node docs/blueprint/build.mjs verify` 再次 **exit 0**，证明恢复后的源与生成视图一致。

最终 v1.8.1 源 SHA-256：

```text
2985f0af11ff7f05fbcf6612aa27c7ea0140230fadd79cd88884273c7523afa9
```

最终 HTML **359920 bytes**，context **15927 bytes**。未运行模型或 benchmark；真实回放结果另记实验报告，不以本轮机制全绿推断学习效果。
