# 当前 Python 核心接口（实施交接）

本轮没有 native Agent/CLI/MCP/runner。只实现以下普通 Python 调用。所有数据 UTF-8 JSON；原文不可变；root 显式传入。模型 Draft 使用总纲的 5 份模型输出 schema，其余宿主记录按这里的实际数据流实现，不强套旧受控运行器字段。

## 公共工具（common.py）

DomainError(code,message,details=None)，digest(JSON或原文)，new_id(prefix)，now_iso()，validate(schema_name,value)；load_contracts() 返回打包 prompts 和模型 schema。validate 返回深拷贝，失败带全部字段路径。不将整个总纲当运行时依赖。

## Store（store.py）

Store(root)，方法：
- ensure_project(project) / active(project) -> {project,snapshot_id,generation,release_id}。
- snapshot(snapshot_id) -> {snapshot_id,project,parent,skills:{skill_id:Skill},assets:{relative_path:text}}；hash 覆盖除 snapshot_id 外的完整 payload。
- put(kind,record_id,record)、get(kind,record_id)、list(kind,project=None)：追加记录，同 ID 异值拒绝；kind 为本轮明确集合。
- remember(kind,content,source,project=None,memory_id=None) -> fact。kind=user|project；user 为全局，project 必填；明确纠正保留修订。学习器不调用此方法。
- facts(project,vault_root=None) -> {user:[],project:[],errors:[]}。兼容旧 JSON frontmatter/Claim，只读 verified personal/project，精确项目匹配，读取不写旧文件。
- context(task,project,vault_root=None,snapshot_id=None,max_skills=3,max_chars=12000) -> {id,project,task,snapshot_id,selected_skills:[...],facts:{...},text,excluded:[],...}；保存该不可变 context，便于 record 回传 id。公开 recall 默认 active；内部评价可给显式 candidate。依赖闭包/冲突/预算不能拆坏，提供不冒充采用。
- create_candidate(project,base_snapshot_id,patch_draft,allowed_targets=None) -> {status:candidate|noop,id,project,base_snapshot_id,snapshot_id?}。使用 PatchDraft，ADD 分配 ID/revision；Skill flatten 保存 steps=[{rule_id,text}]；project 是宿主字段，模型不能扩大。new:<slug> 在同包解析，assets key=<skill_id>/<relative_path>，限制在 scripts/references/templates。
- publish(validation_id,expected_generation) -> release。验证记录必须 accepted/project/base_snapshot_id/candidate_snapshot_id 匹配当前状态、包含全部通过 gates 和完整快照；唯一发布者以锁+原子 active 文件提交。
- rollback(project,snapshot_id,expected_generation,reason) -> release，只允许该项目已发布历史且内容完整；generation 递增。

## MemorySystem（engine.py，main 实现）

MemorySystem(root,model=None) 持有 Store。公开方法：remember、recall、record、add_feedback、learn、evaluate、publish、rollback。

record(task,project,observations,feedback=None,task_id=None,task_revision=None,context_id=None,source="caller_submission") -> episode。observations 为 text 或 {kind,text,...} 列表，宿主分配 event_id。已知 context 必须存在且属于同项目；不知道保持 null。task_id 不给时保持未知，不推断为独立任务。

episode={id,project,task,task_id:null|string,task_revision:null|string,context_id:null|string,snapshot_id:null|string,source,events:[{event_id,kind,text,source,...}],feedback:[],capture_gaps:[],created_at}。record 原始提交不可变；add_feedback(episode_id,feedback,state_ref=None) 写新反馈记录，读取/学习时归并，不改旧字节。反馈缺失合法，不要求 RunGroupPlan/manifest/产物。

learn(episode_ids,candidates=1,policy=None) -> {status,experience_ids,candidate_ids,diagnosis,usage_ids,errors}；批次须同项目；原始 task/run 支持数量分别计算，不计复制引用。候选不自动发布。多候选来自同一个 base。

## learning.py（证据+模型学习）

- build_packet(episodes,max_chars=36000) -> {id,fragments:[{ref_id,episode_id,kind,text,source,raw_hash}],readable_ref_catalog:[],omitted_refs:[],gaps:[],...}。选择要求/反馈/关键失败操作及后续恢复，不全拼冗长原文；每条经验引用来自已提供片段。
- expand_packet(packet,episodes,requests,max_chars) -> packet，目录只用于请求补读，不能直接作为事实依据。
- find_related(experiences,task,project,limit=4) -> list，简单确定性检索/去重，保留反例与边界。
- ModelClient(model="gpt-5.6-terra",base_url="http://localhost:8317/v1",timeout=60,max_calls=...) 使用 OpenAI SDK；generate(prompt_id,inputs,output_schema) -> {value,usage,raw_response}；json_object + 本地 schema；无隐藏重试；错误/截断/预算分别记录。
- learn_from_episodes(episodes,snapshot,related_experiences,model,policy=None) -> {status,experiences:[ExperienceDraft],diagnosis:DiagnosisDraft|null,patch:PatchDraft|null,usage:[],errors:[]}；三个主要模型节点提取/归因/提案；一次格式修复，最多有限补读，缺证可 abstain。输入来源 snapshot/context/反馈可缺失，不伪造原生运行记录。

## evaluation.py

validate_candidate(store,project,candidate_id,cases,evaluator,evaluator_id,repeats=1,max_parallel=1,policy=None) -> validation。candidate_id 指 proposals 中 create_candidate 返回 id。

cases=[{id,split:target|regression|transfer,data:JSON}]。回调 evaluator(snapshot,case) 返回 {outcome:pass|fail|unknown,score:number|null,evidence_refs:[],usage?:dict}。实际执行/评分正确性归调用方；核心记录为 caller-supplied evaluator，不声称自动获得独立真值/隔离。

验证记录：{id,project,base_snapshot_id,candidate_snapshot_id,expected_generation,evaluator_id,cases_hash,policy,results:[{case_id,split,repeat,snapshot_id,outcome,score,evidence_refs,error?,usage}],gates:[{name,passed,reason}],status:accepted|rejected|unknown,metrics:{...},usage:[...],created_at}。默认至少 target/regression；目标平均改善，回归不下降；transfer 若提供则检查不下降，不强制额外严格提升。任一未知/缺结果不 accepted。可保留简单 policy 的 min_gain/max_regression/required_splits/max_calls，不建设通用策略语言。

评价先保存 validations，再允许 publish(validation.id,expected_generation)。验证调用不触发 learn，不修改 base/candidate；全部调用（含异常）保留并统计成本，模型/评测缺失用量不算 0。

## 当前约束

- 不新增客户端适配、CLI、MCP、任务进程框架；直接 Python 样例是消费者。
- 不能为了满足旧 schema 造假 snapshot/context/feedback。项目范围、已知 context round-trip 和延迟反馈是实际当前需求。
- 公共签名如需变更先交 main 统一，不能几个 worker 各定义一套。
