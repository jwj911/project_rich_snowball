"""迁移 dev.db 的 kline_data(D/1d) 到 fut_daily_data，并清理 kline_data。

Usage:
    cd python && .venv/Scripts/python.exe scripts/migrate_kline_to_fut_daily.py
"""

from datetime import datetime, timezone
from sqlalchemy.orm import Session

from models import SessionLocal, KlineDataDB, FutDailyDataDB, VarietyDB, FutContractDB


def migrate():
    db = SessionLocal()
    try:
        varieties = {v.id: v for v in db.query(VarietyDB).all()}
        contracts = {c.fut_code: c for c in db.query(FutContractDB).all()}

        # 1. 读取 kline_data 中 period='D' 或 '1d' 的数据
        kline_rows = (
            db.query(KlineDataDB)
            .filter(KlineDataDB.period.in_(["D", "1d"]))
            .order_by(KlineDataDB.variety_id, KlineDataDB.trading_time.asc())
            .all()
        )

        if not kline_rows:
            print("kline_data 中没有 D/1d 数据，无需迁移")
            return

        print(f"找到 {len(kline_rows)} 条 kline_data D/1d 记录")

        # 2. 转换为 fut_daily_data
        inserted = 0
        skipped = 0
        for row in kline_rows:
            variety = varieties.get(row.variety_id)
            if not variety:
                skipped += 1
                continue

            contract = contracts.get(variety.symbol)
            ts_code = contract.ts_code if contract else f"{variety.contract_code}.{variety.exchange}"

            trade_date = row.trading_time.replace(tzinfo=timezone.utc) if row.trading_time.tzinfo is None else row.trading_time

            # 检查是否已存在
            existing = (
                db.query(FutDailyDataDB)
                .filter(
                    FutDailyDataDB.variety_id == row.variety_id,
                    FutDailyDataDB.ts_code == ts_code,
                    FutDailyDataDB.trade_date == trade_date,
                )
                .first()
            )
            if existing:
                skipped += 1
                continue

            db.add(FutDailyDataDB(
                variety_id=row.variety_id,
                ts_code=ts_code,
                trade_date=trade_date,
                pre_close=row.close_price,
                pre_settle=row.close_price,
                open_price=row.open_price,
                high_price=row.high_price,
                low_price=row.low_price,
                close_price=row.close_price,
                settle=row.close_price,
                change1=0,
                change2=0,
                volume=row.volume,
                amount=0,
                open_interest=0,
                oi_chg=0,
                period="D",
                created_at=datetime.now(timezone.utc),
            ))
            inserted += 1

            if inserted % 100 == 0:
                db.commit()
                print(f"  已提交 {inserted} 条...")

        db.commit()
        print(f"迁移完成: 插入 {inserted} 条, 跳过 {skipped} 条")

        # 3. 删除 kline_data 中的 D/1d 数据
        deleted = (
            db.query(KlineDataDB)
            .filter(KlineDataDB.period.in_(["D", "1d"]))
            .delete(synchronize_session=False)
        )
        db.commit()
        print(f"已删除 kline_data 中 {deleted} 条 D/1d 记录")

        # 4. 验证
        fut_count = db.query(FutDailyDataDB).count()
        kline_d_count = db.query(KlineDataDB).filter(KlineDataDB.period.in_(["D", "1d"])).count()
        print(f"fut_daily_data 总行数: {fut_count}")
        print(f"kline_data D/1d 剩余: {kline_d_count}")

    finally:
        db.close()


if __name__ == "__main__":
    migrate()
