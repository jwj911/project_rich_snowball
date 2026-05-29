"""连续 K 线服务（Continuous K-line Service）
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

import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from models import ContractRolloverDB, FutContractDB, KlineDataDB, VarietyDB
from services.kline_period import period_candidates

logger = logging.getLogger(__name__)

# 用于 segment 边界的 aware 常量，避免 naive/aware 比较错误
_MIN_DT = datetime(1970, 1, 1, tzinfo=UTC)
_MAX_DT = datetime(2099, 12, 31, 23, 59, 59, tzinfo=UTC)


def _ensure_aware(dt: datetime | None) -> datetime | None:
    """将 naive datetime 转换为 UTC aware，aware datetime 保持不变。"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def build_rollover_segments(
    db: Session,
    variety_id: int,
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[dict[str, Any]]:
    """根据品种 rollover 历史构建时间段 → 合约映射（segments）。

    返回 segment 列表，每个 segment 为 dict：
        {start, end, contract_id, contract_code}
    """
    variety = db.query(VarietyDB).filter(VarietyDB.id == variety_id).first()
    if not variety:
        return []

    rollovers = (
        db.query(ContractRolloverDB)
        .filter(ContractRolloverDB.variety_id == variety_id)
        .order_by(ContractRolloverDB.effective_date.asc())
        .all()
    )
    for r in rollovers:
        r.effective_date = _ensure_aware(r.effective_date)  # type: ignore[assignment,arg-type]

    variety_start = _MIN_DT
    if variety.listing_date:
        variety_start = _ensure_aware(variety.listing_date)  # type: ignore[assignment,arg-type]

    segments: list[dict[str, Any]] = []
    if rollovers:
        segments.append({
            "start": variety_start,
            "end": rollovers[0].effective_date,
            "contract_id": rollovers[0].old_contract_id,
            "contract_code": rollovers[0].old_contract_code,
        })
        for i in range(len(rollovers)):
            r = rollovers[i]
            seg_end = rollovers[i + 1].effective_date if i + 1 < len(rollovers) else _MAX_DT
            segments.append({
                "start": r.effective_date,
                "end": seg_end,
                "contract_id": r.new_contract_id,
                "contract_code": r.new_contract_code,
            })
    else:
        if variety.contract_code:
            contract = (
                db.query(FutContractDB)
                .filter(FutContractDB.symbol == variety.contract_code)
                .first()
            )
            if contract:
                segments.append({
                    "start": variety_start,
                    "end": _MAX_DT,
                    "contract_id": contract.id,
                    "contract_code": contract.symbol,
                })

    # 与外部 start/end 取交集，提前过滤无数据区间
    filtered: list[dict[str, Any]] = []
    for seg in segments:
        qs = max(start, seg["start"]) if start is not None else seg["start"]
        qe = min(end, seg["end"]) if end is not None else seg["end"]
        if qs < qe:
            seg["query_start"] = qs
            seg["query_end"] = qe
            filtered.append(seg)
    return filtered


def query_segment_klines(
    db: Session,
    variety_id: int,
    segment: dict,
    period: str,
    limit: int,
) -> list[dict]:
    """查询单个 segment 内的 K 线数据。

    返回内部行列表，每条包含 _dt 字段用于后续排序。
    """
    query_start = segment["query_start"]
    query_end = segment["query_end"]
    seg_limit = limit * 2

    seg_rows = []
    for candidate in period_candidates(period):
        q = (
            db.query(KlineDataDB)
            .filter(KlineDataDB.variety_id == variety_id)
            .filter(KlineDataDB.period == candidate)
            .filter(KlineDataDB.contract_id == segment["contract_id"])
            .filter(KlineDataDB.trading_time >= query_start)
            .filter(KlineDataDB.trading_time < query_end)
            .order_by(KlineDataDB.trading_time.asc())
        )
        seg_rows = q.limit(seg_limit).all()
        if seg_rows:
            break

    if not seg_rows:
        logger.warning(
            "Continuous kline gap: no data for contract_id=%s variety_id=%s period=%s "
            "segment [%s, %s). Skipping this segment.",
            segment["contract_id"], variety_id, period,
            query_start.isoformat(), query_end.isoformat(),
        )
        return []

    rows = []
    for row in seg_rows:
        dt = _ensure_aware(row.trading_time)  # type: ignore[arg-type]
        assert dt is not None
        rows.append({
            "time": dt.isoformat(),
            "open": row.open_price,
            "high": row.high_price,
            "low": row.low_price,
            "close": row.close_price,
            "volume": row.volume,
            "contract_code": segment["contract_code"],
            "contract_id": segment["contract_id"],
            "_dt": dt,
        })
    return rows


