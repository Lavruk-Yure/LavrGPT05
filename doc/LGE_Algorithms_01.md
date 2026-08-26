# RoadMap80 — Market Intelligence та Order Intelligence

---

## 0. Початковий практичний порядок RoadMap80

---

RoadMap80 починається не з автоматичних алгоритмів і не з live trading.

Перший практичний крок — ручне виставлення, супровід і закриття ордерів через LGE.

Це потрібно для всіх ліцензій:

1. TRIAL — користувач бачить, як LGE працює з брокером.
2. NO_TRIAL — ручна торгівля може бути обмежена або заблокована політикою ліцензії, але архітектурно цей шар має існувати.
3. PRO — ручна і напівавтоматична робота.
4. PRO+ — ручна, напівавтоматична та автоматична робота.

Порядок реалізації:

1. Спочатку cTrader.
2. Потім IB.
3. Спочатку ручне відкриття ордера.
4. Потім ручне закриття ордера.
5. Потім зміна SL/TP.
6. Потім супровід позиції.
7. Тільки після цього — сигнали, алгоритми, backtest і AUTO.

Причина:

* без ручного Order Layer немає на що спирати алгоритми;
* OrderPlan має бути зрозумілий ще до автоматизації;
* ручна торгівля дозволяє перевірити broker service, account state, positions, orders, risk checks і журнал подій;
* це найпростіший шлях увійти в тему без стрибка одразу до складних алгоритмів.

---

## 0.0. Життєвий цикл угоди в LGE

---

Головний принцип LGE:

Ручна торгівля та алгоритмічна торгівля повинні проходити через однаковий життєвий цикл.

Усі угоди, незалежно від джерела їх виникнення, повинні використовувати однакові структури даних, однакові перевірки ризику та однаковий журнал подій.

---

Ручна торгівля:

```text
Користувач
→ OrderPlan
→ Risk Check
→ BrokerOrder
→ Position
→ Position Control
→ Close
→ Result
```

---

Алгоритмічна торгівля:

```text
Свічка
→ MarketObservation
→ SignalCandidate
→ FilterResult
→ TradeDecision
→ OrderPlan
→ Risk Check
→ BrokerOrder
→ Position
→ Position Control
→ Close
→ Result
```

---

Центральною сутністю системи є OrderPlan.

Саме в OrderPlan сходяться:

1. ручна торгівля;
2. сигнали;
3. алгоритми;
4. backtest;
5. demo;
6. live.

OrderPlan є єдиною точкою переходу від аналізу ринку до роботи з брокером.

---

Кожна угода повинна мати власний trade_id.

Через trade_id повинні зв'язуватися:

1. MarketObservation;
2. SignalCandidate;
3. TradeDecision;
4. OrderPlan;
5. BrokerOrder;
6. Position;
7. Result.

Це дозволяє в будь-який момент відповісти на питання:

```text
Чому була відкрита ця позиція?
Який сигнал її створив?
Яке рішення було прийняте?
Який ризик був дозволений?
```

---

## 0.0.1. Джерела позицій у LGE

---

LGE повинен працювати не тільки з позиціями, відкритими через LGE.

Система повинна вміти виявляти та аналізувати позиції, які були відкриті безпосередньо в торговому терміналі брокера.

---

Типи джерел позицій:

### LGE

Позиція створена через LGE.

Повний контроль:

1. сигнали;
2. рішення;
3. OrderPlan;
4. BrokerOrder;
5. Position Control;
6. Break Even;
7. Trailing Stop;
8. статистика;
9. backtest-аналітика.

---

### BROKER_MANUAL

Позиція створена вручну в торговому терміналі брокера.

Наприклад:

1. cTrader Desktop;
2. cTrader Web;
3. TWS;
4. IB Gateway;
5. Mobile App.

---

### IMPORTED

Позиція була відкрита раніше або відновлена після втрати з'єднання.

---

Для кожної позиції повинні існувати поля:

```text
position_source

LGE
BROKER_MANUAL
IMPORTED
```

та

```text
controlled_by_lge

True
False
```

---

Правило:

LGE ніколи не повинен змінювати зовнішню позицію без дозволу користувача.

---

Режими роботи із зовнішніми позиціями:

```text
EXTERNAL_POSITION_MODE

IGNORE
MONITOR
TAKE_CONTROL
```

---

IGNORE

Зовнішня позиція ігнорується.

---

MONITOR

LGE показує позицію, аналізує її та веде статистику, але не втручається.

---

TAKE_CONTROL

Користувач дозволяє LGE взяти позицію під супровід.

Після підтвердження дозволяється:

1. Break Even;
2. Trailing Stop;
3. Emergency Close;
4. Position Control;
5. статистика;
6. Risk Manager.

---

Таким чином LGE може працювати як:

1. система ручної торгівлі;
2. система супроводу ручних позицій;
3. напівавтоматична система;
4. повністю автоматична система.

---

## 0.1. Candle-based pipeline для аналізу ринку

---

LGE не зберігає всі тики.

Тиків надто багато, тому для першого етапу аналізу і backtest основою є історичні свічки.

---

Перед аналізом ринку користувач формує WatchList.

WatchList визначає список символів, які LGE повинен аналізувати.

Перший варіант WatchList:

1. EURUSD;
2. GBPUSD.

Пізніше:

1. XAUUSD;
2. USDJPY;
3. US30;
4. NAS100;
5. SPX500;
6. CRYPTO.

---

LGE аналізує тільки символи з WatchList.

Алгоритми не повинні автоматично обробляти всі доступні символи брокера.

---

Для кожного символу повинен існувати SymbolState.

Можливі стани:

```text
ACTIVE
WATCH_ONLY
DISABLED
```

---

ACTIVE

Повний аналіз та створення сигналів.

---

WATCH_ONLY

Аналіз дозволений.

Створення OrderPlan заборонене.

---

DISABLED

Символ повністю виключений з аналізу.

---

Базова операційна схема:

```text
WatchList
→ Market Data
→ Market Context
→ Market Observation
→ Signal Candidate
→ Filters
→ Trade Decision
→ Order Plan
→ Virtual Execution
→ SQLite
```

---

Перший broker для відлагодження:

1. cTrader.

---

Перший практичний етап не алгоритми, а ручне відкриття і закриття ордерів через cTrader.

Тільки після стабільної роботи ручних ордерів дозволяється перехід до автоматичного формування OrderPlan.

---

Перші символи:

1. EURUSD.
2. GBPUSD.

---

Перші таймфрейми:

1. M15 — основний робочий таймфрейм.
2. H1 — старший трендовий фільтр пізніше.

---

Перші типи ордерів:

1. MARKET_BUY.
2. MARKET_SELL.

Пізніше:

