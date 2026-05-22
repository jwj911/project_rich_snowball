"""
测试 scripts/backfill_kline_contract_id.py 的历史语义回填逻辑。
"""

import os
import sys
import tempfile
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from sqlalchemy.orm import Session

from models import (
    Base,
    KlineDataDB,
    VarietyDB,
    FutContractDB,
    ContractRolloverDB,
    SessionLocal,
)

# 被测模块需要在 models 导入后加载，因为它依赖 SessionLocal 的 engine
import scripts.backfill_kline_contract_id as backfill_mod


@pytest.fixture(scope="function")
def backfill_db():
    """为 backfill 测试创建独立的内存数据库（contract_id 临时允许 NULL 以模拟迁移前状态）。"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    # 临时允许 contract_id 为 NULL，模拟 Alembic 迁移前的表结构
    KlineDataDB.__table__.c.contract_id.nullable = True

    engine = create_engine("sqlite:///:memory:")
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)

    # 恢复原始约束，避免影响其他测试
    KlineDataDB.__table__.c.contract_id.nullable = False


def _seed_variety(db: Session, vid: int, code: str, name: str = "测试品种") -> VarietyDB:
    v = VarietyDB(
        id=vid,
        symbol=code,
        name=name,
        exchange="SHFE",
        category="测试",
        contract_code=f"{code}2406",
    )
    db.add(v)
    db.commit()
    return v


def _seed_contract(db: Session, cid: int, symbol: str, ts_code: str) -> FutContractDB:
    c = FutContractDB(
        id=cid,
        symbol=symbol,
        ts_code=ts_code,
        name=f"{symbol}合约",
        exchange="SHFE",
        list_date=datetime(2024, 1, 1),
        delist_date=datetime(2025, 12, 31),
    )
    db.add(c)
    db.commit()
    return c


def _seed_kline(db: Session, vid: int, trading_time: datetime, contract_id: int | None = None) -> KlineDataDB:
    # 测试需要插入 contract_id=NULL 的记录，但最新模型已是 nullable=False
    # 通过直接 SQL 插入绕过 ORM 约束
    # 注意：SQLite 中 DateTime 以 TEXT 存储，ORM 默认带 .000000，
    # text() 参数绑定不带微秒，会导致字符串级比较偏差，故显式格式化
    from sqlalchemy import text
    tt_str = trading_time.strftime("%Y-%m-%d %H:%M:%S.%f") if trading_time else None
    db.execute(
        text(
            "INSERT INTO kline_data (variety_id, contract_id, period, trading_time, open_price, high_price, low_price, close_price, volume) "
            "VALUES (:vid, :cid, :period, :tt, :o, :h, :l, :c, :v)"
        ),
        {
            "vid": vid,
            "cid": contract_id,
            "period": "1d",
            "tt": tt_str,
            "o": 100.0,
            "h": 101.0,
            "l": 99.0,
            "c": 100.5,
            "v": 1000,
        },
    )
    db.commit()
    return db.query(KlineDataDB).filter(KlineDataDB.variety_id == vid, KlineDataDB.trading_time == trading_time).first()


def _seed_rollover(
    db: Session,
    vid: int,
    old_cid: int | None,
    old_code: str | None,
    new_cid: int,
    new_code: str,
    effective_date: datetime,
) -> ContractRolloverDB:
    r = ContractRolloverDB(
        variety_id=vid,
        old_contract_id=old_cid,
        new_contract_id=new_cid,
        old_contract_code=old_code,
        new_contract_code=new_code,
        effective_date=effective_date,
    )
    db.add(r)
    db.commit()
    return r


class TestBuildSegments:
    """测试 _build_segments 的时段划分逻辑。"""

    def test_no_rollovers_fallback(self, backfill_db: Session):
        """无 rollover 时回退到当前主力合约（限制在合约生命周期内）。"""
        db = backfill_db
        _seed_variety(db, 1, "AU")
        _seed_contract(db, 10, "AU2406", "AU2406.SHF")

        segs = backfill_mod._build_segments(db, 1, [], "AU2406")
        assert len(segs) == 1
        assert segs[0]["contract_id"] == 10
        assert segs[0]["contract_code"] == "AU2406"
        assert "fallback_current_main" in segs[0]["note"]

    def test_no_rollovers_no_default(self, backfill_db: Session):
        """无 rollover 且无 default_code 时返回空。"""
        db = backfill_db
        segs = backfill_mod._build_segments(db, 1, [], None)
        assert segs == []

    def test_single_rollover_with_old(self, backfill_db: Session):
        """单个 rollover，old_contract 存在。"""
        db = backfill_db
        _seed_variety(db, 1, "AU")
        _seed_contract(db, 10, "AU2406", "AU2406.SHF")
        _seed_contract(db, 11, "AU2412", "AU2412.SHF")
        eff = datetime(2024, 6, 15)
        _seed_rollover(db, 1, 10, "AU2406", 11, "AU2412", eff)

        segs = backfill_mod._build_segments(db, 1, db.query(ContractRolloverDB).all(), "AU2406")
        assert len(segs) == 2
        assert segs[0]["contract_id"] == 10
        assert segs[0]["end"] == eff
        assert segs[1]["contract_id"] == 11
        assert segs[1]["start"] == eff

    def test_single_rollover_without_old(self, backfill_db: Session):
        """首个 rollover 无 old_contract 时 fallback 到 default_code。"""
        db = backfill_db
        _seed_variety(db, 1, "AU")
        _seed_contract(db, 11, "AU2412", "AU2412.SHF")
        eff = datetime(2024, 6, 15)
        _seed_rollover(db, 1, None, None, 11, "AU2412", eff)

        segs = backfill_mod._build_segments(db, 1, db.query(ContractRolloverDB).all(), "AU2406")
        assert len(segs) == 1  # default_code 无法解析（无 AU2406 合约），只有 new_contract 段
        assert segs[0]["contract_id"] == 11
        assert segs[0]["start"] == eff

    def test_multiple_rollovers(self, backfill_db: Session):
        """多个 rollover 产生多个时段。"""
        db = backfill_db
        _seed_variety(db, 1, "AU")
        for cid, sym in [(10, "AU2406"), (11, "AU2412"), (12, "AU2506")]:
            _seed_contract(db, cid, sym, f"{sym}.SHF")
        r1 = _seed_rollover(db, 1, 10, "AU2406", 11, "AU2412", datetime(2024, 6, 15))
        r2 = _seed_rollover(db, 1, 11, "AU2412", 12, "AU2506", datetime(2024, 12, 15))

        segs = backfill_mod._build_segments(db, 1, db.query(ContractRolloverDB).all(), "AU2406")
        assert len(segs) == 3
        assert segs[0]["contract_id"] == 10
        assert segs[0]["end"] == r1.effective_date
        assert segs[1]["contract_id"] == 11
        assert segs[1]["start"] == r1.effective_date
        assert segs[1]["end"] == r2.effective_date
        assert segs[2]["contract_id"] == 12
        assert segs[2]["start"] == r2.effective_date

    def test_merge_consecutive_same_contract(self, backfill_db: Session):
        """连续相同 contract_id 的时段应合并。"""
        db = backfill_db
        _seed_variety(db, 1, "AU")
        _seed_contract(db, 10, "AU2406", "AU2406.SHF")
        _seed_rollover(db, 1, None, None, 10, "AU2406", datetime(2024, 3, 1))
        _seed_rollover(db, 1, 10, "AU2406", 10, "AU2406", datetime(2024, 6, 1))

        segs = backfill_mod._build_segments(db, 1, db.query(ContractRolloverDB).all(), "AU2406")
        # 首个 rollover 无 old，会生成 pre_first_rollover_fallback，与后续 rollover 合并
        assert len(segs) == 1
        assert segs[0]["contract_id"] == 10
        assert segs[0]["note"] == "pre_first_rollover_fallback+rollover_1+rollover_2"


class TestBackfillSegments:
    """测试 _backfill_segments 的数据库更新逻辑。"""

    def test_backfill_by_time_range(self, backfill_db: Session):
        """按时段范围正确更新 contract_id。"""
        db = backfill_db
        _seed_variety(db, 1, "AU")
        _seed_contract(db, 10, "AU2406", "AU2406.SHF")
        # 创建 5 条 K 线，分布在 6月10日-14日
        for i in range(5):
            _seed_kline(db, 1, datetime(2024, 6, 10 + i))

        segs = [{
            "start": datetime(2024, 6, 1),
            "end": datetime(2024, 6, 13),
            "contract_id": 10,
            "contract_code": "AU2406",
            "note": "test",
        }]
        rows = backfill_mod._backfill_segments(db, 1, segs)
        assert len(rows) == 1
        assert rows[0]["updated"] == 3  # 10,11,12 三天

        # 验证数据库状态
        null_count = db.query(KlineDataDB).filter(KlineDataDB.contract_id.is_(None)).count()
        assert null_count == 2  # 13,14 未被更新

        updated = db.query(KlineDataDB).filter(KlineDataDB.contract_id == 10).all()
        assert len(updated) == 3


class TestBackfillIntegration:
    """测试 backfill 整体流程。"""

    def test_backfill_dry_run(self, backfill_db: Session):
        """dry_run 模式不应实际写入。"""
        db = backfill_db
        _seed_variety(db, 1, "AU")
        _seed_contract(db, 10, "AU2406", "AU2406.SHF")
        _seed_kline(db, 1, datetime(2024, 6, 10))

        summary = backfill_mod.backfill(dry_run=True, db=db)
        assert summary["total_null_before"] == 1
        assert summary["total_matched"] == 1
        # dry_run 后数据应回滚，仍为 null
        null_count = db.query(KlineDataDB).filter(KlineDataDB.contract_id.is_(None)).count()
        assert null_count == 1

    def test_backfill_real_run(self, backfill_db: Session):
        """正常模式应写入并生成 CSV 报告。"""
        db = backfill_db
        _seed_variety(db, 1, "AU")
        _seed_contract(db, 10, "AU2406", "AU2406.SHF")
        _seed_kline(db, 1, datetime(2024, 6, 10))

        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as f:
            report_path = f.name

        try:
            summary = backfill_mod.backfill(dry_run=False, report_csv=report_path, db=db)
            assert summary["total_null_before"] == 1
            assert summary["total_matched"] == 1
            assert summary["total_null_after"] == 0
            assert os.path.exists(report_path)
            content = open(report_path, "r", encoding="utf-8").read()
            assert "variety_id" in content
            assert "AU2406" in content
        finally:
            os.unlink(report_path)

    def test_backfill_with_rollovers(self, backfill_db: Session):
        """结合 rollover 的历史语义回填。"""
        db = backfill_db
        _seed_variety(db, 1, "AU")
        _seed_contract(db, 10, "AU2406", "AU2406.SHF")
        _seed_contract(db, 11, "AU2412", "AU2412.SHF")
        _seed_rollover(db, 1, 10, "AU2406", 11, "AU2412", datetime(2024, 6, 15))

        # 6月10-14日属于 AU2406，6月15-20日属于 AU2412
        for i in range(11):
            _seed_kline(db, 1, datetime(2024, 6, 10 + i))

        summary = backfill_mod.backfill(db=db)
        assert summary["total_matched"] == 11
        assert summary["total_null_after"] == 0

        k2406 = db.query(KlineDataDB).filter(KlineDataDB.contract_id == 10).count()
        k2412 = db.query(KlineDataDB).filter(KlineDataDB.contract_id == 11).count()
        assert k2406 == 5  # 10-14
        assert k2412 == 6  # 15-20

    def test_no_null_records(self, backfill_db: Session):
        """无 null 记录时直接返回。"""
        db = backfill_db
        summary = backfill_mod.backfill(db=db)
        assert summary["total_null_before"] == 0
        assert summary["total_matched"] == 0
