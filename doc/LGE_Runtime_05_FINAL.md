# LGE_Runtime_05.md

# Архітектура LGE Runtime — канонічний документ

Дата створення: 2026-06-09
Проєкт: LavrGPT05 / LGE
Статус: канонічний Runtime-документ, актуалізований після live IB Paper/read-only перевірок 04–05.08.2026
Остання актуалізація: 2026-08-05
Поточна Runtime schema: v8
Мова документа: українська

---

# 1. Призначення документа

`LGE_Runtime_05.md` є єдиним канонічним Runtime-документом для LGE після об'єднання попередніх Runtime-документів:

1. `LGE_Runtime.md`
2. `LGE_Runtime_00.md`
3. `LGE_Runtime_01.md`
4. `LGE_Runtime_02.md`
5. `LGE_Runtime_03.md`
6. `LGE_Runtime_04.md`

Попередні документи залишаються історичними матеріалами й журналом еволюції рішень.
Поточна архітектурна істина для Runtime — цей документ.

---

# 2. Межі документа

Цей документ описує тільки Runtime-архітектуру LGE:

1. запуск;
2. конфігурацію;
3. брокерські сервіси;
4. життєвий цикл сесій;
5. перепідключення;
6. сховище Runtime у SQLite;
7. події Runtime;
8. стан брокера;
9. стан рахунку;
10. межі інтерфейсу.

Цей документ НЕ описує торгові алгоритми.

Для торгових правил, Forex-логіки, патернів, сигналів, керування ризиками та тестування на історичних даних буде окремий документ:

```text
LGE_Algorithms_01.md
```

---

# 3. Головне правило архітектури

LGE Runtime будується за класичною багаторівневою схемою:

```text
GUI
↓
RuntimeEngine
↓
Broker Runtime Service
↓
SessionManager
↓
Adapter
↓
Broker API / Terminal
```

GUI не має працювати напряму із сокетами брокера, Twisted, IB API, cTrader OpenAPI або тестовими скриптами перевірки.

---

# 4. Головне правило `LGE.conf`

`LGE.conf` містить тільки:

1. налаштування користувача;
2. наміри користувача;
3. параметри підключення;
4. вибрані ідентифікатори рахунків;
5. вибраний режим виконання;
6. політику автоматичного підключення.

`LGE.conf` НЕ містить runtime-фактів.

## 4.1. Дозволено зберігати в `LGE.conf`

```json
{
  "engine": {
    "execution_mode": "SEMI",
    "auto_connect": {
      "ib": true,
      "ctrader": true
    }
  },
  "ib": {
    "host": "127.0.0.1",
    "port": 7497,
    "client_id": 1,
    "account_id": "DUM513747"
  },
  "ctrader": {
    "host": "demo.ctraderapi.com",
    "port": 5035,
    "client_id": "...",
    "client_secret": "...",
    "account_mode": "DEMO",
    "account_id": "46368962"
  }
}
```

## 4.2. Заборонено зберігати в `LGE.conf`

Не писати в `LGE.conf`:

1. `CONNECTED`;
2. `DISCONNECTED`;
3. `SAFE_DISCONNECTED`;
4. `RECONNECTING`;
5. balance;
6. equity;
7. margin;
8. free margin;
9. positions;
10. session id;
11. часові мітки створення/оновлення Runtime;
12. стан помилки Runtime;
13. поточний стан брокера.

Це живе тільки в Runtime.

## 4.3. Канонічне правило

```text
CONF = що хоче користувач.
RUNTIME = що реально відбувається зараз.
```

---

# 5. Політика автоматичного підключення

## 5.1. Призначення

`auto_connect` описує не поточний стан з'єднання, а бажання користувача автоматично підключати брокера при старті LGE.

Канонічна структура:

```json
"engine": {
  "auto_connect": {
    "ib": true,
    "ctrader": true
  }
}
```

## 5.2. Поведінка при старті LGE

При старті LGE:

1. RuntimeEngine читає `engine.auto_connect.ib`.
2. Якщо `true`, пробує підключити IB.
3. RuntimeEngine читає `engine.auto_connect.ctrader`.
4. Якщо `true`, пробує підключити cTrader.
5. Якщо підключення не вдалося, оновлюються лише стан Runtime і стан брокера.
6. `LGE.conf` через помилку підключення не переписується.

## 5.3. Помилки автоматичного підключення

Якщо автоматичне підключення не спрацювало:

```text
CONF: auto_connect.ctrader = true
RUNTIME: cTrader = DISCONNECTED / SAFE_DISCONNECTED / ERROR
```

Це нормальний стан.
Користувач увімкнув автопідключення, але фактичний стан брокера залежить від мережі, TWS, IB Gateway, cTrader OpenAPI, токенів і API брокера.

---

# 6. Центральний координатор RuntimeEngine

## 6.1. Призначення

`RuntimeEngine` є центральним координатором Runtime.

Він відповідає за:

1. запуск;
2. завершення роботи;
3. контекст Runtime;
4. вибір активної бази даних;
5. реєстрацію брокерських сервісів;
6. підключення/відключення брокера;
7. інтеграцію завдання перепідключення;
8. планувальник Runtime;
9. події Runtime;
10. синхронізацію стану брокера.

## 6.2. RuntimeEngine не повинен

`RuntimeEngine` не повинен:

1. малювати GUI;
2. показувати QMessageBox;
3. напряму працювати з cTrader OpenAPI;
4. напряму працювати з IB API;
5. зберігати баланс/капітал у `LGE.conf`;
6. виконувати торгові алгоритми без окремого шару стратегій.

---

# 7. Контекст RuntimeContext

## 7.1. Призначення

`RuntimeContext` — поточний знімок стану системи Runtime.

Він може містити:

1. runtime_state;
2. broker;
3. account_mode;
4. execution_mode;
5. active_db;
6. broker_connection_state;
7. session_id;
8. created_utc;
9. updated_utc.

## 7.2. RuntimeContext не є conf

`RuntimeContext` не зберігається як постійний стан у `LGE.conf`.

Після нового запуску LGE контекст Runtime створюється заново.

---

# 8. Стани RuntimeState

Канонічні стани Runtime:

```text
OFF
STARTING
RUNNING
STOPPING
ERROR
```

## 8.1. OFF

Нормальний стартовий стан. Runtime ще не запущено.

## 8.2. STARTING

Runtime запускається, створює контекст, відкриває базу даних і готує сервіси.

## 8.3. RUNNING

Runtime активний. Брокер може бути підключений або відключений — це окремий стан брокера.

## 8.4. STOPPING

Runtime завершує брокерські сесії, планувальник і ресурси.

## 8.5. ERROR

Фатальна runtime-помилка, яка потребує втручання користувача або розробника.

---

# 9. Стан підключення та працездатність брокера

Стан підключення брокера не тотожний `RuntimeState`.

Канонічний стан брокераs:

```text
OFF
CONNECTING
CONNECTED
DISCONNECTED
SAFE_DISCONNECTED
RECONNECTING
ERROR
UNKNOWN
```

## 9.1. CONNECTED

Брокерський сервіс має активне підтверджене з'єднання.

## 9.2. DISCONNECTED

З'єднання відсутнє штатно або після ручного відключення.

## 9.3. SAFE_DISCONNECTED

Broker service виявив, що активний адаптер/session не є надійним.
Це не критична помилка.

У цьому стані:

1. торгові дії блокуються;
2. reconnect дозволений;
3. LGE не треба перезапускати;
4. UI має показати зрозумілий стан брокера.

## 9.4. RECONNECTING

RuntimeReconnectTask або брокерський сервіс виконує перепідключення.

## 9.5. ERROR

Брокерський сервіс отримав помилку, яку не вдалося автоматично усунути.

---

# 10. Події Runtime

Runtime events потрібні для:

1. діагностики;
2. журналювання;
3. UI status;
4. runtime tests;
5. історії перепідключень.

Канонічні типи подій:

```text
STARTUP
SHUTDOWN
BROKER_SERVICE_SELECTED
BROKER_CONNECTING
BROKER_CONNECTED
BROKER_DISCONNECTED
BROKER_CONNECTION_ERROR
MODE_CHANGED
ENGINE_CONFIG_CHANGED
RECONNECT_STARTED
RECONNECT_SUCCESS
RECONNECT_FAILED
ACCOUNT_LOADED
ACCOUNT_UPDATED
ERROR
```

Події існують лише в Runtime.
Вони не записуються в `LGE.conf`.

---

# 11. Стан рахунку RuntimeAccountState

## 11.1. Призначення

`RuntimeAccountState` містить знімок активного брокерського рахунку в Runtime.

Може містити:

1. account_id;
2. broker_name;
3. trader_login;
4. currency;
5. balance;
6. equity;
7. margin;
8. free_margin;
9. leverage;
10. snapshot_utc.

## 11.2. Канонічний тип account_id

Після RoadMap76 канонічний тип:

```python
str | None
```

IB:

```json
"account_id": "DUM513747"
```

cTrader:

```json
"account_id": "46368962"
```

## 11.3. Правило зберігання лише в Runtime

`RuntimeAccountState` не зберігається в `LGE.conf`.

У `LGE.conf` зберігається тільки вибраний `account_id`, а не баланс/капітал/free margin.

---

# 12. Планувальник RuntimeScheduler

## 12.1. Призначення

`RuntimeScheduler` запускає фонові завдання Runtime без прямої залежності від GUI.

Може виконувати:

1. heartbeat;
2. завдання перепідключення;
3. завдання перевірки стану ринку;
4. оновлення стану брокера;
5. майбутні контрольні завдання Runtime.

## 12.2. Правило

Планувальник не виконує торгову логіку безпосередньо.
Торгові алгоритми будуть окремим шаром.

---

# 13. Завдання перепідключення RuntimeReconnectTask

## 13.1. Призначення

`RuntimeReconnectTask` відповідає за повторне підключення брокерського сервісу.

Він працює не з адаптером напряму, а з протоколом сервісу:

```text
reconnect()
get_broker_health()
```

## 13.2. Канонічна поведінка

```text
SAFE_DISCONNECTED
↓
RECONNECTING
↓
CONNECTED
```

або:

```text
SAFE_DISCONNECTED
↓
RECONNECTING
↓
SAFE_DISCONNECTED / ERROR
```

Без перезапуску LGE.

---

# 14. Сховище Runtime у SQLite

## 14.1. Фізичні бази

У корені проєкту використовується папка:

```text
data/
```

Канонічні DB:

```text
data/demo.db
data/live.db
data/test.db
```

## 14.2. demo.db

Для сесій Runtime у режимі DEMO.

## 14.3. live.db

Для сесій Runtime у режимі LIVE.

Схема має бути максимально близькою до `demo.db`.

## 14.4. test.db

Для tests/тестування на історичних данихs/history cache.

Історичні дані не є постійною головною базою.
Вона завантажується під конкретний тест/аналіз і може очищатися.

## 14.5. SQLite PRAGMA

Канонічні правила:

1. режим WAL;
2. зовнішні ключі увімкнено;
3. версія схеми;
4. автоматичне створення таблиць;
5. без ручного створення runtime DB користувачем.

---

# 15. Абстракція брокерів

## 15.1. Рівні

```text
RuntimeEngine
↓
IBRuntimeService / CTraderRuntimeService
↓
IBSessionManager / CTraderSessionManager
↓
IBAdapter / CTraderAdapter
↓
TWS / IB Gateway / cTrader OpenAPI
```

## 15.2. BrokerInterface

Адаптер брокера має надавати канонічні методи:

1. connect;
2. disconnect;
3. перепідключення;
4. is_connected;
5. get_account_info;
6. get_positions;
7. майбутні операції з ордерами та позиціями.

---

# 16. Runtime для Interactive Brokers

## 16.1. RoadMap76 статус

IB переведений на архітектуру Runtime:

```text
RuntimeEngine
↓
IBRuntimeService
↓
IBSessionManager
↓
IBAdapter
↓
TWS / IB Gateway
```

Підтверджено:

1. `ib_connection_dialog.ui` створено;
2. перехід з програмного UI на `.ui` виконано;
3. IB список рахунків працює;
4. вибір рахунку зберігається в `LGE.conf`;
5. завершення роботи LGE завершує IB session;
6. список брокерів у рядку стану показує стан IB;
7. reconnect після перезапуску TWS перевірявся;
8. запуск без TWS обробляється без падіння.

## 16.2. Діагностика підключення IB

При помилці IB-підключення UI має давати зрозумілу підказку:

```text
Перевірте, чи запущено TWS / IB Gateway,
чи увімкнено Enable ActiveX and Socket Clients,
і чи правильний порт 7497/7496/4002/4001.
```

---

# 17. Runtime для cTrader

## 17.1. Канонічна архітектура

```text
Dialog
↓
RuntimeEngine
↓
CTraderRuntimeService
↓
CTraderSessionManager
↓
CTraderAdapter
↓
cTrader OpenAPI
```

Старий ланцюжок:

```text
Dialog
↓
OAuth
↓
Probe
↓
Subprocess
```

не є робочим ланцюжком Runtime.

## 17.2. OAuth

OAuth залишається окремою операцією авторизації.
Він може відкривати браузер і оновлювати `tokens/tokens.json`.

OAuth не є торговим підключенням.

## 17.3. Токени

`tokens/tokens.json` містить токени доступу й оновлення.
Tokens не зберігаються в репозиторії.

Runtime adapter не генерує фіктивний токен.

Якщо token недійсний або прострочений, Runtime має зупинитись із чіткою помилкою до TCP-підключення.

## 17.4. Знімок рахунку cTrader

Після RoadMap77 підтверджено правильний Runtime ланцюжок отримання знімка:

```text
ApplicationAuth
↓
AccountList
↓
AccountAuth
↓
TraderReq
↓
TraderRes
↓
AssetListReq
↓
AssetListRes
↓
BrokerAccount / RuntimeAccountState
```

Відповідь зі списком рахунків не містить баланс/валюту/кредитне плече.

Balance береться з:

```text
ProtoOATrader.balance / (10 ** ProtoOATrader.moneyDigits)
```

Currency береться через:

```text
ProtoOATrader.depositAssetId → ProtoOAAssetListRes.asset
```

Leverage береться з:

```text
ProtoOATrader.leverageInCents / 100
```

## 17.5. Список рахунків cTrader

ComboBox рахунку не повинен бути основним монітором балансу.

Канонічна роль:

```text
Account selector = вибір/ідентичність рахунку.
Balance indicator = контроль фінансового стану.
```

Поточний допустимий формат combo:

```text
46368962 • Demo
```

або тимчасово:

```text
46368962 • Demo • 803.53 USD
```

Але довгостроково баланс/капітал мають бути окремим індикатором.

## 17.6. Відключення cTrader

У `ctrader_connection_dialog.ui` додано кнопку:

```text
Відключити
```

Вона викликає:

```text
RuntimeEngine.disconnect_ctrader()
```

а не adapter напряму.

---

## 17.7. Статус реалізації

---

Реалізовано:

1. підключення Runtime.
2. відключення Runtime.
3. знімок рахунку Runtime.
4. інтеграція стану брокера в Runtime.
5. інтеграція стану рахунку в Runtime.
6. AutoConnect.
7. перевірка перепідключення Runtime.
8. інтеграція спільного RuntimeEngine.

Незавершено:

1. Канонічний баланс/капітал indicator.
2. Повне вилучення залишків старої probe-логіки.

---

# 18. Менеджер сесій SessionManager

## 18.1. Призначення

SessionManager відповідає за життєвий цикл конкретного адаптера брокера.

Для cTrader це критично через Twisted callback-и та Deferred-и.

## 18.2. Обов'язки SessionManager

SessionManager має:

1. створювати адаптер;
2. зберігати активний адаптер;
3. виконувати відключення;
4. виконувати перепідключення;
5. виводити з використання старі сесії адаптера;
6. не дозволяти старим callback-ам псувати новий стан;
7. повертати активний адаптер на рівень сервісу.

## 18.3. Покоління сесій cTrader

cTrader використовує політику поколінь сесій і виведення старих адаптерів із використання.

Старі callback-и після втрата інтернету або timeout мають ігноруватись.

---

# 19. Політика SAFE_DISCONNECTED

SAFE_DISCONNECTED потрібен для cTrader і IB як проміжний безпечний стан.

## 19.1. Коли ставимо SAFE_DISCONNECTED

1. адаптер існує, але сесія неактивна;
2. брокерський сокет розірвано;
3. перепідключення не відновило з’єднання;
4. network loss;
5. TWS/IB Gateway закрито;
6. cTrader OpenAPI перестав відповідати.

## 19.2. Що робить LGE

У SAFE_DISCONNECTED:

1. не відкриває нові ордери;
2. не модифікує позиції;
3. показує стан брокера;
4. дозволяє перепідключення;
5. не переписує `LGE.conf`;
6. не вимагає перезапуску LGE.

---

# 20. Відповідальність інтерфейсу Runtime

## 20.1. GUI дозволено

GUI може:

1. читати user intent;
2. показувати статус;
3. викликати RuntimeEngine methods;
4. показувати вибір рахунку;
5. показувати індикатор балансу;
6. показувати зрозумілі errors.

## 20.2. GUI заборонено

GUI не повинен:

1. створювати адаптер брокера напряму;
2. працювати з Twisted напряму;
3. працювати з IB API напряму;
4. запускати subprocess probe як робочий connect;
5. писати runtime facts у `LGE.conf`;
6. змішувати account selector і account monitor.

---

# 21. Монітор брокерів у рядку стану

Поточний канонічний монітор брокерів:

```text
Brokers: 2/2
IB: CONNECTED
cTrader: CONNECTED
```

Broker Monitor відображає:

- стан брокера;
- ідентифікатор рахунку;
- balance account.

Джерелом інформації є Runtime Account Snapshot.

Приклад майбутнього індикатор балансу:

```text
IB: 10245.31 USD | cT: 803.53 USD
```

або:

```text
Balance: cT 803.53 USD
```

---

# 22. Послідовність запуску

Канонічна послідовність запуску:

1. Після входу користувача виконується розшифрування `LGE.conf`.
2. MainWindow створює або отримує RuntimeEngine.
3. Виконується запуск RuntimeEngine.
4. RuntimeEngine відкриває активну базу даних.
5. RuntimeEngine реєструє брокерські сервіси.
6. GUI читає налаштування `engine.auto_connect`.
7. RuntimeEngine виконує AutoConnect для дозволених брокерів.
8. Broker health оновлює runtime state.
9. StatusBar оновлює стан брокерів.
10. Помилки підключення не змінюють `LGE.conf`.

---

# 23. Послідовність завершення роботи

Канонічна послідовність завершення роботи:

1. GUI ініціює завершення роботи застосунку.
2. Виконується завершення роботи RuntimeEngine.
3. RuntimeScheduler зупиняється.
4. IBRuntimeService виконує disconnect.
5. CTraderRuntimeService виконує disconnect.
6. SessionManager закриває та утилізує adapters.
7. Runtime events фіксують завершення роботи.
8. RuntimeContext видаляється.
9. Runtime-стан не записується в `LGE.conf`.

---

# 24. Тести перепідключення

## 24.1. Interactive Brokers

Тестовий сценарій:

1. Запустити TWS та виконати підключення.
2. Закрити TWS.
3. Broker health переходить у SAFE_DISCONNECTED або DISCONNECTED.
4. Повторно запустити TWS.
5. Виконується reconnect.
6. Broker health повертається у CONNECTED.

## 24.2. cTrader

Тестовий сценарій:

1. Підключити cTrader DEMO.
2. Вимкнути Інтернет.
3. Broker health переходить у SAFE_DISCONNECTED.
4. Увімкнути Інтернет.
5. RuntimeReconnectTask виконує reconnect.
6. Broker health повертається у CONNECTED.
7. Перезапуск LGE не потрібний.

---

# 25. Рівень доступності ринку

Доступність ринку є окремою сутністю і не залежить безпосередньо від стану підключення брокера.

Можливі стани ринку:

```text
MARKET_OPEN
MARKET_CLOSED
MARKET_PREOPEN
MARKET_HALTED
MARKET_UNKNOWN
```

Наявність підключення до брокера не означає, що ринок відкритий.

Перед виконанням будь-якої торгової операції система повинна перевірити одночасно:

```text
broker health
+
market availability
+
execution mode
+
risk manager
```

Створення або виконання ордера дозволяється тільки після успішного проходження всіх перелічених перевірок.

---

# 26. Режими виконання

Канонічні режими виконання:

```text
OFF
MANUAL
SEMI
AUTO
```

Значення `execution_mode` є наміром користувача і може зберігатися в `LGE.conf`.

Runtime-факти не є режимом виконання.

Стан підключення брокера, доступність ринку, стан RuntimeEngine та інші runtime-параметри не повинні змінювати `execution_mode`.

---

# 27. Політика DEMO / LIVE

1. `demo.db` та `live.db` є окремими базами даних.
2. Брокерські сесії DEMO та LIVE повинні бути чітко позначені.
3. LIVE-операції потребують явного дозволу та ліцензійної політики.
4. Runtime-журнали повинні чітко розділяти DEMO та LIVE.
5. GUI ніколи не повинен непомітно перемикати користувача з DEMO на LIVE.
6. DEMO та LIVE повинні використовувати окремі брокерські сесії.
7. Будь-яке перемикання між DEMO та LIVE повинно виконуватися лише за прямою дією користувача.

---

# 28. Політика журналювання

Runtime-журнали повинні містити:

1. broker;
2. account mode;
3. тип події;
4. зміну стану;
5. текст помилки;
6. номер reconnect-спроби;
7. покоління сесії там, де це доречно.

Runtime-журнали не повинні містити секретні дані:

1. client_secret;
2. access_token;
3. refresh_token;
4. паролі.

Під час журналювання потрібно забезпечити аналіз RuntimeEngine, брокерських сервісів, SessionManager і життєвого циклу адаптерів без розкриття конфіденційної інформації.

---

# 29. Межа між Runtime та перекладами

Runtime-рівень не повинен залежати від GUI-перекладів.

Правила:

1. Runtime-повідомлення можуть бути технічними внутрішніми журналами українською або англійською мовою.
2. GUI відповідає за переклад повідомлень для користувача.
3. Runtime services не повинні імпортувати QMessageBox.
4. Runtime services не повинні імпортувати UITranslator.
5. GUI володіє перекладеними діалогами та повідомленнями.
6. Runtime-рівень не повинен містити залежностей від конкретних GUI-компонентів.
7. Перекладені повідомлення користувача повинні формуватися виключно на рівні GUI.

---

# 30. Правило конфігурації QComboBox

Для значень QComboBox, які зберігаються у конфігурації, необхідно використовувати:

```python
combo.addItem(text, userData)
combo.currentData()
```

Канонічним значенням конфігурації є `userData`.

Видимий текст елемента не повинен використовуватися як канонічне значення конфігурації.

Це правило є обов'язковим для всіх налаштувань, які зберігаються у `LGE.conf`.

---

# 31. Правила робочого середовища

1. Заборонено використовувати логіку тестових скриптів усередині робочий GUI.
2. Заборонено виконувати прямі виклики брокерських сокетів із GUI.
3. Заборонено використовувати фіктивні токени.
4. Заборонено зберігати runtime-факти в `LGE.conf`.
5. Заборонено непомітне перемикання користувача з DEMO на LIVE.
6. Заборонено виконання ордерів, якщо broker не перебуває у стані CONNECTED.
7. Заборонено виконання ордерів, якщо ринок недоступний.
8. Заборонено приховані цикли перепідключення без видимого стану Runtime.
9. Заборонено старим callback-ам адаптера змінювати стан нової брокерської сесії.
10. Заборонено вимагати від користувача ручного створення баз даних.

---

# 32. Підтверджений стан після RoadMap77

Підтверджено під час RoadMap77:

1. Архітектура IB Runtime працює коректно.
2. Канонічний тип `account_id` для IB визначено як `str | None`.
3. Інтеграція cTrader перенесена з probe/subprocess-підходу в напрямку RuntimeEngine.
4. Кнопка відключення cTrader працює коректно.
5. Runtime snapshot cTrader може надавати баланс та валюту через Trader/Asset flow.
6. список брокерів у рядку стану може відображати `Brokers: 2/2`, `IB: CONNECTED`, `cTrader: CONNECTED`.
7. Політика `LGE.conf` уточнена: зберігаються лише наміри користувача, без runtime-фактів.
8. Політика `engine.auto_connect` погоджена та прийнята до реалізації.

---

# 33. Незавершені роботи RoadMap77

Розділ збережено як історична фіксація стану наприкінці RoadMap77.

## 33.1. Документація

Планувалося:

1. Додати `LGE_Runtime_05.md` до каталогу `doc/`.
2. Вважати попередні Runtime-документи історичними.
3. У майбутньому створити документ `LGE_Algorithms_01.md`.

Стан після RoadMap78:

1. `LGE_Runtime_05.md` використовується як актуальний Runtime-документ.
2. Попередні Runtime-документи розглядаються як історія розвитку архітектури.
3. Створення `LGE_Algorithms_01.md` залишається окремою майбутньою задачею.

## 33.2. Конфігурація

Планувалося:

1. Додати `engine.auto_connect.ib`.
2. Додати `engine.auto_connect.ctrader`.
3. Забезпечити безпечну міграцію конфігурації.
4. Заборонити запис runtime-стану до конфігурації.

Стан після RoadMap78:

1. `engine.auto_connect.ib` реалізовано.
2. `engine.auto_connect.ctrader` реалізовано.
3. Існуючі налаштування користувача зберігаються.
4. Runtime-факти не записуються до `LGE.conf`.

## 33.3. GUI

Планувалося:

1. Додати AutoConnect для IB та cTrader.
2. Зберігати намір користувача в `LGE.conf`.
3. Додати окремий індикатор балансу.
4. Зберегти компактність broker combo.

Стан після RoadMap78:

1. AutoConnect для IB та cTrader реалізовано.
2. Намір користувача зберігається в `LGE.conf`.
3. Питання окремого індикатора балансу залишається відкритим.
4. Broker combo працює та відображає runtime-стан брокерів.

## 33.4. Запуск Runtime

Планувалося:

1. Зчитувати `engine.auto_connect`.
2. Виконувати AutoConnect для IB.
3. Виконувати AutoConnect для cTrader.
4. Обробляти помилки через стан брокера.
5. Оновлювати StatusBar.

Стан після RoadMap78:

1. RuntimeEngine читає `engine.auto_connect`.
2. AutoConnect для IB працює.
3. AutoConnect для cTrader працює.
4. Помилки відображаються через стан брокера.
5. StatusBar автоматично оновлює стан брокера.

## 33.5. Тести перепідключення

Планувалося:

1. Перевірити перепідключення IB після закриття та запуску TWS.
2. Перевірити перепідключення cTrader після вимкнення та ввімкнення Інтернету.
3. Перевірити ланцюжок SAFE_DISCONNECTED → RECONNECTING → CONNECTED.

Стан після RoadMap78:

1. Перепідключення IB підтверджено.
2. Перепідключення cTrader підтверджено.
3. RuntimeReconnectTask працює для обох брокерів.
4. Ланцюжок SAFE_DISCONNECTED → RECONNECTING → CONNECTED підтверджено тестами.

---

# 34. Застаріло

---

Інформацію перенесено до розділів:

- 38. RoadMap79 — стабілізація життєвого циклу перепідключення
- 39. Підсумковий канон після RoadMap79
- 41. Майбутній документ LGE_Algorithms_01.md

---

# 35. Застаріло

---

Розділ видалено після завершення RoadMap79.

Актуальний підсумковий Runtime-канон міститься в розділі:

- 39. Підсумковий канон після RoadMap79

---

# 36. Підтверджений стан після RoadMap78

## 36.1. Єдиний RuntimeEngine

Під час RoadMap78 усунуто створення локальних RuntimeEngine у broker dialogs.

Поточна архітектура:

```text
LGE/MainWindow
    ↓
RuntimeEngine
    ├─ IBRuntimeService
    └─ CTraderRuntimeService
```

MainWindow створює RuntimeEngine один раз під час запуску застосунку.

Поточний RuntimeEngine публікується через:

```python
session_state.CURRENT_RUNTIME_ENGINE
```

Усі broker dialogs використовують shared RuntimeEngine.

## 36.2. Автоматичне підключення

Реалізовано запуск AutoConnect через RuntimeEngine.

Підтримуються налаштування:

```json
"auto_connect": {
    "ib": true,
    "ctrader": true
}
```

AutoConnect є наміром користувача.

Runtime-факти не записуються до `LGE.conf`.

## 36.3. Монітор брокерів у рядку стану

StatusBar відображає поточний стан брокерські сервіси.

Приклади:

```text
Брокери: 2/2

IB: ПІДКЛЮЧЕНО
cTrader: ПІДКЛЮЧЕНО
```

або:

```text
Брокери: 0/2

IB: БЕЗПЕЧНО ВІДКЛЮЧЕНО
cTrader: БЕЗПЕЧНО ВІДКЛЮЧЕНО
```

StatusBar отримує дані з RuntimeEngine і не використовує runtime-стан із конфігурації.

## 36.4. Стан діалогів підключення брокерів

Для IB та cTrader реалізовано автоматичне керування кнопками.

Підключено:

```text
Підключитися -> disabled
Відключити   -> enabled
```

Відключено:

```text
Підключитися -> enabled
Відключити   -> disabled
```

Стан кнопок автоматично синхронізується з Runtime стан брокера.

---

## 36.5. Особливість автоматичного перекладу нових ключів

---

Під час тестів Runtime Alert було виявлено особливість механізму перекладів LGE.

Сценарій:

1. Новий ключ відсутній у strings.json та strings_fallback.json.
2. Відбувається перший виклик ключа.
3. У цей момент відсутній інтернет.
4. Автоматичний переклад не може отримати переклад.
5. У strings.json створюється лише англійське значення.
6. Після відновлення інтернету переклад автоматично не дозаповнюється, оскільки ключ уже існує.

Приклад RoadMap79:

- RuntimeAlert.brokerConnectionLost був створений при вимкненому інтернеті.
- RuntimeAlert.brokerConnectionRestored був створений при наявному інтернеті.
- У результаті перший ключ залишився лише з EN-перекладом, а другий автоматично отримав UK-переклад.

Висновок:

Це не помилка Runtime Alert, StatusBar або RuntimeEngine.
Це штатна особливість поточного механізму автоматичного створення перекладів.

Для автоматичного створення перекладу необхідно:

1. Видалити ключ із strings.json.
2. Забезпечити доступ до інтернету.
3. Повторно викликати відповідний текст.

---

## 36.6. Відображення балансу в рядку стану Runtime

---

Після RoadMap79 Runtime StatusBar відображає не лише стан підключення брокера, але і поточний баланс рахунку.

Приклад:

```text
Брокери: 2/2

IB       | ПІДКЛЮЧЕНО | DUM513747 | 1 019 948.96 USD
cTrader  | ПІДКЛЮЧЕНО | 46368962  |     764.50 USD
```

Баланс відображається тільки для підключених брокерів.

Джерелом даних є Runtime Account Snapshot, який уже підтримується Runtime Services.

StatusBar не виконує окремих broker-запитів для отримання балансу.

Правило:

* Runtime Service отримує та оновлює інформацію про рахунок.
* Runtime Account Snapshot є джерело істини.
* StatusBar лише відображає поточний snapshot.

Мета:

Користувач повинен бачити поточний стан брокера та баланс рахунку без відкриття broker dialogs.

---

# 37. Підтверджені тести RoadMap78

---

## 37.1. Запуск без Інтернету

---

Підтверджено:

1. LGE успішно запускається.
2. RuntimeEngine створюється.
3. AutoConnect виконується.
4. Невдале підключення не пошкоджує конфігурацію.
5. RuntimeReconnectTask залишається активним.

Результат:

```text
PASS
```
---

## 37.2. cTrader: вимкнення та ввімкнення Інтернету

---

Підтверджено:

1. Підключення cTrader DEMO.
2. Internet OFF.
3. SAFE_DISCONNECTED.
4. RuntimeReconnectTask.
5. Internet ON.
6. Автоматичне відновлення підключення.
7. Перезапуск LGE не потрібний.

Результат:

```text
PASS
```
---

## 37.3. TWS після запуску LGE

---

Підтверджено:

1. LGE запускається без TWS.
2. Startup AutoConnect IB завершується помилкою.
3. RuntimeReconnectTask запускається автоматично.
4. Після запуску TWS виконується reconnect.
5. Broker state переходить у CONNECTED.

Результат:

```text
PASS
```
---

## 37.4. Рядок стану

---

Підтверджено відображення:

```text
Брокери: 0/2
Брокери: 1/2
Брокери: 2/2
```

Результат:

```text
PASS
```

---

## 37.5. Кнопки діалогів підключення брокерів

---

Підтверджено для IB та cTrader:

1. CONNECTED → Connect disabled.
2. CONNECTED → Disconnect enabled.
3. DISCONNECTED / SAFE_DISCONNECTED → Connect enabled.
4. DISCONNECTED / SAFE_DISCONNECTED → Disconnect disabled.