1. LIMIT_BUY.
2. LIMIT_SELL.
3. STOP_BUY.
4. STOP_SELL.

---

SL/TP мають бути обов'язковими вже на рівні OrderPlan.

---

## 0.2. Перехід від історії до реального ринку

---

Алгоритм не повинен знати, звідки прийшла свічка.

У backtest:

```text
SQLite candles_m15
→ MarketCandle
→ Algorithm
```

У live-режимі:

```text
Broker stream
→ Candle Builder
→ MarketCandle
→ Algorithm
```

---

Тобто алгоритм отримує однаковий об'єкт MarketCandle і в історії, і в реальному ринку.

Це головний міст між backtest і live trading.

---

## 0.2.1. SQLite Signal Pipeline

---

Головний принцип LGE:

Алгоритми не працюють напряму з брокером.

Усі етапи аналізу ринку, прийняття рішень, формування ордерів та супроводу позицій повинні бути зафіксовані в SQLite.

---

Базова схема проходження угоди:

```text
WatchList
→ MarketContext
→ MarketObservation
→ SignalCandidate
→ FilterResult
→ TradeDecision
→ Trade
→ OrderPlan
→ BrokerOrder
→ Position
→ Result
```

---

Перші таблиці SQLite:

### watchlists

Списки символів для аналізу.

---

### symbol_states

Стан символів.

---

### market_contexts

Контекст ринку.

---

### market_observations

Факти, помічені системою.

---

Каталог перших Observation:

1. NEW_HIGH;
2. NEW_LOW;
3. LEVEL_BREAKOUT;
4. FALSE_BREAKOUT;
5. IMPULSE_UP;
6. IMPULSE_DOWN;
7. GAP_UP;
8. GAP_DOWN;
9. STOP_SWEEP_UP;
10. STOP_SWEEP_DOWN;
11. VOLATILITY_EXPANSION;
12. VOLATILITY_CONTRACTION.

---

Важливе правило:

MarketObservation не є сигналом.

Observation описує факт.

SignalCandidate описує торгову гіпотезу.

---

### signal_candidates

Кандидати у сигнали.

---

### signal_filter_results

Результати перевірок сигналів.

---

### trade_decisions

Рішення системи.

---

### trades

Канонічна сутність угоди.

---

### order_plans

Плани угод.

---

### broker_orders

Ордери брокера.

---

### positions

Позиції.

---

### position_events

Події супроводу позицій.

---

### virtual_orders

Віртуальні ордери для backtest.

---

### virtual_positions

Віртуальні позиції для backtest.

---

### backtest_results

Результати прогонів.

---

Принцип:

Якщо Observation не записаний у SQLite — для LGE його не існувало.

Якщо SignalCandidate не записаний у SQLite — для LGE його не існувало.

Якщо TradeDecision не записаний у SQLite — рішення не приймалося.

Якщо Trade не записаний у SQLite — угода не існувала.

Якщо OrderPlan не записаний у SQLite — угода не була запланована.

Якщо Position не записана у SQLite — позиція не існувала.

---

SQLite є канонічним журналом роботи системи.

---

## 0.2.2. Market Session Layer

---

Market State і Market Session — різні поняття.

Приклад:

```text
MARKET_OPEN
```

не означає, що зараз хороший час для торгівлі.

---

Для Forex необхідно визначати торгову сесію.

Типи:

1. SYDNEY;
2. TOKYO;
3. LONDON;
4. NEW_YORK;
5. LONDON_NEW_YORK_OVERLAP;
6. UNKNOWN.

---

Багато алгоритмів у майбутньому будуть використовувати:

1. London Open;
2. New York Open;
3. London/New York Overlap;
4. Friday Close;
5. Monday Open.

---

Session Layer є окремим шаром аналізу ринку.

Він не залежить від брокера та використовується всіма алгоритмами.

---

## 0.2.3. Asset Classes

---

LGE не повинен обмежуватися тільки Forex.

Початок реалізації виконується на Forex, але архітектура повинна бути готовою до інших ринків.

---

Підтримувані класи активів:

1. FOREX;
2. STOCK;
3. CFD;
4. INDEX;
5. FUTURE;
6. CRYPTO;
7. UNKNOWN.

---

Кожен клас активів має власні правила:

1. quantity;
2. pip_size;
3. tick_size;
4. contract_size;
5. trading_sessions;
6. risk_rules.

---

Алгоритми повинні працювати через канонічні моделі LGE, а не через специфіку конкретного брокера.

---

## 0.2.4. License Policy Layer

---

Ліцензія є окремим шаром контролю можливостей системи.

Алгоритми не повинні перевіряти тип ліцензії напряму.

Для цього існує License Policy Layer.

---

TRIAL

Дозволено:

1. аналіз ринку;
2. перегляд сигналів;
3. ручні ордери;
4. DEMO.

Заборонено:

1. AUTO.

---

NO_TRIAL

Дозволено:

1. ручні ордери;
2. аналіз ринку;
3. супровід позицій.

---

PRO

Дозволено:

1. MANUAL;
2. SEMI;
3. супровід позицій;
4. розширений аналіз.

---

PRO+

Дозволено:

1. MANUAL;
2. SEMI;
3. AUTO;
4. усі алгоритми;
5. повна автоматизація.

---

Усі перевірки ліцензій повинні виконуватись через єдину політику доступу.

---

## 0.2.5. Execution Mode Layer

---

Execution Mode визначає хто приймає остаточне рішення про виконання угоди.

---

MANUAL

Рішення приймає користувач.

LGE тільки аналізує ринок та готує OrderPlan.

---

SEMI

LGE формує OrderPlan.

Користувач підтверджує виконання.

---

AUTO

LGE самостійно:

1. створює OrderPlan;
2. проходить перевірки;
3. відправляє ордер брокеру;
4. супроводжує позицію.

---

Execution Mode перевіряється перед створенням BrokerOrder.

---

## 0.2.6. Що не входить у RoadMap80

---

RoadMap80 створює фундамент Market Intelligence та Order Intelligence.

RoadMap80 не створює:

1. повноцінну автоматичну торгівлю;
2. AI-прогнозування ринку;
3. оптимізатор стратегій;
4. генетичні алгоритми;
5. машинне навчання;
6. великі історичні архіви;
7. масове завантаження історії;
8. портфельний менеджер;
9. арбітражні системи;
10. високочастотну торгівлю.

---

Мета RoadMap80:

```text
Market Data
→ Market Context
→ Market Observation
→ Signal
→ Decision
→ Trade
→ OrderPlan
→ Position Control
```

---

## 0.2.7. Canonical Market Intelligence Flow

---

Головний канон Market Intelligence у LGE:

