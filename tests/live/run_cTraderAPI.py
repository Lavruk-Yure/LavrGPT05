# run_cTraderAPI.py
import pytest
from ctrader_open_api import Client, EndPoints, Protobuf, TcpProtocol
from ctrader_open_api.messages.OpenApiMessages_pb2 import ProtoOAApplicationAuthReq
from twisted.internet import reactor

from core.lang_manager import LangManager

lang = LangManager()


CLIENT_ID = "x"
CLIENT_SECRET = "x"
HOST = EndPoints.PROTOBUF_LIVE_HOST
PORT = EndPoints.PROTOBUF_PORT


def on_error(_failure):
    """Колбек при виникненні помилки."""
    print(lang.t("generic_error").format(error=_failure))


def on_connected(_client):
    """Колбек при встановленому з'єднанні - надсилаємо авторизаційний запит."""
    print(lang.t("ctrader_connected_simple"))

    req = ProtoOAApplicationAuthReq()
    req.clientId = CLIENT_ID
    req.clientSecret = CLIENT_SECRET
    d = _client.send(req)
    d.addErrback(on_error)


def on_disconnected(_client, reason):
    """Колбек при роз'єднанні."""
    print(lang.t("ctrader_disconnected").format(reason=reason))


def on_message(_client, msg):
    """Колбек для отримання повідомлень."""
    try:
        decoded = Protobuf.extract(msg)
        if decoded:
            print(
                lang.t("ctrader_message_received").format(name=decoded.DESCRIPTOR.name)
            )

            print(decoded)
        else:
            print(lang.t("ctrader_empty_or_unsupported_message").format(msg=msg))

    except Exception as e:
        print(lang.t("extract_failed").format(error=e))


@pytest.mark.timeout(10)
def test_ctrader_connection(monkeypatch):
    """
    Проводить базовий тест підключення до cTrader OpenAPI через SDK.

    Ініціалізує Client, задає колбеки та запускає сервіс.
    Завдяки monkeypatch замінює reactor.run, щоб тест не блокувався.
    Перевіряє, що ініціалізація і старт клієнта відбуваються без помилок.
    """

    client = Client(HOST, PORT, TcpProtocol)
    client.setConnectedCallback(on_connected)
    client.setDisconnectedCallback(on_disconnected)
    client.setMessageReceivedCallback(on_message)

    monkeypatch.setattr(reactor, "run", lambda: print(lang.t("reactor_run_mocked")))

    client.startService()
    reactor.run()  # noqa


def main():
    """
    Програма для запуску клієнта cTrader OpenAPI.

    Ініціалізує клієнта, встановлює колбеки та запускає сервіс із власним event loop.
    Використовується для інтерактивного запуску поза тестуванням.
    """

    client = Client(HOST, PORT, TcpProtocol)
    client.setConnectedCallback(on_connected)
    client.setDisconnectedCallback(on_disconnected)
    client.setMessageReceivedCallback(on_message)

    client.startService()
    reactor.run()  # noqa


if __name__ == "__main__":
    main()
