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
- 保留现有私有表 `user_id` 过滤和返回行数限制逻辑。

## 验证

定向命令：

```text
cd python
.venv\Scripts\python.exe -m pytest tests/test_database_tools.py -q
.venv\Scripts\ruff.exe check services/agent/database_tools.py tests/test_database_tools.py
.venv\Scripts\python.exe -m pip check
```

结果：

- `31 passed, 0 failed`
- Ruff 检查通过
- `pip check`：No broken requirements found

回归覆盖：

- 普通 SELECT、聚合、JOIN；
- CTE 和嵌套子查询；
- 多语句 payload；
- 注释和字符串中的关键字；
- 非白名单表；
- 非 `public` schema；
- 危险函数；
- 原有查询执行、表结构和 LIMIT 行为。

## 后续边界

本批只替换只读语句识别，不宣称已经完成所有用户私有数据隔离。下一步应将
`user_id` 自动注入从字符串操作升级为 AST 级谓词改写，或逐步收敛为显式
repository/API，避免复杂 JOIN 和子查询中的过滤位置歧义。