Результат:

```text
PASS
```

---

# 38. RoadMap79 — стабілізація життєвого циклу перепідключення

---

## 38.1. Причина RoadMap79

---

Після RoadMap78 залишилася нестабільність перепідключення cTrader.

Симптоми:

```text
Twisted reactor run skipped
Deferred TimeoutError
TIMEOUT: cTrader auth not completed
ALREADY_LOGGED_IN
```

Головна причина:

```text
CTraderAdapter owns reactor thread
```

але Twisted reactor є process-level singleton.

Канонічне рішення:

```text
process owns reactor
adapter owns client/session
session manager owns active adapter
```

---

## 38.2. Реактор cTrader на рівні процесу

---

Додано process-level manager:

```text
engine/ctrader_reactor_manager.py
```

Він відповідає за:

1. запуск Twisted reactor один раз за життя LGE process;
2. `call_in_ctrader_reactor(...)`;
3. diagnostic stop helper;
4. відсутність повторного запуску реактора під час перепідключення.

`CTraderAdapter` більше не володіє власним reactor thread.

---

## 38.3. Перевірка доступності сервера cTrader

---

Для cTrader додано TCP-перевірку host/port перед створенням adapter.

Якщо host недоступний:

```text
cTrader host unreachable
```

adapter не створюється.

Це прибирає лавину мертвих Deferred-и при запуску без Інтернету.

---

## 38.4. Незалежність account_mode cTrader від адаптера

---

`CTraderSessionManager` зберігає активний account mode окремо від adapter:

```python
_active_account_mode
```

Це дозволяє виконувати перепідключення навіть тоді, коли активний адаптер ще не створений або вже виведений із використання.

---

## 38.5. Життєвий цикл перепідключення cTrader

---

Для cTrader прийнято правило:

```text
старий adapter залишається active
↓
створюється candidate adapter
↓
якщо candidate connected -> candidate стає active
↓
старий adapter retire/disconnect
↓
якщо candidate failed -> старий active adapter зберігається
```

Це прибрало помилку:

```text
ALREADY_LOGGED_IN
```

---

## 38.6. Політика обробки помилок Deferred

---

У `CTraderAdapter._on_deferred_error(...)` помилка Deferred тепер завершує очікування connect.

`connected_event` використовується як сигнал:

```text
auth finished somehow
```

а не тільки як ознака успішного connect.

Це прибрало зависання на:

```text
TIMEOUT: cTrader auth not completed
```

---

## 38.7. Окремі завдання перепідключення для кожного брокера

---

У `RuntimeEngine` завдання перепідключення розділено:

```python
_ib_reconnect_task
_ctrader_reconnect_task
```

Один спільний `_runtime_reconnect_task` більше не використовується.

Інтервал завдання перепідключення винесено в константи Runtime:

```python
RUNTIME_RECONNECT_TASK_INTERVAL_SECONDS
```

---

## 38.8. Константи Runtime

---

Після RoadMap79 константи Runtime містять значення перепідключення та мережі, зокрема:

```python
IB_RECONNECT_COOLDOWN_SECONDS
CTRADER_RECONNECT_COOLDOWN_SECONDS
CTRADER_HOST_CHECK_TIMEOUT_SECONDS
CTRADER_LATE_CONNECT_TIMEOUT_SECONDS
CTRADER_OLD_SESSION_CLOSE_DELAY_SECONDS
RUNTIME_RECONNECT_TASK_INTERVAL_SECONDS
```

Магічні значення перепідключення, мережі й тайм-аутів не повинні розкидатися по робочому коду.

---

## 38.9. Локалізація рядка стану Runtime

---

Монітор брокерів у рядку стану переведено на систему перекладів.

Додано ключі для:

```text
StatusBar.brokerRuntimeStatus
StatusBar.brokersLabel
StatusBar.brokerStateConnected
StatusBar.brokerStateSafeDisconnected
StatusBar.brokerStateReconnecting
RuntimeAlert.ibConnectionLost
```

Правило:

```text
Runtime state = технічний стан.
GUI text = перекладений користувацький текст.
```

`runtime_broker_health.py` не містить UI-перекладів.

---

## 38.10. IB/TWS — взаємодія під час перепідключення

---

Для IB важливо розрізняти:

```text
LGE не може підключитися до TWS socket API
```

і:

```text
TWS підключений локально, але сам відновлює зв'язок із IBKR servers
```

Код IB `502` означає, що LGE не може під'єднатися до TWS socket API.

Типові причини:

1. TWS не запущений;
2. користувач ще не відповів на діалог TWS;
3. `Enable ActiveX and Socket Clients` вимкнено;
4. неправильний port;
5. TWS ще не завершив login.

Для Paper/TWS очікуваний port:

```text
7497
```

Для IB Gateway Paper:

```text
4002
```

---

## 38.11. Підтверджені тести RoadMap79

---

Підтверджено:

1. Startup без Інтернету → Internet ON → cTrader CONNECTED.
2. cTrader Internet OFF / ON → CONNECTED.
3. Довгі OFF / ON цикли.
4. Короткі OFF / ON цикли.
5. Відсутність `ALREADY_LOGGED_IN`.
6. Відсутність лавини `Deferred TimeoutError`.
7. Відсутність зависання на auth timeout.
8. Завершення роботи закриває активні брокерські сесії.
9. StatusBar показує `Брокери: X/2`.
10. Runtime alerts показують втрату/відновлення з'єднання.
11. Startup без Інтернету → Internet ON → Internet OFF → Internet ON.

Результат:

```text
PASS
```

---

## 38.12. Поточний відомий зовнішній ризик

---

IB/TWS може тимчасово не відновлюватися після багатьох циклів Internet OFF / ON.

Якщо TWS повертає `502`, це не помилка перепідключення LGE, а недоступність socket API TWS.

LGE має продовжувати контроль перепідключення і показувати користувачу зрозумілий стан.

---

# 39. Підсумковий канон після RoadMap79

---

Підсумковий Runtime-канон після RoadMap79:

```text
LGE.conf зберігає налаштування та наміри користувача.

RuntimeEngine зберігає та контролює поточний runtime-стан системи.

Broker services відповідають за життєвий цикл брокерів.

SessionManagers відповідають за життєвий цикл adapters.

Adapters відповідають за взаємодію з broker API.

Twisted reactor належить process-level manager, а не adapter.

cTrader adapter створюється тільки після host reachability gate.

Перепідключення cTrader закриває стару сесію OpenAPI перед авторизацією нового адаптера.

Перепідключення IB залежить від доступності socket API TWS / IB Gateway.

GUI відповідає за відображення інформації, переклади та команди користувача.

Runtime-рівень не залежить від GUI-перекладів.

Торгові алгоритми документуються окремо в LGE_Algorithms_01.md.
```

---



# 40. Перевірка перепідключення у робочому середовищі

---

Проведено тривалий тест Runtime Reconnect Watch.

Сценарії:

- ручне вимкнення інтернету;
- ручне ввімкнення інтернету;
- короткочасні збої провайдера;
- одночасна втрата зв'язку IB та cTrader;
- автоматичне відновлення.

Результат:

IB:
SAFE_DISCONNECTED
→ RECONNECT WATCH
→ CONNECTED

cTrader:
SAFE_DISCONNECTED
→ RECONNECT WATCH
→ CONNECTED

Підтверджено:

- контроль перепідключення працює стабільно;
- дублікати контролю перепідключення не запускаються;
- Runtime StatusBar оновлюється коректно;
- Runtime Alerts працюють коректно;
- AutoConnect після відновлення мережі працює коректно.

---

# 41. Майбутній документ LGE_Algorithms_01.md

---

Окремий документ алгоритмів повинен містити:

1. модель ринку Forex;
2. рейки;
3. імпульсний день;
4. trend/filter logic;
5. flat/range logic;
6. liquidity logic;
7. правила входу;
8. правила виходу;
9. аварійне дострокове закриття позицій;
10. risk manager;
11. керування розміром позиції;
12. політику тестування на історичних даних;
13. політику використання broker history;
14. перевірку DEMO/LIVE;
15. майбутні не-Forex торгові системи.

Runtime-документ не повинен перетворюватися на документ торгових стратегій.

---

# 42. Оновлення балансу рахунку в рядку стану Runtime

---

Додано живе оновлення балансу рахунків у Runtime StatusBar.

Проблема:

- StatusBar оновлював стан брокера;
- але RuntimeAccountState перечитувався тільки після підключення;
- тому баланс у випадаючому списку монітора брокерів міг залишатися старим.

Рішення:

1. Додано константу:

   - `RUNTIME_ACCOUNT_REFRESH_INTERVAL_SECONDS = 30.0`

2. Додано service-level refresh:

   - `IBRuntimeService.refresh_account_state()`
   - `CTraderRuntimeService.refresh_account_state()`

3. У `core/main_logic.py` періодично викликається:

   - `refresh_broker_health()`
   - `refresh_account_state()`
   - `_update_brokers_statusbar()`

4. Для cTrader додано окремий adapter refresh:

   - `CTraderAdapter.refresh_account_info()`

Особливість cTrader:

- `get_account_info()` повертає кеш;
- `refresh_account_info()` надсилає новий `ProtoOATraderReq`;
- відповідь приходить асинхронно;
- тому баланс може оновлюватися із затримкою до 30–60 секунд.

Підтверджено вручну:

- після зміни балансу в cTrader значення в StatusBar оновлюється;
- ComboBox монітора брокерів не змінювався;
- поточне розташування ComboBox залишено без змін.

---

# 43. Ручна торгівля в Runtime

---

Після стабілізації RuntimeEngine та Runtime Services ручна торгівля стала наступним шаром архітектури LGE.

Мета цього шару — надати єдиний Runtime API для ручного відкриття, перегляду та закриття позицій незалежно від конкретного брокера.

Архітектура виклику:

```text
OrdersPage
        │
        ▼
RuntimeEngine
        │
        ▼
Broker Runtime Service
        │
        ▼
SessionManager
        │
        ▼
BrokerAdapter
        │
        ▼
Broker API
```

OrdersPage не звертається безпосередньо до BrokerAdapter або Broker API.

Усі торгові операції виконуються виключно через RuntimeEngine.

---

## Активний брокер

У Runtime одночасно можуть бути підключені кілька брокерів.

Наприклад:

```text
IB          CONNECTED
cTrader     CONNECTED
```

Однак активним торговим брокером у будь-який момент часу може бути лише один.

Активний брокер визначається RuntimeEngine та використовується всіма торговими сторінками, алгоритмами та
автоматичними режимами.

У RuntimeEngine активний брокер є частиною Runtime Context і
виступає єдиним джерелом істини (джерело істини) для всіх торгових операцій.

OrdersPage не вибирає брокера самостійно та не зберігає власний стан активного брокера.

---

## Активний брокер Lock

Під час роботи зі сторінкою ручних ордерів активний брокер блокується.

Поки OrdersPage відкрита:

- зміна активного брокера заборонена;
- перемикач активного брокера у StatusBar відключений.

Після закриття OrdersPage блокування автоматично знімається.

Такий підхід виключає можливість випадкового відкриття форми для одного брокера та відправлення ордера іншому брокеру.

---

## OrdersPage

OrdersPage є Runtime UI для ручної торгівлі.

Сторінка містить:

- вибір інструмента;
- напрямок угоди;
- обсяг;
- Stop Loss;
- Take Profit;
- коментар;
- відкриття ордера;
- оновлення відкритих позицій;
- операції над відкритими позиціями;
- таблицю відкритих позицій;
- рядок стану.

UI відповідає тільки за взаємодію з користувачем.

Будь-яка бізнес-логіка виконується RuntimeEngine.

---

## Правило побудови інтерфейсу Runtime

Для всіх Runtime сторінок використовується єдина схема побудови.

```text
.ui
        │
        ▼
Python wrapper
        │
        ▼
RuntimeEngine
        │
        ▼
Broker Runtime
```

Спочатку створюється структура UI.

Потім підключаються переклади.

Після цього реалізується Runtime-поведінка.

Лише після стабілізації Runtime додається збереження даних у SQLite.

SQLite є шаром збереження даних (Persistence Layer) і не визначає поведінку Runtime,
а лише зберігає результати його роботи.

---

# 44. Основа збереження Runtime — RoadMap82

---

RoadMap82 вводить перший канонічний persistence layer для ручної торгівлі LGE.

Головна ідея:

```text
Runtime керує поведінкою.
SQLite зберігає результат.
```

SQLite не є джерелом торгової логіки, не вибирає брокера, не визначає активний account і не приймає торгових рішень.

---

## 44.1. Канонічний шлях до бази Runtime

Runtime DB path більше не має задаватися магічним рядком у GUI або RuntimeEngine.

Канонічний helper знаходиться в DB-шарі:

```text
engine/db/runtime_db.py
```

Канонічне зіставлення:

```text
DEMO -> data/demo.db
LIVE -> data/live.db
TEST -> data/test.db
```

`OFF` не мапиться мовчки на `DEMO`.

Якщо runtime DB mode невідомий, helper має підняти помилку, а не відкривати випадкову базу.

---

## 44.2. RuntimeRepository

Для доступу Runtime до SQLite введено:

```text
engine/runtime_repository.py
```

`RuntimeRepository` є єдиною Runtime-точкою доступу до persistence layer.

Він не знає про Qt, UI, cTrader OpenAPI, IB API або конкретні adapter-и.

Поточні методи:

```text
create_trade()
create_order_plan()
create_broker_order()
create_position()
get_trade_chain()
get_latest_trade_uid()
```

Repository використовує `sqlite3.Row`, щоб записи можна було читати як словники.

---

## 44.3. Канонічний ланцюжок угоди Runtime

RoadMap82 фіксує перший persistence chain:

```text
Trade
    ↓
OrderPlan
    ↓
BrokerOrder
    ↓
Position
```

Кожна сутність має власний UID:

```text
trade_uid
order_plan_uid
broker_order_uid
position_uid
```

Усі дочірні сутності зв'язуються через `trade_uid`.

`trade_uid` є головним ключем для відновлення повного життєвого циклу ручної угоди.

---

## 44.4. Таблиці SQLite

У runtime DB додано перші таблиці:

```text
trades
order_plans
broker_orders
positions
```

Мінімальна відповідальність таблиць:

```text
trades          — торговий намір Runtime
order_plans     — спосіб виконання Trade
broker_orders   — факт відправлення order брокеру
positions       — Runtime-позиція після фактичного виконання
```

---

## 44.5. Trade

`Trade` описує торговий намір користувача або Runtime.

Trade створюється до відправлення order брокеру.

Мінімальні поля:

```text
trade_uid
broker
account_id
symbol
side
volume
created_utc
source
```

Trade не є broker order.

Trade не містить broker-specific id.

---

## 44.6. OrderPlan

`OrderPlan` описує конкретний спосіб виконання Trade.

На поточному етапі підтримується тільки:

```text
MARKET
BUY / SELL
```

Майбутні варіанти:

```text
LIMIT
STOP
STOP LIMIT
OCO
BRACKET
```

OrderPlan не є broker order і не повинен змішуватися з broker execution result.

---

## 44.7. BrokerOrder

`BrokerOrder` створюється після відправлення order брокеру.

Він містить broker-specific execution факт:

```text
broker_order_uid
trade_uid
order_plan_uid
broker
broker_order_id
execution_status
broker_timestamp
created_utc
source
```

`BrokerOrder` не замінює `Trade`.

`BrokerOrder` лише фіксує, що Runtime передав execution request у broker layer.

---

## 44.8. Position

`Position` у SQLite є Runtime-сутністю.

Вона не є прямою копією `BrokerPosition`.

`BrokerPosition` залишається Runtime DTO для читання поточного стану від брокера.

SQLite Position створюється тільки тоді, коли Runtime має підставу вважати, що broker position реально існує.

Не створювати фальшиву Runtime Position лише тому, що order був відправлений.

---

## 44.9. BrokerPosition DTO

`BrokerPosition` використовується як DTO між адаптером/сервісом брокера та Runtime/UI.

Він може містити:

```text
position_id
symbol_name
side
volume
entry_price
stop_loss
take_profit
unrealized_pnl
opened_utc
raw_payload
```

`BrokerPosition` не є SQLite-моделлю.

---

## 44.10. OrdersPage і брокерські позиції

OrdersPage показує відкриті broker positions через RuntimeEngine.

Канонічний шлях:

```text
OrdersPage
    ↓
RuntimeEngine.get_active_broker_positions()
    ↓
CTraderRuntimeService / IBRuntimeService
    ↓
SessionManager
    ↓
Adapter
    ↓
Broker API
```

OrdersPage не звертається напряму до Adapter.

---

## 44.11. Поведінка оновлення

Кнопка `Оновити` на OrdersPage:

1. читає відкриті позиції активного брокера;
2. оновлює Qt-таблицю;
3. показує поточний broker snapshot;
4. не створює записи у SQLite;
5. не змінює `trades`;
6. не змінює `order_plans`;
7. не змінює `broker_orders`;
8. не змінює `positions`.

Це лише для читання operation щодо Runtime DB.

---

## 44.12. Ордери LGE і ручні ордери брокера

На поточному етапі OrdersPage показує всі відкриті broker positions, які повертає активний broker.

Але persistence policy така:

```text
LGE manual order       -> пишеться у SQLite chain
Broker terminal order  -> показується в UI, але не пишеться в SQLite при Refresh
Imported old order     -> майбутній окремий import/sync режим
```

Канонічні майбутні source-значення:

```text
LGE_MANUAL
BROKER_MANUAL
IMPORTED
```
Поточний код може тимчасово використовувати `MANUAL` / `BROKER`, але цільові канонічні значення для наступної стабілізації —
`LGE_MANUAL`, `BROKER_MANUAL`, `IMPORTED`.

Поточний RoadMap82 не імпортує автоматично broker manual positions у SQLite.

Для цього потрібен окремий режим sync/import, щоб не змішувати live broker snapshot із Runtime-owned trade chain.

---

## 44.13. Нереалізований чистий P/L cTrader

cTrader `ProtoOAReconcileRes.position` не є достатнім джерелом для чистого поточного прибутку.

Для поточного unrealized P/L використовується окремий запит:

```text
ProtoOAGetPositionUnrealizedPnLReq
    ↓
ProtoOAGetPositionUnrealizedPnLRes
    ↓
positionUnrealizedPnL[]
    ↓
netUnrealizedPnL
```

У таблиці OrdersPage колонка `Чистий прибуток` бере значення з `netUnrealizedPnL`.

Значення масштабується через `moneyDigits`.

Це broker-provided unrealized net P/L.

Не рахувати P/L вручну, якщо broker API вже повертає canonical value.

---

## 44.14. Таблиця OrdersPage

Поточна таблиця відкритих позицій показує:

```text
ID
Пара
Напрямок
Обсяг
Ціна входу
SL
TP
Чистий прибуток
Час
```

Таблиця є UI snapshot поточного стан брокера.

Вона не є SQLite viewer.

---

## 44.15. Підтверджені результати RoadMap82

Підтверджено:

1. `RuntimeRepository` створює повний chain:
   ```text
   Trade -> OrderPlan -> BrokerOrder -> Position
   ```

2. `run_runtime_repository_check.py` створює записи у:
   ```text
   trades
   order_plans
   broker_orders
   positions
   ```

3. `run_runtime_latest_trade_chain_check.py` читає останній chain без створення нових записів.

4. DBeaver підтвердив наявність записів у `demo.db`.

5. OrdersPage читає відкриті cTrader positions через RuntimeEngine.

6. Кнопка `Оновити` не змінює SQLite.

7. cTrader unrealized net P/L знайдено через `ProtoOAGetPositionUnrealizedPnLRes`.

8. OrdersPage показує чистий прибуток у таблиці відкритих позицій.

---

# 45. Життєвий цикл ручної торгівлі Runtime — RoadMap83

---

RoadMap83 продовжує persistence foundation RoadMap82 і фіксує перший фактично перевірений manual trading життєвий цикл через LGE Runtime path.

RoadMap82 ввів базовий SQLite chain:

```text
Trade
    ↓
OrderPlan
    ↓
BrokerOrder
    ↓
Position
```

RoadMap83 підтвердив цей chain на реальних manual Open / Close операціях у cTrader DEMO.

---

## 45.1. Межа ручної торгівлі

Manual trading у LGE виконується тільки через Runtime layer.

Канонічна межа:

```text
OrdersPage
    ↓
RuntimeEngine
    ↓
Broker Runtime Service
    ↓
SessionManager
    ↓
Adapter
    ↓
Broker API
```

OrdersPage не створює записи SQLite напряму.

OrdersPage не звертається напряму до BrokerAdapter або broker API.

`RuntimeEngine` є єдиною точкою керування trading action з UI.

---

## 45.2. Ланцюжок ручного відкриття в Runtime

Канонічний шлях відкриття manual market order:

```text
OrdersPage
    ↓
RuntimeEngine.place_manual_market_order()
    ↓
RuntimeRepository.create_trade()
    ↓
RuntimeRepository.create_order_plan(order_type=MARKET)
    ↓
CTraderRuntimeService.place_market_order()
    ↓
RuntimeRepository.create_broker_order(execution_status=FILLED)
    ↓
RuntimeRepository.create_position(state=OPEN)
```

Після успішного manual Open у SQLite мають бути створені записи у таблицях:

```text
trades
order_plans
broker_orders
positions
```

Канонічний стан Runtime Position після відкриття:

```text
state = OPEN
```

---

## 45.3. Ланцюжок ручного закриття в Runtime

Закриття broker position у LGE виконується тільки через Runtime layer.

Канонічний шлях close-position:

```text
OrdersPage selected broker position
    ↓
RuntimeEngine.close_active_broker_position()
    ↓
CTraderRuntimeService.close_position()
    ↓
RuntimeRepository.create_order_plan(order_type=CLOSE_MARKET)
    ↓
RuntimeRepository.create_broker_order(execution_status=FILLED)
    ↓
RuntimeRepository.mark_position_closed_by_broker_position_id()
```

Позиція після закриття не видаляється з SQLite.

Канонічний стан закритої Runtime Position:

```text
state = CLOSED
```

SQLite зберігає життєвий цикл trade:

```text
OPEN -> CLOSED
```

---

## 45.4. Правило подій виконання cTrader

cTrader `ExecutionEvent` не завжди означає фінальне виконання order.

Канонічне правило:

```text
ORDER_ACCEPTED -> тільки log, Runtime chain не завершується
ORDER_FILLED   -> фінальне виконання, можна створювати BrokerOrder / Position
ORDER_REJECTED -> error path
```

Runtime не має створювати фінальний persistence chain на `ORDER_ACCEPTED`.

Це правило потрібне, щоб RuntimeEngine не шукав broker position раніше, ніж вона фактично з'явилась у broker snapshot.

---

## 45.5. Правило зіставлення брокерської позиції

Після manual Open RuntimeEngine має прив'язати SQLite Position саме до нової broker position.

Заборонений слабкий matching:

```text
first position with same symbol + side
```

Канонічний matching:

```text
1. зробити broker positions snapshot before;
2. відправити manual market order;
3. зробити broker positions snapshot after;
4. якщо broker_result містить positionId — шукати саме цей positionId;
5. якщо positionId немає — знайти position_id, якого не було у before;
6. перевірити symbol;
7. перевірити side;
8. перевірити volume;
9. якщо кандидатів декілька — взяти найновіший opened_utc.
```

Це правило обов'язкове для manual Open через LGE.

---

## 45.6. Політика кнопок OrdersPage

OrdersPage має окремі дії для trading operation і для виходу зі сторінки.

Канонічні кнопки:

```text
Відкрити          -> manual market Open через RuntimeEngine
Оновити           -> read-only refresh broker positions
Закрити позицію   -> close selected broker position через RuntimeEngine
Вихід             -> закрити OrdersPage / повернутися назад
```

Кнопка `Вихід` не є trading action.

Кнопка `Закрити позицію` є trading action і має працювати тільки з явно вибраним рядком broker position table.

Вибраний рядок таблиці має бути візуально помітним.

Стиль виділення рядка належить до shared UI style layer:

```text
ui/common_dialogs.qss
```

а не до Runtime logic.

---

## 45.7. Політика оновлення OrdersPage

`Оновити` на OrdersPage є лише для читання дією.

Канонічна поведінка:

```text
Оновити
    ↓
читати broker positions
    ↓
оновити таблицю OrdersPage
    ↓
не писати SQLite
```

Broker-terminal manual positions можуть відображатися в OrdersPage після Refresh.

Такі positions не імпортуються у RuntimeRepository автоматично.

Автоматичний import/sync broker-terminal manual positions є окремим майбутнім режимом і не входить у RoadMap83.

---

## 45.8. Діагностичні скрипти Runtime

Для перевірки latest manual Open chain використовується:

```text
tests/runtime/run_runtime_latest_trade_chain_check.py
```

Очікуваний результат для нового manual Open:

```text
trade exists         : True
order_plans count    : 1
broker_orders count  : 1
positions count      : 1
```

Для перевірки close-position chain використовується:

```text
tests/runtime/run_runtime_position_close_check.py
```

Якщо `broker_position_id` не передано аргументом командного рядка, script запитує його через console input.

Очікуваний результат для закритої Runtime Position:

```text
position_state       : CLOSED
order_plans count    : 2
broker_orders count  : 2
```

---

## 45.9. Підтверджений результат Runtime у RoadMap83

RoadMap83 підтвердив manual cTrader DEMO життєвий цикл через LGE Runtime path.

Підтверджені сценарії:

```text
BUY  open  -> OK
BUY  close -> OK
SELL open  -> OK
SELL close -> OK
```

Канонічний підтверджений життєвий цикл:

```text
LGE Open
    ↓
SQLite Trade
    ↓
SQLite OrderPlan MARKET
    ↓
SQLite BrokerOrder FILLED
    ↓
SQLite Position OPEN
    ↓
LGE Close
    ↓
SQLite OrderPlan CLOSE_MARKET
    ↓
SQLite BrokerOrder FILLED
    ↓
SQLite Position CLOSED
```

Це перший фактично перевірений manual Runtime persistence chain LGE для cTrader DEMO.

---

## 45.10. Що не входить у RoadMap83

RoadMap83 не відкриває такі напрями:

```text
AUTO trading
signals
algorithms
backtest
portfolio
historical storage
tick storage
candle storage
broker-terminal manual import
```

Ці блоки залишаються майбутніми етапами.

RoadMap83 завершує тільки:

```text
manual Open
manual Close
SQLite persistence
OrdersPage broker position control
```

---

## 45.11. Критерій завершення RoadMap83

Runtime persistence layer вважається готовим для ручної cTrader DEMO торгівлі, якщо виконуються умови:

```text
1. manual BUY через LGE створює Trade -> OrderPlan -> BrokerOrder -> Position;
2. manual SELL через LGE створює Trade -> OrderPlan -> BrokerOrder -> Position;
3. BrokerOrder має execution_status=FILLED;
4. Position має state=OPEN після відкриття;
5. close-position через LGE створює CLOSE_MARKET OrderPlan;
6. close-position створює другий BrokerOrder;
7. Position переходить у state=CLOSED;
8. Refresh OrdersPage залишається read-only;
9. broker-terminal manual positions не імпортуються в SQLite автоматично;
10. RuntimeEngine залишається єдиною точкою керування trading action.
```

---

# 46. Життєвий цикл ручної торгівлі IB Paper у Runtime — RoadMap84

---

RoadMap84 переносить manual trading життєвий цикл з cTrader DEMO на IB Paper.

RoadMap83 підтвердив cTrader path:

```text
LGE Open
    ↓
SQLite Trade
    ↓
SQLite OrderPlan MARKET
    ↓
SQLite BrokerOrder FILLED
    ↓
SQLite Position OPEN
    ↓
LGE Close
    ↓
SQLite OrderPlan CLOSE_MARKET
    ↓
SQLite BrokerOrder FILLED
    ↓
SQLite Position CLOSED
```

RoadMap84 підтверджує такий самий Runtime persistence життєвий цикл для IB Paper, але з іншою broker-matching логікою.

---

## 46.1. Мета RoadMap84

Головна ціль RoadMap84:

```text
IB Paper Open
    ↓
SQLite chain
    ↓
IB Paper Close
    ↓
SQLite CLOSED
```

Runtime boundary лишається незмінним:

```text
OrdersPage
    ↓
RuntimeEngine
    ↓
IBRuntimeService
    ↓
IBSessionManager
    ↓
IBAdapter
    ↓
TWS / IB Gateway Paper
```

OrdersPage не звертається напряму до IBAdapter або IB API.

OrdersPage не пише SQLite напряму.

`RuntimeEngine` залишається єдиною точкою керування manual trading action.

---

## 46.2. Позиції IB в OrdersPage

RoadMap84 додав підтримку IB positions в OrdersPage через RuntimeEngine.

Канонічний лише для читання path:

```text
OrdersPage Refresh
    ↓
RuntimeEngine.get_active_broker_positions()
    ↓
IBRuntimeService.get_positions()
    ↓
IBAdapter.get_positions()
    ↓
TWS / IB API positions callback
```

Підтверджено:

```text
TWS Paper position
    ↓
IBAdapter.get_positions()
    ↓
IBRuntimeService.get_positions()
    ↓
RuntimeEngine.get_active_broker_positions()
    ↓
OrdersPage table
```

Для IB position table показує короткий ID:

```text
DUM513747
```

Але внутрішній Runtime `broker_position_id` зберігається повністю:

```text
IB:DUM513747:EURUSD
```

Повний ID зберігається у `Qt.UserRole` першої колонки таблиці й використовується для close-position logic.

---

## 46.3. Правило ідентифікатора позиції IB

IB не має cTrader-style `positionId`.

Тому canonical IB Runtime position id формується LGE runtime layer:

```text
IB:<account_id>:<symbol_name>
```

Приклад:

```text
IB:DUM513747:EURUSD
```

Цей ID є runtime key, а не broker-native position id.

Його не можна скорочувати всередині RuntimeEngine або SQLite, бо один account може мати positions по різних symbols:

```text
IB:DUM513747:EURUSD
IB:DUM513747:GBPUSD
```

Скорочення до `DUM513747` дозволене тільки для UI display.

---

## 46.4. Правило кількості IB

cTrader UI працює з lot-size.

IB Forex API працює з quantity у базовій валюті.

Канонічне перетворення для RoadMap84:

```text
1.00 lot = 100000 units
0.10 lot = 10000 units
0.01 lot = 1000 units
```

Тому manual order з OrdersPage:

```text
symbol = EURUSD
side   = BUY
lots   = 0.01
```

для IB перетворюється у:

```text
BUY EUR.USD 1000 MKT
```

SQLite для IB зберігає volume у broker quantity units, тобто:

```text
volume = 1000
```

а не `0.01`.

---

## 46.5. Ланцюжок відкриття IB у Runtime

RoadMap84 додав IB branch для manual MARKET Open.

Канонічний Open path:

```text
OrdersPage
    ↓
RuntimeEngine.place_manual_market_order()
    ↓
RuntimeEngine._place_manual_market_order_ib()
    ↓
RuntimeRepository.create_trade()
    ↓
RuntimeRepository.create_order_plan(order_type=MARKET)
    ↓
IBRuntimeService.place_market_order()
    ↓
IBAdapter.place_market_order()
    ↓
TWS / IB API placeOrder()
    ↓
IB orderStatus FILLED
    ↓
RuntimeRepository.create_broker_order(execution_status=FILLED)
    ↓
RuntimeRepository.create_position(state=OPEN)
```

Підтверджений тест:

```text
LGE:
EURUSD BUY 0.01

IB:
BUY EUR.USD 1000 MKT

TWS:
BOT 1K

OrdersPage:
DUM513747 | EURUSD | BUY | 1000
```

---

## 46.6. Правило зіставлення відкриття IB

Для cTrader matching може використовувати broker `positionId`.

Для IB такого position id немає.

Тому RoadMap84 вводить canonical quantity-delta matching.

Канонічний порядок:

```text
positions_before
    ↓
place MARKET order
    ↓
orderStatus FILLED
    ↓
positions_after
    ↓
знайти зміну quantity
```

Для BUY:

```text
after_position - before_position = +quantity
```

Для SELL:

```text
after_position - before_position = -quantity
```

Matching key:

```text
account_id
symbol_name
signed volume delta
```

Для BUY position signed volume є positive.

Для SELL position signed volume є negative.

Це головна відмінність IB життєвий цикл від cTrader життєвий цикл.

---

## 46.7. Правило дубльованих callback-ів позиції IB

IB API може повернути дубльований callback для тієї самої account + CASH contract position.

OrdersPage має показувати одну canonical broker position.

Канонічна deduplication key:

```text
broker_position_id = IB:<account_id>:<symbol_name>
```

Приклад:

```text
IB:DUM513747:EURUSD
```

