# app_meta.py
"""
Центральні метадані та константи застосунку LGE.

Тут зібрано:
- метадані програми
- trial/pricing константи
- seller/payment реквізити
- публічні параметри ліцензії

Не зберігати тут приватні ключі.
"""

from __future__ import annotations

APP_NAME = "LGE"
PRODUCT_NAME = "LGE — ATS"
VERSION = "1.0.1"

AUTHOR = "Lavruk Yurii (Лаврук Юрій)"
ASSISTANT_NAME = "GPT Еон"
YEAR = "2025"
EMAIL = "yure144@gmail.com"

TESTED_OS = [
    "Windows 11 (tested)",
    "Windows 10 (expected)",
]

COMMENT = (
    "Проєкт розвивається поетапно. "
    "Ключовий принцип: контрольована система, мінімум сміття, максимум прозорості."
)

# Trial / pricing
CURRENCY = "USD"
TRIAL_DAYS = 90
TRIAL_WARN_BEFORE_EXPIRY_DAYS = 7
PRICE_PRO_USD = 99.00
PRICE_PROPLUS_USD = 199.00

# Seller / Payment
SELLER_NAME = "Lavruk Yurii"
SELLER_COUNTRY = "Ukraina"
SELLER_SALES_EMAIL = "erclavr@gmail.com"
PAYMENT_METHOD_TITLE = "Card/Bank transfer"
PAYMENT_RECIPIENT = "Lavruk Yurii"
PAYMENT_CARD_OR_IBAN = "1111 2222 3333 4444"
PAYMENT_BANK_NAME = "a-bank"
PAYMENT_SWIFT = ""
PAYMENT_REFERENCE_PREFIX = "LGE"

# License crypto (public metadata only)
LICENSE_SIG_ALG = "ed25519"
LICENSE_KEY_ID = "ed25519-main-2026-01"
LICENSE_PUBLIC_KEY_B64 = ""


def get_app_title() -> str:
    """Повернути коротку назву продукту для UI."""
    return f"{APP_NAME} {VERSION}"


def calculate_license_price(
    current_edition: str | None,
    target_edition: str,
) -> float:
    """Порахувати ціну ліцензії або upgrade."""

    cur = (current_edition or "").lower()
    tgt = (target_edition or "").lower()

    if cur in ("", "none", "trial", "free"):
        if tgt == "pro":
            return PRICE_PRO_USD

        if tgt in ("pro_plus", "pro+"):
            return PRICE_PROPLUS_USD

    if cur == "pro" and tgt in ("pro_plus", "pro+"):
        return PRICE_PROPLUS_USD - PRICE_PRO_USD

    return 0.0