```text
Market Data
→ Market Structure
→ Market Context
→ Market Observation
→ Signal Candidate
→ Trade Decision
→ Trade
→ OrderPlan
→ Risk Manager
→ Execution Gateway
→ Broker Service
→ Broker Adapter
→ Broker Order
```

---

Market Structure описує поточну структуру ринку.

Наприклад:

1. TREND_UP;
2. TREND_DOWN;
3. FLAT;
4. IMPULSE_UP;
5. IMPULSE_DOWN;
6. GAP_RISK.

---

MarketObservation не є сигналом.

SignalCandidate не є ордером.

TradeDecision не є дозволом на відкриття позиції.

OrderPlan не є broker order.

Кожен шар виконує тільки свою задачу.

---

Будь-який етап може:

1. дозволити продовження;
2. змінити параметри;
3. заблокувати виконання.

---

Цей ланцюг є канонічною моделлю роботи LGE для:

1. backtest;
2. demo;
3. live;
4. manual;
5. semi;
6. auto.

---


## 0.3. Перший майбутній алгоритм

---

Перший алгоритм для опису після ручних ордерів:

```text
ALG-001 Trend Pullback
```

Українською:

```text
Тренд + відкат
```

---

Базова логіка:

1. H1 визначає напрям тренду.
2. M15 шукає відкат.
3. Формується MarketObservation.
4. Створюється SignalCandidate.
5. Працюють фільтри.
6. Створюється TradeDecision.
7. Створюється OrderPlan.
8. У MANUAL та SEMI користувач підтверджує дію.
9. В AUTO дія може виконуватись автоматично в майбутніх RoadMap.

---

## 1. Що знайдено в RoadMap по алгоритмах аналізу ринку

### 1.1. RoadMap04 — ранній базовий задум ATS

1. Order Manager:

   1. create;
   2. validate;
   3. send;
   4. confirm.
2. Режими:

   1. MANUAL;
   2. SEMI;
   3. AUTO.
3. Risk Manager:

   1. max exposure;
   2. stop-loss;
   3. max drawdown;
   4. блокування ордерів без захисту.
4. Backtester:

   1. подача даних bar-by-bar;
   2. стратегія на історії;
   3. закриття через N барів;
   4. лог результатів.

### 1.2. RoadMap18 — перші практичні торгові правила

1. IB/TWS як контрольний термінал.
2. Quantity ≠ lot:

   1. FX в IB — кількість базової валюти;
   2. LGE має мати власну нормалізовану quantity-модель.
3. Market order без SL/TP — тимчасовий навчальний режим, не бойовий.
4. SL/TP — окремі broker orders або bracket orders.
5. Break Even rule:

   1. якщо ціна пройшла X pips у правильний бік;
   2. перенести SL на entry або entry + buffer.
6. Класична схема супроводу:

   1. Entry;
   2. SL = structure + buffer;
   3. TP1 = 1R;
   4. TP2 = level;
   5. TP3 = trail / extension.
7. Заборона “тягнути TP далі”, якщо:

   1. є протиімпульс;
   2. структура ламається;
   3. ринок дає ознаки розвороту.
8. Другий вхід після вибивання стопа:

   1. stop sweep;
   2. повернення ціни;
   3. повторний вхід тільки після підтвердження.

### 1.3. RoadMap50–51 — підготовка до API-торгівлі

1. Спочатку ручне розуміння термінала.
2. Потім API:

   1. handshake;
   2. account info;
   3. positions;
   4. market data;
   5. order simulation;
   6. тільки потім test order.
3. Принцип:

   1. без market data — нема алгоритму;
   2. без account/positions — нема order execution;
   3. без order simulation — нема live/demo order layer.

### 1.4. RoadMap63–65 — перехід до Runtime ATS

1. Runtime має містити:

   1. sessions;
   2. signals;
   3. filters;
   4. rails;
   5. broker_accounts;
   6. orders;
   7. positions;
   8. events;
   9. settings.
2. Для історії:

   1. historical_candles;
   2. backtest_runs;
   3. backtest_orders;
   4. backtest_positions;
   5. backtest_events;
   6. backtest_results.
3. Окремо згадано:

   1. рейки;
   2. імпульсні дні;
   3. gap після вихідних;
   4. прогон 1–12 місяців.

### 1.5. RoadMap66–68 — Runtime Market State

1. Market availability state відокремлено від broker connection state.
2. Канонічні стани:

   1. MARKET_OPEN;
   2. MARKET_CLOSED;
   3. MARKET_PREOPEN;
   4. MARKET_HALTED;
   5. MARKET_UNKNOWN.
3. Market order дозволений тільки при валідному market state.
4. Pending orders можуть бути дозволені під час MARKET_CLOSED, але це broker-specific.
5. RuntimeMarketStateTask уже існує як scheduler task.

### 1.6. RoadMap77–80 — майбутній документ алгоритмів

1. Окремий документ: `LGE_Algorithms_01.md`.
2. Він має містити:

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
   11. position sizing;
   12. backtest policy;
   13. broker history policy;
   14. demo/live policy.

---

## 2. Що знайдено в Markdown-документах

### 2.1. `LGE_Runtime.md`

1. Instruments and Timeframes:

   1. M1;
   2. M5;
   3. M15;
   4. M30;
   5. H1;
   6. H4;
   7. D1.
2. Instruments:

   1. broker symbols;
   2. normalized instruments;
   3. allowed instruments.
3. Signal:

   1. id;
   2. session_id;
   3. symbol;
   4. timeframe;
   5. type;
   6. direction;
   7. strength;
   8. status.
4. Signal lifecycle:

   1. NEW;
   2. FILTERED;
   3. REJECTED;
   4. APPROVED;
   5. EXECUTED.
5. Rail:

   1. spike;
   2. stop sweep;
   3. reversal;
   4. rail може заборонити сигнал.
6. Runtime Flow:

   1. Market Data;
   2. Signal;
   3. Filter;
   4. Rail;
   5. Decision;
   6. Order;
   7. Position;
   8. Control;
   9. Event Log.
7. Order Lifecycle:

   1. CREATED;
   2. SENT;
   3. ACCEPTED;
   4. FILLED;
   5. PARTIAL;
   6. CLOSED;
   7. CANCELLED;
   8. REJECTED.
8. Position State:

   1. OPEN;
   2. MODIFIED;
   3. CLOSED;
   4. EMERGENCY_CLOSED.
9. Risk Control:

   1. max_positions;
   2. max_risk_per_trade;
   3. max_daily_loss.
