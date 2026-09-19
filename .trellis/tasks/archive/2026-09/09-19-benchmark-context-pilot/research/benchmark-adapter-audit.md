# GDPevo group 007 输入与评分边界审查

固定来源：`/tmp/gdpevo-memory-pilot/repo`，实查 HEAD 为 `56d60ae4ae5e067d1ec0ee1f850622e69f422179`。根目录 LICENSE 是 Apache License 2.0。官方源码、业务 JSON、训练输入和评分器保持只读；适配器不复制或修改标准答案。

本轮读取范围：env 的 README/server/setup/Dockerfile/endpoints/judge_api；train 001/002/004 的公开 input 与 eval/evaluate.py/eval.sh；共享原始业务 JSON。未阅读 test 答案、notes 或评分器用于分析。训练 001 gold 仅在宿主评分接线测试中作为正例读入，未进入 Actor。

## 结论与固定小批

- 采用 **train_001 学习、train_004 开发、test_001 冻结 probe**。该选择在模型调用前固定，不按分数改换题目。test_001 的答案未用于此次审查；测试阶段只通过私有官方评分进程判分，不把失败回流调整提示词。
- 001 和 004 都依赖订单、客户、产品、有效库存；004 额外要求单源调拨和行级决策，可观察同一 ERP 业务内的经验复用。只有一组业务环境和三道任务，不能据此声称完整 GDPevo 成绩、跨领域泛化或统计显著提升。
- 002 是六组件补货任务，规模更小但流程加入 BOM/PO；保留为后备说明材料，本轮不因分数更好而替代已冻结题目。
- 原始提示词没有列出所有确定性业务优先级/例外规则。初次失败可能属于缺少业务规则或稀疏反馈，不能仅凭低分认定上下文工程失败，更不能预先把 notes/gold 的规则补给 Actor。

## 实测数据量与上下文预算

| 任务 | 公开 prompt/memo/template 字节 | 业务范围 | 标准答案文件大小（只 stat） |
| --- | --- | --- | --- |
| train_001 | 672 / 1562 / 4000 | memo 指定8订单，21行，19 SKU，8客户 | 4236 B |
| train_002 | 713 / 756 / 4308 | BOM-300/301，两BOM共6种组件，目标各18套 | 4298 B |
| train_004 | 714 / 975 / 3342 | TRAIN_TRANSFER_B有13订单，31行，22 SKU，12客户 | 13147 B |

共享业务 JSON 共205034 B：orders 88条、products 54条、customers 40条、inventory 162条、purchase_orders 92条、warehouses 3条、boms 9条、suppliers 12条、incidents 212条。服务加载全表到宿主内存不等于把全环境提供给模型。Actor只得到它实际请求的原始业务响应。

001若逐实体查询，约需60次GET；可在一轮模型输出中提出多个独立tool_call。当前Actor预算已按任务规模预定为128次工具请求、6轮模型调用、8192输出tokens。004的大JSON输出尤其不应沿用小演示的2k输出限制。模型如何分批调用与完整调用记录由B/root负责，适配器不替模型查询所有相关实体或计算决策。

## 官方业务接口与必要隔离

`server.py` 的 `ERPHandler.route(parts, query)` 是标准库内的只读业务分发；`load_data()`读现有fixtures。可直接复用官方类，无须启动HTTP服务，也无须运行会写入数据的setup/generate脚本。

001/004所需业务GET：

```text
/orders?wave=&required_date=&customer_id=
/orders/<order_id>
/products/<sku>
/customers/<customer_id>
/warehouses
/inventory?warehouse_id=&sku=
/shipping/quote?warehouse_id=&destination_zip=&weight_lb=&speed=
```

002额外需要`/boms/<bom_id>`与`/purchase_orders?supplier_id=&sku=&status=`。PO接口没有warehouse过滤字段；products集合接口没有sku过滤字段。有效查询结果完全由原官方router产生，适配器不实现有效库存、优先级、调拨或补货答案。

发现公开文档差异：`env/endpoints.txt`还列有未被server实现的`/manifest`、`/inventory/{sku}`、`/warehouses/{id}`、`/suppliers/{id}`、`/purchase_orders/{id}`、`/incidents/{id}`，并将产品标识误称product_id。`env/README.md`的Domain Endpoints与实际router相符，所以`business_docs`采用这段官方原文，不把错误列表塞入提示词。

`POST /api/judge`是训练判分oracle，只有`TASK_ENV_ENABLE_JUDGE=1`时才在官方HTTP服务器启用；`judge_api.py`还说明其仅用于训练反思，不是测试解题工具。它会调用私有标准答案目录。Actor工具表必须没有POST/judge、Python、shell、任意路径或目录读取。env中的`judge_train_eval/**/output/answer.json`同样属于私有评分材料。

`read_input`的task_id由宿主根据当前case固定，不能作为模型可自由选择的工具参数，否则会跨题读取未来材料。公开文件路径精确白名单，允许官方提示词中的单次`input/`前缀；`..`、绝对路径、notes/eval/output以及指向外部材料的链接均拒绝。

## 已交付的最薄接口

实现文件：`examples/gdpevo_pilot/dataset.py`；验证：`tests/test_gdpevo_dataset.py`。

