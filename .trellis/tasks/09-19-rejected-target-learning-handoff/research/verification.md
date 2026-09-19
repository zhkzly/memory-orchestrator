# v1.9.0 拒绝target交接验收

## 行为

- `evolve()`仍为单轮；结果新增`next_episode_ids`，没有第二次Teacher调用。
- 只有candidate+target、Validation rejected且target_gain失败、Selection keep_current、执行/评分已知的请求生成Episode。
- Episode使用source.kind=`rejected_target_evaluation`，精确投影公开task、candidate snapshot、实际events/artifact；adaptation Feedback仅披露target score/outcome/target_gain和来源身份，不包含regression结果或私有criteria。
- lineage重新构造并逐字比较Episode；普通provided_material/execution_function引用comparison return仍返回learning_not_permitted。
- selected、unknown、blocked、base、regression和regression-only rejection均没有交接；active和原评价记录不变。

## 红绿与测试

- 新测试最初因`capture_rejected_target_episodes`不存在而ImportError，保留于`red.txt`。
- 第一次实现暴露EvaluationResult无project_id的错误过滤；修正实际记录查找。测试中伪造accepted Validation违反schema，改用读取时替换Selection来验证早停，没有放宽产品schema。
- `test_memory_rejection_learning`最终10/10通过；真实fixture来自f2fda0c的candidate target/regression return/result、plan、validation、selection、public case set、candidate snapshot，未含test001/gold。
- 相关评价/采样/学习/验证/发布/存储156项通过（36.372秒）。
- 最终`test_*.py` **401项通过、8项skip（85.154秒）**；Python compileall通过。
- 总纲v1.9.0 check/render/verify、packaged schema/prompt一致、37个结构负例和6个生成视图检查通过；最终源hash `5864a65cac2295e4359a662d24a779bfa815ca6c0b857bb73ad9869e62ca4cf7`。

## 官方mutation

修改前：evaluation.py、lineage.py、engine.py均取得许可。engine最初选用的单测单独运行原本为红，拒绝记录保留；改用完整`test_memory_verification`后取得有效许可。

修改后逐边许可全部通过：

- evaluation：target-only、candidate-only、rejected-only、target_gain失败、Episode投影精确；
- lineage：旧comparison return不能改名绕过；
- engine：next_episode_ids不能被删除；
- project-contract：版本/源与生成视图一致。

所有mutation由工具按字节恢复，没有使用git还原。

## 真实Store副本

`physical-handoff.json`在510e84d归档Store副本上运行，模型/benchmark调用均为0：

- Episode 1→2，Feedback 5→6，EvaluationReturn仍4；
- 新Episode为train001、134事件，来源绑定真实candidate target EvaluationReturn；
- active generation=0及snapshot均不变；
- 第二次交接返回相同Episode ID，记录数量不增加。

## 证据边界

本轮证明的是拒绝记录能安全进入**下一轮输入**。没有自动发起下一轮真实Teacher，也没有证明第二轮Skill改善。target被交接后属于adaptation材料，不能再称未见验证；regression/final保持隔离。
