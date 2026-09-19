# 提示词与上下文审查：旧真实 canary 与本轮观测项

状态：只读审查；没有改产品、schema、提示词或阈值，没有发模型请求。本文先记录证据，GDPevo开发样本仍须保持当前prompts运行；任何修正等待新实际messages后定案。

## 1. 审查范围与证据边界

- 当前总纲v1.7.0的6个prompt；`model.py`和`learning.py`；沿check_plan实际消费者只读核对`verification.py`。
- 旧真实工件：`.trellis/tasks/archive/2026-09/09-18-complete-memory-evolution/research/live-canary/{reports,verification_plans,verification_records,verification_materials,summary}.json`。
- reports共5项，其中4项是模型调用、1项是宿主项目报告。实际调用次序为extract→maintain→diagnose→propose；goal_binding/proxy_judge本次旧canary未调用，不能据此断言这两个节点真实语义质量。
- 旧canary是实际gpt-5.6-terra Teacher调用配合本地CSV执行/检查，不是GDPevo任务结果。本轮尚没有新的benchmark测量。
- 旧调用的model.py、learning.py SHA与当前文件完全一致；4个prompt_digest逐项匹配。把当前schemas/prompts bundle的source元数据换回summary.contract_source后，完整文件SHA均与旧summary.source_hashes精确匹配，证明实际模板/schema正文未变。
- reports保存原inputs、prompt_digest、模型输出/用量，未单独保存SDK messages全文。这里按同一渲染代码、同一schema与顺序预算重建；4次序列化字符数均与记录精确相同。下面消息SHA属于这次可复现的离线重建，不冒充额外抓到的网络请求。

## 2. 第一条因果链：为什么会有必需的check_ref:null

旧任务正文明确要求：`empty numeric cells become null`，并明确提到执行器读取`references/csv-policy.json`中的`preserve_string_columns`和`empty_numeric_as_null`。

但目录仅有：

| check_ref | purpose | 实际公开输入 | 没覆盖的行为 |
| --- | --- | --- | --- |
| case:leading-zeros | target | id=001，amount=10 | 没有空number |
| case:numeric-regression | regression | id=a，amount=2.5 | 没有空number |

两次学习执行也都是同一leading-zeros输入的失败，没有空number样例。模型在extract里正确区分了“任务声明此规则”与“执行未验证此规则”，maintenance对这两类经验返回NOOP，均没有捏造成功证据。

实际链条如下：

1. extract输出两项经验：已观察到的字符串ID数值化失败；仅在任务声明中存在、尚未实测的空数值规则。
2. diagnose把两者都放入expected_behavior，并生成空number检查，明确`check_ref:null`、`purpose:transfer`、目录缺材料；necessity仍为proceed。
3. propose收到的`evaluation_scope`是`local CSV repair; target and regression, no transfer claim`，但按提示保留诊断检查，仍实现empty_numeric_as_null并保留null项，文字说明“仅claim target/regression”。
4. `requirements_for`汇集诊断和提案的全部检查义务。两个null分别成为两条missing，另外4条绑定到已有的两个case。
5. verification_records显示4条pass、2条unknown，整体unknown；release_count=0。原质量检查通过不能覆盖缺失义务，发布阻断正确。

**因此不能把null本身归为幻觉或直接禁止它。** 此处确实缺少验证所承诺行为的材料。模型将其命名为transfer也不是阻断的必要条件：任何purpose的必需检查缺材料都会unknown。

### F1：确认的输入/提示词交接缺口

- N07没有evaluation_scope字段；`learning.py:497`组装诊断输入，只有N08在`:552`才得到scope。运行材料有评价范围，但产生检查义务的最早节点看不到它。
- diagnose/propose说明“缺材料用null”，但没有直接告诉模型：**check_plan每一项都会成为阻止发布的必需义务，诊断与提案取并集；null不是可忽略的未来TODO。** JSON Schema描述也只说缺材料，没有发布后果。
- N08同时收到“不能添加全局迁移门槛”和“保留诊断已提出义务”。本例前一节点已承诺未验证行为，后一节点没有权限靠删检查修复；“不claim transfer”的自然语言声明也不会解除义务。
- 依据：`learning.py:189`允许null通过纯校验；`:519`已有needs_evidence分支；`verification.py:62`汇集义务，`:83`缺材料，`:168`合并unknown。模型输出均一次通过，未进入格式修复；增加重试数解决不了这次材料缺口。

