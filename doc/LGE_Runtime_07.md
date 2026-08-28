# LGE Runtime 07 — RoadMap101–104

## MACD Quality, Alligator Regime та Candidate F

Дата початку: 2026-08-17  
Дата базового checkpoint: 2026-08-21  
Дата актуалізації: 2026-08-28

---

# 1. Призначення MD7

`LGE_Runtime_07.md` є канонічним high-level runtime checkpoint для RoadMap101.

RoadMap101 продовжив стабілізований Historical Replay після RoadMap100 і був
присвячений не механічному підбору PnL, а побудові причинно-часової логіки
MACD Quality + Alligator, яка:

```text
працює тільки на завершених strategy bars;
не використовує look-ahead;
має revisioned profile snapshot;
детерміновано відтворюється у Historical Replay;
пояснює ALLOW / REJECT / deferred lifecycle;
не залежить від broker execution.
```

Базове правило RoadMap101:

```text
measure
    -> change one controlled thing
    -> replay
    -> compare
    -> validate
    -> freeze candidate
```

PnL використовувався як secondary metric до моменту формування фінального
Candidate F.

---

# 2. Канонічна технічна база

RoadMap101 спирається на закриту технічну базу RoadMap100:

1. M1 historical CSV -> completed M15 strategy bars;
2. deterministic Historical Replay;
3. окремі `Крок` і `Тік`;
4. M1 execution chronology та Bid/Ask;
5. `NEXT_BAR_OPEN` execution;
6. chart navigation і signal/position cross-navigation;
7. `MAX FAST` із bounded adaptive batching;
8. virtual Replay order -> position -> close lifecycle;
9. profile revision snapshot для MACD та Alligator;
10. Replay leverage `1:500` для margin calculation;
11. broker execution у Historical Replay вимкнений.

Не повертатися до закритих RoadMap100 блоків без підтвердженого regression
defect.

---

# 3. Незмінні invariants RoadMap101

Для production і comparison Replay обов'язкові:

```text
no look-ahead
only completed strategy bars
M1 chronology after signal
signal_timestamp < entry_timestamp
NEXT_BAR_OPEN execution
deterministic Replay
Replay leverage = 1:500
broker_requests = 0
broker_execution_attempted = False
```

Volatility reference Candidate F використовує тільки попередні завершені M15
bars і не включає signal bar.

---

# 4. Time-series windows

Канонічний дослідний split RoadMap101:

## 4.1. Development

```text
2026-01-02 -> 2026-02-28
```

## 4.2. Validation

```text
2026-03-01 -> 2026-05-31
```

## 4.3. Holdout

```text
2026-06-01 -> 2026-08-11
```

Важливе уточнення фінального checkpoint: Validation і Holdout у ході
RoadMap101 багаторазово аналізувалися для структурних diagnostics. Тому після
формування Candidate F вони вже не вважаються повністю недоторканим фінальним
holdout. Для майбутньої незалежної оцінки потрібен новий часовий відрізок або
інший ще не аналізований dataset.

---

# 5. MACD Quality — production checkpoint

Після comparison `12/26/9`, `8/17/5`, `6/13/4` і подальшої time-series
перевірки канонічним MACD-профілем RoadMap101 став:

```text
Profile name       = Custom MACD FAST
Profile revision   = 7
Profile UID        = c498cd4c-12d2-4573-a96c-20a758d7e3fc
Periods            = 8 / 17 / 5
Price source       = Close
Fast MA            = EMA
Slow MA            = EMA
Signal MA          = EMA
Shift              = 0
Signal mode        = EXTENDED
Angle model        = ABC_REALTIME_SCALED
ABC minimum angle  = 2.25°
Legacy angle       = 45° separate / inactive in ABC mode
Prominence         = 0.000015
Distance           = 0.000050
```

Основою сигналу лишається реальний `MACD_CROSS`. Quality layer перевіряє
extremum/prominence/distance/ABC angle без підміни самого crossover.

Періоди й thresholds не трактуються як універсальні константи для всіх
інструментів, timeframe і market regimes.

---

# 6. Alligator regime model

Канонічний Alligator signal-timeframe baseline:

```text
source       = Median
Jaw          = 13, shift 8
Teeth        = 8, shift 5
Lips         = 5, shift 3
MA type      = SMOOTHED
mode         = SAME_TIMEFRAME
strategy TF  = M15
```