Якщо IBAdapter отримав декілька rows для одного `broker_position_id`, у canonical positions list має залишитися один рядок.

---

## 46.8. Ланцюжок закриття IB у Runtime

IB close-position не виконується через broker position id.

IB close-position виконується через opposite MARKET order.

Для position:

```text
EURUSD BUY 1000
```

close order:

```text
SELL EUR.USD 1000 MKT
```

Для position:

```text
EURUSD SELL 1000
```

close order:

```text
BUY EUR.USD 1000 MKT
```

Канонічний Close path:

```text
OrdersPage selected position
    ↓
RuntimeEngine.close_active_broker_position()
    ↓
RuntimeEngine._close_active_broker_position_ib()
    ↓
IBRuntimeService.close_position()
    ↓
IBAdapter.close_position()
    ↓
IBAdapter.place_market_order(opposite side)
    ↓
TWS / IB API placeOrder()
    ↓
IB orderStatus FILLED
    ↓
RuntimeRepository.create_order_plan(order_type=CLOSE_MARKET)
    ↓
RuntimeRepository.create_broker_order(execution_status=FILLED)
    ↓
RuntimeRepository.mark_position_closed_by_broker_position_id()
```

Позиція у SQLite не видаляється.

Закрита Runtime Position має:

```text
state = CLOSED
```

---

## 46.9. Підтверджений результат Open/Close в IB Paper

RoadMap84 підтвердив реальний IB Paper manual життєвий цикл через LGE.

Підтверджений Open:

```text
LGE Open
    ↓
BUY EURUSD 0.01
    ↓
IB quantity conversion
    ↓
BUY EUR.USD 1000 MKT
    ↓
TWS BOT 1K
    ↓
OrdersPage shows EURUSD BUY 1000
    ↓
SQLite Position OPEN
```

Підтверджений Close:

```text
LGE Close selected position
    ↓
SELL EUR.USD 1000 MKT
    ↓
TWS SLD 1K
    ↓
TWS Portfolio EUR.USD POS 0
    ↓
OrdersPage positions count 0
    ↓
SQLite Position CLOSED
```

Підтверджений SQLite chain для IB:

```text
trades:
IB / DUM513747 / EURUSD / BUY / 1000

order_plans:
MARKET BUY 1000
CLOSE_MARKET SELL 1000

broker_orders:
IB / FILLED
IB / FILLED

positions:
IB:DUM513747:EURUSD / EURUSD / BUY / 1000 / CLOSED
```

---

## 46.10. Стан полів таблиці IB

RoadMap84 заповнює для IB positions:

```text
ID
Пара
Напрямок
Обсяг
Ціна входу
```

Поля, які поки можуть бути порожні або нульові:

```text
SL
TP
Чистий прибуток
Час
```

Причини:

```text
SL / TP          -> IB bracket orders ще не реалізовані;
Чистий прибуток -> IB unrealized PnL ще не підключений до OrdersPage;
Час             -> IB position callback не дає canonical opened timestamp.
```

Це не блокує RoadMap84.

Ці поля можуть бути дороблені пізніше окремим RoadMap або UI/data enrichment task.

---

## 46.11. Правило IB SL/TP

RoadMap84 не реалізує IB SL/TP.

IB SL/TP потребує bracket order logic:

```text
parent MARKET order
    ↓
child STOP order
    ↓
child TAKE PROFIT order
```

Це окрема broker-specific execution схема.

Канонічне правило RoadMap84:

```text
IB manual MARKET Open працює тільки без SL/TP.
```

Якщо для IB задано stop_loss або take_profit, Runtime має повернути помилку:

```text
IB SL/TP bracket orders are not implemented yet
```

---

## 46.12. Правило підтвердження в інтерфейсі

Для IB у таблиці показується короткий ID:

```text
DUM513747
```

У confirmation dialog теж показується короткий display ID.

Внутрішній full position id лишається:

```text
IB:DUM513747:EURUSD
```

і передається у RuntimeEngine для close-position.

Кнопки Qt StandardButton можуть тимчасово показуватися як:

```text
Yes
No
```

Це не є Runtime проблемою.

Майбутній UI polish може замінити standard question dialog на custom localized buttons:

```text
Так
Ні
```

RoadMap84 не блокується цим UI polish.

---

## 46.13. Що не входить у RoadMap84

RoadMap84 не включає:

```text
IB bracket orders
IB SL/TP
IB partial close UI
IB unrealized PnL in OrdersPage
IB opened timestamp reconstruction
IB historical executions import
IB broker-terminal manual import into SQLite
AUTO trading
signals
algorithms
backtest
portfolio analytics
```

RoadMap84 завершує тільки:

```text
IB Paper manual Open
IB Paper manual Close
SQLite persistence chain
OrdersPage IB position control
```

---

## 46.14. Критерій завершення RoadMap84

RoadMap84 вважається завершеним, якщо виконуються умови:

```text
1. OrdersPage Refresh показує IB Paper positions через RuntimeEngine;
2. IB positions не дублюються у таблиці;
3. IB internal broker_position_id має формат IB:<account_id>:<symbol>;
4. UI показує короткий ID, але Runtime використовує full ID;
5. LGE Open створює IB MARKET order;
6. IB orderStatus доходить до FILLED;
7. SQLite створює Trade;
8. SQLite створює OrderPlan MARKET;
9. SQLite створює BrokerOrder FILLED;
10. SQLite створює Position OPEN;
11. LGE Close створює opposite IB MARKET order;
12. SQLite створює OrderPlan CLOSE_MARKET;
13. SQLite створює другий BrokerOrder FILLED;
14. SQLite Position переходить у CLOSED;
15. OrdersPage Refresh після close показує positions count 0;
16. cTrader RoadMap83 manual lifecycle не зламаний.
```

---

# 47. Збагачення даних позицій IB в OrdersPage — RoadMap85

## 47.1. Статус

RoadMap85 виконано і перевірено на IB Paper / TWS та cTrader DEMO.

Головна мета RoadMap85 була досягнута: OrdersPage тепер показує IB positions не як мінімальний broker snapshot, а як broker-enriched position view з нормальним volume, entry price, PnL, SL/TP і часом.

RoadMap85 не переписував RoadMap84 manual Open/Close життєвий цикл.

---

## 47.2. Що було перед RoadMap85

Після RoadMap84 уже працювало:

- IB Paper manual MARKET Open з LGE;
- IB Paper manual Close position з LGE;
- SQLite chain для IB:
  - Trade;
  - OrderPlan;
  - BrokerOrder;
  - Position;
- OrdersPage показував IB positions;
- cTrader manual Open/Close життєвий цикл залишався робочим.

Але IB position table ще мала неповне broker-enriched відображення:

- volume міг виглядати не так, як очікується для IB Forex;
- SL/TP не підтягувалися з TWS attached/open orders;
- PnL не був broker-provided;
- час відкриття manual TWS position не був реконструйований;
- існував ризик повернення до мертвого market-data fallback.

RoadMap85 закрив саме display enrichment, а не execution logic.

---

## 47.3. Канонічний шлях читання OrdersPage

OrdersPage читає broker positions тільки через RuntimeEngine.

Канонічний шлях:

    OrdersPage
      -> RuntimeEngine.get_active_broker_positions()
      -> IBRuntimeService.get_positions()
      -> IBSessionManager
      -> IBAdapter.get_positions()
      -> TWS / IB API

OrdersPage не звертається до IBAdapter напряму.

OrdersPage не створює broker requests напряму.

OrdersPage Refresh залишається лише для читання щодо SQLite.

---

## 47.4. Збагачення відображення позицій IB

RoadMap85 збагачує IB position display такими даними:

- broker position volume;
- entry price;
- broker unrealized PnL;
- Stop Loss;
- Take Profit;
- manual TWS execution time.

Ці дані збираються з різних IB API джерел, бо IB position callback не містить усього потрібного.

---

## 47.5. Форматування обсягу IB

IB Forex position volume є broker quantity у базовій валюті.

Для LGE UI прийнято показувати IB quantity як units:

    1000 -> 1 000

Приклад:

    IB position EURUSD BUY 1000

У OrdersPage показується як:

    Обсяг: 1 000

Це відрізняється від cTrader, де UI volume відображається як lots:

    0.01

RoadMap85 не уніфікує broker volume semantics штучно. Він показує broker-native зміст у читабельному форматі.

---

## 47.6. Форматування ціни входу IB

IB entry price показується в OrdersPage у trimmed decimal format.

Мета:

- не показувати зайві нулі;
- не обрізати значущу Forex precision;
- зробити таблицю читабельною.

Приклад:

    1.1460000 -> 1.146

---

## 47.7. IB PnL через reqPnLSingle

Для IB Unrealized PnL у OrdersPage використовується broker-provided PnL через `reqPnLSingle`.

Це правильніше, ніж рахувати PnL вручну на рівні UI.

Канонічний принцип:

    Якщо broker API надає canonical PnL,
    LGE має показувати broker PnL,
    а не дублювати broker calculation вручну.

RoadMap85 підключив IB PnL до OrdersPage.

---

## 47.8. Читання IB SL/TP через відкриті ордери

IB positions не містять SL/TP як поля position.

IB Stop Loss і Take Profit існують як окремі open orders:

- Stop Loss:
  - STP / STOP;
- Take Profit:
  - LMT / LIMIT.

RoadMap85 читає SL/TP через IB open orders:

    reqAllOpenOrders()
      -> openOrder callback
      -> map open STP/LMT orders
      -> enrich BrokerPosition.stop_loss / take_profit

Це дозволило OrdersPage показувати SL/TP, які були створені в TWS або як attached orders.

На цьому етапі RoadMap85 тільки читав existing SL/TP.

Розміщення SL/TP з LGE входить у RoadMap86.

---

## 47.9. Час ручної позиції TWS через reqExecutions

IB position callback не дає canonical opened timestamp.

RoadMap85 додав reconstruction manual TWS position time через executions:

    reqExecutions()
      -> execDetails callback
      -> execution time
      -> map by account / symbol / side

OrdersPage після RoadMap85 може показувати час manual TWS position.

Це не є ідеальна trade history model, але достатнє practical enrichment для runtime position table.

---

## 47.10. Вилучено непрацюючий резервний шлях ринкових даних

Під час RoadMap85 прибрано dead `reqMktData ticks={}` fallback.

Причина:

- market data snapshot у поточному IB Paper/TWS середовищі міг не давати стабільних ticks;
- dead fallback створював шум і ризик зависання/неправильного enrichment;
- RoadMap85 не мав повертати мертвий market-data шлях.

Канонічне правило після RoadMap85:

    Не використовувати dead reqMktData fallback для OrdersPage position enrichment.

Якщо market data буде потрібна пізніше, її треба вводити окремим стабільним шаром, а не прихованим fallback у position refresh.

---

## 47.11. Регресійна перевірка cTrader після RoadMap85

RoadMap85 не зламав cTrader display.

Підтверджено:

- cTrader positions показуються;
- cTrader lot volume показується як 0.01;
- cTrader PnL показується;
- cTrader SL/TP показуються;
- cTrader time показується.

RoadMap85 був broker-specific enrichment для IB і не міняв cTrader execution chain.

---

## 47.12. Життєвий цикл Open/Close не змінювався

RoadMap85 свідомо не переписував manual trading життєвий цикл.

Не змінювалися канонічні робочі ланцюги RoadMap84:

    IB Open MARKET
    IB Close position
    SQLite Trade -> OrderPlan -> BrokerOrder -> Position

Це важливо: RoadMap85 був display/data enrichment task, а не trading execution refactor.

---

## 47.13. Налаштування таблиці OrdersPage

Під час RoadMap85 додатково підправлено відображення таблиці OrdersPage.

Покращено читабельність колонок:

- ID;
- Пара;
- Напрямок;
- Обсяг;
- Ціна входу;
- SL;
- TP;
- Чистий прибуток;
- Час.

Підтверджено, що selection у таблиці лишається видимим.

Кнопки QMessageBox `Yes/No` можуть тимчасово залишатися англійськими. Це UI polish, не Runtime blocker.

---

## 47.14. Підтверджені результати RoadMap85

Підтверджено для IB Paper:

- volume показується як `1 000`;
- entry price показується нормально і без зайвих нулів;
- broker PnL береться з IB `reqPnLSingle`;
- SL/TP читаються з TWS/IB open attached orders;
- manual TWS position time читається через executions;
- dead market data snapshot fallback прибрано;
- OrdersPage показує broker-enriched IB position table.

Підтверджено для cTrader:

- display не зламаний;
- positions читаються;
- SL/TP і PnL показуються;
- Open/Close життєвий цикл не зачеплений.

---

## 47.15. Що не входить у RoadMap85

RoadMap85 не реалізовував:

- IB SL/TP placement з LGE;
- IB bracket orders;
- IB SL/TP modify;
- partial protection warnings;
- position protection coverage model;
- new trading algorithms;
- AUTO trading;
- broker-terminal import у SQLite.

Ці задачі залишилися для наступних RoadMap.

IB SL/TP placement з LGE реалізовано у RoadMap86.

---

## 47.16. Підсумок RoadMap85

RoadMap85 закрив IB OrdersPage broker position enrichment.

Після RoadMap85 OrdersPage став достатньо інформативним для IB Paper manual trading:

- видно volume;
- видно entry price;
- видно PnL;
- видно SL/TP, якщо вони є у TWS;
- видно manual execution time;
- cTrader не зламаний;
- RoadMap84 Open/Close chain не зламаний.

RoadMap85 можна вважати виконаним.

---

# 48. Розміщення IB SL/TP з LGE — RoadMap86

## 48.1. Статус

RoadMap86 виконано і перевірено на IB Paper / TWS.

Головна мета RoadMap86 була досягнута: LGE тепер уміє відкривати IB Forex позиції з optional Stop Loss і Take Profit без ручного створення attached orders у TWS.

Реалізація зроблена без переписування робочого RoadMap84 Open/Close життєвий цикл.

---

## 48.2. Що було перед RoadMap86

Після RoadMap85 уже працювало:

- IB manual MARKET Open з LGE;
- IB manual Close position з LGE;
- IB OrdersPage enrichment:
  - volume;
  - entry price;
  - broker PnL через `reqPnLSingle`;
  - SL/TP reading через `reqAllOpenOrders`;
  - manual TWS execution time через `reqExecutions`;
- cTrader positions display;
- cTrader PnL / SL / TP / time display.

RoadMap85 закрив читання broker-enriched position data.

RoadMap86 додав не читання, а саме розміщення IB SL/TP з LGE.

---

## 48.3. Канонічний шлях виконання

Поточний manual order chain залишився тим самим:

    OrdersPage
      -> RuntimeEngine.place_manual_market_order()
      -> IBRuntimeService.place_market_order()
      -> IBSessionManager / IBAdapter
      -> IBAdapter.place_market_order(...)

UI не звертається до IB напряму.

OrdersPage тільки читає поля:

- symbol;
- side;
- volume;
- stop_loss;
- take_profit;
- comment.

RuntimeEngine передає ці параметри далі в брокерський сервіс.

IBAdapter виконує broker-specific order placement.

---

## 48.4. Зміна RuntimeEngine

У `engine/runtime_engine.py` в IB manual open path прибрано старий guard:

    IB SL/TP bracket orders are not implemented yet

Після RoadMap86 `RuntimeEngine._place_manual_market_order_ib()` більше не блокує IB orders з `stop_loss` або `take_profit`.

Важливо: RuntimeEngine не отримав нової торгової логіки. Він тільки пропускає вже наявні параметри далі в `IBRuntimeService`.

---

## 48.5. MARKET-ордер із підтримкою bracket у IBAdapter

Основна реалізація виконана в `engine/ib_adapter.py`.

`IBAdapter.place_market_order()` тепер працює у двох режимах.

### 48.5.1. Без SL/TP

Якщо `stop_loss is None` і `take_profit is None`, IBAdapter відправляє звичайний MARKET order, як у RoadMap84:

    parent MARKET
    transmit=True

Цей режим підтверджено regression-тестом.

### 48.5.2. З SL/TP

Якщо задано `stop_loss` або `take_profit`, IBAdapter створює bracket/attached orders:

    parent MARKET
    child STP для Stop Loss
    child LMT для Take Profit

Для BUY parent:

    parent: BUY MKT
    stop child: SELL STP
    take-profit child: SELL LMT

Для SELL parent:

    parent: SELL MKT
    stop child: BUY STP
    take-profit child: BUY LMT

Transmit policy:

    parent.transmit = False
    intermediate child.transmit = False
    last child.transmit = True

Якщо є тільки один child order, саме він отримує `transmit=True`.

---

## 48.6. Перевірка IB SL/TP

RoadMap86 не повертав dead market-data path.

Не використовується `reqMktData` для перевірки current market price, щоб не відновити стару проблему з dead `ticks={}` fallback.

Поточна базова validation:

- SL/TP price має бути додатним;
- для BUY, якщо задані та SL, і TP:
  - `SL < TP`;
- для SELL, якщо задані і SL, і TP:
  - `SL > TP`.

Це не повна market validation, але достатній захист від очевидно неправильного bracket direction без зайвого market-data шару.

---

## 48.7. Відстеження ідентифікаторів ордерів

RoadMap86 розширив tracking активних order ids.

Раніше adapter орієнтувався на один `active_order_id`.

Для bracket order потрібно відстежувати parent і child orders, тому додано tracking set:

    active_order_ids

Це потрібно, щоб error/status callback-и не губили child order events.

IB informational messages не вважаються fatal order errors:

- `202`;
- `399`;
- `2109`;
- `2100`;
- `2104`;
- `2106`;
- `2158`.

---

## 48.8. Закриття позиції та очищення дочірніх ордерів

RoadMap86 закрив важливу небезпеку IB attached orders.

Проблема:

    Якщо LGE закриє позицію MARKET order-ом,
    у TWS можуть лишитися активні protective STP/LMT orders.

Це небезпечно, бо після закриття позиції старий SL/TP може перетворитися на новий небажаний trade.

Рішення:

Перед close position IBAdapter виконує пошук related open STP/LMT orders для selected broker position id і скасовує їх через IB cancel order path.

Після цього виконується close MARKET order.

Перевірено:

- close позиції без SL/TP;
- close позиції з full SL/TP;
- close netted позиції з partial SL/TP coverage.

Активні dangling child orders після close не лишилися.

---

## 48.9. Неттовані позиції IB Forex і часткове покриття SL/TP

Під час RoadMap86 виявлено важливу IB-specific особливість.

IB Forex positions є netted.

Приклад:

    Відкрити BUY 1K EURUSD тільки з SL 1.142
    Потім відкрити BUY 1K EURUSD тільки з TP 1.146

У TWS це стає однією net position:

    EURUSD BUY 2K

Але protective orders залишаються окремими:

    SELL STP 1K @ 1.142
    SELL LMT 1K @ 1.146

Це означає:

    SL покриває тільки 1K з 2K
    TP покриває тільки 1K з 2K

Було б неправильно показувати в LGE:

    EURUSD BUY 2 000
    SL 1.142
    TP 1.146

бо це виглядає так, ніби вся позиція 2K повністю захищена.

---

## 48.10. Відображення SL/TP з урахуванням покриття

RoadMap86 додав coverage-aware SL/TP display для IB.

Логіка:

- якщо protective STP/LMT order покриває весь net position volume:
  - SL/TP показується звичайно;
- якщо protective STP/LMT order покриває тільки частину net position volume:
  - SL/TP показується з позначкою `***`;
  - клітинка SL/TP фарбується warning color;
  - внизу OrdersPage показується попередження;
- якщо coverage неоднозначне:
  - використовується warning path;
  - не маскується як повний захист.

Приклад правильного display:

    EURUSD BUY 2 000
    SL 1.142 ***
    TP 1.146 ***

Status warning:

    УВАГА: IB EURUSD BUY 2 000: SL 1 000/2 000, TP 1 000/2 000

Це важливе архітектурне рішення: LGE не має брехати, що весь net position volume захищений, якщо broker open orders покривають тільки частину.

---

## 48.11. Допуски порівняння для покриття SL/TP

Для порівняння IB protective order quantity з net position volume додано іменовані constants у `runtime_constants.py`.

Використовується не magic number в `ib_adapter.py`, а project-level constant.

Сенс tolerance:

- `rel_tol` — дуже мала відносна похибка для float comparison;
- `abs_tol` — абсолютна похибка у IB units, не в lot.

Практичний зміст:

    1000 і 999.999999 вважаються тим самим coverage.
    1000 і 999 не вважаються тим самим coverage.

Це потрібно через float representation і broker/API rounding.

---

## 48.12. Інтерфейс часткового захисту в OrdersPage

У `core/orders_page.py` додано UI handling для partial IB protection.

OrdersPage тепер:

- читає службові SL/TP coverage flags з broker position raw payload;
- додає `***` до partial SL/TP значень;
- фарбує partial SL/TP cell у warning color;
- показує warning text у status area замість звичайного refresh message.

Звичайне повне SL/TP coverage не маркується.

Приклад:

    GBPUSD SELL 1 000
    SL 1.346
    TP 1.339

Якщо SL/TP покриває весь position volume, `***` не показується.

---

## 48.13. Перевірені сценарії IB

### 48.13.1. Відкриття без SL/TP

Перевірено:

    IB Open EURUSD BUY 1 000 без SL/TP

Результат:

- TWS показав `BOT 1K EUR.USD MKT`;
- LGE OrdersPage показав `EURUSD BUY 1 000`;
- SL/TP порожні;
- RoadMap84 Open regression не зламаний.

### 48.13.2. Закриття без SL/TP

Перевірено:

    Close EURUSD BUY 1 000

Результат:

- TWS показав `SLD 1K EUR.USD`;
- IB portfolio position повернувся до 0;
- LGE OrdersPage після refresh показав 0 IB positions.

### 48.13.3. BUY з SL/TP

Перевірено:

    EURUSD BUY 1 000
    SL 1.142
    TP 1.146

Результат у TWS:

    BUY 1K MKT
    SELL 1K STP
    SELL 1K LMT

Результат у LGE:

    EURUSD BUY 1 000
    SL 1.142
    TP 1.146

### 48.13.4. Закриття BUY із SL/TP

Перевірено:

    Close EURUSD BUY 1 000 з attached STP/LMT

Результат:

- позиція закрита;
- active child STP/LMT orders не лишилися;
- LGE OrdersPage після refresh показав 0 positions.

### 48.13.5. SELL з SL/TP

Перевірено:

    EURUSD SELL 1 000
    SL 1.146
    TP 1.142

Результат у TWS:

    SELL 1K MKT
    BUY 1K STP
    BUY 1K LMT

Результат у LGE:

    EURUSD SELL 1 000
    SL 1.146
    TP 1.142

### 48.13.6. Закриття SELL із SL/TP

Перевірено:

    Close EURUSD SELL 1 000 з attached STP/LMT

Результат:

- позиція закрита;
- active child STP/LMT orders не лишилися;
- IB portfolio position повернувся до 0.

### 48.13.7. Лише SL

Перевірено:

    EURUSD BUY 1 000
    SL 1.142
    TP порожній

Результат у TWS:

    BUY 1K MKT
    SELL 1K STP

Результат у LGE:

    EURUSD BUY 1 000
    SL 1.142
    TP порожній

### 48.13.8. Лише TP

Перевірено:

    EURUSD BUY 1 000
    SL порожній
    TP 1.146

Результат у TWS:

    BUY 1K MKT
    SELL 1K LMT

Результат у LGE:

    EURUSD BUY 1 000
    SL порожній
    TP 1.146

### 48.13.9. Часткове покриття

Перевірено:

    EURUSD BUY 1 000 тільки з SL 1.142
    потім EURUSD BUY 1 000 тільки з TP 1.146

IB netted result:

    EURUSD BUY 2 000

Protective orders:

    SELL STP 1 000 @ 1.142
    SELL LMT 1 000 @ 1.146

LGE result:

    EURUSD BUY 2 000
    SL 1.142 ***
    TP 1.146 ***

Warning:

    УВАГА: IB EURUSD BUY 2 000: SL 1 000/2 000, TP 1 000/2 000

Цей результат правильний.

---

## 48.14. cTrader regression-перевірка

Після IB bracket changes виконано cTrader refresh regression.

Результат:

- cTrader positions читаються;
- cTrader SL/TP не зламані;
- cTrader PnL display не зламаний;
- cTrader position table display працює.

RoadMap86 не зачепив cTrader manual/runtime chain.

---

## 48.15. Не зроблено в RoadMap86

RoadMap86 не реалізовував edit existing SL/TP.

Це окремий майбутній блок.

Правильний майбутній UX:

    Виділити позицію
    змінити Stop-loss / Take-profit fields
    натиснути окрему кнопку "Змінити SL/TP"

Правильна IB logic для майбутнього:

    новий SL є, старий SL є      -> modify STP order
    новий SL порожній, старий є  -> cancel STP order
    новий SL є, старого нема     -> create protective STP

    новий TP є, старий TP є      -> modify LMT order
    новий TP порожній, старий є  -> cancel LMT order
    новий TP є, старого нема     -> create protective LMT

Це не треба змішувати з Open або Close.

Кандидат на наступний окремий RoadMap:

    IB SL/TP Modify from LGE

---

## 48.16. Підсумок RoadMap86

RoadMap86 закрив перехід від пасивного читання IB SL/TP до активного розміщення IB protective orders з LGE.

Підтверджено:

- IB MARKET Open без SL/TP не зламаний;
- IB MARKET Close не зламаний;
- IB BUY bracket orders працюють;
- IB SELL bracket orders працюють;
- only SL працює;
- only TP працює;
- close скасовує related child STP/LMT orders;
- partial protection не маскується як full protection;
- OrdersPage показує partial protection через `***` і warning;
- cTrader regression нормальний.

RoadMap86 можна вважати виконаним.

---

# 49. Зміна SL/TP та виконання в IB Paper — RoadMap87–RoadMap89

---

RoadMap87–RoadMap89 завершили повний цикл зміни `Stop Loss` і `Take Profit` для наявних broker positions через LGE.

Підтримано два брокери:

```text
cTrader Demo
Interactive Brokers Paper
```

Канонічний Runtime path:

```text
OrdersPage
    ↓
RuntimeEngine.modify_active_broker_position_sl_tp()
    ↓
BrokerRuntimeService.modify_position_sl_tp()
    ↓
SessionManager.modify_position_sl_tp()
    ↓
BrokerAdapter.modify_position_sl_tp()
    ↓
Broker API
```

`OrdersPage` не звертається безпосередньо до адаптера або API брокера.

---

## 49.1. Межі RoadMap87–RoadMap89

RoadMap87 закрив:

```text
cTrader Modify SL/TP;
вибір наявної позиції в OrdersPage;
синхронізацію symbol, side, SL і TP;
окрему кнопку «Змінити SL/TP»;
автоматичний Refresh після успішної зміни;
IB planner та safety foundation.
```

RoadMap88 закрив внутрішній IB execution layer:

```text
callback operation state;
confirmation policy;
timeout і wait;
execution actions;
IB Contract/Order payloads;
nextValidId;
OCA group;
placeOrder/cancelOrder dispatcher;
broker operation orchestration;
production IBAdapter.modify_position_sl_tp();
IBSessionManager passthrough;
IBRuntimeService passthrough.
```

RoadMap89 закрив:

```text
RuntimeEngine IB branch;
synthetic integration;
OrdersPage integration;
real IB Paper execution;
replacement survivor;
replacement pair;
UI error handling;
final regression.
```

---

## 49.2. Зміна SL/TP у cTrader

Для cTrader використовується broker-native request:

```text
ProtoOAAmendPositionSLTPReq
```

Підтверджено:

```text
створення Stop Loss;
створення Take Profit;
зміна Stop Loss;
зміна Take Profit;
видалення Stop Loss;
видалення Take Profit;
одночасна зміна SL і TP;
автоматичний Refresh після успіху.
```

Канонічний cTrader path:

```text
OrdersPage
    ↓
RuntimeEngine
    ↓
CTraderRuntimeService
    ↓
CTraderSessionManager
    ↓
CTraderAdapter
    ↓
ProtoOAAmendPositionSLTPReq
```

Робочі Open, Close і position snapshot не переписувались.

---

## 49.3. Дії планувальника IB

IB planner:

```text
IBAdapter.build_position_sl_tp_modify_plan()
```

порівнює поточний broker protection із новими значеннями з OrdersPage.

Для кожної ноги planner визначає одну дію:

```text
KEEP
MODIFY
CANCEL
CREATE
BLOCK
```

Значення:

```text
KEEP   — поточна й нова ціна однакові;
MODIFY — наявний order отримує нову ціну;
CANCEL — поле очищено, наявний order треба скасувати;
CREATE — захисту немає, але задано нову ціну;
BLOCK  — безпечне виконання не доведено.
```

Planner не виконує broker operations.

---

## 49.4. Покриття захисту та належність ордерів

Перед виконанням перевіряються:

```text
position account;
position symbol;
position side;
position volume;
protective order action;
full protection coverage;
partial protection coverage;
ambiguous protection coverage;
operational ambiguity;
IB clientId;
orderId;
permId;
Contract object;
Order object;
OCA metadata.
```

Операція блокується, якщо виявлено:

```text
partial coverage;
ambiguous coverage;
кілька operationally ambiguous orders;
different clientId;
відсутній orderId;
відсутній Contract object;
відсутній Order object;
небезпечна OCA-конфігурація;
неповне покриття position volume.
```

У заблокованому plan:

```text
blocked=True
stop_loss_action=BLOCK
take_profit_action=BLOCK
```

До IB API у цьому випадку нічого не передається.

---

## 49.5. OCA

Interactive Brokers використовує:

```text
OCA = One Cancels All
```

Для позиції `BUY`:

```text
SELL STP = Stop Loss
SELL LMT = Take Profit
```

Для позиції `SELL`:

```text
BUY STP = Stop Loss
BUY LMT = Take Profit
```

`SL` і `TP` об’єднуються в одну OCA-групу.

Якщо виконується один order, IB скасовує інший:

```text
спрацював SL → скасувати TP;
спрацював TP → скасувати SL.
```

Це не дозволяє другому protective order залишитися після закриття позиції та випадково відкрити reverse position.

Основні IB-поля:

```text
ocaGroup — ідентифікатор OCA-групи;
ocaType  — правило роботи OCA-групи.
```

Ордер вважається standalone, якщо:

```text
ocaGroup=""
```

Ненульовий `ocaType` без `ocaGroup` сам по собі не робить order членом OCA-групи.

---

## 49.6. Помилка IB 10327

Реальні IB Paper тести підтвердили помилку:

```text
10327
OCA group type revision is not allowed.
```

IB не дозволив:

```text
перетворити чинний OCA-order на standalone;
приєднати чинний standalone order до нової OCA-групи;
змінити OCA-належність чинного order на місці.
```

Тому LGE не змінює `ocaGroup` або `ocaType` чинного order через повторний `placeOrder()` із тим самим `orderId`.

Для зміни структури protection використовуються replacement operations.

---

## 49.7. Звичайний CREATE

Якщо позиція не має SL і TP, а користувач задає обидва рівні:

```text
CREATE SL
CREATE TP
requires_oca_group=True
```

LGE:

```text
1. отримує два нові orderId;
2. створює STP і LMT;
3. задає однаковий ocaGroup;
4. задає узгоджений ocaType;
5. передає обидва orders із transmit=True;
6. чекає broker callbacks;
7. підтверджує обидва активні orders.
```

Після першого реального тесту схема:

```text
перший order transmit=False;
другий order transmit=True
```

виявилася непридатною для двох незалежних OCA-orders.

У TWS перший order залишився локальним із кнопкою `Transmit`, а operation завершилася:

```text
STOP_LOSS=TIMEOUT
```

Після виправлення обидва незалежні OCA-orders передаються з:

```text
transmit=True
```

Підтверджено:

```text
CREATE SL + TP = OK
```

---

## 49.8. MODIFY

Для зміни ціни чинного безпечного order використовується:

```text
placeOrder(existing_order_id, modified_order)
```

Підтверджено:

```text
MODIFY SL;
MODIFY TP;
MODIFY SL + TP;
кількість active protective orders не збільшується;
дублікати не створюються.
```

---

## 49.9. Видалення одного ордера з OCA-пари

Початкова спроба:

```text
KEEP SL
CANCEL TP
```

була небезпечною.

Скасування одного order старої OCA-пари призвело до broker-side скасування другого order.

Реальний результат:

```text
TP скасовано;
SL також зник;
позиція залишилася без protection.
```

Спроба перед скасуванням очистити OCA-поля survivor order:

```text
ocaGroup=""
ocaType=0
```

була відхилена IB:

```text
10327
OCA group type revision is not allowed.
```

Тому реалізовано replacement survivor.

---

## 49.10. Заміна ордера, що залишається

Replacement survivor використовується, коли з OCA-пари треба видалити одну ногу, а другу залишити.

Приклад:

```text
current SL + TP
requested SL + no TP
```

Канонічна послідовність:

