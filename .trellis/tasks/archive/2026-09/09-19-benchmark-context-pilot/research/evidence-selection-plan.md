# 真实GDPevo证据选择修复

边界：只改evidence.py、同族trace.py及相应测试；不改prompt/scope/model/actor/评分器/任务。原预算保持max_chars=42000、max_fragment_chars=1800、max_catalog_refs=24、token_budget=24000；补读仍60000/3000/24/34000。读到证据不代表提取正确或任务得分提高。

## 实际首偏差

- 原episode有136事件、67个真实工具调用。原输入选17事件，外加任务元数据/反馈共19 fragments；11个action、5个observation、2个task、1个feedback。
- 原轨迹的products19、inventory20、customers8条结果均没有正文进入；只看到一条orders结果。
- `build_packet.rank`把所有action排在普通observation前，同类又按source_position从前往后填。随后catalog沿同一ordered/pieces再次遍历，11个目录项全部action；继续扩展也不会自动发现结果。
- 6个已提供GET动作的返回既无正文也无可读locator；required answer_template截断后无续段locator。
- 裸exception匹配customer_exception及业务文本，影响优先级和首段位置；error:null也不能当真实失败锚点。
- 包实际紧凑JSON为41582字符，未越42000；块记录43089使用带空格JSON，不能混作超预算。正文12380、relations5829、catalog6964。目录在extract输入中重复一次。

## 真实fixture与RED

`tests/fixtures/gdpevo_context_train001.json`逐值复制baseline原Episode/Feedback/Context并记录源文件SHA，无理想轨迹重构、无test答案。

`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m unittest tests.test_gdpevo_context -v`：4项中3项按预期失败，预算/原字节范围/全部8个官方评分点对照通过。

1. 失败的库存与产品类别应存在实际返回证据，并保留早期订单材料：原仅orders，FAIL。
2. 已提供GET若实际有返回，应至少给返回正文或可读locator：原6个stranded GET，FAIL。
3. catalog应给结果和所选长模板续段；补读前不可事实引用，补读后才可：原全action，FAIL。
4. 预算、来源hash/range/上下文/任务修订及评分点不因修复丢失；不能靠全量塞入通过：原PASS，保持。

## 有界机制

1. 以同episode+call_id形成当前已知调用单元。唯一action/result用真实身份连接，多动作或多结果仍保留ambiguity；不按相邻文本猜。
2. 保留任务/评价、明确错误、恢复及反证。普通调用按各episode的本地执行次序分散选取代表，避免用所有早期请求耗尽预算；这是覆盖策略，不是时间因果推断。
3. 安置调用单元时一起考虑动作与结果：正文能放则成组放；正文不足但值得提供时，动作和对应结果locator一并计算预算。不能只放动作，再把其唯一返回挤到不可访问区。
4. 目录顺序独立于正文旧rank：先已读重要长事件的未读范围、已提供调用缺失的结果/必要关联，再分散的其他候选。不再次从全部action头部填满。目录仍是未读材料，引用校验不放宽。
5. 目录的调用locator用已有call/goal/source关系连接到实际可见动作，避免给一堆无正文、无语义锚点的随机ID；保持现有schema，不建立新检索服务。
6. failure提示只作有依据的定位/选择信号；字段customer_exception、正常业务exception以及error:null不能当作真实异常。保留ERROR/Traceback/异常类/明确失败的定位能力；原文不改。
7. TraceRecords.select_metadata同步成组/阶段候选策略，查询和保留元数据仍有上限；不能修inline却在磁盘预筛阶段再次丢掉后半程结果。不加载完整长正文。旧failure offset属于提示，使用前按新匹配规则核对，不能把旧缓存提示升级为真值。

## 执行与回归

- 先转上述真实RED为GREEN，再报告固定预算下各类实际正文/目录、配对覆盖、序列化字数；不以片段更多或字数更少替代质量。
- 增加同一原事件的磁盘表示对照与普通业务字段/真实错误定位反例；复用已有goal切换、旧反馈、反证、源hash、不可读引用、补读预算测试。
- 生产源改动期间不触碰另一代理的actor；新scope披露是另一变量。原268个边界由根安排全量回归，mutation等待根的串行窗口。

容量控制证据：相同payload hash 40c825e6904a95d3fecf56f52c063a3262f725e30442f30bc5323f0284dfd0fc在20.94秒返回，input20090/cached19200 tokens，明确承认未提供产品/库存等原数据并仅给通用流程。一次缓存重跑不能证明长上下文导致45秒超时，也不能证明已排除环境/服务波动。

## 实施检查点

- 根在continued结束后授权实施；只修改已分配的evidence.py、trace.py和测试/fixture。
- 3个真实RED已GREEN；74项evidence/trace/goals/learning/真实context测试全部通过，diff --check通过。命令：`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python -m unittest test_gdpevo_context test_memory_evidence test_memory_trace test_memory_goals test_memory_learning -q`，14.7秒。
- 磁盘对照先模拟旧宽匹配策略生成完整index，再重开同一Store；新片段从模板头部开始，旧checkpoint数量及原始字节不变，不靠新建索引掩盖旧hint问题。
- 恢复后源码hash：evidence.py `4acd95426975198dac938dedb97d426d94f5274769fee4aba72dd3b101f85309`；trace.py `52724de581b30eacc5b4791184b3962faddc9ed45d41c79960585ca728b2636b`。
- 根授予独占窗口后，9/9官方mutation全部“执照发放/注入错误时变红”，每项exit0且before/after SHA相同，无存活、无放松断言。命令与原始输出/恢复hash在evidence-mutation-commands.json和evidence-mutation-results.json。覆盖call成组、阶段代表、目录续段、业务非错误/真实错误、旧hint重检、磁盘候选覆盖、完整字符预算、目录不能当事实。窗口已交回根，不运行额外live或核心测试。