10. Market Availability:
11. MARKET_OPEN;
12. MARKET_PRE_CLOSE;
13. MARKET_CLOSED;
14. MARKET_PRE_OPEN.
15. Weekend/Gap:
16. Friday PRE_CLOSE;
17. Weekend CLOSED;
18. Monday PRE_OPEN;
19. gap filter;
20. delayed execution;
21. volatility protection.
22. Backtest:
23. historical data;
24. signal;
25. filter;
26. rail;
27. decision;
28. virtual order;
29. virtual position;
30. close;
31. result.

### 2.2. `LGE_Runtime_00.md`

1. BrokerInterface future methods:

   1. get_positions;
   2. get_orders;
   3. place_market_order;
   4. place_limit_order;
   5. place_stop_order;
   6. modify_position;
   7. close_position.
2. Market Availability State already described:

   1. MARKET_OPEN;
   2. MARKET_CLOSED;
   3. MARKET_PREOPEN;
   4. MARKET_HALTED;
   5. MARKET_UNKNOWN.
3. Execution gate:

   1. can_place_market_order;
   2. can_place_pending_order.

### 2.3. `LGE_Runtime_01.md`

1. Unified Market Layer.
2. Canonical market states.
3. Market orders тільки при MARKET_OPEN.
4. Pending orders можуть бути дозволені при MARKET_CLOSED.
5. `detect_market_state()` як єдина точка.

### 2.4. `LGE_Runtime_02.md`

1. RuntimeMarketStateTask.
2. Periodic market checks.
3. Broker-independent `detect_market_state()`.
4. MARKET_CLOSED:

   1. market orders blocked;
   2. pending orders allowed.

### 2.5. `LGE_Runtime_03.md`

1. Market-state scheduler implemented.
2. Scheduler перевіряє:

   1. market state;
   2. market order availability;
   3. pending order availability.
3. До order actions треба:

   1. broker CONNECTED;
   2. account loaded;
   3. market state valid;
   4. SAFE_DISCONNECTED block.

### 2.6. `LGE_Runtime_05.md`

1. Прямо сказано: Runtime документ не описує торгові алгоритми.
2. Торгові алгоритми мають бути в `LGE_Algorithms_01.md`.
3. Order execution дозволяється тільки після:

   1. RuntimeEngine valid;
   2. broker connected;
   3. account loaded;
   4. market availability valid;
   5. execution_mode дозволяє дію;
   6. risk manager дозволяє дію.
4. Заборонено виконання ордерів, якщо:

   1. broker не CONNECTED;
   2. ринок недоступний;
   3. runtime у SAFE_DISCONNECTED.

---

## 3. Нові ідеї для аналізу ринку

### 3.1. Розділити Market Intelligence на 5 шарів

1. Data Layer:

   1. tick;
   2. candle;
   3. snapshot;
   4. spread;
   5. volume/tick_volume.
2. State Layer:

   1. market open/closed;
   2. session;
   3. volatility;
   4. spread state;
   5. liquidity state.
3. Structure Layer:

   1. trend;
   2. flat/range;
   3. impulse;
   4. level;
   5. gap.
4. Signal Layer:

   1. candidate signal;
   2. filtered signal;
   3. approved signal;
   4. rejected signal.
5. Execution Layer:

   1. entry;
   2. SL;
   3. TP;
   4. BE;
   5. trail;
   6. emergency close.

### 3.2. Не робити “індикаторного зоопарку”

Перший варіант LGE має бути класичний:

1. ціна;
2. свічки;
3. структура;
4. рівні;
5. імпульс;
6. spread;
7. час;
8. ризик.

Індикатори типу MA/MACD/ATR можна додати пізніше як допоміжні фільтри, а не як основу системи.

### 3.3. Ввести Market Regime

Кожен символ у кожен момент має режим:

1. UNKNOWN;
2. TREND_UP;
3. TREND_DOWN;
4. FLAT;
5. IMPULSE_UP;
6. IMPULSE_DOWN;
7. HIGH_VOLATILITY;
8. LOW_LIQUIDITY;
9. GAP_RISK.

### 3.4. Ввести Signal не як “купити/продати”, а як гіпотезу

Signal не повинен одразу означати Order.

Правильний ланцюг:

1. MarketObservation;
2. SignalCandidate;
3. FilterResult;
4. TradeDecision;
5. OrderPlan;
6. BrokerOrder.

### 3.5. Ввести OrderPlan

Перед реальним ордером має бути об’єкт OrderPlan:

1. symbol;
2. side;
3. order_type;
4. quantity;
5. entry_price;
6. stop_loss;
7. take_profit;
8. risk_amount;
9. risk_percent;
10. reason;
11. invalidation_reason;
12. execution_mode.

Це дає контроль, журнал і backtest.

---

# 4. Програма реалізації Market Intelligence + Orders

## 4.1. RoadMap80.1 — Canonical Market Models

### 4.1.1. Створити пакет

```text
engine/market_data/
    __init__.py
    market_symbol.py
    market_tick.py
    market_candle.py
    market_snapshot.py
```

### 4.1.2. MarketSymbol

Поля:

1. symbol;
2. base_asset;
3. quote_asset;
4. broker;
5. broker_symbol;
6. asset_class;
7. min_quantity;
8. quantity_step;
9. is_fractional;
10. price_digits;
11. pip_size.

---

is_fractional показує чи дозволяє інструмент дробові обсяги.

Приклади:

```text
BTCUSD     → True
ETHUSD     → True

AAPL       → False

EURUSD     → залежить від broker rules
```

---

Asset classes:

1. FOREX;
2. CFD;
3. STOCK;
4. FUTURE;
5. INDEX;
6. CRYPTO;
7. UNKNOWN.

---

### 4.1.3. `MarketTick`

Поля:

1. symbol;
2. bid;
3. ask;
4. last;
5. bid_size;
6. ask_size;
7. time_utc;
8. broker;
9. source.

### 4.1.4. `MarketCandle`

Поля:

1. symbol;
2. timeframe;
3. open;
4. high;
5. low;
6. close;
7. volume;
8. tick_volume;
9. start_utc;
10. end_utc;
11. broker;
12. source.

### 4.1.5. `MarketSnapshot`

Поля:

1. symbol;
2. bid;
3. ask;
4. spread;
5. last;
6. time_utc;
7. broker;
8. market_state;
9. is_tradeable.

---

## 4.2. RoadMap80.2 — Symbol Registry

### 4.2.1. Створити пакет

```text
engine/symbols/
    __init__.py
    symbol_registry.py
```

### 4.2.2. Канонічні символи

1. EURUSD;
2. GBPUSD;
3. USDJPY;
4. XAUUSD;
5. US30;
6. NAS100;
7. SPX500.

### 4.2.3. Broker mapping

1. IB:

   1. EURUSD → EUR.USD;
   2. GBPUSD → GBP.USD.
2. cTrader:

   1. EURUSD → EURUSD;
   2. GBPUSD → GBPUSD.