Regime model розрізняє:

```text
ALLIGATOR_REGIME_FLAT
ALLIGATOR_REGIME_TREND_UP
ALLIGATOR_REGIME_TREND_DOWN
```

Trend phase:

```text
ALLIGATOR_REGIME_PHASE_STARTING
ALLIGATOR_REGIME_PHASE_ACTIVE
ALLIGATOR_REGIME_PHASE_ENDING
ALLIGATOR_REGIME_PHASE_NONE
```

Канонічне правило trade gate:

```text
STARTING -> не відкривати позицію негайно
ACTIVE   -> допускається перевірка direction + Candidate F guards
ENDING   -> не відкривати нову позицію
FLAT     -> не відкривати нову позицію
```

Phase diagnostics використовують тільки поточний завершений bar і causal
history `t-2 / t-1 / t`.

---

# 7. Candidate F — production Alligator profile

RoadMap101 зафіксував окремий immutable built-in profile:

```text
Profile name     = LGE Candidate F Smoothed
Profile revision = 1
Profile UID      = 00000000-0000-5000-8000-000000000014
logic_mode       = CANDIDATE_F
```

Fresh workspace default не змінено: legacy `LGE Classic Smoothed` збережений.
Candidate F вибирається явно або через profile binding WSP.

## 7.1. Candidate F parameters

```text
trend_start_confirmation_bars = 4
deferred_expiry_bars           = 5
opening_collapse_threshold     = -0.700
volatility_lookback_bars       = 20

weak_max_active_age            = 2
weak_max_opening               = 0.500

spike_min_range_ratio          = 3.500
spike_max_opening_delta        = -0.500
spike_max_slope_delta          = -0.010

overextended_min_slope        = 0.200
overextended_min_opening      = 3.000
```

## 7.2. ARMED / deferred lifecycle

Якісний MACD signal не втрачається автоматично, якщо Alligator ще у
`STARTING` того самого напрямку.

```text
quality MACD CROSS
    -> SAME_DIRECTION + STARTING
    -> DEFERRED_ARMED
    -> перевірка наступних completed bars
    -> ACTIVE + SAME_DIRECTION + MACD relation still valid
    -> DEFERRED_RELEASE
    -> production NEXT_BAR_OPEN execution
```

Candidate скасовується, якщо до release відбулося одне з:

```text
opposite MACD CROSS
opposite ACTIVE Alligator
MACD relation invalid
TTL expired
```

Один вихідний MACD signal може породити максимум один deferred lifecycle.
Deferred release проходить ті самі downstream Candidate F guards, що й
звичайний MACD CROSS.

## 7.3. Candidate F structural guards

### Opening collapse

```text
normalized_opening(t) - normalized_opening(t-2) < -0.700
    -> REJECT
```

Guard ловить формально ACTIVE trend, у якого Alligator уже швидко
закривається.

### Weak opening / too early ACTIVE

```text
active_age <= 2
AND normalized_opening < 0.500
    -> REJECT
```

Guard відсікає формальний ранній ACTIVE, коли Alligator ще недостатньо
розкритий.

### Volatility spike with deterioration

```text
range_ratio >= 3.500
AND (
    opening_delta < -0.500
    OR slope_delta < -0.010
)
    -> REJECT
```

`range_ratio` порівнює signal-bar range із середнім range попередніх 20
завершених M15 bars.

### Overextended trend

```text
normalized_slope >= 0.200
AND normalized_opening >= 3.000
    -> REJECT
```

Guard відсікає надмірно розігнаний / розкритий trend state.

---

# 8. Canonical reason codes

Candidate F робить рішення видимим у Signals tooltip і Journal detail.
Ключові production reason codes:

```text
ALLIGATOR_DEFERRED_ARMED
ALLIGATOR_DEFERRED_RELEASE
ALLIGATOR_OPENING_COLLAPSE_REJECT
ALLIGATOR_WEAK_OPENING_REJECT
ALLIGATOR_VOLATILITY_SPIKE_DETERIORATION_REJECT
ALLIGATOR_OVEREXTENDED_TREND_REJECT
```

Також збережені канонічні SAME_TIMEFRAME allow/reject reason codes для
напрямку, STARTING, ENDING, FLAT та opposite/neutral cases.

Технічні reason codes не перекладаються; user-facing reason text
локалізується.

