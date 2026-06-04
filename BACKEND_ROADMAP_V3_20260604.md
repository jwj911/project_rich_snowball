# 后端迭代路线图 v3

> 基于 `BACKEND_FIX_ACCEPTANCE_HANDOFF_V6_1_20260530.md` + `BACKEND_ARCHITECTURE_AUDIT_V7_20260601.md`
> 生成日期：2026-06-04
> 策略：按阶段推进，每阶段独立验证、独立提交，不一次性大重构

---

## 总体目标

将后端从当前 **B-/B 级** 提升到 **B+/A- 级**，核心产出：
1. 本地测试环境 100% 可复现
2. P1 安全/数据问题清零
3. 权限模型有最小 RBAC
4. 错误码契约有文档、有代码
5. CI 增加迁移一致性校验

---

## 阶段一：基础可运行性（Day 1）✅ 已完成

**目标**：修复本地 `.venv` 失效，让 pytest 可运行。这是所有后续迭代的前提。

| # | 行动项 | 范围 | 验收标准 | 状态 |
|---|--------|------|----------|------|
| 1.1 | 重建 `python/.venv` 并安装 `requirements.lock` | `python/` | `python/.venv/Scripts/python.exe -c "import sqlalchemy; print(sqlalchemy.__version__)"` 输出 >= 2.0.25 | ✅ 无需重建，venv 正常 |
| 1.2 | 跑通代表 pytest | `python/tests/` | 以下测试全部通过：`test_production_config.py`, `test_realtime_sse.py`, `test_csrf_protection.py`, `test_cors_variable.py`, `test_price_levels.py`, `test_metrics_dashboard.py`, `test_trading_date.py` | ✅ 77 passed, 0 failed |
| 1.3 | 跑全量 pytest | `python/tests/` | `pytest tests -q --tb=short` 通过 | ✅ 359 passed, 6 skipped, 0 failed |
| 1.4 | 更新 AGENTS.md 中 venv 路径提示 | `AGENTS.md` | 如有失效路径引用，同步修正 | ✅ 无失效路径，AGENTS.md 已正确引用 `.venv\Scripts\python.exe` |

**完成时间**：2026-06-04
**测试环境**：Windows PowerShell, Python 3.12.9, SQLAlchemy 2.0.25
**实际结果**：`.venv` 状态良好，绑定路径正确（`D:\Code\project_rich_snowball\python\.venv\Scripts\python.exe`），审计报告中的 venv 失效问题已自然修复（可能由之前的环境重建完成）。全量 359 个测试通过，6 个跳过（均为预期跳过），无失败。

**交付物**：本地测试环境可复现，全量 pytest 通过。

---

## 阶段二：安全与数据一致性修复（P1 清零，Day 2-5）

**目标**：修复 v7 审计全部 6 个 P1 问题 + v6.1 的 metrics 权限 + varieties N+1。

### 2.1 前端日志入口加固
| # | 行动项 | 范围 | 验收标准 |
|---|--------|------|----------|
| 2.1.1 | 鉴权归属：从 token/cookie 解析真实 user_id，忽略客户端传入 user_id | `routers/frontend_logs.py`, `schemas.py` | 未认证请求只能匿名入库（`user_id=None`）；带 token 请求按 token 中的 user_id 落库；客户端伪造 user_id 无效 |
| 2.1.2 | Payload 限制：限制字节数（≤8KB）、层级深度（≤3）、key 数量（≤20） | `schemas.py`, `routers/frontend_logs.py` | 超限返回 422；超大 payload 不进入 DB 也不写服务端日志 |
| 2.1.3 | 补负向测试 | `tests/test_frontend_logs.py` | 新增：伪造 user_id 无效、超大 payload 422、嵌套过深 422 |

### 2.2 新闻 RSS SSRF/超时修复
| # | 行动项 | 范围 | 验收标准 |
|---|--------|------|----------|
| 2.2.1 | URL 校验：改为 `HttpUrl`，禁止内网地址（localhost/private/link-local/file） | `schemas.py`, `services/news_fetcher.py` | 内网 URL 被 schema/服务层拒绝，返回 422 |
| 2.2.2 | 超时：feedparser 前先用 httpx 带 timeout 抓取 | `services/news_fetcher.py` | 慢 URL 10 秒内超时，不阻塞 worker |
| 2.2.3 | 可选后台化：手动 fetch 改后台任务或 scheduler job | `routers/news.py` | 手动 fetch 不阻塞 API 响应 |
| 2.2.4 | 补 SSRF/timeout 测试 | `tests/test_news.py` | 新增：内网 URL 被拒、慢源超时 |

### 2.3 Opinions XSS 清洗
| # | 行动项 | 范围 | 验收标准 |
|---|--------|------|----------|
| 2.3.1 | `OpinionCreate.reason` / `OpinionUpdate.reason` 复用 `sanitize_html_text` | `schemas.py` | `<script>` 被 escape |
| 2.3.2 | 补测试 | `tests/test_opinions.py` | 新增：包含 `<script>` 的 reason 落库后被清洗 |