```text
1. виділити новий orderId;
2. створити replacement SL без OCA;
3. передати replacement із transmit=False;
4. перевірити відсутність local staging error;
5. скасувати старий TP;
6. дочекатися скасування старої OCA-пари;
7. повторно перевірити position side і volume;
8. передати replacement SL із transmit=True;
9. підтвердити Submitted або PreSubmitted.
```

Дзеркальний сценарій:

```text
current SL + TP
requested no SL + TP
```

працює так само для replacement TP.

Підтверджено на IB Paper:

```text
KEEP SL + CANCEL TP = OK
KEEP TP + CANCEL SL = OK
```

Після виконання залишається рівно один standalone protective order.

---

## 49.11. Локальне попереднє розміщення

Replacement orders спочатку передаються з:

```text
transmit=False
```

Такий order залишається локальним у TWS і не повертається через API як звичайний active open order.

Тому успішний staging визначається не callback `openOrder`, а відсутністю broker error протягом короткого settle interval.

Успішний стан:

```text
STAGED_LOCAL_NO_ERROR
```

Він означає:

```text
local order створено;
миттєвої validation error немає;
order ще не активний на ринку.
```

Якщо staging завершується помилкою:

```text
старі protective orders не скасовуються;
replacement operation припиняється;
користувач отримує помилку.
```

Локальний `transmit=False` order може залишатися в TWS до restart.

LGE не намагається викликати `cancelOrder()` для такого local draft, оскільки IB може повернути:

```text
161
Cancel attempted when order is not in a cancellable state.
```

---

## 49.12. Перевірка позиції перед активацією заміни

Після скасування старого protection і перед передаванням replacement із `transmit=True` LGE повторно отримує position snapshot.

Перевіряються:

```text
position_id;
position side;
position volume.
```

Activation блокується, якщо:

```text
позиція зникла;
side змінився;
volume змінився;
position вже закрита.
```

Це не дозволяє replacement `SELL STP/LMT` відкрити reverse position, якщо початкова `BUY` position уже закрилася.

---

## 49.13. Заміна пари

Replacement pair використовується, коли існує один standalone protective order, а користувач додає другу ногу.

Приклад:

```text
current standalone SL
requested SL + TP
```

Старий standalone SL не приєднується до нової OCA-групи, оскільки це викликає IB error `10327`.

Канонічна послідовність:

```text
1. виділити два нові orderId;
2. створити replacement SL;
3. створити новий TP;
4. задати обом новий ocaGroup;
5. задати обом узгоджений ocaType;
6. передати обидва orders із transmit=False;
7. перевірити local staging обох orders;
8. скасувати старий standalone SL;
9. повторно перевірити position side і volume;
10. передати новий SL із transmit=True;
11. передати новий TP із transmit=True;
12. підтвердити обидва active orders.
```

Дзеркальний сценарій:

```text
current standalone TP
requested SL + TP
```

працює за тією самою схемою.

Підтверджено на IB Paper:

```text
KEEP SL + CREATE TP replacement pair = OK
KEEP TP + CREATE SL replacement pair = OK
```

Після execution у TWS залишаються рівно два active orders:

```text
один STP;
один LMT;
одна OCA-група.
```

---

## 49.14. Видалення обох SL/TP

Якщо користувач очищає обидва поля:

```text
requested SL=None
requested TP=None
```

planner повертає:

```text
CANCEL SL
CANCEL TP
```

Підтверджено на IB Paper:

```text
CANCEL SL + CANCEL TP = OK
```

Фінальний стан:

```text
position залишається відкритою;
active STP = 0;
active LMT = 0.
```

---

## 49.15. Стан брокерської операції

Для SL/TP operation збираються callback-и:

```text
openOrder;
orderStatus;
error;
cancel confirmation.
```

Основні стани:

```text
Submitted
PreSubmitted
Cancelled
ERROR
TIMEOUT
WAITING_TRANSMIT_CONFIRMATION
STAGED_LOCAL_NO_ERROR
```

Операція вважається успішною лише після підтвердження всіх необхідних broker actions.

Відсутність Python exception під час `placeOrder()` або `cancelOrder()` не вважається достатнім підтвердженням.

---

## 49.16. Брокерський payload

IB payload містить:

```text
orderId;
Contract;
Order;
account;
action;
orderType;
totalQuantity;
auxPrice або lmtPrice;
tif;
ocaGroup;
ocaType;
transmit.
```

Для OCA-пари:

```text
обидва orders мають однаковий ocaGroup;
обидва orders мають однаковий ocaType;
обидва orders покривають повний volume position;
обидва orders мають правильний protective action.
```

Одноногий OCA batch заборонений.

Відсутній `Contract`, `Order` або `orderId` блокує `placeOrder()` до першого broker call.

Відсутній `ocaGroup` блокує тільки operation, для якої:

```text
requires_oca_group=True
```

---

## 49.17. Строк дії ордера Time in Force

Для IB manual Open і Close:

```text
MARKET order → DAY
```

Для protective orders:

```text
Stop Loss   → GTC
Take Profit → GTC
```

`DAY` для MARKET використовується тому, що order повинен виконатися негайно і не залишатися до наступної торгової сесії.

`GTC` для SL/TP використовується тому, що protection повинна залишатися активною через ніч і між торговими сесіями.

Реальний IB Paper тест підтвердив, що залишений GTC Stop Loss пережив зміну доби та закрив позицію після досягнення ціни.

---

## 49.18. OrdersPage

OrdersPage підтримує:

```text
вибір broker position;
синхронізацію symbol;
синхронізацію BUY/SELL;
завантаження поточних SL і TP;
введення нових SL і TP;
окрему кнопку «Змінити SL/TP»;
автоматичний Refresh після успішної операції;
відображення broker error;
tooltip із повним текстом помилки.
```

Числові поля приймають:

```text
1.141
1,141
```

Тобто крапка й кома підтримуються як десятковий роздільник.

Довге повідомлення про помилку більше не розтягує головне вікно OrdersPage по ширині.

Повний текст залишається доступним у warning dialog і tooltip.

Колонку `Час` розширено, щоб timestamp position не обрізався.

---

## 49.19. Синтетична інтеграційна перевірка

Підтверджено Runtime path:

```text
RuntimeEngine
    ↓
IBRuntimeService
    ↓
IBSessionManager
    ↓
IBAdapter
```

Тест:

```text
run_runtime_engine_ib_sl_tp_modify_integration_check.py
```

Результат:

```text
session_manager_calls=1
adapter_calls=1
RUNTIME_ENGINE_IB_SL_TP_MODIFY_INTEGRATION_CHECK=OK
```

Підтверджено OrdersPage path:

```text
OrdersPage
    ↓
RuntimeEngine.modify_active_broker_position_sl_tp()
```

Тест:

```text
run_orders_page_ib_sl_tp_modify_check.py
```

Перевірено:

```text
передавання position_id;
передавання SL і TP;
automatic Refresh після успіху;
відсутність Refresh після помилки;
оновлення таблиці;
warning dialog;
error status.
```

Результат:

```text
ORDERS_PAGE_IB_SL_TP_MODIFY_CHECK=OK
```

---

## 49.20. Підтверджені синтетичні тести

Підтверджено:

```text
run_ib_open_order_snapshot_enrichment_check.py
run_ib_protection_coverage_metadata_check.py
run_ib_sl_tp_modify_plan_check.py
run_ib_sl_tp_modify_context_check.py
run_ib_sl_tp_operation_state_check.py
run_ib_sl_tp_operation_confirmation_check.py
run_ib_sl_tp_operation_wait_check.py
run_ib_sl_tp_execution_actions_check.py
run_ib_sl_tp_broker_payloads_check.py
run_ib_sl_tp_execution_preparation_check.py
run_ib_sl_tp_broker_dispatch_check.py
run_ib_sl_tp_broker_operation_check.py
run_ib_sl_tp_replacement_survivor_check.py
run_ib_sl_tp_replacement_pair_check.py
run_runtime_engine_ib_sl_tp_modify_integration_check.py
run_orders_page_ib_sl_tp_modify_check.py
```

Ключові результати:

```text
planner matrix                         : OK
coverage guards                       : OK
ownership guards                      : OK
callback aggregation                  : OK
confirmation policy                   : OK
timeout handling                      : OK
broker payload validation             : OK
dispatcher                            : OK
replacement survivor                  : OK
replacement pair                      : OK
RuntimeEngine integration             : OK
OrdersPage integration                : OK
automatic Refresh                     : OK
```

---

## 49.21. Підтверджені реальні сценарії IB Paper

На реальному IB Paper account підтверджено:

```text
manual BUY без SL/TP                    : OK
CREATE SL + TP                          : OK
MODIFY SL + TP                          : OK
KEEP SL + CANCEL TP                     : OK
KEEP TP + CANCEL SL                     : OK
KEEP SL + CREATE TP replacement pair    : OK
KEEP TP + CREATE SL replacement pair    : OK
CANCEL SL + CANCEL TP                   : OK
OrdersPage automatic Refresh            : OK
comma/dot decimal separator             : OK
long error layout                       : OK
```

Помилка:

```text
10327 OCA group type revision is not allowed
```

не приховується та стала підставою для replacement survivor і replacement pair.

---

## 49.22. Закриття position з активною OCA-парою

Перед фінальним Close було створено:

```text
EURUSD BUY 1000
SELL STP 1K
SELL LMT 1K
```

Position закрито через:

```text
OrdersPage
    ↓
«Закрити позицію»
    ↓
RuntimeEngine
    ↓
IBRuntimeService
    ↓
IBSessionManager
    ↓
IBAdapter
    ↓
SELL MARKET 1000
```

Підтверджений фінал:

```text
EUR.USD POS = 0
active STP = 0
active LMT = 0
orphan protective orders = 0
reverse position = 0
```

У LGE:

```text
таблиця позицій порожня;
Оновлено торгові позиції: 0.
```

У TWS після Close не залишилося active protective orders із кнопкою `Cancel`.

---

## 49.23. Фінальна регресійна перевірка позицій IB

Після завершення real IB Paper tests виконано:

```text
tests/runtime/run_runtime_ib_positions.py
```

Результат:

```text
connected=True
broker_state=CONNECTED
positions_count=0
portfolio snapshot rows=0
open orders snapshot rows=0
IB_POSITIONS_CHECK=OK
Process finished with exit code 0
```

IB повернув технічний callback:

```text
EUR.USD
position=0
avgCost=0
```

LGE правильно не включив його до active positions.

Execution history підтвердила:

```text
BUY  1000 EUR.USD
SELL 1000 EUR.USD
net position = 0
```

Після regression не залишилося:

```text
active EUR.USD position;
active STP;
active LMT;
orphan OCA order;
reverse position.
```

---

## 49.24. Інформаційні повідомлення IB

Під час snapshot можуть надходити:

```text
2104 Market data farm connection is OK
2106 HMDS data farm connection is OK
2158 Sec-def data farm connection is OK
2100 API client has been unsubscribed from account data
```

`2104`, `2106` і `2158` є інформаційними повідомленнями про доступність IB data farms.

`2100` може виникнути після штатного припинення account subscription і сам по собі не означає trading failure.

Trading failure визначається за:

```text
reqId;
orderId;
terminal status;
broker error callback.
```

---

## 49.25. Правила безпеки робочого середовища

Для IB SL/TP execution обов’язкові правила:

```text
1. GUI не викликає IB API напряму.
2. Planner виконується до broker dispatch.
3. Unsafe coverage завжди дає BLOCK.
4. Different-client orders не змінюються.
5. OCA-параметри чинного order не змінюються на місці.
6. Replacement staging виконується до скасування старого protection.
7. Старий protection не скасовується після staging ERROR або TIMEOUT.
8. Position перевіряється повторно перед replacement activation.
9. Broker success потребує callback confirmation.
10. Refresh не створює та не змінює broker orders.
11. SL/TP мають покривати повний position volume.
12. Старі й нові orderId не змішуються.
13. Orphan protective orders після Close неприпустимі.
14. Reverse position після protective execution неприпустима.
```

---

## 49.26. Глобальний стан ринку Forex

RoadMap87 додав у головне вікно LGE глобальний індикатор стану Forex-ринку.

Індикатор відокремлює два різні поняття:

```text
broker connection state
market availability state
```

Broker може перебувати у стані:

```text
CONNECTED
```

але Forex-ринок у цей момент може бути закритий.

Тому наявність broker connection сама по собі не означає, що trading operation доступна.

У головному вікні використовується label:

```text
objectName = lblMarketState
```

Для закритого Forex-ринку показується перекладений текст:

```text
MainAppWindow.statusForexMarketClosed
```

Перевірка market state виконується:

```text
під час startup LGE;
після зміни active broker;
після зміни language;
кожні 60 секунд.
```

Індикатор працює для:

```text
cTrader
Interactive Brokers
```

Поточна Forex market availability policy використовує UTC boundary:

```text
Friday 21:59 UTC  → MARKET_OPEN
Friday 22:00 UTC  → MARKET_CLOSED
Saturday          → MARKET_CLOSED
Sunday 21:59 UTC  → MARKET_CLOSED
Sunday 22:00 UTC  → MARKET_OPEN
```

Це Runtime market-state heuristic для глобального Forex banner.

Він не замінює broker-side order validation і не гарантує доступність конкретного інструмента, account або trading session.

Канонічне правило:

```text
broker CONNECTED
    +
Forex market OPEN
    +
execution дозволено
    ↓
trading operation може продовжуватися
```

Перевірено boundary test:

```text
tests/runtime/run_market_availability_state_check.py
```

Підтверджено:

```text
cTrader Friday/Saturday/Sunday boundaries : OK
IB Friday/Saturday/Sunday boundaries      : OK
MARKET_OPEN / MARKET_CLOSED transition    : OK
global Forex market-state banner          : OK
```

---

## 49.27. Підсумок RoadMap87–RoadMap89

RoadMap87–RoadMap89 завершили робочий SL/TP Modify для cTrader та Interactive Brokers Paper.

Підтверджений канонічний результат:

```text
LGE OrdersPage
    ↓
RuntimeEngine
    ↓
Broker Runtime Service
    ↓
SessionManager
    ↓
Broker Adapter
    ↓
safe planner
    ↓
broker execution
    ↓
callback confirmation
    ↓
automatic OrdersPage Refresh
```

Підтверджено:

```text
cTrader Modify SL/TP                  : DONE
IB planner                            : DONE
IB CREATE SL/TP                       : DONE
IB MODIFY SL/TP                       : DONE
IB CANCEL SL/TP                       : DONE
IB replacement survivor              : DONE
IB replacement pair                  : DONE
IB OCA safety                        : DONE
IB RuntimeEngine integration         : DONE
IB OrdersPage integration            : DONE
IB real Paper tests                  : DONE
IB Close with active OCA pair        : DONE
global Forex market-state banner     : DONE
market availability boundary test    : DONE
orphan protective orders             : 0
reverse position                     : 0
final zero-position regression       : DONE
```

RoadMap87–RoadMap89 можна вважати виконаними.

---

# 50. Віртуальні сегменти позицій IB і групи позицій Runtime — RoadMap90

RoadMap90 додав у LGE логічну декомпозицію Interactive Brokers positions на окремі LGE-owned virtual legs.

Головне правило:

```text
IB broker position
    =
broker-side фінансовий або обліковий стан

LGE virtual position leg
    =
окремий логічний вхід, створений і контрольований LGE
```

Virtual leg не є окремою hedge position у брокера.

Вона зберігає логічну ідентичність угоди LGE навіть тоді, коли IB:

```text
неттить кілька входів в одну position;
показує одну Virtual FX position;
закриває leg через protective order;
прибирає execution history після зміни trading day;
перезапускає TWS;
скидає Virtual FX observation до нуля.
```

RoadMap90 не замінив чинну IB net-position логіку RoadMap89.

Новий virtual-leg layer додано над нею.

---

## 50.1. Межі RoadMap90

RoadMap90 не переписував:

```text
cTrader position lifecycle;
IB manual Open;
IB manual Close;
RoadMap89 broker-net SL/TP Modify;
IB connection і reconnect;
OrdersPage broker Refresh;
Trade → OrderPlan → BrokerOrder → Position;
чинну таблицю positions;
RoadMap89 OCA planner та executor.
```

Додано:

```text
IBVirtualPositionLeg;
IBVirtualPositionLegReconciliationSnapshot;
IBPositionGroup;
IBPositionGroupSnapshot;
schema v5;
virtual-leg persistence;
completed-order evidence;
execution-based reconciliation;
exact leg-level SL/TP Modify;
exact leg-level Close;
CASH Forex Virtual FX handling;
OCA survivor execution guard.
```

---

## 50.2. Канонічна модель віртуального сегмента IB

Чиста Runtime DTO:

```python
IBVirtualPositionLeg
```

Основні поля:

```text
position_uid
trade_uid
broker_position_id
account_id
symbol_name
side
volume
entry_price
opened_utc
source

parent_order_id
stop_loss_order_id
take_profit_order_id
stop_loss
take_profit
oca_group
close_order_ids

leg_status
protection_status
reconciliation_status
reconciliation_messages
```

Стани leg:

```text
OPEN
PARTIALLY_CLOSED
CLOSED
```

Стани protection:

```text
NONE
PARTIAL
COMPLETE
BLOCKED
```

Стани reconciliation:

```text
RECONCILED
UNRECONCILED
BLOCKED
```

Signed volume:

```text
BUY  → positive volume
SELL → negative volume
```

Protective action:

```text
BUY leg  → SELL protection
SELL leg → BUY protection
```

---

## 50.3. Знімок брокерських доказів

Канонічний evidence path:

```text
RuntimeEngine
    ↓
IBRuntimeService
    ↓
IBSessionManager
    ↓
IBAdapter
```

Runtime method:

```python
RuntimeEngine.get_ib_virtual_position_leg_evidence_snapshot()
```

Adapter method:

```python
IBAdapter.get_virtual_position_leg_evidence_snapshot()
```

Snapshot об'єднує:

```text
IB positions;
IB active open orders;
IB completed orders;
IB executions.
```

Для кожного джерела зберігається окремий completeness flag:

```text
positions_complete
open_orders_complete
completed_orders_complete
executions_complete
```

Неповний snapshot не може бути виданий за завершений reconciliation result.

Для completed orders використовуються callback-и:

```text
completedOrder
completedOrdersEnd
```

Запит:

```text
reqCompletedOrders(apiOnly=False)
```

дозволяє отримувати також ордери, створені або видимі через TWS.

---

## 50.4. Доказова прив'язка ордерів до віртуального сегмента

Пріоритет identity evidence:

```text
1. збережений child broker order ID;
2. parentOrderId;
3. permId;
4. OCA group;
5. account + contract;
6. protective action;
7. exact quantity;
8. matching execution;
9. same clientId.
```

Заборонено визначати ownership лише за:

```text
symbol;
side;
price;
приблизним volume;
послідовністю orderId.
```

Причина:

```text
один symbol може мати кілька LGE legs;
кілька legs можуть мати однакові або близькі SL/TP;
IB може неттити position;
replacement створює нові child order IDs;
completed orders можуть зникати з active snapshot.
```

Unknown ownership завжди дає:

```text
BLOCKED
```

---

## 50.5. Звірка

Pure reconciler:

```python
reconcile_ib_virtual_position_legs(
    legs,
    evidence_snapshot,
)
```

Вхідні дані:

```text
RuntimeRepository leg seeds
+
IB positions
+
IB active orders
+
IB completed orders
+
IB executions
```

Вихід:

```python
IBVirtualPositionLegReconciliationSnapshot
```

Для звичайної IB net position базова інваріанта:

```text
signed sum OPEN/PARTIALLY_CLOSED legs
    ==
IB broker signed quantity
```

Якщо рівність не доведена:

```text
reconciliation_status = BLOCKED
```

Leg-level Modify або Close для такої group заборонені.

---

## 50.6. IB CASH Forex і спостереження Virtual FX

Для IB CASH Forex рядок position у TWS/API не завжди є terminal broker net truth.

Він може бути:

```text
Virtual FX observation;
результатом executions поточного TWS session;
скинутим до нуля після restart;
відмінним від історичної суми LGE executions;
збереженим після закриття всіх LGE legs.
```

Тому додано:

```text
IB_BROKER_POSITION_KIND_NET
IB_BROKER_POSITION_KIND_VIRTUAL_FX
```

Для Virtual FX:

```text
broker_quantity_is_terminal_truth = False
```

Канонічна доказова база для CASH Forex:

```text
persisted LGE legs
+
exact known order IDs
+
IB executions
+
active protective orders
+
completed orders
+
Virtual FX observation offset
```

Virtual FX observation не використовується як єдиний доказ відкриття або закриття leg.

---

## 50.7. Зсув спостереження CASH FX

Для операцій Modify та Close використовується offset:

```text
observation offset
    =
IB Virtual FX quantity
    -
signed quantity recognized LGE executions
```

Перед broker operation фіксується baseline offset.

Після операції перевіряється:

```text
offset before operation
    ==
offset after operation
```

Допустимі випадки:

```text
Virtual FX дорівнює recognized executions;
Virtual FX reset до 0 після TWS restart;
ненульовий стабільний offset;
Virtual FX змінюється рівно на execution виконаної операції.
```

Блокуються:

```text
неочікувана зміна offset;
unknown same-contract execution;
execution іншої невідомої LGE operation;
розбіжність quantity;
розбіжність action.
```

---

## 50.8. Схема збереження v5

Runtime database schema:

```text
SCHEMA_VERSION = 5
```

Додано дві таблиці:

```text
ib_virtual_position_legs
ib_virtual_position_leg_orders
```

Таблиця `positions` не перетворювалася на virtual-leg table.

### `ib_virtual_position_legs`

Зберігає поточний логічний стан leg:

```text
position_uid
trade_uid
broker_position_id
account_id
symbol
side

initial_volume
remaining_volume
entry_price
opened_utc
source

parent_order_id
stop_loss_order_id
take_profit_order_id
stop_loss
take_profit
oca_group

leg_status
protection_status
reconciliation_status
reconciliation_messages_json

closed_utc
created_utc
updated_utc
```

`initial_volume` і `remaining_volume` розділено для майбутнього `PARTIALLY_CLOSED`.

### `ib_virtual_position_leg_orders`

Зберігає order identity та історію replacements:

```text
position_uid
order_role
broker_order_id
parent_order_id
perm_id
client_id

action
order_type
quantity
price

oca_group
oca_type
execution_status
is_active
created_utc
updated_utc
```

Order roles:

```text
PARENT
STOP_LOSS
TAKE_PROFIT
CLOSE
```

Partial unique index дозволяє тільки один active mapping на:

```text
position_uid + order_role
```

Старі order rows не видаляються після replacement.

Вони переводяться в:

```text
is_active = 0
```

---

## 50.9. Значення активного зіставлення PARENT

`PARENT` mapping залишається active після закриття leg.

Це не означає, що MARKET order залишається активним у TWS.

Його призначення:

```text
стабільна identity leg;
зв'язок position_uid з початковим broker order;
execution history;
reconciliation після restart;
аудит походження leg.
```

Для закритої leg нормальний persistence state:

```text
PARENT      active identity mapping
STOP_LOSS   inactive
TAKE_PROFIT inactive
CLOSE       inactive execution history
```

---

## 50.10. RuntimeRepository

Основні repository methods:

```python
get_open_ib_virtual_position_leg_seeds()
upsert_ib_virtual_position_leg()
set_active_ib_virtual_position_leg_order()
deactivate_ib_virtual_position_leg_order()
get_ib_virtual_position_leg()
get_ib_virtual_position_leg_orders()

persist_confirmed_ib_virtual_position_leg_open()
bootstrap_confirmed_ib_virtual_position_leg_snapshot()
sync_reconciled_ib_virtual_position_leg_snapshot()
persist_confirmed_ib_virtual_position_leg_close()
```

Persistence виконується атомарно.

Для складних sync/bootstrap operations використовується SQLite savepoint.

Заборонено записувати snapshot, якщо він:

```text
incomplete;
BLOCKED;
UNRECONCILED;
містить unmapped protection;
містить duplicate position_uid;
містить unknown ownership;
містить partial operation evidence.
```

---

## 50.11. Контрольоване початкове завантаження

Початкові RoadMap90 legs були створені до schema v5.

Тому використано контрольований bootstrap уже доказово підтвердженого snapshot.

Bootstrap не реконструював order IDs припущеннями.

Було записано:

```text
EURUSD BUY 1K
parent 111
SL 113
CLOSED

EURUSD BUY 2K
parent 114
SL 116
TP 115
CLOSED

GBPUSD BUY 3K
parent 117
SL 119
CLOSED

GBPUSD SELL 2K
parent 120
TP 121
CLOSED
```

Bootstrap:

```text
перевіряв UID;
перевіряв parent order IDs;
перевіряв logical side і volume;
працював спочатку в PLAN;
створював backup перед APPLY;
був ідемпотентним;
не створював broker orders.
```

---

## 50.12. Закриття, ініційоване брокером

Reconciler розпізнає закриття leg через broker protective execution тільки за сукупністю доказів:

```text
exact child order ID;
matching parent або persisted identity;
account + contract;
correct protective action;
exact execution quantity;
same clientId;
completed protective order;
matching execution.
```

Completed-order `total_quantity=0` не вважається достатнім доказом помилки.

Terminal quantity береться з matching execution.

Підтверджені broker-triggered closes:

```text
EURUSD BUY 1K  → SL 113
EURUSD BUY 2K  → SL 116
GBPUSD BUY 3K  → SL 119
GBPUSD SELL 2K → TP 121
```

---

## 50.13. Групи позицій Runtime

Чисті DTO:

```python
IBPositionGroup
IBPositionGroupSnapshot
```

Group об'єднує:

```text
broker-side position або Virtual FX observation
+
zero or more LGE virtual legs
```

Group modes:

```text
LGE_VIRTUAL_LEGS
NET_ONLY
```

`NET_ONLY` використовується для broker-only/manual/imported positions.

Для них:

```text
legs = []
leg_operations_enabled = False
```

Основні group fields:

```text
broker_position_id
account_id
symbol_name
broker_position_present
broker_side
broker_volume
broker_signed_volume
broker_entry_price
broker_position_kind
current_price
unrealized_pnl

group_mode
reconciliation_status
reconciliation_messages
legs
```

Runtime method:

```python
RuntimeEngine.get_active_broker_position_groups()
```

Group із persisted LGE legs не зникає, навіть якщо IB не повернув position row:

```text
broker_position_present = False
```

---

## 50.14. Канонічні Runtime methods

RoadMap90 додав:

```python
RuntimeEngine.get_open_runtime_position_legs()

RuntimeEngine.get_active_broker_position_groups()

RuntimeEngine.sync_reconciled_ib_virtual_position_legs()

RuntimeEngine.modify_runtime_position_leg_sl_tp(
    position_uid,
    stop_loss,
    take_profit,
)

RuntimeEngine.close_runtime_position_leg(
    position_uid,
)

RuntimeEngine.recover_confirmed_runtime_position_leg_close(
    position_uid,
    close_order_id,
)
```

GUI не працює напряму з IBAdapter.

Канонічний broker path:

```text
OrdersPage
    ↓
RuntimeEngine
    ↓
IBRuntimeService
    ↓
IBSessionManager
    ↓
IBAdapter
    ↓
IB API
```

---

## 50.15. Автоматичне збереження після Open

Після нового LGE IB Open виконується:

```text
IB MARKET execution
    ↓
legacy Trade → OrderPlan → BrokerOrder → Position
    ↓
exact parent execution verification
    ↓
exact SL/TP child mapping
    ↓
schema v5 virtual-leg persistence
```

Зберігаються:

```text
position_uid
trade_uid
logical side
logical volume
entry execution price
opened time
parent order ID
SL order ID
TP order ID
SL/TP prices
OCA group
leg_status = OPEN
reconciliation_status = RECONCILED
```

IB Virtual FX quantity не використовується як identity нового входу.

Open proof вимагає:

```text
before/after broker evidence;
exact parent execution;
exact child IDs;
parentOrderId;
account + contract;
action;
quantity;
same clientId.
```

---

## 50.16. Точна зміна SL/TP на рівні сегмента

Канонічний виклик:

```python
RuntimeEngine.modify_runtime_position_leg_sl_tp(
    position_uid,
    stop_loss,
    take_profit,
)
```

Вибір виконується за:

```text
position_uid
```

а не лише за:

```text
broker_position_id;
symbol;
side;
price;
Virtual FX quantity.
```

RoadMap90 повторно використовує RoadMap89 planner та broker executor.

Підтримані actions:

```text
KEEP
MODIFY
CANCEL
CREATE
```

Підтверджені комбінації:

```text
KEEP / KEEP
MODIFY / KEEP
KEEP / MODIFY
MODIFY / MODIFY

CANCEL / CANCEL
CREATE / CREATE

KEEP SL + CANCEL TP
KEEP TP + CANCEL SL

KEEP SL + CREATE TP
KEEP TP + CREATE SL

MODIFY SL + CANCEL TP
MODIFY TP + CANCEL SL

MODIFY SL + CREATE TP
MODIFY TP + CREATE SL
```

---

## 50.17. Звірка після зміни

Після broker confirmation RuntimeEngine не покладається на один миттєвий snapshot.

Використовується retry policy:

```text
attempts = 4
delay = 0.5 seconds
```

Persistence виконується лише коли підтверджено:

```text
leg = RECONCILED
group = RECONCILED
SL відповідає запиту
TP відповідає запиту
protection status правильний
unmapped protective orders = []
CASH FX observation offset не змінився
```

Якщо evidence не стабілізувався, повертається error з:

```text
leg status;
group status;
reconciliation messages;
unmapped order IDs;
expected/actual SL;
expected/actual TP;
protection status.
```

---

## 50.18. Заміна ордера, що залишається в OCA

Для операції:

```text
KEEP SL + CANCEL TP
```

стара OCA-пара не редагується небезпечним способом на місці.

Виконується:

```text
1. staged standalone survivor SL;
2. execution guard;
3. cancel старої OCA-пари;
4. activate survivor;
5. persist new SL order ID;
6. clear TP;
7. clear OCA group.
```

Підтверджений real IB Paper сценарій:

```text
стара OCA:
SL 131
TP 130

результат:
standalone SL 132
TP = None
OCA = ""
```

---

## 50.19. Заміна OCA-пари

Для операції:

```text
KEEP standalone SL + CREATE TP
```

виконується:

```text
1. staged нова SL/TP OCA-пара;
2. execution guard;
3. cancel standalone survivor;
4. activate нову OCA-пару;
5. persist new child IDs;
6. persist new OCA group.
```

Підтверджений real IB Paper сценарій:

```text
standalone:
SL 132

нова OCA:
SL 133
TP 134
OCA LGE_SLTP_1_133_134
```

---

## 50.20. Захист виконання віртуального сегмента

Під час OCA survivor/relink не використовується broker net quantity як єдиний guard.

Guard працює за executions:

```text
1. знімається baseline execution set;
2. replacement staged локально;
3. перед activation повторно читаються executions;
4. нове same-contract execution блокує activation;
5. лише стабільний execution set дозволяє завершення.
```

Розрізняються:

```text
protective execution old SL/TP → BLOCK
unknown same-contract execution → BLOCK
execution іншого symbol → не стосується вибраної leg
```

Перевірено:

```text
stable_guard_confirmed=True
unrelated_symbol_ignored=True
protective_execution_blocked=True
unknown_execution_blocked=True
broker_net_position_guard_bypassed=True
```

---

## 50.21. Точне закриття віртуального сегмента

Канонічний виклик:

```python
RuntimeEngine.close_runtime_position_leg(
    position_uid,
)
```

Послідовність:

```text
1. pre-close reconciliation;
2. CASH FX offset baseline;
3. exact ownership validation;
4. cancel тільки SL/TP вибраної leg;
5. confirm cancellation;
6. opposite MARKET exact leg volume;
7. confirm exact execution;
8. post-close evidence;
9. verify stable CASH FX offset;
10. verify no active protection for leg;
11. verify other legs unchanged;
12. leg → CLOSED;
13. remaining_volume → 0;
14. persist CLOSE order.
```

Для SELL leg:

```text
Close action = BUY
```

Для BUY leg:

```text
Close action = SELL
```

---

## 50.22. Відновлення закриття

Якщо broker Close уже виконано, але persistence не завершилася, повторно надсилати MARKET order заборонено.

Використовується:

```python
RuntimeEngine.recover_confirmed_runtime_position_leg_close(
    position_uid,
    close_order_id,
)
```

Recovery:

```text
не створює нового broker order;
перевіряє completed MARKET order;
перевіряє exact execution;
перевіряє action і quantity;
перевіряє account + contract;
перевіряє неактивність old SL/TP;
записує вже виконаний Close у schema v5.
```

Підтверджений real recovery:

```text
leg parent = 123
close order = 128
side = BUY
quantity = 1K
result = CLOSED
```

---

## 50.23. Правила безпеки робочого середовища

