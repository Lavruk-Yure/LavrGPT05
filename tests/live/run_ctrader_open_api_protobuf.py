# run_ctrader_open_api_protobuf.py
from ctrader_open_api import Client, EndPoints, Protobuf, TcpProtocol
from ctrader_open_api.messages.OpenApiMessages_pb2 import ProtoOAApplicationAuthReq
from twisted.internet import reactor

CLIENT_ID = "x"
CLIENT_SECRET = "x"
HOST = EndPoints.PROTOBUF_DEMO_HOST
PORT = EndPoints.PROTOBUF_PORT


def onerror(_failure):
    """
    Колбек для обробки помилок при відправці запитів.
    Виводить текст помилки у консоль.
    """
    print("Message Error:", _failure)


def connected(_client):
    """
    Колбек, що виконується після встановлення з'єднання з cTrader OpenAPI.
    Формує та відправляє запит авторизації додатка з CLIENT_ID і CLIENT_SECRET.
    """
    print("\nConnected")
    request = ProtoOAApplicationAuthReq()
    request.clientId = CLIENT_ID
    request.clientSecret = CLIENT_SECRET

    deferred = _client.send(request)
    deferred.addErrback(onerror)


def disconnected(_client, reason):
    """
    Колбек, що виконується при роз'єднанні від cTrader OpenAPI.
    Виводить причину роз'єднання.
    """
    print("\nDisconnected:", reason)


def on_message_received(_client, message):
    """
    Колбек для обробки вхідних повідомлень від cTrader OpenAPI.
    Виводить декодоване повідомлення
    або повідомляє про порожнє/нерозпізнане повідомлення.
    """
    print("Message received:\n", Protobuf.extract(message))


def main():
    """
    Запускає клієнт cTrader OpenAPI з потрібними колбеками.
    Ініціалізує сервіс і запускає event loop Twisted reactor.
    """
    client = Client(HOST, PORT, TcpProtocol)
    client.setConnectedCallback(connected)
    client.setDisconnectedCallback(disconnected)
    client.setMessageReceivedCallback(on_message_received)

    client.startService()
    reactor.run()  # noqa


if __name__ == "__main__":
    main()
