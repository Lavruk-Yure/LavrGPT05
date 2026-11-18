"""T116-02 · TEST_ONLY · read-only аудит серверного cTrader DEMO.

Жодного account auth, ордера, запиту позицій, RuntimeEngine або запису конфігурації.
Два дозволені API-запити: ApplicationAuth та GetAccountListByAccessToken.
"""

from __future__ import annotations

import argparse
import getpass
import hashlib
import hmac
import io
import json
import os
import sys
import time
from pathlib import Path

import pyAesCrypt
from ctrader_open_api.endpoints import EndPoints

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.ctrader_account_list_probe import CTraderAccountListProbe  # noqa: E402


class DemoAccountProbe(CTraderAccountListProbe):
    """Зберегти з broker response лише ID рахунку та isLive."""

    def _handle_account_list(self, payload: object) -> None:
        accounts = []
        for account in getattr(payload, "ctidTraderAccount", []):
            account_id = str(getattr(account, "ctidTraderAccountId", "") or "").strip()
            if not account_id:
                continue
            accounts.append(
                {
                    "id": account_id,
                    "mode": (
                        "LIVE" if bool(getattr(account, "isLive", True)) else "DEMO"
                    ),
                }
            )
        self.accounts = accounts


def read_config(path: Path) -> dict:
    """Розшифрувати LGE.conf тільки в пам'яті."""
    if not path.is_file():
        raise RuntimeError("LGE.conf не знайдено")

    if not sys.stdin.isatty():
        raise RuntimeError(
            "Немає інтерактивної консолі. Запусти тест у PowerShell або cmd."
        )

    print("Введи пароль LGE.conf у консолі й натисни Enter.", flush=True)
    print("Символи пароля не відображатимуться — це нормально.", flush=True)
    password = getpass.getpass("Пароль > ")

    if not password:
        raise RuntimeError("Пароль не введено")

    out = io.BytesIO()
    with path.open("rb") as source:
        pyAesCrypt.decryptStream(source, out, password, 64 * 1024)

    data = json.loads(out.getvalue().decode("utf-8"))

    if not isinstance(data, dict):
        raise RuntimeError("Некоректна структура LGE.conf")

    actual = hashlib.sha256(password.encode("utf-8")).hexdigest()
    expected = str(data.get("password_sha256", ""))

    if not hmac.compare_digest(actual, expected):
        raise RuntimeError("Не підтверджено пароль конфігурації")

    return data


def validate_token(path: Path) -> str:
    """Тільки перевірити наявність і термін дії токена, без refresh."""
    if not path.is_file():
        raise RuntimeError("tokens.json не знайдено")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError("Некоректна структура tokens.json")
    token = str(data.get("access_token", "") or "").strip()
    if not token or token in {"new_access_token", "access_token"}:
        raise RuntimeError("Немає придатного access_token")
    if int(data.get("expires_at", 0) or 0) <= int(time.time()):
        raise RuntimeError("Access token прострочений; refresh заборонено")
    return token


def main() -> int:
    parser = argparse.ArgumentParser(description="T116-02 · TEST_ONLY · cTrader DEMO")
    parser.add_argument("--runtime-root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args()
    root = args.runtime_root.expanduser().resolve()
    token_override = os.environ.get("TOKENS_PATH", "").strip()
    token_path = (
        Path(token_override).expanduser().resolve()
        if token_override
        else root / "tokens" / "tokens.json"
    )

    print("T116-02 TEST_ONLY | cTrader DEMO read-only")
    print("order_requests=0")
    print("position_requests=0")
    print("config_writes=0")
    print("token_writes=0")

    secret = ""
    access_token = ""
    try:
        config = read_config(root / "LGE.conf")
        engine = config.get("engine", {})
        ctrader = config.get("ctrader", {})
        if not isinstance(engine, dict) or not isinstance(ctrader, dict):
            raise RuntimeError("Секції engine/ctrader відсутні або некоректні")

        broker = str(engine.get("broker", "") or "").upper().strip()
        engine_mode = str(engine.get("account_mode", "") or "").upper().strip()
        mode = str(ctrader.get("account_mode", "") or "").upper().strip()
        host = str(ctrader.get("host", "") or "").lower().strip()
        port = int(ctrader.get("port", EndPoints.PROTOBUF_PORT))
        account_id = str(ctrader.get("account_id", "") or "").strip()
        client_id = str(ctrader.get("client_id", "") or "").strip()
        secret = str(ctrader.get("client_secret", "") or "").strip()

        print(f"engine_broker={broker or 'MISSING'}")
        print(f"engine_account_mode={engine_mode or 'MISSING'}")
        print(f"ctrader_account_mode={mode or 'MISSING'}")
        print(f"selected_account=***{account_id[-4:] if account_id else 'MISSING'}")

        if engine_mode != "DEMO" or mode != "DEMO":
            raise RuntimeError("Немає узгодженої DEMO-конфігурації engine/ctrader")
        if host and host != str(EndPoints.PROTOBUF_DEMO_HOST).lower():
            raise RuntimeError("Host конфігурації не DEMO endpoint")
        if port != EndPoints.PROTOBUF_PORT:
            raise RuntimeError("Нестандартний порт cTrader Open API")
        if not account_id.isdigit() or not client_id or not secret:
            raise RuntimeError("Некоректні cTrader Account ID / Client ID / Secret")

        access_token = validate_token(token_path)
        os.environ["TOKENS_PATH"] = str(token_path)
        probe = DemoAccountProbe(
            host=EndPoints.PROTOBUF_DEMO_HOST,
            port=EndPoints.PROTOBUF_PORT,
            client_id=client_id,
            client_secret=secret,
        )
        accounts = probe.run()
        print("application_auth=OK")
        print("account_list=OK")
        print("read_only_api_requests=2")
        print(f"accounts_visible={len(accounts)}")

        selected = next((item for item in accounts if item["id"] == account_id), None)
        if selected is None:
            raise RuntimeError("Вибраний рахунок відсутній у відповіді брокера")
        print(f"broker_account_mode={selected['mode']}")
        if selected["mode"] != "DEMO":
            raise RuntimeError("Брокер не підтвердив DEMO для вибраного рахунку")
        print("active_runtime_session=NOT_CHECKED")
        print("T116-02=GREEN_ACCOUNT_DISCOVERY")
        return 0
    except Exception as exc:
        reason = str(exc)
        for value in (secret, access_token):
            if value:
                reason = reason.replace(value, "[REDACTED]")
        print(f"failure={type(exc).__name__}: {reason}")
        print("T116-02=RED")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
