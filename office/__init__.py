# __init__.py
# -*- coding: utf-8 -*-
"""office — package root (LGEOffice).

Важливе:
- Секрети (SMTP пароль, приватні пошти) НЕ тримаємо тут.
- Для SMTP використовується office/core/mail_settings.py (у .gitignore).
"""

from __future__ import annotations

from office.core.pricing import PRICE_PRO_PLUS_USD, PRICE_PRO_USD, get_price_usd

__all__ = [
    "PRICE_PRO_USD",
    "PRICE_PRO_PLUS_USD",
    "get_price_usd",
]
