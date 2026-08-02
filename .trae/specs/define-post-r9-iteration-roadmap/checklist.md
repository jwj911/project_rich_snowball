# Post-R9 后续迭代路线图验收清单

- [x] 新增 `docs/iteration_plan_20260802_post_r9.md`，并成为所有活跃入口指向的唯一当前事实源。
- [x] `docs/iteration_plan_20260724_follow_up.md` 保留 R1 至 R9 历史证据并明确不再承载当前待办。
- [x] Post-R9 基线准确记录 R9 本地与远端门禁已完成，但生产部署和完整业务周期观测未完成。
- [x] 文档没有把 Report-Only 描述为强制 CSP 已收紧或 XSS 风险已关闭。
- [x] 文档没有把 `localStorage` access token 风险描述为已关闭。
- [x] 后续事项按可立即实施、生产操作者、观测证据、容量/并发阈值和候选产品增强分类。
- [x] R10 被定义为 CSP 脱敏证据归类与 S2 准入报告，不自动改变强制 CSP。
- [x] R10 只允许读取已脱敏报告，不新增原始请求体、query、fragment、Cookie、Authorization、
  脚本、DOM 内容或原始 User-Agent。
- [x] R10 聚合维度和指标标签均为受控低基数字段，不包含完整 URL、用户标识或 `trace_id`。
- [x] R10 报告状态至少区分 `insufficient_evidence`、`blocked` 和 `ready_for_review`。
- [x] 本地/CI synthetic 流量明确只能得到 `insufficient_evidence`，不能构成 S2 准入。
- [x] 未知违规存在时 R10 状态为 `blocked`，已知违规要求负责人、决策和复验结果。
- [x] R11 要求真实目标环境、发布/回滚负责人、发布清单、完整业务周期和核心流程覆盖。
- [x] R12 只有在 R10/R11 证据通过后才能逐项实施 nonce/hash 和收紧 `script-src`。
- [x] R13 与 R12 独立，内存 access token 迁移后写请求仍要求 Authorization Bearer。
- [x] cookie-only 写请求与 S4 CSRF/origin 设计未被纳入 R13。
- [x] R8 活动表切换、冷归档和删除仍受容量阈值、备份恢复、维护窗口及审批门禁约束。
- [x] R7 Redis Pub/Sub 与跨实例连接管理仍受并发或高可用需求门禁约束。
- [x] 多因子组合、过滤 DSL、因子注册表、中性化、增强指标和日频 walk-forward 未被重复排期。
- [x] TraderAgent、Data Catalog 和策略进化的候选增强均准确基于现有能力，并要求另立规格。
- [x] `strategy_abstraction_plan.md` 已标记现有抽象能力的实际完成状态。
- [x] `strategy_evolution_agent_design.md` 已消除 walk-forward 仍待实现的过期表述。
- [x] `trader_agent_design.md` 已消除“待 review 后开发”、缺少 `scikit-learn` 和旧全量测试待办
  作为当前状态的误导。
- [x] `data_agent_data_iteration_plan.md` 的下一步入口已切换到 Post-R9 计划。
- [x] README、AGENTS、`.agents/`、发布清单、发布入口和前端安全风险文档均指向一致状态。
- [x] 生产清单中的真实凭据、负责人、备份恢复、目标环境 smoke 和 CSP 观测项保持未勾选。
- [x] 所有文档链接、日期、提交哈希、CI run 和测试计数经过核对。
- [x] 活跃文档中不存在两个同时宣称为“唯一当前事实源”的入口。
- [x] `git diff --check` 和适用的 pre-commit 检查通过。
- [x] 提交范围只包含规格和路线图相关 Markdown，未加入日志、数据库、报告或浏览器产物。
- [x] 文档提交已推送至 `origin/master`，本地与远端一致且工作区干净。
- [x] 下一步明确为先创建 R10 独立规格，不直接实施 S2、S3、生产分区或分布式 SSE。
