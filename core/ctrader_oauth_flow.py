# ctrader_oauth_flow.py
"""
core/ctrader_oauth_flow.py

Production-style OAuth flow для cTrader Open API.

Призначення:
- відкрити браузер для cTrader OAuth authorization code flow;
- підняти локальний callback-сервер на localhost;
- отримати authorization code;
- обміняти code на access/refresh token;
- зберегти tokens.json у форматі, сумісному з core.token_manager.

Важливо:
- sandbox OAuth prototype не використовується;
- GUI тут не імпортується;
- модуль можна викликати з діалогу або тестового CLI;
- secrets не логуються.
"""

from __future__ import annotations

import http.server
import logging
import secrets
import socketserver
import threading
import time
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import requests

from core.token_manager import save_tokens

logger = logging.getLogger(__name__)

CTRADER_AUTH_URL = "https://id.ctrader.com/my/settings/openapi/grantingaccess/"
CTRADER_TOKEN_URL = "https://openapi.ctrader.com/apps/token"
DEFAULT_REDIRECT_URI = "http://localhost:8080/"
DEFAULT_SCOPE = "trading"
DEFAULT_TIMEOUT_SECONDS = 120


@dataclass(frozen=True)
class CTraderOAuthSettings:
    """
    Налаштування OAuth-запиту cTrader.
    """

    client_id: str
    client_secret: str
    redirect_uri: str = DEFAULT_REDIRECT_URI
    scope: str = DEFAULT_SCOPE
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS


@dataclass(frozen=True)
class CTraderOAuthResult:
    """
    Результат успішної OAuth-авторизації.
    """

    access_token: str
    refresh_token: str
    expires_in: int
    expires_at: int
    token_type: str


class OAuthCallbackState:
    """
    Спільний стан одноразового localhost callback-сервера.
    """

    def __init__(self, expected_state: str) -> None:
        self.expected_state = expected_state
        self.code = ""
        self.error = ""
        self.state_error = ""
        self.event = threading.Event()


class _OAuthCallbackHandler(http.server.BaseHTTPRequestHandler):
    """
    HTTP handler для прийому одного OAuth callback-запиту.
    """

    server: "_OAuthCallbackServer"

    def do_GET(self) -> None:  # noqa
        """
        Приймає code/state від cTrader redirect URI.
        """
        parsed_url = urlparse(self.path)
        params = parse_qs(parsed_url.query)

        code = self._first(params, "code")
        state = self._first(params, "state")
        error = self._first(params, "error")
        error_description = self._first(params, "error_description")

        callback_state = self.server.callback_state

        if error:
            callback_state.error = f"{error}: {error_description}".strip(": ")
            self._send_html(400, "cTrader authorization failed.")
            callback_state.event.set()
            return

        if not code:
            callback_state.error = "cTrader OAuth callback не містить code."
            self._send_html(400, "Authorization code was not received.")
            callback_state.event.set()
            return

        if state != callback_state.expected_state:
            callback_state.state_error = "cTrader OAuth state mismatch."
            self._send_html(400, "OAuth state mismatch. You can close this window.")
            callback_state.event.set()
            return

        callback_state.code = code
        self._send_html(200, "Authorization received. You can close this window.")
        callback_state.event.set()

    def log_message(self, _format: str, *args: object) -> None:
        """
        Глушить стандартний HTTP-log у stdout/stderr.
        """
        logger.debug("OAuth callback HTTP log suppressed: %s", _format, args)

    @staticmethod
    def _first(params: dict[str, list[str]], key: str) -> str:
        """
        Повертає перше значення query-параметра.
        """
        values = params.get(key, [])
        if not values:
            return ""
        return str(values[0]).strip()

    def _send_html(self, status_code: int, message: str) -> None:
        """
        Відправляє мінімальну HTML-відповідь у браузер.
        """
        html = (
            "<!doctype html>"
            "<html><head><meta charset='utf-8'><title>LGE cTrader OAuth</title></head>"
            f"<body><h2>{message}</h2></body></html>"
        ).encode("utf-8")

        self.send_response(status_code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html)))
        self.end_headers()
        self.wfile.write(html)


