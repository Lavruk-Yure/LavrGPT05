# run_encryption_manager.py
"""
run_encryption_manager.py — ручний запуск EncryptionManager для тесту.

Призначення:
    - демонстраційне шифрування/дешифрування;
    - перевірка створення ключа.
"""

from core.encryption_manager import EncryptionManager


def main() -> None:
    mgr = EncryptionManager()
    print(mgr.get_key_info())

    text = "LavrGPT05 encryption test"
    enc = mgr.encrypt(text)
    dec = mgr.decrypt(enc)

    print("🔒 Encrypted:", enc)
    print("🔓 Decrypted:", dec)


if __name__ == "__main__":
    main()
