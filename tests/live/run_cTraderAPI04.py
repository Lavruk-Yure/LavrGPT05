# run_cTraderAPI04.py

import pytest
from ctrader_open_api import Client, EndPoints, Protobuf, TcpProtocol
from twisted.internet import reactor

HOST = EndPoints.PROTOBUF_DEMO_HOST
PORT = EndPoints.PROTOBUF_PORT


def on_error(failure):
    """Обробка помилок при відправленні повідомлень."""
    print("❌ Error:", failure)


def on_connected(_client):
    """Колбек при підключенні до демо-хоста cTrader."""
    print("✅ Connected to cTrader (Demo)")


def on_disconnected(_client, reason):
    """Колбек при роз'єднанні від сервера."""
    print("🔌 Disconnected:", reason)


def on_message(_client, msg):
    """Колбек отримання повідомлень API."""
    print(f"\n📩 Message: {type(msg).__name__}")
    try:
        content = Protobuf.extract(msg)
        if content:
            print(content)
    except Exception as e:
        print("⚠️ Не вдалося витягнути контент:", e)


@pytest.mark.timeout(10)
def test_ctrader_demo_connection(monkeypatch):
    """
    Тест підключення до демо хоста cTrader OpenAPI без авторизації.

    Клієнт ініціалізується з колбеками підключення, роз'єднання і прийняття повідомлень.
    Монкіпатчиться reactor.run, щоб тест не блокувався під час виконання.
    """
    client = Client(HOST, PORT, TcpProtocol)
    client.setConnectedCallback(on_connected)
    client.setDisconnectedCallback(on_disconnected)
    client.setMessageReceivedCallback(on_message)

    monkeypatch.setattr(reactor, "run", lambda: print("Reactor run mocked"))
    client.startService()
    reactor.run()  # noqa
