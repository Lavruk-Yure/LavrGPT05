"""
Скрипт для авторизації через cTrader OpenAPI з введенням clientId і
clientSecret з консолі, автоматичним збереженням та оновленням токенів.

Робить:
1. Виводить URL для авторизації.
2. Приймає введення authorization code від користувача.
3. Обмінює код на access_token.
4. Використовує access_token для авторизації та підписки на споти.
5. Автоматично оновлює токен за refresh_token при потребі.
"""

import json
import time
from urllib.parse import quote

import requests
from ctrader_open_api import Client, EndPoints, Protobuf, TcpProtocol
from ctrader_open_api.messages.OpenApiCommonMessages_pb2 import (  # noqa
    ProtoHeartbeatEvent,
    ProtoMessage,
)
from ctrader_open_api.messages.OpenApiMessages_pb2 import (  # noqa
    ProtoOAApplicationAuthReq,
)

# from ctrader_open_api.messages.OpenApiModelMessages_pb2 import *
from twisted.internet import reactor

# ===================== Конфігурація =====================
USE_LIVE = True
host = EndPoints.PROTOBUF_LIVE_HOST if USE_LIVE else EndPoints.PROTOBUF_DEMO_HOST
port = EndPoints.PROTOBUF_PORT

currentAccountId = None
redirect_uri = "http://localhost:8080/"
scope = "trading"

UPDATE_INTERVAL = 10
SPOT_SYMBOL_ID = 1

tokens_file = "tokens.json"


def save_tokens(token_data):
    """Зберігає токени з уніфікованою структурою у файл tokens.json."""
    access = token_data.get("accessToken") or token_data.get("access_token")
    refresh = token_data.get("refreshToken") or token_data.get("refresh_token")
    expires_in = token_data.get("expiresIn") or token_data.get("expires_in") or 0
    now = int(time.time())
    out = {
        "access_token": access,
        "refresh_token": refresh,
        "expires_in": expires_in,
        "expires_at": now + int(expires_in),
        "raw": token_data,
    }
    with open(tokens_file, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=4)
    print("🔒 tokens.json збережено.")


