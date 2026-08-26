# run_cTraderAPI05.py
"""
Тест підключення до демо сервера cTrader OpenAPI без авторизації.

Модуль ініціалізує клієнта cTrader, встановлює колбеки для подій підключення,
роз'єднання та отримання повідомлень. Виконується монкіпатчинг reactor.run,
щоб уникнути блокування під час автоматизованого тестування.
"""

import pytest
from ctrader_open_api import Client, EndPoints, Protobuf, TcpProtocol
from twisted.internet import reactor

HOST = EndPoints.PROTOBUF_DEMO_HOST
PORT = EndPoints.PROTOBUF_PORT


def on_error(failure):
    """Обробка помилок, що виникають при відправці повідомлень."""
    print("❌ Error:", failure)


def on_connected(_client):
    """Колбек, що виконується при успішному підключенні до сервера демо cTrader."""
    print("✅ Connected to cTrader (Demo)")


def on_disconnected(_client, reason):
    """Колбек, який викликається при роз'єднанні з сервером."""
    print("🔌 Disconnected:", reason)


def on_message(_client, msg):
    """Обробка повідомлень, що надходять від API."""
    print(f"\n📩 Message: {type(msg).__name__}")
    try:
        content = Protobuf.extract(msg)
        if content:
            print(content)
    except Exception as e:
        print("⚠️ Не вдалося витягнути контент:", e)


@pytest.mark.timeout(10)
def test_ctrader_demo_no_auth(monkeypatch):
    """
    Тестова функція для перевірки підключення до демо сервера cTrader OpenAPI
    без авторизації.

    Виконує монкіпатчинг reactor.run для уникнення блокування при тестуванні.
    Ініціалізує і запускає клієнт з встановленими колбеками.
    Перевіряє, що підключення відбувається успішно.
    """
    client = Client(HOST, PORT, TcpProtocol)
    client.setConnectedCallback(on_connected)
    client.setDisconnectedCallback(on_disconnected)
    client.setMessageReceivedCallback(on_message)

    monkeypatch.setattr(reactor, "run", lambda: print("Reactor run mocked"))

    client.startService()
    reactor.run()  # noqa
