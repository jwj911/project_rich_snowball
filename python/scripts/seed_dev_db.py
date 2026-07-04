"""开发环境数据库种子脚本。

创建 SQLite 开发库并填充测试品种、行情和 K 线数据，供端到端验收使用。
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal

# 固定使用项目根目录下的 dev.db，避免污染生产数据库
os.environ["DATABASE_URL"] = "sqlite:///./dev.db"
os.environ["SECRET_KEY"] = "dev-secret-key-must-be-at-least-32-characters-long-now"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from sqlalchemy.orm import sessionmaker

import models
from models import (
    Base,
    FutContractDB,
    KlineDataDB,
    RealtimeQuoteDB,
    UserDB,
    VarietyDB,
)
from utils import hash_password


def _ensure_tables():
    Base.metadata.create_all(bind=models.engine)


def _seed_user(session):
    existing = session.query(UserDB).filter(UserDB.username == "dev").first()
    if existing:
        return existing
    user = UserDB(
        username="dev",
        email="dev@example.com",
        password_hash=hash_password("password123"),
    )
    session.add(user)
    session.commit()
    return user


def _seed_varieties(session):
    specs = [
        ("RB", "螺纹钢", "SHFE", "黑色系"),
        ("HC", "热卷", "SHFE", "黑色系"),
        ("I", "铁矿石", "DCE", "黑色系"),
        ("AU", "黄金", "SHFE", "贵金属"),
        ("AG", "白银", "SHFE", "贵金属"),
        ("CU", "铜", "SHFE", "有色金属"),
        ("AL", "铝", "SHFE", "有色金属"),
        ("ZN", "锌", "SHFE", "有色金属"),
        ("NI", "镍", "SHFE", "有色金属"),
        ("SN", "锡", "SHFE", "有色金属"),
        ("SC", "原油", "INE", "能源化工"),
        ("BU", "沥青", "SHFE", "能源化工"),
        ("MA", "甲醇", "ZCE", "能源化工"),
        ("M", "豆粕", "DCE", "农产品"),
        ("C", "玉米", "DCE", "农产品"),
    ]
    varieties = {}
    contracts = {}
    for symbol, name, exchange, category in specs:
        v = session.query(VarietyDB).filter(VarietyDB.symbol == symbol).first()
        if v is None:
            v = VarietyDB(
                symbol=symbol,
                contract_code=f"{symbol}2501",
                name=name,
                exchange=exchange,
                category=category,
                is_active=True,
            )
            session.add(v)
            session.commit()
            session.refresh(v)
        else:
            v.is_active = True
            session.commit()

        # 创建关联合约
        ts_code = f"{symbol}2501.{exchange[:2]}F"
        contract = session.query(FutContractDB).filter(FutContractDB.ts_code == ts_code).first()
        if contract is None:
            contract = FutContractDB(
                ts_code=ts_code,
                symbol=symbol,
                name=name,
                exchange=exchange,
                fut_code=symbol,
                is_active=True,
            )
            session.add(contract)
            session.commit()
            session.refresh(contract)
        varieties[symbol] = v
        contracts[symbol] = contract
    return varieties, contracts


def _seed_quotes(session, varieties):
    base_prices = {
        "RB": 3500.0,
        "HC": 3600.0,
        "I": 800.0,
        "AU": 550.0,
        "AG": 7000.0,
        "CU": 70000.0,
        "AL": 19000.0,
        "ZN": 23000.0,
        "NI": 130000.0,
        "SN": 260000.0,
        "SC": 550.0,
        "BU": 3600.0,
        "MA": 2500.0,
        "M": 3000.0,
        "C": 2400.0,
    }
    for symbol, variety in varieties.items():
        quote = session.query(RealtimeQuoteDB).filter(RealtimeQuoteDB.variety_id == variety.id).first()
        if quote is None:
            quote = RealtimeQuoteDB(variety_id=variety.id)
            session.add(quote)
        base = base_prices.get(symbol, 1000.0)
        quote.current_price = Decimal(str(base + np.random.uniform(-base * 0.02, base * 0.02)))
        quote.change_percent = Decimal(str(np.random.uniform(-3.0, 3.0)))
        quote.open_price = Decimal(str(base + np.random.uniform(-base * 0.01, base * 0.01)))
        quote.high = Decimal(str(base * 1.02))
        quote.low = Decimal(str(base * 0.98))
        quote.volume = int(np.random.uniform(100000, 500000))
        session.commit()


def _seed_klines(session, varieties, contracts):
    np.random.seed(42)
    for symbol, variety in varieties.items():
        existing = session.query(KlineDataDB).filter(KlineDataDB.variety_id == variety.id).first()
        if existing:
            continue

        base_price = 3500.0 if symbol == "RB" else 550.0 if symbol == "AU" else 70000.0 if symbol == "CU" else 1000.0
        if symbol in ("CU", "AL", "ZN", "NI", "SN"):
            base_price = {"CU": 70000.0, "AL": 19000.0, "ZN": 23000.0, "NI": 130000.0, "SN": 260000.0}[symbol]
        if symbol in ("SC", "BU", "MA", "M", "C"):
            base_price = {"SC": 550.0, "BU": 3600.0, "MA": 2500.0, "M": 3000.0, "C": 2400.0}[symbol]

        prices = np.linspace(base_price * 0.95, base_price * 1.05, 120)
        for i in range(120):
            close = prices[i] + np.random.normal(0, base_price * 0.01)
            open_p = close + np.random.normal(0, base_price * 0.005)
            high = max(open_p, close) + np.random.uniform(base_price * 0.005, base_price * 0.015)
            low = min(open_p, close) - np.random.uniform(base_price * 0.005, base_price * 0.015)
            bar_time = datetime.now(UTC) - timedelta(days=120 - i)
            kline = KlineDataDB(
                variety_id=variety.id,
                contract_id=contracts[symbol].id,
                period="1d",
                trading_time=bar_time,
                trading_date=bar_time.date(),
                open_price=round(open_p, 2),
                high_price=round(high, 2),
                low_price=round(low, 2),
                close_price=round(close, 2),
                volume=int(np.random.uniform(10000, 50000)),
            )
            session.add(kline)
        session.commit()


def main():
    _ensure_tables()
    Session = sessionmaker(bind=models.engine)
    session = Session()
    try:
        _seed_user(session)
        varieties, contracts = _seed_varieties(session)
        _seed_quotes(session, varieties)
        _seed_klines(session, varieties, contracts)
        print(f"Seeded dev database: {models.engine.url}")
        print(f"Varieties: {len(varieties)}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
