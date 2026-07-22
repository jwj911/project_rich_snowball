# Phase 4：Agent SQL AST 只读校验

> 实施日期：2026-07-21
> 关联风险：F-12（Agent SQL 工具依赖正则解析）
> 当前迭代事实源：[`iteration_plan_20260718_project_audit.md`](iteration_plan_20260718_project_audit.md)

## 目标

将 `python/services/agent/database_tools.py` 的 SQL 安全边界从关键字和
`FROM/JOIN` 正则匹配升级为解析树校验，降低多语句、嵌套查询、CTE、注释和
函数调用绕过只读限制的风险。

## 实施内容

- 新增 `sqlglot>=26.0.0,<27.0.0`，锁定 `sqlglot==26.20.0`；
- 解析结果必须是单条 `SELECT`、`UNION`、`INTERSECT` 或 `EXCEPT`；
- AST 中拒绝 `INSERT`、`UPDATE`、`DELETE`、DDL、事务、锁定和 `SELECT INTO`；
- 拒绝 `pg_sleep`、`pg_read_file`、`pg_ls_dir`、`dblink_*`、SQLite 扩展读写等危险函数；
- 遍历嵌套查询和 CTE 的真实表引用，保留允许表白名单；
- 仅允许空 schema 或 `public` schema，拒绝其他 schema/catalog；
- 按表别名和 SELECT 作用域注入 owner 谓词；JOIN 表写入 `ON`，避免破坏 LEFT JOIN；
- `agent_task_steps` 通过 `EXISTS` 关联 `agent_tasks.user_id`；
- 只有明确等于当前上下文用户的 AST 条件才跳过重复注入，`user_id = 其他值` 会追加当前用户条件。

## 验证

定向命令：

```text
cd python
.venv\Scripts\python.exe -m pytest tests/test_database_tools.py -q
.venv\Scripts\ruff.exe check services/agent/database_tools.py tests/test_database_tools.py
.venv\Scripts\python.exe -m pip check
```

结果：

- `40 passed, 0 failed`
- Ruff 检查通过
- `pip check`：No broken requirements found
- 全量后端：`978 passed, 8 skipped, 0 failed`

回归覆盖：

- 普通 SELECT、聚合、JOIN；
- CTE 和嵌套子查询；
- 多个私有表和表别名；
- LEFT JOIN 的 ON 谓词保持；
- `agent_task_steps` 的父任务 owner 关联；
- 不同 `user_id` 条件不能越权；
- 多语句 payload；
- 注释和字符串中的关键字；
- 非白名单表；
- 非 `public` schema；
- 危险函数；
- 原有查询执行、表结构和 LIMIT 行为。

## 后续边界

本批已完成私有数据 owner 谓词的 AST 改写。后续仍可将用户私有数据访问逐步
收敛为显式 repository/API，并为复杂关联查询增加 PostgreSQL 专项回归。
