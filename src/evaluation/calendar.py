from __future__ import annotations

from datetime import date
from typing import Sequence


def next_trade_date(trade_dates: Sequence[date], as_of: date) -> date:
    """Return the first supplied trading date strictly after ``as_of``."""
    for trade_date in sorted(trade_dates):
        if trade_date > as_of:
            return trade_date
    raise ValueError(f"no trade date after {as_of.isoformat()}")
