#!/usr/bin/env python3
"""Generate a bounded, read-only CSP evidence report."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import uuid
from collections.abc import Mapping, Sequence
from contextlib import suppress
from pathlib import Path

from sqlalchemy import create_engine

PYTHON_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PYTHON_ROOT.parent
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from services.csp_evidence import (  # noqa: E402
    CSP_EVIDENCE_REPORT_MAX_BYTES,
    CspEvidenceContext,
    CspEvidenceInputCode,
    CspEvidenceProblemCode,
    CspEvidenceReport,
    CspEvidenceReportSizeError,
    CspEvidenceStatus,
    CspEvidenceValidationError,
    build_csp_evidence_failure_report,
    load_csp_evidence_context,
    load_csp_violation_catalog,
    run_csp_evidence,
)

EXIT_READY_FOR_REVIEW = 0
EXIT_INSUFFICIENT_EVIDENCE = 1
EXIT_BLOCKED = 2
EXIT_FAILED = 3
EXIT_REPORT_WRITE_FAILED = 4

_ARGUMENT_INVALID_CODE = "CSP_ARGUMENT_INVALID"
_DATABASE_URL_REQUIRED_CODE = "CSP_DATABASE_URL_REQUIRED"
_REPORT_PATH_INVALID_CODE = "CSP_REPORT_PATH_INVALID"
_REPORT_WRITE_FAILED_CODE = "CSP_REPORT_WRITE_FAILED"
_OPERATION_FAILED_CODE = "CSP_OPERATION_FAILED"
_SAFE_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]{0,127}$")
_EXIT_BY_STATUS = {
    CspEvidenceStatus.READY_FOR_REVIEW: EXIT_READY_FOR_REVIEW,
    CspEvidenceStatus.INSUFFICIENT_EVIDENCE: EXIT_INSUFFICIENT_EVIDENCE,
    CspEvidenceStatus.BLOCKED: EXIT_BLOCKED,
    CspEvidenceStatus.FAILED: EXIT_FAILED,
}


class CspEvidenceArgumentError(ValueError):
    """Raised for command-line syntax failures without retaining input text."""


class CspEvidenceReportPathError(ValueError):
    """Raised when the report destination violates the path boundary."""


class CspEvidenceDatabaseConfigurationError(ValueError):
    """Raised when neither supported database URL source is configured."""


class _SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        del message
        raise CspEvidenceArgumentError from None


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser."""
    parser = _SafeArgumentParser(description="Generate a read-only CSP evidence report")
    parser.add_argument(
        "--database-url",
        help="Database URL; falls back only to DATABASE_URL",
    )
    parser.add_argument(
        "--context-path",
        type=Path,
        required=True,
        help="Explicit CSP evidence context JSON path",
    )
    parser.add_argument(
        "--catalog-path",
        type=Path,
        required=True,
        help="Explicit known-violation catalog JSON path",
    )
    parser.add_argument(
        "--report-path",
        type=Path,
        required=True,
        help="Explicit JSON report path outside the repository",
    )
    return parser


def main(argv: Sequence[str] | None = None, environ: Mapping[str, str] | None = None) -> int:
    """Validate inputs, collect evidence, and atomically write a bounded report."""
    trace_id = uuid.uuid4().hex
    try:
        args = build_parser().parse_args(argv)
    except CspEvidenceArgumentError as exc:
        _emit_error(
            trace_id,
            status="failed",
            code=_ARGUMENT_INVALID_CODE,
            error_type=type(exc).__name__,
        )
        return EXIT_FAILED

    source_environment = os.environ if environ is None else environ
    try:
        context_path = _resolve_input_path(
            args.context_path,
            CspEvidenceInputCode.CONTEXT_READ_FAILED,
        )
        catalog_path = _resolve_input_path(
            args.catalog_path,
            CspEvidenceInputCode.CATALOG_READ_FAILED,
        )
        report_path = _validate_report_path(
            args.report_path,
            context_path=context_path,
            catalog_path=catalog_path,
        )
        context = load_csp_evidence_context(context_path)
        catalog = load_csp_violation_catalog(catalog_path)
    except CspEvidenceValidationError as exc:
        _emit_error(
            trace_id,
            status="failed",
            code=exc.code.value,
            error_type=type(exc).__name__,
        )
        return EXIT_FAILED
    except CspEvidenceReportPathError as exc:
        _emit_error(
            trace_id,
            status="failed",
            code=_REPORT_PATH_INVALID_CODE,
            error_type=type(exc).__name__,
        )
        return EXIT_FAILED

    database_url = args.database_url or source_environment.get("DATABASE_URL")
    if not isinstance(database_url, str) or not database_url:
        _emit_error(
            trace_id,
            status="failed",
            code=_DATABASE_URL_REQUIRED_CODE,
            error_type=CspEvidenceDatabaseConfigurationError.__name__,
        )
        return EXIT_FAILED

    engine = None
    try:
        engine = create_engine(database_url)
        report = run_csp_evidence(
            engine,
            context,
            catalog,
            trace_id=trace_id,
        )
    except Exception as exc:
        report = build_csp_evidence_failure_report(
            context,
            type(exc).__name__,
            trace_id=trace_id,
        )
    finally:
        if engine is not None:
            try:
                engine.dispose()
            except Exception as exc:
                report = build_csp_evidence_failure_report(
                    context,
                    type(exc).__name__,
                    trace_id=trace_id,
                )

    try:
        report, report_payload = _bounded_report_payload(report, context)
    except Exception as exc:
        _emit_error(
            trace_id,
            status="failed",
            code=CspEvidenceProblemCode.REPORT_SIZE_EXCEEDED.value,
            error_type=_safe_identifier(type(exc).__name__, "CspEvidenceReportSizeError"),
        )
        return EXIT_FAILED

    try:
        _atomic_write(report_path, report_payload)
    except Exception as exc:
        _emit_error(
            report.trace_id,
            status="report_write_failed",
            code=_REPORT_WRITE_FAILED_CODE,
            error_type=_safe_identifier(type(exc).__name__, "CspEvidenceWriteError"),
        )
        return EXIT_REPORT_WRITE_FAILED

    if report.status is CspEvidenceStatus.FAILED:
        code = report.problems[0].code.value if report.problems else _OPERATION_FAILED_CODE
        _emit_error(
            report.trace_id,
            status=report.status.value,
            code=code,
            error_type=_safe_identifier(report.error_type, "CspEvidenceError"),
        )
    else:
        _emit_summary(report)
    return _EXIT_BY_STATUS[report.status]


