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

import logging
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from models import ContractRolloverDB, FutContractDB, KlineDataDB, VarietyDB
from services.kline_period import period_candidates


# 用于 segment 边界的 aware 常量，避免 naive/aware 比较错误
_MIN_DT = datetime(1970, 1, 1, tzinfo=timezone.utc)
_MAX_DT = datetime(2099, 12, 31, 23, 59, 59, tzinfo=timezone.utc)


def _ensure_aware(dt: datetime | None) -> datetime | None:
    """将 naive datetime 转换为 UTC aware，aware datetime 保持不变。"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _apply_backward_adjustment(all_rows: list[dict], segments: list[dict]) -> None:
    """对 all_rows 应用反向调整（Backward Adjustment），消除换月跳空。

    逻辑：从最新 segment 开始向前遍历，每遇到一个换月点，
    计算新旧合约在切换时的 close 价差，并将更早的历史价格平移该价差。
    这样可保证最新合约的价格与真实市场一致，技术指标不会因换月跳空失真。
    """
    if len(segments) <= 1:
        return

    # 按 segment start 排序（从旧到新）
    sorted_segments = sorted(segments, key=lambda s: s["start"])

    # 从最新向最旧计算累积调整值
    segment_adj = {seg["contract_id"]: Decimal(0) for seg in segments}
    total_gap = Decimal(0)

    for i in range(len(sorted_segments) - 1, 0, -1):
        curr_seg = sorted_segments[i]
        prev_seg = sorted_segments[i - 1]

        # 找到 curr_seg 的第一个 close（切换后）
        curr_first = next(
            (r for r in all_rows
             if r.get("contract_id") == curr_seg["contract_id"]
             and r["_dt"] >= curr_seg["start"]),
            None,
        )
        # 找到 prev_seg 的最后一个 close（切换前）
        prev_last = next(
            (r for r in reversed(all_rows)
             if r.get("contract_id") == prev_seg["contract_id"]
             and r["_dt"] < curr_seg["start"]),
            None,
        )

        if curr_first and prev_last:
            gap = curr_first["close"] - prev_last["close"]
            total_gap += gap

        segment_adj[prev_seg["contract_id"]] = total_gap

    # 应用调整
    for r in all_rows:
        adj = segment_adj.get(r.get("contract_id"), Decimal(0))
        if adj:
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
    # 归一化 start/end，避免 naive/aware 混用
    start = _ensure_aware(start)
    end = _ensure_aware(end)

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

    # SQLite 读出 DateTime(timezone=True) 可能为 naive，需归一化
    for r in rollovers:
        r.effective_date = _ensure_aware(r.effective_date)

    # 构建时间段 → 合约映射
    # 每个 rollover 的 effective_date 是切换点：
    #   [prev_effective, effective_date) → old_contract
    #   [effective_date, next_effective) → new_contract
    # 确定品种的起始边界（避免从 1970 年开始查询）
    # 使用上市日期作为起点；若无上市日期则回退到最小时间
    variety_start = _MIN_DT
    if variety.listing_date:
        variety_start = _ensure_aware(variety.listing_date)

    segments = []
    if rollovers:
        # 第一段：从品种上市时间到第一个 rollover 生效日期之前
        segments.append({
            "start": variety_start,
            "end": rollovers[0].effective_date,
            "contract_id": rollovers[0].old_contract_id,
            "contract_code": rollovers[0].old_contract_code,
        })
        # 中间段：每个 rollover 生效日期到下一个 rollover 生效日期之前
        for i in range(len(rollovers)):
            r = rollovers[i]
            seg_start = r.effective_date
            seg_end = rollovers[i + 1].effective_date if i + 1 < len(rollovers) else _MAX_DT
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
                    "start": variety_start,
                    "end": _MAX_DT,
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

        # 给单段查询加 LIMIT，避免某段数据异常庞大时内存爆炸
        seg_limit = limit * 2  # 留足余量供多段合并后截断
        seg_rows = []
        for candidate in period_candidates(period):
            q = (
                db.query(KlineDataDB)
                .filter(KlineDataDB.variety_id == variety_id)
                .filter(KlineDataDB.period == candidate)
                .filter(KlineDataDB.contract_id == seg["contract_id"])
                .filter(KlineDataDB.trading_time >= query_start)
                .filter(KlineDataDB.trading_time < query_end)
                .order_by(KlineDataDB.trading_time.asc())
            )
            seg_rows = q.limit(seg_limit).all()
            if seg_rows:
                break

        # 若该 contract_id 下无数据，回退到不限制 contract_id（兼容历史数据不一致场景）
        if not seg_rows:
            logger.warning(
                "Continuous kline fallback: no data for contract_id=%s variety_id=%s period=%s, "
                "falling back to unfiltered query (risk of mixing adjacent contracts).",
                seg["contract_id"], variety_id, period,
            )
            for candidate in period_candidates(period):
                q_fallback = (
                    db.query(KlineDataDB)
                    .filter(KlineDataDB.variety_id == variety_id)
                    .filter(KlineDataDB.period == candidate)
                    .filter(KlineDataDB.trading_time >= query_start)
                    .filter(KlineDataDB.trading_time < query_end)
                    .order_by(KlineDataDB.trading_time.asc())
                )
                seg_rows = q_fallback.limit(seg_limit).all()
                if seg_rows:
                    break

        for row in seg_rows:
            # SQLite 读出 DateTime(timezone=True) 可能为 naive，需归一化
            dt = _ensure_aware(row.trading_time)
            all_rows.append({
                "time": dt.isoformat(),
                "open": row.open_price,
                "high": row.high_price,
                "low": row.low_price,
                "close": row.close_price,
                "volume": row.volume,
                "contract_code": seg["contract_code"],
                "contract_id": seg["contract_id"],
                "_dt": dt,
            })

    # 3. 按时间排序（使用 datetime 对象而非字符串，避免混合时区格式排序错误）
    all_rows.sort(key=lambda x: x["_dt"])

    # 4. 换月价差调整（默认反向调整，消除换月跳空）
    if adjustment == "backward":
        _apply_backward_adjustment(all_rows, segments)

    # 截断后移除内部排序字段
    for r in all_rows[:limit]:
        del r["_dt"]
    return all_rows[:limit]


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

    # 优先按 contract_id 精确查询；若该 contract 下无数据，回退到按 variety_id 查询
    # 以兼容历史数据 contract_id 可能不一致的场景
    if contract:
        rows = []
        for candidate in period_candidates(period):
            q = (
                db.query(KlineDataDB)
                .filter(KlineDataDB.contract_id == contract.id)
                .filter(KlineDataDB.period == candidate)
            )
            if start:
                q = q.filter(KlineDataDB.trading_time >= start)
            if end:
                q = q.filter(KlineDataDB.trading_time <= end)
            rows = q.order_by(KlineDataDB.trading_time.asc()).limit(limit).all()
            if rows:
                break
        if rows:
            return [
                {
                    "time": r.trading_time.isoformat(),
                    "open": r.open_price,
                    "high": r.high_price,
                    "low": r.low_price,
                    "close": r.close_price,
                    "volume": r.volume,
                    "contract_code": contract.symbol,
                    "contract_id": contract.id,
                }
                for r in rows
            ]

    # 回退：按 variety_id 查询，不限制 contract_id
    rows = []
    for candidate in period_candidates(period):
        q = (
            db.query(KlineDataDB)
            .filter(KlineDataDB.variety_id == variety_id)
            .filter(KlineDataDB.period == candidate)
        )
        if start:
            q = q.filter(KlineDataDB.trading_time >= start)
        if end:
            q = q.filter(KlineDataDB.trading_time <= end)
        rows = q.order_by(KlineDataDB.trading_time.asc()).limit(limit).all()
        if rows:
            break
    return [
        {
            "time": r.trading_time.isoformat(),
            "open": r.open_price,
            "high": r.high_price,
            "low": r.low_price,
            "close": r.close_price,
            "volume": r.volume,
            "contract_code": contract.symbol if contract else variety.contract_code,
            "contract_id": contract.id if contract else None,
        }
        for r in rows
    ]
