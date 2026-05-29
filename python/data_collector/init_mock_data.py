from datetime import datetime, timezone
from sqlalchemy.orm import Session
from models import SessionLocal, UserDB, CommentDB, KlineDataDB, VarietyDB, RealtimeQuoteDB, FutContractDB, TradingCalendarDB
from utils import hash_password
from data_collector.mock_collector import MockCollector
from data_collector.upsert import insert_kline_bulk, upsert_realtime, upsert_fut_contract_bulk

# 模拟品种基础数据（用于 RealtimeQuoteDB / KlineDataDB / FutContractDB 初始化）
_MOCK_PRODUCTS = [
    {"name": "黄金", "symbol": "AU", "current_price": 453.2, "change_percent": 1.25, "open_price": 447.5, "high": 455.8, "low": 446.2, "volume": 152340, "category": "贵金属", "margin": 8, "commission": 15},
    {"name": "白银", "symbol": "AG", "current_price": 5420, "change_percent": -0.85, "open_price": 5465, "high": 5500, "low": 5380, "volume": 89420, "category": "贵金属", "margin": 9, "commission": 12},
    {"name": "铜", "symbol": "CU", "current_price": 68450, "change_percent": 2.15, "open_price": 67000, "high": 68800, "low": 66800, "volume": 125680, "category": "有色金属", "margin": 10, "commission": 18},
    {"name": "螺纹钢", "symbol": "RB", "current_price": 3680, "change_percent": -1.32, "open_price": 3730, "high": 3750, "low": 3650, "volume": 2156800, "category": "黑色系", "margin": 12, "commission": 8},
    {"name": "铁矿石", "symbol": "I", "current_price": 825, "change_percent": 0.78, "open_price": 818, "high": 835, "low": 812, "volume": 985420, "category": "黑色系", "margin": 11, "commission": 10},
    {"name": "原油", "symbol": "SC", "current_price": 528.5, "change_percent": -2.15, "open_price": 540.0, "high": 542.0, "low": 525.0, "volume": 425680, "category": "能源化工", "margin": 15, "commission": 20},
    {"name": "甲醇", "symbol": "MA", "current_price": 2580, "change_percent": 1.05, "open_price": 2555, "high": 2600, "low": 2540, "volume": 1856420, "category": "能源化工", "margin": 8, "commission": 6},
    {"name": "豆粕", "symbol": "M", "current_price": 3250, "change_percent": 0.45, "open_price": 3235, "high": 3280, "low": 3220, "volume": 652340, "category": "农产品", "margin": 10, "commission": 7},
    {"name": "玉米", "symbol": "C", "current_price": 2455, "change_percent": -0.62, "open_price": 2470, "high": 2485, "low": 2440, "volume": 425680, "category": "农产品", "margin": 8, "commission": 5},
    {"name": "棉花", "symbol": "CF", "current_price": 16850, "change_percent": 1.88, "open_price": 16540, "high": 16920, "low": 16480, "volume": 285640, "category": "农产品", "margin": 12, "commission": 14},
]


# 模拟评论数据（按 symbol 索引，映射到 variety_id）
_MOCK_COMMENTS = [
    {"symbol": "AU", "user_id": 1, "content": "黄金近期走势强劲，受避险情绪影响明显，建议关注450美元阻力位。"},
    {"symbol": "AU", "user_id": 2, "content": "美联储加息预期降温，金价有望继续上攻。"},
    {"symbol": "CU", "user_id": 3, "content": "铜价突破68000，需求端预期改善，短期内看好。"},
    {"symbol": "SC", "user_id": 1, "content": "原油回落至520附近，OPEC+减产消息需持续关注。"},
    {"symbol": "RB", "user_id": 2, "content": "螺纹钢库存下降，基本面转好信号出现。"},
]