Для IB virtual-leg operations обов'язкові правила:

```text
1. Leg operation виконується тільки за position_uid.
2. Leg має бути RECONCILED.
3. Group має бути RECONCILED.
4. Incomplete evidence дає BLOCK.
5. Unmapped protection дає BLOCK.
6. Unknown ownership дає BLOCK.
7. Different-client order дає BLOCK.
8. Missing child mapping дає BLOCK.
9. Partial execution без повного доказу дає BLOCK.
10. Unknown same-contract execution дає BLOCK.
11. Unexpected CASH FX offset change дає BLOCK.
12. OCA survivor активується тільки після execution guard.
13. Broker success потребує callback або execution confirmation.
14. Persistence виконується тільки після settled evidence.
15. Partial persistence заборонена.
16. Старі order mappings не видаляються.
17. Повторний Close після підтвердженого execution заборонений.
18. Recovery не надсилає trading order.
19. Orphan protective order неприпустимий.
20. Reverse logical leg не створюється з Virtual FX observation.
```

---

## 50.24. Матриця синтетичних тестів

Основні RoadMap90 tests:

```text
run_ib_virtual_leg_model_check.py
run_ib_virtual_leg_reconciliation_check.py
run_ib_virtual_leg_completed_order_evidence_check.py
run_runtime_repository_ib_virtual_leg_seed_check.py
run_runtime_repository_ib_virtual_leg_persistence_check.py
run_runtime_repository_ib_virtual_leg_confirmed_bootstrap_check.py
run_runtime_engine_ib_virtual_leg_evidence_check.py
run_runtime_engine_ib_virtual_legs_check.py
run_ib_virtual_leg_group_snapshot_check.py
run_ib_position_groups_live_readonly_check.py
run_runtime_engine_ib_virtual_leg_open_persistence_check.py
run_runtime_engine_ib_virtual_leg_modify_check.py
run_runtime_engine_ib_virtual_leg_create_cancel_check.py
run_ib_virtual_leg_oca_execution_guard_check.py
run_runtime_engine_ib_virtual_leg_close_check.py
```

Перевірено:

```text
model DTO                            : OK
signed volume                        : OK
repository seeds                     : OK
schema v4 → v5 migration             : OK
foreign keys                         : OK
bootstrap idempotency                : OK
evidence completeness                : OK
broker-triggered Close               : OK
Virtual FX reset                     : OK
nonzero CASH FX offset Modify        : OK
nonzero CASH FX offset Close         : OK
post-Modify retry                    : OK
OCA survivor                         : OK
OCA pair relink                      : OK
execution guard                      : OK
Close recovery                       : OK
BLOCKED snapshot persistence reject  : OK
```

---

## 50.25. Реальні тести IB Paper

### Початкові змішані сегменти

Підтверджено:

```text
EURUSD:
BUY 1K
BUY 2K
broker position / observation 3K

GBPUSD:
BUY 3K
SELL 2K
broker position / observation 1K
```

### Виконання, ініційовані брокером

Підтверджено:

```text
EURUSD BUY 1K  → CLOSED by SL
EURUSD BUY 2K  → CLOSED by SL
GBPUSD BUY 3K  → CLOSED by SL
GBPUSD SELL 2K → CLOSED by TP
```

### Життєвий цикл SELL 1K — parent 123

Підтверджено:

```text
Open SELL 1K
parent 123
SL 125
TP 124

Modify:
SL 1.15
TP 1.14

CANCEL pair:
124 / 125 inactive

CREATE pair:
SL 126
TP 127
OCA LGE_SLTP_1_126_127

Close:
BUY MKT 128
leg CLOSED
```

Close persistence було завершено через controlled recovery.

### Життєвий цикл SELL 1K — parent 129

Підтверджено:

```text
Open SELL 1K
parent 129
entry 1.14335
SL 131
TP 130

Modify only SL:
SL 131 → 1.152
TP 130 KEEP

KEEP SL + CANCEL TP:
old SL 131 cancelled
old TP 130 cancelled
standalone survivor SL 132

KEEP standalone SL + CREATE TP:
old SL 132 cancelled
new SL 133
new TP 134
OCA LGE_SLTP_1_133_134

Close:
cancel SL 133
cancel TP 134
BUY MKT 135
leg CLOSED
```

---

## 50.26. Фінальний стан SQLite

У фінальному RoadMap90 ZIP:

```text
schema version                       = 5
ib_virtual_position_legs             = 6
ib_virtual_position_leg_orders       = 22

OPEN legs                            = 0
CLOSED legs                          = 6
PARTIALLY_CLOSED legs                = 0

active STOP_LOSS mappings            = 0
active TAKE_PROFIT mappings          = 0
active CLOSE mappings                = 0
active PARENT identity mappings      = 6

open RuntimeRepository seeds         = 0
orphan protective orders             = 0
```

Усі шість persisted legs мають:

```text
leg_status = CLOSED
remaining_volume = 0
reconciliation_status = RECONCILED
protection_status = NONE
```

Active `PARENT` mappings є історичною identity, а не активними TWS orders.

---

## 50.27. Фінальний стан брокера

Після останнього real Close:

```text
EURUSD broker position / observation = 0
active protective STP                = 0
active protective LMT                = 0
open LGE virtual legs                = 0
orphan protective orders             = 0
reverse LGE leg                      = 0
```

У TWS не залишилося active protective orders із кнопкою `Cancel`.

---

## 50.28. Що перенесено в RoadMap91

RoadMap90 завершив broker runtime, reconciliation та persistence foundation.

У RoadMap91 переходять:

```text
OrdersPage hierarchical grouping;
broker group row;
nested virtual-leg rows;
QTreeWidget або QTreeView;
selection by position_uid;
leg-level Modify з OrdersPage;
leg-level Close з OrdersPage;
calculated virtual-leg PnL;
broker PnL на group row;
selection persistence після Refresh;
повне row selection;
прибирання current-cell рамки;
tooltip для partial/blocked protection;
зрозумілий reconciliation status;
UI retranslation;
final OrdersPage real tests.
```

OrdersPage не повинен імітувати hierarchy ручними відступами у звичайному `QTableWidget`.

---

## 50.29. Підсумок RoadMap90

RoadMap90 завершив робочу основу Runtime для віртуальних сегментів позицій IB.

Підтверджено:

```text
IB virtual-leg DTO                     : DONE
IB position group DTO                  : DONE
completed-order evidence               : DONE
execution evidence                     : DONE
schema v5                              : DONE
controlled bootstrap                   : DONE
automatic Open persistence             : DONE
broker-triggered Close reconciliation  : DONE
CASH Forex Virtual FX handling         : DONE
Virtual FX reset handling              : DONE
Virtual FX offset baseline             : DONE
leg-level MODIFY                       : DONE
leg-level CANCEL pair                  : DONE
leg-level CREATE pair                  : DONE
OCA survivor                           : DONE
OCA pair relink                        : DONE
execution guard                        : DONE
exact leg Close                        : DONE
Close recovery                         : DONE
atomic persistence                     : DONE
open Runtime seeds                     : 0
active protective orders               : 0
orphan protective orders               : 0
reverse logical legs                   : 0
real IB Paper lifecycle                : DONE
```

RoadMap90 можна вважати виконаним.

Наступний етап:

```text
RoadMap91
    =
OrdersPage IB Position Groups
+
hierarchical virtual-leg UI
+
leg-level UI operations
+
leg PnL
+
UI cleanup
```

---

# 51. Групи позицій IB та інтерфейс віртуальних сегментів OrdersPage — RoadMap91

## 51.1. Мета RoadMap91

RoadMap91 завершив перенесення моделі віртуальних сегментів позицій IB у робочий інтерфейс `OrdersPage`.

Головний результат:

```text
один broker CASH Forex net position
    ↓
одна group-row у OrdersPage
    ↓
окремі дочірні LGE virtual-leg rows
```

Користувач отримав можливість:

```text
переглядати IB position groups;
розкривати окремі virtual legs;
бачити SL/TP кожної leg;
бачити розрахований PnL кожної leg;
змінювати SL/TP вибраної leg;
закривати точний обсяг вибраної leg;
відновлювати delayed Open/Close без повторного ордера;
працювати з кількома валютними парами одночасно.
```

---

## 51.2. Канонічний ланцюжок Runtime

OrdersPage не звертається безпосередньо до IB API або SQLite.

Канонічний шлях:

```text
OrdersPage
    ↓
RuntimeEngine
    ↓
IBRuntimeService
    ↓
IBSessionManager
    ↓
IBAdapter
    ↓
IB API
```

Persistence:

```text
RuntimeEngine
    ↓
RuntimeRepository
    ↓
SQLite
```

Основні RuntimeEngine calls:

```python
get_active_broker_position_groups()

modify_runtime_position_leg_sl_tp(
    position_uid,
    stop_loss,
    take_profit,
)

close_runtime_position_leg(
    position_uid,
)

recover_pending_ib_manual_market_order_opens()

recover_pending_runtime_position_leg_closes()
```

Заборонено:

```text
direct IB API calls із OrdersPage;
direct SQLite reads із OrdersPage;
ручне формування IB orders у Qt handlers;
ідентифікація virtual leg лише за symbol або broker net volume.
```

---

## 51.3. Ієрархічна OrdersPage

Для таблиці позицій використовується hierarchical widget.

Структура IB group:

```text
EURUSD | Virtual FX | BUY | 3 000 | MULTI | MULTI
    ├── LGE LEG | BUY | 1 000 | SL 1.139 | TP 1.146
    └── LGE LEG | BUY | 2 000 | SL 1.138 | TP 1.147
```

Group-row:

```text
представляє broker-side CASH Forex observation;
не є окремою LGE virtual leg;
не отримує position_uid;
використовує broker_position_id як stable key.
```

Child-row:

```text
представляє одну точну LGE virtual leg;
має власний position_uid;
має власний volume;
має власні SL/TP;
має власний reconciliation status;
має власний calculated PnL.
```

---

## 51.4. Режими груп

Підтримуються режими:

```text
LGE_VIRTUAL_LEGS
NET_ONLY
```

### LGE_VIRTUAL_LEGS

Group містить persisted LGE legs.

Для group-row:

```text
Modify disabled;
Close disabled;
користувач повинен вибрати конкретну child leg.
```

### NET_ONLY

Broker position не має розкладення на LGE-owned legs.

Для безпечної NET_ONLY row дозволяються broker-level operations:

```text
Modify SL/TP;
Close broker position.
```

---

## 51.5. Спостереження Virtual FX

IB CASH Forex position row не трактується як окрема справжня hedge-position.

Вона є:

```text
Virtual FX broker observation
```

Тому:

```text
broker net quantity не створює автоматично нову LGE leg;
broker average price не підміняє entry price окремих legs;
broker PnL не розподіляється механічно між legs;
reverse broker observation не створює reverse logical leg.
```

Якщо broker position-row відсутня, але open LGE legs повністю reconciled, group-row будується з legs:

```text
group side   = signed sum open legs;
group volume = absolute signed sum open legs.
```

Підтверджено:

```text
missing broker row:
BUY 1 000 + BUY 2 000
    →
group BUY 3 000
```

Якщо broker row є stale або суперечить open reconciled legs:

```text
side і volume group-row беруться з reconciled open legs;
ненадійні broker entry/PnL fields не показуються;
tooltip пояснює Virtual FX observation.
```

Якщо всі persisted legs закриті, stale Virtual FX observation не показується як активна LGE position group.

---

## 51.6. Правила вибору

Для кожного рядка зберігаються runtime roles:

```text
row kind;
stable key;
broker_position_id;
position_uid;
symbol;
side;
volume;
raw SL;
raw TP;
group mode;
operations enabled.
```

При виборі child leg:

```text
symbol переноситься у ComboBox;
side переноситься у control;
SL переноситься у поле Stop Loss;
TP переноситься у поле Take Profit;
Modify активується;
Close активується.
```

При виборі Virtual FX group-row:

```text
Modify disabled;
Close disabled;
виводиться вимога вибрати конкретну virtual leg.
```

---

## 51.7. Відновлення вибору

Після Refresh OrdersPage відновлює selection за stable identity.

Для IB virtual leg:

```text
stable identity = position_uid
```

Підтверджено:

```text
same_leg_restored=True
parent_expanded=True
closed_leg_selection_cleared=True
```

Якщо leg після операції закрилася:

```text
закритий child-row зникає;
selection очищається;
інша leg залишається видимою;
group залишається розгорнутою, якщо має open legs.
```

---

## 51.8. Автоматичне оновлення

OrdersPage автоматично виконує Refresh при активації сторінки.

Послідовність для IB:

```text
1. recover pending manual Opens;
2. recover pending virtual-leg Closes;
3. отримати position-group snapshot;
4. оновити hierarchy;
5. відновити selection;
6. оновити reconciliation status;
7. оновити Σ PnL.
```

Підтверджено:

```text
activation_refresh_calls=1
activation_open_recovery_calls=1
```

Refresh також виконується після успішних:

```text
Open;
Modify SL/TP;
Close.
```

Кнопка `Оновити` залишається для ручної перевірки стан брокера.

---

## 51.9. PnL віртуального сегмента

IB не надає окремий `reqPnLSingle` для логічної LGE virtual leg усередині одного CASH Forex net position.

Тому використовується calculated PnL.

Для BUY:

```text
PnL = (current_price - entry_price) × volume
```

Для SELL:

```text
PnL = (entry_price - current_price) × volume
```

Позначення:

```text
≈ 6.00
≈ 4.00
```

Символ `≈` означає:

```text
calculated virtual-leg PnL;
не broker-native reqPnLSingle.
```

Підтверджено:

```text
BUY PnL  = 6.00
SELL PnL = 10.00
missing current price → PnL unavailable
```

---

## 51.10. Загальний підсумок PnL

У нижній частині OrdersPage додано summary:

```text
Σ PnL: value
```

Для IB virtual legs:

```text
Σ PnL: ≈ 10.00
```

Сума рахується лише за видимими open LGE legs і не дублює broker group PnL.

Для cTrader:

```text
Σ PnL: 2.00
```

використовується broker-provided net PnL відкритих позицій.

Якщо PnL відсутній:

```text
Σ PnL: —
```

---

## 51.11. Зміна SL/TP віртуального сегмента

Канонічний виклик:

```python
RuntimeEngine.modify_runtime_position_leg_sl_tp(
    position_uid,
    stop_loss,
    take_profit,
)
```

Перед виконанням показується confirmation:

```text
position_uid;
side;
volume;
new SL;
new TP.
```

Операція дозволена лише для exact child leg.

Підтримуються:

```text
KEEP;
MODIFY;
CANCEL;
CREATE;
OCA relink;
standalone survivor replacement.
```

Після успіху:

```text
broker orders перевіряються;
persistence оновлюється;
OrdersPage автоматично виконує Refresh;
та сама leg залишається вибраною.
```

Підтверджено:

```text
position_uid = exact selected leg
SL = 1.142
TP = 1.159
group_refresh_calls = 2
selection persisted
```

---

## 51.12. Точне закриття віртуального сегмента

Канонічний виклик:

```python
RuntimeEngine.close_runtime_position_leg(
    position_uid,
)
```

Закривається:

```text
лише вибрана virtual leg;
лише exact leg volume;
лише протилежною MARKET action;
лише після exact ownership та reconciliation checks.
```

Для BUY leg:

```text
Close = SELL exact volume
```

Для SELL leg:

```text
Close = BUY exact volume
```

Перед Close користувач бачить:

```text
short position_uid;
side;
volume;
SL;
TP.
```

Після підтвердженого Close:

```text
leg_status = CLOSED;
remaining_volume = 0;
protection_status = NONE;
active SL/TP mappings = 0;
CLOSE order записаний у history;
інша leg не змінюється.
```

---

## 51.13. Затримане підтвердження закриття

IB може прийняти MARKET order, але execution evidence може надійти із затримкою.

У такій ситуації LGE не показує звичайний generic timeout.

Користувач отримує повідомлення:

```text
Підтвердження закриття затримується.
Не повторюйте команду «Закрити».
LGE відновить збережене брокерське замовлення.
close_order_id=...
```

Головне правило:

```text
після timeout повторний Close заборонений.
```

LGE зберігає exact identity:

```text
position_uid;
close_order_id;
account;
symbol;
side;
quantity.
```

Pending Close зберігається як active `CLOSE` mapping зі статусом очікування підтвердження.

---

## 51.14. Автоматичне відновлення закриття

Після delayed Close RuntimeEngine:

```text
1. повторно читає broker execution evidence;
2. шукає exact close_order_id;
3. перевіряє account;
4. перевіряє symbol;
5. перевіряє action;
6. перевіряє exact quantity;
7. перевіряє old protection;
8. завершує persistence;
9. не надсилає другого MARKET order.
```

Recovery запускається:

```text
одразу після warning через Refresh;
під час наступного ручного Refresh;
після повторного запуску LGE.
```

Підтверджено:

```text
timeout_close_auto_recovered=True
timeout_recovery_attempts=1
timeout_close_pending_saved=True
timeout_close_blocked_without_evidence=True
timeout_close_restart_recovered=True
duplicate_close_calls=0
```

Real IB Paper підтвердив повідомлення:

```text
Позиція закрита через затримку з підтвердженням брокера.
close_order_id=166
```

Повторне натискання `Оновити` для завершення цього сценарію не знадобилося.

---

## 51.15. Ідентичність ручного Open під час тайм-ауту

Для manual Open IB також може прийняти MARKET order раніше, ніж LGE отримає остаточне execution evidence.

IBAdapter зберігає exact submitted identity:

```text
parent order_id;
child SL order_id;
child TP order_id;
account;
symbol;
side;
quantity;
clientId;
comment.
```

При timeout користувач отримує:

```text
IB accepted the manual Open request,
but final execution confirmation is delayed.

Do not repeat Open.

LGE saved the exact order and will recover it
automatically during Refresh.

order_id=...
```

Повторний Open заборонений, оскільки брокерський ордер уже може бути виконаний.

---

## 51.16. Збереження ручного Open, що очікує підтвердження

Schema v6 додала таблицю:

```text
ib_pending_open_orders
```

Запис містить:

```text
trade_uid;
order_plan_uid;
broker_order_uid;
broker_order_id;
account_id;
symbol;
side;
quantity;
stop_loss_order_id;
take_profit_order_id;
stop_loss;
take_profit;
client_id;
comment;
execution_status;
last_error;
recovery_attempts;
is_active;
created_utc;
updated_utc;
resolved_utc.
```

Після появи broker evidence RuntimeEngine:

```text
не створює новий broker order;
знаходить exact parent execution;
відновлює Trade;
відновлює OrderPlan;
відновлює BrokerOrder;
створює Position;
створює IB virtual leg;
підключає SL/TP mappings;
закриває pending record.
```

---

## 51.17. Безпека відновлення ручного Open

Підтверджено:

```text
timeout_open_auto_recovered=True
timeout_open_pending_saved=True
duplicate_open_calls=0
timeout_open_restart_recovered=True
legacy_orphan_open_adopted=True
ambiguous_legacy_open_blocked=True
```

Legacy orphan Open дозволено прийняти лише тоді, коли існує одна унікальна exact execution identity.

Якщо підходять кілька executions:

```text
automatic adoption заборонена;
operation → BLOCKED.
```

---

## 51.18. Тест ідентичності IB MARKET під час тайм-ауту

Окремо перевірено збереження submitted order ID при timeout.

Результат:

```text
timeout_order_id=700
duplicate_order_warning=True
filled_status_without_event_accepted=True
IB_MARKET_ORDER_TIMEOUT_IDENTITY_CHECK=OK
```

LGE не змінює identity order після timeout і не генерує новий ID для повторної спроби тієї самої операції.

---

## 51.19. Стани звірки

Модель reconciliation підтримує:

RECONCILED
UNRECONCILED
BLOCKED

У робочий OrdersPage підтверджено відображення RECONCILED і BLOCKED.
UNRECONCILED є проміжним Runtime-станом і не дозволяє виконувати
virtual-leg operations.

Virtual-leg operations дозволені лише коли:

```text
group = RECONCILED;
leg = RECONCILED;
ownership = exact;
evidence = complete.
```

BLOCKED використовується при:

```text
quantity mismatch;
unmapped protection;
missing execution evidence;
ambiguous ownership;
unexpected CASH FX offset;
foreign-client order;
unknown same-contract execution.
```

У status area показується warning:

```text
IB reconciliation warning: ...
```

Long warning не розтягує головне вікно по ширині.

---

## 51.20. Область стану OrdersPage

Нижній status area розділено на:

```text
лівий розтягуваний runtime status;
правий компактний Σ PnL.
```

Підтверджено:

```text
orders_status_stretch=1
status_spacer_width=0
```

При звичайному Refresh:

```text
Оновлено групи позицій IB: {groups};
відкриті етапи: {legs}
```

Для cTrader:

```text
Оновлено торгові позиції: {count}
```

При відсутності позицій:

```text
groups = 0;
open legs = 0;
Σ PnL = —.
```

---

## 51.21. Адаптивна таблиця

Усі 13 колонок переведені в:

```text
QHeaderView.Interactive
```

Користувач може вручну змінювати ширину кожної колонки.

Підтверджено:

```text
ID width = 105
Time width >= 90
horizontal scrollbar = AsNeeded
stretchLastSection = True
```

Колонка `Час` більше не обрізається до непридатного значення.

Таблиця не розтягує головне вікно через довгий status/error text.

---

## 51.22. Поля введення ордера

Поле розміру торгового лота збільшене по висоті.

Підтверджено:

```text
spin_min_height=26
```

Це полегшує натискання стрілок `QDoubleSpinBox`.

Числові SL/TP поля приймають:

```text
крапку;
кому.
```

---

## 51.23. Регресійна перевірка cTrader

Перехід на hierarchical widget не змінив flat cTrader behavior.

Для cTrader:

```text
одна broker position = одна top-level row;
child rows = 0;
stable key = CTRADER:{position_id}.
```

Підтверджено:

```text
top_level_rows=1
child_rows=0
stable_key=CTRADER:900001
```

Якщо current price не надійшла з поточного cTrader знімок Runtime:

```text
показується —
```

Заборонено показувати фальшиве значення:

```text
0
```

Для cTrader reconciliation не застосовується:

```text
Reconciliation = —
```

PnL summary використовує broker-provided cTrader net profit.

---

## 51.24. Політика перекладів

Канонічне правило локалізації збережено:

```text
lang/strings.json
    =
лише lang_active
```

Фінальний `strings.json`:

```json
{
  "lang_active": {
    "code": "uk"
  }
}
```

Усі runtime keys знаходяться у:

```text
lang/strings_fallback.json
```

OrdersPage не містить hardcoded активної мови.

Технічні позначення можуть використовувати English fallback без окремого перекладу:

```text
SL
TP
IB NET
LGE LEG
MULTI
```

Порожнє поле конкретної мови для цих технічних tokens не є runtime-помилкою.

Невдалі автоматичні переклади на кшталт:

```text
Reconciliation → Примирення
Broker position → Посада брокера
Virtual FX → Віртуальні спецефекти
NET ONLY → ТІЛЬКИ В ІНТЕРНЕТІ
```

не виправляються вручну в `strings.json`.

Їх слід виправляти централізовано у fallback source/builder, щоб однакова правка застосовувалася до всіх мовних профілів.

---

## 51.25. Матриця синтетичних тестів

RoadMap91 додав і підтвердив:

```text
run_orders_page_ib_position_groups_check.py
run_orders_page_ib_virtual_leg_selection_check.py
run_orders_page_ib_virtual_leg_modify_check.py
run_orders_page_ib_virtual_leg_close_check.py
run_orders_page_position_group_selection_restore_check.py
run_orders_page_ib_position_group_status_check.py
run_ib_virtual_leg_pnl_check.py
run_orders_page_ctrader_tree_regression_check.py
run_orders_page_ib_sl_tp_modify_check.py
run_orders_page_retranslation_check.py
run_orders_page_ib_rejected_symbol_check.py
run_ib_market_order_timeout_identity_check.py
run_runtime_engine_ib_virtual_leg_close_check.py
run_runtime_engine_ib_manual_open_timeout_recovery_check.py
```

Основні результати:

```text
hierarchical IB groups                 : OK
child virtual legs                     : OK
group Modify disabled                  : OK
group Close disabled                   : OK
leg Modify enabled                     : OK
leg Close enabled                      : OK
selection restore                      : OK
closed selection clear                 : OK
calculated BUY PnL                     : OK
calculated SELL PnL                    : OK
PnL summary                            : OK
missing broker-row fallback            : OK
stale broker-row fallback              : OK
closed Virtual FX observation hidden   : OK
activation Refresh                     : OK
activation Open recovery               : OK
cTrader flat regression                : OK
current price zero suppression         : OK
retranslation                          : OK
responsive columns                     : OK
rejected symbol warning                : OK
Close timeout identity                 : OK
Close automatic recovery               : OK
Open timeout identity                  : OK
Open automatic recovery                : OK
duplicate Open prevention              : OK
duplicate Close prevention             : OK
restart recovery                       : OK
```

---

## 51.26. Обробка відхиленого символу

Перевірено помилку contract resolution:

```text
symbol=XAUUSD
IB contract details were not found for XAUUSD
```

Результат:

```text
warning показаний користувачу;
place_calls=1;
active_rows=0;
фальшива runtime position не створена.
```

---

## 51.27. Реальні багатосимвольні тести IB Paper

Real життєвий цикл перевірено не лише на EURUSD.

### EURUSD

```text
BUY 1 000
BUY 2 000
group BUY 3 000
separate SL/TP
Modify exact 1K leg
Close exact 1K leg
Close exact 2K leg
```

### GBPUSD

```text
SELL 1 000
SELL 2 000
group SELL 3 000
separate SL/TP
Close exact 2K leg
Close exact 1K leg
```

### USDZAR

```text
SELL 2 000
delayed Close confirmation
confirmed broker execution
controlled persistence recovery

SELL 3 000
SL 16.6
TP 16.2
delayed Open confirmation
automatic pending Open recovery
exact Close

BUY 2 000
SL 16.3
TP 16.5
залишено відкритим для нічного broker test
```

Для всіх трьох symbols підтверджено:

```text
exact parent identity;
exact leg volume;
correct opposite Close action;
separate SL/TP;
OCA ownership;
RECONCILED result;
відсутність duplicate MARKET orders.
```

---

## 51.28. Випадок затриманого закриття USDZAR

Під час першого USDZAR Close:

```text
IB MARKET order був фактично виконаний;
execution callback не надійшов у початковий timeout;
старий код показав generic timeout;
broker position уже змінилася.
```

Close був відновлений за exact order ID:

```text
close_order_id=159
position_uid=63eda578-2041-448b-8d0d-781a6814a5d3
side=SELL
volume=2 000
result=CLOSED
```

Після цього RoadMap91 було доповнено робочий automatic recovery для звичайного користувача.

Фінальна поведінка:

```text
generic recovery script користувачу не потрібний;
order ID зберігається автоматично;
повторний Close блокується;
Refresh/restart завершує persistence;
користувач отримує зрозумілий status.
```

---

## 51.29. Фінальна жива звірка лише для читання

Після завершення EURUSD, GBPUSD та попередніх USDZAR cycles:

```text
legs=6
open_legs=0
closed_legs=6
unmapped_protective_order_ids=[]
```

Для:

```text
EURUSD
GBPUSD
USDZAR
```

отримано exact execution reconciliation.

Перед фінальним нічним ордером усі попередні legs були:

```text
CLOSED
RECONCILED
remaining_volume=0
protection=NONE
```

---

## 51.30. Розвиток схеми v6–v7

RoadMap91 schema evolution:

```text
schema v6 -> ib_pending_open_orders
schema v7 -> persistent order comments and IB orderRef evidence
```

Поточна Runtime schema:

```text
PRAGMA user_version = 7
```

Virtual-leg tables збережені без втрати history:

```text
ib_virtual_position_legs
ib_virtual_position_leg_orders
```

Перевірено для migration v6 -> v7:

```text
legacy row counts unchanged
PRAGMA integrity_check = ok
PRAGMA foreign_key_check = empty
```

---

## 51.31. Фінальний стан SQLite

Фінальний контрольний ZIP містить checkpointed базу `data/demo.db` без активних
файлів `demo.db-wal` і `demo.db-shm`.

```text
schema_version                      = 7
integrity_check                     = ok
foreign_key_violations              = 0

trades                              = 48
order_plans                         = 67
broker_orders                       = 67
positions                           = 43
ib_virtual_position_legs            = 19
ib_virtual_position_leg_orders      = 69
ib_pending_open_orders              = 5
```

Стани віртуальних сегментів:

```text
OPEN                                = 2
CLOSED                              = 17
PARTIALLY_CLOSED                    = 0
```

Стани звірки:

```text
RECONCILED                          = 19
BLOCKED                             = 0
UNRECONCILED                        = 0
```

Стани захисту:

```text
COMPLETE                            = 2
NONE                                = 17
```

Активні зіставлення ордерів:

```text
PARENT                              = 19
STOP_LOSS                           = 2
TAKE_PROFIT                         = 2
CLOSE pending                       = 0
```

Pending manual Open:

```text
active                              = 0
resolved history                    = 5
```

Перевірки цілісності:

```text
duplicate trade_uid                 = 0
duplicate position_uid              = 0
duplicate broker_order_uid          = 0
duplicate active order roles        = 0
orphan leg-order mappings            = 0
active protection у CLOSED legs     = 0
```

## 51.32. Фінальні відкриті контрольні позиції

У фінальному checkpoint залишено дві контрольні віртуальні позиції.

### USDZAR

```text
symbol                              = USDZAR
side                                = SELL
volume                              = 1 000
position_uid                        = f78056e1-f345-460a-bcf8-a1347d183afb
trade_uid                           = b1fa75e3-9ee2-430e-b01d-7b2071bc3444
parent order                        = 177
stop-loss order                     = 178
take-profit order                   = 179
entry                               = 16.41005
SL                                  = 16.47
TP                                  = 16.35
leg_status                          = OPEN
protection_status                   = COMPLETE
reconciliation_status               = RECONCILED
```

### EURUSD

```text
symbol                              = EURUSD
side                                = BUY
volume                              = 1 000
position_uid                        = bd49b121-8783-4a2d-a8ed-0c488f1ed3ea
trade_uid                           = 533162ea-273d-42b4-8188-451cb111324d
parent order                        = 180
stop-loss order                     = 182
take-profit order                   = 181
entry                               = 1.14135
SL                                  = 1.1391
TP                                  = 1.143
leg_status                          = OPEN
protection_status                   = COMPLETE
reconciliation_status               = RECONCILED
```

Для кожної відкритої позиції підтверджено:

```text
1 active PARENT identity mapping;
1 active STOP_LOSS mapping;
1 active TAKE_PROFIT mapping;
0 pending CLOSE mappings.
```

## 51.33. Застарілий стан Position

Для IB virtual legs authoritative життєвий цикл state:

```text
ib_virtual_position_legs.leg_status
```

Поле:

```text
positions.state
```

залишається legacy runtime identity і для історичних virtual legs може мати:

```text
OPEN
```

навіть коли:

```text
ib_virtual_position_legs.leg_status = CLOSED
```

Тому для IB virtual-leg logic заборонено визначати active/closed стан лише через `positions.state`.

Канонічне джерело істини:

```text
leg_status
remaining_volume
reconciliation_status
active leg-order mappings
```

---

## 51.34. Фінальний архів і файл контрольних сум

Контрольний ZIP після завершення RoadMap91:

```text
LavrGPT05_2026_07_22_20_05_RoadMap91_FINAL_UA.zip
```

Checksum самого ZIP зберігається у зовнішньому companion manifest:

```text
LavrGPT05_2026_07_22_20_05_RoadMap91_FINAL_UA.checksums.txt
```

Checksum ZIP навмисно не вбудовується всередину самого ZIP, оскільки будь-яка
зміна документа всередині архіву змінює checksum архіву.

Фінальний ZIP не містить активних SQLite sidecar-файлів:

```text
data/demo.db-wal
data/demo.db-shm
```

Checksum вкладеного `data/demo.db`:

```text
MD5:
3a17be9d5bba1e04f0cd5e788a0dc3bc

SHA256:
1581668c2bb926890bcf341297be524b0d3de3e716f5a3f6a1d62a73b8e231b4
```

---

## 51.35. Ідентифікація режиму керування брокерським ордером

Для визначення брокерської належності та безпечного відновлення додано
канонічний префікс режиму керування:

```text
MANUAL -> [LGE:M]
SEMI   -> [LGE:S]
AUTO   -> [LGE:A]
```

Приклад коментаря, переданого брокеру:

```text
[LGE:M] LGE manual UI order
[LGE:S] Signal 17
[LGE:A] RailPattern EURUSD
```

Правила:

