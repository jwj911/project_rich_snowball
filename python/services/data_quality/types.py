"""数据质量服务的结构化类型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

QualityStatus = Literal["good", "warning", "bad"]
IssueSeverity = Literal["info", "warning", "bad"]


@dataclass
class DataQualityIssue:
    """单个数据质量问题。"""

    severity: IssueSeverity
    code: str
    message: str
    sample: list[Any] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "sample": self.sample,
        }


@dataclass
class DataQualityReport:
    """固定结构的数据质量报告。"""

    scope: dict[str, Any]
    status: QualityStatus
    score: int
    coverage: dict[str, Any]
    issues: list[DataQualityIssue] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    datasets: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scope": self.scope,
            "status": self.status,
            "score": self.score,
            "coverage": self.coverage,
            "issues": [issue.to_dict() for issue in self.issues],
            "recommendations": self.recommendations,
            "datasets": self.datasets,
        }
