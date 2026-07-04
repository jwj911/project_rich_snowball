<!-- .agents/backend.md — 后端开发规则 -->

## 基础约定

- 导入顺序：标准库 → 第三方库 → 本项目模块。
- 数据库会话统一使用 `dependencies.get_db()`，避免手动创建 `SessionLocal()` 后忘记关闭。
- 路由按领域拆分为 `APIRouter`，在 `main.py` 统一挂载。
- 密码必须用 `utils.hash_password()`，禁止明文、MD5、SHA256。
- JWT 解码捕获 PyJWT 异常，不要裸 `except:`。
- 评论内容通过 Pydantic validator 和 `html.escape()` 做 XSS 过滤，长度限制在 schema 中维护。

## 已完成的重大重构

- **ProductDB 已完全退场**（2026-05-28）：物理表已删除，`comments.product_id` 列已删除，所有前后端代码、测试、schema 已清理。品种数据统一走 `VarietyDB` / `RealtimeQuoteDB` / `KlineDataDB` + `/api/varieties`、`/api/realtime`、`/api/klines`。
- **CSRF 防护**（2026-05-29）：`dependencies.py` 方法感知鉴权，POST/PUT/PATCH/DELETE 只接受 `Authorization: Bearer` header，GET/HEAD 保持 cookie 兼容。
- **错误码契约**（2026-06-04）：`python/errors.py` 定义 `ErrorCode(StrEnum)`，38 个稳定业务错误码；`ServiceError` 及其子类（`NotFoundError`、`ForbiddenError` 等）携带 `code` 参数；全局 exception handler 统一返回 `{code, message, errors, timestamp}`。新增 router 业务错误优先使用 `ServiceError` 而非裸 `HTTPException`。
- **API 版本映射**（2026-06-24）：`ApiVersionMiddleware` 将 `/api/v1/*` 透明映射到 `/api/*`，`/api/` 继续兼容；新代码优先使用 `/api/v1/*`。
- **因子新增规范**（2026-07-04）：新增因子须统一使用 `open/high/low/close/volume/amount` 字段；缺失 `amount` 时用 `close * volume` 近似；所有除法须防除零（`.replace(0, np.nan)` 或 `+ 1e-10`）；`rolling`/`ewm` 须设 `min_periods=1`；每个函数须有完整中文 docstring 说明逻辑与信号方向；同步更新 `tests/test_wanfactor_indicators.py` 与 `docs/factor_integration.md`。

## 数据采集链路

- 遵循 `collector -> adapter -> cleaner -> pipeline -> upsert`。
- upsert 逻辑在 `data_collector/upsert.py`，已兼容 SQLite / PostgreSQL 双方言。

## 生产环境约束

- 生产环境约束在 `config.py`：必须设置强 `SECRET_KEY`（>=32 字符），且不允许 SQLite。
- `/docs`、`/redoc`、`/openapi.json` 在生产环境应关闭。

## 限流与可观测性

- 全局限流中间件覆盖所有写入端点（POST/PUT/PATCH/DELETE），默认 60 秒窗口内 100 请求；高成本 GET（`/api/realtime/batch`、`/api/realtime/stream`）有独立限流窗口。
- 每个请求都有 `X-Request-ID`，通过 `request_id_middleware` 注入，structlog 上下文自动绑定。
- Prometheus 指标通过 `prometheus_middleware` 自动收集，排除 `/metrics`、`/docs`、`/redoc`、`/openapi.json`。
- `/metrics` 端点限制为可信内网 IP，外网返回 403。

## 关键配置

- `pyproject.toml`：项目名 `futures-community-api`，版本 `2.0.0`，`requires-python = ">=3.11"`。
- Ruff：`target-version = "py311"`，`line-length = 120`，启用 `E,W,F,I,N,UP,B,C4,SIM`，忽略 `E501`。
- mypy：`python_version = "3.11"`，排除了 `data_collector/`（除 `pipeline_tasks` 外）、`routers/`、`models.py`、`tests/`、`alembic/` 等目录，用于规避 SQLAlchemy 1.x 类型误报。
- `requirements.txt` 记录直接依赖，`requirements.lock` 为 CI 安装源（全锁定）。

## 测试

后端已有 pytest（50 个文件，含 `conftest.py`）：

- `test_p0_fixes.py`
- `test_phase1_3_integration.py`
- `test_api_version.py`
- `test_cors_variable.py`
- `test_kline_seeded_api.py`
- `test_kline_service.py`
- `test_comment_validation_and_pagination.py`
- `test_cache_orm_detached.py`
- `test_postgres_upsert_integration.py`
- `test_production_config.py`
- `test_watchlists.py`
- `test_price_levels.py`
- `test_workspace.py`
- `test_workspace_api.py`
- `test_contracts.py`
- `test_pipeline_rollover.py`
- `test_circuit_breaker.py`
- `test_scheduler_health.py`
- `test_realtime_batch.py`
- `test_realtime_sse.py`
- `test_backfill_kline_contract_id.py`
- `test_data_quality.py`
- `test_metrics.py`
- `test_ondelete_cascade.py`
- `test_products_query.py`
- `test_rate_limit_middleware.py`
- `test_rate_limit_redis.py`
- `test_refresh_token.py`
- `test_trading_date.py`
- `test_csrf_protection.py`
- `test_frontend_logs.py`
- `test_frontend_logs_query.py`
- `test_metrics_dashboard.py`
- `test_varieties_enhanced.py`
- `test_service_error_handler.py`
- `test_settings.py`
- `test_news.py`
- `test_opinions.py`
- `test_chat.py`
- `test_portfolio.py`
- `test_price_alerts.py`
- `test_password_strength.py`
- `test_alert_events.py`
- `test_agents_core.py`
- `test_backtest_agent.py`
- `test_strategy_compiler.py`
- `test_strategies.py`
- `test_technical_indicators.py`
- `test_factors_router.py`
- `test_wanfactor_indicators.py`
- `test_market_data_service.py`
- `test_backup_scripts.py`

运行方式见 `../AGENTS.md` 中的「常用命令速查」。
