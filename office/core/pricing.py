# pricing.py
# -*- coding: utf-8 -*-
"""
pricing
"""

from __future__ import annotations

PRICE_PRO_USD: float = 99.00
PRICE_PRO_PLUS_USD: float = 199.00


def get_price_usd(edition: str) -> float:
    ed = (edition or "").strip().upper()
    if ed == "PRO_PLUS":
        return float(PRICE_PRO_PLUS_USD)
    return float(PRICE_PRO_USD)
