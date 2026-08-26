# run_cTraderAPI01.py
# 16.10.2025
# Демонстрація підключення до cTrader Open API (Demo/Live)
# Без авторизації — тільки встановлення з'єднання та отримання повідомлень.

from ctrader_open_api import Client, EndPoints, Protobuf, TcpProtocol
from twisted.internet import reactor as twisted_reactor
from twisted.internet.error import ConnectionLost
from twisted.python import log


def on_connected(_client):
    """Викликається при підключенні до сервера cTrader."""
    print("✅ Connected to cTrader — очікується повідомлення...")


def on_disconnected(_client, reason):
    """Викликається при розриві з'єднання."""
    if isinstance(reason, ConnectionLost):
        print("🔌 З'єднання закрито сервером (ConnectionLost).")
    else:
        print(f"🔌 Disconnected: {reason}")
    # noqa нижче знімає псевдо-помилки PyCharm
    twisted_reactor.callLater(1, twisted_reactor.stop)  # noqa


def on_message(_client, msg):
    """Обробка отриманих повідомлень від сервера."""
    print(f"\n📩 Message: {type(msg).__name__}")
    try:
        content = Protobuf.extract(msg)
        if content:
            print(content)
    except Exception as e:
        print("⚠️ Не вдалося витягнути контент:", e)


def on_error(failure):
    """Обробка помилок клієнта (через reactor)."""
    print("❌ Error:", failure)


def main():
    """Запускає демонстраційне підключення до cTrader Open API."""
    host_type = input("Host (Live/Demo): ").strip().lower()
    host = (
        EndPoints.PROTOBUF_LIVE_HOST
        if host_type == "live"
        else EndPoints.PROTOBUF_DEMO_HOST
    )
    port = EndPoints.PROTOBUF_PORT

    print(f"🌐 Connecting to {host}:{port} ...")

    client = Client(host, port, TcpProtocol)
    client.setConnectedCallback(on_connected)
    client.setDisconnectedCallback(on_disconnected)
    client.setMessageReceivedCallback(on_message)

    # Логування Twisted-подій
    log.startLogging(open("ctrader_reactor.log", "w"))
    twisted_reactor.addSystemEventTrigger(  # noqa
        "after", "shutdown", lambda: print("🟢 Reactor stopped.")
    )

    client.startService()

    try:
        twisted_reactor.run()  # noqa
    except KeyboardInterrupt:
        print("🛑 Зупинено користувачем.")
        twisted_reactor.stop()  # noqa


if __name__ == "__main__":
    main()
