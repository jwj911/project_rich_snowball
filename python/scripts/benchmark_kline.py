"""K 线查询性能基准测试

用法：
    # 基准测试（跑 20 轮，输出 p50/p95/p99）
    cd python
    $env:DATABASE_URL="postgresql://futures:futures123@localhost:15432/futures_community"
    .\venv\Scripts\python.exe scripts\benchmark_kline.py

    # 只输出 EXPLAIN ANALYZE（不跑多轮计时）
    $env:DATABASE_URL="postgresql://futures:futures123@localhost:15432/futures_community"
    .\venv\Scripts\python.exe scripts\benchmark_kline.py --explain

前置条件：
    - 数据库已启动且可连接
    - alembic upgrade head 已执行
    - 若表中无 benchmark 数据，脚本会自动生成并插入
"""

import argparse
import os
import statistics
import sys
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal

# 将项目根目录加入路径，以便导入 models
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from models import (
    Base,
    ContractRolloverDB,
    FutContractDB,
    KlineDataDB,
    VarietyDB,
)
from services.continuous_kline import get_continuous_kline, get_main_contract_kline

BENCHMARK_SYMBOL = "BENCH"
BENCHMARK_CONTRACT_CODE = "BENCH2401"
BENCHMARK_CONTRACT_CODE_2 = "BENCH2405"


def _get_engine():
    database_url = os.getenv("DATABASE_URL", "sqlite:///./futures_community.db")
    return create_engine(database_url, echo=False, pool_pre_ping=True)


def _ensure_benchmark_data(session: Session) -> tuple[int, int, int]:
    """确保数据库中有足够的 benchmark 数据。返回 (variety_id, contract1_id, contract2_id)。"""
    variety = session.query(VarietyDB).filter(VarietyDB.symbol == BENCHMARK_SYMBOL).first()
    if not variety:
        variety = VarietyDB(
            symbol=BENCHMARK_SYMBOL,
            contract_code=BENCHMARK_CONTRACT_CODE,
            name="Benchmark Variety",
            exchange="SHFE",
            category="metal",
            tick_size=Decimal("1.0"),
            multiplier=Decimal("10.0"),
            is_active=True,
        )
        session.add(variety)
        session.flush()

    c1 = (
        session.query(FutContractDB)
        .filter(FutContractDB.symbol == BENCHMARK_CONTRACT_CODE)
        .first()
    )
    if not c1:
        c1 = FutContractDB(
            ts_code="BENCH2401.SHFE",
            symbol=BENCHMARK_CONTRACT_CODE,
            fut_code="BENCH",
            exchange="SHFE",
            list_date=datetime(2024, 1, 1, tzinfo=UTC),
            delist_date=datetime(2024, 4, 30, tzinfo=UTC),
            is_active=True,
        )
        session.add(c1)
        session.flush()

    c2 = (
        session.query(FutContractDB)
        .filter(FutContractDB.symbol == BENCHMARK_CONTRACT_CODE_2)
        .first()
    )
    if not c2:
        c2 = FutContractDB(
            ts_code="BENCH2405.SHFE",
            symbol=BENCHMARK_CONTRACT_CODE_2,
            fut_code="BENCH",
            exchange="SHFE",
            list_date=datetime(2024, 5, 1, tzinfo=UTC),
            delist_date=datetime(2024, 8, 31, tzinfo=UTC),
            is_active=True,
        )
        session.add(c2)
        session.flush()

    # rollover
    rollover = (
        session.query(ContractRolloverDB)
        .filter(
            ContractRolloverDB.variety_id == variety.id,
            ContractRolloverDB.new_contract_id == c2.id,
        )
        .first()
    )
    if not rollover:
        rollover = ContractRolloverDB(
            variety_id=variety.id,
            old_contract_id=c1.id,
            new_contract_id=c2.id,
            old_contract_code=c1.symbol,
            new_contract_code=c2.symbol,
            effective_date=datetime(2024, 5, 1, tzinfo=UTC),
            source="benchmark",
        )
        session.add(rollover)
        session.flush()

    # 检查已有 K 线数量
    existing_count = (
        session.query(KlineDataDB)
        .filter(KlineDataDB.variety_id == variety.id)
        .count()
    )

    target_daily = 365  # 1 年日线
    target_1min = 90 * 240  # 3 个月分钟线（约 90 交易日 × 240 根）

    if existing_count < target_daily + target_1min:
        print(f"[benchmark] 生成测试数据：现有 {existing_count} 条，目标 {target_daily + target_1min} 条 ...")
        _generate_klines(session, variety.id, c1.id, c2.id)
        session.commit()
        print("[benchmark] 测试数据生成完成。")
    else:
        print(f"[benchmark] 已有 {existing_count} 条 K 线数据，足够 benchmark。")

    return variety.id, c1.id, c2.id


