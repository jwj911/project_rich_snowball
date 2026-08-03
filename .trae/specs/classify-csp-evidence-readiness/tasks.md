# Tasks

- [x] Task 1: 完成 R10 交接检查并固定实现边界。
  - [x] SubTask 1.1: fetch `origin`，确认当前分支为 `master`、领先/落后为 0、工作区没有未说明
    改动，Post-R9 路线图提交已存在于远端。
  - [x] SubTask 1.2: 核对 R9 payload allowlist、`FrontendLogDB` 现有列、CSP 指标和发布预检
    `RELEASE_COMMIT` 契约。
  - [x] SubTask 1.3: 固定 R10 为服务层 + 离线只读 CLI；确认无管理员 HTTP API、无新表/迁移、
    无 CSP 策略或认证变更。

- [x] Task 2: 为新 CSP 记录增加可信归属与安全 source 类别。
  - [x] SubTask 2.1: 在 `config.py` 增加可选 40 位 Git `RELEASE_COMMIT` 解析与校验，缺失时
    不阻止应用启动。
  - [x] SubTask 2.2: 修改 CSP 持久化路径，由服务端写入受控 environment/release，客户端输入
    不能覆盖。
  - [x] SubTask 2.3: 将 `chrome-extension` / `moz-extension` blocked URL 降维为固定
    `browser-extension`，不保存扩展标识和路径。
  - [x] SubTask 2.4: 扩充 R9 单元与 PostgreSQL 持久化测试，确认原 allowlist、批量单次提交、
    脱敏和失败回滚无回归。

- [x] Task 3: 实现 CSP 证据领域服务。
  - [x] SubTask 3.1: 定义 context、catalog、记录、聚合、check/problem、report 和状态的强类型
    模型及固定枚举。
  - [x] SubTask 3.2: 实现 64 KiB context/catalog 校验、完整 UTC 窗口、完整 Git SHA、origin、
    核心流程、指标、目录唯一性和决策/复验组合校验。
  - [x] SubTask 3.3: 实现固定路由、directive、blocked source 分类，保证 unknown 和 unexpected
    origin 只产生稳定类别/问题码。
  - [x] SubTask 3.4: 实现 31 天、50,000 行、500 条 keyset page、500 聚合组和 30 秒的有界
    查询；只选择必要列。
  - [x] SubTask 3.5: 为 PostgreSQL 设置 read-only transaction + statement timeout，为 SQLite
    设置 query-only；检测无归属记录且不修改数据库。
  - [x] SubTask 3.6: 实现 R9 allowlist 二次校验、敏感/非法记录阻断、计数一致性与
    `persist_failed` 门禁。
  - [x] SubTask 3.7: 实现确定性的聚合排序、known/unknown 匹配、检查结果和四状态优先级。
  - [x] SubTask 3.8: 实现最大 256 KiB 的稳定 JSON，确认不含完整 URL、origin、记录 trace、
    用户信息、原始 payload 或路径。

- [x] Task 4: 实现安全离线 CLI。
  - [x] SubTask 4.1: 新增 `scripts/csp_evidence_report.py`，要求 database/context/catalog/report
    参数，并仅允许 DATABASE_URL 作为数据库参数回退。
  - [x] SubTask 4.2: 在数据库查询前完成输入大小/结构和仓库外 report path 校验。
  - [x] SubTask 4.3: 使用同目录临时文件、受限权限和原子 replace 写入报告；写入失败清理临时
    文件。
  - [x] SubTask 4.4: 实现 0/1/2/3/4 稳定退出码，stdout/stderr 只输出 trace、状态、固定计数或
    异常类型，不输出正文、路径、数据库 URL 或异常文本。

- [x] Task 5: 补齐 R10 定向测试与 CI 门禁。
  - [x] SubTask 5.1: 覆盖 context/catalog 的大小、结构、枚举、时间、origin、重复和组合边界。
  - [x] SubTask 5.2: 覆盖全部固定路由/directive/source 映射、匹配优先级、unknown 和
    unexpected origin。
  - [x] SubTask 5.3: 覆盖 synthetic、目标环境、零报告、known/unknown、流程/指标缺口、计数
    不一致、无归属和四状态优先级。
  - [x] SubTask 5.4: 覆盖 50,001 行、501 组、31 天、30 秒、256 KiB、malformed/额外/敏感
    payload 和安全输出。
  - [x] SubTask 5.5: 覆盖 CLI 仓库内路径拒绝、原子写入、权限、退出码、失败清理和报告写入
    失败。
  - [x] SubTask 5.6: 覆盖 SQLite query-only 与 PostgreSQL read-only、statement timeout、
    有界查询和零 DML。
  - [x] SubTask 5.7: 在 Backend CI 增加 R10 契约门禁，明确断言 synthetic 只能返回
    `insufficient_evidence`。

- [x] Task 6: 执行本地完整验证与安全复核。
  - [x] SubTask 6.1: 运行 R10、R9 CSP、release preflight 和前端日志聚焦 pytest。
  - [x] SubTask 6.2: 有隔离 PostgreSQL 时运行 R10/R9 PostgreSQL 专项；没有时保持明确 skip，
    不用 SQLite 伪造通过。
  - [x] SubTask 6.3: 运行后端全量 pytest、Ruff check/format 和 `git diff --check`。
  - [x] SubTask 6.4: 检索报告、stdout/stderr、日志和测试快照，确认无 URL、origin、凭据、记录
    trace、payload、文件路径或数据库 URL 泄露。
  - [x] SubTask 6.5: 确认没有生产 context/catalog/report、测试数据库、临时文件、日志或 CI
    产物进入版本控制。

- [x] Task 7: 更新文档、形成非生产工程基线并远程闭环。
  - [x] SubTask 7.1: 更新 `.env.example`、Compose、README、AGENTS、`.agents/`、Post-R9
    计划和发布清单，说明 `RELEASE_COMMIT` 与 R10 使用方式。
  - [x] SubTask 7.2: 新增 R10 非生产发布记录，分别记录本地/CI 证据、回滚点、限额、退出码和
    未完成 R11/R12/R13。
  - [x] SubTask 7.3: 明确 synthetic `insufficient_evidence` 不是生产 SLO 或 S2 准入，强制
    CSP、Report-Only、token 和 Bearer/CSRF 边界不变。
  - [x] SubTask 7.4: 只暂存 R10 相关代码、测试、CI、规格和文档，运行 pre-commit 并创建原子
    提交。
  - [x] SubTask 7.5: 推送 `origin/master`，核对 Backend CI；失败时以独立修复提交处理。
  - [x] SubTask 7.6: 确认本地/远端 0/0、工作区干净、规格任务和 checklist 全部勾选，下一阶段
    仍为受生产操作者门禁的 R11。

# Task Dependencies

- Task 2 and Task 3 depend on Task 1，二者可并行实施。
- Task 4 depends on Task 3.
- Task 5 depends on Task 2、Task 3 and Task 4.
- Task 6 depends on Task 5.
- Task 7 depends on Task 6.
