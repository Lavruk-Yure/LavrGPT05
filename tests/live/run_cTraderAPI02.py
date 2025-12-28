from ctrader_open_api import Client, EndPoints, Protobuf, TcpProtocol
from ctrader_open_api.messages.OpenApiMessages_pb2 import ProtoOAAccountAuthReq  # noqa
from ctrader_open_api.messages.OpenApiMessages_pb2 import (  # noqa; noqa
    ProtoOAApplicationAuthReq,
)
from twisted.internet import reactor


def on_error(_failure):
    """
    Обробка помилок при відправці повідомлень.

    Args:
        _failure: Об'єкт помилки Deferred
    """
    print("❌ Error:", _failure)


# def on_connected(_client, client_id, client_secret):
#         """
#         Після підключення виконує аутентифікацію додатка
#         і акаунта через ProtoOAApplicationAuthReq та ProtoOAAccountAuthReq.
#
#         Args:
#             _client: Об'єкт клієнта
#             client_id (str): Ідентифікатор клієнта
#             client_secret (str): Секрет клієнта
#         """
#         print("✅ Connected to cTrader (Demo)")
#
#     try:
#         auth_req = ProtoOAApplicationAuthReq()
#         auth_req.clientId = client_id
#         auth_req.clientSecret = client_secret
#         auth_req.sessionToken = ""  # за необхідності
#
#         deferred = _client.send(auth_req)
#         deferred.addErrback(on_error)
#     except Exception as e:
#         print("⚠️ Не вдалося аутентифікувати додаток:", e)
#
#     try:
#         account_auth_req = ProtoOAAccountAuthReq()
#         account_auth_req.ctidTraderAccountId = 0  # Для демо
#         account_auth_req.accessToken = ""
#         deferred = _client.send(account_auth_req)
#         deferred.addErrback(on_error)
#     except Exception as e:
#         print("⚠️ Не вдалося аутентифікувати акаунт:", e)


def on_connected(_client, client_id, client_secret):
    print("✅ Connected to cTrader (Demo)")

    try:
        auth_req = ProtoOAApplicationAuthReq()
        auth_req.clientId = client_id
        auth_req.clientSecret = client_secret
        deferred = _client.send(auth_req)
        deferred.addErrback(on_error)
        print("🔑 Application auth request sent.")
    except Exception as e:
        print("⚠️ Помилка при автентифікації додатка:", e)


def on_disconnected(_client, reason):
    """
    Обробка роз'єднання від сервера.

    Args:
        _client: Об'єкт клієнта
        reason: Причина роз'єднання
    """
    print("🔌 Disconnected:", reason)


def on_message(_client, msg):
    """
    Обробка отриманих повідомлень від API.

    Args:
        _client: Об'єкт клієнта
        msg: Отримане повідомлення
    """
    print(f"\n📩 Message: {type(msg).__name__}")
    try:
        content = Protobuf.extract(msg)
        if content:
            print(content)
    except Exception as e:
        print("⚠️ Не вдалося витягнути контент:", e)


def main():
    """
    Головна функція запуску клієнта cTrader OpenAPI.
    Запитує clientId та clientSecret,
    встановлює колбеки з передачою облікових даних,
    і запускає подієвий цикл twisted.
    """
    client_id = input("Введіть CLIENT_ID: ").strip()
    client_secret = input("Введіть CLIENT_SECRET: ").strip()

    host = EndPoints.PROTOBUF_DEMO_HOST
    port = EndPoints.PROTOBUF_PORT

    client = Client(host, port, TcpProtocol)

    # Встановлюємо колбеки з використанням Лямбда для передачі параметрів
    client.setConnectedCallback(lambda c: on_connected(c, client_id, client_secret))
    client.setDisconnectedCallback(on_disconnected)
    client.setMessageReceivedCallback(on_message)

    client.startService()
    reactor.run()  # noqa


if __name__ == "__main__":
    main()
