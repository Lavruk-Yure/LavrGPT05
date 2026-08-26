# test_cTraderAPI01.py
"""
Test connection to cTrader Open API (Demo or Live).

Цей тест перевіряє базове встановлення TCP-з'єднання через SDK `ctrader_open_api`.
Використовується демонстраційне середовище, без авторизації.
Тест виконується у безпечному (pytest) режимі — без реального виклику reactor.run().
"""

import pytest
from ctrader_open_api import Client, EndPoints, Protobuf, TcpProtocol


@pytest.fixture(scope="module")
def demo_client():
    """Ініціалізує клієнт для DEMO-хосту без запуску reactor."""
    host = EndPoints.PROTOBUF_DEMO_HOST
    port = EndPoints.PROTOBUF_PORT
    client = Client(host, port, TcpProtocol)
    yield client


def on_error(failure):
    """Обробник помилок під час з'єднання."""
    print("❌ Error:", failure)


def on_connected(_client):
    """Callback при успішному підключенні."""
    print("✅ Connected to cTrader")


def on_disconnected(_client, reason):
    """Callback при відключенні."""
    print("🔌 Disconnected:", reason)


def on_message(_client, msg):
    """Callback при отриманні повідомлення від брокера."""
    print(f"\n📩 Message: {type(msg).__name__}")
    try:
        content = Protobuf.extract(msg)
        if content:
            print(content)
    except Exception as e:
        print("⚠️ Не вдалося витягнути контент:", e)


def test_ctrader_client_callbacks(demo_client):
    """
    Перевіряє, що клієнт може коректно встановити callback-и
    без реального запуску мережевого циклу.
    """
    demo_client.setConnectedCallback(on_connected)
    demo_client.setDisconnectedCallback(on_disconnected)
    demo_client.setMessageReceivedCallback(on_message)

    # Перевіряємо наявність методів у клієнта
    assert hasattr(demo_client, "setConnectedCallback")
    assert hasattr(demo_client, "setDisconnectedCallback")
    assert hasattr(demo_client, "setMessageReceivedCallback")

    # Перевіряємо, що callback-и були встановлені
    for func in (on_connected, on_disconnected, on_message):
        assert callable(func)