def init_mock_data():
    db = SessionLocal()
    try:
        variety_map = {v.symbol: v for v in db.query(VarietyDB).all()}

        # 1. 初始化用户
        if db.query(UserDB).count() == 0:
            users = [
                {"username": "trader001", "email": "trader001@example.com", "password_hash": hash_password("password123")},
                {"username": "investor_wang", "email": "wang@example.com", "password_hash": hash_password("password123")},
                {"username": "futures_master", "email": "master@example.com", "password_hash": hash_password("password123")},
            ]
            for u in users:
                db.add(UserDB(**u))
            db.commit()

        # 3. 初始化评论（仅使用 variety_id）
        if db.query(CommentDB).count() == 0:
            for c in _MOCK_COMMENTS:
                variety = variety_map.get(c["symbol"])
                if variety:
                    db.add(CommentDB(
                        variety_id=variety.id,
                        user_id=c["user_id"],
                        content=c["content"],
                    ))

        # 4. 初始化实时行情（直接从 mock 数据写入 RealtimeQuoteDB，不再依赖 ProductDB 作为数据源）
        if db.query(RealtimeQuoteDB).count() == 0:
            for p in _MOCK_PRODUCTS:
                variety = variety_map.get(p["symbol"])
                if variety:
                    upsert_realtime(db, {
                        "symbol": p["symbol"],
                        "current_price": p["current_price"],
                        "change_percent": p["change_percent"],
                        "open_price": p["open_price"],
                        "high": p["high"],
                        "low": p["low"],
                        "volume": p["volume"],
                        "limit_up": round(float(p["current_price"]) * 1.05, 2) if p["current_price"] else None,
                        "limit_down": round(float(p["current_price"]) * 0.95, 2) if p["current_price"] else None,
                        "updated_at": datetime.now(timezone.utc),
                    })

        # 确保每个品种都有对应的合约记录，供 K 线匹配 contract_id
        # 使用 upsert 避免 PostgreSQL 等环境下的唯一约束冲突
        varieties = db.query(VarietyDB).all()
        contract_rows = []
        for variety in varieties:
            contract_rows.append({
                "ts_code": f"{variety.contract_code}.{variety.exchange}",
                "symbol": variety.contract_code,
                "name": variety.name,
                "fut_code": variety.symbol,
                "exchange": variety.exchange,
                "is_active": True,
            })
        if contract_rows:
            upsert_fut_contract_bulk(db, contract_rows)
        db.commit()

        collector = MockCollector()
        for variety in varieties:
            # 同时生成 1h/1d（基础 K 线）和 D（连续/主力 K 线）数据
            for period, limit in (("1h", 120), ("1d", 90), ("D", 90)):
                has_kline = db.query(KlineDataDB).filter(
                    KlineDataDB.variety_id == variety.id,
                    KlineDataDB.period == period,
                ).first()
                if not has_kline:
                    rows = collector.fetch_kline(variety.contract_code, period, limit=limit)
                    insert_kline_bulk(db, rows, period)

        # 5. 兜底：确保每个 Variety 都有 RealtimeQuote（避免 init_varieties 与 mock 数据脱节）
        mock_price_map = {p["symbol"]: p["current_price"] for p in _MOCK_PRODUCTS}
        for variety in variety_map.values():
            existing = db.query(RealtimeQuoteDB).filter(RealtimeQuoteDB.variety_id == variety.id).first()
            if not existing:
                default_price = mock_price_map.get(variety.symbol, 0.0)
                db.add(RealtimeQuoteDB(
                    variety_id=variety.id,
                    current_price=default_price,
                    change_percent=0.0,
                    open_price=default_price,
                    high=default_price,
                    low=default_price,
                    volume=0,
                    limit_up=None,
                    limit_down=None,
                    updated_at=datetime.now(timezone.utc),
                ))

        # 初始化手续费/保证金数据，供 /api/varieties/{symbol}/fees 使用
        from models import FutTradeFeeDB
        if db.query(FutTradeFeeDB).count() == 0:
            for variety in varieties:
                db.add(FutTradeFeeDB(
                    exchange=variety.exchange,
                    contract_name=variety.name,
                    contract_code=variety.contract_code,
                    margin_per_hand=variety.margin_rate,
                    fee_open_fixed=str(variety.commission),
                    fee_updated_at=datetime.now(timezone.utc),
                ))

        # 初始化交易日历（2025-2026）
        if db.query(TradingCalendarDB).count() == 0:
            _init_trading_calendar(db)

        db.commit()
        print("模拟数据初始化完成")
    finally:
        db.close()


def _init_trading_calendar(db: Session) -> None:
    """导入 2025-2026 中国期货交易日历。"""
    from datetime import date, timedelta

    # 2025 年法定节假日（国务院公布 + 期货交易所实际休市）
    holidays_2025 = {
        "2025-01-01",  # 元旦
        "2025-01-28", "2025-01-29", "2025-01-30", "2025-01-31",
        "2025-02-01", "2025-02-02", "2025-02-03", "2025-02-04",  # 春节
        "2025-04-04", "2025-04-05", "2025-04-06",  # 清明
        "2025-05-01", "2025-05-02", "2025-05-03", "2025-05-04", "2025-05-05",  # 劳动节
        "2025-05-31", "2025-06-01", "2025-06-02",  # 端午
        "2025-10-01", "2025-10-02", "2025-10-03", "2025-10-04",
        "2025-10-05", "2025-10-06", "2025-10-07", "2025-10-08",  # 国庆+中秋
    }
    holidays_2026 = {
        "2026-01-01",  # 元旦
        "2026-02-17", "2026-02-18", "2026-02-19", "2026-02-20",
        "2026-02-21", "2026-02-22", "2026-02-23", "2026-02-24",  # 春节（预估）
        "2026-04-04", "2026-04-05", "2026-04-06",  # 清明
        "2026-05-01", "2026-05-02", "2026-05-03", "2026-05-04", "2026-05-05",  # 劳动节
        "2026-06-19", "2026-06-20", "2026-06-21",  # 端午（预估）
        "2026-09-25", "2026-09-26", "2026-09-27", "2026-09-28",
        "2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04",
        "2026-10-05", "2026-10-06", "2026-10-07", "2026-10-08",  # 国庆+中秋（预估）
    }
    holidays = holidays_2025 | holidays_2026

    start = date(2025, 1, 1)
    end = date(2026, 12, 31)
    current = start
    while current <= end:
        is_holiday = current.strftime("%Y-%m-%d") in holidays or current.weekday() >= 5
        remark = None
        if current.strftime("%Y-%m-%d") in holidays:
            remark = "法定节假日"
        db.add(TradingCalendarDB(
            trade_date=datetime(current.year, current.month, current.day, tzinfo=timezone.utc),
            is_trading_day=not is_holiday,
            day_session_start="09:00",
            day_session_end="15:00",
            night_session_start="21:00",
            night_session_end="02:30",
            exchange="ALL",
            remark=remark,
        ))
        current += timedelta(days=1)


if __name__ == "__main__":
    init_mock_data()
