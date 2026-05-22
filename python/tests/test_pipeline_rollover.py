"""测试 pipeline run_fut_mapping 的 rollover 自动记录功能。"""
import pytest
from datetime import datetime

from models import VarietyDB, FutContractDB, ContractRolloverDB
from data_collector.pipeline import DataPipeline


class MockMappingCollector:
    """返回固定的 mapping 数据，模拟主力合约切换。"""
    def __init__(self, rows):
        self._rows = rows

    def fetch_mapping(self, trade_date=None):
        return self._rows

    def __class__(self):
        return MockMappingCollector


def test_run_fut_mapping_records_rollover(db_session):
    # 创建测试品种和合约
    variety = VarietyDB(
        symbol="TESTMAP",
        name="测试映射品种",
        exchange="SHFE",
        contract_code="TESTMAP2501",
    )
    db_session.add(variety)
    db_session.commit()
    db_session.refresh(variety)

    c1 = FutContractDB(
        ts_code="TESTMAP2501.SHF",
        symbol="TESTMAP2501",
        name="测试映射01",
        fut_code="TESTMAP",
        exchange="SHFE",
        is_active=True,
    )
    c2 = FutContractDB(
        ts_code="TESTMAP2502.SHF",
        symbol="TESTMAP2502",
        name="测试映射02",
        fut_code="TESTMAP",
        exchange="SHFE",
        is_active=True,
    )
    db_session.add_all([c1, c2])
    db_session.commit()
    db_session.refresh(c1)
    db_session.refresh(c2)

    # 初始主力合约是 TESTMAP2501
    assert variety.contract_code == "TESTMAP2501"

    # 模拟 collector 返回切换数据：从 TESTMAP2501 切换到 TESTMAP2502
    collector = MockMappingCollector([
        {"ts_code": "TESTMAP.SHF", "mapping_ts_code": "TESTMAP2502.SHFE"}
    ])
    pipeline = DataPipeline(collector=collector)
    stats = pipeline.run_fut_mapping(trade_date="20250210", db=db_session)

    assert stats["processed"] == 1
    assert stats["skipped"] == 0

    # 验证 variety.contract_code 已更新
    db_session.refresh(variety)
    assert variety.contract_code == "TESTMAP2502"

    # 验证 rollover 记录已创建
    rollover = (
        db_session.query(ContractRolloverDB)
        .filter(ContractRolloverDB.variety_id == variety.id)
        .first()
    )
    assert rollover is not None
    assert rollover.old_contract_code == "TESTMAP2501"
    assert rollover.new_contract_code == "TESTMAP2502"
    assert rollover.old_contract_id == c1.id
    assert rollover.new_contract_id == c2.id
    assert rollover.effective_date == datetime(2025, 2, 10)
    assert rollover.source == "mapping_pipeline"


def test_run_fut_mapping_no_change_no_rollover(db_session):
    variety = VarietyDB(
        symbol="TESTMAP2",
        name="测试映射品种2",
        exchange="SHFE",
        contract_code="TESTMAP22501",
    )
    db_session.add(variety)
    db_session.commit()
    db_session.refresh(variety)

    c1 = FutContractDB(
        ts_code="TESTMAP22501.SHF",
        symbol="TESTMAP22501",
        name="测试映射2-01",
        fut_code="TESTMAP2",
        exchange="SHFE",
        is_active=True,
    )
    db_session.add(c1)
    db_session.commit()

    # collector 返回相同的 mapping，不应触发切换
    collector = MockMappingCollector([
        {"ts_code": "TESTMAP2.SHF", "mapping_ts_code": "TESTMAP22501.SHFE"}
    ])
    pipeline = DataPipeline(collector=collector)
    stats = pipeline.run_fut_mapping(db=db_session)

    assert stats["processed"] == 0

    rollover_count = (
        db_session.query(ContractRolloverDB)
        .filter(ContractRolloverDB.variety_id == variety.id)
        .count()
    )
    assert rollover_count == 0
