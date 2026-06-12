"""Small formatting helpers shared by dashboard.py and visualisation.py.

These were previously copy-pasted (byte-for-byte) into both files; keeping a
single definition here avoids the two drifting apart.
"""
from __future__ import annotations

import math
from typing import Any


def safe_float(value: Any, default: float = math.nan) -> float:
    """Coerce a value to float, returning `default` for None/blank/NaN inputs."""
    try:
        output = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(output):
        return default
    return output


def seconds_to_clock(seconds: float) -> str:
    """Format a simulation time (seconds since midnight) as a 'HH:MM' clock string."""
    if not math.isfinite(float(seconds)):
        return ''
    total = int(round(float(seconds)))
    hours = (total // 3600) % 24
    minutes = (total % 3600) // 60
    return f'{hours:02d}:{minutes:02d}'
