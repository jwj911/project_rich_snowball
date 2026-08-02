r"""K 线查询性能基准测试。

用法：
    # 只读基准测试（要求数据库中已有 BENCH 数据）
    cd python
    $env:DATABASE_URL="postgresql://futures:futures123@localhost:15432/futures_community"
    .\venv\Scripts\python.exe scripts\benchmark_kline.py

    # 仅在非生产隔离数据库中显式生成 BENCH 数据
    .\venv\Scripts\python.exe scripts\benchmark_kline.py --seed

    # 输出稳定 JSON
    .\venv\Scripts\python.exe scripts\benchmark_kline.py --json

前置条件：
    - 数据库已启动且可连接
    - alembic upgrade head 已执行
    - 默认模式和 --explain 均不会写入数据库
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

# 将项目根目录加入路径，以便导入 models
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from models import (
    ContractRolloverDB,
    FutContractDB,
    KlineDataDB,
    VarietyDB,
)
from services.continuous_kline import get_continuous_kline, get_main_contract_kline

BENCHMARK_SYMBOL = "BENCH"
BENCHMARK_CONTRACT_CODE = "BENCH2401"
BENCHMARK_CONTRACT_CODE_2 = "BENCH2405"
DEFAULT_DATABASE_URL = "sqlite:///./futures_community.db"
MINUTE_P99_THRESHOLD_MS = 500.0
TARGET_DAILY_ROWS = 365
TARGET_MINUTE_ROWS = 90 * 240

EXIT_SUCCESS = 0
EXIT_NO_BENCHMARK_DATA = 1
EXIT_INVALID_ARGUMENT = 2
EXIT_DATABASE_ERROR = 3
EXIT_PRODUCTION_SEED_REFUSED = 4


@dataclass(frozen=True)
class BenchmarkDataset:
    """已存在的 BENCH 数据标识和规模。"""

    variety_id: int
    contract1_id: int
    contract2_id: int
    row_count: int


class BenchmarkDataError(RuntimeError):
    """BENCH 数据缺失或不完整。"""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _get_engine():
    database_url = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
    return create_engine(database_url, echo=False, pool_pre_ping=True)


def _load_benchmark_data(session: Session) -> BenchmarkDataset:
    """只读查找完整 BENCH 数据；缺失时给出稳定错误。"""
    variety = session.query(VarietyDB).filter(VarietyDB.symbol == BENCHMARK_SYMBOL).first()
    if variety is None:
        raise BenchmarkDataError(
            "benchmark_data_missing",
            "未找到 BENCH benchmark 数据；请在非生产隔离数据库中显式使用 --seed。",
        )

    c1 = session.query(FutContractDB).filter(FutContractDB.symbol == BENCHMARK_CONTRACT_CODE).first()
    c2 = session.query(FutContractDB).filter(FutContractDB.symbol == BENCHMARK_CONTRACT_CODE_2).first()
    if c1 is None or c2 is None:
        raise BenchmarkDataError(
            "benchmark_data_incomplete",
            "BENCH benchmark 合约数据不完整；请检查隔离数据库或显式使用 --seed。",
        )

    row_count = session.query(KlineDataDB).filter(KlineDataDB.variety_id == variety.id).count()
    contract1_daily_count = (
        session.query(KlineDataDB)
        .filter(
            KlineDataDB.variety_id == variety.id,
            KlineDataDB.contract_id == c1.id,
            KlineDataDB.period == "D",
        )
        .count()
    )
    contract2_minute_count = (
        session.query(KlineDataDB)
        .filter(
            KlineDataDB.variety_id == variety.id,
            KlineDataDB.contract_id == c2.id,
            KlineDataDB.period == "1m",
        )
        .count()
    )
    if row_count == 0 or contract1_daily_count == 0 or contract2_minute_count == 0:
        raise BenchmarkDataError(
            "benchmark_data_incomplete",
            "BENCH benchmark K 线数据不完整，至少需要首个合约日线和第二个合约分钟线。",
        )

    return BenchmarkDataset(
        variety_id=variety.id,
        contract1_id=c1.id,
        contract2_id=c2.id,
        row_count=row_count,
    )


def _seed_benchmark_data(session: Session) -> bool:
    """在显式 seed 模式下生成隔离 BENCH 数据，返回是否新增了数据。"""
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

    c1 = session.query(FutContractDB).filter(FutContractDB.symbol == BENCHMARK_CONTRACT_CODE).first()
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

    c2 = session.query(FutContractDB).filter(FutContractDB.symbol == BENCHMARK_CONTRACT_CODE_2).first()
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
    existing_count = session.query(KlineDataDB).filter(KlineDataDB.variety_id == variety.id).count()

    target_rows = TARGET_DAILY_ROWS + TARGET_MINUTE_ROWS
    if existing_count == 0:
        _generate_klines(session, variety.id, c1.id, c2.id)
    elif existing_count < target_rows:
        raise BenchmarkDataError(
            "benchmark_seed_partial_data",
            f"BENCH 已有 {existing_count} 条 K 线，少于目标 {target_rows} 条；拒绝覆盖或混合部分数据。",
        )

    changed = bool(session.new)
    session.commit()
    return changed


def _generate_klines(session: Session, variety_id: int, c1_id: int, c2_id: int) -> None:
    """生成 1 年日线 + 3 个月分钟线模拟数据。"""
    base_price = Decimal("5000.0")
    volume_base = 10000

    # 1 年日线（c1: Jan-Apr, c2: May-Dec）
    start_date = datetime(2024, 1, 1, tzinfo=UTC)
    for i in range(TARGET_DAILY_ROWS):
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
    for i in range(TARGET_MINUTE_ROWS):
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


def _summarize_timings(scenario: str, name: str, times: list[float], iterations: int) -> dict:
    """生成各查询场景共用的统计结构。"""
    times.sort()
    return {
        "scenario": scenario,
        "name": name,
        "iterations": iterations,
        "sample_count": len(times),
        "p50": _percentile(times, 50),
        "p95": _percentile(times, 95),
        "p99": _percentile(times, 99),
        "min": min(times),
        "max": max(times),
        "mean": statistics.mean(times),
    }


def benchmark_variety_kline(session: Session, variety_id: int, iterations: int = 20) -> dict:
    """测试品种 K 线查询（等价于 GET /api/klines/{symbol}）。"""
    times = []
    for _ in range(iterations):
        _, ms = _timeit(
            lambda: (
                session.query(KlineDataDB)
                .filter(KlineDataDB.variety_id == variety_id, KlineDataDB.period == "D")
                .order_by(KlineDataDB.trading_time.desc())
                .limit(100)
                .all()
            )
        )
        times.append(ms)
    return _summarize_timings(
        "variety_kline",
        "variety_kline (D, limit=100)",
        times,
        iterations,
    )


def benchmark_contract_kline(session: Session, contract_id: int, iterations: int = 20) -> dict:
    """测试合约 K 线查询（等价于 GET /api/contracts/{id}/kline）。"""
    times = []
    for _ in range(iterations):
        _, ms = _timeit(
            lambda: (
                session.query(KlineDataDB)
                .filter(KlineDataDB.contract_id == contract_id, KlineDataDB.period == "D")
                .order_by(KlineDataDB.trading_time.asc())
                .limit(500)
                .all()
            )
        )
        times.append(ms)
    return _summarize_timings(
        "contract_kline",
        "contract_kline (D, limit=500)",
        times,
        iterations,
    )


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
    return _summarize_timings(
        "continuous_kline",
        "continuous_kline (D, limit=500, backward)",
        times,
        iterations,
    )


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
    return _summarize_timings(
        "main_contract_kline",
        "main_contract_kline (D, limit=500)",
        times,
        iterations,
    )


def benchmark_minute_kline(session: Session, contract_id: int, iterations: int = 20) -> dict:
    """测试分钟 K 线查询（1m 周期，大量数据）。"""
    times = []
    for _ in range(iterations):
        _, ms = _timeit(
            lambda: (
                session.query(KlineDataDB)
                .filter(KlineDataDB.contract_id == contract_id, KlineDataDB.period == "1m")
                .order_by(KlineDataDB.trading_time.asc())
                .limit(5000)
                .all()
            )
        )
        times.append(ms)
    return _summarize_timings(
        "minute_kline",
        "minute_kline (1m, limit=5000)",
        times,
        iterations,
    )


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
        print(f"\n{'=' * 60}")
        print(f"EXPLAIN ANALYZE: {name}")
        print("=" * 60)
        result = session.execute(text(sql), params)
        for row in result:
            print(row[0])


def _build_json_report(
    results: list[dict],
    dialect: str,
    row_count: int,
    seeded: bool,
) -> dict:
    """构建不含连接凭据和运行时间的稳定 JSON 报告。"""
    scenarios = [
        {
            "iterations": result["iterations"],
            "p50": round(result["p50"], 6),
            "p95": round(result["p95"], 6),
            "p99": round(result["p99"], 6),
            "sample_count": result["sample_count"],
            "scenario": result["scenario"],
        }
        for result in results
    ]
    minute_result = next(result for result in scenarios if result["scenario"] == "minute_kline")
    raw_minute_result = next(result for result in results if result["scenario"] == "minute_kline")
    minute_p99 = minute_result["p99"]
    threshold_passed = raw_minute_result["p99"] <= MINUTE_P99_THRESHOLD_MS
    return {
        "database": {
            "dialect": dialect,
            "row_count": row_count,
        },
        "duration_unit": "ms",
        "scenarios": scenarios,
        "schema_version": 1,
        "seeded": seeded,
        "threshold": {
            "conclusion": "within_threshold" if threshold_passed else "threshold_exceeded",
            "limit_ms": MINUTE_P99_THRESHOLD_MS,
            "metric": "minute_kline.p99",
            "observed_ms": minute_p99,
            "passed": threshold_passed,
        },
    }


def print_report(results: list[dict], dialect: str, row_count: int, seeded: bool) -> None:
    print(f"\n{'=' * 60}")
    print("K 线查询性能基准测试报告")
    print("=" * 60)
    print(f"数据库方言: {dialect}")
    print(f"测试时间: {datetime.now(UTC).isoformat()}")
    print(f"BENCH K 线数据量: {row_count} 条")
    print(f"本次生成数据: {'是' if seeded else '否'}")
    print(f"{'-' * 60}")

    for r in results:
        print(f"\n场景: {r['name']}")
        print(f"  迭代次数: {r['iterations']}")
        print(f"  样本数:   {r['sample_count']}")
        print(f"  p50:    {r['p50']:8.3f} ms")
        print(f"  p95:    {r['p95']:8.3f} ms")
        print(f"  p99:    {r['p99']:8.3f} ms")
        print(f"  mean:   {r['mean']:8.3f} ms")
        print(f"  min:    {r['min']:8.3f} ms")
        print(f"  max:    {r['max']:8.3f} ms")

    minute_result = next(result for result in results if result["scenario"] == "minute_kline")
    threshold_passed = minute_result["p99"] <= MINUTE_P99_THRESHOLD_MS
    print(f"\n{'=' * 60}")
    print("整体阈值结论（基于 minute_kline p99）:")
    print(f"  - 阈值: {MINUTE_P99_THRESHOLD_MS:.0f} ms")
    print(f"  - 实测: {minute_result['p99']:.3f} ms")
    print(f"  - 结论: {'通过' if threshold_passed else '超过阈值'}")
    print("=" * 60)


def _emit_error(code: str, message: str, json_output: bool) -> None:
    """输出不包含异常详情或数据库连接串的稳定错误。"""
    if json_output:
        print(
            json.dumps(
                {
                    "error": {
                        "code": code,
                        "message": message,
                    },
                    "status": "error",
                },
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return
    print(f"[benchmark] ERROR {code}: {message}", file=sys.stderr)


def build_parser() -> argparse.ArgumentParser:
    """创建 benchmark 命令行参数解析器。"""
    parser = argparse.ArgumentParser(description="K 线查询性能基准测试")
    parser.add_argument("--explain", action="store_true", help="只输出 EXPLAIN ANALYZE，不跑多轮计时")
    parser.add_argument("--iterations", type=int, default=20, help="每场景迭代次数（默认 20）")
    parser.add_argument("--json", action="store_true", help="输出稳定 JSON 报告")
    parser.add_argument("--seed", action="store_true", help="在非生产隔离数据库中显式生成 BENCH 数据")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """运行 benchmark 并返回稳定退出码。"""
    args = build_parser().parse_args(argv)

    if args.seed and os.getenv("ENV", "development").strip().lower() == "production":
        _emit_error(
            "production_seed_refused",
            "ENV=production 时禁止生成 BENCH benchmark 数据。",
            args.json,
        )
        return EXIT_PRODUCTION_SEED_REFUSED
    if args.seed and args.explain:
        _emit_error(
            "seed_explain_conflict",
            "--explain 必须保持只读，不能与 --seed 同时使用。",
            args.json,
        )
        return EXIT_INVALID_ARGUMENT
    if args.iterations <= 0:
        _emit_error(
            "invalid_iterations",
            "--iterations 必须是大于 0 的整数。",
            args.json,
        )
        return EXIT_INVALID_ARGUMENT

    try:
        engine = _get_engine()
    except SQLAlchemyError as exc:
        _emit_error("database_connection_failed", f"无法创建数据库引擎（{type(exc).__name__}）。", args.json)
        return EXIT_DATABASE_ERROR

    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    seeded = False

    try:
        if args.seed:
            seeded = _seed_benchmark_data(session)
        dataset = _load_benchmark_data(session)

        if args.explain:
            run_explain(session, dataset.variety_id, dataset.contract1_id)
            return EXIT_SUCCESS

        if not args.json:
            print(f"[benchmark] 开始测试，每场景 {args.iterations} 轮 ...\n")

        results = []
        results.append(benchmark_variety_kline(session, dataset.variety_id, args.iterations))
        results.append(benchmark_contract_kline(session, dataset.contract1_id, args.iterations))
        results.append(benchmark_main_kline(session, dataset.variety_id, args.iterations))
        results.append(benchmark_continuous_kline(session, dataset.variety_id, args.iterations))
        results.append(benchmark_minute_kline(session, dataset.contract2_id, args.iterations))

        if args.json:
            report = _build_json_report(
                results,
                dialect=engine.dialect.name,
                row_count=dataset.row_count,
                seeded=seeded,
            )
            print(
                json.dumps(
                    report,
                    ensure_ascii=True,
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
        else:
            print_report(
                results,
                dialect=engine.dialect.name,
                row_count=dataset.row_count,
                seeded=seeded,
            )
        return EXIT_SUCCESS
    except BenchmarkDataError as exc:
        session.rollback()
        _emit_error(exc.code, str(exc), args.json)
        return EXIT_NO_BENCHMARK_DATA
    except SQLAlchemyError as exc:
        session.rollback()
        _emit_error("database_operation_failed", f"数据库操作失败（{type(exc).__name__}）。", args.json)
        return EXIT_DATABASE_ERROR
    finally:
        session.close()
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
