# PostgreSQL 集成验收指南

> 本文档面向后端开发者与新加入的 AI 编程助手。  
> 目的：验证后端在 PostgreSQL 上的功能完整性，确保 SQLite 开发路径与 PG 生产路径等价。

---

## 1. 前置条件

- Docker Desktop 或兼容容器运行时
- PowerShell（Windows）或 Bash（Linux/macOS）
- 项目根目录 `d:\Code\project_rich_snowball`（以下命令以此为准，请根据实际调整）

---

## 2. 启动 PostgreSQL

```powershell
cd d:\Code\project_rich_snowball
docker-compose up -d postgres redis
```

验证服务状态：

```powershell
docker-compose ps
```

预期输出包含：
- `futures_postgres` → `Up (healthy)`，端口 `0.0.0.0:15432->5432/tcp`
- `futures_redis` → `Up`，端口 `0.0.0.0:6379->6379/tcp`

---

## 3. 配置环境变量

```powershell
$env:DATABASE_URL="postgresql://futures:futures123@localhost:15432/futures_community"
$env:SECRET_KEY="test-secret-key-for-local-dev-only-must-be-32-characters-long"
$env:ENABLE_SCHEDULER="0"
```

> **注意**：生产环境 `SECRET_KEY` 必须 >= 32 字符，且不可使用上述示例值。

---

## 4. 执行 Alembic 迁移

```powershell
cd d:\Code\project_rich_snowball\python
.\venv\Scripts\alembic upgrade head
```

验证：

```powershell
.\venv\Scripts\alembic current
```

应输出当前最新的 revision ID（例如 `head`）。

---

## 5. 运行 PG-only 测试

### 5.1 集成测试（ upsert 方言兼容性）

```powershell
cd d:\Code\project_rich_snowball\python
$env:DATABASE_URL="postgresql://futures:futures123@localhost:15432/futures_community"
$env:SECRET_KEY="test-secret-key-for-local-dev-only-must-be-32-characters-long"
$env:ENABLE_SCHEDULER="0"
.\venv\Scripts\python.exe -m pytest tests/test_postgres_upsert_integration.py -v
```

**预期结果**：全部通过（当 `DATABASE_URL` 为 PostgreSQL 时）；若连接不到 PG 则自动 skip。

### 5.2 全量测试套件

```powershell
.\venv\Scripts\python.exe -m pytest tests -q --tb=short
```

**预期结果**：与 SQLite 路径数量一致（约 230+ passed，少量 skip），无失败。

---

## 6. 连接池指标验证

启动后端：

```powershell
cd d:\Code\project_rich_snowball\python
$env:DATABASE_URL="postgresql://futures:futures123@localhost:15432/futures_community"
$env:SECRET_KEY="test-secret-key-for-local-dev-only-must-be-32-characters-long"
.\venv\Scripts\python.exe main.py
```

另开终端访问 metrics：

```powershell
curl http://127.0.0.1:8200/metrics | findstr db_pool
```

预期看到：
- `db_pool_connections_total`
- `db_pool_checkout_total`
- `db_pool_checkin_total`

---

## 7. 何时必须跑 PG 测试

以下变更**必须**在 PG 上验证后才能合并：

1. `models.py` 中新增/修改表结构（需确认 Alembic 迁移在 PG 上可执行）
2. `data_collector/upsert.py` 逻辑变更（需验证 PG `INSERT ... ON CONFLICT` 语法）
3. `routers/` 中涉及分页、排序、聚合的查询变更（PG 与 SQLite 方言差异）
4. 索引或约束变更（`EXPLAIN ANALYZE` 仅在 PG 上有意义）

以下变更**建议**在 PG 上抽查：

1. 纯业务逻辑变更（不触及 SQL 方言）
2. Schema/Pydantic 模型字段增减（不涉及 DB 查询）

---

## 8. 常见问题

### Q1: `alembic upgrade head` 报错 `connection refused`
- 检查 `docker-compose ps` 中 postgres 是否 `Up`
- 检查 `DATABASE_URL` 端口是否为 `15432`

### Q2: pytest 在无 PG 时全部 skip
- 这是预期行为。`test_postgres_upsert_integration.py` 等测试会检测 `DATABASE_URL`，非 PG 时自动 skip。
- 如需强制验证，必须按步骤 2-3 启动并配置 PG。

### Q3: 测试通过但生产仍报错
- 确认生产 `DATABASE_URL` 使用 PostgreSQL，且 `ENV=production`
- 确认 `SECRET_KEY` 长度 >= 32
- 确认 `CORS_ORIGINS` 已配置，不含 `*` 和 localhost

---

*最后更新：2026-05-29*
