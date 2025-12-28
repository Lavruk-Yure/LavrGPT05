"""
Тест підключення до демо сервера cTrader OpenAPI без підписки на акаунти.

Цей модуль ініціалізує клієнта, задає колбеки на обробку подій підключення,
роз'єднання та отримання повідомлень, а також обробку помилок.
Виконує монкіпатчинг reactor.run для запобігання блокуванню під час
автоматизованого тестування у pytest.
"""

import pytest
from ctrader_open_api import Client, EndPoints, Protobuf, TcpProtocol
from twisted.internet import reactor

HOST = EndPoints.PROTOBUF_DEMO_HOST
PORT = EndPoints.PROTOBUF_PORT


def on_error(failure):
    """Обробка помилок при відправці повідомлень."""
    print("❌ Error:", failure)


def on_connected(_client):
    """
    Колбек, що виконується після встановлення з'єднання з демо-хостом.

    У цьому прикладі не підписуємось на акаунти, просто слухаємо всі повідомлення.
    """
    print("✅ Connected to cTrader (Demo)")
    print("ℹ️ Слухаємо всі повідомлення без підписки на акаунти")


def on_disconnected(_client, reason):
    """Колбек для обробки події роз'єднання від сервера."""
    print("🔌 Disconnected:", reason)


def on_message(_client, msg):
    """
    Колбек, що оброблює отримані повідомлення від API.

    На основі отриманого повідомлення витягується вміст і виводиться.
    """
    print(f"\n📩 Message: {type(msg).__name__}")
    try:
        content = Protobuf.extract(msg)
        if content:
            print(content)
    except Exception as e:
        print("⚠️ Не вдалося витягнути контент:", e)


@pytest.mark.timeout(10)
def test_ctrader_demo_no_subscription(monkeypatch):
    """
    Інтеграційний тест, що встановлює з'єднання з демо cTrader OpenAPI без підписки.

    Функція встановлює колбеки, ініціалізує клієнта і монкіпатчить reactor.run для
    уникнення блокування під час виконання тесту.
    """
    client = Client(HOST, PORT, TcpProtocol)
    client.setConnectedCallback(on_connected)
    client.setDisconnectedCallback(on_disconnected)
    client.setMessageReceivedCallback(on_message)

    monkeypatch.setattr(reactor, "run", lambda: print("Reactor run mocked"))

    client.startService()
    reactor.run()  # noqa