### 4.2.4. Правило

У Runtime та алгоритмах використовується тільки canonical symbol.

Broker-specific symbol дозволений тільки в adapter/service layer.

---

## 4.3. RoadMap80.3 — Market Data Service

### 4.3.1. Створити

```text
engine/services/
    market_data_service.py
```

### 4.3.2. Відповідальність

1. отримати tick від broker service;
2. нормалізувати в `MarketTick`;
3. оновити `MarketSnapshot`;
4. передати дані в algorithms layer;
5. писати події в RuntimeEvents.

### 4.3.3. Перший етап

Без real streaming.

Почати з ручного/тестового snapshot:

1. fake tick;
2. manual snapshot;
3. unit/manual diagnostic script.

---

## 4.4. RoadMap80.4 — Market State Service 2.0

### 4.4.1. Поточний стан

Уже є:

1. `market_availability_state.py`;
2. `RuntimeMarketStateTask`.

### 4.4.2. Доробити

Створити:

```text
engine/services/
    market_state_service.py
```

### 4.4.3. Об’єднати

1. Forex weekday/weekend heuristic;
2. broker-specific session check;
3. spread state;
4. holiday/future calendar later;
5. manual override later.

### 4.4.4. Вихід

`MarketStateResult`:

1. symbol;
2. state;
3. reason;
4. can_place_market_order;
5. can_place_pending_order;
6. source;
7. checked_utc.

---

## 4.5. RoadMap80.5 — Historical Data Storage

### 4.5.1. Таблиці

```text
candles_m1
candles_m5
candles_m15
candles_h1
candles_h4
candles_d1
```

### 4.5.2. Поля

1. id;
2. symbol;
3. broker;
4. time_utc;
5. open;
6. high;
7. low;
8. close;
9. volume;
10. tick_volume;
11. source;
12. created_utc.

### 4.5.3. Правило

Поки не робити масове завантаження.

Тільки:

1. структура;
2. insert одного candle;
3. read останніх N candles;
4. diagnostic test.

---

## 4.6. RoadMap80.6 — Market Structure Layer

### 4.6.1. Створити

```text
engine/market_analysis/
    __init__.py
    market_structure.py
    market_regime.py
    trend_detector.py
    range_detector.py
    impulse_detector.py
    level_detector.py
```

### 4.6.2. Призначення

Market Structure є першим рівнем інтерпретації ринку після отримання Market Data.

---

Канонічний ланцюг:

```text
Market Data
→ Market Structure
→ Market Context
→ Market Observation
→ Signal Candidate
```

---

### 4.6.3. Market regimes

1. UNKNOWN;
2. TREND_UP;
3. TREND_DOWN;
4. FLAT;
5. IMPULSE_UP;
6. IMPULSE_DOWN;
7. HIGH_VOLATILITY;
8. LOW_LIQUIDITY;
9. GAP_RISK.

---

### 4.6.4. Перший мінімальний аналіз

1. trend by higher highs / higher lows;
2. trend by lower highs / lower lows;
3. flat by narrow range;
4. impulse by candle body/range ratio;
5. gap by open vs previous close;
6. spread filter.

---

### 4.6.5. Вихід

MarketStructureResult:

1. symbol;
2. timeframe;
3. market_regime;
4. confidence;
5. created_utc.

---

## 4.7. RoadMap80.7 — Signal Layer

### 4.7.1. Створити

```text
engine/signals/
    __init__.py
    signal_type.py
    signal_candidate.py
    signal_filter_result.py
    trade_signal.py
```

### 4.7.2. Signal types

1. TREND_UP;
2. TREND_DOWN;
3. FLAT;
4. IMPULSE_UP;
5. IMPULSE_DOWN;
6. RAIL_UP;
7. RAIL_DOWN;
8. GAP_RISK;
9. UNKNOWN.

### 4.7.3. Signal lifecycle

1. CANDIDATE;
2. FILTERED;
3. REJECTED;
4. APPROVED;
5. EXPIRED;
6. EXECUTED.

### 4.7.4. Правило

Signal не створює order напряму.

Signal тільки передається в Decision Layer.

---

## 4.8. RoadMap80.8 — Filter Layer

### 4.8.1. Створити

```text
engine/filters/
    __init__.py
    spread_filter.py
    market_state_filter.py
    volatility_filter.py
    time_filter.py
    risk_filter.py
```

### 4.8.2. Мінімальні фільтри

1. market must be open;
2. spread <= max_spread;
3. no first N minutes after Monday open;
4. no Friday pre-close aggressive entries;
5. no trading during SAFE_DISCONNECTED;
6. no trading if account not loaded.

---

## 4.9. RoadMap80.9 — Decision Layer

### 4.9.1. Створити

```text
engine/decisions/
    __init__.py
    trade_decision.py
    decision_engine.py
```

### 4.9.2. Decision states

1. NO_TRADE;
2. WATCH;
3. APPROVE_BUY;
4. APPROVE_SELL;
5. CLOSE_POSITION;
6. MODIFY_POSITION;
7. EMERGENCY_CLOSE.

### 4.9.3. Decision має містити

1. signal_id;
2. symbol;
3. side;
4. reason;
5. confidence;
6. risk_status;
7. created_utc.

---

## 4.10. RoadMap80.10 — OrderPlan Layer

### 4.10.1. Створити

```text
engine/orders/
    __init__.py
    order_plan.py
    order_type.py
    order_side.py
    trade_state.py
```

### 4.10.2. Trade Lifecycle

Кожна угода проходить життєвий цикл.

```text
CREATED
OBSERVED
SIGNALLED
APPROVED
PLANNED
EXECUTED
MANAGED
CLOSED
CANCELLED
REJECTED
```

---

### 4.10.3. OrderPlan

Поля:

1. trade_id;
2. symbol;
3. side;
4. order_type;
5. quantity;
6. entry_price;
7. stop_loss;
8. take_profit;
9. risk_amount;
10. risk_percent;
11. source_signal_id;
12. source_decision_id;
13. execution_mode;
14. created_utc.

---

### 4.10.4. Правило

OrderPlan ще не є broker order.

Broker order створюється тільки після:

1. broker CONNECTED;
2. market_state valid;
3. risk approved;
4. rails approved;
5. execution_mode allowed;
6. user confirmation, якщо MANUAL або SEMI.

---

## 4.11. RoadMap80.11 — Risk Manager

### 4.11.1. Створити

```text
engine/risk/
    __init__.py
    risk_manager.py
    risk_result.py
    position_sizing.py
    risk_rails.py
```

### 4.11.2. Мінімальні правила

1. max risk per trade;
2. max daily loss;
3. max open positions;
4. block order without SL;
5. block order if spread too high;
6. block order if market state invalid;
7. block AUTO if license/execution mode does not allow.

