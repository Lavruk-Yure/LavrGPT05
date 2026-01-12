# license_manager.py
# -*- coding: utf-8 -*-
"""
LicenseManager — логіка ліцензій LGE05 (офлайн, без license.json).

Важливе:
- Джерело правди: LGE05.conf -> data["license"].
- Варіант machine_id: MachineGuid + SystemUUID (Windows).
- Free: demo 90 днів (TRIAL_OK), потім TRIAL_EXPIRED (viewer only).
- Pro: 180 днів повний (PRO_OK), потім PRO_LIMITED (manual+semi only).
- Pro+: без ліміту.
- TAMPERED -> fatal (Exit робить caller).
- CLOCK_ROLLBACK -> fatal для pro/pro_plus (Exit робить caller).

Цей модуль НЕ створює файлів і НЕ показує UI. Працює з dict.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Dict, Optional

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

DEBUG_LICENSE_MANAGER = True

logger = logging.getLogger(__name__)
if not logger.handlers:
    logger.addHandler(logging.NullHandler())


def log_lp(name: str, **kw: Any) -> None:
    """Локальний debug-логер LicenseManager."""
    if not DEBUG_LICENSE_MANAGER:
        return
    msg = f"[LIC:{name}] " + ", ".join(f"{k}={v!r}" for k, v in kw.items())
    print(msg)


# -----------------------------
# Public data structures
# -----------------------------
@dataclass(frozen=True)
class LicenseCaps:
    ui_view: bool
    ib_connect: bool
    signals_view: bool

    live_manual: bool
    live_semi: bool

    auto_demo: bool
    auto_full: bool


@dataclass(frozen=True)
class LicenseResult:
    status: str
    edition: str
    days_used: int
    caps: LicenseCaps
    fatal: bool
    fatal_reason: Optional[str]


# -----------------------------
# LicenseManager
# -----------------------------
class LicenseManager:
    """
    Вся ліцензійна логіка у 1 місці.
    Працює з dict-конфігом і повертає статус/права.
    """

    # Термінологія
    EDITIONS = ("free", "pro", "pro_plus")

    # Статуси
    ST_NO_LICENSE = "NO_LICENSE"
    ST_TRIAL_OK = "TRIAL_OK"
    ST_TRIAL_EXPIRED = "TRIAL_EXPIRED"
    ST_PRO_OK = "PRO_OK"
    ST_PRO_LIMITED = "PRO_LIMITED"
    ST_OTHER_MACHINE = "OTHER_MACHINE"
    ST_EXPIRED = "EXPIRED"
    ST_UPDATE_REQUIRED = "UPDATE_REQUIRED"
    ST_TAMPERED = "TAMPERED"
    ST_CLOCK_ROLLBACK = "CLOCK_ROLLBACK"

    # Толеранс до “відкоту годинника”
    CLOCK_TOLERANCE_SECONDS = 5 * 60  # 5 хв

    # SALT (вшитий; потім можна винести у build-time)
    _SALT = "LGE05::LICENSE::SALT::v1"
    PUBLIC_KEY_B64 = "nPbiv6R5pfK4GHvpxmMgNc3Tt56gEIir/qPIXq6yadA="

    @classmethod
    def compute_and_update(
        cls,
        conf: Dict[str, Any],
        *,
        now: Optional[datetime] = None,
        app_version: Optional[str] = None,
    ) -> LicenseResult:
        """
        Головний entry-point:
        - рахує machine_id
        - перевіряє clock rollback
        - визначає статус
        - оновлює conf["license"].status + last_check_at + last_run_at
        (+ activated_at для free)
        """
        now = now or datetime.now(UTC)
        lic = cls._ensure_license_block(conf)

        edition = cls._norm_edition(lic.get("edition"))
        lic["edition"] = edition

        # 1) clock rollback check (для pro/pro_plus fatal)
        fatal = False
        fatal_reason: Optional[str] = None

        last_run_at = cls._parse_dt(lic.get("last_run_at"))
        if last_run_at is not None:
            delta = (last_run_at - now).total_seconds()
            if delta > cls.CLOCK_TOLERANCE_SECONDS:
                lic["status"] = cls.ST_CLOCK_ROLLBACK
                cls._touch_times(lic, now, touch_run=False)  # не оновлюємо last_run_at
                caps = cls._caps_for_status(cls.ST_CLOCK_ROLLBACK, edition, 0)
                if edition in ("pro", "pro_plus"):
                    fatal = True
                    fatal_reason = cls.ST_CLOCK_ROLLBACK
                log_lp(
                    "clock_rollback",
                    edition=edition,
                    last_run_at=str(last_run_at),
                    now=str(now),
                )
                return LicenseResult(
                    status=lic["status"],
                    edition=edition,
                    days_used=0,
                    caps=caps,
                    fatal=fatal,
                    fatal_reason=fatal_reason,
                )

        # 2) machine_id
        machine_id_preferred, machine_id_candidates = (
            cls.compute_machine_id_candidates()
        )

        stored_mid = lic.get("machine_id")
        if not isinstance(stored_mid, str) or not stored_mid:
            lic["machine_id"] = machine_id_preferred
        else:
            if stored_mid not in machine_id_candidates:
                # реальна інша машина
                lic["status"] = cls.ST_OTHER_MACHINE
                days_used = cls._days_used(lic, now, set_if_missing=False)
                cls._touch_times(lic, now, touch_run=True)
                caps = cls._caps_for_status(cls.ST_OTHER_MACHINE, edition, days_used)
                log_lp("other_machine", stored=stored_mid, current=machine_id_preferred)
                return LicenseResult(
                    status=lic["status"],
                    edition=edition,
                    days_used=days_used,
                    caps=caps,
                    fatal=False,
                    fatal_reason=None,
                )

            # back-compat: якщо збіглось з legacy — оновлюємо на preferred
            if stored_mid != machine_id_preferred:
                lic["machine_id"] = machine_id_preferred
                log_lp(
                    "machine_id.upgrade",
                    stored=stored_mid,
                    preferred=machine_id_preferred,
                )

        # 3) status by edition/time/key
        status, days_used, fatal, fatal_reason = cls._compute_status(
            conf=conf,
            lic=lic,
            now=now,
            app_version=app_version,
        )

        lic["status"] = status
        cls._touch_times(lic, now, touch_run=True)
        caps = cls._caps_for_status(status, edition, days_used)

        return LicenseResult(
            status=status,
            edition=edition,
            days_used=days_used,
            caps=caps,
            fatal=fatal,
            fatal_reason=fatal_reason,
        )

    # -----------------------------
    # Activation (stub; to be implemented with real signature check)
    # -----------------------------
    @classmethod
    def activate_key(
        cls,
        conf: Dict[str, Any],
        *,
        license_key: str,
        now: Optional[datetime] = None,
        app_version: Optional[str] = None,
    ) -> tuple[bool, str]:
        """
        Активує ключ. Поки що це "каркас":
        - розбирає ключ на payload/signature
        - перевіряє базові поля product/edition/version/expires
        - signature check: TODO (пізніше підключимо реальну криптографію)

        Повертає (ok, message).
        """
        now = now or datetime.now(UTC)
        lic = cls._ensure_license_block(conf)

        parsed = cls._parse_license_key(license_key)
        if parsed is None:
            return False, "Invalid license key format"

        payload_b64, signature_b64, payload = parsed

        # basic checks
        if payload.get("product") != "LGE":
            return False, "Invalid product"
        edition = payload.get("edition")
        if edition not in ("pro", "pro_plus"):
            return False, "Invalid edition"

        # version_min
        version_min = payload.get("version_min")
        if version_min and app_version and cls._version_lt(app_version, version_min):
            return False, "Update required"

        # expires_at
        expires_at = payload.get("expires_at")
        if isinstance(expires_at, str) and expires_at:
            dt_exp = cls._parse_dt(expires_at)
            if dt_exp and now > dt_exp:
                return False, "License expired"

        # verify signature using embedded public key
        if not cls._verify_signature(payload_b64, signature_b64):
            return False, "Invalid signature"

        # write conf
        lic["edition"] = edition
        lic["payload_b64"] = payload_b64
        lic["signature_b64"] = signature_b64

        lic["issued_at"] = payload.get("issued_at")
        lic["expires_at"] = payload.get("expires_at")
        lic["version_min"] = payload.get("version_min")
        lic["source"] = payload.get("source")
        lic["note"] = payload.get("note")

        lic["activated_at"] = now.isoformat()
        lic["machine_id"] = cls.compute_machine_id()

        lic["status"] = cls.ST_PRO_OK
        lic["last_check_at"] = now.isoformat()
        lic["last_run_at"] = now.isoformat()

        return True, "Activated"

    # -----------------------------
    # Machine ID (Variant 1)
    # -----------------------------
    @classmethod
    def compute_machine_id(cls) -> str:
        """
        Variant 1:
        machine_id = sha256("LGE|v1|<MachineGuid>|<SystemUUID>|<SALT>")
        """
        mg = cls._read_machine_guid() or "NA"
        su = cls._read_system_uuid() or "NA"
        raw = f"LGE|v1|{mg}|{su}|{cls._SALT}"
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        return f"SHA256:{digest}"

    @classmethod
    def compute_machine_id_candidates(cls) -> tuple[str, set[str]]:
        """
        Повертає (preferred_id, candidates).
        candidates містить legacy-варіанти для back-compat.
        """
        mg = cls._read_machine_guid() or "NA"
        su = cls._read_system_uuid() or "NA"

        preferred_raw = f"LGE|v1|{mg}|{su}|{cls._SALT}"
        preferred = (
            f"SHA256:{hashlib.sha256(preferred_raw.encode('utf-8')).hexdigest()}"
        )

        candidates = {preferred}

        # legacy: UUID був 'NA' (коли wmic не було)
        legacy_raw = f"LGE|v1|{mg}|NA|{cls._SALT}"
        legacy = f"SHA256:{hashlib.sha256(legacy_raw.encode('utf-8')).hexdigest()}"
        candidates.add(legacy)

        return preferred, candidates

    @staticmethod
    def _read_machine_guid() -> Optional[str]:
        # Windows Registry read via reg.exe (без додаткових lib)
        try:
            cp = subprocess.run(
                [
                    "reg",
                    "query",
                    r"HKLM\SOFTWARE\Microsoft\Cryptography",
                    "/v",
                    "MachineGuid",
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
            out = (cp.stdout or "").strip()
            for line in out.splitlines():
                if "MachineGuid" in line:
                    parts = line.split()
                    if parts:
                        return parts[-1].strip().upper()
        except Exception as e:  # noqa
            log_lp("read_machine_guid_fail", err=str(e))
        return None

    @staticmethod
    def _read_system_uuid() -> Optional[str]:
        """
        System UUID через PowerShell (CIM). Працює без wmic.
        """
        try:
            cp = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-Command",
                    "(Get-CimInstance Win32_ComputerSystemProduct).UUID",
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=8,
            )
            s = (cp.stdout or "").strip()
            if not s:
                return None
            # інколи повертає кілька рядків
            line = s.splitlines()[-1].strip()
            if not line:
                return None
            return line.upper()
        except Exception as e:  # noqa
            log_lp("read_system_uuid_fail", err=str(e))
        return None

    # -----------------------------
    # Status computation
    # -----------------------------
    @classmethod
    def _compute_status(
        cls,
        *,
        conf: Dict[str, Any],
        lic: Dict[str, Any],
        now: datetime,
        app_version: Optional[str],
    ) -> tuple[str, int, bool, Optional[str]]:
        _ = conf
        """
        Повертає (status, days_used, fatal, fatal_reason)
        """
        edition = cls._norm_edition(lic.get("edition"))

        # no key => free flow
        has_key = isinstance(lic.get("payload_b64"), str) and isinstance(
            lic.get("signature_b64"), str
        )

        # For free: always trial logic
        if edition == "free" or not has_key:
            days_used = cls._days_used(lic, now, set_if_missing=True)
            free_days = cls._policy_int(lic, "free_preview_days", 90)
            if days_used <= free_days:
                return cls.ST_TRIAL_OK, days_used, False, None
            return cls.ST_TRIAL_EXPIRED, days_used, False, None

        # Pro/Pro+: validate stored signature/payload (stub now)
        # NOTE: real signature check will be added in Patch 19.2b
        parsed = cls._parse_payload_from_conf(lic)

        if parsed is None:
            return cls.ST_TAMPERED, 0, True, cls.ST_TAMPERED

        payload_b64 = lic.get("payload_b64")
        signature_b64 = lic.get("signature_b64")

        if not isinstance(payload_b64, str) or not isinstance(signature_b64, str):
            return cls.ST_TAMPERED, 0, True, cls.ST_TAMPERED

        if not cls._verify_signature(payload_b64, signature_b64):
            return cls.ST_TAMPERED, 0, True, cls.ST_TAMPERED

        payload = parsed

        if payload.get("product") != "LGE":
            return cls.ST_TAMPERED, 0, True, cls.ST_TAMPERED

        # version_min
        version_min = lic.get("version_min")
        if isinstance(version_min, str) and version_min and app_version:
            if cls._version_lt(app_version, version_min):
                days_used = cls._days_used(lic, now, set_if_missing=False)
                return cls.ST_UPDATE_REQUIRED, days_used, False, None

        # expires_at
        dt_exp = cls._parse_dt(lic.get("expires_at"))
        if dt_exp and now > dt_exp:
            days_used = cls._days_used(lic, now, set_if_missing=False)
            return cls.ST_EXPIRED, days_used, False, None

        # time policy
        days_used = cls._days_used(lic, now, set_if_missing=True)

        if edition == "pro_plus":
            return cls.ST_PRO_OK, days_used, False, None

        # pro
        pro_days = cls._policy_int(lic, "pro_full_days", 180)
        if days_used <= pro_days:
            return cls.ST_PRO_OK, days_used, False, None
        return cls.ST_PRO_LIMITED, days_used, False, None

    # -----------------------------
    # Capabilities (матриця)
    # -----------------------------
    @classmethod
    def _caps_for_status(cls, status: str, edition: str, days_used: int) -> LicenseCaps:
        """
        Стартова матриця доступів (можна міняти пізніше).
        Враховано: TRIAL_EXPIRED -> PAPER_MODE ❌ (і paper тут взагалі нема).
        """
        _ = days_used

        # базово: viewer
        ui_view = True
        ib_connect = True
        signals_view = True

        live_manual = False
        live_semi = False
        auto_demo = False
        auto_full = False

        if status in (cls.ST_TAMPERED,):
            # caller має завершити роботу, але на всяк випадок
            return LicenseCaps(
                ui_view=False,
                ib_connect=False,
                signals_view=False,
                live_manual=False,
                live_semi=False,
                auto_demo=False,
                auto_full=False,
            )

        if status in (cls.ST_TRIAL_OK, cls.ST_NO_LICENSE):
            # Free demo
            live_manual = False
            live_semi = False
            auto_demo = True
            auto_full = False

        elif status == cls.ST_TRIAL_EXPIRED:
            # Viewer only
            ib_connect = True
            signals_view = True
            auto_demo = False
            auto_full = False

        elif status == cls.ST_PRO_OK:
            live_manual = True
            live_semi = True
            if edition == "pro_plus":
                auto_full = True
            elif edition == "pro":
                auto_full = True
            else:
                auto_full = False

        elif status == cls.ST_PRO_LIMITED:
            live_manual = True
            live_semi = True
            auto_full = False
            auto_demo = False

        elif status == cls.ST_OTHER_MACHINE:
            live_manual = False
            live_semi = False
            auto_demo = False
            auto_full = False

        elif status in (cls.ST_EXPIRED, cls.ST_UPDATE_REQUIRED):
            live_manual = False
            live_semi = False
            auto_demo = False
            auto_full = False

        elif status == cls.ST_CLOCK_ROLLBACK:
            # Free -> viewer, Pro/Pro+ -> fatal (caller)
            live_manual = False
            live_semi = False
            auto_demo = False
            auto_full = False

        return LicenseCaps(
            ui_view=ui_view,
            ib_connect=ib_connect,
            signals_view=signals_view,
            live_manual=live_manual,
            live_semi=live_semi,
            auto_demo=auto_demo,
            auto_full=auto_full,
        )

    # -----------------------------
    # Helpers
    # -----------------------------
    @classmethod
    def _ensure_license_block(cls, conf: Dict[str, Any]) -> Dict[str, Any]:
        lic = conf.get("license")
        if not isinstance(lic, dict):
            lic = {}
            conf["license"] = lic

        # ensure trial_policy exists
        if "trial_policy" not in lic or not isinstance(lic.get("trial_policy"), dict):
            lic["trial_policy"] = {
                "free_preview_days": 90,
                "auto_preview_days": 90,
                "pro_full_days": 180,
                "proplus_full_days": None,
            }
        return lic

    @staticmethod
    def _norm_edition(value: Any) -> str:
        if isinstance(value, str):
            v = value.strip().lower()
            if v in ("free", "pro", "pro_plus"):
                return v
        return "free"

    @staticmethod
    def _policy_int(lic: Dict[str, Any], key: str, default: int) -> int:
        tp = lic.get("trial_policy")
        if not isinstance(tp, dict):
            return default
        v = tp.get(key, default)
        try:
            return int(v)
        except Exception:  # noqa
            return default

    @staticmethod
    def _parse_dt(value: Any) -> Optional[datetime]:
        if not isinstance(value, str) or not value.strip():
            return None
        try:
            # isoformat, with timezone expected
            return datetime.fromisoformat(value)
        except Exception:  # noqa
            return None

    @staticmethod
    def _days_used(lic: Dict[str, Any], now: datetime, *, set_if_missing: bool) -> int:
        activated_at = LicenseManager._parse_dt(lic.get("activated_at"))
        if activated_at is None:
            if set_if_missing:
                lic["activated_at"] = now.isoformat()
                activated_at = now
            else:
                return 0
        delta = now - activated_at
        days = int(delta.total_seconds() // 86400)
        if days < 0:
            days = 0
        return days

    @staticmethod
    def _touch_times(lic: Dict[str, Any], now: datetime, *, touch_run: bool) -> None:
        lic["last_check_at"] = now.isoformat()
        if touch_run:
            lic["last_run_at"] = now.isoformat()

    @staticmethod
    def _parse_license_key(
        key_str: str,
    ) -> Optional[tuple[str, str, Dict[str, Any]]]:
        """
        Очікуємо: payload_b64.signature_b64
        payload_b64 — base64url JSON
        signature_b64 — base64url bytes
        """
        if not isinstance(key_str, str):
            return None
        s = key_str.strip()
        if "." not in s:
            return None
        payload_b64, signature_b64 = s.split(".", 1)
        if not payload_b64 or not signature_b64:
            return None

        try:
            payload_json = LicenseManager._b64url_decode(payload_b64).decode("utf-8")
            payload = json.loads(payload_json)
            if not isinstance(payload, dict):
                return None
        except Exception:  # noqa
            return None

        return payload_b64, signature_b64, payload

    @staticmethod
    def _parse_payload_from_conf(lic: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        payload_b64 = lic.get("payload_b64")
        if not isinstance(payload_b64, str) or not payload_b64:
            return None
        try:
            payload_json = LicenseManager._b64url_decode(payload_b64).decode("utf-8")
            payload = json.loads(payload_json)
            return payload if isinstance(payload, dict) else None
        except Exception:  # noqa
            return None

    @staticmethod
    def _b64url_decode(s: str) -> bytes:
        s = s.strip()
        pad = "=" * ((4 - len(s) % 4) % 4)
        return base64.urlsafe_b64decode(s + pad)

    @classmethod
    def _verify_signature(cls, payload_b64: str, signature_b64: str) -> bool:
        try:
            payload_bytes = cls._b64url_decode(payload_b64)
            sig_bytes = cls._b64url_decode(signature_b64)

            pub_bytes = base64.b64decode(cls.PUBLIC_KEY_B64)
            pub = Ed25519PublicKey.from_public_bytes(pub_bytes)

            pub.verify(sig_bytes, payload_bytes)
            return True
        except Exception as e:  # noqa
            log_lp("sig.verify.fail", err=str(e))
            return False

    @staticmethod
    def _version_lt(a: str, b: str) -> bool:
        """
        Дуже проста перевірка semver-like (0.1.0).
        Якщо формат “кривий” — вважаємо що не менше.
        """

        def parse(v: str) -> tuple[int, int, int]:
            parts = (v or "").strip().split(".")
            nums: list[int] = []
            for i in range(3):
                try:
                    nums.append(int(parts[i]))
                except Exception:  # noqa
                    nums.append(0)
            return nums[0], nums[1], nums[2]

        return parse(a) < parse(b)
