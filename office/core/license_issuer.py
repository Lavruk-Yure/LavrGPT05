# license_issuer.py
# -*- coding: utf-8 -*-
"""
license_issuer — генерація файлу ліцензії LGE Office.

RoadMap47 / Patch 47.1:
- Формує payload (canonical JSON).
- Підписує Ed25519 (_private_ed25519.pem).
- Пише тільки .lic (payload_b64 + signature_b64).
- Формування листів винесене в license_email_builder.py
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from office.core.license_email_builder import (
    build_license_email_body,
    build_license_email_subject,
    write_license_email_file,
)
from office.core.office_paths import get_private_key_path

priv_path = get_private_key_path()


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _canonical_json_bytes(obj: dict) -> bytes:
    s = json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return s.encode("utf-8")


def _load_private_key_pem(path: Path, password: str | None) -> Ed25519PrivateKey:
    raw = path.read_bytes()
    pw_bytes: bytes | None = password.encode("utf-8") if password else None
    key = serialization.load_pem_private_key(raw, password=pw_bytes)
    if not isinstance(key, Ed25519PrivateKey):
        raise TypeError("Private key is not Ed25519PrivateKey")
    return key


@dataclass(frozen=True)
class IssueResult:
    license_path_abs: Path
    license_path_rel: str
    payload: dict
    payload_b64: str
    signature_b64: str
    email_uk_path: Path
    email_en_path: Path


def issue_license_files(
    *,
    office_dir: Path,
    order_id: str,
    edition: str,
    customer_email: str,
    customer_name: str,
    fingerprint: str,
    app_version: str,
    payment_ref: str,
    office_email: str,
    admin_password: str,
) -> IssueResult:

    order_id = order_id.strip()
    edition = edition.strip()
    customer_email = customer_email.strip()
    fingerprint = fingerprint.strip()
    app_version = app_version.strip()
    payment_ref = payment_ref.strip()

    if not order_id:
        raise ValueError("ORDER_ID обов’язковий")
    if not edition:
        raise ValueError("Edition обов’язковий")
    if not customer_email:
        raise ValueError("Email обов’язковий")
    if not fingerprint:
        raise ValueError("Fingerprint обов’язковий")
    if not app_version:
        raise ValueError("App version обов’язковий")

    issued_utc = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    license_uid = str(uuid4())

    payload = {
        "product": "LGE",
        "order_id": order_id,
        "edition": edition,
        "customer_email": customer_email,
        "fingerprint": fingerprint,
        "app_version": app_version,
        "payment_ref": payment_ref,
        "issued_utc": issued_utc,
        "license_uid": license_uid,
        "office_email": office_email,
    }

    priv_key = _load_private_key_pem(priv_path, admin_password)

    payload_bytes = _canonical_json_bytes(payload)
    payload_b64 = _b64url(payload_bytes)
    signature_b64 = _b64url(priv_key.sign(payload_bytes))

    lic_dir = office_dir / "licenses"
    lic_dir.mkdir(parents=True, exist_ok=True)

    lic_name = f"{order_id}.lic"
    lic_path_abs = lic_dir / lic_name
    lic_obj = {"payload_b64": payload_b64, "signature_b64": signature_b64}
    lic_path_abs.write_text(
        json.dumps(lic_obj, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    lic_rel = str(Path("licenses") / lic_name)

    subject_uk = build_license_email_subject("uk", order_id)
    subject_en = build_license_email_subject("en", order_id)

    body_uk = build_license_email_body(
        language="uk",
        customer_name=customer_name,
        office_email=office_email,
        order_uid=order_id,
        edition=edition,
        app_version=app_version,
        payment_ref=payment_ref,
        fingerprint=fingerprint,
    )

    body_en = build_license_email_body(
        language="en",
        customer_name=customer_name,
        office_email=office_email,
        order_uid=order_id,
        edition=edition,
        app_version=app_version,
        payment_ref=payment_ref,
        fingerprint=fingerprint,
    )

    email_uk_path = lic_dir / f"{order_id}_email_uk.txt"
    email_en_path = lic_dir / f"{order_id}_email_en.txt"

    write_license_email_file(
        file_path=email_uk_path,
        customer_email=customer_email,
        subject=subject_uk,
        body=body_uk,
    )

    write_license_email_file(
        file_path=email_en_path,
        customer_email=customer_email,
        subject=subject_en,
        body=body_en,
    )

    return IssueResult(
        license_path_abs=lic_path_abs,
        license_path_rel=lic_rel,
        payload=payload,
        payload_b64=payload_b64,
        signature_b64=signature_b64,
        email_uk_path=email_uk_path,
        email_en_path=email_en_path,
    )