---

### 4.11.3. Risk Rails

Risk Rails є окремим захисним шаром.

Вони можуть заборонити виконання угоди незалежно від сигналів та алгоритмів.

Перші рейки:

1. SAFE_DISCONNECTED_RAIL;
2. MARKET_CLOSED_RAIL;
3. WEEKEND_RAIL;
4. SPREAD_RAIL;
5. NEWS_RAIL;
6. MAX_DAILY_LOSS_RAIL;
7. ACCOUNT_NOT_READY_RAIL;
8. LICENSE_RAIL.

---

Будь-яка активна рейка має право заблокувати виконання BrokerOrder.

---

### 4.11.4. Position Sizing

1. fixed quantity;
2. fixed risk amount;
3. percent of equity;
4. broker minimum quantity;
5. broker quantity step.

---

## 4.11.5. News Layer

---

Новинний шар не входить у першу реалізацію RoadMap80.

Проте архітектура повинна враховувати його появу.

---

Майбутні рівні новин:

1. LOW_IMPACT;
2. MEDIUM_IMPACT;
3. HIGH_IMPACT.

---

Майбутні режими:

```text
ALLOW_TRADING
REDUCE_RISK
NO_TRADE
```

---

Приклад:

```text
NFP
CPI
FOMC
ECB
BOE
```

можуть автоматично активувати:

```text
NO_TRADE_WINDOW
```

---

News Layer повинен працювати через Risk Rails і не змінювати алгоритми напряму.

---

## 4.12. RoadMap80.12 — Position Control

### 4.12.1. Створити

```text
engine/positions/
    __init__.py
    position_controller.py
    break_even_rule.py
    trailing_rule.py
    emergency_close_rule.py
    protection_rules.py
```

### 4.12.2. Position Control

Position Control є окремим шаром системи.

Він працює після відкриття позиції.

---

### 4.12.3. Базові правила

1. move SL to BE after X pips / X R;
2. partial close TP1/TP2/TP3 later;
3. emergency close при сильному русі проти позиції;
4. не керувати EXTERNAL positions без дозволу;
5. controlled_by_lge flag.

---

### 4.12.4. Position Protection

Окремий шар захисту позиції.

Перші типи:

1. Weekend Protection;
2. Gap Protection;
3. Spread Protection;
4. News Protection.

---

### 4.12.5. External Positions

Для EXTERNAL_POSITION_MODE:

```text
IGNORE
MONITOR
TAKE_CONTROL
```

Position Control повинен враховувати режим роботи із зовнішніми позиціями.

---

## 4.13. RoadMap80.13 — Algorithm Framework

### 4.13.1. Створити

```text
engine/algorithms/
    __init__.py
    algorithm_base.py
    algorithm_context.py
```

### 4.13.2. `AlgorithmBase`

Методи:

1. on_tick();
2. on_candle();
3. build_signal();
4. build_decision();
5. build_order_plan().

### 4.13.3. Перші алгоритми

Без реальної торгівлі:

1. TrendStructureAlgorithm;
2. FlatRangeAlgorithm;
3. ImpulseAlgorithm;
4. RailAlgorithm;
5. GapProtectionAlgorithm.

---

## 4.14. RoadMap80.14 — Backtest Foundation

### 4.14.1. Створити

```text
engine/backtest/
    __init__.py
    backtest_engine.py
    backtest_context.py
    virtual_order.py
    virtual_position.py
    backtest_result.py
```

### 4.14.2. Backtest flow

1. historical candles;
2. algorithm;
3. signal;
4. filter;
5. decision;
6. virtual order;
7. virtual position;
8. close;
9. result.

### 4.14.3. Метрики

1. profit_loss;
2. trades;
3. wins;
4. losses;
5. win_rate;
6. max_drawdown;
7. profit_factor;
8. emergency_closes;
9. rail_blocks;
10. filter_rejections.

---

## 4.15. RoadMap80.15 — Execution Gateway

### 4.15.1. Створити пізніше

```text
engine/execution/
    __init__.py
    execution_gateway.py
    execution_result.py
```

### 4.15.2. Призначення

Перетворює OrderPlan у broker order.

### 4.15.3. Політика RoadMap80

RoadMap80 дозволяє ручну торгівлю через cTrader та IB.

RoadMap80 не дозволяє автоматичне виконання OrderPlan алгоритмами.

Автоматичне виконання є предметом наступного RoadMap.

---

Ручні сценарії дозволені:

1. відкриття позиції;
2. закриття позиції;
3. зміна Stop Loss;
4. зміна Take Profit;
5. Position Control;
6. супровід зовнішніх позицій.

---

Заборонено:

1. автоматичне створення BrokerOrder алгоритмами;
2. автоматичне відкриття позицій без підтвердження користувача;
3. автоматичне виконання AUTO-стратегій.

---

Мета RoadMap80:

1. Market Models;
2. Symbol Registry;
3. Market Snapshot;
4. Market Intelligence;
5. Signal Pipeline;
6. Trade Pipeline;
7. OrderPlan;
8. Position Control;
9. Manual Trading Foundation.

---

# 5. Рекомендований порядок RoadMap80

## 5.1. Перший пакет

Ручна торгівля cTrader.

1. відкриття позиції;
2. закриття позиції;
3. зміна Stop Loss;
4. зміна Take Profit.

---

## 5.2. Другий пакет

Position Control.

1. Break Even;
2. Trailing Stop;
3. Emergency Close;
4. External Position Mode.

---

## 5.3. Третій пакет

Market Models.

1. MarketSymbol;
2. MarketTick;
3. MarketCandle;
4. MarketSnapshot.

---

## 5.4. Четвертий пакет

Symbol Registry.

1. canonical symbols;
2. broker mapping;
3. EURUSD;
4. GBPUSD;
5. XAUUSD.

---

## 5.5. П’ятий пакет

Historical Storage.

1. candles_m15;
2. candles_h1;
3. read/write API;
4. diagnostic scripts.

---

## 5.6. Шостий пакет

Market Structure.

1. trend;
2. flat;
3. impulse;
4. levels;
5. gap.

---

## 5.7. Сьомий пакет

Market Observation.

1. breakout;
2. false breakout;
3. stop sweep;
4. volatility expansion;
5. volatility contraction.

---

## 5.8. Восьмий пакет

Signal Layer.

1. SignalCandidate;
2. SignalFilterResult;
3. lifecycle.

---

## 5.9. Дев’ятий пакет

Decision Layer.

1. TradeDecision;
2. DecisionEngine.

---

## 5.10. Десятий пакет

OrderPlan.

1. Trade;
2. OrderPlan;
3. Trade Lifecycle.