这里能确认“范围披露晚、义务语义未完整披露”；尚不能确认改提示词就会得到一个合理可发布候选。原TaskSpec本身要求空数值行为，补开发材料也可能是正确处理，而不是缩scope。

### 有界修正候选（尚未执行）

1. 在N07就提供与N08相同的本轮评价范围/受保护检查说明；明确所有check_plan项都是本候选的发布义务。
2. 明确区分：当前行为必须验证却无材料→保留null并needs_evidence；只属于范围外未来猜想→放现有unknowns/alternatives，不能同时在当前Skill里承诺实现它却移出必需检查。
3. 若开发任务本来就要求该行为，由可信调用方根据公开任务规范补充最小检查材料，固定规则和数据后重测。不能由Teacher编造gold，不能借final样本补材料。
4. 保留N09/N10门和诊断义务并集。不能让propose删null、改成另一个purpose、换一个不等价check_ref或降低门槛来取得发布。

## 3. 实际上下文计量

单位严格分开：字符数是紧凑JSON序列化后的字符；tokens为provider实报。4次输入共80,582字符、23,956 tokens，输出共3,791 tokens；没有修复调用。最大单次输入34,075/120,000字符，总输入80,582/480,000字符。**没有上下文预算耗尽证据，也不能据此声称context rot。**

| 实际节点 | SDK messages序列化字符 | provider输入tokens | user文本字符 | 输出schema字符 / user占比 | 主要输入块字符 |
| --- | ---: | ---: | ---: | --- | --- |
| extract | 21,378 | 6,531 | 18,486 | 2,882 / 15.6% | evidence_packet 11,916；feedback 1,337；另传catalog 1,111；任务身份405 |
| maintain | 9,506 | 2,853 | 8,517 | 1,668 / 19.6% | new_experiences 5,896；comparison_evidence 531；limits49 |
| diagnose | 34,075 | 9,776 | 29,958 | 2,969 / 9.9% | evidence_packets 11,918；相关经验封装6,385；experiences 3,663；source_provenance 1,369；feedback1,337；检查目录1,279 |
| propose | 15,623 | 4,796 | 13,356 | 7,381 / 55.3% | change_intent2,954；检查目录1,279；操作限制688；scope60 |

重建messages SHA-256：

- extract：`743a1fe6651faebd025649e3edced283d5a0a6ca69cfd28174d3c99f2287f620`
- maintain：`5fe2733ba2306f1d65605c4dd177969f89b4c3884372d4b041fb326d48eb855a`
- diagnose：`09808a80af119368f2a68136305aba5f1d887bad61d97f68e7f35205e92da3e7`
- propose：`1ea4137105057556319f6857eff5f43a65a81125eecb75b379551c344b39d749`

### F2：确认存在冗余；质量影响尚未测量

- extract的readable_ref_catalog以完全相同内容既放在packet内又单列，原始JSON重复1,111字符（实际messages还增加转义开销）。代码位置`learning.py:416`。
- diagnose的2项experiences又逐字出现在related_experiences[*].draft中；后者不是新增旧反例，而是刚写入的同两项经验。`related_experiences`整体6,272字符。保留来源计数/边界有必要，重复全部正文不一定必要。
- target_snapshot.skills、related_skills_and_relations.skills、existing_capability_catalog.skills是同一view的三份输入。本例都是空库，所以尚未造成明显体积；库变大后的增长是静态可预测问题，不能冒充本次已发生故障。
- 8个fragment的实际text合计3,200字符，完整packet11,916字符；完整fragments对象8,235字符。引用、hash、范围、身份、关系和目录占了大量字符。不能把这些全当垃圾删除：要保留可读引用/范围/来源/缺口，可考虑宿主保留完整审计数据、模型只接单一精简投影。
- 两条feedback片段从完整JSON的中部开始，其中一个以截断的hash尾部开头；真正的reason被嵌成转义JSON字符串。同一批绑定元数据又在available_feedback出现。此次模型正确读到了actual/expected，没有证据表明此形状造成错误；但应在GDPevo长反馈里观察有效诊断文本是否被结构元数据挤掉。
- propose的一半以上user文本是完整PatchDraft schema。JSON Schema必要，不建议先去掉校验或隐去约束。若新实测出现格式/注意力问题，可提供受当前允许操作约束的清晰合法例子或更紧凑的同义schema呈现；必须保持本地校验等价，不能只展示ADD却实际要求复杂PATCH字段。

