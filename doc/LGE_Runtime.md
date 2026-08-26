# LGE Runtime Architecture

## Призначення

Цей документ описує runtime-архітектуру системи LGE.

Мета документа:

- уніфікувати логіку системи;
- визначити межі компонентів;
- забезпечити стабільну основу для інтеграції IB та cTrader;
- визначити SQLite як runtime-ядро;
- формалізувати поведінку системи;
- контролювати розвиток архітектури;
- фіксувати статус реалізації.

---

# Загальна структура системи

    LGE
     ├── UI
     ├── Core
     ├── Engine
     ├── Broker Adapters
     │     ├── IB
     │     └── cTrader
     └── SQLite Storage

---

# Основні принципи

- UI не містить бізнес-логіки
- SQLite є єдиним джерелом runtime-стану
- Signal ≠ Order
- Система працює тільки в межах Session
- Broker logic ізольований через adapter
- DEMO і LIVE розділені логічно
- Система враховує стан ринку
- Runtime будується поступово
- Архітектурні зміни обов'язково фіксуються в цьому документі

---

# LANG Architecture Rules

## Критичне правило LANG-системи

Нові перекладні ключі не додаються вручну в:

    lang/strings_fallback.json

`strings_fallback.json` є:

- canonical fallback resource;
- build-resource файлом;
- результатом rebuild;
- не місцем ручного додавання нових ключів.

---

## Єдиний API перекладу

Заборонено:

- локальні `_tr()` helper-и;
- дублювання translation helper у модулях.

Правильний API:

    self._lang_mgr.tr(key, fallback)

Єдине canonical місце:

    core/lang_manager.py

---

## Критичне правило fallback

`fallback` у:

    self._lang_mgr.tr(key, fallback)

Завжди повинен бути англійським текстом.

Правильно:

    self._lang_mgr.tr(
        "SettingsPageLicense.msgTrialEnabled",
        "TRIAL enabled.",
    )

Неправильно:

    self._lang_mgr.tr(
        "SettingsPageLicense.msgTrialEnabled",
        "Пробний режим увімкнено.",
    )

`fallback` є canonical EN-source для всіх автоперекладів.

Якщо передати неанглійський fallback, LANG-система запише неправильне значення в `en` і подальші переклади будуть зіпсовані.

---

## Правильний цикл додавання нового ключа

Новий ключ створюється через:

    self._lang_mgr.tr("Some.Key", "English fallback")

а не через:

    "[Some.Key]"

якщо ключ ще не існує.

---

## Що робить LangManager.tr()

`LangManager.tr()`:

- перевіряє `strings.json`;
- перевіряє `strings_fallback.json`;
- якщо ключ не існує, записує його в `lang/strings.json`;
- для активної мови може створити автопереклад;
- повертає готовий текст для UI.

Приклад правильного створення нового ключа:

    NavEntry(
        self._lang_mgr.tr(
            "SettingsCenter.tree.trading",
            "Trading mode",
        ),
        page_index=2,
    )

---

## Canonical LANG Workflow

Правильний порядок:

1. Новий UI/runtime текст додається через:

       self._lang_mgr.tr(key, english_fallback)

2. Перший запуск додає ключ у:

       lang/strings.json

3. Після накопичення нових ключів запускається:

       dev_tools/rebuild_fallback.py

4. `rebuild_fallback.py` переносить базові ключі у:

       lang/strings_fallback.json

5. Потім запускається:

       dev_tools/build_all.py

6. `build_all.py` компілює fallback у Qt resources.

7. Після цього для вже існуючих ключів можна використовувати формат:

       "[Some.Key]"

---

## Коли можна використовувати "[Some.Key]"

Формат:

    "[Some.Key]"

використовується тільки коли:

- ключ уже існує;
- fallback уже rebuilt;
- key уже є в fallback resources.

---

## Коли треба використовувати tr()

Формат:

    self._lang_mgr.tr(key, fallback)

використовується:

- для нових ключів;
- для кодових текстів;
- для status bar;
- для message boxes;
- для runtime-generated UI;
- для нових Settings pages;
- для будь-яких нових runtime labels.

---

## Типова помилка нового ключа

Якщо використати:

    "[Some.New.Key]"

Для нового ключа, тоді:

- ключ не буде створений;
- `strings.json` не оновиться;
- `rebuild_fallback.py` нічого не побачить;
- UI покаже сирий `[Some.New.Key]`.

Це вважається LANG bug.

---

## QGroupBox translation rule

`QGroupBox` не перекладається через `text()`.

Для `QGroupBox` треба окремо обробляти:

    title()
    setTitle()

Canonical pattern у `core/ui_translator.py`:

    def _apply_widget(self, widget: QWidget) -> None:
        self._apply_widget_title(widget)
        self._apply_widget_text(widget)
        self._apply_widget_placeholder(widget)

        if isinstance(widget, QGroupBox):
            self._apply_group_box_title(widget)

Окремий метод потрібен тому, що `QGroupBox` має власний API заголовка і не проходить через стандартну обробку `text()`.