```text
префікс додається програмно;
повторне кодування не створює дубль;
старий формат із суфіксом розпізнається лише для сумісності;
перед відображенням користувачу технічний префікс видаляється;
SQLite source залишається канонічним MANUAL / SEMI / AUTO;
коментар брокера є додатковим доказом належності, а не єдиним джерелом істини.
```

---

## 51.36. Фільтри походження ордерів в OrdersPage

> **Уточнення RoadMap96:** назву filter `Відкритий у брокері` замінено на `Зовнішні у брокері`. Поточна канонічна семантика та explicit external rows описані в розділі 55.

OrdersPage має локальні checkbox-фільтри:

```text
Ручний
Напівавтомат
Автомат
Відкритий у брокері
```

Фільтр:

```text
не виконує брокерське оновлення;
не змінює брокерські ордери;
не змінює SQLite;
приховує або показує вже завантажені рядки;
перераховує PnL лише за видимими рядками;
приховує батьківську групу IB, якщо всі її дочірні сегменти відфільтровані;
очищає вибір, якщо вибраний рядок став невидимим.
```

Класифікація:

```text
[LGE:M] -> MANUAL
[LGE:S] -> SEMI
[LGE:A] -> AUTO
без LGE identity -> BROKER
historical persisted LGE leg без marker -> MANUAL
```

---

## 51.37. Поточна ціна cTrader

`ProtoOAReconcileRes` не містить live bid/ask для відкритої позиції cTrader.
Тому адаптер окремо підписується на spot-котирування відкритих символів:

```text
ProtoOASubscribeSpotsReq
    -> ProtoOASubscribeSpotsRes
    -> ProtoOASpotEvent
```

Кеш котирувань зберігає:

```text
symbol_id
bid
ask
timestamp
```

Для відображення ціни, за якою позиція може бути закрита:

```text
BUY position  -> current_price = bid
SELL position -> current_price = ask
```

Якщо котирування ще не надійшло, OrdersPage показує `—`, а не фальшивий `0`.
Підписка виконується один раз для символу в межах поточної сесії cTrader і
скидається під час відключення або перепідключення.

---

## 51.38. Валютно-коректний PnL

Розрахований PnL віртуального сегмента IB має валюту котирування символу:

```text
EURUSD -> USD
GBPUSD -> USD
USDZAR -> ZAR
USDJPY -> JPY
```

Тому інтерфейс показує валюту біля кожного приблизного значення:

```text
≈ 6.00 USD
≈ -7.50 ZAR
```

Різні валюти не складаються в одне число. Підсумок групується за валютою:

```text
Σ PnL: ≈ 6.00 USD; ≈ -7.50 ZAR
```

Для cTrader використовується наданий брокером PnL у валюті рахунку. Для
IB `NET_ONLY` використовується валюта брокерського PnL із кешу знімка рахунку.
Якщо валюту не доведено, система не додає вигаданий код валюти.

---

## 51.39. Виправлення перекладів

`lang/strings.json` знову містить лише:

```json
{
  "lang_active": {
    "code": "uk"
  }
}
```

Виправлені українські підписи Runtime:

```text
Manual            -> Ручний
Semi-Auto         -> Напівавтомат
Auto              -> Автомат
Opened in broker  -> Відкритий у брокері
Broker position   -> Позиція брокера
Virtual FX        -> Віртуальна FX-позиція
Reconciliation    -> Звірка
```

Нові регресійні перевірки:

```text
run_ctrader_current_price_check.py
run_orders_page_pnl_currency_check.py
run_orders_page_order_origin_filter_check.py
run_orders_page_retranslation_check.py
```

Після синтетичних і живих перевірок підсумок PnL остаточно закрито також для
IB virtual legs із різними валютами: значення показуються і підсумовуються
окремо за кожною валютою.

---

## 51.40. Ролі валютних пар у регресійних і стрес-тестах

Канонічний розподіл валютних пар для наступних етапів:

```text
EURUSD / GBPUSD -> базові regression tests і алгоритмічне налаштування
USDZAR          -> stress-test інструмент
```

USDZAR використовується для перевірки:

```text
швидких брокерських подій SL/TP;
очищення OCA;
затриманих callback-ів;
відновлення Open/Close;
PnL у різних валютах;
високої частоти зміни ціни.
```

USDZAR не замінює EURUSD/GBPUSD як основну повторювану базу регресійних тестів.

---

## 51.41. Збереження коментарів у схемі v7

Схема v7 додає три незалежні рівні ідентичності ордера:

```text
trades.comment
    чистий текст користувача без технічного префікса;

broker_orders.broker_comment
    точний текст, переданий брокеру;

ib_virtual_position_leg_orders.order_ref
    точний IB orderRef для зіставлення parent / Stop Loss / Take Profit / Close.
```

Приклад:

```text
source          = SEMI
trades.comment  = Signal 17
broker_comment  = [LGE:S] Signal 17
order_ref       = [LGE:S] Signal 17
```

`source` залишається канонічним полем режиму. Коментар не замінює `source`,
`position_uid`, `broker_order_id` або докази звірки.

---

## 51.42. Міграція схеми v6 → v7

Міграція є доповнювальною і не перебудовує попередній ланцюжок Runtime.

Додаються колонки:

```text
ALTER TABLE trades
    ADD COLUMN comment TEXT NOT NULL DEFAULT '';

ALTER TABLE broker_orders
    ADD COLUMN broker_comment TEXT NOT NULL DEFAULT '';

ALTER TABLE ib_virtual_position_leg_orders
    ADD COLUMN order_ref TEXT NOT NULL DEFAULT '';
```

Правила міграції:

```text
наявні записи зберігаються;
невідомий історичний коментар залишається порожнім;
коментар delayed Open відновлюється з ib_pending_open_orders;
відомий точний broker comment доповнює parent/Close order mapping;
активний IB Refresh може доповнити order_ref із брокерських доказів.
```

---

## 51.43. Регресійні перевірки збереження коментарів

Додано та розширено тести:

```text
run_runtime_order_comment_schema_check.py
run_runtime_order_comment_live_db_check.py
run_runtime_engine_order_identity_check.py
run_runtime_engine_ib_virtual_leg_open_persistence_check.py
```

Підтверджуються:

```text
schema_version=7;
наявні записи збережено;
Trade comment зберігається без [LGE:*];
BrokerOrder comment зберігається точно;
IB parent/SL/TP orderRef зберігаються точно;
foreign-key violations = 0.
```

---

## 51.44. Безперервність orderRef після зміни SL/TP

Після `Змінити SL/TP` нові або змінені захисні ордери IB зберігають початкову
ідентичність LGE та додають маркер операції:

```text
parent orderRef:
[LGE:M] LGE manual UI order

modified Stop Loss / Take Profit orderRef:
[LGE:M] LGE manual UI order | SLTP_MODIFY
```

RuntimeEngine отримує ідентичність із шару збереження в такому порядку:

```text
ib_virtual_position_leg_orders.PARENT.order_ref;
broker_orders.broker_comment;
trades.comment + trades.source.
```

Це одночасно зберігає:

```text
режим MANUAL / SEMI / AUTO;
чистий користувацький коментар;
точну брокерську ознаку зміни SL/TP.
```

Маркер операції ідемпотентний: повторна зміна SL/TP не додає другий
`| SLTP_MODIFY`.

---

## 51.45. Нічне виконання захисного ордера IB

Під час нічного виконання захисного ордера IB може не повернути відповідний
рядок через `reqCompletedOrders`, але зберегти точне виконання у
`reqExecutions`.

Підтверджений реальний випадок:

```text
EURUSD BUY 1 000
parent order     = 180
stop-loss order  = 182
take-profit      = 181
execution order  = 181
execution action = SELL
execution volume = 1 000
execution price  = 1.143
```

Захисне виконання приймається лише за одночасного точного збігу:

```text
persisted child order_id;
account;
symbol;
opposite action;
full virtual-leg quantity.
```

Небезпечні варіанти залишаються заблокованими:

```text
partial execution;
wrong action;
dual SL/TP child execution;
foreign account or symbol.
```

Після точного execution-only evidence Runtime виконує:

```text
leg_status          = CLOSED
remaining_volume    = 0
protection_status   = NONE
reconciliation      = RECONCILED
active SL/TP mapping = false
```

---

## 51.46. Збереження broker-triggered закриття під час Refresh

`OrdersPage` використовує production sync-шлях:

```text
OrdersPage Refresh
    -> RuntimeEngine.sync_active_broker_position_groups()
    -> one IB evidence snapshot
    -> virtual-leg reconciliation
    -> safe SQLite persistence
    -> position-group rendering from the same snapshot
```

Повністю звірений snapshot записується атомарно.

Перехідний або `BLOCKED` snapshot:

```text
повертається в OrdersPage;
відображає поточний безпечний стан;
не записується в SQLite;
не перериває все оновлення сторінки.
```

Це усуває помилку UI:

```text
Only fully reconciled IB virtual-leg groups may be persisted
```

без послаблення persistence guard.

---

## 51.47. Повторне відкриття CASH FX після захисного виконання

Після закриття старої EURUSD BUY-leg через TP було відкрито нову EURUSD
SELL-leg.

У поточному execution window одночасно залишалися:

```text
order 181 = старе TAKE_PROFIT SELL 1 000;
order 183 = новий PARENT SELL 1 000.
```

Стара cumulative-арифметика помилково отримувала:

```text
-1 000 + -1 000 = -2 000
```

при поточному Virtual FX:

```text
SELL 1 000
```

Reconciliation тепер окремо оцінює:

```text
cumulative exact LGE executions;
exact executions current OPEN exposure.
```

Executions уже закритих legs не додаються до поточної відкритої експозиції,
коли broker Virtual FX відповідає новим OPEN legs. Підтримка cumulative CASH
FX history при цьому збережена.

---

## 51.48. IB quote cache для відкритих virtual legs

Для символів із `OPEN` virtual legs додано streaming quote cache.

Правила:

```text
BUY leg  -> bid;
SELL leg -> ask;
live і delayed ticks підтримуються;
відсутня ціна -> None / «—»;
нульова вигадана ціна заборонена;
повторний Refresh не дублює subscription;
після закриття останньої leg subscription скасовується;
disconnect очищає всі quote subscriptions.
```

PnL залишається валютно-коректним:

```text
EURUSD -> USD;
USDZAR -> ZAR.
```

OrdersPage відображає окремі підсумки без математичного змішування валют:

```text
Σ PnL: ≈ ... USD; ≈ ... ZAR
```

Синтетично підтверджено:

```text
USDZAR SELL uses ask;
EURUSD BUY uses bid;
EURUSD SELL uses ask;
missing quote remains blank;
stale subscriptions are cancelled.
```

---

## 51.49. Фінальна жива регресія 23.07.2026

Під час фінальної перевірки підтверджено одночасну роботу quote cache,
багатосегментної EURUSD-групи, зміни захисту та точного Close.

### USDZAR

```text
side                  = SELL
volume                = 1 000
parent order          = 177
stop-loss order       = 178
take-profit order     = 179
SL                    = 16.47
TP                    = 16.35
protection_status     = COMPLETE
reconciliation_status = RECONCILED
current price         = IB ask quote
PnL currency          = ZAR
```

### EURUSD — закритий сегмент

```text
side                  = SELL
initial volume        = 1 000
parent order          = 183
Stop Loss             = removed
Take Profit           = replacement order 189
Close order           = 190
Close action          = BUY
Close quantity        = 1 000
Close price           = 1.14055
leg_status            = CLOSED
remaining_volume      = 0
protection_status     = NONE
reconciliation_status = RECONCILED
```

Під час зміни захисту Stop Loss було безпечно вилучено, а Take Profit
збережено. Перед exact Close залишковий TP було скасовано.

### EURUSD — відкритий сегмент

```text
side                  = SELL
volume                = 2 000
parent order          = 186
entry                 = 1.14035
stop-loss order       = 188
SL                    = 1.145
take-profit order     = 187
TP                    = 1.139
protection_status     = COMPLETE
reconciliation_status = RECONCILED
current price         = IB ask quote
PnL currency          = USD
```

Після закриття сегмента 1 000 broker position і OrdersPage узгоджено показали:

```text
EURUSD SELL 2 000
USDZAR SELL 1 000
```

Дублікати рядків, нульові котирування, persistence warning та повторне
відкриття ордера не виникли.

---

## 51.50. Фінальний SQLite checkpoint RoadMap91

Checkpoint після фінальної живої регресії:

```text
schema_version                       = 7
integrity_check                      = ok
foreign_key_violations               = 0
ib_virtual_position_legs total       = 21
ib_virtual_position_legs OPEN        = 2
ib_virtual_position_legs CLOSED      = 19
ib_virtual_position_legs RECONCILED  = 21
ib_virtual_position_legs BLOCKED     = 0
active pending Opens                 = 0
```

Відкриті канонічні virtual legs:

```text
USDZAR SELL 1 000
parent = 177
SL order = 178
TP order = 179
protection = COMPLETE
reconciliation = RECONCILED

EURUSD SELL 2 000
parent = 186
SL order = 188
TP order = 187
protection = COMPLETE
reconciliation = RECONCILED
```

Останній exact Close:

```text
EURUSD SELL 1 000
parent = 183
close order = 190
leg_status = CLOSED
protection = NONE
reconciliation = RECONCILED
```

Для IB virtual legs канонічним станом залишається:

```text
ib_virtual_position_legs.leg_status
remaining_volume
reconciliation_status
ib_virtual_position_leg_orders.is_active
```

`positions.state` є legacy runtime identity і не використовується як єдине
джерело active/closed стану virtual leg.

Цей checkpoint замінює попередні фінальні значення у розділах
51.31, 51.34 і старій редакції 51.45.

---

## 51.51. Підсумок RoadMap91 станом на 23.07.2026

Основний функціональний блок RoadMap91 завершено станом на 23.07.2026.
Фінальні уточнення, підтверджені 24.07.2026, зафіксовано у розділі 52.

Додатково до попереднього функціоналу підтверджено:

```text
overnight protective-fill recovery             : DONE
execution-only exact child evidence             : DONE
Refresh persistence of broker-triggered Close   : DONE
safe BLOCKED snapshot display without write     : DONE
CASH FX reopen after closed protective leg      : DONE
current OPEN exposure reconciliation            : DONE
IB virtual-leg quote cache                      : DONE
live/delayed bid/ask support                     : DONE
side-aware BUY bid / SELL ask                    : DONE
subscription reuse and cleanup                  : DONE
mixed USD/ZAR PnL summary                       : DONE
live Open 2 000 + Modify + exact Close           : DONE
final database integrity                        : OK
```

Фінальний архів:

```text
LavrGPT05_2026_07_23_14_25_RoadMap91_FINAL.zip
```

Архів не містить:

```text
data/demo.db-wal
data/demo.db-shm
Word temporary lock files ~$*.docx
```

`LGE_Runtime_05.md` залишається канонічним Runtime-підсумком до RoadMap91.

Наступний етап ведеться окремо:

```text
LGE_Runtime_06.md
    =
RoadMap92
+
Algorithm Workspace / WSP
+
Replay / historical mode
+
Manual / Semi-Auto / Auto per WSP
+
algorithm Start / Stop
+
session persistence
```

---

# 52. Фінальні уточнення RoadMap91 від 24.07.2026

## 52.1. Причина додаткового циклу перевірок

Після основного завершення RoadMap91 живі IB Paper тести виявили два стани,
які не можна безпечно зводити до звичайного `RECONCILED` або загального
`BLOCKED`:

```text
1. broker net містить експозицію поза точними OPEN virtual legs LGE;
2. persisted virtual leg виглядає закритою у broker net, але точного evidence
   виконання Close, SL або TP в доступній історії IB немає.
```

Обидва випадки тепер мають окрему канонічну модель і не руйнують точні
операції з іншими virtual legs тієї самої групи.

---

## 52.2. Broker residual у змішаній IB-групі

Для CASH Forex поточна broker net position може відрізнятися від підписаної
суми точних `OPEN` virtual legs LGE. Причинами можуть бути:

1. зовнішня ручна операція у TWS;
2. broker execution поза поточним історичним вікном;
3. позиція, яка не має exact LGE identity;
4. перезапуск після втрати частини доступної execution history.

Канонічне представлення:

```text
IB group row
    = поточний broker net

LGE LEG child rows
    = exact managed virtual legs

Broker residual child row
    = broker net - signed sum(exact OPEN LGE legs)
```

Приклад:

```text
broker net              = BUY 2 000
exact managed LGE leg   = SELL 1 000
broker residual         = BUY 3 000
```

Це не математична помилка. Підписана сума:

```text
SELL 1 000 + BUY 3 000 = BUY 2 000
```

Broker residual:

1. має окрему стабільну identity;
2. зберігається через restart;
3. не залежить від повторної наявності старого external execution у поточній
   IB history;
4. відображається як read-only child row;
5. не може бути змінений або закритий як exact virtual leg;
6. не підміняє та не поглинає exact LGE legs.

Групове попередження про residual не блокує точний `Modify SL/TP` або exact
`Close` для окремої повністю узгодженої LGE leg.

---

## 52.3. `CLOSE_EVIDENCE_MISSING`

Окремий reconciliation state використовується, коли одночасно виконується:

```text
persisted virtual leg має status OPEN;
broker net більше не підтверджує цю leg;
persisted SL/TP orders не активні;
matching exact close execution не знайдено;
matching exact protective execution не знайдено.
```

Канонічний status:

```text
CLOSE_EVIDENCE_MISSING
```

Runtime не має права виводити `CLOSED` лише з факту зникнення broker position
або захисних ордерів. Без exact evidence це створило б приховану втрату
історії та могло б дозволити небезпечну повторну операцію.

Для такої leg:

```text
leg_status              = OPEN у persistence до exact evidence;
reconciliation_status   = CLOSE_EVIDENCE_MISSING;
Modify SL/TP             = disabled;
exact Close              = disabled;
автоматичне припущення   = заборонено.
```

Після появи точного broker evidence Runtime може безпечно завершити
reconciliation і записати канонічний `CLOSED` state.

---

## 52.4. Межі операцій у змішаній групі

Після фінального виправлення груповий warning і операційний стан конкретної
leg розділено.

Канонічне правило:

```text
group warning
    !=
automatic ban for every child leg
```

Точний `Modify SL/TP` або exact `Close` дозволено лише для child row, яка має:

```text
exact position_uid;
exact trade_uid;
exact parent order identity;
leg_status = OPEN;
reconciliation_status = RECONCILED;
безпечний protection state для відповідної операції.
```

Операції заборонені для:

```text
broker residual row;
NET_ONLY row як virtual leg;
CLOSE_EVIDENCE_MISSING leg;
BLOCKED leg;
foreign або ambiguous identity.
```

Синтетично підтверджено:

```text
mixed_group_exact_leg_modify = True
mixed_group_exact_leg_close  = True
group_warning_does_not_block_exact_leg = True
```

---

## 52.5. Канонічний переклад reconciliation і tooltip

OrdersPage не перекладає Runtime-стани hardcoded умовами української мови.
Використовується загальна схема LGE:

```text
LangManager.tr(...)
    ↓
lang/strings.json
    ↓
переклад відсутніх мовних значень
    ↓
dev_tools/rebuild_fallback.py
    ↓
lang/strings_fallback.json
    ↓
Qt resource
    ↓
runtime retranslation
```

Підтверджені видимі українські значення:

```text
RECONCILED             -> Узгоджено
UNRECONCILED           -> Неузгоджено
BLOCKED                -> Заблоковано
CLOSE_EVIDENCE_MISSING -> Відсутнє підтвердження закриття
```

Через `tr` також локалізуються:

1. lifecycle status virtual leg;
2. protection status;
3. parent execution outside current IB history;
4. відсутність parent execution;
5. відсутність exact close evidence;
6. unmapped protective order;
7. broker net без virtual legs LGE;
8. broker residual;
9. Virtual FX offset і quantity mismatch;
10. пояснення group row, exact legs і residual child row;
11. причина блокування `Modify SL/TP` та `Close`;
12. warning у нижньому status field OrdersPage.

Raw reconciliation messages зберігаються у data roles рядка, а tooltip
формується повторно для поточної мови. Тому перемикання мови не потребує
нового broker refresh і не втрачає технічний зміст повідомлення.

Технічні identity-поля tooltip:

```text
position_uid;
trade_uid;
leg_status;
protection_status.
```

залишаються доступними для діагностики, але їхні підписи та статусні значення
локалізуються.

---

## 52.6. Відновлення Statusbar після зміни selection

Для disabled leg OrdersPage показує точну причину:

```text
Вибрану віртуальну позицію не можна змінити або закрити: {status}
```

Раніше після переходу на інший рядок цей локальний warning міг залишатися у
status field і маскувати актуальний стан snapshot.

Тепер selection transition працює так:

```text
select disabled leg
    -> показати причину блокування конкретної leg

select another row
    -> відновити актуальний status поточного IB snapshot
```

Підтверджено:

```text
selection_status_restored = True
```

Statusbar, reconciliation column і tooltip використовують однакові
локалізовані status values.

---

## 52.7. Фінальна матриця перевірок 24.07.2026

Підтверджені тести:

```text
run_ib_broker_residual_and_missing_close_evidence_check.py
run_runtime_engine_ib_broker_residual_persistence_check.py
run_orders_page_ib_broker_residual_check.py
run_runtime_engine_ib_virtual_leg_modify_check.py
run_runtime_engine_ib_virtual_leg_close_check.py
run_runtime_engine_ib_virtual_legs_check.py
run_ib_virtual_leg_group_snapshot_check.py
run_orders_page_ib_reconciliation_translation_check.py
run_orders_page_retranslation_check.py
run_ib_forex_quote_cache_check.py
run_runtime_engine_ib_virtual_leg_quote_enrichment_check.py
run_orders_page_ib_virtual_leg_quote_check.py
```

Підтверджені production-властивості:

```text
broker residual calculation                    : DONE
broker residual restart persistence             : DONE
read-only residual row                          : DONE
missing close evidence fail-closed state        : DONE
mixed group exact-leg Modify                    : DONE
mixed group exact-leg Close                     : DONE
quote cache and side-aware PnL                   : DONE
localized reconciliation values                 : DONE
localized reconciliation tooltips               : DONE
localized protection and lifecycle statuses     : DONE
localized OrdersPage warning                    : DONE
selection status restoration                    : DONE
cTrader flat-row regression                     : PRESERVED
```

---

## 52.8. Остаточний канон RoadMap91

Після фінальних перевірок RoadMap91 вважається завершеним.

Канонічна модель IB OrdersPage:

```text
broker group row
    = current broker net observation

exact LGE LEG rows
    = managed logical virtual positions

broker residual row
    = read-only exposure outside exact LGE legs

NET_ONLY row
    = broker position without LGE virtual-leg model
```

Канонічні safety rules:

```text
exact identity before operation;
no close inference without exact evidence;
no residual operation as virtual leg;
group warning does not erase safe exact-leg operations;
BLOCKED and CLOSE_EVIDENCE_MISSING fail closed;
all user-facing reconciliation text passes through tr;
Runtime technical state remains language-independent.
```

`LGE_Runtime_05_FINAL.md` завершує Runtime-документацію RoadMap91.

Фінальний narrow archive цього уточнення:

```text
2026_07_24_21_01_RoadMap91_LGE_Runtime_05_FINAL.zip
```

Нові WSP, Replay та algorithm-runtime роботи документуються в:

```text
LGE_Runtime_06.md
```

---

# 53. RoadMap91A — IB NET visibility recovery та фінальний live regression

Дата перевірки: 28.07.2026  
Статус: завершено і підтверджено на IB Paper / TWS

RoadMap91A є вузьким продовженням RoadMap91 після виявлення production-випадку,
коли реальна ненульова IB Forex позиція зникала з OrdersPage через наявність
лише історичних закритих LGE virtual legs.

---

## 53.1. Виявлена помилка

Початковий live snapshot для `EURUSD` містив:

```text
broker_present=True
broker_side=BUY
broker_volume=1 000
open_legs=0
closed_legs=1
mode=LGE_VIRTUAL_LEGS
status=RECONCILED
```

У TWS реальна позиція `EUR.USD BUY 1K` залишалася відкритою, але OrdersPage
повністю приховував групу, оскільки історична `CLOSED` leg помилково впливала
на класифікацію активної групи.

Правильний production-інваріант:

```text
historical CLOSED LGE leg
+ broker_present=True
+ abs(broker_volume) > 0
+ open_legs=0
-> active group remains visible as NET_ONLY
```

Історичні закриті legs не мають права робити поточну ненульову брокерську
позицію невидимою.

---

## 53.2. Виправлена класифікація

В `engine/ib_position_group.py` active mode тепер визначається за відкритими
legs, а не за всіма історичними legs.

Канонічний результат для broker-only exposure:

```text
mode=NET_ONLY
broker_present=True
broker_side=BUY або SELL
broker_volume>0
legs=[]
status=UNRECONCILED
message=Broker net position has no LGE virtual legs
```

У `core/orders_page.py` доданий display guard: ненульова брокерська позиція не
приховується навіть тоді, коли upstream snapshot помилково нагадує закриту
Virtual FX observation.

Відображення в OrdersPage:

```text
DUM513747 | EURUSD | Лише NET | BUY | 1 000 | Неузгоджено | BROKER
```

`Неузгоджено` в цьому випадку не є runtime-помилкою. Це точний стан: у брокера
є exposure, але немає відповідної відкритої LGE LEG.

---

## 53.3. Regression-перевірки

Підтверджені тести:

```text
run_ib_closed_leg_broker_net_visibility_check.py
    active_group_mode=NET_ONLY
    active_group_legs=0
    broker_net=BUY 1000
    IB_CLOSED_LEG_BROKER_NET_VISIBILITY_CHECK=OK

run_orders_page_ib_position_groups_check.py
    closed_virtual_fx_with_broker_position_visible=True
    ORDERS_PAGE_IB_POSITION_GROUPS_CHECK=OK

run_ib_position_groups_live_readonly_check.py
    EURUSD mode=NET_ONLY
    broker_present=True
    broker_side=BUY
    broker_volume=1 000
    open_legs=0
    closed_legs=0
    net_only_groups=1
    sqlite_read_only=True
    IB_POSITION_GROUPS_LIVE_READONLY_CHECK=OK
```

---

## 53.4. Live close broker NET position

Видимий `EURUSD NET_ONLY BUY 1 000` був закритий через LGE одним MARKET
контрордером:

```text
EURUSD SELL MARKET 1 000
```

TWS підтвердив виконання приблизно за ціною `1.13700`.

Фінальний стан:

```text
EUR.USD POS = 0
USD.ZAR POS = 0
OrdersPage IB groups = 0
open legs = 0
CLOSE_EVIDENCE_MISSING = absent
```

Цим підтверджено, що broker-only `NET_ONLY` позиція не лише видима, а й може
бути безпечно закрита через канонічний LGE runtime chain.

---

## 53.5. Live regression на двох незалежних валютних парах

Після очищення broker exposure через LGE були відкриті дві нові незалежні
позиції.

### EURUSD

```text
side=BUY
volume=1 000
entry_price=1.13735
source=MANUAL
mode=LGE_VIRTUAL_LEGS
open_legs=1
status=RECONCILED
```

OrdersPage показав:

```text
EURUSD | Virtual FX | BUY | 1 000 | Узгоджено
    LGE LEG | BUY | 1 000 | Узгоджено
```

TWS підтвердив `EUR.USD POS = 1K`.

### GBPUSD

```text
side=SELL
volume=1 000
entry_price=1.33015
source=MANUAL
mode=LGE_VIRTUAL_LEGS
open_legs=1
status=RECONCILED
```

OrdersPage показав:

```text
GBPUSD | Virtual FX | SELL | 1 000 | Узгоджено
    LGE LEG | SELL | 1 000 | Узгоджено
```

TWS підтвердив `GBP.USD POS = -1K`.

Підсумок OrdersPage:

```text
IB groups=2
open legs=2
EURUSD and GBPUSD are independent
```

---

## 53.6. Live SL/TP modify для двох позицій

SL/TP були встановлені через LGE для конкретних дочірніх `LGE LEG`.

### EURUSD BUY 1 000

```text
SL=1.1355
TP=1.1420
```

IB створив захисні SELL-ордери:

```text
SELL STP 1K
SELL LMT 1K
```

### GBPUSD SELL 1 000

```text
SL=1.3370
TP=1.1328
```

IB створив захисні BUY-ордери:

```text
BUY STP 1K
BUY LMT 1K
```

Після refresh OrdersPage показав однакові SL/TP на group row і відповідній
child leg. Обидві групи залишилися `Узгоджено`.

Цим підтверджено повний production chain:

```text
OrdersPage selection
    -> RuntimeEngine
    -> IB Runtime Service
    -> SessionManager
    -> IB Adapter
    -> TWS protective orders
    -> broker snapshot refresh
    -> exact LGE LEG reconciliation
```

---

## 53.7. Остаточний канон RoadMap91A

RoadMap91A закриває останній production edge case RoadMap91:

```text
historical closed legs do not define active group mode;
non-zero broker exposure is never hidden;
broker-only exposure is represented as NET_ONLY;
NET_ONLY remains explicitly UNRECONCILED until mapped or closed;
NET_ONLY close uses exact broker side and quantity;
new LGE positions create exact virtual legs;
SL/TP modify remains exact-leg scoped;
multiple currency pairs remain independent;
all live refreshes preserve broker truth.
```

Фінальний live regression підтвердив:

```text
NET_ONLY visibility                  : DONE
NET_ONLY live close                  : DONE
EURUSD exact LGE LEG open            : DONE
GBPUSD exact LGE LEG open            : DONE
independent multi-pair grouping      : DONE
EURUSD SL/TP live placement          : DONE
GBPUSD SL/TP live placement          : DONE
OrdersPage reconciliation            : DONE
TWS broker confirmation              : DONE
CLOSE_EVIDENCE_MISSING regression    : PASSED
```

Основний блок `NET_ONLY` завершено. Наступні підрозділи фіксують додатковий
production recovery, який був виявлений під час наступного торгового дня.

---

## 53.8. Наступний торговий день: відсутня CASH observation

Після зміни торгового дня IB перестав повертати поточні CASH position rows для
частини Virtual FX станів. Це створило два різні випадки, які не можна
обробляти однаково.

### GBPUSD — захищена persisted leg

```text
symbol=GBPUSD
broker_present=False
open_legs=1
leg=SELL 1 000
protection=COMPLETE
reconciliation=RECONCILED
leg_operations=True
```

Активні `BUY STP` і `BUY LMT` у TWS точно відповідали persisted GBPUSD leg.
Відсутність CASH row не означала, що leg закрита, тому захист не скасовувався і
група залишилася керованою.

### EURUSD — відсутнє підтвердження закриття

```text
symbol=EURUSD
broker_present=False
broker_volume=0
open_legs=1
leg=SELL 1 000
active_protection=NONE
close_execution=not found
reconciliation=CLOSE_EVIDENCE_MISSING
leg_operations=False
```

Автоматично оголошувати таку leg закритою заборонено: відсутність CASH row і
відсутність доступної історії виконань не є достатнім доказом. Звичайні `Close`
та `Modify SL/TP` залишаються заблокованими.

Окремий display fix зберігає persisted атрибути групи навіть без поточної CASH
observation:

```text
EURUSD | Virtual FX | SELL | 1 000 | Відсутнє підтвердження закриття
    EURUSD | LGE LEG | SELL | 1 000 | Відсутнє підтвердження закриття
```

Regression:

```text
run_ib_cash_fx_missing_observation_display_check.py
    protected_group=GBPUSD SELL 1000 RECONCILED
    protected_leg_operations=True
    unresolved_group=EURUSD SELL 1000 CLOSE_EVIDENCE_MISSING
    unresolved_broker_kind=VIRTUAL_FX
    unresolved_leg_operations=False
    IB_CASH_FX_MISSING_OBSERVATION_DISPLAY_CHECK=OK
```

---

## 53.9. CLOSE_EVIDENCE_MISSING Manual Recovery UI

У `OrdersPage` додана окрема дія `Вирішення питань узгодження`. Вона доступна
тільки для конкретної дочірньої `LGE LEG` зі статусом
`CLOSE_EVIDENCE_MISSING`. Для group row кнопка вимкнена.

Канонічний шлях:

```text
OrdersPage
    -> RuntimeEngine.resolve_ib_close_evidence_missing()
    -> fresh complete IB evidence snapshot
    -> repository transaction
    -> runtime audit event
    -> position-group refresh
```

Перед зміною БД RuntimeEngine повторно перевіряє:

```text
position_uid still exists
leg_status=OPEN
remaining_volume>0
reconciliation_status=CLOSE_EVIDENCE_MISSING
broker exposure=0
active SL/TP/close orders=absent
IB evidence snapshot=complete
```

Будь-яка зміна цих фактів блокує recovery і вимагає нового refresh.

Після двох явних підтверджень виконується тільки локальна звірка:

```text
position.state=CLOSED
leg.status=CLOSED
remaining_volume=0
protection_status=NONE
reconciliation_status=RECONCILED_MANUAL
active order mappings=MANUAL_RECOVERY_CLOSED
broker_operation_attempted=false
```

Audit event:

```text
IB_MANUAL_RECONCILIATION_RESOLVED
```

Жоден `placeOrder`, `cancelOrder`, broker close або modify не викликається.

Підтверджений RuntimeEngine synthetic test:

```text
run_runtime_engine_ib_close_evidence_manual_recovery_check.py
    first_attempt_with_broker_exposure_blocked=True
    broker_operation_attempted=False
    position_state=CLOSED
    leg_status=CLOSED
    remaining_volume=0
    protection_status=NONE
    reconciliation_status=RECONCILED_MANUAL
    persisted_orders_deactivated=3
    runtime_audit_event=True
    duplicate_resolution_blocked=True
    active_groups_after_resolution=0
    RUNTIME_ENGINE_IB_CLOSE_EVIDENCE_MANUAL_RECOVERY_CHECK=OK
```

OrdersPage regression розширений перевіркою локалізованих кнопок. Очікуваний
вихід після запуску в PySide6-середовищі:

```text
run_orders_page_ib_close_evidence_manual_recovery_check.py
    recovery_button_group_enabled=False
    recovery_button_leg_enabled=True
    modify_close_blocked=True
    localized_buttons=Так/Ні
    confirmations=2
    runtime_resolve_calls=1
    broker_close_calls=0
    broker_modify_calls=0
    active_groups_after_resolution=0
    ORDERS_PAGE_IB_CLOSE_EVIDENCE_MANUAL_RECOVERY_CHECK=OK
```

Кнопки підтвердження локалізуються через LGE i18n як `Так / Ні`, а не
залишаються системними `Yes / No`.

---

## 53.10. Реальний IB recovery test

Live test був виконаний для EURUSD leg
`78ab6bfb-84a5-40bd-95a0-f3639312f1fc`.

До recovery:

```text
GBPUSD SELL 1 000 = RECONCILED, protection COMPLETE
EURUSD SELL 1 000 = CLOSE_EVIDENCE_MISSING
TWS EURUSD position = absent
TWS EURUSD active orders = absent
TWS GBPUSD BUY STP/LMT = active
```

Обидва діалоги були підтверджені. Другий діалог явно повідомив, що дія не
закриває позицію у брокера і не надсилає ордер до IB.

Після recovery:

```text
EURUSD removed from active OrdersPage groups
EURUSD warning removed
GBPUSD remained RECONCILED
GBPUSD protective orders remained active
IB groups=1
open legs=1
No new EURUSD broker order
No GBPUSD cancel or modify
```

Status line LGE:

```text
Ручна звірка з IB завершена. Жодного брокерського ордера не було надіслано.
```

Після окремого refresh і повного перезапуску LGE EURUSD не відновився як
відкрита leg. Отже, `RECONCILED_MANUAL` і `CLOSED` збережені у runtime DB.

---

## 53.11. Post-recovery multi-leg regression

Після recovery через загальну OrdersPage були створені ще дві ручні IB legs з
SL/TP.

### Нова GBPUSD BUY leg

```text
side=BUY
volume=1 000
entry≈1.33025
SL=1.3269
TP=1.3320
source=MANUAL
reconciliation=RECONCILED
```

Разом із раніше відкритою GBPUSD `SELL 1 000` група містить дві протилежні
legs. Тому aggregate row коректно показує:

```text
side=UNKNOWN
volume=0
SL=MULTI
TP=MULTI
open legs=2
```

Обидві дочірні legs залишаються видимими окремо зі своїми SL/TP.

### Нова EURUSD BUY leg

```text
side=BUY
volume=1 000
entry≈1.13970
SL=1.1359
TP=1.1412
source=MANUAL
reconciliation=RECONCILED
```

Підсумок OrdersPage:

```text
IB groups=2
open legs=3
GBPUSD legs=SELL 1 000 + BUY 1 000
EURUSD legs=BUY 1 000
all visible legs=RECONCILED
```

TWS підтвердив нові MARKET-виконання і окремі захисні STP/LMT для нових legs.

Алгоритмічні WSP після цього показали `Orders: 0 / Positions: 0`. Це правильно:
ручні ордери були створені загальною OrdersPage без `workspace_uid`, тому жодна
WSP не має права привласнювати їх собі.

---

## 53.12. Канонічні runtime paths і чистота тестів

Виявлена залежність старих модулів від process current working directory:

```text
Path("lang/strings.json")
Path("lang")
RuntimeEngine(db_path="data/demo.db")
```

Через різні PyCharm Run Configuration це створювало помилкові каталоги:

```text
tests/runtime/lang
tests/runtime/data
```

Шляхи переведені на канонічні `core.app_paths` і
`get_runtime_database_path()`. Regression:

```text
run_runtime_path_anchor_check.py
    project_root=D:\LavrGPT\LavrGPT05
    lang_dir=D:\LavrGPT\LavrGPT05\lang
    demo_db=D:\LavrGPT\LavrGPT05\data\demo.db
    relative_lang_paths=0
    relative_runtime_db_paths=0
    cwd_artifacts_created=False
    RUNTIME_PATH_ANCHOR_CHECK=OK
```

Помилкові `tests/runtime/lang` і `tests/runtime/data` можна видаляти; канонічні
root-level `lang` і `data` залишаються єдиними runtime каталогами.

Test doubles також очищені від неправильних protocol casts. Підтверджено:

```text
RUNTIME_ENGINE_ORDER_IDENTITY_CHECK=OK
RUNTIME_ENGINE_CTRADER_SERVICE_CHECK=OK
```

---

## 53.13. Фінальний статус RoadMap91A

```text
NET_ONLY visibility                              : DONE
NET_ONLY live close                              : DONE
missing CASH observation display                 : DONE
CLOSE_EVIDENCE_MISSING safety block              : DONE
manual recovery RuntimeEngine                    : DONE
manual recovery OrdersPage UI                    : DONE
manual recovery live IB confirmation             : DONE
no-broker-operation guarantee                    : CONFIRMED
manual recovery persistence after restart        : CONFIRMED
localized confirmation buttons Так/Ні            : IMPLEMENTED
post-recovery multi-leg regression               : PASSED
workspace ownership isolation                    : PASSED
canonical runtime paths                          : DONE
RoadMap91A                                       : CLOSED
```

Подальша WSP Runtime робота ведеться у `LGE_Runtime_06.md`.

---
# 54. RoadMap94 — стабілізація IB virtual legs, OCA-захисту та керованого завершення LGE

RoadMap94 продовжив production-hardening Runtime після RoadMap91A. Основні
завдання цього блоку:

1. не відновлювати закриту LGE virtual leg лише через неоднозначний рядок
   `IB CASH Forex Virtual FX`;
2. не втрачати підтверджений post-modify snapshot через повторний застарілий
   broker refresh;
3. дозволити безпечне створення відсутнього одиночного SL або TP;
4. безпечно замінювати orphaned OCA survivor на нову повну захисну пару;
5. забезпечити єдиний controlled shutdown для меню, кнопки, системного tray і
   системного закриття головного вікна;
6. поліпшити OrdersPage selection lifecycle;
7. підтвердити зміни реальними IB Paper перевірками на EURUSD і GBPUSD.

---

## 54.1. Virtual FX observation не є доказом відкритої LGE leg

IB `CASH Forex` може повертати Virtual FX observation, яка не є самостійним
доказом нового MARKET-виконання LGE.

Критичний сценарій:

```text
LGE leg має точний close evidence
position_state=CLOSED
leg_status=CLOSED
current LGE exposure=0
IB Virtual FX observation=BUY 1 000
```

Заборонено:

```text
закриту LGE leg знову робити OPEN
```

Канонічна поведінка:

```text
історична leg залишається CLOSED
активна broker observation показується окремо
active group mode=NET_ONLY
active group status=BLOCKED
active group legs=0
leg operations=false
```

Тобто LGE не приховує брокерську експозицію, але й не приписує її старій
закритій virtual leg без точної order/execution identity.

Підтверджені regression tests:

```text
run_ib_closed_leg_virtual_fx_observation_block_check.py
    closed_lge_legs=1
    exact_close_evidence=True
    current_exposure_executions=0
    virtual_fx_observation=BUY 1000
    active_group_mode=NET_ONLY
    active_group_status=BLOCKED
    active_group_legs=0
    leg_operations=False
    IB_CLOSED_LEG_VIRTUAL_FX_OBSERVATION_BLOCK_CHECK=OK

run_orders_page_ib_closed_leg_virtual_fx_block_check.py
    group_visible=True
    group_type=NET_ONLY
    reconciliation=BLOCKED
    modify_enabled=False
    close_enabled=False
    recovery_enabled=False
    broker_operation_attempted=False
    ORDERS_PAGE_IB_CLOSED_LEG_VIRTUAL_FX_BLOCK_CHECK=OK

run_ib_closed_leg_broker_net_visibility_check.py
    historical_closed_legs=1
    broker_present=True
    broker_net=BUY 1000
    active_group_mode=NET_ONLY
    active_group_legs=0
    broker_residual=False
    historical_only_group_mode=LGE_VIRTUAL_LEGS
    IB_CLOSED_LEG_BROKER_NET_VISIBILITY_CHECK=OK
```

---

## 54.2. Manual recovery не застосовується до реальної broker exposure

Manual close-evidence recovery дозволений лише коли одночасно підтверджено:

```text
broker position absent
active protective orders absent
selected LGE leg=CLOSE_EVIDENCE_MISSING
```

Якщо IB показує non-zero Virtual FX або іншу broker exposure, recovery-кнопка
не повинна перетворювати її на закриту локальну leg.

Для `NET_ONLY / BLOCKED`:

```text
Modify disabled
Close disabled
Manual recovery disabled
broker operation not attempted
```

Це консервативна production-політика. Неоднозначність вирішується через точні
execution/order facts або окрему брокерську дію користувача, а не автоматичним
припущенням LGE.

---

## 54.3. Повторне використання підтвердженого post-modify snapshot

Після успішної зміни SL/TP IB може короткий час повертати застарілий open-order
snapshot. Раніше негайний повторний refresh міг перекрити вже підтверджений
результат і створити хибний `BLOCKED` або пропуск persistence.

Канонічний ланцюжок після RoadMap94:

```text
Modify virtual leg
    ↓
отримати broker confirmation
    ↓
повторити reconciliation при stale snapshot
    ↓
отримати confirmed post-modify group snapshot
    ↓
повторно використати саме цей snapshot у RuntimeEngine / OrdersPage
    ↓
зберегти підтверджений стан у SQLite
```

Підтверджено:

```text
post_modify_reconciliation_attempts=2
stale_post_modify_snapshot_retried=True
confirmed_group_snapshot_reused=True
persistence_legs_written=1
```

Regression tests:

```text
RUNTIME_ENGINE_IB_VIRTUAL_LEG_MODIFY_CHECK=OK
ORDERS_PAGE_IB_VIRTUAL_LEG_MODIFY_CHECK=OK
```

OrdersPage не виконує зайвий незалежний refresh, який міг би втратити
підтверджений snapshot.

---

## 54.4. Створення одиночного захисту для virtual leg

Для відкритої IB virtual leg без child orders дозволено створити один
відсутній захисний ордер:

```text
no children + new SL -> CREATE STOP_LOSS
no children + new TP -> CREATE TAKE_PROFIT
```

У цьому вузькому випадку guard `has no child order IDs` не блокує операцію,
оскільки створення першого захисту не модифікує невідому існуючу OCA-пару.

При цьому guard залишається обов'язковим, якщо child pair уже існує або broker
metadata неоднозначні.

Підтверджено:

```text
run_ib_virtual_leg_single_protection_create_check.py
    no_children_add_stop_loss=CREATE
    no_children_add_take_profit=CREATE
    no_children_guard_bypassed=True
    existing_child_pair_guard_preserved=True
    orphaned_oca_survivor_replaced=True
    active_unmapped_oca_peer_blocked=True
    IB_VIRTUAL_LEG_SINGLE_PROTECTION_CREATE_CHECK=OK
```

---

## 54.5. Orphaned OCA survivor і replacement pair

Проблемний сценарій:

```text
virtual leg має тільки один активний захисний ордер
цей ордер має OCA metadata
другий OCA peer відсутній або вже неактивний
користувач додає відсутній SL або TP
```

Заборонено просто залишити старий survivor і створити до нього новий ордер з
іншою OCA identity. Це руйнує atomic protection.

Канонічний replacement flow:

```text
1. Побудувати новий survivor replacement.
2. Побудувати новий missing peer.
3. Обом призначити одну нову OCA group.
4. Stage обидва orders локально з transmit=False.
5. Підтвердити, що обидва staged orders прийняті локально.
6. Лише після цього скасувати старий orphan survivor.
7. Активувати нову пару з transmit=True.
8. Виконати post-modify reconciliation і persistence.
```

Очікуваний порядок broker calls:

```text
placeOrder(new survivor, transmit=False)
placeOrder(new peer, transmit=False)
cancelOrder(old survivor)
placeOrder(new survivor, transmit=True)
placeOrder(new peer, transmit=True)
```

Якщо local stage не підтверджено, old survivor не скасовується:

```text
replacement pair aborted before old survivor cancellation
```

Local staged `transmit=False` rows не можна вручну передавати кнопкою
`Transmit` у TWS. Їх треба скасувати як локальні залишки невдалої staging
операції або перезапустити TWS, після чого повторити керовану операцію з LGE.

Якщо виявлено активний unmapped OCA peer, автоматична replacement-операція
блокується.

Підтверджено:

```text
run_ib_sl_tp_replacement_pair_check.py
    KEEP SL + CREATE TP replacement pair plan=OK
    KEEP TP + CREATE SL replacement pair plan=OK
    staged_transmit=[False, False]
    active_transmit=[True, True]
    confirmed=True
    stage safety guard=OK
    IB_SL_TP_REPLACEMENT_PAIR_CHECK=OK

run_ib_virtual_leg_oca_execution_guard_check.py
    stable_guard_confirmed=True
    unrelated_symbol_ignored=True
    protective_execution_blocked=True
    unknown_execution_blocked=True
    survivor_guard_calls=1
    pair_guard_calls=1
    broker_net_position_guard_bypassed=True
    IB_VIRTUAL_LEG_OCA_EXECUTION_GUARD_CHECK=OK
```

---

## 54.6. Controlled shutdown RuntimeEngine

`RuntimeEngine.shutdown()` є idempotent і виконує повне завершення Runtime:

```text
runtime_state -> STOPPING -> OFF
RuntimeScheduler.stop()
cTrader disconnect exactly once
IB disconnect exactly once
SHUTDOWN event exactly once
SQLite connection close
повторний shutdown безпечний
```

Підтверджено:

```text
run_runtime_engine_controlled_shutdown_check.py
    runtime_state=OFF
    scheduler_running=False
    ctrader_disconnect_calls=1
    ib_disconnect_calls=1
    shutdown_events=1
    database_closed=True
    duplicate_shutdown_safe=True
    RUNTIME_ENGINE_CONTROLLED_SHUTDOWN_CHECK=OK
```

---

## 54.7. Controlled shutdown усіх Algorithm Workspaces

Перед завершенням застосунку всі WSP повинні бути зупинені незалежно від
поточного runtime state.

Канонічна дія `AlgorithmWorkspaceArea.shutdown_all_workspaces()`:

```text
stop active WorkspaceRuntime contexts
close all MDI subwindows
stop save/balance/replay timers
detach RuntimeEngine from controller and area
clear volatile runtime references
allow duplicate shutdown call
```

Підтверджено:

```text
run_algorithm_workspace_shutdown_check.py
    workspaces=2
    first_runtime_stopped=True
    second_runtime_stopped=True
    mdi_windows_closed=True
    timers_stopped=True
    runtime_engine_detached=True
    duplicate_shutdown_safe=True
    ALGORITHM_WORKSPACE_CONTROLLED_SHUTDOWN_CHECK=OK
```

Повний WSP Runtime-канон залишається в `LGE_Runtime_06.md`. У цьому документі
зафіксовано лише application shutdown contract.

---

## 54.8. Єдиний маршрут завершення LGE

Усі способи виходу використовують один shared controlled-shutdown path:

```text
верхнє меню Вихід
ліва кнопка Вихід
system tray Вихід
системне закриття головного вікна
```

Послідовність:

```text
1. Заблокувати повторний паралельний shutdown.
2. Зберегти стан головного вікна і Session UI.
3. Зупинити всі WSP.
4. Закрити auxiliary/top-level windows і dialogs.
5. Зупинити main-window timers.
6. Від'єднати OrdersPage від RuntimeEngine.
7. Виконати RuntimeEngine.shutdown().
8. Закрити SQLite connection.
9. Очистити session_state.CURRENT_RUNTIME_ENGINE.
10. Завершити QApplication.
```

Підтверджено:

```text
run_lge_controlled_exit_check.py
    workspace_shutdown_calls=1
    auxiliary_windows_closed=True
    main_timers_stopped=True
    runtime_state=OFF
    runtime_database_closed=True
    orders_runtime_detached=True
    session_state_cleared=True
    main_window_state_saved=True
    menu_button_window_tray_routes_shared=True
    duplicate_shutdown_safe=True
    LGE_CONTROLLED_EXIT_CHECK=OK
```

Windows temporary runtime DB після тесту видаляється без `WinError 32`, що
підтверджує фактичне закриття SQLite handle.

---

## 54.9. OrdersPage selection lifecycle

Виділення position/group/leg не повинно залишатися приховано активним після
того, як користувач перейшов до створення іншого ордера.

Додано два явні способи очистити selection:

```text
Esc
клік по порожній області дерева
```

Після очищення:

```text
current tree item=None
Modify disabled
Close disabled
Recovery disabled
SL field cleared
TP field cleared
status details cleared
```

Підтверджено synthetic і реальним UI test:

```text
run_orders_page_selection_clear_check.py
    escape_cleared=True
    empty_click_cleared=True
    operation_buttons_disabled=True
    sl_tp_fields_cleared=True
    ORDERS_PAGE_SELECTION_CLEAR_CHECK=OK
```

---

## 54.10. Реальний IB Paper regression: EURUSD

Після очищення старої неоднозначної broker exposure через реальну брокерську
операцію в LGE створено нову EURUSD virtual leg:

```text
symbol=EURUSD
side=BUY
volume=1 000
source=MANUAL
entry≈1.1519776
SL=1.1430
TP=1.1540
reconciliation=RECONCILED
```

Послідовність захисту:

```text
OPEN BUY без захисту
    ↓
CREATE SL
    ↓
CREATE/REPLACE TP з безпечною OCA-парою
    ↓
Refresh
    ↓
RECONCILED
```

TWS підтвердив активні `SELL STP` і `SELL LMT` для BUY-position.

---

## 54.11. Реальний IB Paper regression: GBPUSD

Після ручного закриття старої неоднозначної GBPUSD broker exposure створено
нову GBPUSD virtual leg:

```text
symbol=GBPUSD
side=BUY
volume=1 000
source=MANUAL
entry≈1.34410
initial protection=NONE
```

Далі через OrdersPage виконано:

```text
ADD SL=1.3350
    ↓
single protection CREATE confirmed
    ↓
ADD TP=1.3500
    ↓
orphan/survivor-safe replacement pair
    ↓
SL=1.3350, TP=1.3500
    ↓
RECONCILED
```

TWS підтвердив повну активну пару:

```text
GBPUSD SELL STP 1 000 @ 1.33500
GBPUSD SELL LMT 1 000 @ 1.35000
```

Старий одиночний SL не залишився третім активним захисним ордером.

---

## 54.12. Фінальний live snapshot 30.07.2026

Після останнього Refresh OrdersPage показав дві незалежні узгоджені IB-групи:

```text
EURUSD BUY 1 000
    one OPEN LGE LEG
    SL=1.1430
    TP=1.1540
    reconciliation=RECONCILED

GBPUSD BUY 1 000
    one OPEN LGE LEG
    SL=1.3350
    TP=1.3500
    reconciliation=RECONCILED
```

Підсумковий status line:

```text
IB groups=2
open legs=2
```

Обидві групи мають broker presence, окрему exact LGE leg identity та повний
захист. Cross-symbol contamination не виявлено.

---

## 54.13. Підтверджений стан broker-runtime блоку RoadMap94

```text
closed leg + non-zero Virtual FX resurrection blocked     : DONE
broker NET observation remains visible                    : DONE
unsafe manual recovery blocked                            : DONE
post-modify confirmed snapshot reuse                      : DONE
single SL/TP CREATE without child IDs                     : DONE
orphan OCA survivor replacement pair                      : DONE
active unmapped OCA peer safety block                     : DONE
controlled RuntimeEngine shutdown                         : DONE
controlled WSP shutdown                                   : DONE
shared menu/button/window/tray exit route                 : DONE
SQLite handle closure                                     : CONFIRMED
OrdersPage Esc selection clear                            : DONE
OrdersPage empty-area selection clear                     : DONE
real EURUSD BUY + SL/TP reconciliation                    : PASSED
real GBPUSD BUY + SL then TP replacement reconciliation  : PASSED
broker-runtime block RoadMap94                            : VERIFIED
```

RoadMap94 не змінює головну архітектурну межу:

```text
OrdersPage / WSP UI
    ↓
RuntimeEngine
    ↓
Broker Runtime Service
    ↓
SessionManager
    ↓
Adapter
    ↓
Broker API
```

GUI не працює з IB API напряму, а всі safety guards, OCA replacement,
reconciliation, persistence і shutdown залишаються відповідальністю Runtime.

---


# 55. RoadMap96 — повторне використання IB orderId та постійний облік зовнішньої CASH FX експозиції

RoadMap96 містив не лише алгоритмічну роботу, описану в `LGE_Runtime_06.md`.
Під час реальних багатоденних IB Paper перевірок було виявлено окремий
критичний broker-runtime блок, який істотно змінив канонічну модель IB CASH
Forex у `LGE_Runtime_05.md`.

Це не косметичне виправлення OrdersPage.

Змінено:

```text
довготривалу identity IB orders;
звірку LGE virtual legs після повторного використання orderId;
трактування позицій, відкритих безпосередньо в TWS;
трактування foreign-client SL/TP;
поведінку після зникнення reqPositions / Virtual FX observation;
SQLite schema v7 -> v8;
OrdersPage hierarchy і filter semantics;
майбутню безпеку AUTO Paper/Live виконання.
```

Алгоритмічні частини RoadMap95–RoadMap96 залишаються в
`LGE_Runtime_06.md` та `LGE_Algorithms_01.md`.
Цей розділ є канонічним саме для broker Runtime.

---

## 55.1. Причина production-hardening

Реальна IB Paper перевірка виявила одночасно кілька небезпечних властивостей
IB CASH Forex.

### 1. `orderId` може бути повторно використаний

Після нового TWS/API session IB знову використав broker order IDs:

```text
243
244
245
```

Ці значення вже належали старій закритій EURUSD virtual leg, але в новій
session ті самі `orderId` були видані новому parent/SL/TP ланцюжку.

Отже:

```text
orderId не є глобальною довготривалою identity.
```

### 2. TWS-ордери зливаються з LGE exposure

Позиція, відкрита вручну безпосередньо в TWS, потрапляє в той самий IB CASH
Forex net/Virtual FX стан, що й LGE virtual legs.

Приклад:

```text
EURUSD broker observation = BUY 3 000
точні OPEN LGE legs       = BUY 2 000
зовнішня експозиція       = BUY 1 000

GBPUSD broker observation = BUY 3 000
точні OPEN LGE legs       = BUY 2 000
зовнішня експозиція       = BUY 1 000
```

Зовнішні `1 000` не можна приписувати жодній LGE leg.

### 3. `reqPositions` може не повернути CASH FX row

Після restart, зміни trading day або особливостей Virtual FX observation
поточний positions snapshot може бути порожнім, хоча:

```text
раніше підтверджена зовнішня експозиція існувала;
foreign-client protective orders залишилися активними;
точні OPEN LGE legs залишилися у SQLite;
ризик для автоматичного виконання не зник.
```

Канонічний висновок:

```text
відсутність IB CASH Forex position row
    !=
доведена відсутність зовнішньої експозиції.
```

### 4. Foreign-client protective orders не є unmapped LGE protection

SL/TP, створені через TWS або інший `clientId`, можуть бути видимі через IB
API. Вони не належать LGE virtual legs і не повинні:

```text
прив'язуватися до LGE position_uid;
потрапляти до unmapped LGE protective IDs;
блокувати всі точні LGE legs як чужа помилка LGE;
зникати з інтерфейсу.
```

Водночас вони є важливим evidence потенційної зовнішньої експозиції.

---

## 55.2. Канонічна identity IB order після RoadMap96

Для довготривалої identity заборонено використовувати лише `orderId`.

Пріоритет доказів:

```text
1. persisted position_uid / trade_uid;
2. exact order role: PARENT / STOP_LOSS / TAKE_PROFIT / CLOSE;
3. permId;
4. parentOrderId;
5. OCA group;
6. clientId;
7. account + symbol;
8. action + quantity;
9. exact execution evidence;
10. orderId лише в межах підтвердженого identity context.
```

`IBVirtualPositionLeg` тепер зберігає окремо:

```text
parent_order_perm_id;
stop_loss_order_perm_id;
take_profit_order_perm_id.
```

Таблиця `ib_virtual_position_leg_orders` продовжує зберігати:

```text
broker_order_id;
parent_order_id;
perm_id;
client_id;
order_role;
oca_group;
order_ref;
is_active.
```

### Перевірений reused-orderId випадок

```text
reused_order_ids             = [243, 244, 245]
old_parent_perm_id           = 1900828147
current_parent_perm_id       = 963655516
old_closed_stays_reconciled  = True
current_open_owns_protection = True
group_reconciled             = True
no_unmapped_protection       = True
```

Repository sync додатково підтвердив:

```text
old_parent_repaired     = True
old_close_not_rebound   = True
current_eur_active      = True
current_gbp_active      = True
repeat_reconciled       = True
```

Головне правило:

```text
старий CLOSED leg не можна прив'язати до нового ордера
лише через однаковий orderId.
```

---

## 55.3. Три незалежні шари IB CASH Forex

Після RoadMap96 IB CASH Forex розглядається через три незалежні шари.

### 1. Точні LGE virtual legs

```text
persisted position_uid;
exact parent/SL/TP/CLOSE identity;
exact executions;
керовані LGE операції.
```

Це `managed LGE exposure`.

### 2. Поточна broker observation

```text
IB CASH Forex position / Virtual FX row;
поточний broker-side signed volume;
транзитне спостереження, яке може зникнути після restart.
```

Це не довготривала identity окремої leg.

### 3. Зовнішня IB FX експозиція

```text
частина broker exposure, яка не належить точним OPEN LGE legs;
позиція, відкрита через TWS або інший clientId;
broker-only position без LGE virtual legs;
раніше підтверджена експозиція, поточний row якої зник;
обережно виведена експозиція з foreign-client protective bracket.
```

Це read-only external exposure.

Коли current broker row доступний:

```text
external signed volume
    =
broker signed volume
    -
signed sum exact OPEN LGE legs
```

Зовнішня експозиція:

```text
не створює Trade;
не створює Position;
не створює IBVirtualPositionLeg;
не отримує position_uid;
не стає MANUAL / SEMI / AUTO leg;
не отримує вигадану entry price, SL, TP або PnL.
```

---

## 55.4. SQLite schema v8 — `ib_fx_external_exposures`

Поточна Runtime schema після RoadMap96:

```text
SCHEMA_VERSION = 8
PRAGMA user_version = 8
```

Додано таблицю:

```text
ib_fx_external_exposures
```

Поля:

```text
id
broker_position_id UNIQUE
account_id
symbol
signed_volume
evidence_status
last_confirmed_utc
last_observed_utc
cleared_utc
updated_utc
```

Індекс:

```text
account_id + symbol + evidence_status
```

Стани evidence:

```text
CONFIRMED
STALE
CLEARED
```

### `CONFIRMED`

Поточний complete broker snapshot підтвердив зовнішню експозицію або поточну
broker-only CASH FX position.

### `STALE`

Поточний position observation відсутній, але Runtime має достатній доказ,
щоб не забути потенційний broker risk:

```text
раніше підтверджений ledger row;
або foreign-client protective bracket.
```

`STALE` означає:

```text
експозиція показується;
потрібне підтвердження брокера;
AUTO Paper/Live для того самого account + symbol блокується.
```

### `CLEARED`

Точний поточний broker evidence підтвердив нульову зовнішню експозицію для
конкретного `broker_position_id`.

Важливе правило:

```text
порожній reqPositions snapshot сам по собі не очищає ledger.
```

Persistence external exposure виконується атомарно в тому самому safe sync,
що й reconciled virtual legs.

---

## 55.5. Політика evidence для зовнішньої експозиції

Канонічна послідовність:

### A. Є current CASH FX row і є точні LGE legs

```text
residual = broker signed volume - managed OPEN LGE volume
residual != 0 -> external exposure CONFIRMED
```

Group може залишатися `RECONCILED`, якщо exact LGE legs і їхній захист
узгоджені.

### B. Є current CASH FX row, але LGE legs відсутні

Уся broker position показується як read-only external exposure:

```text
group mode/status = safe read-only representation
external evidence = CONFIRMED
external operations = False
```

### C. Current CASH FX row зник, але ledger активний

```text
external exposure retained
status = STALE
confirmation_required = True
```

### D. Current CASH FX row зник, але є foreign-client protective orders

Runtime може вивести guarded external exposure, але не стверджує, що
underlying position точно існує.

Канонічне повідомлення:

```text
External IB FX exposure was inferred from active foreign-client
protective orders while the current position observation is absent;
the orders may be orphaned, so broker confirmation is required.
```

Це `STALE`, а не `CONFIRMED`.

### E. Один bracket рахується один раз

Активні SL і TP однієї foreign-client bracket-пари не означають дві позиції.

Bracket identity визначається в порядку:

```text
parentOrderId;
OCA group;
permId;
positive orderId.
```

Для однієї bracket-пари перевіряються:

```text
одна protective action;
однакова quantity;
account;
symbol.
```

Результат додається один раз.

### F. Foreign-client orders не є unmapped LGE orders

Захисні ордери іншого `clientId`:

```text
не додаються до unmapped_protective_order_ids;
залишаються read-only broker evidence.
```

IB API `orderId=0` не є stable identity та ігнорується в unmapped ID list.

---

## 55.6. IBPositionGroup після RoadMap96

`IBPositionGroup` додатково містить:

```text
broker_residual_signed_volume;
broker_residual_evidence_status;
broker_residual_present;
broker_residual_confirmation_required;
broker_residual_side;
broker_residual_volume.
```

Для Virtual FX group без current broker row UI використовує:

```text
display signed volume
    =
signed OPEN LGE legs
    +
broker residual signed volume
```

Реальний приклад 04.08.2026:

```text
EURUSD:
managed OPEN LGE legs = BUY 1 000
external exposure     = BUY 1 000
group display         = BUY 2 000

GBPUSD:
managed OPEN LGE legs = BUY 2 000
external exposure     = BUY 1 000
group display         = BUY 3 000
```

Зовнішній residual не повинен автоматично переводити точні LGE legs у
`BLOCKED`.

Дозволено:

```text
точний reconciled LGE child leg -> leg-level Modify/Close;
external child row              -> тільки read-only display.
```

Таким чином LGE не приховує повну broker exposure і водночас не втрачає
можливість точно керувати власними virtual legs.

---

## 55.7. OrdersPage — явний рядок зовнішньої експозиції

Попередня назва filter:

```text
Відкритий у брокері
```

після RoadMap96 замінена на точнішу:

```text
Зовнішні у брокері
```

Причина: рядок може бути видимим навіть тоді, коли current `reqPositions` row
відсутній. Це не обов'язково поточна «відкрита позиція» у вузькому значенні,
а збережена або виведена зовнішня exposure, яка потребує контролю.

Явний external row:

```text
ID                  = BROKER
Тип                 = Зовнішня експозиція
Напрямок            = BUY / SELL
Обсяг               = exact external residual
Джерело             = BROKER
position_uid        = відсутній
SL / TP             = порожні
PnL                 = порожній
операції             = disabled
```

Для current confirmed exposure:

```text
Звірка = Узгоджено
```

Для ledger/protective-only evidence:

```text
Звірка = Потрібне підтвердження
```

`STALE` row виділяється попереджувальним кольором у колонках:

```text
Тип;
Обсяг;
Звірка.
```

External row:

```text
не selectable;
Modify disabled;
Close disabled;
Manual recovery disabled;
не надсилає broker request.
```

Filter semantics:

```text
«Зовнішні у брокері» ON
    -> external rows видимі;

«Зовнішні у брокері» OFF
    -> external rows приховані;

mixed group з видимими LGE legs
    -> parent group залишається;

external-only group і filter OFF
    -> group не показується;

усі origin filters OFF
    -> таблиця порожня.
```