def _compute_segment_gaps(
    sorted_segments: list[dict],
    all_rows: list[dict],
) -> dict[int | None, Decimal]:
    """计算每个 segment（除最新外）的向后累计调整量。

    从最新 segment 开始向前遍历，每遇到一个换月点，
    计算新旧合约在切换时的 close 价差，并将更早的历史价格累计该价差。
    返回 {contract_id: total_gap} 映射。
    """
    segment_adj: dict[int | None, Decimal] = {
        seg["contract_id"]: Decimal(0) for seg in sorted_segments
    }
    total_gap = Decimal(0)

    for i in range(len(sorted_segments) - 1, 0, -1):
        curr_seg = sorted_segments[i]
        prev_seg = sorted_segments[i - 1]

        curr_first = next(
            (r for r in all_rows
             if r.get("contract_id") == curr_seg["contract_id"]
             and r["_dt"] >= curr_seg["start"]),
            None,
        )
        prev_last = next(
            (r for r in reversed(all_rows)
             if r.get("contract_id") == prev_seg["contract_id"]
             and r["_dt"] < curr_seg["start"]),
            None,
        )

        if curr_first and prev_last:
            total_gap += curr_first["close"] - prev_last["close"]

        segment_adj[prev_seg["contract_id"]] = total_gap

    return segment_adj


def apply_backward_adjustment(all_rows: list[dict], segments: list[dict]) -> None:
    """对 all_rows 应用反向调整（Backward Adjustment），消除换月跳空。

    这样可保证最新合约的价格与真实市场一致，技术指标不会因换月跳空失真。
    """
    if len(segments) <= 1:
        return

    sorted_segments = sorted(segments, key=lambda s: s["start"])
    segment_adj = _compute_segment_gaps(sorted_segments, all_rows)

    for r in all_rows:
        adj = segment_adj.get(r.get("contract_id"), Decimal(0))
        if not adj:
            continue
        r["open"] -= adj
        r["high"] -= adj
        r["low"] -= adj
        r["close"] -= adj
        if any(r[k] <= 0 for k in ("open", "high", "low", "close")):
            logger.warning(
                "Backward adjustment produced non-positive price for contract_id=%s: %s",
                r.get("contract_id"), {k: r[k] for k in ("open", "high", "low", "close")}
            )


def get_continuous_kline(
    db: Session,
    variety_id: int,
    period: str = "D",
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = 5000,
    adjustment: str = "backward",
) -> list[dict]:
    """获取某品种的连续 K 线。

    参数:
        db: SQLAlchemy Session
        variety_id: 品种 ID
        period: K 线周期，如 "D", "60", "15"
        start: 起始时间（包含）
        end: 结束时间（包含）
        limit: 最大返回条数
        adjustment: 换月价差调整策略，"none" 不调整，"backward" 反向调整（默认）

    返回:
        按 trading_time 升序排列的 dict 列表，每条包含:
        {time, open, high, low, close, volume, contract_code, contract_id}
    """
    start = _ensure_aware(start)
    end = _ensure_aware(end)

    segments = build_rollover_segments(db, variety_id, start, end)
    if not segments:
        return []

    all_rows = []
    for seg in segments:
        seg_rows = query_segment_klines(db, variety_id, seg, period, limit)
        all_rows.extend(seg_rows)

    all_rows.sort(key=lambda x: x["_dt"])

    if adjustment == "backward":
        apply_backward_adjustment(all_rows, segments)

    for r in all_rows[:limit]:
        del r["_dt"]
    return all_rows[:limit]


def _fetch_kline_rows(db: Session, base_filters: list, period: str, start: datetime | None, end: datetime | None, limit: int):
    """通用 K 线查询：先按 period 候选列表 fallback，再应用时间过滤和 limit。"""
    for candidate in period_candidates(period):
        q = db.query(KlineDataDB).filter(*base_filters).filter(KlineDataDB.period == candidate)
        if start:
            q = q.filter(KlineDataDB.trading_time >= start)
        if end:
            q = q.filter(KlineDataDB.trading_time <= end)
        rows = q.order_by(KlineDataDB.trading_time.asc()).limit(limit).all()
        if rows:
            return rows
    return []


def attach_contract_metadata(rows: list, db: Session, default_contract_code: str | None = None) -> list[dict]:
    """为原始 K 线行附加 contract 元数据，返回标准 dict 列表。

    如果行中 contract_id 能在 FutContractDB 中找到，则使用真实合约信息；
    否则使用 default_contract_code 和原始 contract_id。
    """
    if not rows:
        return []

    contract_ids = {r.contract_id for r in rows}
    contracts = {
        c.id: c
        for c in db.query(FutContractDB).filter(FutContractDB.id.in_(contract_ids)).all()
    } if contract_ids else {}

    result = []
    for r in rows:
        actual = contracts.get(r.contract_id)
        result.append({
            "time": r.trading_time.isoformat(),
            "open": r.open_price,
            "high": r.high_price,
            "low": r.low_price,
            "close": r.close_price,
            "volume": r.volume,
            "contract_code": actual.symbol if actual else default_contract_code,
            "contract_id": actual.id if actual else r.contract_id,
        })
    return result


def get_main_contract_kline(
    db: Session,
    variety_id: int,
    period: str = "D",
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = 5000,
) -> list[dict]:
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

    if contract:
        rows = _fetch_kline_rows(
            db, [KlineDataDB.contract_id == contract.id], period, start, end, limit
        )
        if rows:
            return attach_contract_metadata(rows, db, default_contract_code=contract.symbol)  # type: ignore[arg-type]

    # 回退：按 variety_id 查询，不限制 contract_id
    rows = _fetch_kline_rows(
        db, [KlineDataDB.variety_id == variety_id], period, start, end, limit
    )
    return attach_contract_metadata(rows, db, default_contract_code=variety.contract_code)  # type: ignore[arg-type]
