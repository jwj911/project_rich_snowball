# Tasks

- [x] Task 1: 建立 K 线存储容量预检与脱敏诊断报告。
  - [x] SubTask 1.1: 定义阈值常量、稳定检查代码、结果模型和 `trace_id` 报告结构。
  - [x] SubTask 1.2: 实现 PostgreSQL 行数、容量、周期分布、时间边界、分区状态和计划摘要采集。
  - [x] SubTask 1.3: 实现 SQLite 基础统计与 `unsupported_for_partitioning` 降级。
  - [x] SubTask 1.4: 提供默认只读 CLI，并覆盖失败退出码、脱敏和无副作用测试。

- [x] Task 2: 修正 benchmark 的只读契约。
  - [x] SubTask 2.1: 默认禁止自动创建 BENCH 数据，空数据时返回明确非 0 状态。
  - [x] SubTask 2.2: 仅在显式 `--seed` 和非生产确认条件下生成隔离 benchmark 数据。
  - [x] SubTask 2.3: 增加 JSON 输出，稳定记录样本数、p50、p95、p99 和阈值结论。

- [x] Task 3: 实现当前模型兼容的影子分区 DDL 与生命周期命令。
  - [x] SubTask 3.1: 提取周期分组和分区命名常量，覆盖全部现有周期别名及默认分区。
  - [x] SubTask 3.2: 生成包含当前字段、精度、外键、复合主键、自然唯一键和共享序列的 PostgreSQL DDL。
  - [x] SubTask 3.3: 实现未来 3 个月分钟分区规划，确保 dry-run 默认、输出稳定且 apply 幂等。
  - [x] SubTask 3.4: 对活动表名、非 PostgreSQL、缺少确认参数和非法标识符执行硬拒绝。

- [x] Task 4: 实现隔离迁移演练与一致性验证。
  - [x] SubTask 4.1: 在显式影子表上复制源数据，并使用事务或清理路径隔离失败资源。
  - [x] SubTask 4.2: 验证总行数、周期计数、时间边界、自然键、序列和外键一致性。
  - [x] SubTask 4.3: 验证 ORM 核心查询、批量冲突忽略和分钟分区裁剪。
  - [x] SubTask 4.4: 生成只含聚合证据、检查代码和 `trace_id` 的演练报告。

- [x] Task 5: 增加管理员 K 线存储观测。
  - [x] SubTask 5.1: 提供低成本、带缓存的 PostgreSQL 容量和分区概况。
  - [x] SubTask 5.2: 提供 SQLite 兼容摘要并明确 `partitioning_supported=false`。
  - [x] SubTask 5.3: 增加管理员只读端点及普通用户 403 回归。
  - [x] SubTask 5.4: 避免将高成本统计接入每次 Prometheus scrape。

- [x] Task 6: 补齐 PostgreSQL 集成、回归与 CI 门禁。
  - [x] SubTask 6.1: 在隔离 PostgreSQL 数据库或 schema 中验证分区 DDL、别名路由、默认分区和幂等维护。
  - [x] SubTask 6.2: 验证影子迁移一致性、失败清理、查询裁剪和既有 K 线 API/采集契约。
  - [x] SubTask 6.3: 运行 Ruff、后端全量 pytest、Alembic head 和 PostgreSQL API smoke。
  - [x] SubTask 6.4: 将 R8 只读预检和影子分区契约加入 Backend CI，且不在 CI 留存影子资源。

- [x] Task 7: 维护 R8 迭代和发布文档。
  - [x] SubTask 7.1: 更新 `CHANGELOG.md`、`AGENTS.md`、`.agents/`、README 和当前迭代计划。
  - [x] SubTask 7.2: 修订 `python/docs/kline_partitioning.md`，替换过时字段、周期和约束说明。
  - [x] SubTask 7.3: 更新发布清单并新增 R8 非生产发布记录，保留活动表切换和冷归档未完成项。
  - [x] SubTask 7.4: 校验文档链接、测试计数、提交哈希、CI 链接和状态表述。

- [x] Task 8: 原子提交并推送本轮迭代。
  - [x] SubTask 8.1: 检查工作区，只暂存 R8 代码、测试、规格和文档。
  - [x] SubTask 8.2: 运行 pre-commit 与最终差异检查，创建范围单一的迭代提交。
  - [x] SubTask 8.3: 推送至 `origin/master`，确认本地/远程提交一致。
  - [x] SubTask 8.4: 记录远程 CI；失败时修复、重新验证并以独立提交推送。
  - [x] SubTask 8.5: 确认影子数据库/schema、报告、benchmark 数据和临时产物已清理，工作区干净。

# Task Dependencies

- Task 2 可与 Task 1 并行。
- Task 3 depends on Task 1 的阈值与报告契约。
- Task 4 depends on Task 3.
- Task 5 depends on Task 1。
- Task 6 depends on Task 1 through Task 5.
- Task 7 depends on Task 6 的最终验证结果。
- Task 8 depends on Task 6 and Task 7.
