# 项目文件审计与清理追踪

**审计日期:** 2026-07-05 | **审计人:** Claude (Fable 5) | **初始状态:** 669 passed, 7 skipped, 0 failed

---

## 一、审计发现总览

### 统计数据

| 类别 | 数量 | 说明 |
|------|------|------|
| 已确认可删除 | ~25 项 | 垃圾文件、过期日志、临时数据库、残留目录 |
| 需要移动归类 | ~20 项 | 根目录文档散落、因子报告、数据文件 |
| 建议更新 | 3 项 | README、.gitignore、文档体系 |
| 清理后预计释放 | ~85 MB+ | .playwright-mcp 76MB + venv_old 6.3MB + 其他 |

### 问题分类

1. **根目录杂乱**: 28个文件，包括已完成的计划、历史审计报告、因子分析输出、日志文件
2. **临时数据库残留**: 6个调试/备份 SQLite 文件在 python/ 下
3. **大型缓存目录未清理**: .playwright-mcp (76MB)、venv_old (6.3MB)
4. **孤立依赖**: 根目录 node_modules/ (327KB) 与前端无关
5. **其他项目截图**: docs/archive/ 下 14 个 OpenAlice 截图
6. **过期 worktree**: 5月21日的 claude/hopeful-visvesvaraya-fb9772
7. **日志文件未进 .gitignore**: 开发日志散落在 python/ 和 frontend/ 下

---

## 二、操作日志

### Phase 1: 删除明确垃圾文件 (2026-07-05)

| # | 操作 | 目标 | 结果 |
|---|------|------|------|
| 1 | rm | `plan.md` | ✅ 已删除 |
| 2 | rm | `backend-e2e.log` + `backend-e2e.err` | ✅ 已删除 |
| 3 | rm | `dev.db` (根目录) | ✅ 已删除 |
| 4 | rm | `backfill_report.csv` (根目录) — 与 python/ 下完全一致 | ✅ 已删除 |
| 5 | rm -rf | `.trae/` (含 documents/) | ✅ 已删除 |
| 6 | rm | `python/tmp_backtest_debug.db` | ✅ 已删除 |
| 7 | rm | `python/tmp_backtest_debug2.db` | ✅ 已删除 |
| 8 | rm | `python/test_evo_debug.db` | ✅ 已删除 |
| 9 | rm | `python/test_evo_dbg2.db` | ✅ 已删除 |
| 10 | rm | `python/dev.db.bak` | ✅ 已删除 |
| 11 | rm | `python/futures_community.db` (0 B 空文件) | ✅ 已删除 |
| 12 | rm | `python/futures_community.db.backup.20260502_223808` | ✅ 已删除 |
| 13 | rm | `python/futures_community_sync.db` | ✅ 已删除 |
| 14 | rm | `python/backend-dev.log`, `backend-dev.err.log`, `backend.log` | ✅ 已删除 |
| 15 | rm | `frontend/frontend-dev*.log` (5个) + `frontend.log` | ✅ 已删除 |
| 16 | rm -rf | `python/venv_old/` (6.3 MB) | ✅ 已删除 |
| 17 | rm -rf | `node_modules/` (根目录, 327 KB) | ✅ 已删除 |
| 18 | rm -rf | `.playwright-mcp/` (76 MB) | ✅ 已删除 |
| 19 | rm | `docs/archive/openalice_*.png` (14个) | ✅ 已删除 |
| 20 | git worktree remove --force | `.claude/worktrees/hopeful-visvesvaraya-fb9772` | ✅ 已删除 |
| 21 | git branch -D | `claude/hopeful-visvesvaraya-fb9772` | ✅ 已删除 |

**Phase 1 小结:** 删除 21 批次共 ~40 个文件/目录，预计释放 ~90 MB 磁盘空间。

### Phase 2: 移动归类文档 (2026-07-05)

#### 历史审计文档 → docs/archive/

| # | 操作 | 目标 | 结果 |
|---|------|------|------|
| 1 | mv | `BACKEND_ARCHITECTURE_AUDIT_V7_20260601.md` → `docs/archive/` | ✅ 已移动 |
| 2 | mv | `BACKEND_FIX_ACCEPTANCE_HANDOFF_V6_1_20260530.md` → `docs/archive/` | ✅ 已移动 |
| 3 | mv | `BACKEND_ROADMAP_V3_20260604.md` → `docs/archive/` | ✅ 已移动 |
| 4 | mv | `BACKEND_FEATURE_ROADMAP.md` → `docs/archive/` | ✅ 已移动 |
| 5 | mv | `FRONTEND_ITERATION_PLAN_v6_20260528.md` → `docs/archive/` | ✅ 已移动 |
| 6 | mv | `FRONTEND_ROADMAP_v8_20260529.md` → `docs/archive/` | ✅ 已移动 |

