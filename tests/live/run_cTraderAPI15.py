# run_cTraderAPI15.py – автоматичне отримання authorization code та інтеграція
"""
token_manager.py для LavrGPT05

Увага!!!
Запуск для робочої директорії
D:\\LavrGPT\\Lavr #n
"""
import time
import urllib.parse

import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.options import Options
from selenium.webdriver.edge.service import Service
from selenium.webdriver.support import expected_conditions as EC  # noqa
from selenium.webdriver.support.ui import WebDriverWait

from core.token_manager import refresh_if_needed, save_tokens


# --- Функція для отримання access_token з автооновленням ---
def get_access_token():
    tokens = refresh_if_needed()
    if tokens:
        print(f"[token_manager] Access token: {tokens['access_token']}")
        return tokens["access_token"]
    else:
        print(
            "[token_manager] Tokens missing. "
            "Потрібно пройти авторизацію через Selenium."
        )
        return None


def exchange_auth_code_for_tokens(auth_code, client_id, client_secret, redirect_uri):
    """Обмінює authorization_code на токени."""
    token_url = "https://openapi.ctrader.com/apps/token"
    data = {
        "grant_type": "authorization_code",
        "code": auth_code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "client_secret": client_secret,
    }
    response = requests.post(
        token_url,
        data=data,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Помилка при отриманні токену: HTTP {response.status_code}")
        print("Текст відповіді:", response.text)
        return None


def main():
    print("=== Авторизація cTrader OpenAPI (LavrGPT05) ===")

    # --- введення даних з консолі ---
    client_id = input("Введіть client_id: ").strip()
    client_secret = input("Введіть client_secret: ").strip()  # noqa: F841
    login = input("Введіть логін (Email або cTrader ID): ").strip()
    password = input("Введіть пароль: ").strip()

    redirect_uri = "http://localhost:8080/"
    scope = "trading"

    redirect_uri_encoded = urllib.parse.quote(redirect_uri, safe="")
    auth_url = (
        f"https://id.ctrader.com/my/settings/openapi/grantingaccess/"
        f"?client_id={client_id}&redirect_uri={redirect_uri_encoded}"
        f"&scope={scope}&product=web"
    )

    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")

    service = Service(executable_path=r"C:\WebDriver\msedgedriver.exe")
    driver = webdriver.Edge(service=service, options=options)

    auth_code = None  # ініціалізація, щоб код після finally був досяжним # noqa
    try:
        driver.get(auth_url)
        wait = WebDriverWait(driver, 20)
        wait.until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )

        # Вводимо login
        try:
            email_input = wait.until(EC.visibility_of_element_located((By.NAME, "id")))
            email_input.clear()
            email_input.send_keys(login)
        except Exception as error:
            print("[WARN] Не вдалося знайти/заповнити поле логіну:", error)

        # Вводимо пароль
        try:
            password_input = wait.until(
                EC.visibility_of_element_located((By.NAME, "password"))
            )
            password_input.clear()
            password_input.send_keys(password)
        except Exception as error:
            print("[WARN] Не вдалося знайти/заповнити поле паролю:", error)

        # Натискаємо кнопку "Log in"
        try:
            login_button = wait.until(
                EC.element_to_be_clickable(
                    (By.CSS_SELECTOR, 'button.auth-form-btn[type="submit"]')
                )
            )
            login_button.click()
            print("✅ Log In натиснуто")
        except Exception as error:
            print("[WARN] Кнопка Log In не знайдена/не натиснута:", error)

        # Очікуємо кнопку "Дать разрешение" (не обов'язково — може бути збережено)
        try:
            permission_button = wait.until(
                EC.element_to_be_clickable((By.ID, "auth-btn-allow"))
            )
            driver.execute_script(
                "arguments[0].scrollIntoView(true);", permission_button
            )
            time.sleep(1)
            permission_button.click()
            print("✅ Дозвіл доступу надано")
        except Exception as error:
            print(
                f"⚠️ Кнопка дозволу не знайдена — можливо, "
                f"дозвіл вже збережено ({error})."
            )

        # Очікуємо редірект на redirect_uri
        try:
            wait.until(EC.url_contains(redirect_uri))
            current_url = driver.current_url
            print("Поточна URL після надання дозволу:", current_url)

            parsed_url = urllib.parse.urlparse(current_url)
            query_params = urllib.parse.parse_qs(parsed_url.query)
            auth_code = query_params.get("code", [None])[0]
            if auth_code:
                print("Отримано код авторизації:", auth_code)
            else:
                print("Код авторизації не знайдено у URL!")
                # не повертаємо тут, дозволяємо виконатися finally, потім
                # перевіримо auth_code
        except Exception as error:
            print("[ERROR] Редірект або отримання коду не вдалося:", error)
            # auth_code лишиться None
    finally:
        try:
            driver.quit()
        except Exception as error:
            print("[WARN] Не вдалося коректно закрити драйвер:", error)

    # --- Обробка auth_code (після finally) ---
    if not auth_code:  # noqa
        print("Код авторизації відсутній, пропускаємо отримання токену.")
        return

    token_data = exchange_auth_code_for_tokens(  # noqa
        auth_code, client_id, client_secret, redirect_uri
    )
    if token_data:  # noqa
        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        expires_in = token_data.get("expires_in", 0)

        print("Access token:", access_token)
        print("Refresh token:", refresh_token)

        save_tokens(
            {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "expires_in": expires_in,
                "expires_at": int(time.time()) + expires_in,
                "_comment": "Отримано через run_cTraderAPI15.py",
            }
        )
    else:
        print("Отримати токени не вдалося.")


if __name__ == "__main__":
    main()