---

## 55.8. Захист AUTO Paper/Live від конфлікту із зовнішньою експозицією

Додано pure guard:

```python
evaluate_ib_fx_external_exposure_guard(
    exposures,
    account_id,
    symbol_name,
    runtime_mode,
)
```

DTO рішення:

```text
IBFxExternalExposureGuardDecision
```

Reason codes:

```text
IB_FX_EXTERNAL_EXPOSURE_ALLOWED
IB_FX_EXTERNAL_EXPOSURE_BLOCKED
```

Режими:

```text
REPLAY
LIVE_READ_ONLY
PAPER
LIVE
```

Політика:

```text
REPLAY         -> allowed, broker orders відсутні;
LIVE_READ_ONLY -> allowed, broker orders відсутні;
PAPER          -> same account + symbol external exposure blocks execution;
LIVE           -> same account + symbol external exposure blocks execution;
different symbol -> allowed.
```

Production integration RoadMap96 викликає guard перед AUTO IB MARKET order.

Послідовність:

```text
1. Refresh current broker group evidence.
2. Перевірити current broker-only/residual exposure.
3. Перевірити persisted external exposure ledger.
4. Якщо evidence refresh провалився -> fail closed.
5. Якщо same-symbol external exposure active -> BLOCK.
6. Trade / OrderPlan не створювати.
7. Broker request не надсилати.
```

Підтверджено:

```text
auto_integration_blocked_before_trade = True
broker_requests                       = 0
```

Поточна production інтеграція застосована саме до `AUTO` control mode.
Pure guard уже має окремі `PAPER` і `LIVE` semantics для подальшого WSP
execution layer.

---

## 55.9. Реальна live read-only перевірка 04.08.2026

### Virtual-leg snapshot

```text
complete                       = True
legs                           = 5
open_legs                      = 3
closed_legs                    = 2
unmapped_protective_order_ids  = []
sqlite_read_only               = True
```

Групи:

```text
EURUSD = RECONCILED
GBPUSD = RECONCILED
```

Для обох груп current CASH Forex position observation була відсутня, але
foreign-client protective orders залишалися видимими.

Runtime показав:

```text
external exposure inferred;
orders may be orphaned;
broker confirmation required.
```

### Position-group snapshot

```text
groups                = 2
EURUSD broker_present = False
GBPUSD broker_present = False
open_legs             = 3
closed_legs           = 2
net_only_groups        = 0
unmapped               = []
sqlite_read_only       = True
```

Точні LGE virtual legs залишилися `RECONCILED` і не були стерті через порожній
`reqPositions`.

Повторний live run дав той самий узгоджений результат, тобто read-only sync є
ідемпотентним і не залежить від одноразового transient snapshot.

### OrdersPage UI

Підтверджено:

```text
усі filters ON:
    LGE legs + external EURUSD + external GBPUSD;

external filter OFF:
    external rows hidden;

усі filters OFF:
    таблиця порожня;

Manual + External ON:
    точні manual LGE legs і read-only external rows;

external rows:
    BUY 1 000;
    Потрібне підтвердження;
    BROKER;
    operations disabled.
```

Фактичний UI-підсумок:

```text
EURUSD group = BUY 2 000
    LGE LEG          BUY 1 000
    External exposure BUY 1 000

GBPUSD group = BUY 3 000
    LGE LEG          BUY 1 000
    LGE LEG          BUY 1 000
    External exposure BUY 1 000
```

---

## 55.10. Синтетичні та live regression tests RoadMap96

Ключові перевірки:

```text
tests/runtime_ib/run_ib_virtual_leg_reused_order_id_check.py
tests/runtime_repository/run_runtime_repository_ib_reused_order_id_sync_check.py
tests/runtime_ib/run_ib_virtual_leg_external_residual_protection_check.py
tests/runtime_ib/run_ib_fx_external_exposure_ledger_check.py
tests/runtime_ib/run_ib_fx_external_exposure_display_snapshot_check.py
tests/runtime_ib/run_ib_cash_fx_missing_observation_display_check.py
tests/runtime_orders/run_orders_page_ib_broker_residual_check.py
tests/runtime_orders/run_orders_page_ib_external_only_exposure_check.py
tests/runtime_orders/run_orders_page_ib_stale_external_exposure_check.py
tests/runtime_manual/run_ib_virtual_leg_live_readonly_check.py
tests/runtime_manual/run_ib_position_groups_live_readonly_check.py
```

Підтверджені результати:

```text
reused orderId old/new identity separation       : OK
permId-based parent repair                       : OK
old Close mapping not rebound                    : OK
foreign TWS residual                             : OK
foreign bracket counted once                     : OK
foreign protective orders not unmapped           : OK
orderId=0 ignored as unstable identity            : OK
persistent external exposure after restart       : OK
empty reqPositions does not erase ledger         : OK
STALE requires confirmation                      : OK
current evidence clears matching symbol          : OK
unobserved external symbol retained              : OK
explicit OrdersPage external row                 : OK
external filter controls visibility              : OK
external row non-selectable                      : OK
external operations disabled                     : OK
same-symbol MANUAL/SEMI/AUTO guard before Trade  : OK
broker requests during blocked new execution     : 0
live read-only snapshot                          : OK
repeated live read-only snapshot                 : OK
```

---

## 55.11. Реорганізація Runtime tests

Через зростання кількості перевірок стару монолітну папку `tests/runtime`
розділено за відповідальністю.

Актуальні категорії:

```text
tests/runtime_core
tests/runtime_ctrader
tests/runtime_ib
tests/runtime_manual
tests/runtime_orders
tests/runtime_repository
tests/runtime_translation
tests/runtime_workspace
```

Правило:

```text
runtime_manual
    = реальні broker read-only / live regression scripts;

runtime_ib
    = чисті та синтетичні IB Runtime checks;

runtime_orders
    = OrdersPage behavior;

runtime_repository
    = SQLite persistence і migrations;

runtime_workspace
    = WSP Runtime;

runtime_translation
    = localization policy і retranslation.
```

Старі test paths у попередніх історичних розділах цього документа можуть
залишатися як назви тестів свого часу. Для поточного запуску використовуються
нові категоризовані paths.

Також виправлено сигнатури test doubles `LangManager.tr()` відповідно до
базового `LangManager`, прибрано protected-access, unused-variable та
shadowing warnings у нових tests/runtime helpers.

---

## 55.12. Канонічні інваріанти після RoadMap96

```text
1. IB orderId сам по собі не є довготривалою identity.
2. Reused orderId не може переприв'язати стару CLOSED leg.
3. permId, order role, parent/OCA/clientId та execution evidence мають вищий
   пріоритет за простий збіг orderId.
4. IB CASH Forex position row є transient Virtual FX observation.
5. Відсутність position row не доводить відсутність exposure.
6. Зовнішня exposure не перетворюється на LGE virtual leg.
7. External exposure зберігається окремо у schema v8 ledger.
8. Empty reqPositions не очищає ledger.
9. Current exact evidence може очистити тільки відповідний matching symbol.
10. Unobserved external symbols не стираються побічно.
11. Foreign-client SL/TP є read-only broker evidence, а не unmapped LGE
    protection.
12. Foreign bracket pair рахується один раз.
13. Foreign orderId=0 не є stable identity.
14. Exact reconciled LGE legs залишаються керованими навіть у mixed group.
15. External row ніколи не отримує Modify, Close або Manual Recovery.
16. External row не отримує вигадані entry, SL, TP або PnL.
17. STALE exposure завжди показує «Потрібне підтвердження».
18. MANUAL/SEMI/AUTO Paper/Live для exact account + symbol мають fail closed.
19. BLOCK виконується до Trade persistence і до broker execution request.
20. Replay і Live Read-only залишаються дозволеними, бо не виконують orders.
21. `lang/strings.json` вручну не редагується; нові keys живуть у fallback
    policy.
22. Поточна Runtime schema після цього блоку — v8.
```

---

## 55.13. Остаточний статус broker-runtime блоку RoadMap96

```text
reused IB orderId protection                         : DONE
permId-aware virtual-leg identity                    : DONE
repository repair without old-leg rebinding          : DONE
external TWS residual model                          : DONE
foreign-client protection classification             : DONE
IB orderId=0 unmapped false-positive fix              : DONE
persistent IB FX external exposure ledger            : DONE
schema v8                                             : DONE
CONFIRMED / STALE / CLEARED lifecycle                 : DONE
restart without position row                         : DONE
empty reqPositions retention                         : DONE
protective-only guarded exposure inference            : DONE
foreign bracket counted once                         : DONE
explicit external OrdersPage rows                    : DONE
filter «Зовнішні у брокері»                           : DONE
external row operation block                         : DONE
MANUAL/SEMI/AUTO same-symbol LGE EXCLUSIVE guard       : DONE
no broker request on guard block                      : CONFIRMED
real EURUSD/GBPUSD live read-only regression          : PASSED
repeated live snapshot idempotency                    : PASSED
broker-runtime RoadMap96 hardening                    : VERIFIED
```

Цей розділ замінює старі припущення попередніх розділів про те, що:

```text
порожній IB CASH position snapshot можна трактувати як нуль exposure;
будь-який foreign protective order є unmapped LGE protection;
external TWS residual повинен блокувати всю reconciled LGE group;
filter «Відкритий у брокері» достатньо точно описує broker-only state;
orderId є достатнім для довготривалої identity.
```

Після RoadMap96 канонічна модель така:

```text
точні LGE virtual legs
+
поточна transient IB CASH observation
+
постійний read-only external exposure ledger
+
fail-closed LGE EXCLUSIVE guard для всіх нових Paper/Live orders
```

---

# 56. LGE EXCLUSIVE і WSP `SAFETY_HOLD_EXTERNAL_EXPOSURE`

Цей розділ фіксує наступний суттєвий runtime-крок після базового зовнішнього
IB FX ledger з розділу 55.

Проблема, яку закрито:

```text
зовнішня позиція або bracket у TWS може з'явитися не тільки до запуску LGE,
а й під час уже активного WSP;

простий блок під час натискання Open недостатній;

AUTO WSP не повинен продовжувати формувати або виконувати нові ордери для
того самого IB account + symbol, не пояснивши користувачу причину;

read-only market data, chart і діагностика при цьому не повинні зникати.
```

---

## 56.1. Канонічна політика `LGE EXCLUSIVE`

Для IB Paper/Live вводиться exact-scope policy:

```text
broker + account_id + symbol
```

Правило:

```text
якщо для exact IB account + Forex symbol існує активна зовнішня FX exposure,
новий ордер LGE за цим самим ключем заборонено.
```

Політика стосується всіх джерел нового виконання:

```text
MANUAL;
SEMI;
AUTO.
```

Блокування виконується однаково для UI Open і майбутнього автоматичного
execution chain.

Не блокуються:

```text
Replay;
Live Read-only;
читання broker evidence;
оновлення chart;
журнал;
Close / Modify точних уже наявних reconciled LGE legs,
якщо відповідна операція сама по собі безпечна.
```

Останній пункт принциповий: `LGE EXCLUSIVE` не повинен заважати зменшити вже
наявний ризик або прибрати точну LGE-позицію.

---

## 56.2. Order-path invariant

Для нового IB ордера встановлено жорсткий порядок:

```text
1. Отримати актуальне IB evidence.
2. Оновити external exposure ledger.
3. Застосувати LGE EXCLUSIVE для exact account + symbol.
4. Лише якщо ALLOW — створити Trade.
5. Створити OrderPlan.
6. Надіслати broker execution request.
```

При `BLOCK` гарантовано:

```text
Trade rows created       = 0
OrderPlan rows created   = 0
broker execution request = 0
```

Runtime піднімає спеціальну помилку:

```text
IBFxExternalExposureExecutionBlockedError
```

Вона містить структуроване рішення guard і, коли доступно, exact external
exposure:

```text
account_id;
symbol;
side;
volume;
evidence_status;
confirmation_required.
```

Якщо current IB evidence отримати неможливо, execution path працює
`fail closed` з reason code:

```text
IB_FX_EXTERNAL_EVIDENCE_UNAVAILABLE
```

---

## 56.3. Persistent lifecycle і durable runtime events

Таблиця `ib_fx_external_exposures` залишається канонічним persistent ledger.
Schema не змінювалася і залишається `v8`.

Додано durable runtime events:

```text
IB_FX_EXTERNAL_EXPOSURE_CONFIRMED
IB_FX_EXTERNAL_EXPOSURE_STALE
IB_FX_EXTERNAL_EXPOSURE_CLEARED
```

Подія пишеться тільки при реальному переході або зміні факту:

```text
нова exposure;
CONFIRMED -> STALE;
STALE -> CONFIRMED;
зміна signed_volume;
CLEARED.
```

Повторний однаковий read-only snapshot не створює дубль події.

Payload містить:

```text
policy = LGE_EXCLUSIVE;
broker = IB;
broker_position_id;
account_id;
symbol;
signed_volume;
evidence_status;
previous_signed_volume;
previous_evidence_status.
```

Оновлення ledger і запис event виконуються в одній SQLite transaction разом із
reconciliation snapshot.

---

## 56.4. Новий recoverable WSP phase

Додано startup/runtime phase:

```text
SAFETY_HOLD_EXTERNAL_EXPOSURE
```

Це не `ERROR` і не `STOPPED`.

Коли зовнішня exposure з'явилася під час `RUNNING`:

```text
RUNNING
    -> STARTING
    -> SAFETY_HOLD_EXTERNAL_EXPOSURE
```

Під час hold:

```text
safety_hold_active      = True
signal_allowed          = False
can_form_signal()       = False
new LGE execution       = blocked
read-only quote polling = continues
chart updates           = continues
algorithm diagnostics   = continues
broker execution        = 0
```

У runtime context зберігаються volatile facts:

```text
safety_hold_reason_code;
safety_hold_message;
safety_hold_signed_volume;
safety_hold_evidence_status;
safety_hold_confirmation_required;
safety_hold_checked_utc;
safety_hold_revision.
```

`WorkspaceRuntime` журналює:

```text
SAFETY_HOLD_ENTERED
SAFETY_HOLD_UPDATED
SAFETY_HOLD_CLEARED
```

Перевірка safety виконується через broker-market provider. Для production
`RuntimeEngineWorkspaceMarketProvider` current evidence оновлюється не частіше
ніж один раз на 10 секунд, якщо не потрібен forced refresh.

---

## 56.5. Broker disconnect і safety hold

Connectivity має вищий оперативний пріоритет:

```text
SAFETY_HOLD_EXTERNAL_EXPOSURE
    -> WAIT_BROKER при disconnect;
```

Після reconnect:

```text
binding revalidated;
market-data subscription restored;
current external-exposure evidence перевіряється forced;
якщо exposure лишилася — WSP повертається у SAFETY HOLD;
якщо exposure очищена — WSP переходить у WAIT_SPREAD.
```

Chart та algorithm state під час цього циклу не очищаються.

---

## 56.6. Безпечне відновлення WSP

Hold не очищається лише тому, що користувач закрив TWS-вікно, змінив filter або
натиснув кнопку.

Потрібне current broker evidence:

```text
matching external exposure absent;
або matching ledger fact підтверджено як CLEARED.
```

Після підтвердженого очищення:

```text
SAFETY_HOLD_EXTERNAL_EXPOSURE
    -> WAIT_SPREAD
    -> READY
    -> RUNNING
```

Між clearing і `RUNNING` обов'язково потрібна нова live quote з допустимим
спредом. Старий spread до відновлення не використовується.

### 56.6.1. Канонічна семантика статусів IB open orders

Поточним open-order evidence вважаються лише нетермінальні broker rows.

Активні статуси:

```text
Submitted
PreSubmitted
PendingCancel
```

Термінальні статуси:

```text
Cancelled
ApiCancelled
Inactive
Filled
```

`PendingCancel` залишається активним evidence, доки IB не надішле
термінальний статус. Це запобігає передчасному зняттю safety hold під час
асинхронного скасування.

Термінальні rows відкидаються під час побудови current open-order snapshot і
не можуть:

```text
створювати broker residual;
підтримувати external protective-order evidence;
утримувати WSP у SAFETY_HOLD_EXTERNAL_EXPOSURE.
```

Видимий у TWS сірий рядок із червоним terminal marker і без активної кнопки
`Cancel` не є current open order. TWS може залишати такий рядок на екрані як
історичний запис. LGE орієнтується на broker status, а не на сам факт
візуальної присутності рядка.

`GTC` визначає строк життя активного ордера до виконання або скасування, але
не змінює семантику terminal status.

### 56.6.2. Очищення protective-only `STALE` exposure

External exposure, яка була виведена лише з foreign-client protective orders,
має таке походження:

```text
evidence_status    = STALE
last_confirmed_utc = NULL
```

Якщо complete current IB snapshot більше не містить matching активної
broker position і matching нетермінальних foreign-client protective orders,
така protective-only exposure переходить у `CLEARED`.

Очищення виконується тільки в exact scope:

```text
account_id + symbol
```

При цьому:

```text
керовані LGE virtual legs зберігаються;
external exposure інших symbols не очищається;
broker execution request не надсилається;
Trade і OrderPlan не створюються.
```

Раніше підтверджена broker position exposure не очищається автоматично лише
через зникнення SL/TP. Для неї потрібен current broker evidence, що точно
підтверджує нульову matching exposure.

---

## 56.7. Повідомлення користувачу і маршрут вирішення

Користувач не повинен здогадуватися, чому WSP перестав виконувати нові
ордери, де шукати проблему і які саме ордери TWS стосуються блокування.

Реалізовано повний recovery route:

```text
1. У WSP state показується локалізована «ЗАХИСНА ПАУЗА».
2. Tooltip state локалізований і містить:
   account + symbol + side + volume + evidence status;
   пояснення, що market data продовжує надходити;
   точний маршрут Orders -> external row -> Resolve reconciliation;
   маршрут повернення Monitoring -> WSP -> Journal.
3. При першому вході у hold головне вікно автоматично переходить в OrdersPage.
4. Warning прямо повідомляє, що OrdersPage вже відкрито автоматично.
5. Активним broker робиться IB.
6. Вмикається filter «Зовнішні у брокері».
7. Фокусується exact symbol WSP.
8. Помаранчевий external row можна виділити для діагностики.
9. Кнопка «Вирішення питань узгодження» відкриває read-only evidence dialog.
10. Після врегулювання у TWS користувач натискає «Оновити».
11. Для перегляду WSP і журналу користувач переходить у «Моніторинг».
```

External row залишається операційно read-only, але вже не є «мертвим» рядком:

```text
selectable              = True
Modify                  = False
Close                   = False
Resolve reconciliation  = diagnostic details only
broker request          = 0
Trade persistence       = 0
```

У таблиці та evidence dialog показуються поточні foreign-client protective
orders, якщо IB передав їх у snapshot:

```text
symbol;
action;
order_type;
quantity;
price;
orderId;
permId;
parentId;
clientId;
OCA group;
status;
TIF.
```

Для foreign-client order IB може повернути:

```text
orderId = 0
```

Це не помилка LGE. У такому разі canonical identity для ручної перевірки:

```text
permId + clientId + parentId + OCA + symbol + order type + price
```

LGE не вигадує номери рядків TWS на кшталт `6.1/6.2`. Якщо exact current
order rows відсутні, UI прямо забороняє скасовувати щось навмання і радить
перевірити TWS або IB Activity Statement.

LGE не має права самовільно закривати або змінювати чужу TWS exposure.

---

## 56.8. Localization

Нові ключі зареєстровані через стандартний `LangManager.tr(key, fallback)`
workflow і перенесені у `lang/strings_fallback.json` через:

```text
python dev_tools/rebuild_fallback.py --no-rcc
```

`lang/strings.json` після rebuild знову містить лише:

```json
{
  "lang_active": {
    "code": "uk"
  }
}
```

Критичні exact translations додано централізовано для:

```text
uk;
pl;
de;
fr.
```

Локалізовано не лише popup, а й safety tooltip та safety-critical journal
records. Raw English `SAFETY_HOLD_ENTERED`, `SAFETY_HOLD_UPDATED`,
`SAFETY_HOLD_CLEARED` і raw guard message більше не показуються користувачу
у відповідних safety lines.

Нові та розширені ключі:

```text
AlgorithmWorkspaceWindow.safetyHoldTooltip
AlgorithmWorkspaceJournal.categorySafety
AlgorithmWorkspaceJournal.safetyHoldEntered
AlgorithmWorkspaceJournal.safetyHoldUpdated
AlgorithmWorkspaceJournal.safetyHoldCleared
AlgorithmWorkspaceJournal.safetyHoldActiveMessage
AlgorithmWorkspaceJournal.safetyHoldClearedMessage
AlgorithmWorkspaceJournal.safetyPhaseChanged
AlgorithmWorkspaceJournal.safetyPhaseChangedMessage
AlgorithmWorkspaceSafety.sideBuy
AlgorithmWorkspaceSafety.sideSell
AlgorithmWorkspaceSafety.sideUnknown
AlgorithmWorkspaceSafety.evidenceConfirmed
AlgorithmWorkspaceSafety.evidenceStale
AlgorithmWorkspaceSafety.evidenceCleared
AlgorithmWorkspaceSafety.evidenceUnavailable
AlgorithmWorkspaceArea.externalExposureDetectedMessage
OrdersPage.msgExternalExposureOrderBlocked
OrdersPage.titleExternalExposureDetails
OrdersPage.msgExternalExposureDetailsIntro
OrdersPage.msgExternalExposureOrdersHeader
OrdersPage.msgExternalExposureOrderLine
OrdersPage.msgExternalExposureNoCurrentOrders
OrdersPage.msgExternalExposureResolutionSteps
OrdersPage.statusExternalExposureSelected
```

---

## 56.9. Regression checks

Оновлено:

```text
tests/runtime_ib/run_ib_fx_external_exposure_display_snapshot_check.py
```

Додатково перевіряє:

```text
foreign protective order rows captured = 2
permId preserved                       = True
parentId/clientId/OCA preserved        = True
orderId=0 preserved                    = True
LMT/STP prices preserved               = True
external operations                    = False
```

Оновлено:

```text
tests/runtime_orders/run_orders_page_ib_external_only_exposure_check.py
```

Додатково перевіряє:

```text
external diagnostic row selectable     = True
Modify/Close remain disabled            = True
exact foreign SL/TP visible             = True
Resolve reconciliation opens details    = True
permId/parentId/clientId/OCA visible     = True
orderId=0 visible without invention      = True
external filter recovery route           = True
```

Розширено:

```text
tests/runtime_workspace/
    run_algorithm_workspace_external_exposure_safety_hold_check.py
```

Додатково перевіряє:

```text
localized tooltip mentions Orders       = True
localized tooltip mentions Monitoring   = True
raw English guard message hidden         = True
localized SAFETY_HOLD_ENTERED             = True
localized SAFETY_HOLD_CLEARED             = True
broker execution attempted               = False
```

Чинними лишаються:

```text
tests/runtime_ib/run_ib_fx_external_exposure_ledger_check.py
tests/runtime_workspace/run_algorithm_workspace_live_readonly_check.py
```

Вони підтверджують durable ledger, exact account/symbol guard, відсутність
broker request і незмінність Live Read-only market flow.

Додано:

```text
tests/runtime_ib/run_ib_open_order_terminal_status_filter_check.py
tests/runtime_ib/run_ib_fx_inactive_external_orders_clear_check.py
```

Перший check фіксує:

```text
Submitted / PreSubmitted / PendingCancel = active evidence;
Cancelled / ApiCancelled / Inactive / Filled = terminal evidence;
terminal rows filtered                   = True;
PendingCancel kept active                = True;
broker requests                          = 0.
```

Другий check фіксує:

```text
terminal EURUSD protective orders ignored = True;
protective-only EURUSD exposure CLEARED    = True;
managed EURUSD leg preserved               = True;
active GBPUSD exposure preserved           = True;
exact scope account + symbol               = True;
broker execution attempted                 = False.
```

### 56.9.1. Windows/PySide6 і реальний IB Paper regression 05.08.2026

На робочому Windows/PySide6 середовищі пройшли:

```text
IB_OPEN_ORDER_TERMINAL_STATUS_FILTER_CHECK=OK
IB_FX_INACTIVE_EXTERNAL_ORDERS_CLEAR_CHECK=OK
IB_FX_EXTERNAL_EXPOSURE_DISPLAY_SNAPSHOT_CHECK=OK
IB_FX_EXTERNAL_EXPOSURE_LEDGER_CHECK=OK
ORDERS_PAGE_IB_EXTERNAL_ONLY_EXPOSURE_CHECK=OK
ALGORITHM_WORKSPACE_EXTERNAL_EXPOSURE_SAFETY_HOLD_CHECK=OK
```

Реальна IB Paper перевірка підтвердила повний lifecycle:

```text
1. Foreign-client EURUSD/GBPUSD protective pairs були показані як
   read-only BROKER exposure з exact permId/clientId/parentId/OCA evidence.
2. Після terminal broker statuses сірі TWS rows могли залишатися видимими,
   але більше не вважалися current open orders.
3. BROKER EURUSD і BROKER GBPUSD rows були очищені після Refresh.
4. Три керовані LGE virtual legs залишилися без змін.
5. IB GBPUSD WSP вийшов із SAFETY_HOLD_EXTERNAL_EXPOSURE через WAIT_SPREAD
   і повернувся у RUNNING після нової допустимої live quote.
6. LGE не надсилав modify/cancel/close broker request для external rows.
```

---

## 56.10. Змінені production modules

```text
engine/runtime_constants.py
engine/ib_adapter.py
engine/ib_fx_external_exposure.py
engine/ib_position_group.py
engine/ib_virtual_position_leg.py
engine/runtime_events.py
engine/runtime_repository.py
engine/runtime_engine.py
core/workspace_broker_market.py
core/workspace_runtime.py
core/algorithm_workspace_area.py
core/orders_page.py
core/main_logic.py
core/translation_policy.py
lang/strings_fallback.json
```

---

## 56.11. Канонічна модель після цього блоку

```text
IB current evidence
    +
persistent external exposure ledger
    +
durable transition events
    +
LGE EXCLUSIVE exact account/symbol guard
    +
WSP recoverable SAFETY HOLD
    +
user-visible Orders recovery route
    +
exact foreign protective-order evidence for manual TWS identification
    +
terminal IB order-status filtering
    +
exact protective-only STALE exposure clearing
```

Головний інваріант:

```text
зовнішня TWS exposure не приховується,
не перетворюється на LGE leg,
не керується LGE,
але блокує всі нові LGE Paper/Live orders для exact account + symbol
до підтвердженого clearing і нового допустимого live spread.

Термінальний IB order row не є current open-order evidence навіть тоді, коли
TWS ще залишає його видимим у таблиці.
```

---

## 56.12. Статус реалізації

```text
LGE EXCLUSIVE exact scope                    : DONE
MANUAL/SEMI/AUTO pre-Trade guard             : DONE
fail-closed evidence unavailable             : DONE
persistent transition journal                : DONE
WSP SAFETY_HOLD_EXTERNAL_EXPOSURE             : DONE
read-only market flow during hold             : DONE
fresh-spread recovery                         : DONE
OrdersPage automatic recovery route           : DONE
external row selectable for diagnostics       : DONE
external row Modify/Close remain disabled      : DONE
exact TWS evidence identifiers                 : DONE
orderId=0 / permId identity handled            : DONE
no invented TWS row numbers                    : DONE
localized WSP tooltip and safety journal       : DONE
uk/pl/de/fr critical translations              : DONE
strings.json cleanup workflow                 : DONE
terminal-order filtering                     : PASSED
inactive protective-only exposure clearing    : PASSED
non-Qt synthetic regression                   : PASSED
non-Qt exact evidence regression              : PASSED
Qt OrdersPage regression                      : PASSED
Qt WSP localization regression                : PASSED
real IB Paper live regression                 : PASSED
managed LGE legs preserved                    : PASSED
WSP safety-hold recovery to RUNNING            : PASSED
broker execution from recovery path           : 0
schema                                        : v8 unchanged
```

Цей розділ має пріоритет над старим формулюванням розділу 55, де safety guard
описувався лише як `AUTO guard`. Після цього блоку канонічне правило охоплює
`MANUAL`, `SEMI` і `AUTO` нові IB Paper/Live orders.

---

## 56.13. Завершальний RoadMap91B regression 05.08.2026

### 56.13.1. Реальний IB Paper lifecycle для двох symbols

Після попередньої synthetic/Qt regression виконано завершальну реальну
перевірку на `DUM513747` для `GBPUSD` та `EURUSD`.

Перевірено послідовність:

```text
external MKT execution у TWS
    -> external protective SL/TP іншого clientId
    -> exact BROKER row в OrdersPage
    -> automatic recovery popup
    -> exact-symbol WSP SAFETY_HOLD_EXTERNAL_EXPOSURE
    -> read-only market data continues
    -> opposite MKT execution у TWS
    -> manual Cancel only for exact remaining foreign SL/TP
    -> popup OK
    -> automatic Orders refresh
    -> BROKER row removed
    -> WAIT_SPREAD
    -> RUNNING
```

Результат `GBPUSD`:

```text
TWS executions                  : BUY 3K / SELL 3K
TWS Summary Net                 : 0
exact foreign protection        : TP 1.365 / SL 1.338
foreign protection cleanup      : manual Cancel in TWS
BROKER GBPUSD row after cleanup : absent
IB GBPUSD WSP                   : RUNNING
```

Результат `EURUSD`:

```text
TWS executions                  : BUY 1K / SELL 1K
TWS Summary Net                 : 0
exact foreign protection        : TP 1.170 / SL 1.140
foreign protection cleanup      : manual Cancel in TWS
BROKER EURUSD row after cleanup : absent
```

Підсумковий стан LGE:

```text
BROKER EURUSD external row      : absent
BROKER GBPUSD external row      : absent
managed EURUSD LGE leg          : preserved
managed GBPUSD LGE legs         : preserved
cTrader EURUSD WSP              : RUNNING
IB GBPUSD WSP                   : RUNNING
unrelated WSP interrupted       : False
LGE external cancel/modify      : 0
```

Практичне уточнення:

```text
закриття external net position не гарантує, що foreign protective SL/TP
зникнуть у TWS автоматично. Якщо exact foreign rows залишаються active,
користувач скасовує саме їх у TWS. LGE показує identifiers і стан, але не
виконує Cancel для external rows.
```

### 56.13.2. Popup auto-refresh

Підтверджено канонічний UI route:

```text
WSP detects exact external exposure
    -> Orders page prepared before popup
    -> warning popup shown
    -> user presses OK
    -> broker/account/symbol refresh runs once
    -> matching BROKER row is selected when still present
    -> cleared row disappears without separate manual Refresh
```

Пройшов Windows/PySide6 check:

```text
MAIN_EXTERNAL_EXPOSURE_POPUP_AUTO_REFRESH_CHECK=OK
```

Значення check:

```text
popup_closed=True
deferred_setup_before_popup=True
refresh_called_once_after_popup=True
broker_execution_attempted=False
```

### 56.13.3. Одноразовий warning sound для safety hold

До першого входу exact WSP у
`SAFETY_HOLD_EXTERNAL_EXPOSURE` додано системний Qt warning sound:

```text
QApplication.beep()
```

Звук прив'язаний до того самого one-shot guard, що й автоматичний recovery
popup:

```text
first entry into one hold        -> one sound
repeated runtime sync            -> no sound
SAFETY_HOLD_UPDATED              -> no sound
repeated broker snapshot         -> no sound
clear hold                       -> re-arm
new later hold                   -> one new sound
```

Додано regression check:

```text
tests/runtime_workspace/
    run_algorithm_workspace_external_exposure_alert_check.py
```

Він перевіряє:

```text
first_hold_beep_once=True
repeated_sync_silent=True
hold_update_silent=True
clear_silent=True
clear_rearms_alert=True
popup_signal_once_per_hold=True
exact_scope=DUM513747,GBPUSD
broker_execution_attempted=False
```

### 56.13.4. Остаточний інваріант RoadMap91B

```text
External IB FX execution/order evidence is always visible and exact.
LGE never adopts it as an LGE leg and never manages it.
Exact account + symbol WSP enters a recoverable safety hold.
The user receives one popup and one warning sound per hold lifecycle.
Market data remains read-only and active.
After current broker evidence is clear, LGE refreshes automatically,
requires a fresh valid spread and returns the WSP to RUNNING.
```

Фінальний статус після виконання нового Windows check:

```text
real dual-symbol IB Paper regression          : PASSED
TWS EURUSD Net 0                              : PASSED
TWS GBPUSD Net 0                              : PASSED
external foreign SL/TP exact cleanup          : PASSED
managed LGE legs preserved                    : PASSED
popup post-OK automatic refresh               : PASSED
one-shot safety-hold warning sound             : IMPLEMENTED
one-shot alert Windows/PySide6 check           : PASSED
broker execution from recovery/alert path      : 0
schema                                         : v8 unchanged
```

---
