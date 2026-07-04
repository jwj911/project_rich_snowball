"""Import WanFactor factor packs into the local factor definition table.

The importer keeps every manifest row. Expressions that can be represented by
the current agent factor DSL are stored in converted_formula; the rest are
stored with conversion_status=unsupported and a reason for later expansion.
"""

from __future__ import annotations

import argparse
import ast
import csv
import json
import re
import sys
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from models import FactorDefinitionDB, SessionLocal  # noqa: E402
from services.agent.factor_engine.dsl import validate_factor_formula  # noqa: E402


SUPPORTED_FIELDS = {"open", "high", "low", "close", "volume"}
SUPPORTED_DIRECT_FUNCTIONS = {
    "ema",
    "ts_dema",
    "ts_mean",
    "ts_std",
    "ts_sum",
    "ts_median",
    "ts_max",
    "ts_min",
    "ts_midpoint",
    "ts_inverse_cv",
    "ts_maxmin",
    "ts_mean_return",
    "ts_skew",
    "ts_kurt",
    "ts_rank",
    "ts_zscore",
    "ts_corr",
    "ts_cov",
    "ts_regression_beta",
    "rank",
    "sign",
    "abs",
    "sqrt",
    "exp",
    "clip",
}
CALL_FUNCTIONS = {
    "add",
    "sub",
    "mul",
    "div",
    "neg",
    "log",
    "delay",
    "delta",
    "ts_pct_change",
    "signed_power",
    "zscore",
    *SUPPORTED_DIRECT_FUNCTIONS,
}


class UnsupportedExpression(ValueError):
    """Raised when a pack expression needs fields or operators the agent cannot evaluate yet."""


@dataclass
class ConversionResult:
    formula: str | None
    status: str
    error: str | None
    fields: list[str]
    category: str | None