def _resolve_input_path(path: Path, read_code: CspEvidenceInputCode) -> Path:
    try:
        return path.expanduser().resolve(strict=False)
    except (OSError, RuntimeError, ValueError):
        raise CspEvidenceValidationError(read_code) from None


def _validate_report_path(
    path: Path,
    *,
    context_path: Path,
    catalog_path: Path,
) -> Path:
    try:
        repository_root = REPOSITORY_ROOT.resolve(strict=True)
        report_path = path.expanduser().resolve(strict=False)
    except (OSError, RuntimeError, ValueError):
        raise CspEvidenceReportPathError from None

    if (
        report_path == repository_root
        or report_path.is_relative_to(repository_root)
        or report_path in {context_path, catalog_path}
    ):
        raise CspEvidenceReportPathError
    return report_path


def _bounded_report_payload(
    report: CspEvidenceReport,
    context: CspEvidenceContext,
) -> tuple[CspEvidenceReport, bytes]:
    try:
        payload = report.to_json().encode("utf-8")
    except Exception as exc:
        report = build_csp_evidence_failure_report(
            context,
            type(exc).__name__,
            trace_id=report.trace_id,
        )
        payload = report.to_json().encode("utf-8")

    if len(payload) > CSP_EVIDENCE_REPORT_MAX_BYTES:
        report = build_csp_evidence_failure_report(
            context,
            CspEvidenceReportSizeError.__name__,
            trace_id=report.trace_id,
            problem_code=CspEvidenceProblemCode.REPORT_SIZE_EXCEEDED,
        )
        payload = report.to_json().encode("utf-8")
    if len(payload) > CSP_EVIDENCE_REPORT_MAX_BYTES:
        raise CspEvidenceReportSizeError
    return report, payload


def _atomic_write(report_path: Path, payload: bytes) -> None:
    descriptor: int | None = None
    temporary_path: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            dir=report_path.parent,
            prefix=f".{report_path.name}.",
            suffix=".tmp",
        )
        temporary_path = Path(temporary_name)
        _set_private_mode(descriptor, temporary_path)
        with os.fdopen(descriptor, "wb") as report_file:
            descriptor = None
            report_file.write(payload)
            report_file.flush()
            os.fsync(report_file.fileno())
        os.replace(temporary_path, report_path)
        temporary_path = None
    finally:
        if descriptor is not None:
            with suppress(OSError):
                os.close(descriptor)
        if temporary_path is not None:
            with suppress(OSError):
                temporary_path.unlink(missing_ok=True)


def _set_private_mode(descriptor: int, path: Path) -> None:
    if hasattr(os, "fchmod"):
        try:
            os.fchmod(descriptor, 0o600)
            return
        except NotImplementedError:
            pass
    with suppress(NotImplementedError):
        os.chmod(path, 0o600)


def _emit_summary(report: CspEvidenceReport) -> None:
    print(
        json.dumps(
            {
                "trace_id": report.trace_id,
                "status": report.status.value,
                "counts": report.counts.to_dict(),
            },
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
    )


def _emit_error(trace_id: str, *, status: str, code: str, error_type: str) -> None:
    print(
        json.dumps(
            {
                "trace_id": trace_id,
                "status": status,
                "code": _safe_identifier(code, _OPERATION_FAILED_CODE),
                "error_type": _safe_identifier(error_type, "CspEvidenceError"),
            },
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ),
        file=sys.stderr,
    )


def _safe_identifier(value: str | None, fallback: str) -> str:
    if isinstance(value, str) and _SAFE_IDENTIFIER_PATTERN.fullmatch(value):
        return value
    return fallback


if __name__ == "__main__":
    raise SystemExit(main())
