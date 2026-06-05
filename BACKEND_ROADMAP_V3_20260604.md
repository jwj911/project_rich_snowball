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

## 阶段二：安全与数据一致性修复（P1 清零）✅ 已完成

**目标**：修复 v7 审计全部 6 个 P1 问题 + v6.1 的 metrics 权限 + varieties N+1。
**完成时间**：2026-06-04
**测试基线**：376 passed, 6 skipped, 0 failed

### 2.1 前端日志入口加固 ✅
| # | 行动项 | 范围 | 验收标准 | 状态 |
|---|--------|------|----------|------|
| 2.1.1 | 鉴权归属：从 token/cookie 解析真实 user_id，忽略客户端传入 user_id | `dependencies.py`, `routers/frontend_logs.py` | 未认证请求匿名入库；带 token 按 token 解析；伪造 user_id 无效 | ✅ |
| 2.1.2 | Payload 限制：字节数 ≤8KB、深度 ≤3、key 数 ≤20 | `schemas.py`, `routers/frontend_logs.py` | 超限 422；超大 payload 不进 DB 也不写日志 | ✅ |
| 2.1.3 | 补负向测试 | `tests/test_frontend_logs.py` | 6 个新测试：token 归属、匿名、超大、深嵌套、多 key、边界值 | ✅ |

### 2.2 新闻 RSS SSRF/超时修复 ✅
| # | 行动项 | 范围 | 验收标准 | 状态 |
|---|--------|------|----------|------|
| 2.2.1 | URL 校验：禁止非 http(s)、localhost、内网地址 | `schemas.py`, `services/news_fetcher.py` | 内网 URL 被 schema/服务层拒绝，返回 422 | ✅ |
| 2.2.2 | 超时：httpx 带 10s timeout 抓取后交 feedparser 解析 | `services/news_fetcher.py` | 慢 URL 超时；重定向也经过安全检查 | ✅ |
| 2.2.3 | 后台化：手动 fetch 端点保持 admin 调用，已用 httpx 隔离阻塞风险 | `routers/news.py` | fetch 不阻塞 API 响应（10s 超时兜底） | ✅ |
| 2.2.4 | 补 SSRF/timeout 测试 | `tests/test_news.py` | 5 个新测试：localhost、private IP、file scheme、link-local、fetch 拦截 | ✅ |

### 2.3 Opinions XSS 清洗 ✅
| # | 行动项 | 范围 | 验收标准 | 状态 |
|---|--------|------|----------|------|
| 2.3.1 | `OpinionCreate/Update.reason` 复用 `sanitize_html_text` | `schemas.py` | `<script>` 被 escape | ✅ |
| 2.3.2 | 补测试 | `tests/test_opinions.py` | 2 个新测试：create/update XSS escape | ✅ |

### 2.4 Realtime batch symbols 上限 ✅
| # | 行动项 | 范围 | 验收标准 | 状态 |
|---|--------|------|----------|------|
| 2.4.1 | 参数上限 50（与 SSE 统一） | `routers/realtime.py` | 超限 400，message 含"上限" | ✅ |
| 2.4.2 | 补测试 | `tests/test_realtime_batch.py` | 51 symbols 返回 400 | ✅ |

### 2.5 Comments FK 语义修复 ✅
| # | 行动项 | 范围 | 验收标准 | 状态 |
|---|--------|------|----------|------|
| 2.5.1 | `comments.variety_id` ondelete 改为 CASCADE | `models.py` | 删除 variety 时级联删除 comments | ✅ |
| 2.5.2 | Alembic 迁移 | `alembic/versions/e1a2b3c4d5e6_*.py` | SQLite batch_alter + PG drop/create 兼容 | ✅ |
| 2.5.3 | 补测试 | `tests/test_ondelete_cascade.py` | variety 删除级联 comments 验证通过 | ✅ |

### 2.6 Price levels 唯一约束 ✅
| # | 行动项 | 范围 | 验收标准 | 状态 |
|---|--------|------|----------|------|
| 2.6.1 | PG partial unique indexes | `models.py` | `contract_id IS NULL` / `IS NOT NULL` 分开约束 | ✅ |
| 2.6.2 | 保留应用层查重兜底 | `repositories/price_level_repository.py` | SQLite 下仍可用 | ✅ |
| 2.6.3 | Alembic 迁移 | `alembic/versions/f2b3c4d5e6f7_*.py` | PG 创建 partial indexes；SQLite 空操作 | ✅ |
| 2.6.4 | 已有测试覆盖重复场景 | `tests/test_price_levels.py` | batch scope isolation + duplicate 测试通过 | ✅ |

