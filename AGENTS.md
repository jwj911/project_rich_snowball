<!-- AGENTS.md — 期货交流社区 -->

> 本文档面向 AI 编程助手。进入本仓库后，先读这里，再动代码。
>
> **最后更新**：2026-07-04（Agent 系统体验修复计划 P0/P1 完成；新增因子 CRUD API 与测试，routers/factors.py 已上线；AGENTS.md 拆分为总-分结构）

---

## 项目定位与当前阶段

**期货交流社区**（产品名「倍增计划」）是一个前后端分离的期货行情与私密交流社区应用。当前产品形态为“登录后的行情工作台”。

- Phase 5「策略优化与性能调优」**已完成**（2026-07-04）：参数网格搜索、策略信号可视化、回测缓存、监控告警、全量测试（669 passed, 7 skipped, 0 failed）。
- **Agent 系统 Phase 0~2 已完成**：DataAgent、DataQualityAgent、TechAnalysisAgent、RiskManagementAgent、AnalysisPipelineAgent、StrategyCompilerAgent、BacktestAgent、FactorMiningAgent 已上线，前端 Chat 页支持 9 种模式切换，执行过程通过 SSE 真实流式展示。
- **Agent 系统体验修复计划 P0/P1 已完成**（2026-07-04）：流式事件升级为真实进度推送、风控使用品种真实合约参数、策略 DSL 成交量语义修正、LLM 客户端连接池与重试、执行器批量提交消除 SQLite 锁、SSE 取消与 malformed 行治理、移除悬空 `orchestrator` 能力。
- 近期新增：策略工作台、策略参数优化、回测信号可视化、预警中心、Agent 工作台。
- **已知测试问题**：无。`test_strategies.py` 事务隔离问题已修复，当前全量测试全绿。

---

## 文档导航（分册索引）

本仓库采用「总-分-总」结构：根目录 `AGENTS.md` 保留高频总览；详细内容拆分至 `.agents/` 目录下的主题分册。请按需要跳转：

| 分册 | 说明 |
|------|------|
| [.agents/project.md](.agents/project.md) | 项目概览、技术栈、目录结构 |
| [.agents/frontend.md](.agents/frontend.md) | 前端开发规则、关键配置、组件/Hooks/API 约定 |
| [.agents/backend.md](.agents/backend.md) | 后端开发规则、错误码/限流/测试、关键配置 |
| [.agents/data.md](.agents/data.md) | 数据采集与调度、PostgreSQL 与历史回填、后端文档目录 |
| [.agents/operations.md](.agents/operations.md) | 环境变量、构建/运行/测试命令、CI/CD、代码风格 |
| [.agents/security.md](.agents/security.md) | 生产环境强制要求、CSRF/XSS/SSRF、部署安全 |
| [.agents/agents.md](.agents/agents.md) | Agent 系统架构、Agent 划分、开发约束 |
| [.agents/roadmap.md](.agents/roadmap.md) | 模块演进状态、待处理 P1/P2 事项 |

---

## Git 工作流约定

- **默认在 `master` 分支工作**。每次新对话开始时，先执行 `git branch` 确认当前分支。
- 如果当前不在 `master`，**立即提醒用户**，并在征得同意后切换到 `master`（切换前用 `git stash` 保存未提交修改）。
- 如有明确需求要在其他分支操作，按用户指令执行。
- 修改前后都要用 `git status --short` 观察，不要回滚无关改动。
- **分支陷阱**：`codex/new_fronted` 等历史分支曾执行 `git filter-branch`，部分文件（如 `tushare_pg_ingest/*.py`）在那些分支上被移除。需要这些文件时务必在 `master` 上操作。

---

## 关键端口与环境

| 服务 | 地址/端口 | 说明 |
|------|-----------|------|
| 后端开发 | `127.0.0.1:8401` | `HOST`/`PORT` 可覆盖 |
| 前端开发 | `127.0.0.1:3200` | `npm run dev` |
| PostgreSQL | `localhost:15432` | docker-compose 映射 |
| Redis | `localhost:6379` | docker-compose 映射 |

环境变量速查：详见 [.agents/operations.md](.agents/operations.md)。

---

## 常用命令速查

### 启动后端

```powershell
cd python
python -m venv .venv
.venv/Scripts/python.exe -m pip install --upgrade pip
.venv/Scripts/python.exe -m pip install -r requirements.lock
$env:SECRET_KEY='change-this-to-a-real-secret'
.venv/Scripts/python.exe main.py
```

### 启动前端

```powershell
cd frontend
npm install
npm run dev
```

### 后端测试

```powershell
cd python
$env:SECRET_KEY='test-secret-key'
$env:ENABLE_SCHEDULER='0'
.venv/Scripts/python.exe -m pytest tests -v
```

### 前端检查

```powershell
cd frontend
npx tsc --noEmit
npm run lint
npm run test
```

更多命令（worker、Lighthouse、Ruff、Alembic、PG 回填等）见 [.agents/operations.md](.agents/operations.md)。

---

## 常见陷阱

- 导入任何依赖 `config.py` 的模块前必须有 `SECRET_KEY`，测试中通常用环境变量设置。
- README 旧说法里的 `python/init_data.py` 已过时，主流程使用 `data_collector/init_mock_data.py`。
- 前端端口不是默认 3000，而是 `127.0.0.1:3200`。
- 后端端口不是 8000，而是 `127.0.0.1:8401`，除非 `HOST` / `PORT` 覆盖。
- `docker-compose.yml` 的 PostgreSQL 暴露端口是 15432。
- `node_modules`、`.next`、`venv`、数据库文件和日志可能在工作区中产生大量噪声，提交时不要顺手纳入。
- 当前仓库可能已有用户或其他助手留下的未提交变更，修改前后都要用 `git status --short` 观察，不要回滚无关改动。
- Windows 上 `python/main.py` 已 patch `asyncio.proactor_events._ProactorBasePipeTransport._call_connection_lost` 以抑制无害的 `ConnectionResetError 10054` 噪音，不要移除此 patch。

---

## 核心约定总结

1. **分支**：默认 `master`，开工前 `git branch` 确认。
2. **API 调用**：前端统一走 `frontend/lib/api/client.ts` 的 `api` 实例；后端优先使用 `/api/v1/*`。
3. **数据库**：后端统一使用 `dependencies.get_db()`；生产必须用 PostgreSQL。
4. **鉴权**：写接口必须 `Authorization: Bearer`；密码必须 bcrypt；JWT 异常必须捕获。
5. **错误处理**：新增业务错误优先使用 `python/errors.py` 中的 `ErrorCode` 和 `ServiceError`，避免裸 `HTTPException`。
6. **格式化**：价格显示用 `formatPrice()`，API payload 用 `formatPricePayload()`；K 线 markers 用 lightweight-charts v5 插件方式。
7. **Agent**：确定性计算优先；新增 Agent 继承 `BaseAgent`；Tool 用 `@register_tool` 注册；步骤写入 `agent_task_steps`。
8. **修改后验证**：前端跑 `tsc --noEmit` + `lint`；后端跑相关 pytest + `ruff check .`。

> 详细规则、演进状态与专项说明请查看 [.agents/](.agents/) 下的分册文档。
