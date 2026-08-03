# Tasks

- [ ] Task 1: 满足 R11 生产操作者门禁并冻结发布输入。
  - [ ] SubTask 1.1: 确认真实 production 环境、PostgreSQL、Redis、HTTPS CORS、真实数据源和
    `single|sticky` SSE 拓扑。
  - [ ] SubTask 1.2: 指定发布负责人、回滚负责人、证据保管人和安全评审人；仓库只记录角色
    已确认，不记录个人账号或审批 ID。
  - [ ] SubTask 1.3: 批准 deploy SHA、rollback SHA、镜像 digest、UTC 发布窗口、sample rate 和
    仓库外证据根目录。
  - [ ] SubTask 1.4: 确认证据至少保留 90 天、加密存储、受限访问和到期双人销毁审批。
  - [ ] SubTask 1.5: 若任一真实输入缺失，保持 R11 `blocked` 并停止后续执行，不使用 placeholder
    或历史 CI 代替。

- [ ] Task 2: 创建不可变 R11 发布计划与证据清单。
  - [ ] SubTask 2.1: 从通用发布清单复制 R11 专属生产记录，所有未执行项保持未勾选。
  - [ ] SubTask 2.2: 固定 deploy/rollback SHA、镜像 digest、Alembic head、SSE 模式、sample rate
    和双 CSP 规范化 hash。
  - [ ] SubTask 2.3: 为 preflight、backup、restore、deploy、smoke、metrics、context、catalog、
    report 和 rollback 分配低敏 artifact ID。
  - [ ] SubTask 2.4: 定义每个 artifact 的 SHA-256、生成时间、schema version、保留截止时间、
    保管角色和状态，不记录路径、host、用户名、URL 或凭据。
  - [ ] SubTask 2.5: 发布输入变化时取消旧计划并重新审批，不覆盖历史记录。

- [ ] Task 3: 执行真实预检、备份与隔离恢复。
  - [ ] SubTask 3.1: 使用真实生产输入执行 R7 `release_preflight.py`，11 项全部通过并保存脱敏
    trace 报告。
  - [ ] SubTask 3.2: 创建 PostgreSQL 逻辑备份，记录工具版本、窗口、字节数和 SHA-256。
  - [ ] SubTask 3.3: 在隔离 PostgreSQL 恢复备份，禁止覆盖生产或 `python/dev.db`。
  - [ ] SubTask 3.4: 核对 Alembic head、核心表、聚合行数、约束和只读应用 readiness。
  - [ ] SubTask 3.5: 记录恢复 RTO，并由回滚负责人确认恢复步骤和备份可用性。
  - [ ] SubTask 3.6: 任一预检/恢复/校验失败时停止，不执行生产迁移或部署。

- [ ] Task 4: 部署 S1 基线并完成窗口前 canary。
  - [ ] SubTask 4.1: 部署冻结镜像，执行 `alembic upgrade head`，确认运行时
    `RELEASE_COMMIT` 与 deploy SHA/镜像一致。
  - [ ] SubTask 4.2: 验证 API scheduler 关闭、独立 worker 唯一启用、Redis/数据源共享和
    `single|sticky` 拓扑。
  - [ ] SubTask 4.3: 计算并比较强制 CSP、Report-Only、认证和配置 hash，确认与 R9/R10 基线
    一致。
  - [ ] SubTask 4.4: 验证 liveness、readiness、scheduler、管理员/普通用户权限和关键 API。
  - [ ] SubTask 4.5: 在正式窗口前执行 CSP reporting canary，验证可信 release/environment、
    outcome 指标和脱敏持久化，并从正式窗口排除 canary。
  - [ ] SubTask 4.6: 执行 14 项核心流程 smoke；失败时回滚且不开始完整观测窗口。

- [ ] Task 5: 执行不可缩短的完整业务周期观测。
  - [ ] SubTask 5.1: 由发布负责人和安全评审人共同确认 UTC `window_start`。
  - [ ] SubTask 5.2: 覆盖至少 5 个实际交易日、连续 7 个自然日、一个周末/休市段、日盘、夜盘、
    调度周期和非交易时段；休市时顺延。
  - [ ] SubTask 5.3: 冻结 release、镜像、sample rate、双 CSP、认证、SSE、origins 和指标口径。
  - [ ] SubTask 5.4: 逐项记录 14 个生产流程的 passed/failed/not_run、时间、角色、release 和
    低敏 artifact ID。
  - [ ] SubTask 5.5: 采集业务 HTTP 与六类 CSP outcome 窗口增量、accepted 记录数、重启/reset
    和告警事件。
  - [ ] SubTask 5.6: 确认 `persist_failed=0`、accepted 与目标记录一致，解释所有 rejected /
    rate_limited。
  - [ ] SubTask 5.7: 发生变更、重启、指标缺口、敏感数据或上限截断时标记窗口 invalidated，
    修复后从新窗口重新执行，不拼接证据。

- [ ] Task 6: 生成 production R10 证据并闭环所有分类。
  - [ ] SubTask 6.1: 在仓库外生成 `target_environment / production` context，release、窗口、
    sample rate、14 流程和指标与 R11 完全一致。
  - [ ] SubTask 6.2: 在仓库外维护低基数 catalog，为每个分类记录 owner role、decision 和
    retest status。
  - [ ] SubTask 6.3: 运行 R10 CLI，保存受限 report、SHA-256、trace 和安全摘要，不记录路径或
    报告正文。
  - [ ] SubTask 6.4: 对 `insufficient_evidence` / `blocked` / `failed` /
    `report_write_failed` 逐项处理；需要代码或配置修复时终止窗口并重新部署/观测。
  - [ ] SubTask 6.5: 确认最终报告为 `ready_for_review`，无 unknown、pending、failed、敏感或
    truncated 项。

- [ ] Task 7: 完成 R11 签字、回滚验证与文档闭环。
  - [ ] SubTask 7.1: 验证停止 worker/API、应用回滚、readiness、认证、行情、SSE 和 CSP 恢复
    步骤；正常 R11 回滚不执行 Alembic downgrade。
  - [ ] SubTask 7.2: 由发布、回滚、证据保管和安全评审四类角色确认退出条件。
  - [ ] SubTask 7.3: 新增 R11 生产观测记录，只写低敏提交、窗口、artifact hash 摘要、状态、
    trace 和签字状态。
  - [ ] SubTask 7.4: 更新 Post-R9 计划、发布清单、README、AGENTS 和 `.agents/`，准确标记
    completed / blocked / invalidated / rolled_back。
  - [ ] SubTask 7.5: 确认生产 context/catalog/report、备份、日志和业务数据未进入 Git 或 CI
    artifact。
  - [ ] SubTask 7.6: 只提交 R11 规格与脱敏文档，推送后确认本地/远端一致、工作区干净。
  - [ ] SubTask 7.7: R11 完成后只将 R12 标记为“待人工专项评审”，不自动实施 nonce/hash。

# Task Dependencies

- Task 2 depends on Task 1.
- Task 3 depends on Task 2.
- Task 4 depends on Task 3.
- Task 5 depends on Task 4.
- Task 6 depends on Task 5.
- Task 7 depends on Task 6.