def _generate_klines(session: Session, variety_id: int, c1_id: int, c2_id: int) -> None:
    """生成 1 年日线 + 3 个月分钟线模拟数据。"""
    base_price = Decimal("5000.0")
    volume_base = 10000

    # 1 年日线（c1: Jan-Apr, c2: May-Dec）
    start_date = datetime(2024, 1, 1, tzinfo=UTC)
    for i in range(365):
        dt = start_date + timedelta(days=i)
        contract_id = c1_id if dt.month <= 4 else c2_id
        price = base_price + Decimal(str((i % 100) - 50))
        session.add(
            KlineDataDB(
                variety_id=variety_id,
                contract_id=contract_id,
                period="D",
                trading_time=dt,
                trading_date=dt.date(),
                open_price=price,
                high_price=price + Decimal("10"),
                low_price=price - Decimal("10"),
                close_price=price + Decimal("5"),
                volume=volume_base + i,
                open_interest=volume_base,
            )
        )

    # 3 个月分钟线（1m，仅 c2，May-Jul）
    start_min = datetime(2024, 5, 1, 9, 0, tzinfo=UTC)
    for i in range(90 * 240):
        dt = start_min + timedelta(minutes=i)
        price = base_price + Decimal(str((i % 200) - 100))
        session.add(
            KlineDataDB(
                variety_id=variety_id,
                contract_id=c2_id,
                period="1m",
                trading_time=dt,
                trading_date=dt.date(),
                open_price=price,
                high_price=price + Decimal("2"),
                low_price=price - Decimal("2"),
                close_price=price + Decimal("1"),
                volume=volume_base + i,
                open_interest=volume_base,
            )
        )


def _timeit(fn, *args, **kwargs):
    """执行一次函数并返回（结果, 耗时_ms）。"""
    t0 = time.perf_counter()
    result = fn(*args, **kwargs)
    t1 = time.perf_counter()
    return result, (t1 - t0) * 1000


def _percentile(sorted_values: list[float], p: float) -> float:
    if not sorted_values:
        return 0.0
    k = (len(sorted_values) - 1) * p / 100.0
    f = int(k)
    c = f + 1 if f + 1 < len(sorted_values) else f
    if f == c:
        return sorted_values[f]
    return sorted_values[f] + (sorted_values[c] - sorted_values[f]) * (k - f)


def benchmark_variety_kline(session: Session, variety_id: int, iterations: int = 20) -> dict:
    """测试品种 K 线查询（等价于 GET /api/klines/{symbol}）。"""
    times = []
    for _ in range(iterations):
        _, ms = _timeit(
            lambda: session.query(KlineDataDB)
            .filter(KlineDataDB.variety_id == variety_id, KlineDataDB.period == "D")
            .order_by(KlineDataDB.trading_time.desc())
            .limit(100)
            .all()
        )
        times.append(ms)
    times.sort()
    return {
        "name": "variety_kline (D, limit=100)",
        "iterations": iterations,
        "p50": _percentile(times, 50),
        "p95": _percentile(times, 95),
        "p99": _percentile(times, 99),
        "min": min(times),
        "max": max(times),
        "mean": statistics.mean(times),
    }


def benchmark_contract_kline(session: Session, contract_id: int, iterations: int = 20) -> dict:
    """测试合约 K 线查询（等价于 GET /api/contracts/{id}/kline）。"""
    times = []
    for _ in range(iterations):
        _, ms = _timeit(
            lambda: session.query(KlineDataDB)
            .filter(KlineDataDB.contract_id == contract_id, KlineDataDB.period == "D")
            .order_by(KlineDataDB.trading_time.asc())
            .limit(500)
            .all()
        )
        times.append(ms)
    times.sort()
    return {
        "name": f"contract_kline (contract_id={contract_id}, D, limit=500)",
        "iterations": iterations,
        "p50": _percentile(times, 50),
        "p95": _percentile(times, 95),
        "p99": _percentile(times, 99),
        "min": min(times),
        "max": max(times),
        "mean": statistics.mean(times),
    }


def benchmark_continuous_kline(session: Session, variety_id: int, iterations: int = 20) -> dict:
    """测试连续 K 线查询（等价于 GET /api/klines/{symbol}/continuous）。"""
    times = []
    for _ in range(iterations):
        _, ms = _timeit(
            get_continuous_kline,
            session,
            variety_id,
            period="D",
            limit=500,
            adjustment="backward",
        )
        times.append(ms)
    times.sort()
    return {
        "name": "continuous_kline (D, limit=500, backward)",
        "iterations": iterations,
        "p50": _percentile(times, 50),
        "p95": _percentile(times, 95),
        "p99": _percentile(times, 99),
        "min": min(times),
        "max": max(times),
        "mean": statistics.mean(times),
    }


def benchmark_main_kline(session: Session, variety_id: int, iterations: int = 20) -> dict:
    """测试主力 K 线查询（等价于 GET /api/klines/{symbol}/main）。"""
    times = []
    for _ in range(iterations):
        _, ms = _timeit(
            get_main_contract_kline,
            session,
            variety_id,
            period="D",
            limit=500,
        )
        times.append(ms)
    times.sort()
    return {
        "name": "main_contract_kline (D, limit=500)",
        "iterations": iterations,
        "p50": _percentile(times, 50),
        "p95": _percentile(times, 95),
        "p99": _percentile(times, 99),
        "min": min(times),
        "max": max(times),
        "mean": statistics.mean(times),
    }