```python
dataset = GDPevoDataset(
    "/tmp/gdpevo-memory-pilot/repo",
    group_id="task_group_007",
    commit="56d60ae4ae5e067d1ec0ee1f850622e69f422179",
)
task = dataset.task("train", "001")
# task_id=train_001；description=官方prompt全文；无gold/eval路径
# project_id可由运行宿主改成对应实验臂的项目；revision/source身份保留。
dataset.public_files("train_001")
# {'prompt.txt':672, 'payloads/answer_template.json':4000,
#  'payloads/expedite_queue_memo.json':1562}
dataset.read_input("train_001", "payloads/expedite_queue_memo.json")
dataset.business_get("/orders", {"wave":"TRAIN_TRANSFER_B"})
feedback = dataset.evaluate(request, execution, full_case)
```

TaskSpec还记录具体输入的`source_id`与共享ERP的`shared_environment_id`，避免把任务ID不同误说成业务环境独立。`business_docs`是字符串属性，只有官方业务GET说明。

Actor由B实现真实SDK工具循环；`execution['artifact']`是其最终JSON对象，或解析失败时的原始字符串。适配器不会剥解释、补字段、算业务答案，也不会把参考答案伪装成模型结果。

`business_get`复用官方route并深拷贝返回值；合法路径/查询行为与官方一致。唯一有意更严格的边界是拒绝未实现端点和不支持的query字段，避免官方静默忽略过滤条件而令Actor误以为结果已过滤。

## 私有评分接口与语义

- 001/002：`evaluate.py <candidate.json>`，内部通过`__file__`定位本训练题的`output/answer.json`。001另有`score(candidate,expected)`纯函数。
- 004：`evaluate.py <candidate.json> <standard_answer.json>`。官方`eval.sh`封装了这个差异。
- 因此适配器统一使用`bash <固定task>/eval/eval.sh <显式临时candidate.json>`。当前工作目录是独立临时目录，不启动网络，不给Actor可调用评分函数。
- **不得省略candidate参数**：这三个官方eval.sh默认都把`output/answer.json`本身当候选，空参数会造出虚假的100%。
- 评分都是8个字段组的加权精确匹配：001总权重17、002为18、004为17。同一组通常要所有订单/行匹配才获得该组权重；分数不是逐行正确率。
- 001/004的读取/JSON错误也可能以exit0返回score0；002部分错误exit1。返回码不是任务成功判断。原始数值分数保留不重加权；通过条件遵官方judge的接近1判定。
- 适配器保存原stdout/stderr/returncode、scorer hash、candidate hash及完整评分细项。不存在有效官方数值分数（例如评分器崩溃）时为unknown，不捏造0分。评分资源缺失在启动前判为unknown；语法错误的实际候选按官方已返回分数记录。
- 官方judge HTTP响应只给归一化score/correct；本pilot宿主选择保留原评分器细项，因此训练反馈比单纯judge API分数更丰富。两实验条件必须使用同一反馈披露方式，不能把该条件的结果冒充所有官方运行设置。
- 原评分器有规范化和部分字段投影，不是完整输出schema验证。适配器保持官方分数，不能额外修改评分规则来方便自身，也不能由score1推导所有格式/语义要求均已被验证。

## 已执行检查与冻结状态

最初新测试因dataset模块尚不存在而RED；实现后执行：

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. .venv/bin/python -m unittest discover -s tests -p 'test_gdpevo_dataset.py' -v
Ran 8 tests in 0.141s — OK
```

测试来自真实train001：保留完整公开提示、精确文件白名单、真实业务过滤/深拷贝、judge和错误端点拒绝、实际commit校验、官方gold正例score1、删除一行shipping_quote导致原始score=15/17、空答/无效JSON虽exit0仍score0，以及请求/题目身份核对。训练gold正例仅是评分接线检查，不是Actor成绩。

另以`/dev/stdin`传入`{}`单独执行001/002/004原评分器，三者均为score0、8项判定、权重17/18/17，exit0；未读取test评分材料。根联合17项和task/catalog预检通过后已开始live baseline，本适配器与官方source按根要求冻结，不运行mutation或修改运行源。

## 有限mutation计划（已执行，证据见末节）

只覆盖当前真实边界，不扩展框架：实际commit检查、input目录/白名单、业务GET白名单、unsupported query、深拷贝、显式candidate参数、score而非exit判定、full_case身份绑定。准备时未宣称通过；根授予窗口后，从中选择5条关键边使用官方`mutation_license.py`执行，实际结果见末节。

示例验收命令（每条变体使用对应单项测试）：

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests:. .venv/bin/python -m unittest test_gdpevo_dataset.GDPevoDatasetTests.test_read_input_only_allows_current_public_files -v
```

本轮没有读取test答案/notes/eval做调试，没有LLM调用、服务启动或benchmark源修改。live运行与后续上下文诊断由根代理组织。

## Dataset 官方变体完成记录

在live开发运行结束、根代理授予dataset目标独占窗口后，已执行5项有界官方mutation：公开input相对越界、judge/未知路由拒绝、candidate误换为gold、exit0误当pass、request/case身份绑定。5/5均由官方工具检出，全部exit_code=0；每条均经历原始GREEN→注入RED→按原字节恢复GREEN，没有修改正式实现或扩展测试需求。

证据：`dataset-mutations.json`包含确切注入文本与单项真实数据测试；`dataset-mutation-results.json`包含每条官方命令、原始工具stdout/stderr、exit与before/after SHA-256；`01-public-input-traversal-tests.txt`至`05-case-identity-tests.txt`保留完整三阶段测试stdout。变体只读取训练材料，没有读test私有内容或调用模型。

恢复后完整`test_gdpevo_dataset.py`的8项再次GREEN，输出在`dataset-restored-tests.txt`。结束时重新比较当前源码SHA-256与全部5条before/after，完全一致；dataset窗口已交还根代理，C无运行中变体或测试。
