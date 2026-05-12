"""
连续 K 线服务（Continuous K-line Service）
============================================
将不同交割月份的合约 K 线，按主力切换日期拼接成一条连续时间序列。

核心策略：
    1. 读取品种的 contract_rollovers 表，拿到主力合约切换时间点。
    2. 对每个时间段，从 kline_data 中读取对应 contract_id 的数据。
    3. 按 trading_time 合并去重，返回连续 OHLCV。

适用场景：
    - 回测需要跨合约的连续价格序列
    - 技术分析图表展示主力连续走势
"""

from typing import List, Optional
from datetime import datetime
from sqlalchemy.orm import Session

from models import KlineDataDB, ContractRolloverDB, VarietyDB, FutContractDB


def get_continuous_kline(
    db: Session,
    variety_id: int,
    period: str = "D",
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    limit: int = 5000,
) -> List[dict]:
    """
    获取某品种的连续 K 线。

    参数:
        db: SQLAlchemy Session
        variety_id: 品种 ID
        period: K 线周期，如 "D", "60", "15"
        start: 起始时间（包含）
        end: 结束时间（包含）
        limit: 最大返回条数

    返回:
        按 trading_time 升序排列的 dict 列表，每条包含:
        {time, open, high, low, close, volume, contract_code, contract_id}
    """
    variety = db.query(VarietyDB).filter(VarietyDB.id == variety_id).first()
    if not variety:
        return []

    # 1. 读取该品种的切换历史（按时间升序）
    rollovers = (
        db.query(ContractRolloverDB)
        .filter(ContractRolloverDB.variety_id == variety_id)
        .order_by(ContractRolloverDB.effective_date.asc())
        .all()
    )

    # 构建时间段 → 合约映射
    # 每个 rollover 的 effective_date 是切换点：
    #   [prev_effective, effective_date) → old_contract
    #   [effective_date, next_effective) → new_contract
    segments = []
    if rollovers:
        # 第一段：从最小时间到第一个 rollover 生效日期之前
        segments.append({
            "start": datetime.min,
            "end": rollovers[0].effective_date,
            "contract_id": rollovers[0].old_contract_id,
            "contract_code": rollovers[0].old_contract_code,
        })
        # 中间段：每个 rollover 生效日期到下一个 rollover 生效日期之前
        for i in range(len(rollovers)):
            r = rollovers[i]
            seg_start = r.effective_date
            seg_end = rollovers[i + 1].effective_date if i + 1 < len(rollovers) else datetime.max
            segments.append({
                "start": seg_start,
                "end": seg_end,
                "contract_id": r.new_contract_id,
                "contract_code": r.new_contract_code,
            })
    else:
        # 没有切换记录时，回退到当前品种 contract_code 对应的合约
        if variety.contract_code:
            contract = (
                db.query(FutContractDB)
                .filter(FutContractDB.symbol == variety.contract_code)
                .first()
            )
            if contract:
                segments.append({
                    "start": datetime.min,
                    "end": datetime.max,
                    "contract_id": contract.id,
                    "contract_code": contract.symbol,
                })

    if not segments:
        return []

    # 2. 对每个时间段查询 K 线
    all_rows = []
    for seg in segments:
        # 与外部 start/end 取交集
        query_start = max(start, seg["start"]) if start else seg["start"]
        query_end = min(end, seg["end"]) if end else seg["end"]

        if query_start >= query_end:
            continue

        q = (
            db.query(KlineDataDB)
            .filter(KlineDataDB.variety_id == variety_id)
            .filter(KlineDataDB.period == period)
            .filter(KlineDataDB.contract_id == seg["contract_id"])
            .filter(KlineDataDB.trading_time >= query_start)
            .filter(KlineDataDB.trading_time < query_end)
            .order_by(KlineDataDB.trading_time.asc())
        )

        for row in q.all():
            all_rows.append({
                "time": row.trading_time.isoformat(),
                "open": float(row.open_price),
                "high": float(row.high_price),
                "low": float(row.low_price),
                "close": float(row.close_price),
                "volume": row.volume,
                "contract_code": seg["contract_code"],
                "contract_id": seg["contract_id"],
            })

    # 3. 按时间排序并截断
    all_rows.sort(key=lambda x: x["time"])
    return all_rows[:limit]


def get_main_contract_kline(
    db: Session,
    variety_id: int,
    period: str = "D",
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    limit: int = 5000,
) -> List[dict]:
    """
    获取当前主力合约的 K 线（不拼接，仅返回当前合约）。
    这是连续 K 线的退化版本，适合不需要历史切换的场景。
    """
    variety = db.query(VarietyDB).filter(VarietyDB.id == variety_id).first()
    if not variety or not variety.contract_code:
        return []

    contract = (
        db.query(FutContractDB)
        .filter(FutContractDB.symbol == variety.contract_code)
        .first()
    )
    if not contract:
        return []

    q = (
        db.query(KlineDataDB)
        .filter(KlineDataDB.contract_id == contract.id)
        .filter(KlineDataDB.period == period)
    )
    if start:
        q = q.filter(KlineDataDB.trading_time >= start)
    if end:
        q = q.filter(KlineDataDB.trading_time <= end)

    rows = q.order_by(KlineDataDB.trading_time.asc()).limit(limit).all()
    return [
        {
            "time": r.trading_time.isoformat(),
            "open": float(r.open_price),
            "high": float(r.high_price),
            "low": float(r.low_price),
            "close": float(r.close_price),
            "volume": r.volume,
            "contract_code": contract.symbol,
            "contract_id": contract.id,
        }
        for r in rows
    ]
