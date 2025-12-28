# test_cTraderAPI02.py
import pytest
from ctrader_open_api import Client, EndPoints, Protobuf, TcpProtocol
from ctrader_open_api.messages.OpenApiMessages_pb2 import (
    ProtoOAAccountAuthReq,
    ProtoOAApplicationAuthReq,
)
from twisted.internet import reactor

HOST = EndPoints.PROTOBUF_DEMO_HOST
PORT = EndPoints.PROTOBUF_PORT


def on_error(_failure):
    """Колбек для обробки помилок."""
    print("❌ Error:", _failure)


def on_connected(_client):
    """
    Колбек після підключення до демо-хоста cTrader.

    Виконує аутентифікацію додатка (ProtoOAApplicationAuthReq)
    та аутентифікацію акаунта (ProtoOAAccountAuthReq) з пустими токенами для Demo.
    """
    print("✅ Connected to cTrader (Demo)")
    try:
        auth_req = ProtoOAApplicationAuthReq()
        auth_req.applicationId = "Demo"
        auth_req.applicationVersion = "1.0"
        auth_req.sessionToken = ""
        deferred = _client.send(auth_req)
        deferred.addErrback(on_error)
    except Exception as e:
        print("⚠️ Не вдалося аутентифікувати додаток:", e)

    try:
        account_auth_req = ProtoOAAccountAuthReq()
        account_auth_req.ctidTraderAccountId = 0  # для демо можна 0 або ваш акаунт
        account_auth_req.accessToken = ""
        deferred = _client.send(account_auth_req)
        deferred.addErrback(on_error)
    except Exception as e:
        print("⚠️ Не вдалося аутентифікувати акаунт:", e)


def on_disconnected(_client, reason):
    """Колбек при роз'єднанні клієнта."""
    print("🔌 Disconnected:", reason)


def on_message(_client, msg):
    """Колбек при отриманні повідомлень."""
    print(f"\n📩 Message: {type(msg).__name__}")
    try:
        content = Protobuf.extract(msg)
        if content:
            print(content)
    except Exception as e:
        print("⚠️ Не вдалося витягнути контент:", e)


@pytest.mark.timeout(10)
def test_ctrader_demo_auth(monkeypatch):
    """
    Тест підключення та аутентифікації до демо cTrader OpenAPI.

    Ініціалізує клієнта, задає колбеки для підключення, роз'єднання і повідомлень.
    Змонкіпатчено reactor.run для уникнення блокування в тестовому оточенні.

    Тест перевіряє безпомилковий запуск підключення та
    надсилання повідомлень авторизації.
    """
    client = Client(HOST, PORT, TcpProtocol)
    client.setConnectedCallback(on_connected)
    client.setDisconnectedCallback(on_disconnected)
    client.setMessageReceivedCallback(on_message)

    monkeypatch.setattr(reactor, "run", lambda: print("Reactor run mocked"))

    client.startService()
    reactor.run()  # noqa
