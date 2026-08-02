"""K 线 benchmark 只读契约与结构化输出测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from models import Base, ContractRolloverDB, FutContractDB, KlineDataDB, VarietyDB
from scripts import benchmark_kline


@pytest.fixture
def isolated_engine(tmp_path: Path) -> Engine:
    engine = create_engine(f"sqlite:///{tmp_path / 'benchmark.db'}")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


def _business_table_counts(engine: Engine) -> dict[str, int]:
    with Session(engine) as session:
        return {
            "contract_rollovers": session.query(ContractRolloverDB).count(),
            "fut_contracts": session.query(FutContractDB).count(),
            "kline_data": session.query(KlineDataDB).count(),
            "varieties": session.query(VarietyDB).count(),
        }


@pytest.mark.parametrize("argv", [[], ["--explain"]])
def test_empty_database_is_read_only_and_returns_nonzero(
    argv: list[str],
    isolated_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    statements: list[str] = []

    def capture_statement(
        _connection,
        _cursor,
        statement: str,
        _parameters,
        _context,
        _executemany,
    ) -> None:
        statements.append(statement.lstrip().upper())

    event.listen(isolated_engine, "before_cursor_execute", capture_statement)
    monkeypatch.setattr(benchmark_kline, "_get_engine", lambda: isolated_engine)
    before = _business_table_counts(isolated_engine)
    statements.clear()

    exit_code = benchmark_kline.main(argv)

    captured = capsys.readouterr()
    assert exit_code == benchmark_kline.EXIT_NO_BENCHMARK_DATA
    assert "benchmark_data_missing" in captured.err
    assert "--seed" in captured.err
    assert _business_table_counts(isolated_engine) == before
    write_prefixes = ("INSERT", "UPDATE", "DELETE", "CREATE", "ALTER", "DROP", "TRUNCATE")
    assert not any(statement.startswith(write_prefixes) for statement in statements)


def test_seed_requires_explicit_flag_and_creates_benchmark_data(
    isolated_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setattr(benchmark_kline, "_get_engine", lambda: isolated_engine)

    exit_code = benchmark_kline.main(["--seed", "--iterations", "1", "--json"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    counts = _business_table_counts(isolated_engine)
    assert exit_code == benchmark_kline.EXIT_SUCCESS
    assert captured.err == ""
    assert counts == {
        "contract_rollovers": 1,
        "fut_contracts": 2,
        "kline_data": benchmark_kline.TARGET_DAILY_ROWS + benchmark_kline.TARGET_MINUTE_ROWS,
        "varieties": 1,
    }
    assert payload["seeded"] is True
    assert payload["database"] == {
        "dialect": "sqlite",
        "row_count": benchmark_kline.TARGET_DAILY_ROWS + benchmark_kline.TARGET_MINUTE_ROWS,
    }


def test_production_seed_is_rejected_before_database_connection(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    def forbidden_engine():
        raise AssertionError("production seed must be rejected before connecting")

    monkeypatch.setenv("ENV", "production")
    monkeypatch.setattr(benchmark_kline, "_get_engine", forbidden_engine)

    exit_code = benchmark_kline.main(["--seed", "--json"])

    captured = capsys.readouterr()
    assert exit_code == benchmark_kline.EXIT_PRODUCTION_SEED_REFUSED
    assert captured.out == ""
    assert json.loads(captured.err) == {
        "error": {
            "code": "production_seed_refused",
            "message": "ENV=production 时禁止生成 BENCH benchmark 数据。",
        },
        "status": "error",
    }


def test_explain_cannot_be_combined_with_seed(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    def forbidden_engine():
        raise AssertionError("--explain --seed must be rejected before connecting")

    monkeypatch.setenv("ENV", "development")
    monkeypatch.setattr(benchmark_kline, "_get_engine", forbidden_engine)

    exit_code = benchmark_kline.main(["--explain", "--seed"])

    captured = capsys.readouterr()
    assert exit_code == benchmark_kline.EXIT_INVALID_ARGUMENT
    assert "seed_explain_conflict" in captured.err


def _fixed_result(scenario: str, iterations: int, p99: float) -> dict:
    return {
        "iterations": iterations,
        "max": p99,
        "mean": 20.0,
        "min": 10.0,
        "name": scenario,
        "p50": 20.1234567,
        "p95": 30.7654321,
        "p99": p99,
        "sample_count": iterations,
        "scenario": scenario,
    }


def _patch_fixed_benchmarks(
    monkeypatch: pytest.MonkeyPatch,
    dataset: benchmark_kline.BenchmarkDataset,
) -> None:
    monkeypatch.setattr(benchmark_kline, "_load_benchmark_data", lambda _session: dataset)
    benchmark_specs = (
        ("benchmark_variety_kline", "variety_kline", 40.1111111),
        ("benchmark_contract_kline", "contract_kline", 50.2222222),
        ("benchmark_main_kline", "main_contract_kline", 60.3333333),
        ("benchmark_continuous_kline", "continuous_kline", 70.4444444),
        ("benchmark_minute_kline", "minute_kline", 500.0000004),
    )
    for function_name, scenario, p99 in benchmark_specs:

        def fixed_benchmark(
            _session,
            _identifier,
            iterations,
            scenario=scenario,
            p99=p99,
        ):
            return _fixed_result(scenario, iterations, p99)

        monkeypatch.setattr(benchmark_kline, function_name, fixed_benchmark)


def test_json_output_is_stable_and_database_url_credentials_are_omitted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    password = "benchmark-password-must-not-leak"
    database_path = tmp_path / "credential-output.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path}?password={password}")
    dataset = benchmark_kline.BenchmarkDataset(
        variety_id=10,
        contract1_id=20,
        contract2_id=30,
        row_count=12345,
    )
    _patch_fixed_benchmarks(monkeypatch, dataset)

    first_exit_code = benchmark_kline.main(["--iterations", "3", "--json"])
    first_output = capsys.readouterr()
    second_exit_code = benchmark_kline.main(["--iterations", "3", "--json"])
    second_output = capsys.readouterr()

    assert first_exit_code == second_exit_code == benchmark_kline.EXIT_SUCCESS
    assert first_output.err == second_output.err == ""
    assert first_output.out == second_output.out
    assert password not in first_output.out
    assert "DATABASE_URL" not in first_output.out

    payload = json.loads(first_output.out)
    assert payload == {
        "database": {"dialect": "sqlite", "row_count": 12345},
        "duration_unit": "ms",
        "scenarios": [
            {
                "iterations": 3,
                "p50": 20.123457,
                "p95": 30.765432,
                "p99": 40.111111,
                "sample_count": 3,
                "scenario": "variety_kline",
            },
            {
                "iterations": 3,
                "p50": 20.123457,
                "p95": 30.765432,
                "p99": 50.222222,
                "sample_count": 3,
                "scenario": "contract_kline",
            },
            {
                "iterations": 3,
                "p50": 20.123457,
                "p95": 30.765432,
                "p99": 60.333333,
                "sample_count": 3,
                "scenario": "main_contract_kline",
            },
            {
                "iterations": 3,
                "p50": 20.123457,
                "p95": 30.765432,
                "p99": 70.444444,
                "sample_count": 3,
                "scenario": "continuous_kline",
            },
            {
                "iterations": 3,
                "p50": 20.123457,
                "p95": 30.765432,
                "p99": 500.0,
                "sample_count": 3,
                "scenario": "minute_kline",
            },
        ],
        "schema_version": 1,
        "seeded": False,
        "threshold": {
            "conclusion": "threshold_exceeded",
            "limit_ms": 500.0,
            "metric": "minute_kline.p99",
            "observed_ms": 500.0,
            "passed": False,
        },
    }