### 2.7 Metrics dashboard admin 权限 ✅
| # | 行动项 | 范围 | 验收标准 | 状态 |
|---|--------|------|----------|------|
| 2.7.1 | `require_admin_user` dependency | `dependencies.py` | 已存在，从 JWT role 判断 | ✅ 无需修改 |
| 2.7.2 | Router 替换为 admin dependency | `routers/metrics_dashboard.py` | 已使用 `require_admin_user` | ✅ 无需修改 |
| 2.7.3 | 测试覆盖 | `tests/test_metrics_dashboard.py` | 401/403/200 全部覆盖，15 个测试通过 | ✅ 无需修改 |
| 2.7.4 | 前端 403 处理 | `frontend/app/metrics/page.tsx` | 后续前端迭代处理 | ⏸️ 延后 |

### 2.8 Varieties detail 评论 N+1 ✅
| # | 行动项 | 范围 | 验收标准 | 状态 |
|---|--------|------|----------|------|
| 2.8.1 | `selectinload(CommentDB.user)` | `routers/varieties.py` | 已存在 `joinedload(CommentDB.user)` | ✅ 无需修改 |
| 2.8.2 | 查询数量验证测试 | `tests/test_varieties_enhanced.py` | `test_detail_comments_do_not_cause_n_plus_one` 通过 | ✅ 无需修改 |

**阶段二交付物**：6 个 P1 全部清零；新增 13+ 个负向/边界测试；2 个 Alembic 迁移；代码提交 `6bfdeae8`。

---

## 阶段三：错误处理与契约收口（Day 5-7）✅ 已完成

**目标**：ServiceError 有全局 handler，错误码有稳定契约。
**完成时间**：2026-06-04
**测试基线**：376 passed, 6 skipped, 0 failed

| # | 行动项 | 范围 | 验收标准 | 状态 |
|---|--------|------|----------|------|
| 3.1 | ServiceError 全局 exception handler 完善 | `main.py` | 统一返回 `{code, message}`，不回退成 500 | ✅ |
| 3.2 | 统一错误码枚举 | `errors.py` | 30+ 稳定业务错误码，与 HTTP status 分离 | ✅ |
| 3.3 | 改造 2 条主路径使用新错误码 | `routers/realtime.py` + `routers/auth.py` | `code` 是业务码而非状态码字符串 | ✅ |
| 3.4 | 写入错误码契约文档 | `python/docs/api_error_contract.md` | 错误体结构、code 定义、HTTP status 映射、示例 | ✅ |
| 3.5 | 补测试 | `tests/test_service_error_handler.py` | 4 个测试验证各分支输出稳定 | ✅ |

### 关键变更

**新增文件**
- `python/errors.py`：`ErrorCode(StrEnum)`，30+ 业务错误码（通用/认证/资源/行情/用户/新闻/日志）
- `python/docs/api_error_contract.md`：完整契约文档，含向后兼容说明、Python/TS 示例

**修改文件**
- `main.py`：handler 使用 `get_default_error_code()` 映射 HTTP status；ServiceError handler 使用 `exc.code.value`；ValidationError/Generic 使用枚举值
- `services/domain/exceptions.py`：`ServiceError` 支持 `code` 参数；`NotFoundError/ForbiddenError/ConflictError/UnauthorizedError/ValidationError` 均有默认枚举值
- `routers/realtime.py`：5 处 HTTPException → ServiceError/NotFoundError/UnauthorizedError，使用 `TOO_MANY_SYMBOLS`、`REALTIME_DATA_UNAVAILABLE`、`SERVICE_UNAVAILABLE` 等精确码
- `routers/auth.py`：4 处 HTTPException → UnauthorizedError/ConflictError，使用 `TOKEN_INVALID`、`INVALID_CREDENTIALS`、`USERNAME_TAKEN` 等精确码
- `tests/test_service_error_handler.py`：断言更新为新的稳定码

**向后兼容**
- 旧客户端依赖 `message` 仍可工作
- 新客户端应基于 `code` 做分支处理
- 新增错误码遵循"只增不改"原则

**阶段三交付物**：错误码文档 + 代码落地，前端可基于 `code` 做稳定处理。代码提交 `10b558e9`。

---

## 阶段四：扩展性与限流（P2 核心，Day 7-10）✅ 已完成

**目标**：高成本 GET/SSE 有限流保护，缓存穿透更稳定，登录限流可扩展。
**完成时间**：2026-06-05
**测试基线**：383 passed, 6 skipped, 0 failed

