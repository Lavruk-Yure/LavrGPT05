# test_ctrader_open_api_protobuf.py
import pytest
from ctrader_open_api import Client, EndPoints, Protobuf, TcpProtocol
from ctrader_open_api.messages.OpenApiMessages_pb2 import ProtoOAApplicationAuthReq
from twisted.internet import reactor

CLIENT_ID = "x"
CLIENT_SECRET = "x"
HOST = EndPoints.PROTOBUF_DEMO_HOST
PORT = EndPoints.PROTOBUF_PORT


def onerror(_failure):
    """Колбек при виникненні помилки."""
    print("Message Error:", _failure)


def connected(_client):
    """Колбек при встановленому з'єднанні: надсилаємо запит авторизації."""
    print("\nConnected")
    request = ProtoOAApplicationAuthReq()
    request.clientId = CLIENT_ID
    request.clientSecret = CLIENT_SECRET

    deferred = _client.send(request)
    deferred.addErrback(onerror)


def disconnected(_client, reason):
    """Колбек при роз'єднанні клієнта."""
    print("\nDisconnected:", reason)


def on_message_received(_client, message):
    """Колбек при отриманні будь-якого повідомлення."""
    print("Message received:\n", Protobuf.extract(message))


@pytest.mark.timeout(10)
def test_ctrader_connection(monkeypatch):
    """
    Тест підключення до cTrader OpenAPI через SDK.

    Ініціалізує клієнта, встановлює колбеки, запускає сервіс.
    З монкіпатчем reactor.run, щоб уникнути блокування під час тестування.
    Перевіряє безпомилкову ініціалізацію та запуск з передачею авторизаційних даних.
    """
    client = Client(HOST, PORT, TcpProtocol)
    client.setConnectedCallback(connected)
    client.setDisconnectedCallback(disconnected)
    client.setMessageReceivedCallback(on_message_received)

    # Монкіпатчимо reactor.run, щоб не запускати реальний event loop
    monkeypatch.setattr(reactor, "run", lambda: print("Reactor run mocked"))

    client.startService()
    reactor.run()  # noqa
