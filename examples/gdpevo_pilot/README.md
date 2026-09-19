# GDPevo 小批量上下文诊断

本目录是当前记忆核心的一个具体benchmark执行/评分适配。任务、业务数据和评分程序使用GDPevo固定提交 `56d60ae4ae5e067d1ec0ee1f850622e69f422179` 的 `task_group_007`；本轮学习train001、开发回归train004、最后冻结探测test001。它不等于官方完整GDPevo成绩。

- `dataset.py`：只向Actor提供当前任务公开input和原业务router的GET。官方评分脚本在独立临时输出上运行，gold和judge端点不提供给Actor。
- `actor.py`：真实SDK工具循环，按需读文件、查业务记录、读被选Skill资产并提交JSON。没有shell/Python工具；此设置不测新增脚本工具的实际使用效果。
- `sdk.py`：在真实网络调用前保存完整可见messages/tools，记录返回、未知用量、输入字符和物理调用预算。不记录隐藏推理或凭据。
- `run.py`：调用原有sample_tasks/evolve/report。baseline保存学习前Store，continued/revised复用相同训练证据，probe只评价已冻结的库。

先获取一组公开数据（不会运行其setup）：

```bash
GIT_LFS_SKIP_SMUDGE=1 git clone --filter=blob:none --sparse https://github.com/Prism-Shadow/GDPevo.git /tmp/gdpevo-memory-pilot/repo
git -C /tmp/gdpevo-memory-pilot/repo checkout 56d60ae4ae5e067d1ec0ee1f850622e69f422179
git -C /tmp/gdpevo-memory-pilot/repo sparse-checkout set data/task_groups/task_group_007
```

已有工程虚拟环境即可运行，无须安装/启动Flask或Docker服务。调用模型前读取run.py的固定预算与本轮manifest；API key只从OPENAI_API_KEY读取。

```bash
PYTHONPATH=src .venv/bin/python -m examples.gdpevo_pilot.run \
  --source /tmp/gdpevo-memory-pilot/repo --root /tmp/new-memory-pilot --stage baseline
```

各stage不可覆盖。`--budget`只接受显式记录的剩余预算变更：重读原ledger验证已用调用/字符，不能因此扩大96次SDK和300万输入字符的总上限。本轮原45秒超时记录保留；120秒继续配置另存，并从总预算扣除了旧尝试。不能把重新运行说成恢复了未返回的原调用。

`probe`先比较两臂真正会向Actor提供的库快照、事实和关系。如果完全相同，就记录not_run并保留任务，不消耗两次相同条件的随机执行来冒充memory对照。

本轮Actor每题最多6次模型调用、128个工具请求、8192输出tokens；每次实际请求带一条最新剩余预算状态。核心Teacher每周期最多8次调用。任务执行结束与任务成功分开，正常stop未提交的原文本、截断、超时和预算耗尽均保留，不由宿主修补答案。

官方脚本的score是加权项目总分，不是逐行正确率；退出码0也可能score0。脚本细项反馈比官方HTTP judge的score/correct更丰富，本轮各条件一致使用该反馈。冻结probe数据不能用于修改提示词或选择候选。

定向检查：

```bash
PYTHONPATH=src:tests .venv/bin/python -m unittest discover -s tests -p 'test_gdpevo_*.py' -v
```

Dataset测试依赖上述固定checkout；模型接口测试用保存的真实公开输入与构造传输返回，不发API请求。所有实测数字、原始失败和改前/后输入位于对应Trellis任务的research/pilot，不把构造测试算作模型效果。