class FactorExpressionConverter(ast.NodeVisitor):
    """Convert select-stock-pro-style expressions into the local safe factor DSL."""

    def __init__(self) -> None:
        self.fields: set[str] = set()

    def convert(self, expression: str) -> str:
        tree = ast.parse(expression, mode="eval")
        formula = self.visit(tree.body)
        validate_factor_formula(formula)
        return formula

    def visit_Name(self, node: ast.Name) -> str:  # noqa: N802
        name = node.id
        if name in CALL_FUNCTIONS:
            return name
        if name in SUPPORTED_FIELDS:
            self.fields.add(name)
            return name
        derived = self._convert_derived_field(name)
        if derived is not None:
            return derived
        raise UnsupportedExpression(f"unsupported field: {name}")

    def visit_Constant(self, node: ast.Constant) -> str:  # noqa: N802
        if isinstance(node.value, (int, float)):
            return repr(node.value)
        raise UnsupportedExpression(f"unsupported constant: {node.value!r}")

    def visit_UnaryOp(self, node: ast.UnaryOp) -> str:  # noqa: N802
        value = self.visit(node.operand)
        if isinstance(node.op, ast.USub):
            return f"(-({value}))"
        if isinstance(node.op, ast.UAdd):
            return f"(+({value}))"
        raise UnsupportedExpression(f"unsupported unary operator: {type(node.op).__name__}")

    def visit_BinOp(self, node: ast.BinOp) -> str:  # noqa: N802
        left = self.visit(node.left)
        right = self.visit(node.right)
        op = {
            ast.Add: "+",
            ast.Sub: "-",
            ast.Mult: "*",
            ast.Div: "/",
            ast.Pow: "**",
            ast.Mod: "%",
        }.get(type(node.op))
        if op is None:
            raise UnsupportedExpression(f"unsupported binary operator: {type(node.op).__name__}")
        return f"(({left}) {op} ({right}))"

    def visit_Call(self, node: ast.Call) -> str:  # noqa: N802
        if not isinstance(node.func, ast.Name):
            raise UnsupportedExpression("only simple function calls are supported")
        func = node.func.id
        args = [self.visit(arg) for arg in node.args]
        kwargs = {kw.arg: self.visit(kw.value) for kw in node.keywords if kw.arg}

        if func == "add":
            return self._binary_func(func, args, "+")
        if func == "sub":
            return self._binary_func(func, args, "-")
        if func == "mul":
            return self._binary_func(func, args, "*")
        if func == "div":
            return self._binary_func(func, args, "/")
        if func == "neg":
            self._require_arg_count(func, args, 1)
            return f"(-({args[0]}))"
        if func == "log":
            self._require_arg_count(func, args, 1)
            # Pack log is signed log1p(abs(x)); this preserves that behavior with current DSL ops.
            return f"(sign({args[0]}) * log(1 + abs({args[0]})))"
        if func == "delay":
            self._require_arg_count(func, args, 2)
            return f"ts_delay({args[0]}, {args[1]})"
        if func == "delta":
            if len(args) == 1:
                return f"ts_delta({args[0]}, 1)"
            self._require_arg_count(func, args, 2)
            return f"ts_delta({args[0]}, {args[1]})"
        if func == "ts_pct_change":
            self._require_arg_count(func, args, 2)
            return f"(ts_delta({args[0]}, {args[1]}) / abs({args[0]}))"
        if func == "signed_power":
            exponent = kwargs.get("exponent")
            if exponent is None and len(args) == 2:
                exponent = args[1]
            self._require_at_least(func, args, 1)
            if exponent is None:
                raise UnsupportedExpression("signed_power requires exponent")
            return f"(sign({args[0]}) * (abs({args[0]}) ** {exponent}))"
        if func == "zscore":
            if len(args) == 1:
                return f"zscore({args[0]})"
            self._require_arg_count(func, args, 2)
            return f"ts_zscore({args[0]}, {args[1]})"
        if func in SUPPORTED_DIRECT_FUNCTIONS:
            return f"{func}({', '.join(args)})"

        raise UnsupportedExpression(f"unsupported function: {func}")

    def generic_visit(self, node: ast.AST) -> str:
        raise UnsupportedExpression(f"unsupported syntax: {type(node).__name__}")

    def _convert_derived_field(self, name: str) -> str | None:
        ret_match = re.fullmatch(r"ret_(\d+)", name)
        if ret_match:
            window = ret_match.group(1)
            self.fields.add("close")
            return f"((close / ts_delay(close, {window})) - 1)"

        if name == "intraday_range":
            self.fields.update({"high", "low", "close"})
            return "((high - low) / close)"
        if name == "amplitude":
            self.fields.update({"high", "low", "close"})
            return "((high - low) / close)"
        if name == "gap":
            self.fields.update({"open", "close"})
            return "((open / ts_delay(close, 1)) - 1)"

        return None

    @staticmethod
    def _require_arg_count(func: str, args: list[str], count: int) -> None:
        if len(args) != count:
            raise UnsupportedExpression(f"{func} expects {count} args, got {len(args)}")

    @staticmethod
    def _require_at_least(func: str, args: list[str], count: int) -> None:
        if len(args) < count:
            raise UnsupportedExpression(f"{func} expects at least {count} args, got {len(args)}")

    @staticmethod
    def _binary_func(func: str, args: list[str], operator: str) -> str:
        if len(args) < 2:
            raise UnsupportedExpression(f"{func} expects at least 2 args, got {len(args)}")
        expr = args[0]
        for arg in args[1:]:
            expr = f"(({expr}) {operator} ({arg}))"
        return expr


def convert_expression(expression: str) -> ConversionResult:
    converter = FactorExpressionConverter()
    try:
        formula = converter.convert(expression)
    except Exception as exc:
        return ConversionResult(
            formula=None,
            status="unsupported",
            error=str(exc),
            fields=sorted(converter.fields),
            category=infer_category(expression),
        )
    return ConversionResult(
        formula=formula,
        status="converted",
        error=None,
        fields=sorted(converter.fields),
        category=infer_category(expression),
    )


def infer_category(expression: str) -> str:
    expr = expression.lower()
    if "volume" in expr or "amount" in expr or "turnover" in expr:
        return "volume_price"
    if "std" in expr or "amplitude" in expr or "intraday_range" in expr or "maxmin" in expr:
        return "volatility"
    if "ret_" in expr or "pct_change" in expr or "delta" in expr or "gap" in expr:
        return "momentum"
    if "market_cap" in expr or "fund" in expr:
        return "fundamental"
    return "technical"


def extract_constant(source: str, name: str) -> str | None:
    match = re.search(rf"^{name}\s*=\s*['\"]([^'\"]+)['\"]", source, flags=re.MULTILINE)
    return match.group(1) if match else None


def decimal_or_none(value: str | None) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(value)
    except (InvalidOperation, ValueError):
        return None


def bool_from_int(value: str | None) -> bool:
    return value == "1" or str(value).lower() == "true"