---

# 9. Candidate F production parity

Candidate F був спочатку сформований як test-only controlled candidate, після
чого перенесений у production algorithm без зміни очікуваного Replay result.

Порівняння з поточним до Candidate F 3-bar gate:

```text
Current 3-bar:
trades = 40
wins   = 20
losses = 20
SL     = 7
PnL    = -8.96 USD

Candidate F:
trades = 30
wins   = 20
losses = 10
SL     = 2
PnL    = +0.14 USD
```

Candidate F у дослідному split зберіг усі 20 winners і прибрав 10 losers,
включно з 5 STOP_LOSS. Це є факт цього dataset, а не гарантія майбутньої
прибутковості.

## 9.1. Development

```text
trades = 7
wins / losses = 6 / 1
SL / PD / TP = 0 / 7 / 0
PnL = +1.06 USD
Max DD = 0.17 USD
PF = 7.2353
```

## 9.2. Validation

```text
trades = 16
wins / losses = 10 / 6
SL / PD / TP = 2 / 14 / 0
PnL = -1.03 USD
Max DD = 3.24 USD
PF = 0.8049
```

## 9.3. Holdout

```text
trades = 7
wins / losses = 4 / 3
SL / PD / TP = 0 / 7 / 0
PnL = +0.11 USD
Max DD = 0.08 USD
PF = 1.6875
```

Aggregate:

```text
trades = 30
wins / losses = 20 / 10
SL = 2
sum PnL = +0.14 USD
```

Production parity test підтвердив:

```text
candidate_matches_green_37=True
profile_snapshot_contains_candidate_thresholds=True
candidate_uses_completed_bars_only=True
volatility_reference_excludes_signal_bar=True
no_look_ahead=True
broker_execution_attempted=False
ALGORITHM_WORKSPACE_ALLIGATOR_CANDIDATE_F_PRODUCTION_CHECK=OK
```

---

# 10. Manual LGE acceptance

Production Candidate F перевірений не тільки synthetic/runtime tests, а й
реальним Historical Replay через LGE із профілями:

```text
MACD      = Custom MACD FAST r7
Alligator = LGE Candidate F Smoothed r1
EURUSD M15
M1 CSV
spread = 0.00012
initial balance = 1000 USD
AUTO
MAX FAST
```

Manual LGE Replay збігся з production parity:

```text
Development = 7 trades / 6W / 1L / 0 SL / +1.06
Validation  = 16 trades / 10W / 6L / 2 SL / -1.03
Holdout     = 7 trades / 4W / 3L / 0 SL / +0.11
```

Ключові manual control points:

```text
2026-04-02 06:00 SELL
    -> ALLIGATOR_OVEREXTENDED_TREND_REJECT

2026-04-21 19:30 SELL
    -> SAME_TIMEFRAME SELL ALLOW
    -> NEXT_BAR_OPEN
    -> STOP_LOSS -3.10

2026-06-18 06:15 BUY
    -> ALLIGATOR_WEAK_OPENING_REJECT

2026-06-26 12:45 BUY
    -> ALLIGATOR_VOLATILITY_SPIKE_DETERIORATION_REJECT

2026-07-31 13:30 SELL
    -> ALLIGATOR_OPENING_COLLAPSE_REJECT
```

`2026-04-21 19:30 SELL -> STOP_LOSS -3.10` свідомо залишено як benchmark
невідворотного/непоясненого loss. SAME_TIMEFRAME і HIGHER_1 формально
підтверджували SELL. Impulse diagnostics не дали достатньо чистої ознаки для
окремого production filter без втрати winners. Не підганяти поточні guards
під цей один випадок. У майбутньому benchmark може використовуватися для
нового фільтра або окремої гіпотези reverse/counter-trend signal.

---

# 11. Signals / Journal / UI observability

RoadMap101 закрив також observability для ручного algorithm analysis:

1. Signals table показує regime, phase, timeframe/mode, profile revision,
   result і reason;
2. таблиця має горизонтальний scroll і читабельні interactive widths;
3. ручні ширини колонок зберігаються після restart для WSP Signals,
   Positions, Orders та головної OrdersPage positions table;
4. Signals tooltip показує localized reason + technical diagnostic detail;
5. Journal для signal records показує той самий читабельний structured detail,
   а raw technical content лишається доступним;
