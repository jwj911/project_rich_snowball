# R8 K 线分区生命周期准备 Spec

## Why

`kline_data` 分区与冷归档是当前唯一明确的 P2 数据规模风险项，但既有方案已落后于实际模型，
且未证明当前数据量达到迁移阈值。直接替换活动表会引入主键、唯一约束、周期别名和迁移回滚风险。

## What Changes

- 新增只读容量预检，基于 PostgreSQL 行数、表/索引大小、周期分布、时间范围和查询计划判断是否达到分区阈值。
- 预检生成带独立 `trace_id` 的脱敏 JSON 诊断报告，不输出原始行情或数据库凭据。
- 修正分区契约，使字段、精度、外键、`trading_date`、周期别名和唯一约束与当前模型一致。
- 新增默认 dry-run、幂等的影子分区表规划与未来 3 个月分钟分区维护命令。
- 新增隔离迁移演练，验证复制计数、分组计数、时间边界、自然键唯一性、序列和核心查询语义。
- 将既有 K 线 benchmark 改为默认只读，只有显式 `--seed` 才允许生成 benchmark 数据。
- 增加管理员可见的 K 线存储概况，SQLite 返回受支持的非分区摘要，PostgreSQL 返回分区与容量信息。
- 增加 PostgreSQL 集成测试和 Backend CI 门禁，并同步迭代、运维、发布和 Agent 文档。
- 完成验证后创建原子提交并推送至 GitHub `origin/master`。
- 本轮无 **BREAKING** API 变更，不自动切换活动 `kline_data` 表。

## Impact

- Affected specs: K 线存储、PostgreSQL 运维、容量治理、指标面板、发布治理。
- Affected code:
  - `python/services/kline_storage.py`
  - `python/services/kline_partitioning.py`
  - `python/scripts/kline_storage_preflight.py`
  - `python/scripts/manage_kline_partitions.py`
  - `python/scripts/benchmark_kline.py`
  - `python/routers/metrics_dashboard.py`
  - `python/services/metrics.py`
  - `.github/workflows/backend-ci.yml`
  - PostgreSQL/SQLite 测试与项目文档

## ADDED Requirements

### Requirement: 只读容量预检

系统 SHALL 提供只读 K 线存储预检，至少采集以下证据：

- 数据库方言和 PostgreSQL 版本；
- `kline_data` 总行数、表大小、索引大小和总大小；
- 各 `period` 的行数、最早/最晚 `trading_time`；
- 当前表是否已分区、分区数量和缺失的未来月份；
- 核心品种/合约分钟查询的 `EXPLAIN` 计划摘要；
- 既定阈值：总行数 1 亿、总大小 100 GiB、分钟查询 P99 500 ms。

预检 SHALL 默认不执行 `ANALYZE`、不插入 benchmark 数据、不创建分区、不锁表。

#### Scenario: 未达到分区阈值

- **WHEN** 行数、大小和查询延迟均低于阈值
- **THEN** 报告状态为 `not_required`，并明确禁止把该结果表述为已完成生产分区

#### Scenario: 达到任一分区阈值

- **WHEN** 任一阈值达到或超过
- **THEN** 报告状态为 `recommended`，列出触发代码和下一步影子迁移演练要求

#### Scenario: 非 PostgreSQL 环境

- **WHEN** 预检运行在 SQLite
- **THEN** 返回受支持的基础统计和 `unsupported_for_partitioning`，不得执行 PostgreSQL 专有 SQL

### Requirement: 脱敏诊断报告

系统 SHALL 为每次容量预检生成独立 `trace_id` 和结构化 JSON 报告。报告可包含聚合计数、字节数、
时间边界、计划节点和阈值结论，但不得包含数据库密码、Provider Token、原始 OHLCV 行或 SQL 参数值。

#### Scenario: 统计查询失败

- **WHEN** 任一统计或计划查询失败
- **THEN** 报告保留 `trace_id`、稳定错误代码和异常类型，并以非 0 退出，不输出连接串或原始 SQL 数据

### Requirement: 当前模型兼容的分区契约

系统 SHALL 使用当前 `KlineDataDB` 契约生成 PostgreSQL 影子表 DDL，包含：

- `contract_id NOT NULL`、`trading_date`、当前 Numeric 精度、时区时间列和级联外键；
- 自然唯一键 `(variety_id, contract_id, period, trading_time)`；
- 数据库主键包含 PostgreSQL 要求的全部分区键，同时保持 `id` 由共享序列生成；
- 当前所有周期别名均进入明确分组，未知周期进入默认分区；
- 分钟周期按月范围分区，日/周/月周期进入长期分区。

