# R8 K 线分区生命周期工程基线（2026-08-02）

> 类型：`engineering baseline`，不是生产分区或生产发布。
> 对应清单：[`../release_checklist_20260719.md`](../release_checklist_20260719.md)
> 运维边界：[`../../python/docs/kline_partitioning.md`](../../python/docs/kline_partitioning.md)

## 发布元数据

- R8 实现提交：`41c79f1ed70b90cfe46f163f3e5af80b5f93d3d6`
- 应用回滚点：`bd2d5737ea33bc312ded9705d631c8e6dfe40c55`
- 变更范围：K 线容量预检、benchmark 只读契约、影子分区 DDL、隔离复制演练、管理员存储
  概况、PostgreSQL CI 门禁和文档治理
- 生产发布窗口：未指定
- 发布负责人：未指定
- 回滚负责人：未指定
- 生产状态：活动 `kline_data` 未切换

## 已交付能力

### 容量与性能门禁

- `kline_storage_preflight.py` 只读采集方言、版本、行数、容量、周期分布、时间边界、分区状态、
  未来月份覆盖和查询计划摘要；
- 固定阈值为 1 亿行、100 GiB 和分钟查询 P99 500 ms；
- PostgreSQL 未达到阈值时返回 `not_required`；SQLite 返回
  `unsupported_for_partitioning`；
- 每次报告生成独立 `trace_id`，不包含连接凭据、Provider Token、原始 OHLCV 或 SQL
  参数值；
- `benchmark_kline.py` 默认只读，只有显式 `--seed` 且非生产环境才允许生成 BENCH 数据。

### 影子分区与迁移演练

- 影子父表按 `LIST (period)`，分钟组按月 `RANGE (trading_time)`；
- 分钟别名为 `1m/1/5m/5/15m/15/30m/30/1h/60`，长周期为
  `1d/D/1w/W/M`，未知周期进入 DEFAULT；
- DDL 保留当前 `KlineDataDB` 字段、Numeric 精度、时区、`trading_date`、非空条件和级联
  外键；主键及自然唯一键包含 PostgreSQL 要求的分区键；
- 管理和演练命令默认 dry-run；活动表、非法标识符、非 PostgreSQL 和缺少确认参数均被
  拒绝；
- 演练使用 `REPEATABLE READ` 和 transaction-level advisory lock，验证总数、周期计数、
  时间边界、自然键、sequence、外键、核心查询、冲突忽略、级联和实际分区裁剪；
- 成功可显式 `--cleanup`，失败由 PostgreSQL 事务回滚，不包含 rename/swap 路径。

### 观测与 CI

- 管理员端点 `GET /metrics/dashboard/kline-storage` 使用 60 秒 TTL；
- PostgreSQL 使用系统目录估算，SQLite 返回基础行数；普通用户返回 403；
- Prometheus `/metrics` 不执行 K 线容量统计；
- Backend CI 在 PostgreSQL 16 中执行 R8 只读预检、全部周期路由、重复 DDL、隔离演练、
  失败回滚和资源残留断言。

## 本地验证

- R8 聚焦回归：`79 passed, 3 skipped, 0 failed`；
- 全量后端：`1157 passed, 18 skipped, 0 failed`；
- Ruff check：通过；
- Ruff format check：通过；
- `git diff --check`：通过。

新增的 3 个 skip 是真实 PostgreSQL 分区专项用例。本机没有可确认的隔离 PostgreSQL，因此
未将 fake/SQLite 结果表述为 PostgreSQL 通过；这些用例必须由 Backend CI 的 PostgreSQL 16
service 执行。其余 15 个为既有环境跳过。

## 远程门禁

- R8 Backend CI：首次实现提交推送后回填；
- 必须通过 Alembic `upgrade head`、R8 K 线门禁、PostgreSQL 全量 pytest/API smoke、
  Ruff check/format 和 `pip-audit`；
- CI 最后必须确认当前 schema 不存在 `kline_data_shadow_*` 表或 sequence。

CI 数据库是空白隔离环境，只能证明 DDL、迁移演练和清理契约，不能证明真实生产容量达到或
未达到阈值，也不能替代生产切换证据。

## 回滚

R8 未新增 Alembic 迁移，也未修改活动表。应用回滚时停止 worker 和 API，保留脱敏报告及
`trace_id`，回滚到 `bd2d5737ea33bc312ded9705d631c8e6dfe40c55` 后重新执行现有
readiness、认证、行情和 K 线 smoke。

若隔离演练因进程中断留下显式 shadow 资源，只能核对表名、`trace_id` 和当前连接后删除该
shadow 表及其 sequence；不得操作活动 `kline_data`。R8 没有生产数据库恢复点可声明。

## 未完成生产项

以下条件未满足，因此不得将 R8 表述为生产已经分区：

- [ ] 已使用真实生产只读连接生成容量、查询 P99 和分区状态报告。
- [ ] 任一阈值已达到，并完成活动表切换规格及评审。
- [ ] 已指定维护窗口、发布负责人和回滚负责人。
- [ ] 已完成生产发布前备份和隔离恢复验证。
- [ ] 已验证停写/增量追平、权限、sequence、依赖对象、切换和回滚时限。
- [ ] 已在生产完成活动表切换、readiness、采集、K 线 API 和查询计划 smoke。
- [ ] 已完成冷数据导出、对象存储校验、恢复抽检和删除审批。

活动表切换、冷数据导出/删除、对象存储归档和生产恢复演练必须另立规格执行。