6. signal -> position / chart / journal navigation збережена;
7. chart target crosshair і hint auto-hide збережені;
8. зміни UI не змінюють trade gate або broker execution.

Виявлений UX carry-over для RoadMap102:

```text
Parameters WSP -> "Дані та Replay"
Parameters WSP -> "Алгоритм"
```

Ці групи зараз можуть показувати порожню праву панель із текстом, що параметри
не визначені. Runtime не порушений, але UI треба зробити змістовним: або
показувати релевантні parameters/action, або не показувати порожню group.

---

# 12. Profile / revision invariants

Канонічна profile model після RoadMap101:

```text
built-in templates are immutable
user profiles are editable through revisions
archive does not physically delete historical profile state
WSP stores profile UID + revision snapshot
profile edit does not mutate old Replay snapshot
legacy Alligator profile is preserved
fresh workspace default is unchanged
Candidate F is explicitly selectable
```

Candidate F duplicate/edit revision UI acceptance:

```text
candidate_f_duplicate_editable=True
jaw_revision_incremented=True
candidate_logic_mode_preserved=True
candidate_threshold_snapshot_preserved=True
broker_execution_attempted=False
WORKSPACE_INDICATOR_PROFILE_CANDIDATE_F_REVISION_UI_CHECK=OK
```

---

# 13. Final regression RoadMap101

Фінальний regression після production Candidate F:

```text
candidate_f_production=True
candidate_f_profile_revision_ui=True
alligator_same_timeframe=True
signal_localization=True
signal_table=True
signal_analysis_navigation=True
table_column_width_persistence=True
candidate_f_matches_green_37=True
legacy_profile_preserved=True
fresh_workspace_default_unchanged=True
completed_bars_only=True
no_look_ahead=True
signal_reason_localization_preserved=True
journal_readable_detail_preserved=True
table_width_persistence_preserved=True
broker_execution_attempted=False
ROADMAP101_CANDIDATE_F_FINAL_REGRESSION_CHECK=OK
```

Статус:

```text
RoadMap101 = CLOSED / GREEN
```

---

# 14. Що RoadMap101 свідомо не доводить

Candidate F не є доказом універсальної прибутковості.

RoadMap101 не робить висновку, що зафіксовані thresholds універсальні для:

```text
інших symbols
інших timeframes
інших volatility regimes
Paper / Live execution
майбутніх невідомих даних
```

Також не виконувалась спроба довести кількість SL до нуля. Частина loss є
нормальною невідворотною властивістю trading system.

Не вводити новий filter лише тому, що він пояснює один відомий loss.

---

# 15. Boundary для RoadMap102

RoadMap102 починається вже від GREEN production Candidate F.

Перші carry-over напрями:

```text
1. привести Parameters WSP "Дані та Replay" / "Алгоритм" до змістовного UX;
2. не ламати Candidate F та його reason-code observability;
3. перевіряти Candidate F на нових, ще не використаних даних;
4. не підбирати thresholds повторно по вже вивчених Validation/Holdout;
5. окремо досліджувати benchmark 2026-04-21 19:30 SELL тільки через нову
   обґрунтовану hypothesis, а не через ad-hoc threshold;
6. майбутні alternative signal/filter sources додавати по одному;
7. Stochastic та Canonical Donchian лишаються окремими кандидатами для
   подальших експериментів, не частиною Candidate F.
```

Канонічний production checkpoint для переходу:

```text
MACD = Custom MACD FAST r7, 8/17/5, EXTENDED,
       prominence 0.000015, distance 0.000050,
       ABC_REALTIME_SCALED 2.25°

Alligator = LGE Candidate F Smoothed r1,
            SAME_TIMEFRAME,
            13/8, 8/5, 5/3,
            SMOOTHED MEDIAN,
            Candidate F logic enabled

Historical Replay invariants = completed bars / no-look-ahead /
                               deterministic / broker execution disabled
```

---

# 16. RoadMap102 — production stabilization Candidate F

RoadMap102 не змінював production signal gate Candidate F без окремої
перевірки. Основний результат етапу — стабілізація WSP/Replay observability та
перенесення перевіреної exit-recovery policy у production Runtime.

Канонічні runtime/UI invariants, підтверджені RoadMap102:

