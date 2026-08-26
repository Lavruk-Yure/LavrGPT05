# mail_settings.py
# -*- coding: utf-8 -*-
"""\
mail_settings — локальні налаштування SMTP для LGEOffice.

ВАЖЛИВО:
- Цей файл має бути у .gitignore (містить секрети).
- Не комітьте його в репозиторій.

Мінімум для роботи SMTP:
- SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD
"""

from __future__ import annotations

# --- Office inbox (внутрішня пошта) ---

# Куди приходять “запити” на видачу ліцензії (якщо ти це використовуєш в шаблонах).
OFFICE_EMAIL_INBOX: str = "erclavr@gmail.com"


# --- SMTP ---

# Приклад для Gmail (якщо використовуєш): smtp.gmail.com / 587
SMTP_HOST: str = "smtp.gmail.com"
SMTP_PORT: int = 465
SMTP_USER: str = "erclavr@gmail.com"  # email відправника (логін)
SMTP_PASSWORD: str = "jpaf fymx ewqi akps"  # app password / пароль SMTP


def validate_smtp_settings() -> tuple[bool, str]:
    """Повертає (ok, message) для перевірки заповнення SMTP-конфіг."""
    if not SMTP_HOST.strip():
        return False, "SMTP_HOST порожній (office/core/mail_settings.py)"
    if not isinstance(SMTP_PORT, int) or SMTP_PORT <= 0:
        return False, "SMTP_PORT некоректний (office/core/mail_settings.py)"
    if not SMTP_USER.strip():
        return False, "SMTP_USER порожній (office/core/mail_settings.py)"
    if not SMTP_PASSWORD.strip():
        return False, "SMTP_PASSWORD порожній (office/core/mail_settings.py)"
    return True, "OK"
