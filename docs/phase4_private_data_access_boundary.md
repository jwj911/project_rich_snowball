# Phase 4：私有数据访问边界决策

> 决策日期：2026-07-24
> 状态：已执行
> 关联迭代：[R2 私有数据访问边界收敛](iteration_plan_20260724_follow_up.md)
> 前置证据：[PostgreSQL owner-scope 回归](phase4_sql_ast_readonly.md)

## 目标

为 Agent 通用 SQL 查询建立可审计的私有数据边界：任何允许查询的用户数据都必须
有明确 owner 策略和测试；包含其他用户自建内容的数据不得通过通用 SQL 暴露。

## 决策

### 1. 通用 SQL 继续限于白名单

`query_database` 仅用于：

- 公共期货行情、合约、基本面和交易日历数据；
- 当前用户的研究与工作区数据，且只能经过 AST owner 谓词改写访问。

`users`、refresh token、用户 LLM 配置和任何未列入白名单的表始终不可查询。

### 2. 私有表集中登记 owner policy

`_PRIVATE_TABLE_USER_COLUMNS` 是通用 SQL 的唯一 owner policy 清单：

- 直接以 `user_id` 隔离：观点、模拟持仓、策略、回测、标注、自选、评论、预警、
  Alert 状态、Agent 任务、前端日志和用户偏好；
- `agent_task_steps` 不含 `user_id`，通过关联 `agent_tasks` 的 `EXISTS` 子查询隔离。

新增进入通用 SQL 白名单的用户数据表，必须同时：

1. 在该 policy 中登记 owner 策略；
2. 增加 SQLite 结构回归；
3. 对复杂 JOIN、CTE 或间接 owner 关系增加 PostgreSQL 执行回归。

### 3. 用户自建新闻数据不再开放给通用 SQL

`news_sources` 和 `news_articles` 已移出 `query_database` 白名单。新闻源可能包含
用户自建订阅地址，其可见性应由 `/api/news` 的身份校验和可见源规则处理，不能由
LLM 生成的通用 SQL 绕过。

### 4. 不在本轮创建宽泛的新 repository

现有用户工作区、观点、策略、持仓、任务、设置和新闻已分别拥有 router、service
或 repository 边界。当前没有证据表明 DataAgent 需要某一稳定、受产品承诺的
“任意私有 SQL”能力，因此本轮不为假设性调用方引入新的通用 repository/API。

后续新增 Agent 能力时：

- 有稳定产品契约的读取需求，应优先接入对应领域 service/repository；
- 仅研究型、低频的自有数据检索可保留在通用 SQL 中，但必须遵守本文件的 policy
  和回归要求；
- 不得以“已有 owner 注入”为理由绕过领域鉴权和字段脱敏。

## 验证

本轮回归覆盖：

- SQLite：所有直接 owner 表均会注入当前用户的 `user_id` 条件；
- SQLite：`agent_task_steps` 使用父任务 `EXISTS` 条件；
- SQLite：`news_sources`、`news_articles` 被通用 SQL 白名单拒绝；
- PostgreSQL：LEFT JOIN、CTE/UNION、任务步骤关联、前端日志和用户偏好均只返回
  当前用户数据；
- PostgreSQL：隔离测试库已从空库迁移到 `f7a8b9c0d1e2`。

## 后续

R2 完成后，下一阶段进入 R3「数据基础与可复现性」：先以独立设计和最小 schema
确定 `raw_contract` 日级宽表的血缘、幂等键和重建方式，再实施数据管道。
