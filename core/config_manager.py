# config_manager.py
# -*- coding: utf-8 -*-
"""
ConfigManager — єдина точка доступу до LGE05.conf.

Підтримує:
- AES шифрування / розшифрування
- читання / запис
- нормалізацію мови (без білого списку, default='en')
- автоміграцію старих конфігів + автозбереження після міграції
- дефолтну структуру
- базову "колекцію" (ConfigCollection) з get/set
"""

from __future__ import annotations

import getpass
import hashlib
import io
import json
import logging
import platform
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, Tuple

import pyAesCrypt  # noqa

AES_BUFFER = 64 * 1024  # 64 KiB

DEBUG_CONFIG_MANAGER = False

logger = logging.getLogger(__name__)
if not logger.handlers:
    logger.addHandler(logging.NullHandler())


def log_cp(name: str, **kw: Any) -> None:
    """Локальний debug-логер ConfigManager."""
    if not DEBUG_CONFIG_MANAGER:
        return
    msg = f"[CONF:{name}] " + ", ".join(f"{k}={v!r}" for k, v in kw.items())
    print(msg)


def make_machine_stub() -> Dict[str, str]:
    """Поточні дані машини для поля 'machine'."""
    return {
        "username": getpass.getuser(),
        "platform": platform.platform(),
        "node": platform.node(),
        "mac": hex(uuid.getnode()),
    }


def _read_version_from_root_init() -> str:
    # core/.. -> корінь проєкту
    root_init = Path(__file__).resolve().parents[1] / "__init__.py"
    if not root_init.exists():
        return "0.0.0"

    text = root_init.read_text(encoding="utf-8", errors="ignore")
    m = re.search(r'^__version__\s*=\s*"([^"]+)"\s*$', text, re.MULTILINE)
    return m.group(1).strip() if m else "0.0.0"


class ConfigCollection:
    """
    Обгортка над dict для зручного доступу:
    - get(section, key, default)
    - set(section, key, value)
    - to_dict()
    """

    def __init__(self, data: Dict[str, Any]) -> None:
        self._data = data

    def get(self, section: str, key: str, default: Any = None) -> Any:
        if not section:
            return self._data.get(key, default)

        sec = self._data.get(section)
        if not isinstance(sec, dict):
            return default
        return sec.get(key, default)

    def set(self, section: str, key: str, value: Any) -> None:
        """Якщо секції немає — створюємо. Оновлює updated_at."""
        if not section:
            self._data[key] = value
        else:
            sec = self._data.get(section)
            if not isinstance(sec, dict):
                sec = {}
                self._data[section] = sec
            sec[key] = value

        self._touch_updated()

    def to_dict(self) -> Dict[str, Any]:
        return self._data

    def _touch_updated(self) -> None:
        now = datetime.now(UTC).isoformat()
        self._data.setdefault("created_at", now)
        self._data["updated_at"] = now


