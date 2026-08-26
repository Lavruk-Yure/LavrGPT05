# license_status.py
"""
Канонічні стани ліцензії LGE і допоміжна логіка для їх читання.

Поточна модель RoadMap58:
1. Free без activated_at -> NO_LICENSE.
2. Free з activated_at і валідним строком -> TRIAL_OK.
3. Free після завершення trial -> TRIAL_EXPIRED.
4. PRO і PRO+ безстрокові, валідний комерційний стан -> PRO_OK.
5. Окремо лишаємо службові/помилкові стани:
   - OTHER_MACHINE
   - EXPIRED
   - UPDATE_REQUIRED
   - TAMPERED
   - CLOCK_ROLLBACK
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from core.app_meta import TRIAL_DAYS, TRIAL_WARN_BEFORE_EXPIRY_DAYS


class LicenseStatus(StrEnum):
    """Канонічні стани ліцензії LGE."""

    NO_LICENSE = "NO_LICENSE"
    TRIAL_OK = "TRIAL_OK"
    TRIAL_EXPIRED = "TRIAL_EXPIRED"
    PRO_OK = "PRO_OK"

    OTHER_MACHINE = "OTHER_MACHINE"
    EXPIRED = "EXPIRED"
    UPDATE_REQUIRED = "UPDATE_REQUIRED"
    TAMPERED = "TAMPERED"
    CLOCK_ROLLBACK = "CLOCK_ROLLBACK"


LICENSE_STATUS_DESCRIPTIONS: dict[LicenseStatus, str] = {
    LicenseStatus.NO_LICENSE: "Ліцензії немає.",
    LicenseStatus.TRIAL_OK: "Пробний період активний.",
    LicenseStatus.TRIAL_EXPIRED: "Пробний період завершився.",
    LicenseStatus.PRO_OK: "Активна комерційна ліцензія.",
    LicenseStatus.OTHER_MACHINE: "Ліцензія прив’язана до іншої машини.",
    LicenseStatus.EXPIRED: "Строк дії комерційної ліцензії завершився.",
    LicenseStatus.UPDATE_REQUIRED: "Потрібне оновлення програми.",
    LicenseStatus.TAMPERED: (
        "Ліцензія пошкоджена, змінена вручну або не проходить перевірку."
    ),
    LicenseStatus.CLOCK_ROLLBACK: "Виявлено підозрілий відкат системного часу.",
}


LICENSE_DATE_FIELDS_DESCRIPTION: dict[str, str] = {
    "activated_at": (
        "Дата і час активації поточного режиму або ліцензії. "
        "Для TRIAL заповнюється в момент запуску trial."
    ),
    "issued_at": (
        "Дата і час видачі комерційної ліцензії. " "Для TRIAL зазвичай null."
    ),
    "expires_at": (
        "Дата і час завершення строку дії. "
        "Для TRIAL це activated_at + trial_days. "
        "Для безстрокових PRO і PRO+ це null, якщо не задано окремо."
    ),
    "last_check_at": "Дата і час останньої перевірки стану ліцензії.",
    "last_run_at": "Дата і час останнього запуску програми.",
    "version_min": (
        "Мінімальна версія програми для цієї ліцензії. "
        "Якщо поточна версія менша — статус UPDATE_REQUIRED."
    ),
}


def parse_license_status(value: object) -> LicenseStatus:
    """Безпечно перетворити сирий рядок статусу на LicenseStatus."""
    if isinstance(value, LicenseStatus):
        return value

    if isinstance(value, str):
        try:
            return LicenseStatus(value.strip())
        except ValueError:
            return LicenseStatus.NO_LICENSE

    return LicenseStatus.NO_LICENSE


def parse_iso_datetime(value: object) -> datetime | None:
    """Безпечно розібрати ISO datetime."""
    if not value or not isinstance(value, str):
        return None

    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None

    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)

    return dt


def get_trial_days(lic: dict[str, Any]) -> int:
    """Повернути кількість днів trial з policy або дефолт з app_meta."""
    trial_policy = lic.get("trial_policy")
    if not isinstance(trial_policy, dict):
        return TRIAL_DAYS

    value = trial_policy.get("trial_days", TRIAL_DAYS)
    try:
        result = int(value)
    except (TypeError, ValueError):
        return TRIAL_DAYS

    return result if result > 0 else TRIAL_DAYS


def get_warn_before_expiry_days(lic: dict[str, Any]) -> int:
    """Повернути кількість днів попередження до завершення trial."""
    trial_policy = lic.get("trial_policy")
    if not isinstance(trial_policy, dict):
        return TRIAL_WARN_BEFORE_EXPIRY_DAYS

    value = trial_policy.get(
        "warn_before_expiry_days",
        TRIAL_WARN_BEFORE_EXPIRY_DAYS,
    )
    try:
        result = int(value)
    except (TypeError, ValueError):
        return TRIAL_WARN_BEFORE_EXPIRY_DAYS

    return result if result >= 0 else TRIAL_WARN_BEFORE_EXPIRY_DAYS


def get_trial_days_left(
    lic: dict[str, Any],
    now: datetime | None = None,
) -> int | None:
    """
    Повернути скільки днів лишилось до кінця trial.

    Повертає:
    - int >= 0, якщо expires_at коректний
    - None, якщо дату завершення визначити не вдалося
    """
    now = now or datetime.now(UTC)

    expires_at = parse_iso_datetime(lic.get("expires_at"))
    if expires_at is None:
        return None

    seconds_left = (expires_at - now).total_seconds()
    if seconds_left <= 0:
        return 0

    days_left = int(seconds_left // 86400)
    if seconds_left % 86400:
        days_left += 1

    return days_left


def should_show_trial_warning(
    lic: dict[str, Any],
    now: datetime | None = None,
) -> bool:
    """
    Чи треба показувати warning про швидке завершення trial.

    Правило:
    - статус має бути TRIAL_OK
    - days_left має бути > 0
    - days_left <= warn_before_expiry_days
    """
    status = parse_license_status(lic.get("status"))
    if status is not LicenseStatus.TRIAL_OK:
        return False

    days_left = get_trial_days_left(lic, now)
    if days_left is None or days_left <= 0:
        return False

    warn_days = get_warn_before_expiry_days(lic)
    return days_left <= warn_days


def build_statusbar_license_text(
    lic: dict[str, Any],
    *,
    full_label: str = "Повний",
) -> tuple[str, str]:
    """
    Повертає два тексти для status bar:
    1) короткий статус ліцензії
    2) текст по повному режиму
    """
    status = parse_license_status(lic.get("status"))
    edition = str(lic.get("edition") or "free").strip().lower()
    trial_days = get_trial_days(lic)
    days_left = get_trial_days_left(lic)

    if status is LicenseStatus.NO_LICENSE:
        return "Ліцензії немає", f"{full_label}: {trial_days}дн"

    if status is LicenseStatus.TRIAL_OK:
        if days_left is None:
            return "TRIAL активна", f"{full_label}: ?"
        return "TRIAL активна", f"{full_label}: {days_left}дн"

    if status is LicenseStatus.TRIAL_EXPIRED:
        return "TRIAL завершено", f"{full_label}: 0дн"

    if status is LicenseStatus.PRO_OK:
        if edition == "pro_plus":
            return "PRO+ активна", f"{full_label}: ∞"
        return "PRO активна", f"{full_label}: ∞"

    if status is LicenseStatus.OTHER_MACHINE:
        return "Інша машина", f"{full_label}: 0дн"

    if status is LicenseStatus.EXPIRED:
        return "Ліцензія завершилась", f"{full_label}: 0дн"

    if status is LicenseStatus.UPDATE_REQUIRED:
        return "Потрібне оновлення", f"{full_label}: ?"

    if status is LicenseStatus.TAMPERED:
        return "Ліцензію пошкоджено", f"{full_label}: 0дн"

    if status is LicenseStatus.CLOCK_ROLLBACK:
        return "Проблема з часом", f"{full_label}: 0дн"

    if edition == "pro_plus":
        return "PRO+ активна", f"{full_label}: ∞"

    if edition == "pro":
        return "PRO активна", f"{full_label}: ∞"

    return "Ліцензія невідома", f"{full_label}: ?"
