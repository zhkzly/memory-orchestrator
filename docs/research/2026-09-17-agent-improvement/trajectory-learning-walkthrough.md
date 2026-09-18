# 从 Coding Agent 轨迹到可复用经验：数据与最小实现

核对日期：2026-09-18。本地已检查 Codex CLI 0.154.0、Claude Code 2.1.274 的帮助及版本；已读取官方文档与 SkillFlow 固定提交。没有启动新的模型任务。本文给出教学数据和拟议实现顺序，不能当作已实现的采集器或效果实验。

## 1. 现成 Agent 有哪些轨迹入口

- **Codex CLI**：`codex exec --json` 输出 JSONL 运行事件，官方列有命令执行、文件变更、MCP 调用和 Agent 消息等 item。仅保存最后一条回复不等于保存轨迹。[官方 OpenAI 文档](https://learn.chatgpt.com/docs/non-interactive-mode#make-output-machine-readable)
- **Claude Code**：`--output-format stream-json --verbose` 提供结构化输出；SDK 可流式接收工具输入，或从既有会话读取消息。交互会话也有持久化记录。[CLI](https://code.claude.com/docs/en/headless)、[SDK 会话](https://code.claude.com/docs/en/agent-sdk/sessions)
- **Claude 工具 Hook**：PostToolUse 含 tool_input、tool_response 和 tool_use_id；失败事件需另接 PostToolUseFailure。只监听成功事件会漏掉失败经历。[官方 Hook](https://code.claude.com/docs/en/hooks#posttooluse)
- **本次会话的本地检查**：只检查当前 Codex 会话日志的工具项字段，确认 function_call / custom_tool_call 及对应 output 记录具有 call_id 和输入/输出字段。没有导出会话内容。该内部日志格式与公开 exec JSONL 是两种格式，不能共用未经验证的解析器。

可以采用的采集命令示意（本轮未执行）：

```bash
codex exec --json "检查这个仓库的测试入口" > codex.events.jsonl
claude -p "检查这个仓库的测试入口" --output-format stream-json --verbose > claude.events.jsonl
```

原始事件保留原样，stdout 与 stderr 分开。若需 token 级片段，Claude 另有 include-partial-messages；做工具级学习通常先使用完整消息，避免重复统计片段与完成消息。参数支持不等于已完成端到端录制验证。

## 2. 本项目所说的轨迹

轨迹记录任务执行时可观察的行为：任务要求、可见消息、工具名与参数、工具返回、代码/文件变化和终止状态。项目验收反馈另行附加，并注明来源和对应的代码版本。

不要求取得完整模型私有推理，也不要求取得权重、梯度或 logprob。即使某客户端提供公开推理摘要，也不能把它当成完整内部思考；后生成的反思同样只是一个分析结果。

三种资料要区别：

| 层 | 内容 | 谁产生 |
| --- | --- | --- |
| 原生记录 | JSONL 事件、会话消息、工具返回 | Codex/Claude 及其运行环境 |
| 任务证据 | 起始状态、实际文件差异、测试工件、独立验收或 review | 外层采集器、测试系统、维护者 |
| 学习视图 | 与问题相关的片段、来源引用、现有 Skill、结果 | 本项目的适配与选择流程 |

CLI 运行结束、tool exit code 为 0、Agent 自称完成，都不能自动变成任务成功标签。测试通过也只说明被执行的测试通过。真正的结果可以是 pass、fail 或 unknown，并保留评价者及判定范围。

环境的完整真实状态、每次模型的完整实际输入、被截断的工具全文等，未必出现在原生事件里。缺失应标注，不能靠摘要补造。若要重放，需要另外保存起始工作区、配置和必要工件。

## 3. 一份教学用规范化 Episode

以下是拟议的统一格式示意；它不等于 Codex/Claude 原生字段。机器可读版见 [trajectory-learning.example.json](trajectory-learning.example.json)。

```json
{
  "illustrative_example": true,
  "note": "教学示例；不是实测记录，也不是任一客户端的原生事件 schema。",
  "episode_id": "example-api-field-001",
  "task": {
    "instruction": "新增用户备注字段，并确保服务重启后仍能读到。"
  },
  "execution": {
    "agent": "codex-or-claude-code",
    "repo_snapshot": "example-before",
    "skill_version": "example-v0"
  },
  "events": [
    {
      "event_id": "e1",
      "type": "file_change",
      "paths": [
        "src/api.py"
      ],
      "diff_ref": "example:patch"
    },
    {
      "event_id": "e2",
      "type": "tool_call",
      "call_id": "c1",
      "tool": "shell",
      "arguments": {
        "command": "pytest tests/test_api.py -q"
      }
    },
    {
      "event_id": "e3",
      "type": "tool_result",
      "call_id": "c1",
      "exit_code": 0,
      "output": "4 passed"
    },
    {
      "event_id": "e4",
      "type": "assistant_message",
      "text": "接口测试通过，修改完成。"
    }
  ],
  "feedback": [
    {
      "feedback_id": "f1",
      "source": "independent_test",
      "status": "failed",
      "target_snapshot": "example-after",
      "detail": "重启后备注字段丢失。"
    }
  ],
  "completeness": {
    "tool_pairs_complete": true,
    "example_only": true
  }
}
```

这里已有足够信息提出“验证只覆盖了一部分行为”的候选教训；还不足以直接确定缺陷究竟在写入、序列化还是读取代码。具体归因需要源码和额外测试证据。

原始轨迹与后续反馈分开：测试可能在 Agent 结束后才执行，必须绑定正确的任务和产物版本，不能把后来已修改的代码结果误记给旧轨迹。

## 4. 论文怎样消费这些数据

### SkillFlow：规范化步骤与结果 → 文件补丁

实际代码读取 `trajectory.json` 的 steps，选取 agent_message、tool_calls、env_outputs；再与任务结果、verifier 报告合成 TrialOutcome。当前 Skill 文件快照也进入模型输入，模型输出 summary、upsert_files、delete_paths。

官方实现确实包含 Claude Code 原生日志到统一轨迹的解析，按调用 ID 将返回挂到对应步骤。它通过原生 CLI 做任务，更新器是另外一次模型调用。因此使用现成 Agent 不妨碍经验更新。

来源：[解析器](https://github.com/ZhangZi-a/SkillFlow/blob/7b49ff5a7e26cd7706e959bfa0dba4746d18440d/analysis/skill_usage_parser.py#L274)、[压缩与结果抽取](https://github.com/ZhangZi-a/SkillFlow/blob/7b49ff5a7e26cd7706e959bfa0dba4746d18440d/libs/skill_evolution/patcher.py#L97)、[更新提示词](https://github.com/ZhangZi-a/SkillFlow/blob/7b49ff5a7e26cd7706e959bfa0dba4746d18440d/libs/skill_evolution/patcher.py#L310)。

它会截短参数与工具结果，因而学习视图不是无损档案。也没有逐补丁的独立回归准入；这与额外产品治理机制需要分开。

### ReasoningBank：经历 → 策略记忆

任务及轨迹交给 LLM judge 产生代理成功/失败标签，再按结果提炼有标题、描述和内容的策略条目。后续任务按相关性检索，放入输入上下文。该文的基本 consolidation 是追加；judge 噪声是论文承认的限制。[论文 §3.2](https://arxiv.org/html/2509.25140v2)

### Evo-Harness：失败反思 → 批次整理后的指导

Solver 根据执行上下文和反馈提出候选经验；Evolver 汇总一批候选，对现有指导增加、合并、修订或跳过，再服务之后的任务。检查过的 CL 代码使用原 Solver 会话生成反思；若用外部 CLI 日志替代这个上下文，要明确这是适配，并验证信息是否足够。[论文 §3](https://arxiv.org/html/2608.15071)、[实现](https://github.com/A-EVO-Lab/a-evolve/blob/3c7c7b8c62a3f07da1d4407aa03f0ca079954bcf/evo_harness/cl_bench.py#L1187)

## 5. “学习”在本项目中实际更新什么

这里首先更新外部的程序性指导，模型权重保持原样：

```text
任务 A：轨迹 + 外部反馈
→ 分析可复用的条件与做法
→ 对现有 Skill 生成小补丁
→ 验证/选择一个版本
→ 任务 B：原生 Agent 读取新版 Skill 后执行
→ 用任务 B 的独立结果判断经验有没有用
```

从上面的教学案例，可以提出候选指导：

> 修改需要持久化的字段时，核对写入、序列化和重新读取路径；接口内存态测试通过后，还需要适用的关闭重开验收。

这句话是本次编写的教学候选，不是已验证的一般规律。适用条件与执行代价要检查，不能机械要求所有任务重跑全部测试。

更新器的最小输入可以是：原任务要求、相关事件与原始引用、外部反馈、当前 Skill 快照。要求输出适用情形、支持证据、操作步骤、例外和建议改动；证据不足允许不更新。这里模型做的是经验归纳，程序负责数据绑定、工件读写与版本，而独立任务结果负责检验收益。

未来若做 SFT/RL，才进入另一条参数训练链；不能把生成 Markdown Skill 称为已经训练了 Codex/Claude 的权重，也不能把有日志称为已经具备合格训练数据。

## 6. 最小实现顺序

1. **先采集一个完整任务记录。** 一个客户端、一项受控任务；保存任务输入、原始事件、起始工作区标识、增量文件变化、终止信息和验收结果。起始脏状态与未跟踪文件不能丢，也不能将用户并发改动全部归给 Agent。
2. **再做只读规范化。** 按 call_id 配对请求/返回，保留并行顺序、父子 Agent 关系和缺失/截断标志。完整原文留存，面向模型的片段可引用原文。不同客户端各自适配，不能按消息相邻顺序猜配对。
3. **再离线提炼一次经验。** 从有明确反馈的记录生成可审阅 Skill patch。此阶段先看是否有证据、有适用范围、是否混入一次性答案；不因为 JSON 合法就标记事实正确。
4. **在新任务上验证消费与效果。** 使用新会话，固定原生记忆及配置；分别记录可用、读取、相关行为和最终结果。先比较无更新、静态短清单，再逐步接现成强方法。
5. **最后自动接会话生命周期。** 在采集和规范化可靠后接 Hook/SDK，不先假定所有 UI 会话都有同样字段，或事件结束就有业务成功反馈。

第一步验收只问：能否从记录看清任务、实际工具调用与返回、变更工件和判定来源；能否保留失败及缺失，而不是只留下“已完成”的摘要。它不证明长期收益。

## 7. 当前仓库的具体缺口

当前 `ingestSessionFile` 保存摘要文本；`summarizeSessionTranscript` 主要提取 Decision/TODO/Evidence 等标记行。它们尚未把原生工具事件与外部任务判定规范化为上述记录。

因此，当前最先需要补的是**轨迹采集/适配与反馈绑定**。有了可信输入，才有依据实现经验生成。现成 Agent 可以继续负责执行任务，不需要为了拿轨迹先重写一套 Agent。

## 8. 本轮证据与边界

已做：本机版本/帮助检查、官方文档核对、当前会话工具项字段检查、论文源码阅读、教学数据结构展示。仅生成本地说明和示例。

未做：新模型调用、真实 CLI 录制 smoke、安装 Hook/SDK、产品解析器实现、经验写入或效果评测。事件接口存在与端到端采集已验收是两种状态。