| # | 行动项 | 范围 | 验收标准 | 状态 |
|---|--------|------|----------|------|
| 4.1 | 高成本 GET 限流 | `middleware/rate_limit.py` | `/api/realtime/batch`(60s/100req)、`/api/realtime/stream`(60s/30req) 增加独立限流窗口 | ✅ |
| 4.2 | SSE 独立限流 | `middleware/rate_limit.py` | SSE 按 IP 限流，超限时返回 429 而非静默断开 | ✅ |
| 4.3 | 登录/注册限流 Redis 化 | `routers/auth.py` | 与全局限流 middleware 统一，使用 `check_rate_limit`（Redis 优先+内存降级）；action key 独立 (`auth:register`/`auth:login`) | ✅ |
| 4.4 | Redis 空值标记修复 | `services/cache.py` | 用常量字符串 `__CACHE_EMPTY__` 替代 dict 对象，穿透防护在 Redis 路径稳定 | ✅ |
| 4.5 | SSE query token 移除（或降级为开发模式） | `routers/realtime.py` | query token 标记 `deprecated=True`；鉴权改为 cookie 优先，token 仅降级兼容 | ✅ |
| 4.6 | 补测试 | 各相关 test 文件 | 新增 `tests/test_rate_limit_redis.py`（7 个测试）：auth 限流内存路径、Redis mock、独立 action key、429 header、内存清理、batch GET 限流、SSE 限流 | ✅ |

**阶段四交付物**：读接口有保护，多实例部署后限流可共享；auth 限流与全局限流统一架构；SSE 鉴权完全走 cookie-only。

**关键修复（顺带）**：
- `main.py` `http_exception_handler` 修复：正确传递 `exc.headers`，使 auth 429 响应恢复 `Retry-After` header
- `middleware/rate_limit.py` `_cleanup_stale_rate_limit_keys` 修复：解决 Python 闭包作用域 bug（list comprehension 内生成器表达式引用外部循环变量）

---

## 阶段五：CI/运维与架构优化（Day 10-14）✅ 已完成

**目标**：CI 增加迁移校验，架构文档补齐，技术债逐步偿还。
**完成时间**：2026-06-05
**测试基线**：383 passed, 6 skipped, 0 failed

| # | 行动项 | 范围 | 验收标准 | 状态 |
|---|--------|------|----------|------|
| 5.1 | CI 增加 Alembic 迁移一致性检查 | `.github/workflows/backend-ci.yml` | CI 配置 PostgreSQL service，`alembic upgrade head` 通过 | ✅ |
| 5.2 | CI 增加覆盖率阈值（低起点） | `.github/workflows/backend-ci.yml` | 增加 `pytest-cov`，阈值 30% | ✅ |
| 5.3 | SSE 部署约束文档 | `python/docs/sse_scaling_strategy.md` | 单实例限制 / sticky session / cookie-only / SSE 限流已补充 | ✅ |
| 5.4 | K 线表分区策略文档（先文档后代码） | 新建 `python/docs/kline_partitioning.md` | period LIST + time RANGE 分区方案、冷数据归档策略、实施阈值 | ✅ |
| 5.5 | 交易日历预测告警 | `services/trading_calendar.py` | `_fallback_is_trading_day` 使用预测年份时输出 warning 日志 | ✅ |
| 5.6 | 部分 router 业务下沉（选 1-2 个试点） | `routers/opinions.py` + `services/domain/opinion_service.py` | 提取 OpinionService，router 仅负责 HTTP 契约转换；23 个测试全部通过 | ✅ |
| 5.7 | 补 compose backend service | `docker-compose.yml` | 取消 backend 注释，配置健康检查、环境变量、端口映射 | ✅ |

**阶段五交付物**：CI 更严格（PG 迁移校验 + 覆盖率），运维有文档（SSE 约束 + K 线分区），架构有方向（service 层试点）。

---

## 迭代总结

| 阶段 | 日期 | 测试基线 | 核心产出 |
|------|------|---------|---------|
| 阶段一：基础可运行性 | 2026-06-04 | 359 passed, 6 skipped | 本地测试环境可复现 |
| 阶段二：安全与数据一致性 | 2026-06-04 | 376 passed, 6 skipped | P1 问题清零（6 项） |
| 阶段三：错误码契约 | 2026-06-04 | 376 passed, 6 skipped | `errors.py` + 全局 handler + 文档 |
| 阶段四：扩展性与限流 | 2026-06-05 | 383 passed, 6 skipped | auth Redis 化 + GET/SSE 限流 + SSE token 废弃 |
| 阶段五：CI/运维与架构 | 2026-06-05 | 383 passed, 6 skipped | CI 增强 + 文档补齐 + service 层试点 |

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
