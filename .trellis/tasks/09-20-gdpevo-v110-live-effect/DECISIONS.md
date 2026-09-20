# Decisions

gdpevo-v110-live-effect|介入2|返工0|固定checkout/双study/真实ledger/公开报告/简历v2|红线违反0

- 首轮 diagnosis 即时 InternalServerError 后允许一次同配置独立重试；第二轮再次出现 APIStatusError/timeout，按计划停止。
- 不提高 timeout、不缩短 prompt、不换模型、不跳过 diagnosis，以免把配置改变混入同一实验版本。
- 无 Candidate 时不执行四次 Actor 对照；0 comparison 是协议结果，不是缺失分数填零。