优先级：先修已定位的信息缺失/义务语义，再用同一真实输入对照去重。此轮不要同时改Scope、schema、检索和多个prompt后把变化都归因于“上下文优化”。

## 4. 六个节点逐一对账

| 节点 | 已核实的输入→消费 | 确认边界/待观察项 |
| --- | --- | --- |
| extract | 原始片段、身份、反馈、相关经验和可补读目录；引用只准已给正文；可请求补读 | 本次分开观察失败和未实测规则；目录重复、反馈JSON包装偏重。没有成功对照不能把经验说成因果结论 |
| diagnose | 经验+原证据+当前库+来源/消费未知；necessity决定noop/缺证/提案 | 缺当前scope、check_plan生命周期披露不全。当前scope只给下一节点；不是要允许删除已承诺检查 |
| propose | 诊断、允许编辑内容、原规则ID/资产路径/预算、目录 | 本次ADD+UPSERT一次合法成功；全schema占55.3%。不能据一个ADD样例推断复杂PATCH已获真实模型验证 |
| goal_binding | 用户锚点、历史目标目录、窗口/补读限额；旁注不覆盖observed身份 | 旧canary没调用。新benchmark受控单任务不应为了“跑全六节点”人为调用它；后续若有真实缺标用户事件再测 |
| proxy_judge | 明确允许标准+有界证据；来源固定llm_proxy | 旧canary没调用；GDPevo有官方评分器时应使用官方反馈，不以proxy代替独立效果证据 |
| maintain | 新/旧经验、可比较对和引用、现有关系、动作预算；关系参与后续召回 | 本次对互补经验NOOP且保留未验证空数值的不确定性，未错误合并。没有真实重复/冲突样本，不能推断语义去重准确率 |

所有6个prompt当前只渲染system、输入和JSON Schema，没有作为消息内容发送的具体合法输出实例；repo里的examples不等于模型实际看过。当前4次返回都一次合法，故“缺例子导致此次失败”不成立。可在新开发失败暴露具体歧义时，补一个经过同一pure check验证的最小合法例子，而不是先灌完整教程。

## 5. 可修复反馈是否可执行

- `model.py:197`在同一格式修复/总调用预算内运行pure check；`:205`保留原指令和被拒JSON，再附全部诊断及当前余量。目标错误已能给actual/allowed和ADD需targets=[]的明确修正。
- `_check_verification_refs`检查未知ref和purpose不匹配，但显式接受null。对此应保持诚实缺证；当前缺少的是“缺证会阻止发布”的前置解释，不是应制造一个格式错误强迫改成假ref。
- Schema的check_plan.required目前不含check_ref，运行时和prompt却要求显式字段或null。该确定性额外约束已通过prompt披露并在pure check内可修复；这是可进一步同源对齐的静态点，本轮没有缺字段输出，暂不归为实测故障。
- 4次真实调用都只有attempt=1，没有解析、引用、目标或补读修复。检查缺证直到验证阶段才落为unknown；旧流程不会把该结果自动送回Teacher继续修改，不能把“max_format_repairs=1”误写成能修复业务验收缺证。

## 6. 单轨迹、重复次数与归因证据