---

## Common button rule

Canonical keys:

    [Common.btnOK]
    [Common.btnApply]
    [Common.btnCancel]

Правильні значення:

    "Common.btnOK": {
      "en": "OK",
      "uk": "Гаразд"
    }

    "Common.btnApply": {
      "en": "Apply",
      "uk": "Застосувати"
    }

    "Common.btnCancel": {
      "en": "Cancel",
      "uk": "Скасувати"
    }

Не використовувати для `Common.btnApply` значення типу:

    Подати заявку

Це інший зміст і для Settings-сторінок є помилкою.

---

# Runtime Development Rules

## md = canonical source

`md` (`LGE_Runtime.md`) є головним архітектурним документом runtime-системи.

Будь-які зміни:

- database schema
- engine modules
- event flow
- backtest logic
- broker integration
- risk logic
- session management
- LANG/i18n flow

Повинні:

1. відповідати md;
2. бути зафіксованими в md;
3. мати статус виконання.

---

## Mandatory progress tracking

Кожен великий етап і важливий підетап повинен мати статус:

- `[TODO]`
- `[IN_PROGRESS]`
- `[DONE]`
- `[DEPRECATED]`
- `[REPLACED]`

Приклад:

    ## SQLite Foundation [IN_PROGRESS]

---

## Architecture change control

Якщо під час реалізації:

- змінюється архітектура;
- виявляється помилка;
- приймається нове рішення;
- або знаходиться кращий підхід;

Це повинно:

1. бути явно описано;
2. бути внесено в md;
3. містити коротке пояснення причини змін.

Не допускаються "тихі" архітектурні зміни лише в коді.

---

## Incremental implementation rule

Система будується:

- малими кроками;
- з тестуванням після кожного етапу;
- без одночасного введення великих шматків логіки.

Правильний порядок реалізації:

1. database foundation
2. models
3. validation
4. event flow
5. backtest
6. broker execution
7. runtime UI

---

# Engine Layer Architecture

## Engine folder

Друга функціональна частина LGE реалізується в окремій папці:

    engine/

Назва `runtime/` не використовується.

`core/` залишається першою стабільною частиною LGE.

`engine/` містить:

- sessions
- signals
- filters
- rails
- decisions
- events
- backtest
- broker execution logic

---

## RoadMap66 canonical runtime modules [IN_PROGRESS]

RoadMap66 починає реальну runtime-основу ATS.

Поточна canonical структура runtime foundation:

    engine/
        __init__.py
        runtime_state.py
        runtime_events.py
        runtime_context.py
        runtime_engine.py

        db/
            __init__.py
            runtime_db.py

Призначення модулів:

- `runtime_state.py` — canonical runtime state machine;
- `runtime_events.py` — canonical runtime event model;
- `runtime_context.py` — живий runtime context у пам'яті;
- `runtime_engine.py` — orchestration layer;
- `db/runtime_db.py` — SQLite bootstrap для runtime DB.

Ці модулі не повинні залежати від:

- Qt;
- QWidget;
- QMessageBox;
- statusbar;
- Settings UI;
- broker-specific API.

---

## Runtime foundation rule

Runtime foundation реалізовується до broker adapters.

Правильний порядок RoadMap66:

1. runtime state machine;
2. runtime events;
3. runtime context;
4. runtime engine lifecycle;
5. SQLite bootstrap;
6. broker adapter interface;
7. IB/cTrader adapters.

Backtest поки не реалізується.

---

# Runtime State Machine [IN_PROGRESS]

## Призначення

Runtime State Machine визначає дозволені стани ATS engine і забороняє хаотичні переходи.

Це не UI-стан і не broker connection state.

Runtime state показує стан саме LGE engine.

---

## Canonical runtime states

    OFF
    STARTING
    RUNNING
    STOPPING
    ERROR

---

## Значення станів

### OFF

Нормальний стартовий стан.

Runtime:

- не запущений;
- не підключений до broker;
- не виконує торгову логіку;
- не створює ордери.

---

### STARTING

Runtime запускається.

На цьому етапі можуть виконуватися:

- відкриття SQLite DB;
- створення session;
- підготовка broker adapter;
- перевірка конфігурації;
- запис startup event.

---

### RUNNING

Runtime активний.

На цьому етапі дозволені:

- broker sync;
- event logging;
- account info;
- future signals/filters/orders flow.

---

### STOPPING

Runtime коректно завершується.

На цьому етапі виконуються:

- shutdown event;
- broker disconnect;
- session finalize;
- flush runtime data.

---

### ERROR

Аварійний стан runtime.

Причини:

- DB failure;
- broker failure;
- invalid state transition;
- startup/shutdown error;
- internal runtime error.

---

## Дозволені переходи

    OFF      -> STARTING

    STARTING -> RUNNING
    STARTING -> ERROR

    RUNNING  -> STOPPING
    RUNNING  -> ERROR

    STOPPING -> OFF
    STOPPING -> ERROR

    ERROR    -> OFF

