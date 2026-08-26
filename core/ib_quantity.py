# ib_quantity.py
"""
Нормалізація quantity для Interactive Brokers.

IB quantity залежить від типу інструмента:
- STK: shares
- CASH: FX units
- FUT: contracts
- OPT: contracts
"""

from __future__ import annotations


def normalize_ib_quantity(sec_type: str, quantity: float) -> float:
    """Нормалізувати quantity для IB за типом інструмента."""
    sec_type = sec_type.strip().upper()

    if sec_type in {"STK", "FUT", "OPT"}:
        return max(1, int(round(quantity)))

    if sec_type == "CASH":
        return float(quantity)

    if quantity <= 0:
        raise ValueError("IB quantity must be positive.")

    return float(quantity)