def benchmark_minute_kline(session: Session, contract_id: int, iterations: int = 20) -> dict:
    """测试分钟 K 线查询（1m 周期，大量数据）。"""
    times = []
    for _ in range(iterations):
        _, ms = _timeit(
            lambda: session.query(KlineDataDB)
            .filter(KlineDataDB.contract_id == contract_id, KlineDataDB.period == "1m")
            .order_by(KlineDataDB.trading_time.asc())
            .limit(5000)
            .all()
        )
        times.append(ms)
    times.sort()
    return {
        "name": f"minute_kline (contract_id={contract_id}, 1m, limit=5000)",
        "iterations": iterations,
        "p50": _percentile(times, 50),
        "p95": _percentile(times, 95),
        "p99": _percentile(times, 99),
        "min": min(times),
        "max": max(times),
        "mean": statistics.mean(times),
    }


def run_explain(session: Session, variety_id: int, contract_id: int) -> None:
    """输出核心查询的 EXPLAIN ANALYZE 结果（PostgreSQL only）。"""
    is_pg = session.bind.dialect.name == "postgresql"
    if not is_pg:
        print("[explain] 当前数据库不是 PostgreSQL，跳过 EXPLAIN ANALYZE。")
        return

    queries = [
        (
            "variety_kline_D",
            """
            EXPLAIN ANALYZE
            SELECT * FROM kline_data
            WHERE variety_id = :vid AND period = 'D'
            ORDER BY trading_time DESC
            LIMIT 100
            """,
            {"vid": variety_id},
        ),
        (
            "contract_kline_D",
            """
            EXPLAIN ANALYZE
            SELECT * FROM kline_data
            WHERE contract_id = :cid AND period = 'D'
            ORDER BY trading_time ASC
            LIMIT 500
            """,
            {"cid": contract_id},
        ),
        (
            "minute_kline_1m",
            """
            EXPLAIN ANALYZE
            SELECT * FROM kline_data
            WHERE contract_id = :cid AND period = '1m'
            ORDER BY trading_time ASC
            LIMIT 5000
            """,
            {"cid": contract_id},
        ),
    ]

    for name, sql, params in queries:
        print(f"\n{'='*60}")
        print(f"EXPLAIN ANALYZE: {name}")
        print("=" * 60)
        result = session.execute(text(sql), params)
        for row in result:
            print(row[0])


def print_report(results: list[dict], total_rows: int) -> None:
    print(f"\n{'='*60}")
    print("K 线查询性能基准测试报告")
    print("=" * 60)
    print(f"数据库: {os.getenv('DATABASE_URL', 'sqlite:///./futures_community.db')}")
    print(f"测试时间: {datetime.now(UTC).isoformat()}")
    print(f"K 线总数据量: {total_rows} 条")
    print(f"{'-'*60}")

    for r in results:
        print(f"\n场景: {r['name']}")
        print(f"  迭代次数: {r['iterations']}")
        print(f"  p50:    {r['p50']:8.3f} ms")
        print(f"  p95:    {r['p95']:8.3f} ms")
        print(f"  p99:    {r['p99']:8.3f} ms")
        print(f"  mean:   {r['mean']:8.3f} ms")
        print(f"  min:    {r['min']:8.3f} ms")
        print(f"  max:    {r['max']:8.3f} ms")

    print(f"\n{'='*60}")
    print("阈值建议（供分区决策参考）:")
    print("  - p95 > 500ms 时，考虑 PG range partition by trading_time")
    print("  - 单品种 1m 数据 > 100 万行时，考虑按 period 分表")
    print("  - 当前所有 p95 < 500ms 时，保持现有单表 + 索引策略")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="K 线查询性能基准测试")
    parser.add_argument("--explain", action="store_true", help="只输出 EXPLAIN ANALYZE，不跑多轮计时")
    parser.add_argument("--iterations", type=int, default=20, help="每场景迭代次数（默认 20）")
    args = parser.parse_args()

    engine = _get_engine()
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    try:
        variety_id, c1_id, c2_id = _ensure_benchmark_data(session)
        total_rows = (
            session.query(KlineDataDB)
            .filter(KlineDataDB.variety_id == variety_id)
            .count()
        )

        if args.explain:
            run_explain(session, variety_id, c1_id)
            return

        print(f"[benchmark] 开始测试，每场景 {args.iterations} 轮 ...\n")

        results = []
        results.append(benchmark_variety_kline(session, variety_id, args.iterations))
        results.append(benchmark_contract_kline(session, c1_id, args.iterations))
        results.append(benchmark_main_kline(session, variety_id, args.iterations))
        results.append(benchmark_continuous_kline(session, variety_id, args.iterations))
        results.append(benchmark_minute_kline(session, c2_id, args.iterations))

        print_report(results, total_rows)

    finally:
        session.close()


if __name__ == "__main__":
    main()