Заборонені приклади:

    OFF -> RUNNING
    RUNNING -> STARTING
    ERROR -> RUNNING
    STOPPING -> STARTING

---

## Runtime state implementation

Файл:

    engine/runtime_state.py

Містить:

- `RuntimeState`
- `RuntimeStateError`
- `ALLOWED_TRANSITIONS`
- `normalize_runtime_state()`
- `can_transition()`
- `validate_transition()`
- `is_active()`
- `can_start()`
- `can_stop()`

---

# Runtime Events [IN_PROGRESS]

## Призначення

Runtime events — це canonical журнал життя ATS runtime.

Runtime events використовуються для:

- SQLite runtime log;
- debug;
- diagnostics;
- future Runtime UI;
- audit of runtime lifecycle.

---

## Canonical runtime event types

    STARTUP
    SHUTDOWN
    BROKER_SELECTED
    MODE_CHANGED
    ENGINE_CONFIG_CHANGED
    BROKER_CONNECTED
    BROKER_DISCONNECTED
    BROKER_CONNECTION_ERROR
    ERROR

---

## RuntimeEvent structure

RuntimeEvent містить:

- `event_type`
- `message`
- `created_utc`
- `payload`

Файл:

    engine/runtime_events.py

---

## Runtime internal language rule

Runtime internals можуть використовувати EN canonical messages.

UI-повідомлення повинні проходити через LANG/i18n.

Тобто:

- runtime DB/log messages — EN canonical допустимо;
- UI/statusbar/dialog messages — тільки через `LangManager.tr(key, english_fallback)`.

---

# Runtime Context [IN_PROGRESS]

## Призначення

RuntimeContext — поточний живий runtime state ATS у пам'яті.

RuntimeContext не читає config і не відкриває SQLite самостійно.

---

## RuntimeContext містить

    runtime_state
    broker
    account_mode
    execution_mode
    active_db
    session_id
    created_utc
    updated_utc

---

## Active DB

`active_db` показує, з якою SQLite DB працює поточний runtime engine.

Приклади:

    data/demo.db
    data/live.db
    data/test.db

---

## RuntimeContext implementation

Файл:

    engine/runtime_context.py

Містить:

- `RuntimeContext`
- `set_runtime_state()`
- `touch()`
- `to_dict()`

---

# Runtime Engine [IN_PROGRESS]

## Призначення

RuntimeEngine — orchestration layer ATS runtime.

RuntimeEngine:

- створює RuntimeContext;
- відкриває runtime DB;
- керує runtime state;
- створює runtime events;
- записує lifecycle events у SQLite;
- створює session record.

---

## RuntimeEngine constructor

Canonical pattern:

    RuntimeEngine(db_path="data/demo.db")

Це потрібно для майбутнього:

    DEMO -> data/demo.db
    LIVE -> data/live.db
    TEST -> data/test.db

Hardcode `"data/demo.db"` всередині engine не допускається.

---

## Поточний lifecycle

Startup:

    OFF -> STARTING -> RUNNING

Shutdown:

    RUNNING -> STOPPING -> OFF

---

## RuntimeEngine implementation

Файл:

    engine/runtime_engine.py

Поточна реалізація:

- `RuntimeEngine.__init__(db_path)`
- `add_event()`
- `startup()`
- `shutdown()`
- `set_broker()`
- `set_execution_mode()`
- `get_runtime_state()`

---

## RuntimeEngine boundaries

RuntimeEngine поки НЕ відповідає за:

- strategy execution;
- indicators;
- signals;
- filters;
- rails;
- orders;
- positions;
- backtest;
- Qt UI.

Це буде додаватися наступними етапами.

---

# SQLite Storage Structure

## Database structure

LGEOffice не використовується і не змінюється.
Це окрема програма з окремою БД.

Engine використовує 3 SQLite бази даних:

    data/
    ├─ demo.db
    ├─ live.db
    └─ test.db

---

## RoadMap66 runtime SQLite bootstrap [IN_PROGRESS]

Файл:

    engine/db/runtime_db.py

Призначення:

- відкрити SQLite DB;
- створити parent directory;
- увімкнути WAL;
- застосувати PRAGMA;
- встановити schema version;
- автоматично створити мінімальні runtime tables.

Canonical SQLite bootstrap застосовується однаково до:

    data/demo.db
    data/live.db
    data/test.db

---

## Runtime SQLite PRAGMA

Canonical PRAGMA:

    PRAGMA journal_mode=WAL;
    PRAGMA foreign_keys=ON;
    PRAGMA synchronous=NORMAL;
    PRAGMA temp_store=MEMORY;

---

## Runtime schema version

Runtime DB використовує:

    PRAGMA user_version

Поточна schema version:

    1

---

## Runtime bootstrap tables

Поточні runtime foundation tables:

    sessions
    runtime_events
    broker_accounts
    settings_runtime

Ці таблиці створюються автоматично через `connect_runtime_db()`.

---

## Runtime table naming decision

