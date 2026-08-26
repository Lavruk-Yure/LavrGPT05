# brokers\ctrader_sandbox_oauth.py

"""Модуль реалізує простий локальний HTTP сервер для отримання
OAuth authorization code через редірект,
автоматично відкриває браузер для авторизації користувача,
і здійснює обмін отриманого коду на Access Token.

Використовує стандартні бібліотеки http.server, socketserver, threading, webbrowser
та requests для HTTP-запитів.
"""

import http.server
import socketserver
import threading
import webbrowser
from urllib.parse import parse_qs, urlparse

import requests

from core.lang_manager import LangManager

lang = LangManager()


# --- Налаштування ---
CLIENT_ID = "x"  # Ваш client_id
# Ваш client_secret
CLIENT_SECRET = "x"
REDIRECT_URI = "http://localhost:8080/"
AUTH_URL = (
    f"https://id.ctrader.com/connect/authorize?"
    f"client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&"
    "response_type=code&scope=trading"
)

# --- Змінна для зберігання коду ---
authorization_code = None


class OAuthHandler(http.server.BaseHTTPRequestHandler):
    def __init__(self, request, client_address, server):
        super().__init__(request, client_address, server)

    def do_GET(self):  # noqa
        global authorization_code
        query = urlparse(self.path).query
        params = parse_qs(query)
        if "code" in params:
            authorization_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<html><body><h2>Authorization code received. "
                b"You can close this window.</h2></body></html>"
            )
        else:
            self.send_response(400)
            self.end_headers()

    def log_message(self, format, *args):  # noqa
        return


# --- Запуск локального сервера ---
def start_server():
    # with socketserver.TCPServer(("localhost", 8080), OAuthHandler) as httpd:
    #     httpd.handle_request()  # обробити один запит
    with socketserver.TCPServer(
        ("localhost", 8080), OAuthHandler  # type: ignore[arg-type]
    ) as httpd:
        httpd.handle_request()


if __name__ == "__main__":
    # Запускаємо HTTP сервер в окремому потоці
    server_thread = threading.Thread(target=start_server)
    server_thread.start()

    # Відкриваємо браузер для авторизації користувача
    print("Відкрий браузер та авторизуйся у Spotware Sandbox...")
    webbrowser.open(AUTH_URL)

    # Чекаємо, поки сервер отримає authorization_code
    server_thread.join()

    if authorization_code:
        print(f"Authorization code: {authorization_code}")  # noqa

        # Обмінюємо authorization code на access token
        token_url = "https://connect.spotware.com/connect/token"
        data = {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "grant_type": "authorization_code",
            "code": authorization_code,
            "redirect_uri": REDIRECT_URI,
        }
        response = requests.post(token_url, data=data)
        token_data = response.json()
        print("\n=== Access Token Data ===")
        print(token_data)
    else:
        print("Authorization code не отримано.")
