"""Safe calculator engine for arithmetic expressions using AST parsing. Qt-free."""
from __future__ import annotations

from .modes import (
    CalcResult, calculate, format_number,
    ALLOWED_FUNCTIONS, ALLOWED_CONSTANTS,
)

__all__ = [
    "CalcResult", "calculate", "format_number",
    "ALLOWED_FUNCTIONS", "ALLOWED_CONSTANTS",
]