У попередніх правилах naming зазначено, що таблиці мають бути короткими, наприклад:

    sessions
    events
    signals
    orders
    positions

RoadMap66 уточнює це правило.

Для runtime foundation допускаються і фіксуються таблиці:

    runtime_events
    settings_runtime

Причина:

- відокремити engine lifecycle events від future trading events;
- уникнути конфлікту між runtime events, broker events, strategy events і backtest events;
- не змішувати runtime settings із загальними application settings.

Таблиця `sessions` залишається короткою, бо session є базовою runtime сутністю.

---

## Database purpose

### demo.db

Робоча база DEMO-режиму.

Містить:

- sessions
- signals
- filters
- rails
- orders
- positions
- events
- settings
- runtime_events
- broker_accounts
- settings_runtime

---

### live.db

Робоча база LIVE-режиму.

Структура повинна бути однаковою або максимально близькою до `demo.db`.

LIVE-режим реалізовується тільки після стабілізації DEMO runtime.

---

### test.db

База:

- backtest;
- прогон-тестів;
- тимчасово завантаженої broker history;
- тестових результатів.

Може містити:

- test_runs
- test_orders
- test_positions
- test_events
- test_results
- candles

У RoadMap66 `test.db` також отримує мінімальні runtime bootstrap tables, щоб структура DB lifecycle була єдиною.

---

## Historical data policy

LGE не веде постійне накопичення історичних ринкових даних.

Історичні дані:

- не завантажуються масово;
- не кешуються постійно;
- не є стандартним режимом роботи системи.

Broker history завантажується тільки:

- за явним запитом;
- для конкретного broker;
- для конкретного instrument;
- для конкретного timeframe;
- для конкретного періоду;
- для backtest/progon-test або ручного аналізу.

Тимчасова broker history може зберігатися в `test.db` і може очищатися після завершення тесту або аналізу.

---

## Runtime mode policy

LGE одночасно працює:

- тільки з одним broker;
- тільки в одному account mode.

Поточний broker і режим роботи зберігаються в `LGE.conf`.

Приклад:

    "engine": {
      "account_mode": "DEMO",
      "broker": "CTRADER",
      "execution_mode": "MANUAL"
    }

Поле `enabled` не використовується як базове архітектурне рішення, бо воно нечітке.
Стан роботи engine повинен визначатися через session, broker connection, account mode, execution mode та risk state.

---

## RoadMap65 canonical engine state

Після RoadMap65 canonical startup state у `LGE.conf`:

    "engine": {
      "broker": "OFF",
      "account_mode": "OFF",
      "execution_mode": "OFF"
    }

`engine.execution_mode` є source of truth для statusbar/runtime mode.

Statusbar більше не прив'язаний до license status.

Canonical values:

    broker:
        OFF
        CTRADER
        IB

    account_mode:
        OFF
        DEMO
        LIVE

    execution_mode:
        OFF
        MANUAL
        SEMI
        AUTO

---

## QComboBox configuration rule

Для всіх QComboBox, які записують canonical config value, обов'язково використовувати:

    addItem(text, userData)

Не покладатися на visible text як config value.

Причина:

- `currentData()` повинен повертати canonical value;
- переклад UI не повинен ламати конфігурацію;
- statusbar/runtime logic повинні працювати з canonical codes, а не з локалізованим текстом.

---

## Database implementation order

Правильний порядок реалізації:

    1. demo.db
    2. test.db
    3. live.db

RoadMap66 bootstrap технічно вже підтримує всі три DB:

    data/demo.db
    data/live.db
    data/test.db

Але functional implementation все одно йде в порядку:

    DEMO -> TEST -> LIVE

---

## Database naming rules

Зайве дублювання назв не використовується.

Контекст задається:

- файлом БД;
- модулем;
- структурою engine.

Тому таблиці мають короткі назви.

Правильно:

    sessions
    events
    signals
    orders
    positions
    candles
    test_runs

Неправильно:

    engine_sessions
    backtest_orders

RoadMap66 exception:

    runtime_events
    settings_runtime

Це не вважається порушенням, бо ці таблиці спеціально відокремлюють lifecycle/runtime-service data від future domain events/settings.

---

## Initial implementation rule

Початкова реалізація повинна бути мінімальною.

Нові:

- таблиці;
- поля;
- індекси;
- analytics;
- optimization blocks;
- додаткові runtime-компоненти;

Додаються лише після стабілізації базового engine flow.

---

# Broker Adapter Model

## Загальна схема

    LGE Order Core
        ↓
    Broker Adapter Interface
        ↓
    IB Adapter / cTrader Adapter / Other Broker Adapter

---

## Правила

- Core не знає деталей брокера
- Adapter транслює команди
- Основна логіка знаходиться в Core/Engine
- Broker-specific логіка ізольована

---

## RoadMap67 broker integration foundation [IN_PROGRESS]

RoadMap67 починає реальну broker integration architecture.

Перший production adapter:

    engine/ctrader_adapter.py

