# license_keygen.py
# -*- coding: utf-8 -*-
"""
License key generator for LGE05 (Ed25519) — interactive console mode.

Key format:
    LICENSE_KEY = payload_b64.signature_b64

Private key file (raw 32 bytes):
    dev_tools/_private_ed25519.key

IMPORTANT:
- Never commit private key to git.

edition: pro | pro_plus

pro → 180 днів повний, потім PRO_LIMITED

pro_plus → без ліміту, PRO_OK

source: gumroad | ctrader_store | manual (тільки аналітика/довідка)

order_id: довільний рядок (для підтримки/звірки)

support_email: для контакту (може йти в діагностику)

version_min: якщо app_version < version_min → UPDATE_REQUIRED

expires_at: ISO datetime або пусто → якщо прострочено → EXPIRED

note: довільно, не показувати користувачу
"""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, Optional

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

PRIVATE_KEY_PATH = Path(__file__).parent / "_private_ed25519.key"


def b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def canonical_json_bytes(payload: Dict[str, Any]) -> bytes:
    # критично: однакові bytes для sign/verify
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def ask(prompt: str, default: Optional[str] = None) -> str:
    if default is None:
        s = input(f"{prompt}: ").strip()
        return s
    s = input(f"{prompt} [{default}]: ").strip()
    return s if s else default


def ask_choice(prompt: str, choices: list[str], default: str) -> str:
    s = ask(f"{prompt} ({'/'.join(choices)})", default=default).strip().lower()
    return s if s in choices else default


def ask_optional_iso_dt(prompt: str) -> Optional[str]:
    s = input(f"{prompt} (ISO або порожньо): ").strip()
    if not s:
        return None
    # не валідую жорстко — це dev_tool; валідація буде в LicenseManager
    return s


def main() -> None:
    if not PRIVATE_KEY_PATH.exists():
        raise SystemExit(f"Private key not found: {PRIVATE_KEY_PATH}")

    priv_bytes = PRIVATE_KEY_PATH.read_bytes()
    if len(priv_bytes) != 32:
        raise SystemExit("Invalid private key file (expected 32 raw bytes).")

    private_key = Ed25519PrivateKey.from_private_bytes(priv_bytes)

    print("=== LGE05 License Key Generator (Ed25519) ===")

    edition = ask_choice("Edition", ["pro", "pro_plus"], default="pro")
    source = ask_choice(
        "Source",
        ["gumroad", "ctrader_store", "manual"],
        default="manual",
    )
    order_id = ask("Order ID", default="TEST-001")
    support_email = ask("Support email", default="lavrhome@gmail.com")

    version_min = ask("Version min (optional)", default="").strip() or None
    expires_at = ask_optional_iso_dt("Expires at")
    note = ask("Note (optional)", default="").strip() or None

    now = datetime.now(UTC).isoformat()

    payload: Dict[str, Any] = {
        "product": "LGE",
        "edition": edition,
        "issued_at": now,
        "expires_at": expires_at,
        "version_min": version_min,
        "source": source,
        "order_id": order_id,
        "support_email": support_email,
        "note": note,
    }

    payload_bytes = canonical_json_bytes(payload)
    sig_bytes = private_key.sign(payload_bytes)

    payload_b64 = b64url_encode(payload_bytes)
    sig_b64 = b64url_encode(sig_bytes)

    license_key = f"{payload_b64}.{sig_b64}"

    print()
    print("LICENSE_KEY=" + license_key)
    print()
    print("Payload (canonical):")
    print(payload_bytes.decode("utf-8"))


if __name__ == "__main__":
    main()
