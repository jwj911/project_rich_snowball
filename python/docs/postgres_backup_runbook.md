# PostgreSQL 备份与恢复 Runbook

> 目标：建立可复现的备份策略和恢复演练流程，防止数据丢失。
> 适用环境：生产环境 PostgreSQL（docker-compose 或独立部署）。
> 更新日期：2026-05-27

---

## 一、备份策略

### 1.1 物理备份（推荐：pg_basebackup）

适用于：全量备份，Point-in-Time Recovery (PITR)

```bash
# 在 PostgreSQL 容器内或宿主机执行
pg_basebackup -h localhost -p 15432 -U futures -D /backup/pg_base/$(date +%Y%m%d_%H%M%S) -Ft -z -P -X stream
```

**参数说明**：
- `-Ft`：tar 格式
- `-z`：gzip 压缩
- `-P`：显示进度
- `-X stream`：同时备份 WAL

**保留策略**：保留最近 7 天全量 + WAL 归档。

### 1.2 逻辑备份（pg_dump）

适用于：跨版本迁移、单表恢复、开发环境数据脱敏。

```bash
# 全库逻辑备份
pg_dump -h localhost -p 15432 -U futures -d futures_community -Fc -f /backup/pg_dump/futures_community_$(date +%Y%m%d).dump

# 仅核心表（快速恢复测试用）
pg_dump -h localhost -p 15432 -U futures -d futures_community \
  --table=users --table=products --table=varieties --table=realtime_quotes \
  --table=comments --table=price_levels --table=watchlists \
  -Fc -f /backup/pg_dump/futures_core_$(date +%Y%m%d).dump
```

**参数说明**：
- `-Fc`：自定义格式（支持选择性恢复）

**保留策略**：保留最近 30 天逻辑备份。

### 1.3 定时任务（crontab 示例）

```bash
# 每天 02:00 执行逻辑备份
0 2 * * * /usr/local/bin/pg_dump -h localhost -p 15432 -U futures -d futures_community -Fc -f /backup/pg_dump/futures_community_$(date +\%Y\%m\%d).dump && find /backup/pg_dump -name "*.dump" -mtime +30 -delete

# 每周日 03:00 执行物理备份
0 3 * * 0 /usr/local/bin/pg_basebackup -h localhost -p 15432 -U futures -D /backup/pg_base/$(date +\%Y\%m\%d_\%H\%M\%S) -Ft -z -P -X stream && find /backup/pg_base -maxdepth 1 -type d -mtime +7 -exec rm -rf {} +
```

---

## 二、恢复演练

### 2.1 逻辑备份恢复（单表/全库）

**场景**：误删数据、开发环境同步、跨版本迁移。

```bash
# 1. 创建新数据库（恢复目标）
createdb -h localhost -p 15432 -U futures futures_community_restore

# 2. 恢复全库
pg_restore -h localhost -p 15432 -U futures -d futures_community_restore /backup/pg_dump/futures_community_20260527.dump

# 3. 仅恢复特定表（自定义格式支持）
pg_restore -h localhost -p 15432 -U futures -d futures_community_restore \
  --table=users --table=comments \
  /backup/pg_dump/futures_community_20260527.dump
```

**验证清单**：
- [ ] 表数量与生产一致：`\dt` 或 `SELECT count(*) FROM information_schema.tables WHERE table_schema='public';`
- [ ] 核心表行数一致：`SELECT count(*) FROM users;` 等
- [ ] 索引和约束存在：`\d tablename`
- [ ] 应用连接测试：`/health/ready` 返回 200

### 2.2 物理备份恢复（PITR）

**场景**：数据库崩溃、硬件故障、需要恢复到特定时间点。

```bash
# 1. 停止 PostgreSQL 服务（如果是容器则停止容器）
docker-compose stop postgres

# 2. 备份当前数据目录（防止进一步损坏）
mv /var/lib/postgresql/data /var/lib/postgresql/data_corrupted_$(date +%Y%m%d_%H%M%S)

# 3. 解压物理备份
mkdir -p /var/lib/postgresql/data
tar -xzf /backup/pg_base/20260527_030000/base.tar.gz -C /var/lib/postgresql/data

# 4. 恢复 WAL（如果使用了 PITR）
# 编辑 recovery.signal 和 postgresql.conf 中的 restore_command
# 详见 PostgreSQL 官方 PITR 文档

# 5. 启动 PostgreSQL
docker-compose start postgres
```

**验证清单**：
- [ ] PostgreSQL 日志无 ERROR
- [ ] 连接池可正常获取连接
- [ ] 全量 pytest 通过
- [ ] `/health/ready` 返回 ready=True

---

## 三、Docker Compose 环境备份恢复

项目使用 `docker-compose.yml` 部署 PostgreSQL，以下为 compose 环境的快速操作：

```bash
# 备份数据卷
docker run --rm -v project_rich_snowball_postgres_data:/data -v $(pwd)/backup:/backup alpine tar czf /backup/postgres_data_$(date +%Y%m%d_%H%M%S).tar.gz -C /data .

# 恢复数据卷（先停止服务）
docker-compose stop postgres
docker run --rm -v project_rich_snowball_postgres_data:/data -v $(pwd)/backup:/backup alpine sh -c "rm -rf /data/* && tar xzf /backup/postgres_data_20260527_030000.tar.gz -C /data"
docker-compose start postgres
```

---

## 四、RTO / RPO 目标

| 场景 | RTO（恢复时间） | RPO（数据丢失） | 备份方式 |
|------|----------------|----------------|----------|
| 单表误删 | < 30 分钟 | 0（可精确到行） | 逻辑备份 + WAL |
| 数据库崩溃 | < 2 小时 | < 15 分钟 | 物理备份 + WAL |
| 硬件故障 | < 4 小时 | < 1 小时 | 物理备份 + 异地副本 |
| 迁移/升级 | < 4 小时 | 0（可控窗口） | 逻辑备份 |

---

## 五、恢复演练计划

**频率**：每季度一次（或每次重大发布前）。

**演练步骤**：
1. 在 staging 环境执行完整恢复流程。
2. 验证数据完整性（行数、校验和抽样）。
3. 运行全量 pytest 和 Playwright E2E。
4. 记录耗时和遇到的问题。
5. 更新本 runbook。

**上次演练记录**：
| 日期 | 演练类型 | 结果 | 耗时 | 问题 |
|------|----------|------|------|------|
| — | — | — | — | 尚未执行 |

---

## 六、注意事项

1. **备份存储**：备份文件应存储在与数据库不同的磁盘/机器上，最好是异地。
2. **加密**：生产环境备份文件建议加密存储（`gpg` 或云存储服务端加密）。
3. **权限**：备份目录权限设为 700，仅 postgres/备份用户可访问。
4. **测试恢复**：备份的唯一价值在于可恢复。没有验证过的备份等于没有备份。

---

*本文档随备份策略调整和演练结果更新。*