Поточний canonical flow:

    RuntimeEngine
        ↓
    BrokerInterface
        ↓
    CTraderAdapter
        ↓
    cTrader Open API

Перший broker — cTrader.

Причини:

- уже є working manual tests;
- auth flow перевірений;
- market order flow перевірений;
- positions/SLTP були перевірені раніше;
- старт простіший, ніж IB.

Поточний canonical broker interface:

    connect()
    disconnect()
    is_connected()
    get_account_info()

RoadMap67 scope:

- connection lifecycle;
- application auth;
- account auth;
- account lookup by `ctidTraderAccountId`;
- broker connection state;
- runtime event logging;
- SQLite runtime logging.

RoadMap67 НЕ включає:

- order execution у runtime engine;
- positions control;
- SL/TP;
- signals;
- backtest;
- Runtime UI.

Manual scripts у:

    tests/ctrader/manual/

залишаються тільки як diagnostic/manual recovery tools.

Вони не є основною runtime architecture.

---

## cTrader token/auth foundation [IN_PROGRESS]

RoadMap67 виявив і виправив критичну проблему старого auth шару.

Заборонено:

- генерувати fake tokens;
- зберігати placeholder tokens типу `new_access_token`;
- вважати token валідним тільки за локальним `expires_at`, якщо broker його відкидає;
- падати через hardcoded `C:\WebDriver\msedgedriver.exe`.

Canonical behavior:

- `tokens.json` зберігається у:

      tokens/tokens.json

- якщо access token недоступний або прострочений — виконується login/password auth flow;
- Selenium спочатку пробує заданий Edge driver path;
- якщо driver не знайдено — використовується Selenium Manager / PATH;
- після успішного browser auth token set зберігається в `tokens.json`;
- runtime adapter читає готовий token і не створює fake refresh result.

Поточний diagnostic tool:

    tests/ctrader/manual/run_ctrader_06a_place_order_login.py

Підтверджено:

- Selenium Manager сам підтягнув `msedgedriver`;
- login/password auth пройшов;
- `tokens.json` оновився;
- account list отриманий;
- account auth пройшов;
- market SELL order був прийнятий і виконаний у DEMO.

---

# Instruments and Timeframes

## Timeframes

    M1
    M5
    M15
    M30
    H1
    H4
    D1

Правила:

- визначаються в Engine;
- не залежать від брокера;
- проходять validation layer.

---

## Instruments

    broker symbols
        ↓
    normalized instruments
        ↓
    allowed instruments

Правило:

    недозволений instrument/timeframe → сигнал блокується

---

# Session

    id
    account_id
    broker
    mode
    started_utc
    ended_utc
    status

---

## Session rule

    без session → нема торгівлі

---

## RoadMap66 runtime session implementation [IN_PROGRESS]

Поточна runtime foundation вже створює запис у таблиці:

    sessions

Поточні поля:

- session_id
- runtime_state
- broker
- account_mode
- execution_mode
- created_utc

Це мінімальна session foundation.

Повна trading session schema буде розширена пізніше.

---

# Signal

    id
    session_id
    symbol
    timeframe
    type
    direction
    strength
    status

---

# Signal Lifecycle

    NEW
     → FILTERED
     → REJECTED | APPROVED
     → EXECUTED

---

# Rail

Рейки — це різкий імпульсний рух із вибиванням стопів і подальшим розворотом.

    id
    symbol
    timeframe
    direction
    spike_points
    reversal_points
    detected_utc
    active

---

## Rail rule

    rail може заборонити виконання сигналу

---

# Runtime Flow

    Market Data
     → Signal
     → Filter
     → Rail
     → Decision
     → Order
     → Position
     → Control
     → Event Log

---

# Order Lifecycle

    CREATED
     → SENT
     → ACCEPTED
     → FILLED | PARTIAL
     → CLOSED | CANCELLED | REJECTED

---

# Position State

    OPEN
     → MODIFIED
     → CLOSED
     → EMERGENCY_CLOSED

---

# Broker Quantity / Volume Model

    LGE quantity
        ↓
    Broker adapter
        ↓
    broker-specific volume / quantity

---

## cTrader

    lots ↔ api_volume

---

## IB

    STK  → shares
    CASH → FX units
    FUT  → contracts
    OPT  → contracts

---

## Quantity rule

- Core/Engine зберігає нормалізовану quantity
- Adapter відповідає за перерахунок

---

# Runtime UI / Dashboard

LGE не замінює брокерський термінал.

Брокерський термінал використовується як контрольний інструмент.

LGE Runtime UI показує:

- стан системи;
- сигнали;
- рішення;
- ордери;
- позиції;
- події;
- ризики.

---

## Мінімальні блоки

    Session
    Signals
    Orders
    Positions
    Events
    Connection Status
    Risk / Warnings

---

# Контрольна панель

## Session

    broker
    account
    demo/live
    mode
    status

---

## Signals

    time
    symbol
    timeframe
    type
    decision

---

## Orders

    symbol
    side
    type
    volume
    status
    origin

---

