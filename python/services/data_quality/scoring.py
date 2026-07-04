"""数据质量评分规则。"""

from __future__ import annotations

from services.data_quality.types import DataQualityIssue, QualityStatus


def score_issues(issues: list[DataQualityIssue]) -> tuple[QualityStatus, int]:
    """根据问题严重程度生成状态和 0-100 健康分。"""
    score = 100
    has_bad = False
    has_warning = False

    for issue in issues:
        if issue.severity == "bad":
            score -= 30
            has_bad = True
        elif issue.severity == "warning":
            score -= 12
            has_warning = True
        else:
            score -= 3

    score = max(0, min(100, score))
    if has_bad or score < 60:
        return "bad", score
    if has_warning or score < 85:
        return "warning", score
    return "good", score
