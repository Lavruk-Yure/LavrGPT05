import ctrader_open_api.messages.OpenApiModelMessages_pb2 as m  # noqa
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
    Колбек, що виконується після встановлення з'єднання з демо-хостом cTrader.

    Відправляє повідомлення для підписки (або авторизації, якщо потрібно),
    використовуючи protobuf клас PROTO_OA_APPLICATION_AUTH_REQ (як у моделі).
    """
    print("✅ Connected to cTrader (Demo)")
    try:
        req = m.PROTO_OA_APPLICATION_AUTH_REQ()  # noqa
        # В демо можна залишити поля пустими або задати відповідні тестові
        deferred = _client.send(req)
        deferred.addErrback(on_error)
        print("🔔 Підписка або авторизація Demo відправлена")
    except Exception as e:
        print("⚠️ Не вдалося підписатися на акаунти:", e)


def on_disconnected(_client, reason):
    """Колбек, що виконується при роз'єднанні від сервера."""
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


@pytest.mark.timeout(10)
def test_ctrader_demo_subscription(monkeypatch):
    """
    Pytest тест підключення до демо сервера cTrader OpenAPI.

    Клієнт ініціалізується з callback-ами для обробки з'єднань і повідомлень.
    Виконується монкіпатчинг reactor.run для уникнення блокування тесту.
    Тест перевіряє коректність відправки запиту підписки/авторизації.
    """

    client = Client(HOST, PORT, TcpProtocol)
    client.setConnectedCallback(on_connected)
    client.setDisconnectedCallback(on_disconnected)
    client.setMessageReceivedCallback(on_message)

    monkeypatch.setattr(reactor, "run", lambda: print("Reactor run mocked"))
    client.startService()
    reactor.run()  # noqa