## Positions

    symbol
    side
    volume
    pnl
    SL
    TP
    controlled_by_lge

---

## Events

    time
    level
    source
    message

---

## Runtime UI rule

    Брокерський термінал показує ринок.
    LGE Runtime UI показує дії LGE.

---

# Контроль позицій

## Emergency Close

Дострокове закриття позиції при сильному русі проти неї.

    adverse_move_points
    time_window_sec
    volatility_factor

---

## Ownership

    origin:
        LGE
        EXTERNAL

---

## Ownership rule

    external → не керувати без дозволу

---

## Account Type

    DEMO
    LIVE

---

# Risk Control

    max_positions
    max_risk_per_trade
    max_daily_loss

---

## Risk rule

    risk перевищений → ордер не створюється

---

# Market Availability State [TODO]

## Призначення

MarketAvailabilityState показує доступність ринку для execution logic.

Це окремий стан від:

- RuntimeState
- BrokerConnectionState

Broker може бути:

    CONNECTED

але ринок може бути:

    MARKET_CLOSED

---

## Canonical market states

    MARKET_OPEN
    MARKET_PRE_CLOSE
    MARKET_CLOSED
    MARKET_PRE_OPEN

---

## Market state rule

При:

    MARKET_CLOSED

дозволені:

- broker connection;
- account sync;
- pending orders;
- runtime events;
- diagnostics;
- SQLite logging.

Заборонені:

- market orders;
- execution requiring live market price.

---

## Friday PRE_CLOSE rule

При:

    MARKET_PRE_CLOSE

система може:

- блокувати нові market entries;
- знижувати risk;
- закривати positions;
- дозволяти тільки protective actions.

---

## Weekend CLOSED rule

При:

    MARKET_CLOSED

Runtime може залишатися активним:

- broker connection alive;
- SQLite logging active;
- session active;
- runtime events active.

---

## Market availability architecture rule

Broker connection state і market availability state не повинні змішуватися.

Правильний приклад:

    BrokerConnectionState = CONNECTED
    MarketAvailabilityState = MARKET_CLOSED

У цьому стані:

- broker API доступний;
- account sync дозволений;
- runtime events дозволені;
- pending orders можуть бути дозволені;
- market execution заборонений.

---

## Pending Orders During CLOSED Market

Потрібно перевірити broker-specific behavior.

Очікуваний сценарій:

    MARKET_CLOSED

дозволяє:

- LIMIT orders
- STOP orders
- STOP_LIMIT orders

але блокує:

- MARKET orders

---

## Friday / Weekend protection

Перед weekend:

    MARKET_PRE_CLOSE

система може:

- закривати risk positions;
- блокувати нові aggressive entries;
- дозволяти тільки захисні дії.

Після weekend:

    MARKET_PRE_OPEN

може застосовуватись:

- gap filter;
- delayed execution;
- volatility protection.

---

## RoadMap67 follow-up verification

Потрібно перевірити:

    2026-05-16

для cTrader:

- account auth при закритому ринку;
- market order behavior;
- pending order behavior;
- broker response codes;
- canonical runtime handling.

---

## Runtime market state future tasks

Майбутні задачі:

- broker schedule sync;
- timezone handling;
- holiday calendar;
- Friday close logic;
- weekend gap protection;
- broker-specific trading sessions.

# Execution Mode

    MANUAL
    SEMI
    AUTO

---

# Event Model

    INFO
    WARNING
    ERROR
    BROKER_EVENT
    SYSTEM_EVENT

---

# Market Schedule and Time Behavior

## Market States

    OPEN
    PRE_CLOSE
    CLOSED
    PRE_OPEN

---

## Friday PRE_CLOSE

    - обмеження нових входів
    - можливе закриття позицій
    - зниження ризику

---

## Weekend CLOSED

    - ринок закритий
    - можливі broker events
    - session може бути активною

---

## Monday Open

    ризик: Weekend Gap

---

## Monday rules

    - блок входу перші N хвилин
    - або спеціальна стратегія

---

## Gap Control

    gap = abs(open_price - last_close_price)

---

## Gap rule

    gap > threshold → блок входу

---

## Weekend protection rule

    Після вихідних система не входить у ринок без додаткової перевірки.

---

# Historical Test / Backtest

Backtest перевіряє повний торговий цикл LGE на історичних даних.

    historical data
     → signal
     → filter
     → rail
     → decision
     → virtual order
     → virtual position
     → close
     → result

---

# Backtest Periods

    last 1 month
    last 2 months
    ...
    last 12 months

---

# Data Source Priority

    1. broker history
    2. temporary SQLite cache

---

# Result Metrics

    profit_loss
    number_of_trades
    wins
    losses
    win_rate
    max_drawdown
    profit_factor
    emergency_closes
    rail_blocks
    filter_rejections

---

# Backtest Rule

    Backtest не створює реальних broker orders.

---

# Status Tracking

## SQLite Foundation [IN_PROGRESS]

