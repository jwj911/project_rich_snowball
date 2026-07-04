#!/usr/bin/env python3
"""万因子精选 Top27 导入脚本。

从 factor_screening_top100.csv 读取前 27 个因子，
提取原始 .py 代码，写入 factor_definitions 表。

用法：
    cd python
    .venv/Scripts/python.exe scripts/import_wanfactor_selected.py
"""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

# 将项目根目录加入路径，确保可 import dependencies/models
# noqa: E402
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dependencies import get_db  # noqa: E402, I001
from models import FactorDefinitionDB  # noqa: E402, I001


CSV_PATH = Path("D:/Code/project_rich_snowball/factor_screening_top100.csv")
SOURCE_ROOT = Path("D:/BaiduNetdiskDownload/pack021-032")

# 字段映射：A股 -> 期货
FIELD_MAP = {
    "开盘价_复权": "open",
    "收盘价_复权": "close",
    "最高价_复权": "high",
    "最低价_复权": "low",
    "成交量": "volume",
    "成交额": "amount",
    "前收盘价": "pre_close",
}


# Pack 编号映射：长名称 -> 从1开始的连续编号
PACK_MAP = {
    "factor_pack_021": "1",
    "factor_pack_022": "2",
    "factor_pack_023": "3",
    "factor_pack_024": "4",
    "factor_pack_025": "5",
    "factor_pack_026": "6",
    "factor_pack_027": "7",
    "factor_pack_028": "8",
    "factor_pack_029": "9",
    "factor_pack_030": "10",
    "factor_pack_031": "11",
    "factor_pack_032": "12",
}


def _extract_formula_from_docstring(source_code: str) -> str | None:
    """从 docstring 中提取公式注释行。"""
    m = re.search(r'来源:\s*mining/mining\s*\|\s*公式:\s*([^\n]+)', source_code)
    return m.group(1).strip() if m else None


def _adapt_formula(formula_str: str) -> str:
    """将 A 股字段名替换为期货字段名。"""
    if not formula_str:
        return ""
    result = formula_str
    for old, new in FIELD_MAP.items():
        result = result.replace(old, new)
    return result


def _read_source_py(pack: str, factor_name: str) -> str:
    """读取因子原始 .py 文件内容。"""
    file_path = SOURCE_ROOT / pack / "因子库" / f"{factor_name}.py"
    if not file_path.exists():
        return ""
    return file_path.read_text(encoding="utf-8")


def _build_converted_formula(source_code: str) -> str:
    """从原始代码构建适配期货的 pandas 表达式摘要。"""
    m = re.search(r'def add_factor\(.*?\):(.*?)(?=\ndef |\Z)', source_code, re.DOTALL)
    if not m:
        return ""
    body = m.group(1).strip()
    for old, new in FIELD_MAP.items():
        body = body.replace(f'\"{old}\"', f'\"{new}\"')
    return body


def _extract_fields(columns_str: str) -> list[str]:
    """从 CSV columns 字段提取依赖字段列表。"""
    if not columns_str:
        return []
    fields = [f.strip() for f in columns_str.split(",")]
    return [FIELD_MAP.get(f, f) for f in fields if f]


def main() -> None:
    if not CSV_PATH.exists():
        print(f"ERROR: CSV not found: {CSV_PATH}")
        sys.exit(1)

    rows = []
    with CSV_PATH.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rank = int(row["rank"])
            if rank <= 27:
                rows.append(row)

    db = next(get_db())
    inserted = 0
    updated = 0

    try:
        for row in rows:
            pack = row["pack"]
            pkg_id = PACK_MAP.get(pack, pack)
            name = row["name"]
            category = row["category"]
            q_score = row["Q"]
            test_rankicir = row["test_rankicir"]
            monotonicity = row["monotonicity"]
            ls_sharpe = row["ls_sharpe"]
            composite_score = row["composite_score"]
            formula = row.get("formula", "")
            columns_str = row.get("columns", "")

            source_code = _read_source_py(pack, name)
            source_formula = _extract_formula_from_docstring(source_code) or formula
            converted_formula = _build_converted_formula(source_code)
            fields = _extract_fields(columns_str)

            metadata = {
                "composite_score": composite_score,
                "pack": pack,
                "formula": source_formula,
                "rank": row["rank"],
            }

            existing = db.query(FactorDefinitionDB).filter(
                FactorDefinitionDB.package_id == pkg_id,
                FactorDefinitionDB.factor_id == name,
            ).first()

            if existing:
                existing.name = name
                existing.source = "wanfactor"
                existing.category = category
                existing.q_score = float(q_score) if q_score else None
                existing.test_rankicir = float(test_rankicir) if test_rankicir else None
                existing.monotonicity = float(monotonicity) if monotonicity else None
                existing.ls_sharpe = float(ls_sharpe) if ls_sharpe else None
                existing.source_expression = source_code
                existing.converted_formula = converted_formula
                existing.conversion_status = "converted"
                existing.fields_json = json.dumps(fields, ensure_ascii=False)
                existing.metadata_json = json.dumps(metadata, ensure_ascii=False)
                existing.is_active = True
                updated += 1
            else:
                factor = FactorDefinitionDB(
                    package_id=pkg_id,
                    factor_id=name,
                    name=name,
                    source="wanfactor",
                    category=category,
                    q_score=float(q_score) if q_score else None,
                    test_rankicir=float(test_rankicir) if test_rankicir else None,
                    monotonicity=float(monotonicity) if monotonicity else None,
                    ls_sharpe=float(ls_sharpe) if ls_sharpe else None,
                    source_expression=source_code,
                    converted_formula=converted_formula,
                    conversion_status="converted",
                    fields_json=json.dumps(fields, ensure_ascii=False),
                    metadata_json=json.dumps(metadata, ensure_ascii=False),
                    is_active=True,
                )
                db.add(factor)
                inserted += 1

        db.commit()
        print(f"Done: inserted={inserted}, updated={updated}, total={inserted + updated}")
    except Exception as e:
        db.rollback()
        print(f"ERROR: {e}")
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