---

## 5.11. Одинадцятий пакет

Risk Manager.

1. Position Sizing;
2. Risk Rails;
3. License Policy;
4. Execution Policy.

---

## 5.12. Дванадцятий пакет

Algorithm Framework.

1. AlgorithmBase;
2. AlgorithmContext;
3. Dummy Algorithm.

---

## 5.13. Тринадцятий пакет

Backtest Foundation.

1. Virtual Orders;
2. Virtual Positions;
3. Backtest Engine;
4. Backtest Results.

---

# 6. Головне архітектурне правило

---

LGE не має права переходити напряму від ринкових даних до брокерського ордера.

Заборонений шлях:

```text
Market Data
→ Broker Order
```

---

Так само заборонені спрощені варіанти:

```text
Market Data
→ Signal
→ Order
```

або

```text
Market Data
→ Indicator
→ Order
```

---

Будь-яке торгове рішення повинно проходити повний канонічний ланцюг.

---

Канонічний ланцюг LGE:

```text
Market Data
→ Market Structure
→ Market Context
→ Market Observation
→ Signal Candidate
→ Filter Result
→ Trade Decision
→ Trade
→ OrderPlan
→ Risk Manager
→ Execution Gateway
→ Broker Service
→ Broker Adapter
→ Broker Order
→ Position
→ Position Control
→ Result
```

---

Кожний шар має власну відповідальність.

---

### Market Structure

Описує структуру ринку.

Приклади:

1. TREND_UP;
2. TREND_DOWN;
3. FLAT;
4. IMPULSE_UP;
5. IMPULSE_DOWN;
6. GAP_RISK.

---

### Market Context

Описує середовище ринку.

Приклади:

1. LONDON;
2. NEW_YORK;
3. LONDON_NEW_YORK_OVERLAP;
4. HIGH_VOLATILITY;
5. LOW_LIQUIDITY.

---

### Market Observation

Описує факт.

Приклади:

1. NEW_HIGH;
2. NEW_LOW;
3. LEVEL_BREAKOUT;
4. FALSE_BREAKOUT;
5. STOP_SWEEP_UP;
6. STOP_SWEEP_DOWN.

---

### Signal Candidate

Описує торгову гіпотезу.

Сигнал ще не є рішенням.

Сигнал ще не є ордером.

---

### Filter Result

Перевіряє торгову гіпотезу.

Приклади:

1. spread filter;
2. market state filter;
3. session filter;
4. volatility filter;
5. risk filter.

---

### Trade Decision

Приймає рішення.

Можливі результати:

1. NO_TRADE;
2. WATCH;
3. APPROVE_BUY;
4. APPROVE_SELL;
5. CLOSE_POSITION;
6. MODIFY_POSITION;
7. EMERGENCY_CLOSE.

---

### Trade

Trade є бізнес-сутністю LGE.

Trade описує намір виконати торгову операцію.

Trade існує незалежно від брокера.

---

### OrderPlan

OrderPlan описує план виконання угоди.

OrderPlan ще не є broker order.

---

### Risk Manager

Перевіряє:

1. ризик;
2. ліміти;
3. рейки;
4. ліцензію;
5. execution mode.

---

### Execution Gateway

Перетворює OrderPlan у broker order.

---

### Position

Позиція виникає тільки після виконання broker order.

Position не дорівнює Trade.

---

### Position Control

Супровід відкритої позиції.

Приклади:

1. Break Even;
2. Trailing Stop;
3. Emergency Close;
4. Protection Rules.

---

### Result

Фінальний результат угоди.

Використовується для:

1. статистики;
2. аналітики;
3. журналу;
4. backtest;
5. навчання алгоритмів.

---

Головний принцип:

```text
Observation ≠ Signal

Signal ≠ Decision

Decision ≠ Trade

Trade ≠ OrderPlan

OrderPlan ≠ BrokerOrder

BrokerOrder ≠ Position
```

---

Кожний шар існує окремо.

Кожний шар має власну відповідальність.

Кожний шар повинен зберігатися в SQLite.

---

Саме ця схема є канонічною архітектурою LGE для:

1. Backtest;
2. Demo;
3. Live;
4. Manual;
5. Semi;
6. Auto.

---

# 90. Нотатки для майбутніх ревізій

---

Цей розділ не є частиною поточної реалізації RoadMap80.

Він містить архітектурні спостереження, отримані під час послідовних ітерацій аналізу документа.

---

## 90.1. Уніфікація канонічного ланцюга

У документі існує кілька близьких варіантів канонічного ланцюга проходження даних.

Під час наступних RoadMap необхідно привести їх до єдиного канону.

Поточний кандидат:

```text
Market Data
→ Market Structure
→ Market Context
→ Market Observation
→ Signal Candidate
→ Trade Decision
→ Trade
→ OrderPlan
→ Risk Manager
→ Execution Gateway
→ Broker Service
→ Broker Adapter
→ Broker Order
```

---

## 90.2. Розділення Market Context та Filters

Потрібно остаточно розвести поняття:

### Market Context

Описує середовище ринку.

Приклади:

1. LONDON;
2. NEW_YORK;
3. HIGH_VOLATILITY;
4. LOW_LIQUIDITY;
5. GAP_RISK.

---

### Filters

Приймають рішення про допуск або блокування торгової ідеї.

Приклади:

1. spread filter;
2. market state filter;
3. risk filter;
4. news filter.

---

Принцип:

```text
Context = опис середовища.

Filter = правило допуску.
```

---

## 90.3. Position Lifecycle

У документі вже існує Trade Lifecycle.

У майбутньому необхідно описати окремий життєвий цикл позиції.

Попередній варіант:

```text
OPEN
MODIFIED
PROTECTED
PARTIAL_CLOSED
CLOSED
EMERGENCY_CLOSED
```

---

## 90.4. Market Observation як окрема сутність

Одним із головних результатів розвитку архітектури стало розділення понять:

```text
MarketObservation
```

та

```text
SignalCandidate
```

---

Принцип:

```text
MarketObservation ≠ SignalCandidate
```

---

Observation описує факт.

Приклади:

1. NEW_HIGH;
2. NEW_LOW;
3. LEVEL_BREAKOUT;
4. FALSE_BREAKOUT;
5. IMPULSE_UP;
6. IMPULSE_DOWN.

---

SignalCandidate описує торгову гіпотезу.

Тільки після цього можливе створення:

```text
TradeDecision
→ Trade
→ OrderPlan
```

---

## 90.5. Найважливіший практичний пріоритет

Під час розвитку документа було зроблено висновок:

Перед створенням складних алгоритмів необхідно повністю завершити:

1. ручну торгівлю через cTrader;
2. ручну торгівлю через IB;
3. Position Control;
4. External Position Mode;
5. історію позицій;
6. журнал Trade та OrderPlan.

