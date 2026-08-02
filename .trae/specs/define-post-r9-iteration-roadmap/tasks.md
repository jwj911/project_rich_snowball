# Tasks

- [x] Task 1: 固化 Post-R9 文档基线并建立状态矩阵。
  - [x] SubTask 1.1: 确认 `master`、`origin/master`、工作区状态和 R9 最终提交，记录文档更新
    前的可追溯基线。
  - [x] SubTask 1.2: 汇总活跃文档中的未完成项，按可立即实施、生产操作者、观测证据、
    容量/并发阈值和候选产品增强分类。
  - [x] SubTask 1.3: 核对策略抽象、walk-forward、TraderAgent、Data Catalog 和策略进化事件流
    的当前实现，排除已完成能力的重复排期。

- [x] Task 2: 新建 Post-R9 唯一迭代事实源。
  - [x] SubTask 2.1: 创建 `docs/iteration_plan_20260802_post_r9.md`，记录 R9 已验证基线、
    非生产边界和文档审计结论。
  - [x] SubTask 2.2: 写入 R10 CSP 证据归类与 S2 准入报告的目标、输入边界、验收、停止条件
    和独立规格要求。
  - [x] SubTask 2.3: 写入 R11 目标环境 S1 观测、R12 nonce/hash 收紧和 R13 内存 token 迁移
    的依赖顺序与回滚边界。
  - [x] SubTask 2.4: 写入 R8 分区/归档与 R7 SSE 分布式能力的阈值触发轨道，明确未满足条件时
    不排期。
  - [x] SubTask 2.5: 写入 Trader 计划生命周期、Data Catalog 前端展示和策略进化实时进度
    候选项，要求逐项另立规格。
  - [x] SubTask 2.6: 为每个后续事项提供状态、优先级、依赖、准入证据、退出证据和非目标。

- [x] Task 3: 同步项目入口、发布和安全事实源。
  - [x] SubTask 3.1: 将 `docs/iteration_plan_20260724_follow_up.md` 标记为 R1 至 R9 已完成历史
    事实源，并链接 Post-R9 计划。
  - [x] SubTask 3.2: 更新 `README.md`、`AGENTS.md`、`.agents/project.md` 和
    `.agents/roadmap.md` 的当前迭代与文档导航。
  - [x] SubTask 3.3: 更新 `.agents/security.md`、`.agents/operations.md` 和
    `frontend/docs/SECURITY_RISKS.md`，保留 S1/S2/S3 顺序和认证停止条件。
  - [x] SubTask 3.4: 更新 `docs/release_checklist_20260719.md` 与 `docs/releases/README.md`，
    增加 Post-R9 入口但不勾选任何未执行的生产事项。

- [x] Task 4: 校正活跃设计文档的状态漂移。
  - [x] SubTask 4.1: 更新 `docs/strategy_abstraction_plan.md` 状态，说明多因子组合、过滤 DSL、
    注册表、中性化和增强指标已实现，原路线保留为历史设计。
  - [x] SubTask 4.2: 更新 `docs/strategy_evolution_agent_design.md`，说明日频 walk-forward 已由
    R4 实现，剩余实时前端体验是候选项。
  - [x] SubTask 4.3: 更新 `docs/trader_agent_design.md`，移除“待 review 后开发”的当前状态，
    将过期依赖/全量测试问题标为历史，并保留真正未完成的产品候选。
  - [x] SubTask 4.4: 更新 `docs/data_agent_data_iteration_plan.md`，将 R5 之后的过期“下一步”
    指向 Post-R9 计划，并保留 Data Catalog 前端展示为候选。

- [x] Task 5: 系统验证路线图与文档一致性。
  - [x] SubTask 5.1: 检查所有新增和修改链接、文件名、提交哈希、CI run、测试计数和日期。
  - [x] SubTask 5.2: 全文检索“唯一事实源”“当前迭代”“待实现”“待验证”等表述，确认没有
    与当前实现或门禁状态冲突的活跃文档。
  - [x] SubTask 5.3: 确认文档没有把 R9 描述为生产部署、把 R10 描述为 CSP 强制收紧、把
    R8/R7 条件轨道描述为已排期。
  - [x] SubTask 5.4: 运行 `git diff --check` 和适用于修改文件的 pre-commit，确认未加入日志、
    数据库、报告、浏览器或 Lighthouse 产物。

- [x] Task 6: 原子提交并推送 Post-R9 路线图文档。
  - [x] SubTask 6.1: 只暂存本规格和 Post-R9 规划相关 Markdown；`.trae/` 规格路径使用
    `git add -f` 显式纳入，并检查提交范围。
  - [x] SubTask 6.2: 创建单一文档提交并推送 `origin/master`。
  - [x] SubTask 6.3: 确认本地与远端领先/落后均为 0，工作区干净，并记录下一步应先为 R10
    创建独立规格而不是直接实施 S2。

# Task Dependencies

- Task 2 depends on Task 1.
- Task 3 and Task 4 depend on Task 2，二者可并行执行。
- Task 5 depends on Task 3 and Task 4.
- Task 6 depends on Task 5.