- engine folder structure
- database structure
- database naming
- runtime mode policy
- historical data policy
- status tracking rules
- LANG architecture rules
- RoadMap66 runtime SQLite bootstrap
- WAL/PRAGMA foundation
- schema version foundation
- demo/live/test DB bootstrap

---

## Runtime Foundation [IN_PROGRESS]

- `runtime_state.py` created
- `runtime_events.py` created
- `runtime_context.py` created
- `runtime_engine.py` created
- `engine/db/runtime_db.py` created
- runtime lifecycle implemented:
  - OFF -> STARTING -> RUNNING
  - RUNNING -> STOPPING -> OFF
- runtime events implemented:
  - STARTUP
  - SHUTDOWN
- runtime events are written to SQLite
- sessions are written to SQLite
- `RuntimeEngine(db_path=...)` supported
- `active_db` stored in RuntimeContext

---

## Trading Mode Settings [DONE]

- settings menu item created
- IB/cTrader separate stub pages removed
- `SettingsCenter.tree.trading` key created through `LangManager.tr()`
- `SettingsPageTrading.header` key created through `LangManager.tr()`
- `SettingsPageTrading` UI created through `.ui`
- `QGroupBox.title()` translation fixed in `UITranslator`
- common button translations normalized
- broker/account/execution mode saved to `LGE.conf`
- OFF/DEMO/LIVE fixed for account mode
- OFF/MANUAL/SEMI/AUTO fixed for execution mode
- statusbar uses `engine.execution_mode`
- statusbar no longer depends on license status
- QComboBox uses `addItem(text, userData)`

---

## Engine Models [TODO]

---

## Validation Layer [TODO]

---

## Event Flow [TODO]

---

## Backtest Engine [TODO]

---

## Broker Execution [IN_PROGRESS]

RoadMap67 completed/started:

- `engine/broker_interface.py` created/used as canonical interface
- `engine/broker_connection_state.py` created
- `engine/broker_account.py` created
- `engine/ctrader_adapter.py` created
- cTrader TCP connection verified
- cTrader application auth verified
- cTrader account auth verified
- `RuntimeEngine -> CTraderAdapter.connect()` verified
- `connected=True` verified
- `broker_state=CONNECTED` verified
- current scope limited to connection lifecycle

Not implemented yet:

- runtime order execution
- positions sync
- order sync
- account balance/equity sync
- SL/TP control
- reconnect strategy

---

## Runtime UI [TODO]

---

# Журнал архітектурних рішень

## 2026-05-06

- Прибрано архітектуру external import
- Broker history + SQLite cache обрані як canonical approach

---

## 2026-05-07

- md оголошено головним архітектурним документом
- Додано обов'язковий контроль виконання
- Додано контроль архітектурних змін
- Engine layer відокремлено від core
- Runtime implementation переведено на incremental model

---

## 2026-05-08

- Структуру баз даних спрощено до:
  - demo.db
  - live.db
  - test.db
- Постійний history.db прибрано
- Broker history переведено в тимчасовий on-demand режим
- Дозволено тільки один активний broker і один account mode одночасно
- DEMO-реалізацію обрано як перший етап implementation

---

## 2026-05-09

- Зафіксовано canonical LANG workflow
- Нові ключі створюються через `LangManager.tr(key, english_fallback)`
- Заборонено локальні `_tr()` helper-и в модулях
- Заборонено ручне додавання нових ключів у `strings_fallback.json`
- `fallback` у `tr()` повинен бути тільки англійським
- Settings item `Торговий режим / Trading mode` додано перед `Ліцензія / License`

---

## 2026-05-11

- RoadMap66 відкрито для стабілізації i18n/LANG flow
- Підтверджено canonical flow:
  - `LangManager.tr(key, english_fallback)`
  - `strings.json`
  - `rebuild_fallback.py`
  - `strings_fallback.json`
  - `build_all.py`
- Виправлено переклад `QGroupBox.title()` через окрему обробку в `UITranslator`
- Зафіксовано, що `QGroupBox` не перекладається через `text()`
- Нормалізовано зміст `Common.btnApply`:
  - `en`: `Apply`
  - `uk`: `Застосувати`
- Підтверджено, що `strings_fallback.json` не редагується вручну для нових ключів
- Після `rebuild_fallback.py` `strings.json` очищується до `lang_active`
- Наступна ціль: запис `broker/account_mode/execution_mode` у `LGE.conf`

---

## 2026-05-12

- RoadMap65 закрито
- `settings_page_trading.py` стабілізовано
- `LGE.conf` читається і пишеться правильно
- Canonical `engine` block:
  - broker: OFF
  - account_mode: OFF
  - execution_mode: OFF
- Account mode values:
  - OFF
  - DEMO
  - LIVE
- Execution mode values:
  - OFF
  - MANUAL
  - SEMI
  - AUTO
- Statusbar бере режим з `engine.execution_mode`
- Statusbar більше не прив'язаний до license status
- Для QComboBox зафіксовано правило:
  - завжди використовувати `addItem(text, userData)`
  - не покладатися на visible translated text

---