```text
Parameters WSP = змістовні групи Data & Replay / Algorithm / Execution / Diagnostics
Historical Replay timing = monotonic start/finish/elapsed, local UI + UTC data chronology
MDI/WSP restore = STOPPED після restore, без automatic start
Replay execution = deterministic, NEXT_BAR_OPEN, broker execution disabled
Candidate F signal pipeline = preserved
```

Production Candidate F після RoadMap102 використовує ті самі signal-side
профілі, зафіксовані RoadMap101:

```text
MACD = Custom MACD FAST r7, 8/17/5, EXTENDED,
       prominence 0.000015, distance 0.000050,
       ABC_REALTIME_SCALED 2.25°

Alligator = LGE Candidate F Smoothed r1,
            SAME_TIMEFRAME
```

---

# 17. Candidate F negative-PD recovery — production 6K

RoadMap102 / 6K переносить у production лише перевірену exit state-machine для
negative `PROFIT_DRAWDOWN`. Positive profit drawdown, як і раніше, закривається
негайно.

Канонічна policy:

```text
production_policy = NEGATIVE_PD_3_M1_RECOVERY_WITH_M2_ABORT

negative PROFIT_DRAWDOWN
    -> RECOVERY_PENDING

M1: PnL >= 0
    -> RECOVERY CLOSE

M2: PnL >= 0
    -> RECOVERY CLOSE

M1 step <= 0 AND M2 step <= 0
    -> EARLY ABORT CLOSE

M3: PnL >= 0
    -> RECOVERY CLOSE

otherwise after M3
    -> TIMEOUT CLOSE
```

Policy активується тільки для валідованого production context:

```text
Candidate F
Alligator confirmation = SAME_TIMEFRAME
strategy timeframe = M15
data mode = Historical Replay
execution source timeframe = M1
```

Не поширювати цю policy автоматично на:

```text
Paper
Live
інші strategy timeframes
інші execution source timeframes
інші Alligator logic/profile modes
```

Для такого Runtime у Journal обов'язково фіксується activation event:

```text
CANDIDATE_F_NEGATIVE_PD_RECOVERY_ACTIVE
```

Frozen pre-6J research baseline ізольований окремо і не повинен змінюватися:

```text
trades = 59
wins / losses / break-even = 31 / 27 / 1
net = -5.90 USD
profit factor = 0.6895
maximum drawdown = 6.90 USD
```

Production 6K regression:

```text
trades = 59
wins / losses / break-even = 40 / 18 / 1
net = -4.05 USD
profit factor = 0.7808
maximum drawdown = 5.80 USD

recovery_pending:
    started = 18
    recovery = 9
    early_abort = 5
    timeout = 4

broker_requests = 0
broker_execution_attempted = False
```

Контрольний regression:

```text
ALGORITHM_WORKSPACE_CANDIDATE_F_PRODUCTION_EXIT_RECOVERY_2025_CHECK=OK
```

---

# 18. Manual LGE acceptance production 6K

23.08.2026 production 6K перевірений через реальний LGE Historical Replay, а
не тільки через test runner.

Replay context:

```text
dataset = 2025-01-01_2026-08-21_CTRADER_EURUSD_M1.csv
requested end = 2025-12-31 23:59 UTC
actual period = 2025-01-01 22:01 UTC -> 2025-12-31 21:58 UTC
strategy timeframe = M15
source timeframe = M1
spread = 0.00012
initial balance = 1000.00 USD
Replay leverage = 1:500
AUTO / MAX FAST
```

GUI Journal підтвердив production activation event:

```text
CANDIDATE_F_NEGATIVE_PD_RECOVERY_ACTIVE
```

Historical Replay Summary збігся з production 6K regression:

```text
bars / skipped / gaps = 23753 / 236564 / 2403
trades = 59
wins = 40
losses = 18
win rate = 67.8%
net PnL = -4.05 USD
final balance = 995.95 USD
profit factor = 0.78
maximum drawdown = 5.80 USD / 0.58%
average trade = -0.07 USD

STOP_LOSS = 9
TAKE_PROFIT = 2
PROFIT_DRAWDOWN = 48
SESSION_END = 0

MACD signals = 3042
MACD Quality pass / reject = 414 / 2626
Alligator allow / reject = 59 / 357
```

Внутрішні recovery counters не зобов'язані показуватися у GUI Summary; їх
канонічно фіксує production regression test. GUI acceptance перевіряє
activation event, повне завершення Replay без Runtime error та збіг фінальних
торгових метрик.