### 2.4 Realtime batch symbols 上限
| # | 行动项 | 范围 | 验收标准 |
|---|--------|------|----------|
| 2.4.1 | 参数增加 `max_items=50`（与 SSE 上限统一） | `routers/realtime.py` | 超限返回 422/400，有明确 error message |
| 2.4.2 | 补测试 | `tests/test_realtime_batch.py` | 新增：51 个 symbols 返回 422 |

### 2.5 Comments FK 语义修复
| # | 行动项 | 范围 | 验收标准 |
|---|--------|------|----------|
| 2.5.1 | `comments.variety_id`：二选一，改为 `ondelete="CASCADE"`（因为当前有 nullable=False） | `models.py` | 删除 variety 时关联 comments 被级联删除 |
| 2.5.2 | 生成 Alembic 迁移 | `alembic/versions/` | 迁移脚本在 SQLite 和 PG 均可执行 |
| 2.5.3 | 补测试 | `tests/test_ondelete_cascade.py` 或新建 | 删除 variety 后 comments 清理行为在 SQLite/PG 均通过 |

### 2.6 Price levels 唯一约束
| # | 行动项 | 范围 | 验收标准 |
|---|--------|------|----------|
| 2.6.1 | PG：增加 partial unique indexes（`contract_id IS NULL` 与 `IS NOT NULL` 分开） | `models.py`（索引定义） | 并发创建同一 continuous/main 标注只有 1 条成功 |
| 2.6.2 | 保留应用层查重作为兜底 | `repositories/price_level_repository.py` | 应用层和 DB 层双重保护 |
| 2.6.3 | 生成 Alembic 迁移 | `alembic/versions/` | PG 下 partial index 生效 |
| 2.6.4 | 补集成测试 | `tests/test_price_levels.py` | 并发/重复场景测试通过 |

### 2.7 Metrics dashboard admin 权限
| # | 行动项 | 范围 | 验收标准 |
|---|--------|------|----------|
| 2.7.1 | 增加 `require_admin_user` dependency | `dependencies.py` | 从 JWT role 或 `ADMIN_USERNAMES` 环境变量判断 |
| 2.7.2 | Metrics dashboard router 替换为 admin dependency | `routers/metrics_dashboard.py` | 普通用户 403，admin 200 |
| 2.7.3 | 补测试 | `tests/test_metrics_dashboard.py` | 新增：普通用户 403、admin 200 |
| 2.7.4 | 前端 `/metrics` 页面处理 403 | `frontend/app/metrics/page.tsx` | 403 时显示无权限提示 |

### 2.8 Varieties detail 评论 N+1
| # | 行动项 | 范围 | 验收标准 |
|---|--------|------|----------|
| 2.8.1 | 评论查询增加 `selectinload(CommentDB.user)` | `routers/varieties.py` | 保持响应契约不变 |
| 2.8.2 | 补查询数量验证测试 | `tests/test_varieties_enhanced.py` 或新建 | 用 SQLAlchemy event 统计，评论数增加不线性增加查询次数 |

**阶段二交付物**：6 个 P1 清零 + 2 个 v6.1 优先项修复，新增 10+ 个负向/边界测试。

---

## 阶段三：错误处理与契约收口（Day 5-7）

**目标**：ServiceError 有全局 handler，错误码有稳定契约。

| # | 行动项 | 范围 | 验收标准 |
|---|--------|------|----------|
| 3.1 | ServiceError 全局 exception handler 完善 | `main.py` | 所有 router 抛出的 `ServiceError` 统一返回 `{code, message}`，不回退成 500 |
| 3.2 | 统一错误码枚举 | 新建 `errors.py` 或 `schemas.py` | 定义业务错误码枚举（如 `INVALID_SYMBOL`、`RATE_LIMITED`、`NOT_FOUND`），与 HTTP status 分离 |
| 3.3 | 至少改造 2 条主路径使用新错误码 | 选 `routers/realtime.py` + `routers/auth.py` | 错误响应 `code` 是业务码而非状态码字符串 |
| 3.4 | 写入错误码契约文档 | `python/docs/api_error_contract.md` | 包含：错误体结构、code 定义、HTTP status 映射、示例 |
| 3.5 | 补测试 | `tests/test_service_error_handler.py` | 验证 ServiceError 各分支输出稳定 |

**阶段三交付物**：错误码文档 + 代码落地，前端可基于 `code` 做稳定处理。

---

## 阶段四：扩展性与限流（P2 核心，Day 7-10）

**目标**：高成本 GET/SSE 有限流保护，缓存穿透更稳定，登录限流可扩展。

