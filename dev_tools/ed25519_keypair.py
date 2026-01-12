# ed25519_keypair.py
# -*- coding: utf-8 -*-
"""
Ed25519 keypair generator for LGE05 licensing.

- Generates ONE keypair.
- Saves private key to local file (NOT for git).
- Prints public key (base64) for embedding into LicenseManager.

Run once. Keep private key secret.
"""

from __future__ import annotations

import base64
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

PRIVATE_KEY_PATH = Path(__file__).parent / "_private_ed25519.key"


def main() -> None:
    if PRIVATE_KEY_PATH.exists():
        print("❌ Private key already exists:")
        print(f"   {PRIVATE_KEY_PATH}")
        print("   Aborting to avoid overwrite.")
        return

    # --- generate keypair ---
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    # --- serialize private key (raw) ---
    priv_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )

    # --- serialize public key (raw) ---
    pub_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )

    # --- save private key ---
    PRIVATE_KEY_PATH.write_bytes(priv_bytes)

    # --- output public key ---
    pub_b64 = base64.b64encode(pub_bytes).decode("ascii")

    print("✅ Ed25519 keypair generated")
    print()
    print("🔐 Private key saved to:")
    print(f"   {PRIVATE_KEY_PATH}")
    print()
    print("📢 Public key (base64) — embed into LicenseManager:")
    print(pub_b64)


if __name__ == "__main__":
    main()