Статус:

```text
RoadMap102 / 6K = CLOSED / GREEN
Candidate F production exit baseline = -4.05 / PF 0.7808 / DD 5.80
```

---

# 19. Boundary для RoadMap103 / 7A

Після GREEN production 6K exit recovery вважається зафіксованою production
базою і не повинна змінюватися під час наступного дослідження Stop-Loss.

RoadMap103 починається з:

```text
7A — Stop-Loss Anatomy
```

Правила розділення змін:

```text
1. не підкручувати 6K recovery policy паралельно зі Stop-Loss research;
2. будь-яку SL hypothesis перевіряти від production baseline -4.05 / 0.7808 / 5.80;
3. frozen pre-6J baseline -5.90 / 0.6895 / 6.90 лишається research reference;
4. signal gate Candidate F не змінювати без окремої hypothesis та regression;
5. Live/Paper або інші timeframe не успадковують 6K policy без окремої validation.
```

---

# 20. RoadMap103 — Stop-Loss / Structural SL/TP checkpoint

RoadMap103 не змінював production 6K exit policy. Дослідження SL/TP виконувалося
як causal paired diagnostic на тих самих production entries.

## 20.1. Stop-Loss anatomy

Production baseline 2025:

```text
trades = 59
wins / losses / break-even = 40 / 18 / 1
net = -4.05 USD
PF = 0.7808
DD = 5.80 USD
STOP_LOSS = 9
```

Для STOP_LOSS trades зафіксовано:

```text
stop distance: min 12.0, median 15.4, max 37.0 pip
initial risk: min 1.20, median 1.54, max 3.70 USD
next-bar adverse gap: min +0.005R, median +0.053R, max +0.075R
```

One-bar impulse gate був сильним diagnostic у 2025, але cross-period показав,
що його не можна переносити в production як універсальний entry gate.

## 20.2. Structural support/resistance geometry

Досліджено causal support/resistance zones тільки з завершених M15 bars.
Фінальна bounded geometry RoadMap103 / 8A:

```text
SL fallback = 12 pip
SL structural window = 12..24 pip
structure buffer = 1 pip
TP fallback = 2R
TP minimum = 24 pip
TP structural target = nearest valid zone від max(24 pip, 1R) до 2R
TP trailing = False
broken TP zone -> automatic re-entry = False
continuation -> only by a new signal
future bars for level definition = False
```

Cross-period paired diagnostic:

```text
2025 BASELINE          net -4.05  PF 0.7808  DD 5.80
2025 FIXED_12_2R       net -0.26  PF 0.9826  DD 4.82
2025 ZONE_SL_2R        net -1.17  PF 0.9297  DD 5.50
2025 FINAL_ZONE_SL_TP  net -1.80  PF 0.8919  DD 5.50

2026 BASELINE          net +1.37  PF 1.2518  DD 3.53
2026 FIXED_12_2R       net +1.68  PF 1.2833  DD 2.88
2026 ZONE_SL_2R        net +2.43  PF 1.4691  DD 2.88
2026 FINAL_ZONE_SL_TP  net +2.43  PF 1.4691  DD 2.88
```

Висновок: structural SL має перспективу, але фінальний SL/TP policy у production
не зафіксовано. Structural TP не показав стабільної додаткової переваги.
Поточний стан — research candidate, не production contract.

---

# 21. RoadMap104 — ранній Alligator opening та exit/re-entry research

## 21.1. GREEN entry baseline 8C.1

`FIRST_EXPANSION_FROM_CANONICAL_COMPRESSED_MOUTH` прийнято як сильний test-only
entry baseline. Використовується існуючий поріг `normalized_opening <= 0.600`,
без нового numeric tuning.

```text
2025 STARTING reference: 88 trades, net -19.20, PF 0.7500, DD 30.00
2025 OPENING EXPANSION: 122 trades, net +8.40, PF 1.0886, DD 14.40
median lead до formal STARTING = 2 M15 bars

2026 STARTING reference: 79 trades, net -19.20, PF 0.7241, DD 22.80
2026 OPENING EXPANSION: 90 trades, net +26.67, PF 1.4293, DD 15.60
median lead до formal STARTING = 3 M15 bars
```

Simple opposite MACD cross як exit відхилено: у 2026 він погіршив результат до
`net -17.70`. Entry pipeline 8C.1 лишається frozen під час exit research.