---

Після цього можливий перехід до:

1. Market Structure;
2. Market Observation;
3. Signal Layer;
4. Decision Layer;
5. Algorithm Framework.

---

Пріоритет:

```text
Реальна позиція
→ Контроль позиції
→ Аналіз ринку
→ Сигнали
→ Алгоритми
```

а не навпаки.

---

## 90.6. Метод послідовних ітерацій

Документ розвивається методом послідовних ітерацій.

Кожна нова ревізія повинна перевіряти:

1. суперечності;
2. дублювання;
3. відсутні сутності;
4. відсутні зв'язки;
5. проблеми масштабування;
6. проблеми майбутньої реалізації.

---

Мета кожної ітерації:

Не додавання нових можливостей, а спрощення та уточнення архітектури.

---

## 90.7. Trade та Position — різні сутності

---

Під час розвитку документа було встановлено важливе правило:

```text
Trade ≠ Position
```

---

Trade є бізнес-сутністю LGE.

Position є брокерською сутністю.

---

Один Trade може:

1. не створити Position;
2. створити одну Position;
3. створити декілька Position;
4. бути скасований до виконання;
5. бути відхилений брокером;
6. завершитися помилкою виконання.

---

Position існує тільки після виконання broker order.

---

Тому статистика, аналітика та журнал рішень повинні будуватись навколо:

```text
Trade
```

а не навколо:

```text
Position
```

---

## 90.8. Канонічне правило SQLite

---

SQLite є Source of Truth для LGE.

---

Принцип:

```text
Broker повідомляє факт.

SQLite зберігає факт.

LGE працює через факт.
```

---

Алгоритми не повинні напряму залежати від брокера.

---

У майбутньому повинно бути можливим:

```text
Backtest
Demo
Live
```

через однаковий набір SQLite-сутностей.

---

## 90.9. Спочатку модель даних, потім алгоритм

---

Під час розробки RoadMap80 встановлено правило:

Не можна створювати алгоритм, якщо для нього ще не існує канонічної моделі даних.

---

Правильний порядок:

```text
Market Model
→ Storage
→ Observation
→ Signal
→ Decision
→ Trade
→ OrderPlan
→ Algorithm
```

---

Неправильний порядок:

```text
Ідея алгоритму
→ Код алгоритму
→ Потім спроба придумати структури
```

---

Це призводить до складної та нестабільної архітектури.

---

## 90.10. Принцип брокерської незалежності

---

Будь-яка бізнес-логіка LGE повинна працювати через канонічні структури.

---

Алгоритм не повинен знати:

1. cTrader;
2. IB;
3. Demo;
4. Live.

---

Алгоритм повинен працювати тільки з:

```text
MarketSymbol
MarketTick
MarketCandle
MarketSnapshot

MarketStructure
MarketContext
MarketObservation

SignalCandidate
TradeDecision
Trade
OrderPlan
Position
```

---

Broker-specific логіка дозволена тільки в:

```text
Adapter Layer
Service Layer
```

---

Це дозволить додати:

1. Forex;
2. Stocks;
3. Futures;
4. Indices;
5. Crypto;

без зміни алгоритмів.

---

## 90.11. Невдала угода також є угодою

---

Trade Lifecycle не завершується тільки відкриттям Position.

Необхідно враховувати сценарії, коли broker order не був виконаний.

---

Приклади:

1. broker reject;
2. insufficient funds;
3. invalid quantity;
4. invalid stop loss;
5. invalid take profit;
6. market closed;
7. connection lost;
8. timeout.

---

Майбутні стани Trade:

```text
CREATED
OBSERVED
SIGNALLED
APPROVED
PLANNED

EXECUTED

REJECTED
FAILED
CANCELLED

MANAGED
CLOSED
```

---

Приклад:

```text
Trade
→ OrderPlan
→ BrokerOrder
→ REJECTED
→ Result
```

---

Навіть невдала угода повинна зберігатися у SQLite.

---

Невдала угода є важливою для:

1. статистики;
2. аналізу алгоритмів;
3. діагностики брокера;
4. контролю ризиків.

---

## 90.12. Пояснюваність рішень

---

У майбутньому кожна сутність аналізу повинна містити пояснення причин свого створення.

---

MarketObservation повинна відповідати на питання:

```text
Що сталося?
```

---

SignalCandidate повинна відповідати на питання:

```text
Чому це може бути торговою можливістю?
```

---

TradeDecision повинна відповідати на питання:

```text
Чому було прийняте саме це рішення?
```

---

OrderPlan повинен відповідати на питання:

```text
Чому вибрані саме ці параметри угоди?
```

---

У майбутньому бажано додати:

```text
reason
details
evidence
```

для всіх ключових сутностей.

---

Головна мета:

У будь-який момент користувач повинен мати можливість зрозуміти:

1. чому виник Observation;
2. чому створено SignalCandidate;
3. чому прийнято Decision;
4. чому створено OrderPlan.

---

## 90.13. External Position Manager

---

Однією з ключових особливостей LGE повинна стати робота із зовнішніми позиціями.

---

Позиція може бути створена:

1. через LGE;
2. через cTrader Desktop;
3. через cTrader Web;
4. через TWS;
5. через Mobile App;
6. іншими засобами брокера.

---

LGE повинен вміти:

1. виявляти такі позиції;
2. показувати їх користувачу;
3. вести статистику;
4. виконувати моніторинг;
5. за дозволом користувача брати їх під супровід.

---

Режими:

```text
IGNORE
MONITOR
TAKE_CONTROL
```

---

У майбутньому External Position Manager може існувати як окремий функціональний модуль системи.

---

## 90.14. Portfolio Layer

---

Після завершення Position Control необхідно створити Portfolio Layer.

---

Portfolio Layer працює над рівнем окремих позицій.

---

Приклади:

```text
EURUSD BUY
GBPUSD BUY
USDCHF SELL
XAUUSD BUY
```

---

Кожна позиція може бути коректною окремо.

Проте сумарний ризик портфеля може бути надмірним.

---

Portfolio Layer повинен контролювати:

1. сумарний ризик;
2. кореляцію інструментів;
3. концентрацію позицій;
4. exposure по валютах;
5. exposure по класах активів.

---

Portfolio Layer не входить у RoadMap80.

Його поява очікується після завершення:

1. Position Control;
2. Historical Storage;
3. Trade Statistics.

---

## 90.15. Position не повинна знати свій алгоритм

---

Position є торговим фактом.

Position не повинна містити логіку алгоритму.

---

Неправильно:

```text
Position
→ Trade
→ TradeDecision
→ SignalCandidate
→ MarketObservation
```

---