| # | 行动项 | 范围 | 验收标准 |
|---|--------|------|----------|
| 4.1 | 高成本 GET 限流 | `middleware/rate_limit.py` | `/api/varieties/{symbol}/detail`、`/api/klines/*`、`/api/realtime/*` 等增加独立限流窗口（如 IP 级 60 秒 30 请求） |
| 4.2 | SSE 独立限流 | `middleware/rate_limit.py` 或 `routers/realtime.py` | SSE 按 IP+user 限流，超限时返回 429 而非静默断开 |
| 4.3 | 登录/注册限流 Redis 化 | `routers/auth.py` | 与全局限流 middleware 统一，使用 Redis 存储窗口状态；进程内 dict 作为降级 |
| 4.4 | Redis 空值标记修复 | `services/cache.py` | 用常量字符串 `_EMPTY_MARKER` 替代对象 identity 比较，穿透防护在 Redis 路径稳定 |
| 4.5 | SSE query token 移除（或降级为开发模式） | `routers/realtime.py` | 生产环境强制 cookie-only；query token 仅在 `ENV=development` 可用或完全移除 |
| 4.6 | 补测试 | 各相关 test 文件 | 新增限流 429、空值标记穿透防护测试 |

**阶段四交付物**：读接口有保护，多实例部署后限流可共享。

---

## 阶段五：CI/运维与架构优化（Day 10-14）

**目标**：CI 增加迁移校验，架构文档补齐，技术债逐步偿还。

| # | 行动项 | 范围 | 验收标准 |
|---|--------|------|----------|
| 5.1 | CI 增加 Alembic 迁移一致性检查 | `.github/workflows/backend-ci.yml` | 执行 `alembic upgrade head` 通过；可添加 autogenerate drift check |
| 5.2 | CI 增加覆盖率阈值（低起点） | `.github/workflows/backend-ci.yml` | 增加 `pytest-cov`，先设 30% 阈值，逐步提升 |
| 5.3 | SSE 部署约束文档 | `python/docs/sse_scaling_strategy.md` 或 README | 明确：单实例限制 / sticky session / 未 Redis 化前不宣称横向扩展完成 |
| 5.4 | K 线表分区策略文档（先文档后代码） | 新建 `python/docs/kline_partitioning.md` | 包含：按 period + trading_time 的 range partition 方案、冷数据归档策略、实施时机（数据量阈值） |
| 5.5 | 交易日历预测告警 | `services/trading_calendar.py` | 当使用预测日期时，日志输出 warning；或增加 metric 计数 |
| 5.6 | 部分 router 业务下沉（选 1-2 个试点） | `routers/varieties.py` 或 `routers/opinions.py` | 提取 service 层，router 只负责 HTTP 契约转换 |
| 5.7 | 补 compose backend service | `docker-compose.yml` | 取消 backend 注释，提供本地一键后端部署（可选，受限于测试时间） |

**阶段五交付物**：CI 更严格，运维有文档，架构有方向。

---

## 迭代顺序总览

```
Day 1   [阶段一]  venv 修复 + 测试跑通
Day 2-3 [阶段二前半] 日志加固 + RSS SSRF + opinions XSS + realtime batch 上限
Day 4-5 [阶段二后半] comments FK + price_levels 约束 + metrics admin + varieties N+1
Day 5-7 [阶段三]   ServiceError handler + 错误码契约 + 文档
Day 7-10[阶段四]   GET/SSE 限流 + Redis 空值标记 + 登录限流 Redis 化 + SSE token
Day 10-14[阶段五]  CI 迁移校验 + 覆盖率 + 文档补齐 + 架构试点
```

---

## 风险与回退策略

| 风险 | 缓解措施 |
|------|----------|
| Alembic 迁移在 SQLite 和 PG 行为不一致 | 每个迁移在两种数据库上测试；SQLite 不支持的部分用 `op.execute` 条件分支 |
| 限流改造误伤正常用户 | 先调宽阈值（如 GET 60 秒 100 请求），观察后再收紧 |
| 错误码改造破坏前端 | 保留旧 `code` 做 backward compatible，逐步迁移 |
| 时间超预期 | 阶段二（P1 清零）是硬性 deadline，阶段四/五可顺延 |

---

## 验收里程碑

| 里程碑 | 检查项 |
|--------|--------|
| M1（Day 1） | `pytest tests -q` 全绿 |
| M2（Day 5） | P1 问题数 = 0；metrics dashboard 403/200 测试通过；varieties detail N+1 查询数验证通过 |
| M3（Day 7） | `api_error_contract.md` 存在；至少 2 个 router 使用新错误码；ServiceError handler 测试通过 |
| M4（Day 10）| GET/SSE 限流测试 429 通过；Redis 空值标记穿透测试通过 |
| M5（Day 14）| CI 增加 alembic + cov 步骤且通过；sse_scaling_strategy.md 已更新 |

---

*生成于 2026-06-04，供后端迭代使用。*