def build_factor_payload(row: dict[str, str], factor_dir: Path, package_fallback: str) -> dict[str, Any]:
    name = row["name"]
    source_path = factor_dir / f"{name}.py"
    source_text = source_path.read_text(encoding="utf-8", errors="replace") if source_path.exists() else ""

    expression = row.get("expression") or ""
    converted = convert_expression(expression)
    package_id = extract_constant(source_text, "WANFACTOR_PACKAGE_ID") or package_fallback
    factor_id = extract_constant(source_text, "WANFACTOR_FACTOR_ID") or row.get("id") or name
    watermark_sig = extract_constant(source_text, "WANFACTOR_SIG")
    metadata = {
        "manifest_name": name,
        "manifest_id": row.get("id"),
        "source_exists": source_path.exists(),
    }

    return {
        "package_id": package_id,
        "factor_id": factor_id,
        "name": name,
        "source": row.get("source"),
        "cluster_id": row.get("cluster_id"),
        "is_cluster_rep": bool_from_int(row.get("is_cluster_rep")),
        "q_score": decimal_or_none(row.get("Q")),
        "rankic": decimal_or_none(row.get("rankic")),
        "rankicir": decimal_or_none(row.get("rankicir")),
        "test_rankicir": decimal_or_none(row.get("test_rankicir")),
        "monotonicity": decimal_or_none(row.get("monotonicity")),
        "ls_sharpe": decimal_or_none(row.get("ls_sharpe")),
        "size_corr": decimal_or_none(row.get("size_corr")),
        "coverage": decimal_or_none(row.get("coverage")),
        "source_expression": expression,
        "converted_formula": converted.formula,
        "conversion_status": converted.status,
        "conversion_error": converted.error,
        "category": converted.category,
        "fields_json": json.dumps(converted.fields, ensure_ascii=False),
        "metadata_json": json.dumps(metadata, ensure_ascii=False),
        "watermark_sig": watermark_sig,
        "source_file": str(source_path) if source_path.exists() else None,
        "is_active": True,
    }


def iter_manifest_rows(manifest_path: Path, limit: int | None) -> Any:
    with manifest_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        for index, row in enumerate(reader):
            if limit is not None and index >= limit:
                break
            yield row


def upsert_factor(session, payload: dict[str, Any]) -> str:
    row = (
        session.query(FactorDefinitionDB)
        .filter(
            FactorDefinitionDB.package_id == payload["package_id"],
            FactorDefinitionDB.factor_id == payload["factor_id"],
        )
        .first()
    )
    if row is None:
        session.add(FactorDefinitionDB(**payload))
        return "inserted"

    for key, value in payload.items():
        setattr(row, key, value)
    return "updated"


def import_pack(args: argparse.Namespace) -> dict[str, int]:
    pack_dir = args.pack_dir.resolve()
    manifest_path = args.manifest.resolve() if args.manifest else pack_dir / "manifest.csv"
    factor_dir = args.factor_dir.resolve() if args.factor_dir else pack_dir / "因子库"
    package_fallback = pack_dir.name

    if not manifest_path.exists():
        raise FileNotFoundError(f"manifest not found: {manifest_path}")
    if not factor_dir.exists():
        raise FileNotFoundError(f"factor dir not found: {factor_dir}")

    stats = {"seen": 0, "converted": 0, "unsupported": 0, "inserted": 0, "updated": 0}
    session = SessionLocal()
    try:
        for row in iter_manifest_rows(manifest_path, args.limit):
            payload = build_factor_payload(row, factor_dir, package_fallback)
            stats["seen"] += 1
            stats[payload["conversion_status"]] += 1
            if args.dry_run:
                continue

            action = upsert_factor(session, payload)
            stats[action] += 1
            if stats["seen"] % args.batch_size == 0:
                session.commit()
                print(f"committed {stats['seen']} rows...")

        if not args.dry_run:
            session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    return stats


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import a WanFactor factor pack into factor_definitions.")
    parser.add_argument("--pack-dir", type=Path, required=True, help="Path containing README.md, manifest.csv and 因子库/")
    parser.add_argument("--manifest", type=Path, default=None, help="Override manifest.csv path")
    parser.add_argument("--factor-dir", type=Path, default=None, help="Override 因子库 path")
    parser.add_argument("--limit", type=int, default=None, help="Import only the first N manifest rows")
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--dry-run", action="store_true", help="Parse and convert without writing to the database")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    stats = import_pack(args)
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