#### Scenario: 当前周期别名写入

- **WHEN** 写入 `1m/1/5m/5/15m/15/30m/30/1h/60/1d/D/1w/W/M`
- **THEN** 每条记录进入预期分区，且既有自然键冲突处理保持有效

#### Scenario: 未知周期写入

- **WHEN** 写入未列入周期目录的值
- **THEN** 记录进入默认分区，不因缺少 LIST 分区导致采集任务中断

### Requirement: 幂等分区生命周期命令

系统 SHALL 提供默认 dry-run 的分区管理命令，可生成影子表 DDL并维护未来 3 个月的分钟分区。
任何实际 DDL SHALL 要求 PostgreSQL、显式 `--apply`、显式影子表名和确认参数。

#### Scenario: 重复规划同一月份

- **WHEN** 对相同影子表和月份重复执行
- **THEN** 计划稳定且 apply 幂等，不重复创建或覆盖既有分区

#### Scenario: 误指向活动表

- **WHEN** 目标表名为 `kline_data`
- **THEN** 命令拒绝执行，即使提供 `--apply`

### Requirement: 隔离迁移演练

系统 SHALL 支持将源 `kline_data` 复制到显式影子表进行演练，并在成功前验证：

- 总行数和按周期分组计数一致；
- 最早/最晚交易时间一致；
- 自然键无重复；
- 影子表序列大于当前最大 `id`；
- ORM 核心查询、批量 `ON CONFLICT DO NOTHING` 和级联外键语义通过；
- 查询计划能够裁剪目标分钟分区。

演练失败 SHALL 回滚或删除本轮创建的影子资源，并保留脱敏 `trace_id` 诊断。

#### Scenario: 演练校验不一致

- **WHEN** 任一计数、边界、约束或查询语义不一致
- **THEN** 演练失败且不得生成可切换结论

### Requirement: K 线存储观测

系统 SHALL 为管理员提供只读 K 线存储概况，并避免在每次 Prometheus scrape 时执行高成本全表扫描。
PostgreSQL 概况 SHALL 包含容量、行数估计、分区数、未来分区覆盖和最后采集时间；SQLite SHALL
返回基础行数和 `partitioning_supported=false`。

#### Scenario: 普通用户访问

- **WHEN** 非管理员请求 K 线存储概况
- **THEN** 返回 403，不暴露数据库容量和分区结构

## MODIFIED Requirements

### Requirement: Benchmark 默认只读

`benchmark_kline.py` SHALL 默认仅使用现有数据。只有显式 `--seed` 时才允许生成 BENCH 品种、
合约、换月和 K 线；输出 SHALL 支持结构化 JSON，并区分 p50、p95、p99 与样本数。

#### Scenario: 空数据库默认运行

- **WHEN** 未提供 `--seed` 且没有 benchmark 数据
- **THEN** 命令以可解释的非 0 状态结束，不写入任何业务表

### Requirement: 迭代文档与远程交付

R8 完成后 SHALL 更新 `CHANGELOG.md`、`AGENTS.md`、`.agents/`、README、当前迭代计划、
`python/docs/kline_partitioning.md`、发布清单和新的非生产发布记录。文档 SHALL 明确区分：

- 已完成的容量门禁、影子 DDL、隔离演练和观测；
- 尚未执行的活动表切换、真实冷数据导出/删除和生产恢复演练。

全部本地及远程门禁通过后 SHALL 推送 GitHub，并确认工作区干净。

#### Scenario: R8 工程验收完成

- **WHEN** 代码、PostgreSQL 集成、全量测试、CI 和文档均通过
- **THEN** R8 提交推送至 `origin/master`，但发布记录仍标注为非生产分区

## REMOVED Requirements

### Requirement: Benchmark 自动造数

**Reason**: 只读性能检查不应在未确认时写入数据库或污染生产统计。

**Migration**: 需要生成隔离 benchmark 数据时显式使用 `--seed`，并使用专用测试数据库。

### Requirement: R8 自动切换活动表或删除冷数据

**Reason**: 当前无法证明生产阈值已达到，且活动表切换需要真实容量报告、备份恢复和维护窗口。

**Migration**: R8 仅产出可审计证据和影子迁移能力；达到阈值后另立生产切换/归档规格。
