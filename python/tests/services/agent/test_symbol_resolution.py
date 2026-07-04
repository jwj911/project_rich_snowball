"""品种别名解析测试。"""

from __future__ import annotations

import pytest

from models import VarietyDB
from services.agent.utils import resolve_symbol


@pytest.fixture
def _seed_varieties(db_session):
    """初始化测试品种。"""
    specs = [
        ("RB", "螺纹钢"),
        ("AU", "黄金"),
        ("CU", "铜"),
        ("AL", "铝"),
        ("ZN", "锌"),
    ]
    for symbol, name in specs:
        existing = db_session.query(VarietyDB).filter(VarietyDB.symbol == symbol).first()
        if existing:
            existing.name = name
            existing.is_active = True
        else:
            db_session.add(
                VarietyDB(
                    symbol=symbol,
                    contract_code=symbol + "2501",
                    name=name,
                    exchange="SHFE",
                    category="测试",
                    is_active=True,
                )
            )
    db_session.commit()


class TestResolveSymbol:
    def test_resolve_builtin_alias(self, db_session, _seed_varieties):
        assert resolve_symbol(db_session, "螺纹钢走势如何") == "RB"
        assert resolve_symbol(db_session, "黄金价格") == "AU"
        assert resolve_symbol(db_session, "铜期货") == "CU"

    def test_resolve_symbol_code(self, db_session, _seed_varieties):
        assert resolve_symbol(db_session, "RB2501") == "RB"
        assert resolve_symbol(db_session, "AU") == "AU"

    def test_resolve_db_name(self, db_session, _seed_varieties):
        # 数据库中品种名称应被识别
        assert resolve_symbol(db_session, "铝最近怎么样") == "AL"
        assert resolve_symbol(db_session, "锌技术面") == "ZN"

    def test_resolve_unknown_returns_none(self, db_session, _seed_varieties):
        assert resolve_symbol(db_session, "未知品种 XXXX") is None

    def test_resolve_longest_match_wins(self, db_session, _seed_varieties):
        # "螺纹钢" 应优先于 "螺纹"
        assert resolve_symbol(db_session, "螺纹钢 5 日均线上穿") == "RB"