OAuthHandlerFactory = Callable[
    [Any, Any, socketserver.TCPServer],
    socketserver.BaseRequestHandler,
]


class _OAuthCallbackServer(socketserver.TCPServer):
    """
    TCPServer із прив'язаним OAuth callback state.
    """

    allow_reuse_address = True

    def __init__(
        self,
        server_address: tuple[str, int],
        callback_state: OAuthCallbackState,
    ) -> None:
        self.callback_state = callback_state

        handler_class: OAuthHandlerFactory = _OAuthCallbackHandler

        super().__init__(server_address, handler_class)


class CTraderOAuthFlow:
    """
    Виконує повний browser OAuth flow для cTrader Open API.
    """

    def __init__(self, settings: CTraderOAuthSettings) -> None:
        self.settings = settings
        self._validate_settings()

    def run(self) -> CTraderOAuthResult:
        """
        Запускає OAuth flow, зберігає tokens.json і повертає результат.
        """
        logger.info("Starting cTrader OAuth flow.")

        state = secrets.token_urlsafe(32)
        callback_state = OAuthCallbackState(expected_state=state)
        host, port = self._parse_local_redirect_uri()

        with _OAuthCallbackServer((host, port), callback_state) as server:
            server_thread = threading.Thread(
                target=server.handle_request,
                name="CTraderOAuthCallbackServer",
                daemon=True,
            )
            server_thread.start()

            auth_url = self._build_auth_url(state)
            logger.debug("Opening cTrader OAuth authorization URL in browser.")
            webbrowser.open(auth_url)

            if not callback_state.event.wait(self.settings.timeout_seconds):
                raise TimeoutError(
                    "cTrader OAuth timeout:" " authorization code not received."
                )

            server_thread.join(timeout=1)

        if callback_state.state_error:
            raise RuntimeError(callback_state.state_error)

        if callback_state.error:
            raise RuntimeError(callback_state.error)

        if not callback_state.code:
            raise RuntimeError("cTrader OAuth authorization code is empty.")

        token_data = self.exchange_code_for_tokens(callback_state.code)
        result = self._normalize_token_response(token_data)
        self._save_result(result, token_data)

        logger.info("cTrader OAuth flow completed successfully.")
        return result

    def exchange_code_for_tokens(self, code: str) -> dict[str, Any]:
        """
        Обмінює authorization code на access/refresh token.
        """
        params = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.settings.redirect_uri,
            "client_id": self.settings.client_id,
            "client_secret": self.settings.client_secret,
        }

        logger.debug("Requesting cTrader access token by authorization code.")
        response = requests.get(
            CTRADER_TOKEN_URL,
            params=params,
            headers={"Accept": "application/json"},
            timeout=30,
        )
        response.raise_for_status()

        data = response.json()
        if not isinstance(data, dict):
            raise RuntimeError("cTrader token endpoint returned invalid JSON.")

        self._raise_for_token_error(data)
        return data

    def refresh_tokens(self, refresh_token: str) -> CTraderOAuthResult:
        """
        Оновлює access token через refresh token і зберігає tokens.json.
        """
        refresh_token = str(refresh_token).strip()
        if not refresh_token:
            raise ValueError("refresh_token is required.")

        params = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self.settings.client_id,
            "client_secret": self.settings.client_secret,
        }

        logger.debug("Refreshing cTrader access token.")
        response = requests.get(
            CTRADER_TOKEN_URL,
            params=params,
            headers={"Accept": "application/json"},
            timeout=30,
        )
        response.raise_for_status()

        data = response.json()
        if not isinstance(data, dict):
            raise RuntimeError("cTrader refresh endpoint returned invalid JSON.")

        self._raise_for_token_error(data)
        result = self._normalize_token_response(data)
        self._save_result(result, data)
        return result

    def _build_auth_url(self, state: str) -> str:
        """
        Формує URL для відкриття у браузері.
        """
        query = urlencode(
            {
                "client_id": self.settings.client_id,
                "redirect_uri": self.settings.redirect_uri,
                "scope": self.settings.scope,
                "product": "web",
                "state": state,
            }
        )
        return f"{CTRADER_AUTH_URL}?{query}"

    def _parse_local_redirect_uri(self) -> tuple[str, int]:
        """
        Перевіряє redirect_uri і повертає host/port для локального сервера.
        """
        parsed = urlparse(self.settings.redirect_uri)
        host = parsed.hostname or "localhost"
        port = parsed.port or 80

        if parsed.scheme != "http":
            raise ValueError(
                "Для локального OAuth callback зараз підтримується тільки http."
            )

        if host not in {"localhost", "127.0.0.1"}:
            raise ValueError("redirect_uri має вказувати на localhost або 127.0.0.1.")

        return host, port

    def _validate_settings(self) -> None:
        """
        Перевіряє обов'язкові OAuth-параметри.
        """
        if not self.settings.client_id.strip():
            raise ValueError("client_id is required.")

        if not self.settings.client_secret.strip():
            raise ValueError("client_secret is required.")

        if not self.settings.redirect_uri.strip():
            raise ValueError("redirect_uri is required.")

        if self.settings.scope not in {"accounts", "trading"}:
            raise ValueError("scope must be 'accounts' or 'trading'.")

        if self.settings.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive.")

    @staticmethod
    def _raise_for_token_error(data: dict[str, Any]) -> None:
        """
        Перевіряє помилку у відповіді token endpoint.
        """
        error_code = str(data.get("errorCode") or data.get("error") or "").strip()
        description = str(
            data.get("description") or data.get("error_description") or ""
        ).strip()

        if error_code:
            message = f"{error_code}: {description}".strip(": ")
            raise RuntimeError(message)

    @staticmethod
    def _normalize_token_response(data: dict[str, Any]) -> CTraderOAuthResult:
        """
        Нормалізує camelCase-відповідь cTrader у внутрішній snake_case-формат.
        """
        access_token = str(
            data.get("accessToken") or data.get("access_token") or ""
        ).strip()
        refresh_token = str(
            data.get("refreshToken") or data.get("refresh_token") or ""
        ).strip()
        token_type = str(
            data.get("tokenType") or data.get("token_type") or "bearer"
        ).strip()

        try:
            expires_in = int(data.get("expiresIn") or data.get("expires_in") or 0)
        except (TypeError, ValueError):
            expires_in = 0

        if not access_token:
            raise RuntimeError("cTrader token response does not contain accessToken.")

        if not refresh_token:
            raise RuntimeError("cTrader token response does not contain refreshToken.")

        if expires_in <= 0:
            raise RuntimeError(
                "cTrader token response does not contain valid expiresIn."
            )

        # Невеликий запас, щоб не використовувати токен на самому краю expiry.
        expires_at = int(time.time()) + expires_in - 60

        return CTraderOAuthResult(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=expires_in,
            expires_at=expires_at,
            token_type=token_type or "bearer",
        )

    @staticmethod
    def _save_result(
        result: CTraderOAuthResult,
        raw_response: dict[str, Any],
    ) -> None:
        """
        Зберігає токени у форматі core.token_manager.
        """
        tokens = {
            "access_token": result.access_token,
            "refresh_token": result.refresh_token,
            "expires_in": result.expires_in,
            "expires_at": result.expires_at,
            "token_type": result.token_type,
            "received_at": int(time.time()),
            "provider": "ctrader",
            "raw_keys": sorted(str(key) for key in raw_response.keys()),
        }
        save_tokens(tokens)


def run_ctrader_oauth_flow(
    client_id: str,
    client_secret: str,
    redirect_uri: str = DEFAULT_REDIRECT_URI,
    scope: str = DEFAULT_SCOPE,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> CTraderOAuthResult:
    """
    Фасадна функція для виклику з UI-діалогу.
    """
    settings = CTraderOAuthSettings(
        client_id=client_id.strip(),
        client_secret=client_secret.strip(),
        redirect_uri=redirect_uri.strip(),
        scope=scope.strip(),
        timeout_seconds=timeout_seconds,
    )
    return CTraderOAuthFlow(settings).run()