- 这里是2条运行轨迹，但只有1个独立已知任务leading-zeros，两个输入/产物一致。不是2个独立任务，也没有成功轨迹或区别性对照支持唯一根因。
- 宿主在related经验中实际给出了source_episode_count=2、known_task_count=1、known_support_task_count=1；packet.gaps明确环境重置/独立可比性未知，消费日志也是unknown。
- diagnose实际保留了“执行器未应用资产/解析序列化偏差/相同任务重复不证明唯一原因”等替代解释；没有把“提供空库”误写为某条旧Skill造成失败。这部分本次表现合理。
- 第一条经验的unknown_task_episode_ids还含这两个已知任务Episode，因为部分host结果事件缺task_id。它是事件级缺失与任务级已知混合的保守统计，可能让模型理解成本上升；尚无因果误判证据。新日志宜明确显示“1个任务、2次重复、哪些事件身份缺失”，不要把unknown数量当额外任务。
- 对GDPevo的下一步应观察跨任务成功/失败对照是否进入当前可见包、哪条规则来自哪项反馈。不能为了数量好看强迫每次多采样，也不能把同题重复当迁移证据。

## 7. 本轮小批量应保存什么，怎样有界修正

1. 每次实际SDK调用保存完整messages（含repair轮）、prompt/schema/可见材料hash、各输入块字符、实报tokens/耗时/费用、余量；0-call预算拒绝独立记录。当前root已计划这样做，不用本次重建替代新抓取。
2. 先保留未改prompt的开发样本。给每个null check追溯到用户当前要求、候选新增行为或范围外猜想；查看当时catalog究竟缺什么。先定位最早分歧，别只统计JSON成功率。
3. 若仍复现F1，先仅披露N07 scope与义务语义，用相同开发数据/评分器/预算复测；保持null/needs_evidence与发布门合法存在。若确需材料，由可信开发材料补齐，不能用final来补。
4. 若context冗余明显，再单独比较相同证据的紧凑投影，保留所有必要引用、反例、范围和缺口；观察有效输出、修复率、输入tokens和总维护成本，不单看压缩百分比。
5. 正式保留探测只报告，不用失败再改提示词；这里四次旧真实调用不足以证明新的通用优化收益。

操作风险另记：旧diagnose调用29.26秒，timeout为30秒，虽未超时但裕量很小。新任务更长时需在运行前显式选择时限/调用预算；不能把网络或超时失败算为任务失败，也不能靠隐式重试掩盖成本。

## 8. 真实GDPevo baseline：已确认的证据供给缺口

新工件：`research/pilot/baseline/result.json`、`baseline/teacher-inputs/01-extract_v1.json`、`pilot/calls/call_0006.start.json`。Actor实际5个SDK调用/67个工具调用；官方得分5/17。Teacher只有extract尝试，45.05秒APITimeoutError、无输出/usage、没有经验/候选/发布，不能把Actor任务失败与Teacher传输失败混计。

实际SDK messages共61,004紧凑JSON字符，整个payload为61,087，hash `40c825e6904a95d3fecf56f52c063a3262f725e30442f30bc5323f0284dfd0fc`。packet为41,582紧凑字符，未超42,000预算；teacher-inputs.blocks记录43,089采用带空格JSON，口径不同。catalog紧凑6,964字符（普通JSON7,359）在packet内与单独input中重复。

### 输入究竟有/没有什么

原事件136条；19个fragment包含17个事件、1个任务元数据和1个Feedback。正文12,380字符，fragments连元数据26,618，relations5,829。Task总说明完整，出现三次相近内容（任务元数据、host instruction、read_input prompt结果）。

| 原轨迹工具类别 | 实际结果数 | 初始包已给结果正文数 |
| --- | ---: | ---: |
| read_input | 3 | 3（模板和memo有截断） |
| orders | 8 | 1 |
| customers | 8 | 0 |
| products | 19 | 0 |
| inventory | 20 | 0 |
| shipping | 8 | 0 |
| submit_answer | 1 | 0（有提交动作和host最终artifact片段） |

不存在独立warehouses GET，因此不能把“没有warehouse结果”都归咎于packer。这里能直接证实的是：实际已获取的库存/产品/客户结果没有送入Teacher。

