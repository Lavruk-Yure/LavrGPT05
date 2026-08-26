# run_cTraderAPI06.py
# run_cTraderAPI06.py

"""
Проєкт для підключення до демо сервера cTrader OpenAPI без підписки на акаунти.

Цей скрипт ініціалізує клієнта, прив'язує колбеки для обробки подій,
запускає сервіс і реактор, а також використовує монкіпатчинг для
запобігання блокувань під час тестування.
"""

import pytest
from ctrader_open_api import Client, EndPoints, Protobuf, TcpProtocol
from twisted.internet import reactor

HOST = EndPoints.PROTOBUF_DEMO_HOST
PORT = EndPoints.PROTOBUF_PORT


def on_error(failure):
    """Обробка помилок при відправленні повідомлень."""
    print("❌ Error:", failure)


def on_connected(_client):
    """Колбек, що виконується при підключенні до сервера."""
    print("✅ Connected to cTrader (Demo)")


def on_disconnected(_client, reason):
    """Колбек, що виконується при роз'єднанні від сервера."""
    print("🔌 Disconnected:", reason)


def on_message(_client, msg):
    """Обробка вхідних повідомлень від API."""
    print(f"\n📩 Message: {type(msg).__name__}")
    try:
        content = Protobuf.extract(msg)
        if content:
            print(content)
    except Exception as e:
        print("⚠️ Не вдалося витягнути контент:", e)


@pytest.mark.timeout(10)
def test_ctrader_no_subscription(monkeypatch):
    """
    Тестовий сценарій для підключення до демо сервера без підписки.

    Встановлює колбеки, монкіпатчить reactor.run, виконує запуск клієнта.
    """
    client = Client(HOST, PORT, TcpProtocol)
    client.setConnectedCallback(on_connected)
    client.setDisconnectedCallback(on_disconnected)
    client.setMessageReceivedCallback(on_message)

    # Монкіпатч для уникнення блокування тесту
    monkeypatch.setattr(reactor, "run", lambda: print("Reactor run mocked"))

    # Запуск сервісу
    client.startService()
    reactor.run()  # noqa