## 21.2. Exit і Donchian

Ранні MACD contraction/slope reversal events самі по собі виявилися надто
частими і як direct exit погіршували baseline. Alligator state у момент раннього
MACD reversal не дав чистого structural discriminator.

Donchian використовується causal:

```text
period = 20 reference only
shift = 0
channel = previous completed M15 bars
current bar excluded from channel reference
no look-ahead
```

Donchian midline як прямий exit нестабільний. Opposite boundary break був
кращим structural event, але не перевершив frozen SL/TP baseline в обох
періодах. TP release після favorable breakout дав покращення у 2025, але
сильне погіршення у 2026, тому universal TP-release policy відхилено.

Post-TP Donchian re-entry і pullback/re-breakout без додаткового momentum
filter також нестабільні між періодами.

## 21.3. Relative MACD restart і identity blocker

`dominant acceleration` diagnostic:

```text
signal momentum favorable
AND signal_hist_delta > abs(signal_hist)
```

дав позитивний incremental result у 2025 і 2026, але sample малий.
T104-13 виявив causal identity collisions у first-leg, re-entry і selected
re-entry inventory. До production/re-entry висновків ці collisions мають бути
усунені або канонічно нормалізовані; diagnostic collapse не є execution policy.

## 21.4. Alligator forward displacement projection

Forward shifted Alligator lines — це не price forecast. Це відома display
geometry, яку можна обчислити causal без future market data.

```text
maximum causal projection horizon = 3 M15 bars
2025 H1 candidate precision = 0.8765, coverage = 0.8320
2026 H1 candidate precision = 0.8766, coverage = 0.8420
median lead = 1 M15 bar
```

Projected H1 лишається diagnostic / early-warning source, не самостійним entry
permission.

---

# 22. Manual indicator screening — TradingView reference

Manual screening на EURUSD M15 виконується як visual hypothesis generation,
а не як доказ performance. Community scripts не є runtime dependency LGE;
формули для LGE мають реалізовуватися й тестуватися незалежно.

| Indicator | Reference | Поточна оцінка / роль |
| --- | --- | --- |
| BBW | 20, Close, 2 | дуже перспективний `compression -> expansion`, FLAT -> START |
| CHOP | 14 | regime guard: chop/flat vs directional trend |
| AC | Bill Williams 34/5/5 reference | acceleration/deceleration momentum, START/EXIT warning |
| Stochastic | 14/1/3 | pullback completion, second-leg / re-entry candidate |
| DMI/ADX | 14/14 | strength/direction guard для вже сформованого trend |
| Aroon | 14 | шумний на M15; не priority |
| Ichimoku | 9/26/52/26 | regime/support-resistance reference; не current priority |

Поточний short list для quantitative research:

```text
BBW         -> compression / expansion
AC          -> acceleration / deceleration
Stochastic  -> pullback completion
DMI/ADX     -> trend strength guard, якщо буде потрібен після основних tests
```

---

# 23. Boundary / порядок продовження RoadMap104

Перед новим SL/TP-indicator screening завершити незакриті quantitative роботи
і не змішувати одночасно entry, exit, re-entry та protection policy.

Канонічний порядок:

```text
1. causal identity collisions — окремо закрити regression/normalization;
2. BBW compression -> expansion quantitative anatomy;
3. AC acceleration/deceleration quantitative anatomy;
4. Stochastic pullback-completion quantitative anatomy;
5. лише після цього повернутися до SL/TP visual screening;
6. кожний перспективний SL/TP indicator перевіряти окремим causal runner;
7. production змінювати тільки після cross-period validation і regression.
```

Для SL/TP visual screening першочергові кандидати:

```text
confirmed swing / fractal levels -> local support/resistance
Pivot Points Standard            -> higher-level session/day S/R
ATR                              -> distance/buffer, не price level
Supertrend                       -> dynamic stop / trailing-exit reference
Donchian                         -> already researched structural boundary reference
```

`Zig Zag` не використовувати як causal SL/TP source без окремої confirmed-pivot
семантики через ризик repaint/look-ahead. Volume Profile відкласти: він більше
залежить від feed/session semantics і не є першим кандидатом для canonical LGE.

RoadMap104 лишається active research. Жоден із BBW / AC / Stochastic / DMI/ADX
поки не перенесений у production logic.

