# 工程基线记录：Phase 3 文档治理

> 类型：`engineering baseline`，不是生产发布。
> 对应清单：[`../release_checklist_20260719.md`](../release_checklist_20260719.md)
> 当前迭代事实源：[`../iteration_plan_20260718_project_audit.md`](../iteration_plan_20260718_project_audit.md)

## 发布元数据

- 基线提交：`b6a32e75`
- 基线窗口：2026-07-19
- 变更范围：建立唯一迭代事实源、发布清单、历史文档归档和发布记录入口。
- 生产发布状态：未发布
- 回滚负责人：不适用（文档基线）

## 已完成验证

- `git diff --check`：通过。
- 文档归档路径、导航和归档文件内部链接：通过。
- 提交前 pre-commit：通过。
- 本次仅修改文档，未触发 Backend/Frontend workflow。
- 代码质量与运行链路证据沿用：
  - [Backend CI #22](https://github.com/jwj911/project_rich_snowball/actions/runs/29661326225)
  - [Frontend CI #28](https://github.com/jwj911/project_rich_snowball/actions/runs/29670891119)

## 生产发布阻塞项

以下项目必须在真实生产发布时重新执行，不得直接复用本基线结果：

- [ ] 生产提交、发布窗口和回滚负责人已确定。
- [ ] PostgreSQL 迁移、逻辑备份和恢复演练已完成。
- [ ] `SECRET_KEY`、CORS、API/worker scheduler owner 已核验。
- [ ] readiness、认证、行情、前端 smoke 和 Lighthouse 已执行。
- [ ] 事故日志、trace id 和回滚结果已写入本次生产记录。
