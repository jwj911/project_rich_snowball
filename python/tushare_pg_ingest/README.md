# Tushare -> PostgreSQL 回填脚本

这个目录是独立于应用启动流程的历史数据灌库工具。脚本会读取项目根目录 `.env` 中的 `TUSHARE_TOKEN`、`DATABASE_URL`、`SECRET_KEY`，默认要求 `DATABASE_URL` 指向 PostgreSQL。

## 前置条件

```powershell
cd D:\Code\project_rich_snowball\python
$env:DATABASE_URL="postgresql://futures:futures123@localhost:15432/futures_community"
$env:ENABLE_SCHEDULER="0"
alembic upgrade head
```

## 常用命令

```powershell
# 日线：写入 fut_daily_data
python tushare_pg_ingest\ingest_daily.py --symbols AU,AG,CU --period D --start-date 20250101 --end-date 20250505

# 周线/月线：同样写入 fut_daily_data，period 分别为 W/M
python tushare_pg_ingest\ingest_daily.py --symbols AU,AG,CU --period W --start-date 20250101 --end-date 20250505
python tushare_pg_ingest\ingest_daily.py --symbols AU,AG,CU --period M --start-date 20250101 --end-date 20250505

# 结算参数
python tushare_pg_ingest\ingest_settle.py --start-date 20250501 --end-date 20250505 --exchanges SHFE,DCE,CZCE

# 仓单日报
python tushare_pg_ingest\ingest_wsr.py --start-date 20250501 --end-date 20250505 --symbols AU,CU

# 持仓排名
python tushare_pg_ingest\ingest_holding.py --start-date 20250501 --end-date 20250505 --symbols AU,CU --exchanges SHFE

# 涨跌停价格
python tushare_pg_ingest\ingest_price_limit.py --start-date 20250501 --end-date 20250505 --symbols AU,CU

# 主力映射：更新 varieties.contract_code
python tushare_pg_ingest\ingest_mapping.py --start-date 20250501 --end-date 20250505

# 周度交易统计
python tushare_pg_ingest\ingest_weekly_detail.py --start-date 20250101 --end-date 20250505

# 保守总入口
python tushare_pg_ingest\ingest_all.py --start-date 20250501 --end-date 20250505 --symbols AU,AG,CU --exchanges SHFE,DCE,CZCE
```

先跑 `--dry-run` 可以验证 Tushare 返回量和字段映射，不写数据库：

```powershell
python tushare_pg_ingest\ingest_daily.py --symbols AU --period D --start-date 20250501 --end-date 20250505 --dry-run
```

历史分钟 `ft_mins` 入口暂时只保留占位脚本，当前阶段不纳入默认回填。