def load_tokens():
    """Завантажує токени з файлу tokens.json або повертає None."""
    try:
        with open(tokens_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa
        return None


def token_is_valid(token):
    """Перевіряє, чи токен ще дійсний (попередження 5 секунд)."""
    if not token:
        return False
    return int(time.time()) + 5 < int(token.get("expires_at", 0))


def refresh_token_http(refresh_token, client_id, client_secret):
    """
    Проводить оновлення токена через refresh token.

    Args:
        refresh_token (str): refresh token
        client_id (str): client id
        client_secret (str): client secret

    Returns:
        dict: оновлені токени
    """
    token_endpoint = "https://openapi.ctrader.com/apps/token"
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    r = requests.post(token_endpoint, data=data, headers=headers, timeout=10)
    r.raise_for_status()
    token_data = r.json()
    if "accessToken" not in token_data and "access_token" not in token_data:
        raise Exception(f"Помилка refresh: {token_data}")
    save_tokens(token_data)
    return token_data


def obtain_token_by_code_interactive(client_id, client_secret):
    """
    Інтерактивно приймає authorization code від користувача, обмінює на токени.

    Args:
        client_id (str)
        client_secret (str)

    Returns:
        dict: отримані токени
    """
    redirect_encoded = quote(redirect_uri, safe="")
    playground_url = (
        f"https://id.ctrader.com/my/settings/openapi/grantingaccess/"
        f"?client_id={client_id}&redirect_uri={redirect_encoded}"
        f"&scope={scope}&product=web"
    )
    print(
        "Перейдіть за цим URL у браузері, увійдіть у свій cTrader та "
        "скопіюйте code з адресного рядка:"
    )
    print(playground_url)
    auth_code = input("Введіть код авторизації (code): ").strip()
    if not auth_code:
        raise SystemExit("Код не введено. Вихід.")

    token_endpoint = "https://openapi.ctrader.com/apps/token"
    params = {
        "grant_type": "authorization_code",
        "code": auth_code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "client_secret": client_secret,
    }
    resp = requests.post(
        token_endpoint,
        data=params,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=10,
    )
    resp.raise_for_status()
    token_data = resp.json()
    save_tokens(token_data)
    return token_data


# ===================== Підготовка клієнта =====================
client = Client(host, port, TcpProtocol)
accessToken = None


# ===================== Колбеки =====================
def on_connected(_c):
    print(f"✅ Connected to cTrader ({'Live' if USE_LIVE else 'Demo'})")
    req = ProtoOAApplicationAuthReq()
    req.clientId = clientId
    req.clientSecret = clientSecret
    d = client.send(req)
    d.addErrback(on_error)
    print("ℹ️ Надіслав ApplicationAuthReq")


def on_disconnected(_c, reason):
    print("🔌 Disconnected:", reason)


def on_error(failure):
    print("❌ Error:", failure)


def on_message(_c, msg):
    try:
        content = Protobuf.extract(msg)
    except Exception as e:
        print("⚠️ Не вдалося витягнути контент:", e)
        return
    if not content:
        return
    cname = type(content).__name__

    if cname == "ProtoHeartbeatEvent":
        return

    print(f"\n📩 Message: {cname}")

    if cname == "ProtoOAApplicationAuthRes":
        print("✅ ApplicationAuth успішний")
        send_get_account_list_by_token()
    elif cname == "ProtoOAGetAccountListByAccessTokenRes":
        process_account_list(content)
    elif cname == "ProtoOAAccountAuthRes":
        print("✅ AccountAuth успішний")
        subscribe_spots(SPOT_SYMBOL_ID, durationSec=60)

        info_req = ProtoOAGetAccountInformationReq()  # noqa
        info_req.ctidTraderAccountId = int(currentAccountId)  # noqa
        d = client.send(info_req)
        d.addErrback(on_error)
        print(
            f"ℹ️ Надіслав ProtoOAGetAccountInformationReq для акаунту "
            f"{currentAccountId}"
        )
    elif cname == "ProtoOAGetAccountInformationRes":
        print(f"💰 Баланс акаунта {getattr(content, 'ctidTraderAccountId', '(none)')}:")
        print(f"   Balance: {getattr(content, 'balance', '(no data)')}")
        print(f"   Equity: {getattr(content, 'equity', '(no data)')}")
        print(f"   Margin: {getattr(content, 'margin', '(no data)')}")
    elif cname == "ProtoOASpotEvent":
        print(
            f"ℹ️ Спот подія: ctidTraderAccountId: {content.ctidTraderAccountId}, "
            f"symbolId: {content.symbolId}, bid: {getattr(content, 'bid', None)}, "
            f"ask: {getattr(content, 'ask', None)}"
        )
    elif cname == "ProtoOASubscribeSpotsRes":
        print(
            f"ℹ️ Підписка на споти підтверджена: ctidTraderAccountId: "
            f"{getattr(content, 'ctidTraderAccountId', None)}"
        )
    elif cname == "ProtoOAErrorRes":
        print(
            f"⚠️ Помилка акаунта "
            f"{getattr(content, 'ctidTraderAccountId', '(none)')}: "
            f"{getattr(content, 'errorCode', '')} - "
            f"{getattr(content, 'description', '')}"
        )
    else:
        print("ℹ️ Інше повідомлення:", content)


# ===================== Запити протоколу =====================
def send_get_account_list_by_token():
    if not accessToken:
        print("⚠️ accessToken відсутній, запит акаунтів не відправляється.")
        return
    req = ProtoOAGetAccountListByAccessTokenReq()  # noqa
    req.accessToken = accessToken
    d = client.send(req)
    d.addErrback(on_error)
    print("ℹ️ Надіслав ProtoOAGetAccountListByAccessTokenReq")


def process_account_list(response):
    global currentAccountId
    try:
        accounts = list(getattr(response, "ctidTraderAccount", []))
        if not accounts:
            print("⚠️ Акаунти не знайдені у відповіді.")
            return
        print("Список акаунтів:")
        for acc in accounts:
            print(
                f"  ID: {getattr(acc, 'ctidTraderAccountId', '(no id)')}, "
                f"Login: {getattr(acc, 'traderLogin', '(no login)')}, "
                f"Live: {getattr(acc, 'isLive', '(no live)')}"
            )
        currentAccountId = getattr(accounts[0], "ctidTraderAccountId", None)
        if currentAccountId:
            send_account_auth_request()
    except Exception as e:
        print("⚠️ Помилка при обробці списку акаунтів:", e)


def send_account_auth_request():
    if currentAccountId is None:
        print("⚠️ currentAccountId не встановлено")
        return
    req = ProtoOAAccountAuthReq()  # noqa
    req.ctidTraderAccountId = int(currentAccountId)
    req.accessToken = accessToken or ""
    d = client.send(req)
    d.addErrback(on_error)
    print(f"✅ Надіслав AccountAuthReq для акаунту {currentAccountId}")


def subscribe_spots(symbol_id, duration_sec=30, subscribe_to_spot_timestamp=False):
    if currentAccountId is None:
        return
    req = ProtoOASubscribeSpotsReq()  # noqa
    req.ctidTraderAccountId = int(currentAccountId)
    req.symbolId.append(int(symbol_id))
    req.subscribeToSpotTimestamp = subscribe_to_spot_timestamp
    d = client.send(req)
    d.addErrback(on_error)
    print(f"✅ Підписка на споти SymbolID={symbol_id} на {duration_sec} сек")
    reactor.callLater(duration_sec, unsubscribe_spots, symbol_id)


def unsubscribe_spots(symbol_id):
    if currentAccountId is None:
        return
    req = ProtoOAUnsubscribeSpotsReq()  # noqa
    req.ctidTraderAccountId = int(currentAccountId)
    req.symbolId.append(int(symbol_id))
    d = client.send(req)
    d.addErrback(on_error)
    print(f"❌ Відписка від спотів SymbolID={symbol_id}")


if __name__ == "__main__":
    clientId = input("Введіть clientId: ").strip()
    clientSecret = input("Введіть clientSecret: ").strip()

    tok = load_tokens()
    if tok and token_is_valid(tok):
        accessToken = tok.get("access_token")
        print("🔑 Використовую збережений access_token.")
    elif tok and tok.get("refresh_token"):
        try:
            print("♻️ Оновлюю токен за refresh_token...")
            newtok = refresh_token_http(
                tok.get("refresh_token"), clientId, clientSecret
            )
            accessToken = newtok.get("AccessToken") or newtok.get("access_token")
        except Exception as e:
            print("❌ Не вдалося оновити токен refresh_token:", e)
            td = obtain_token_by_code_interactive(clientId, clientSecret)
            accessToken = td.get("AccessToken") or td.get("access_token")
    else:
        td = obtain_token_by_code_interactive(clientId, clientSecret)
        accessToken = td.get("AccessToken") or td.get("access_token")

    if not accessToken:
        raise SystemExit(
            "❌ Не вдалося отримати accessToken. Перевір дані та спробуй знову."
        )

    client.startService()
    reactor.run()