## 2026-05-13

- RoadMap66 перейшов до real runtime layer
- Створено canonical runtime modules:
  - `engine/runtime_state.py`
  - `engine/runtime_events.py`
  - `engine/runtime_context.py`
  - `engine/runtime_engine.py`
  - `engine/db/runtime_db.py`
- Runtime foundation не залежить від Qt/UI
- Backtest поки не реалізується
- Broker adapters поки не реалізуються

---

## 2026-05-13

- Реалізовано Runtime State Machine
- Canonical states:
  - OFF
  - STARTING
  - RUNNING
  - STOPPING
  - ERROR
- Дозволені переходи:
  - OFF -> STARTING
  - STARTING -> RUNNING
  - STARTING -> ERROR
  - RUNNING -> STOPPING
  - RUNNING -> ERROR
  - STOPPING -> OFF
  - STOPPING -> ERROR
  - ERROR -> OFF

---

## 2026-05-13

- Реалізовано Runtime Events foundation
- Canonical runtime event types:
  - STARTUP
  - SHUTDOWN
  - BROKER_SELECTED
  - MODE_CHANGED
  - ENGINE_CONFIG_CHANGED
  - ERROR
- Runtime events мають:
  - event_type
  - message
  - created_utc
  - payload

---

## 2026-05-13

- Реалізовано RuntimeContext
- RuntimeContext містить:
  - runtime_state
  - broker
  - account_mode
  - execution_mode
  - active_db
  - session_id
  - created_utc
  - updated_utc
- `active_db` фіксує поточну runtime DB

---

## 2026-05-13

- Реалізовано RuntimeEngine lifecycle
- Startup lifecycle:
  - OFF -> STARTING -> RUNNING
- Shutdown lifecycle:
  - RUNNING -> STOPPING -> OFF
- `RuntimeEngine(db_path=...)` підтримується
- Hardcode `data/demo.db` прибрано з RuntimeEngine

---

## 2026-05-13

- Реалізовано runtime SQLite bootstrap
- Canonical DB files:
  - data/demo.db
  - data/live.db
  - data/test.db
- У всіх трьох DB створюються foundation tables:
  - sessions
  - runtime_events
  - broker_accounts
  - settings_runtime
- Поточна schema version:
  - 1
- SQLite PRAGMA:
  - WAL
  - foreign_keys=ON
  - synchronous=NORMAL
  - temp_store=MEMORY

---

## 2026-05-13

- Реалізовано automatic runtime lifecycle logging
- `STARTUP` записується в `runtime_events`
- `SHUTDOWN` записується в `runtime_events`
- Session записується в `sessions`
- `runtime_events` підтверджено в SQLite
- `demo.db`, `live.db`, `test.db` підтверджено як bootstrap-ready

---

## 2026-05-13

- Уточнено table naming rule
- Для runtime foundation дозволено:
  - `runtime_events`
  - `settings_runtime`
- Причина:
  - відокремити runtime lifecycle events від future domain events
  - не змішувати runtime-service data з trading/backtest entities
- Це є свідомий RoadMap66 architecture decision, а не випадкове відхилення

---


## 2026-05-15

- RoadMap67 відкрито як перший реальний broker integration foundation етап
- UI, backtest і order execution у runtime engine поки не чіпаються
- Першим broker adapter обрано cTrader
- Створено/використано canonical flow:
  - `RuntimeEngine`
  - `BrokerInterface`
  - `CTraderAdapter`
  - `cTrader Open API`
- Додано/зафіксовано broker connection states:
  - DISCONNECTED
  - CONNECTING
  - CONNECTED
  - RECONNECTING
  - ERROR
- Додано/зафіксовано runtime broker events:
  - BROKER_ADAPTER_SELECTED
  - BROKER_CONNECTING
  - BROKER_CONNECTED
  - BROKER_DISCONNECTED
  - BROKER_CONNECTION_ERROR
- Підтверджено реальний runtime connection test:
  - TCP connected
  - application auth OK
  - account auth OK
  - `connected=True`
  - `broker_state=CONNECTED`
- Старий manual cTrader order script залишено як diagnostic/manual recovery tool
- `tests/ctrader/manual` більше не вважається основною architecture layer
- Виявлено і виправлено проблему старого auth/token шару:
  - fake token refresh заборонено
  - placeholder tokens заборонено
  - `tokens.json` має містити тільки реальні token values
- `run_ctrader_06a_place_order_login.py` відновлено як diagnostic tool для login/password auth і market order перевірки
- Selenium auth flow тепер може працювати без hardcoded `C:\WebDriver\msedgedriver.exe`, через Selenium Manager / PATH fallback
- Підтверджено, що Selenium Manager сам завантажив сумісний `msedgedriver`
- Підтверджено manual DEMO market SELL order:
  - ORDER_ACCEPTED
  - ORDER_FILLED
  - position created/opened
- Наступний production крок:
  - account sync
  - positions sync
  - order sync

---
# Статус документа

    Version: v8
    State: working
    RoadMap: 67