#### 技术参考文档 → docs/guides/

| # | 操作 | 目标 | 结果 |
|---|------|------|------|
| 7 | mv | `BACKEND_API_REFERENCE_FOR_FRONTEND.md` → `docs/guides/` | ✅ 已移动 |
| 8 | mv | `BACKEND_API_VERSIONING_GUIDE.md` → `docs/guides/` | ✅ 已移动 |
| 9 | mv | `DATA_PIPELINE_AND_POSTGRES_GUIDE.md` → `docs/guides/` | ✅ 已移动 |
| 10 | mv | `TUSHARE_POSTGRES_VERIFICATION.md` → `docs/guides/` | ✅ 已移动 |

#### 因子报告 → quantative_tools/reports/

| # | 操作 | 目标 | 结果 |
|---|------|------|------|
| 11 | mv | `factor_report_价格动量.md` → `quantative_tools/reports/` | ✅ 已移动 |
| 12 | mv | `factor_report_波动振幅.md` → `quantative_tools/reports/` | ✅ 已移动 |
| 13 | mv | `factor_report_资金动量.md` → `quantative_tools/reports/` | ✅ 已移动 |
| 14 | mv | `factor_report_量能动量.md` → `quantative_tools/reports/` | ✅ 已移动 |
| 15 | mv | `factor_screening_report.md` → `quantative_tools/reports/` | ✅ 已移动 |
| 16 | mv | `factor_screening_top100.csv` → `quantative_tools/reports/` | ✅ 已移动 |
| 17 | mv | `factor_screening_top100.json` → `quantative_tools/reports/` | ✅ 已移动 |

#### 数据文件归位

| # | 操作 | 目标 | 结果 |
|---|------|------|------|
| 18 | mv | `python/zz1000_options.csv` → `python/data/` | ✅ 已移动 |

#### 新增目录

| # | 操作 | 说明 |
|---|------|------|
| — | mkdir | `docs/guides/` — 技术参考文档 |
| — | mkdir | `quantative_tools/reports/` — 因子分析报告 |

**Phase 2 小结:** 移动 18 个项目到合适位置，新建 2 个目录。根目录从 Phase 1 后的 21 个文件减少到 7 个（AGENTS.md + README.md + docker-compose.yml + 4 个配置/环境文件）。

### 文档更新 (2026-07-05)

| # | 文件 | 操作 |
|---|------|------|
| 1 | `README.md` | 更新项目结构图、新增 docs/guides/ 文档链接、移除过时的 FULLSTACK_REVIEW 和 Java 目录引用 |
| 2 | `AGENTS.md` | 更新日期、新增审计追踪链接、新增 docs/guides/ 文档导航表格、新增 quantative_tools/reports/ 引用 |
| 3 | `.gitignore` | 新增 .playwright-mcp/、.trae/、.claude/worktrees/、根目录临时数据导出规则 |

---

## 三、待处理清单

### 待删除（已确认）— ✅ 全部完成

- [x] `plan.md` — Phase 3 计划，已实施完毕
- [x] `.trae/` 整个目录 — Trae IDE 历史计划
- [x] `backend-e2e.log` + `backend-e2e.err` — 5月底过期 E2E 日志
- [x] `dev.db` (根目录) — 孤立 SQLite 文件
- [x] `python/tmp_backtest_debug.db` — 临时调试数据库
- [x] `python/tmp_backtest_debug2.db` — 临时调试数据库
- [x] `python/test_evo_debug.db` — 临时调试数据库
- [x] `python/test_evo_dbg2.db` — 临时调试数据库
- [x] `python/dev.db.bak` — 开发数据库备份
- [x] `python/futures_community.db` — 空文件 (0 B)
- [x] `python/futures_community.db.backup.20260502_223808` — 2月前备份
- [x] `python/futures_community_sync.db` — 测试残留
- [x] `python/venv_old/` — 旧虚拟环境 (6.3 MB)
- [x] `node_modules/` (根目录) — 孤立依赖
- [x] `.playwright-mcp/` — Playwright MCP 缓存 (76 MB)
- [x] `.claude/worktrees/hopeful-visvesvaraya-fb9772` + 对应 git 分支
- [x] `docs/archive/openalice_*.png` (14个) — 其他项目截图
- [x] `python/backend-dev.log` + `python/backend-dev.err.log` + `python/backend.log`
- [x] `frontend/frontend-dev*.log` + `frontend/frontend.log`
- [x] `backfill_report.csv` (根目录) — 与 python/backfill_report.csv 完全一致，已删

