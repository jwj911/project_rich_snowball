"""Executable contract for Strategy DSL condition transforms.

Transforms alter the right-hand-side indicator of a condition.  The contract
is shared by the compiler validator and backtest engine so unsupported values
cannot silently become a no-signal condition.
"""

from __future__ import annotations

import math
from typing import Any

MULTIPLY_INDICATOR2 = "multiply_indicator2"
MULTIPLY_VALUE = "multiply_value"

# ``multiply_value`` is retained for stored DSLs created before R4. New DSL
# output uses the explicit ``multiply_indicator2`` name.
SUPPORTED_TRANSFORMS = frozenset({MULTIPLY_INDICATOR2, MULTIPLY_VALUE})


class TransformContractError(ValueError):
    """Raised when a DSL transform cannot be executed deterministically."""


def validate_condition_transform(condition: dict[str, Any], *, context: str = "condition") -> None:
    """Validate a condition transform and its required parameters.

    Both supported transforms have the same deliberately narrow execution
    shape: ``indicator2 * value`` is used as the condition's right-hand side.
    ``multiply_value`` is a backwards-compatible alias; compilers emit
    ``multiply_indicator2``.
    """
    transform = condition.get("transform")
    if transform is None:
        return
    if not isinstance(transform, str) or transform not in SUPPORTED_TRANSFORMS:
        supported = ", ".join(sorted(SUPPORTED_TRANSFORMS))
        raise TransformContractError(f"{context} 不支持的 transform：{transform!r}；允许值：{supported}")
    if not condition.get("indicator2"):
        raise TransformContractError(f"{context} transform={transform} 需要 indicator2")

    _transform_multiplier(condition, context=context)


def transform_multiplier(condition: dict[str, Any], *, context: str = "condition") -> float:
    """Return the right-hand-side multiplier after validating the transform."""
    validate_condition_transform(condition, context=context)
    if condition.get("transform") is None:
        return 1.0
    return _transform_multiplier(condition, context=context)


def format_transformed_indicator2(condition: dict[str, Any]) -> str | None:
    """Render the executable RHS expression for compiler and report output."""
    if condition.get("transform") not in SUPPORTED_TRANSFORMS:
        return None
    indicator2 = condition.get("indicator2")
    value = condition.get("value")
    if not indicator2 or value is None:
        return None
    return f"{indicator2} × {value}"


def _transform_multiplier(condition: dict[str, Any], *, context: str) -> float:
    value = condition.get("value")
    if isinstance(value, bool) or value is None:
        raise TransformContractError(f"{context} transform={condition.get('transform')} 需要有限且大于 0 的数值 value")
    try:
        multiplier = float(value)
    except (TypeError, ValueError) as exc:
        raise TransformContractError(
            f"{context} transform={condition.get('transform')} 需要有限且大于 0 的数值 value"
        ) from exc
    if not math.isfinite(multiplier) or multiplier <= 0:
        raise TransformContractError(f"{context} transform={condition.get('transform')} 需要有限且大于 0 的数值 value")
    return multiplier
