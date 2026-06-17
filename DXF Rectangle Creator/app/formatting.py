from __future__ import annotations


def format_dim(value: float) -> str:
    """Format a dimension value; omit trailing .0 for whole numbers."""
    rounded = round(value)
    if abs(value - rounded) < 1e-9:
        return str(int(rounded))
    return f"{value:.1f}"