### 待移动归类 — ✅ 全部完成

- [x] `BACKEND_ARCHITECTURE_AUDIT_V7_20260601.md` → `docs/archive/`
- [x] `BACKEND_FIX_ACCEPTANCE_HANDOFF_V6_1_20260530.md` → `docs/archive/`
- [x] `BACKEND_ROADMAP_V3_20260604.md` → `docs/archive/`
- [x] `BACKEND_FEATURE_ROADMAP.md` → `docs/archive/`
- [x] `FRONTEND_ITERATION_PLAN_v6_20260528.md` → `docs/archive/`
- [x] `FRONTEND_ROADMAP_v8_20260529.md` → `docs/archive/`
- [x] `BACKEND_API_REFERENCE_FOR_FRONTEND.md` → `docs/guides/`
- [x] `BACKEND_API_VERSIONING_GUIDE.md` → `docs/guides/`
- [x] `DATA_PIPELINE_AND_POSTGRES_GUIDE.md` → `docs/guides/`
- [x] `TUSHARE_POSTGRES_VERIFICATION.md` → `docs/guides/`
- [x] `factor_report_价格动量.md` → `quantative_tools/reports/`
- [x] `factor_report_波动振幅.md` → `quantative_tools/reports/`
- [x] `factor_report_资金动量.md` → `quantative_tools/reports/`
- [x] `factor_report_量能动量.md` → `quantative_tools/reports/`
- [x] `factor_screening_report.md` → `quantative_tools/reports/`
- [x] `factor_screening_top100.csv` → `quantative_tools/reports/`
- [x] `factor_screening_top100.json` → `quantative_tools/reports/`
- [x] `python/zz1000_options.csv` → `python/data/`

### 待更新 — ✅ 全部完成

- [x] `README.md` — 同步最新项目结构
- [x] `.gitignore` — 添加日志文件、.playwright-mcp/ 等规则
- [x] `AGENTS.md` — 更新文档导航引用

---

## 四、目录对比（清理前 → 清理后）

### 根目录清理前 (28个文件)

```
.env, .env.example, .gitignore, .pre-commit-config.yaml,
AGENTS.md, README.md, plan.md, docker-compose.yml,
BACKEND_API_REFERENCE_FOR_FRONTEND.md, BACKEND_API_VERSIONING_GUIDE.md,
BACKEND_ARCHITECTURE_AUDIT_V7_20260601.md, BACKEND_FEATURE_ROADMAP.md,
BACKEND_FIX_ACCEPTANCE_HANDOFF_V6_1_20260530.md, BACKEND_ROADMAP_V3_20260604.md,
DATA_PIPELINE_AND_POSTGRES_GUIDE.md, TUSHARE_POSTGRES_VERIFICATION.md,
FRONTEND_ITERATION_PLAN_v6_20260528.md, FRONTEND_ROADMAP_v8_20260529.md,
factor_report_价格动量.md, factor_report_波动振幅.md, factor_report_资金动量.md, factor_report_量能动量.md,
factor_screening_report.md, factor_screening_top100.csv, factor_screening_top100.json,
backfill_report.csv, backend-e2e.log, backend-e2e.err, dev.db
```

### 根目录清理后（实际结果：7 个文件）

```
.env, .env.example, .gitignore, .pre-commit-config.yaml,
AGENTS.md, README.md, docker-compose.yml
```

### 新的目录结构

```
project_rich_snowball/
├── .agents/                      # AI 助手分册文档 (8 个)
├── .github/workflows/            # CI/CD
├── docs/
│   ├── guides/                   # 技术参考 (4 个：API参考、版本指南、数据管道、Tushare验证)
│   ├── archive/                  # 历史审计/路线图 (6 个 + 更多旧归档)
│   ├── audit_cleanup_20260705.md # 本追踪文档
│   └── ... (设计文档)
├── frontend/                     # Next.js 前端
├── python/                       # FastAPI 后端
└── quantative_tools/
    ├── factors/                  # 因子定义
    ├── signals/                  # 择时信号
    ├── strategy/                 # 选股策略
    └── reports/                  # 因子分析报告 (7 个)
```

---

## 五、总结

| 阶段 | 操作 | 结果 |
|------|------|------|
| Phase 1 | 删除垃圾文件 | ~40 文件/目录删除，释放 ~90 MB |
| Phase 2 | 移动归类 | 18 项移动至正确位置，新建 2 个子目录 |
| 文档更新 | README + AGENTS + .gitignore | 3 个文件同步更新 |
| **最终根目录** | **28 个文件 → 7 个文件** | **减少 75%** |