class ConfigManager:
    """Менеджер читання-запису зашифрованого конфігу LGE05."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    # ----------------------------------------------------------------------
    # PUBLIC API
    # ----------------------------------------------------------------------
    def load(self, password: str) -> Dict[str, Any] | None:
        """Back-compat: повертає dict або None."""
        data, status = self.load_with_status(password)
        log_cp("load", status=status)
        return data if status == "ok" else None

    def load_with_status(self, password: str) -> Tuple[Dict[str, Any] | None, str]:
        """
        Повертає (data|None, status).

        status:
          - missing
          - corrupted        (файл не схожий на AES Crypt)
          - wrong_password   (AES заголовок є, але decrypt не пройшов)
          - json_error
          - hash_mismatch
          - ok

        Після міграції робить автозбереження (щоб прибрати зайві/legacy ключі на диску).
        """
        if not self.path.exists():
            return None, "missing"

        if not self._looks_like_aes_crypt_file():
            return None, "corrupted"

        try:
            raw = self._aes_decrypt(password)
        except ValueError:
            # AES заголовок є → найімовірніше невірний пароль
            return None, "wrong_password"
        except Exception:  # noqa
            logger.exception("Config load failed: decrypt error")
            return None, "corrupted"

        try:
            data: Dict[str, Any] = json.loads(raw.decode("utf-8"))
        except Exception:  # noqa
            return None, "json_error"

        stored = data.get("password_sha256", "")
        if hashlib.sha256(password.encode("utf-8")).hexdigest() != stored:
            return None, "hash_mismatch"

        migrated, changed = self._migrate(data)

        if changed:
            try:
                self.save(migrated, password)
                logger.info("Config migrated and saved (canonical cleanup)")
            except Exception:  # noqa
                logger.exception("Config migrated but failed to save")

        return migrated, "ok"

    def save(self, data: Dict[str, Any], password: str) -> None:
        now = datetime.now(UTC).isoformat()
        data.setdefault("created_at", now)
        data["updated_at"] = now

        raw = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self._aes_encrypt(raw, password)

    def create_default(
        self,
        email: str,
        lang: str,
        pwd_hash: str,
        machine: Dict[str, str],
    ) -> Dict[str, Any]:
        now = datetime.now(UTC).isoformat()

        return {
            "app": "LGE05",
            "version": _read_version_from_root_init(),
            "email": email,
            "language": self._normalize_lang(lang),
            "password_sha256": pwd_hash,
            "created_at": now,
            "updated_at": now,
            "multi_language": False,
            "translator": {
                "provider": "off",
                "deepl_key_1": "",
                "deepl_key_2": "",
            },
            "machine": machine,
            "license": {
                # --- базове ---
                "edition": "free",  # free | pro | pro_plus
                "status": "NO_LICENSE",  # computed, але зберігаємо
                "machine_id": None,
                # --- підписаний ключ ---
                "payload_b64": None,
                "signature_b64": None,
                # --- дати ---
                "activated_at": None,  # перший запуск / активація
                "issued_at": None,  # з payload
                "expires_at": None,  # з payload або null
                "version_min": None,  # з payload або null
                # --- службове ---
                "last_check_at": None,
                "last_run_at": None,
                # --- аналітика / підтримка ---
                "source": None,  # gumroad | ctrader_store | manual
                "note": None,
                # --- політика часу (НЕ міняти в рантаймі) ---
                "trial_policy": {
                    "free_preview_days": 90,  # Free demo
                    "auto_preview_days": 90,  # Auto demo
                    "pro_full_days": 180,  # Pro повний
                    "proplus_full_days": None,  # Pro+ без ліміту
                },
            },
        }

    @staticmethod
    def _default_license_block() -> Dict[str, Any]:
        """Дефолтний блок license для міграції старих конфігів."""
        return {
            "edition": "free",  # free | pro | pro_plus
            "status": "NO_LICENSE",  # computed, але зберігаємо
            "machine_id": None,
            "payload_b64": None,
            "signature_b64": None,
            "activated_at": None,
            "issued_at": None,
            "expires_at": None,
            "version_min": None,
            "last_check_at": None,
            "last_run_at": None,
            "source": None,  # gumroad | ctrader_store | manual
            "note": None,
            "trial_policy": {
                "free_preview_days": 90,
                "auto_preview_days": 90,
                "pro_full_days": 180,
                "proplus_full_days": None,
            },
        }

    # ----------------------------------------------------------------------
    # INTERNAL — AES I/O
    # ----------------------------------------------------------------------
    def _aes_encrypt(self, plain: bytes, password: str) -> None:
        src = io.BytesIO(plain)
        dst = io.BytesIO()
        pyAesCrypt.encryptStream(src, dst, password, AES_BUFFER)

        dst.seek(0)
        with self.path.open("wb") as f:
            f.write(dst.read())

    def _aes_decrypt(self, password: str) -> bytes:
        with self.path.open("rb") as fin:
            src = io.BytesIO(fin.read())
            src.seek(0)

        dst = io.BytesIO()
        pyAesCrypt.decryptStream(src, dst, password, AES_BUFFER)
        dst.seek(0)
        return dst.read()

    def _looks_like_aes_crypt_file(self) -> bool:
        """
        AES Crypt файли в нашому кейсі починаються з b'AES\\x02' (або інша версія).
        Якщо заголовок інший — це точно не наш конфіг (або битий).
        """
        try:
            head = self.path.read_bytes()[:4]
        except Exception:  # noqa
            return False
        if len(head) < 4:
            return False
        return head[0:3] == b"AES" and head[3] in (2, 3, 4)

    # ----------------------------------------------------------------------
    # INTERNAL — MIGRATION
    # ----------------------------------------------------------------------
    def _migrate(self, data: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
        """
        Гарантує, що всі ключі існують.
        Translator приводимо до канонічної схеми і тим самим прибираємо
        будь-які старі/зайві ключі без окремих "legacy алгоритмів".
        """
        changed = False

        # language
        old_lang = data.get("language")
        fixed_lang = self._normalize_lang(old_lang)
        if fixed_lang != old_lang:
            data["language"] = fixed_lang
            changed = True

        # multi_language
        if "multi_language" not in data:
            data["multi_language"] = False
            changed = True
        try:
            from LavrGPT05 import __version__ as app_version  # type: ignore
        except Exception:  # noqa
            app_version = None

        if (
            "version" not in data
            or not isinstance(data.get("version"), str)
            or not data["version"].strip()
        ):
            data["version"] = str(app_version or "0.0.0")
            changed = True

        # translator (canonical only) — DeepL/Off only
        old_tr = data.get("translator")
        if not isinstance(old_tr, dict):
            old_tr = {}
            changed = True

        provider = old_tr.get("provider")
        provider = provider.strip().lower() if isinstance(provider, str) else "off"
        if provider not in ("deepl", "off"):
            provider = "off"
            changed = True

        deepl_key_1 = old_tr.get("deepl_key_1")
        deepl_key_2 = old_tr.get("deepl_key_2")

        deepl_key_1 = deepl_key_1.strip() if isinstance(deepl_key_1, str) else ""
        deepl_key_2 = deepl_key_2.strip() if isinstance(deepl_key_2, str) else ""

        new_tr = {
            "provider": provider,
            "deepl_key_1": deepl_key_1,
            "deepl_key_2": deepl_key_2,
        }

        if dict(old_tr) != new_tr:
            data["translator"] = new_tr
            changed = True
        else:
            data["translator"] = new_tr

        # machine
        if "machine" not in data or not isinstance(data["machine"], dict):
            data["machine"] = {}
            changed = True

        for key in ("username", "platform", "node", "mac"):
            if key not in data["machine"]:
                data["machine"][key] = ""
                changed = True
        # license (canonical keys)
        defaults_lic = self._default_license_block()

        lic = data.get("license")
        if not isinstance(lic, dict):
            data["license"] = defaults_lic
            changed = True
        else:
            # докинути відсутні ключі верхнього рівня
            for k, v in defaults_lic.items():
                if k not in lic:
                    lic[k] = v
                    changed = True

            # trial_policy окремо (вкладений dict)
            tp = lic.get("trial_policy")
            if not isinstance(tp, dict):
                lic["trial_policy"] = defaults_lic["trial_policy"]
                changed = True
            else:
                for k, v in defaults_lic["trial_policy"].items():
                    if k not in tp:
                        tp[k] = v
                        changed = True

        # created_at / updated_at
        now = datetime.now(UTC).isoformat()
        if "created_at" not in data:
            data["created_at"] = now
            changed = True
        if "updated_at" not in data:
            data["updated_at"] = now
            changed = True

        return data, changed

    # ----------------------------------------------------------------------
    # INTERNAL — language normalization (no whitelist)
    # ----------------------------------------------------------------------
    @staticmethod
    def _normalize_lang(value: Any) -> str:
        """
        Нормалізує код мови без білого списку.
        'uk', 'UK', 'uk-UA', 'ua', 'UA' → 'uk'
        інше: беремо базову частину BCP47 → 'zh-Hans' → 'zh', 'pt-BR' → 'pt'
        якщо не виходить — 'en'
        """
        if not isinstance(value, str):
            return "en"

        s = value.strip()
        if not s:
            return "en"

        s = s.replace("_", "-").lower()
        base = s.split("-", 1)[0].strip()

        if base == "ua":
            return "uk"

        if re.fullmatch(r"[a-z]{2,3}", base):
            return base

        return "en"


class _PwdBox:
    value: str | None = None


USER_PASSWORD = _PwdBox()
