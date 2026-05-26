# PostgreSQL 备份与恢复 Runbook

> 制定日期：2026-05-26
> 适用环境：生产环境 PostgreSQL 16（docker-compose 或独立部署）

---

## 一、备份策略

### 1.1 逻辑备份（pg_dump）

**频率**：每日凌晨 03:00（交易结束后）
**保留期**：30 天滚动删除
**存储**：本地 + 对象存储（S3/OSS）双副本

```bash
# 每日全量逻辑备份
pg_dump -h localhost -p 15432 -U futures -d futures_community \
  -Fc -f /backup/futures_community_$(date +%Y%m%d_%H%M%S).dump

# 压缩后上传对象存储
aws s3 cp /backup/*.dump s3://your-backup-bucket/futures/ \
  --storage-class STANDARD_IA
```

### 1.2 物理备份（pg_basebackup）

**频率**：每周日全量，其余时间增量（WAL 归档）
**保留期**：14 天
**前提**：`postgresql.conf` 中启用 `wal_level = replica`, `archive_mode = on`

```bash
# 全量物理备份
pg_basebackup -h localhost -p 15432 -U futures \
  -D /backup/base/$(date +%Y%m%d) -Ft -z -P
```

### 1.3 关键表单独导出（快速恢复用）

```bash
# 交易日历、品种元数据等低频变更但高依赖的表
pg_dump -h localhost -p 15432 -U futures -d futures_community \
  --table=varieties --table=trading_calendar --data-only \
  -f /backup/metadata_$(date +%Y%m%d).sql
```

---

## 二、恢复演练

### 2.1 演练频率

**每季度至少一次**，选择非交易日晚间或周末。

### 2.2 逻辑备份恢复步骤

```bash
# 1. 停止应用写入（或切换维护模式）
# 2. 创建新数据库用于验证
psql -h localhost -p 15432 -U futures -c "CREATE DATABASE futures_recovery;"

# 3. 恢复备份
pg_restore -h localhost -p 15432 -U futures -d futures_recovery \
  /backup/futures_community_20260526_030000.dump

# 4. 验证核心表行数
psql -h localhost -p 15432 -U futures -d futures_recovery -c \
  "SELECT COUNT(*) FROM varieties; SELECT COUNT(*) FROM kline_data;"

# 5. 运行数据质量检查
python scripts/data_quality_report.py --db-url postgresql://.../futures_recovery

# 6. 确认无误后如需切换，重命名数据库
psql -h localhost -p 15432 -U futures -c \
  "ALTER DATABASE futures_community RENAME TO futures_community_old;"
psql -h localhost -p 15432 -U futures -c \
  "ALTER DATABASE futures_recovery RENAME TO futures_community;"
```

### 2.3 点-in-time 恢复（PITR）

基于 WAL 归档恢复到指定时间点：

```bash
# 1. 解压基础备份
tar -xzf /backup/base/20260526/base.tar.gz -C /var/lib/postgresql/recovery

# 2. 配置 recovery.conf / postgresql.auto.conf
cat >> /var/lib/postgresql/recovery/postgresql.auto.conf <<EOF
restore_command = 'cp /archive/wal/%f %p'
recovery_target_time = '2026-05-26 14:30:00'
recovery_target_action = 'promote'
EOF

# 3. 启动 PostgreSQL 进入恢复模式
docker-compose restart postgres
# 或
pg_ctl start -D /var/lib/postgresql/recovery

# 4. 验证数据后提升为主库
```

---

## 三、自动化脚本建议

### backup.sh

```bash
#!/bin/bash
set -euo pipefail

DB_NAME="futures_community"
BACKUP_DIR="/backup"
RETENTION_DAYS=30
DATE=$(date +%Y%m%d_%H%M%S)

echo "[$(date)] Starting backup..."
pg_dump -h localhost -p 15432 -U futures -d "$DB_NAME" \
  -Fc -f "$BACKUP_DIR/${DB_NAME}_${DATE}.dump"

echo "[$(date)] Cleaning up backups older than $RETENTION_DAYS days..."
find "$BACKUP_DIR" -name "${DB_NAME}_*.dump" -mtime +$RETENTION_DAYS -delete

echo "[$(date)] Backup completed."
```

### 添加到 crontab

```bash
0 3 * * * /opt/futures/backup.sh >> /var/log/futures_backup.log 2>&1
```

---

## 四、RTO / RPO 目标

| 场景 | RTO（恢复时间目标） | RPO（数据丢失目标） |
|------|-------------------|-------------------|
| 单表误删 | < 30 分钟 | 0（可精确恢复单表） |
| 全库损坏 | < 2 小时 | < 24 小时（日备份） |
| 服务器整机故障 | < 4 小时 | < 1 小时（WAL 归档） |

---

## 五、检查清单（Checklist）

- [ ] 备份脚本已配置 cron 并验证执行成功
- [ ] 备份文件可定期下载到异地（对象存储）
- [ ] 本季度恢复演练已完成并记录结果
- [ ] 备份磁盘容量监控已配置（> 80% 告警）
- [ ] pg_dump 版本与 PostgreSQL 服务端版本一致

---

*本 runbook 随备份策略变更更新。*
