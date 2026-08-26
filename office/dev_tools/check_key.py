import base64
from pathlib import Path

from cryptography.hazmat.primitives import serialization

PRIVATE_KEY_PATH = Path("keys/_private_ed25519.pem")

private_data = PRIVATE_KEY_PATH.read_bytes()

password = input("Password: ").encode()

private_key = serialization.load_pem_private_key(
    private_data,
    password=password,
)

public_key = private_key.public_key()

raw = public_key.public_bytes_raw()

print("PUBLIC KEY B64:")
print(base64.b64encode(raw).decode())