- 官方反馈可见片段包含全部8个SP、matched和weight、earned_weight=5、total_weight=17。失败类别为库存/shortage、inactive/low-stock、final decisions、next actions、summary；不是评分反馈整体丢失。
- answer_template原工具结果4,540字符，给了[143,1943)中部，后面的部分next_action枚举、shipping字段和summary完整要求不在此段。memo原结果1,785字符，因业务词exception从717开始，丢了包含8个order_ids的前部。
- 原目录11项全是action（局部位置21–41），没有任何result，也没有所选模板、memo、final artifact或Feedback的后续范围。目录无正文/语义预览，只有call ID/位置/引用等元数据。
- 6个已提供GET的返回既不在正文，也不在目录。relations诚实标partial，但没有给可用补读入口。由于expand只接受本目录且不刷新新前沿，模型也不能通过请求这些已知存在但未列出的结果补齐。

首选择偏差在`evidence.py`原rank：action固定先于普通observation，同层按早期position填；catalog又重复同一ordered，因此两个阶段都优先请求而非执行结果。裸exception使customer_exception/业务exception成为假失败提示，另有error:null的假锚点。这是可证的输入选择问题，尚不是超时成因。

### 同payload容量探针

根随后保存的`pilot/capacity-probe-result.json`确认相同payload hash在20.94秒返回，prompt_tokens=20,090、cached_tokens=19,200。一次缓存重跑不能分离服务负载、缓存、传输波动，也不能用来证明长上下文导致第一次超时。

实际返回completed，引用官方失败分项，给出“逐字段构造证据表/汇总前核对”等通用流程；unknowns明确说没有所省略的产品、库存、客户、warehouse、policy和summary细节，无法定位具体错误记录或规则。它没有编造缺失数据；这直接支持“可见证据不足以作具体归因”的诊断，而不是context rot断言。

continued原提示词后来正常产生候选，diagnosis引用均绑定target/regression、没有null（根告知，详细数值由根报告）。所以旧canary的scope/null问题不能直接作为这次GDPevo失败的复现依据。

## 9. 单变量证据修复的离线回放结果

获授权后只改evidence/trace选择；未由本worker改prompt、model、learning或Actor。原预算42,000/1,800/24不变，原episode/Feedback/Context逐值复制到真实fixture并记录源SHA。初始4个回归中3个真实RED：产品/库存结果缺失、GET返回不可达、目录没有结果/模板续段；预算/原范围/全部SP保留对照PASS。

修复将同episode+call_id的动作/结果正文或locator成组安置，普通调用按本地阶段分散选取；目录先供部分正文的续段与调用结果，避免再次按所有action从头填。错误提示匹配排除customer_exception、业务exception及error:null，保留Error类/明确失败。磁盘候选预筛同族同步；旧failure hint使用前重新核对，旧归档/已完成checkpoint不重写。

| 相同fixture/预算 | 之前 | 之后 |
| --- | --- | --- |
| packet紧凑字符 | 41,582 | 41,246 |
| 正文字符 | 12,380 | 11,702 |
| 已选事件 | 17 | 20 |
| 实际业务结果 | orders×1 | orders×1，products×2，inventory×2，customers×1 |
| catalog | action×11 | result×7，feedback续段×4，action续段×2 |
| catalog紧凑字符 | 6,964 | 7,992 |
| call端点元数据覆盖 | complete×4 / partial×18 | complete×10 |
| 模板首段起点 | 143 | 0，并有可补读续段 |

complete指端点已提供或可读，不表示目录正文已经读过；目录引用在展开前仍不可用于事实引用。新catalog变大，所以不能据packet略小就宣称SDK总输入更短，也不能以类别覆盖增加宣称模型已经学会规则。

74项证据/磁盘/目标/学习及真实fixture回归通过。包括用旧宽匹配规则先构建完整磁盘索引、cold reopen后仍纠正customer_exception锚点，原数据/checkpoint不变。旧测试曾依赖selector主动拆散call才会出现partial；现改为真实窄projection隐藏一个返回后，再断言partial与引用边界，保护没有删除。真实修复后模型/任务结果由根另跑，不能与N07 scope提示词机制修正混作同一收益归因。
