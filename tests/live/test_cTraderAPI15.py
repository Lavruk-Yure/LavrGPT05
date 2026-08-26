# test_cTraderAPI15.py
"""
Pytest для run_cTraderAPI15.py — мокований інтеграційний сценарій авторизації.

"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))  # noqa

import builtins  # noqa
import types  # noqa
from typing import Any  # noqa

import pytest  # noqa

import tests.live.run_cTraderAPI15  # noqa


class DummyDriver:
    """Мок WebDriver: зберігає current_url і має execute_script/quit."""

    def __init__(self):
        self.current_url = "about:blank"
        self._logged_in = False

    def get(self, url: str) -> None:
        self.current_url = url

    def execute_script(self, _script: str) -> str:  # noqa
        # Виклик для document.readyState -> повертаємо "complete"
        return "complete"

    def quit(self) -> None:
        self.current_url = "about:blank"


class MockElement:
    """Мок елементів форми (input/button)."""

    def __init__(self, driver: DummyDriver, role: str):
        self.driver = driver
        self.role = role  # 'email', 'password', 'login', 'allow'

    def clear(self) -> None:  # noqa
        return None

    def send_keys(self, _value: str) -> None:  # noqa
        # нічого не робимо — просто для сумісності
        return None

    def click(self) -> None:
        # Симулюємо натискання логіну або дозволу
        if self.role == "login":
            self.driver._logged_in = True
        elif self.role == "allow":
            # ставимо редірект на redirect_uri з ?code=
            self.driver.current_url = "http://localhost:8080/?code=TEST_AUTH_CODE"


# class DummyWait:
#     """
#     Мок WebDriverWait.until: якщо callable повертає True -> повертає True.
#     Інакше послідовно повертає MockElement для введення/кліків.
#     """
#
#     def __init__(self, driver: DummyDriver, _timeout: int):
#         self.driver = driver
#         self._counter = 0
#
#     def until(self, condition: Any, _timeout: int | None = None) -> Any:
#         try:
#             if callable(condition) and condition(self.driver):
#                 return True
#         except Exception as exc:  # noqa: BLE001
#             raise RuntimeError("Unexpected condition error") from exc
#
#         role_map = {0: "email", 1: "password", 2: "login", 3: "allow"}
#         role = role_map.get(self._counter, "generic")
#         self._counter += 1
#         return MockElement(self.driver, role)


class DummyWait:
    def __init__(self, driver: DummyDriver, _timeout: int):
        self.driver = driver
        self._counter = 0

    def until(self, _condition: Any, _timeout: int | None = None) -> Any:
        # Імітація очікувань: просто повертаємо різні моки по черзі без виклику callable
        role_map = {0: "email", 1: "password", 2: "login", 3: "allow"}
        role = role_map.get(self._counter, "generic")
        self._counter += 1
        return MockElement(self.driver, role)


class DummyResponse:
    def __init__(self, status_code: int = 200, data: dict[str, Any] | None = None):
        self.status_code = status_code
        self._data = data or {}

    def json(self) -> dict[str, Any]:
        return self._data


@pytest.fixture(autouse=True)
def patch_external(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """
    Патчимо зовнішнє оточення:
    - webdriver.Edge -> DummyDriver
    - WebDriverWait -> DummyWait
    - requests.post -> повертає токени
    - builtins.input -> ітератор вводів
    - run_cTraderAPI15.save_tokens -> зберігає у локальний dict
    - time.sleep -> no-op
    """
    monkeypatch.setattr(
        tests.live.run_cTraderAPI15.webdriver, "Edge", lambda *_, **__: DummyDriver()
    )
    monkeypatch.setattr(
        tests.live.run_cTraderAPI15,
        "WebDriverWait",
        lambda driver, timeout: DummyWait(driver, timeout),
    )

    fake_tokens = {
        "access_token": "FAKE_ACCESS_TOKEN",
        "refresh_token": "FAKE_REFRESH_TOKEN",
        "expires_in": 3600,
    }
    monkeypatch.setattr(
        tests.live.run_cTraderAPI15.requests,
        "post",
        lambda *_, **__: DummyResponse(200, fake_tokens),
    )

    inputs = iter(
        ["fake_client_id", "fake_client_secret", "user@example.com", "password123"]
    )
    monkeypatch.setattr(builtins, "input", lambda _prompt="": next(inputs))

    saved: dict[str, Any] = {}

    def fake_save_tokens(data: dict[str, Any]) -> None:
        saved.clear()
        saved.update(data)

    monkeypatch.setattr(tests.live.run_cTraderAPI15, "save_tokens", fake_save_tokens)
    monkeypatch.setattr(
        tests.live.run_cTraderAPI15,
        "time",
        types.SimpleNamespace(
            sleep=lambda *_: None, time=tests.live.run_cTraderAPI15.time.time
        ),
    )

    return {"saved": saved}


def test_full_token_flow(patch_external: dict[str, Any]) -> None:
    """Повний мокований потік: main() має зберегти токени через save_tokens."""
    saved = patch_external["saved"]

    tests.live.run_cTraderAPI15.main()

    assert saved["access_token"] == "FAKE_ACCESS_TOKEN"
    assert saved["refresh_token"] == "FAKE_REFRESH_TOKEN"
    assert saved["expires_in"] == 3600
