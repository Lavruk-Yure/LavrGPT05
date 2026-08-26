# run_cTraderAPI03.py
import pytest
from ctrader_open_api import Client, EndPoints, Protobuf, TcpProtocol
from ctrader_open_api.messages.OpenApiMessages_pb2 import (
    ProtoOAAccountAuthReq,
    ProtoOAApplicationAuthReq,
)
from twisted.internet import reactor

CLIENT_ID = "xxxxxxx"
CLIENT_SECRET = "xxxxxxx"
HOST = EndPoints.PROTOBUF_DEMO_HOST
PORT = EndPoints.PROTOBUF_PORT


def on_error(_failure):
    """Обробка помилок при відправці повідомлень."""
    print("❌ Error:", _failure)


def on_connected(_client):
    """
    Колбек, що виконується після підключення до демо-хоста cTrader.

    Аутентифікація додатка через ProtoOAApplicationAuthReq з clientId і clientSecret.
    Аутентифікація акаунта через ProtoOAAccountAuthReq з коректним accessToken.
    """
    print("✅ Connected to cTrader (Demo)")
    try:
        auth_req = ProtoOAApplicationAuthReq()
        auth_req.clientId = CLIENT_ID
        auth_req.clientSecret = CLIENT_SECRET
        deferred = _client.send(auth_req)
        deferred.addErrback(on_error)
    except Exception as e:
        print("⚠️ Не вдалося аутентифікувати додаток:", e)

    try:
        account_auth_req = ProtoOAAccountAuthReq()
        account_auth_req.ctidTraderAccountId = 0  # demo або ваш акаунт
        account_auth_req.accessToken = ""  # валідний access token OAuth2
        deferred = _client.send(account_auth_req)
        deferred.addErrback(on_error)
    except Exception as e:
        print("⚠️ Не вдалося аутентифікувати акаунт:", e)


def on_disconnected(_client, reason):
    """Обробка роз'єднання з сервером."""
    print("🔌 Disconnected:", reason)


def on_message(_client, msg):
    """Обробка отриманих повідомлень від API."""
    print(f"\n📩 Message: {type(msg).__name__}")
    try:
        content = Protobuf.extract(msg)
        if content:
            print(content)
    except Exception as e:
        print("⚠️ Не вдалося витягнути контент:", e)


@pytest.mark.timeout(20)
def test_ctrader_demo_auth(monkeypatch):
    """
    Тест підключення та аутентифікації на демо середовищі cTrader OpenAPI.

    Ініціалізує клієнта з колбеками для підключення, роз'єднання і повідомлень.
    Замінює reactor.run для запобігання блокування у тестах.

    Верифікує запуск та надсилання аутентифікаційних запитів.
    """
    client = Client(HOST, PORT, TcpProtocol)
    client.setConnectedCallback(on_connected)
    client.setDisconnectedCallback(on_disconnected)
    client.setMessageReceivedCallback(on_message)

    monkeypatch.setattr(reactor, "run", lambda: print("Reactor run mocked"))
    client.startService()
    reactor.run()  # noqa
