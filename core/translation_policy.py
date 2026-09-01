# core/translation_policy.py — локалізаційна політика LGE
# -*- coding: utf-8 -*-
"""Центральна політика перекладу, hints і точні override LGE.

Модуль задає контексти автоматичної локалізації та точні переклади критичних
UI-термінів без ручного редагування ``lang/strings.json``. RoadMap99_04C
додає українські Signal/Entry diagnostics у Positions, а RoadMap99_04F —
явний статус вибраного indicator profile та pending Save. RoadMap99_04G
прибирає малопомітну галочку й підсилює selected-state. RoadMap100 додає
локалізовану кнопку ``Тік`` для найдрібнішої execution-події Replay; технічні
identifiers і reason codes залишаються незмінними. RoadMap101 уточнює назву
revision-save для indicator profile без прямого редагування
``strings_fallback.json``: canonical override лишається тут. RoadMap101 також
фіксує українські назви Alligator regime diagnostics для Signals.
"""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping

from core.translation_format import restore_format_placeholders

# Default context for short desktop UI strings outside a specialized domain.
DEFAULT_TRANSLATION_CONTEXT = (
    "Translate a concise label for the LGE desktop application. Preserve "
    "product names, abbreviations, placeholders and technical identifiers."
)

# Domain context is selected by the longest matching translation-key prefix.
TRANSLATION_CONTEXTS_BY_PREFIX: tuple[tuple[str, str], ...] = (
    (
        "AlgorithmWorkspace",
        "The text belongs to an algorithmic-trading workspace in a desktop "
        "application. It concerns charts, historical Replay, market data, "
        "orders, positions, runtime states, indicators, risk controls and "
        "algorithm parameters. Translate it as a concise professional UI "
        "label, not as general prose.",
    ),
    (
        "OrdersPage",
        "The text belongs to a broker orders and positions screen in a "
        "desktop trading application. It concerns order actions, stop loss, "
        "take profit, profit and broker reconciliation.",
    ),
    (
        "SettingsPageTranslator",
        "The text belongs to translation-provider settings in a desktop "
        "application. Preserve provider names, language codes and API terms.",
    ),
)

# Central preferred terminology. These terms are appended to DeepL context;
# they are not a remote DeepL glossary resource and require no glossary ID.
LGE_TRANSLATION_GLOSSARY: Mapping[str, Mapping[str, str]] = {
    "uk": {
        "workspace": "робочий простір",
        "Replay": "Replay",
        "runtime": "середовище виконання",
        "timeframe": "таймфрейм",
        "bar": "бар",
        "warm-up": "прогрів",
        "spread": "спред",
        "drawdown": "відкат",
        "stop loss": "стоп-лосс",
        "take profit": "тейк-профіт",
        "disabled": "вимкнено",
    },
    "pl": {
        "workspace": "obszar roboczy",
        "Replay": "Replay",
        "runtime": "środowisko wykonawcze",
        "timeframe": "interwał",
        "bar": "bar",
        "warm-up": "rozgrzewka",
        "spread": "spread",
        "drawdown": "obsunięcie",
        "order": "zlecenie",
        "position": "pozycja",
        "stop loss": "stop loss",
        "take profit": "take profit",
        "disabled": "wyłączone",
    },
}

# Rare exact translations for strings whose meaning is too ambiguous for a
# short isolated machine-translation request. UI modules still call only
# LangManager.tr(key, fallback); the policy is applied centrally.
CENTRAL_TRANSLATION_OVERRIDES: Mapping[str, Mapping[str, str]] = {
    "CommonConfirmDialog.btnYes": {
        "uk": "Так",
        "pl": "Tak",
        "de": "Ja",
        "fr": "Oui",
    },
    "CommonConfirmDialog.btnNo": {
        "uk": "Ні",
        "pl": "Nie",
        "de": "Nein",
        "fr": "Non",
    },
    "AlgorithmWorkspaceWindow.replaySyntheticAccount": {
        "uk": "Віртуальний рахунок Replay",
    },
    "AlgorithmWorkspaceWindow.replayAccountTooltip": {
        "uk": (
            "Цей віртуальний рахунок існує лише всередині Replay і не "
            "пов’язаний з IB або cTrader."
        ),
    },
    "AlgorithmWorkspaceWindow.lblReplayEquity": {
        "uk": "Кошти Replay:",
    },
    "AlgorithmWorkspaceWindow.lblReplayRealizedPnl": {
        "uk": "Закритий PnL:",
    },
    "AlgorithmWorkspaceWindow.lblReplayBalance": {
        "uk": "Баланс Replay:",
    },
    "AlgorithmWorkspaceWindow.lblReplaySummaryEquity": {
        "uk": "Кошти Replay:",
    },
    "AlgorithmWorkspaceHistoricalSummaryDialog.windowTitle": {
        "uk": "Підсумок Historical Replay",
        "de": "Zusammenfassung Historical Replay",
        "fr": "Résumé Historical Replay",
    },
    "AlgorithmWorkspaceHistoricalSummaryDialog.title": {
        "uk": (
            "Historical Replay завершено. Наведені значення зафіксовані "
            "для цього прогону."
        ),
        "de": (
            "Historical Replay ist abgeschlossen. Die Werte sind für "
            "diesen Lauf festgeschrieben."
        ),
        "fr": (
            "Historical Replay est terminé. Les valeurs sont figées pour "
            "cette exécution."
        ),
    },
    "AlgorithmWorkspaceHistoricalSummaryDialog.grpData": {
        "uk": "Дані",
        "de": "Daten",
        "fr": "Données",
    },
    "AlgorithmWorkspaceHistoricalSummaryDialog.symbol": {
        "uk": "Символ:",
        "de": "Symbol:",
        "fr": "Symbole :",
    },
    "AlgorithmWorkspaceHistoricalSummaryDialog.timeframe": {
        "uk": "Таймфрейм алгоритму:",
        "de": "Strategie-Zeitrahmen:",
        "fr": "Unité de temps de la stratégie :",
    },
    "AlgorithmWorkspaceHistoricalSummaryDialog.sourceTimeframe": {
        "uk": "Таймфрейм джерела:",
        "de": "Quell-Zeitrahmen:",
        "fr": "Unité de temps source :",
    },
    "AlgorithmWorkspaceHistoricalSummaryDialog.csvSelectionTime": {
        "uk": "Час вибірки CSV:",
        "de": "CSV-Auswahlzeit:",
        "fr": "Temps de sélection CSV :",
    },
    "AlgorithmWorkspaceHistoricalSummaryDialog.replayTime": {
        "uk": "Час прогону Replay:",
        "de": "Replay-Laufzeit:",
        "fr": "Durée du Replay :",
    },
    "AlgorithmWorkspaceHistoricalSummaryDialog.period": {
        "uk": "Період:",
        "de": "Zeitraum:",
        "fr": "Période :",
    },
    "AlgorithmWorkspaceHistoricalSummaryDialog.bars": {
        "uk": "Бари / пропущено / розриви:",
        "de": "Bars / übersprungen / Lücken:",
        "fr": "Barres / ignorées / écarts :",
    },
    "AlgorithmWorkspaceHistoricalSummaryDialog.spread": {
        "uk": "Спред:",
        "de": "Spread:",
        "fr": "Spread :",
    },
    "AlgorithmWorkspaceHistoricalSummaryDialog.grpResult": {
        "uk": "Результат торгівлі",
        "de": "Handelsergebnis",
        "fr": "Résultat de trading",
    },
    "AlgorithmWorkspaceHistoricalSummaryDialog.initialBalance": {
        "uk": "Початковий баланс:",
        "de": "Anfangssaldo:",
        "fr": "Solde initial :",
    },
    "AlgorithmWorkspaceHistoricalSummaryDialog.finalBalance": {
        "uk": "Кінцевий баланс:",
        "de": "Endsaldo:",
        "fr": "Solde final :",
    },
    "AlgorithmWorkspaceHistoricalSummaryDialog.netPnl": {
        "uk": "Чистий PnL:",
        "de": "Netto-PnL:",
        "fr": "PnL net :",
    },
    "AlgorithmWorkspaceHistoricalSummaryDialog.profitFactor": {
        "uk": "Profit factor:",
        "de": "Profit-Faktor:",
        "fr": "Facteur de profit :",
    },
    "AlgorithmWorkspaceHistoricalSummaryDialog.trades": {
        "uk": "Угоди:",
        "de": "Trades:",
        "fr": "Trades :",
    },
    "AlgorithmWorkspaceHistoricalSummaryDialog.winRate": {
        "uk": "Win rate:",
        "de": "Trefferquote:",
        "fr": "Taux de réussite :",
    },
    "AlgorithmWorkspaceHistoricalSummaryDialog.winners": {
        "uk": "Прибуткові:",
        "de": "Gewinner:",
        "fr": "Gagnants :",
    },
    "AlgorithmWorkspaceHistoricalSummaryDialog.losers": {
        "uk": "Збиткові:",
        "de": "Verlierer:",
        "fr": "Perdants :",
    },
    "AlgorithmWorkspaceHistoricalSummaryDialog.breakEven": {
        "uk": "Беззбиткові:",
        "pl": "Break-even:",
        "de": "Break-even:",
        "fr": "À l’équilibre :",
    },
    "AlgorithmWorkspaceHistoricalSummaryDialog.maxDrawdown": {
        "uk": "Макс. просадка:",
        "de": "Max. Drawdown:",
        "fr": "Drawdown max. :",
    },
    "AlgorithmWorkspaceHistoricalSummaryDialog.averageTrade": {
        "uk": "Середня угода:",
        "de": "Durchschnittstrade:",
        "fr": "Trade moyen :",
    },
    "AlgorithmWorkspaceHistoricalSummaryDialog.macdQuality": {
        "uk": "MACD Quality — прийнято / відхилено:",
        "pl": "MACD Quality — przyjęto / odrzucono:",
    },
    "AlgorithmWorkspaceHistoricalSummaryDialog.macdQualityRejects": {
        "uk": "Відмови N / W / D / F:",
        "pl": "Odrzucenia N / W / D / F:",
    },
    "AlgorithmWorkspaceHistoricalSummaryDialog.grpSignals": {
        "uk": "Сигнали",
        "de": "Signale",
        "fr": "Signaux",
    },
    "AlgorithmWorkspaceHistoricalSummaryDialog.signals": {
        "uk": "Сигнали MACD:",
        "de": "MACD-Signale:",
        "fr": "Signaux MACD :",
    },
    "AlgorithmWorkspaceHistoricalSummaryDialog.directions": {
        "uk": "BUY / SELL:",
        "de": "BUY / SELL:",
        "fr": "BUY / SELL :",
    },
    "AlgorithmWorkspaceHistoricalSummaryDialog.alligator": {
        "uk": "Alligator — дозволено / відхилено:",
        "de": "Alligator — erlaubt / abgelehnt:",
        "fr": "Alligator — autorisés / rejetés :",
    },
    "AlgorithmWorkspaceHistoricalSummaryDialog.rejects": {
        "uk": "Відмови — прогрів / ризик:",
        "de": "Ablehnungen — Aufwärmen / Risiko:",
        "fr": "Rejets — préchauffage / risque :",
    },
    "AlgorithmWorkspaceHistoricalSummaryDialog.grpExits": {
        "uk": "Причини закриття",
        "de": "Schließgründe",
        "fr": "Raisons de clôture",
    },
    "AlgorithmWorkspaceHistoricalSummaryDialog.stopLoss": {
        "uk": "Стоп-лос:",
        "de": "Stop-Loss:",
        "fr": "Stop loss :",
    },
    "AlgorithmWorkspaceHistoricalSummaryDialog.takeProfit": {
        "uk": "Тейк-профіт:",
        "de": "Take-Profit:",
        "fr": "Take profit :",
    },
    "AlgorithmWorkspaceHistoricalSummaryDialog.profitDrawdown": {
        "uk": "Закриття за відкатом прибутку:",
        "de": "Gewinnrückgang:",
        "fr": "Repli du profit :",
    },
    "AlgorithmWorkspaceHistoricalSummaryDialog.sessionEnd": {
        "uk": "Закриття в кінці Replay:",
        "de": "Replay-Ende:",
        "fr": "Fin du Replay :",
    },
    "AlgorithmWorkspaceHistoricalSummaryDialog.other": {
        "uk": "Інші:",
        "de": "Andere:",
        "fr": "Autres :",
    },
    "AlgorithmWorkspaceHistoricalSummaryDialog.btnClose": {
        "uk": "Закрити",
        "de": "Schließen",
        "fr": "Fermer",
    },
    "AlgorithmWorkspaceReplayDialog.grpAccount": {
        "uk": "Віртуальний рахунок Replay",
    },
    "AlgorithmWorkspaceReplayDialog.lblInitialBalance": {
        "uk": "Початковий баланс Replay, USD:",
    },
    "AlgorithmWorkspaceReplayDialog.accountNote": {
        "uk": (
            "Цей баланс існує лише всередині Replay. Він не пов’язаний "
            "з рахунком IB або cTrader і не може створювати брокерські "
            "ордери."
        ),
    },
    "AlgorithmWorkspaceSignalTooltip.reason": {"uk": "Причина"},
    "AlgorithmWorkspaceSignalTooltip.signalTime": {"uk": "Час сигналу"},
    "AlgorithmWorkspaceSignalTooltip.macdReason": {"uk": "Причина MACD"},
    "AlgorithmWorkspaceSignalTooltip.macdState": {"uk": "Стан MACD"},
    "AlgorithmWorkspaceSignalTooltip.macdProfile": {"uk": "Профіль MACD"},
    "AlgorithmWorkspaceSignalTooltip.macdQualityResult": {
        "uk": "Результат MACD Quality"
    },
    "AlgorithmWorkspaceSignalTooltip.alligatorReason": {"uk": "Причина Alligator"},
    "AlgorithmWorkspaceSignalTooltip.alligatorState": {"uk": "Стан Alligator"},
    "AlgorithmWorkspaceSignalTooltip.alligatorObservationState": {
        "uk": "Стан observation Alligator"
    },
    "AlgorithmWorkspaceSignalTooltip.alligatorRegime": {"uk": "Режим Alligator"},
    "AlgorithmWorkspaceSignalTooltip.alligatorPhase": {"uk": "Фаза Alligator"},
    "AlgorithmWorkspaceSignalTooltip.alligatorActiveAge": {"uk": "Вік ACTIVE, барів"},
    "AlgorithmWorkspaceSignalTooltip.alligatorNormalizedSlope": {
        "uk": "Нормалізований нахил Alligator"
    },
    "AlgorithmWorkspaceSignalTooltip.alligatorNormalizedOpening": {
        "uk": "Нормалізоване розкриття Alligator"
    },
    "AlgorithmWorkspaceAlligatorRegime.flat": {"uk": "Флет"},
    "AlgorithmWorkspaceAlligatorRegime.trendUp": {"uk": "Тренд вгору"},
    "AlgorithmWorkspaceAlligatorRegime.trendDown": {"uk": "Тренд вниз"},
    "AlgorithmWorkspaceAlligatorRegime.trendUpStarting": {"uk": "Початок тренду вгору"},
    "AlgorithmWorkspaceAlligatorRegime.trendUpEnding": {
        "uk": "Завершення тренду вгору"
    },
    "AlgorithmWorkspaceAlligatorRegime.trendDownStarting": {
        "uk": "Початок тренду вниз"
    },
    "AlgorithmWorkspaceAlligatorRegime.trendDownEnding": {
        "uk": "Завершення тренду вниз"
    },
    "AlgorithmWorkspaceAlligatorRegime.warmup": {"uk": "Прогрів"},
    "AlgorithmWorkspaceAlligatorRegime.disabled": {"uk": "Вимкнено"},
    "AlgorithmWorkspaceAlligatorPhase.starting": {"uk": "STARTING"},
    "AlgorithmWorkspaceAlligatorPhase.active": {"uk": "ACTIVE"},
    "AlgorithmWorkspaceAlligatorPhase.ending": {"uk": "ENDING"},
    "AlgorithmWorkspaceSignalTooltip.alligatorMode": {"uk": "Режим Alligator"},
    "AlgorithmWorkspaceSignalTooltip.alligatorTimeframe": {"uk": "Таймфрейм Alligator"},
    "AlgorithmWorkspaceSignalTooltip.alligatorProfile": {"uk": "Профіль Alligator"},
    "AlgorithmWorkspaceSignalTooltip.observationTime": {"uk": "Час спостереження"},
    "AlgorithmWorkspaceSignalTooltip.availableAt": {"uk": "Доступно з"},
    "AlgorithmWorkspaceSignalTooltip.alligatorT2": {"uk": "Alligator t-2"},
    "AlgorithmWorkspaceSignalTooltip.alligatorT1": {"uk": "Alligator t-1"},
    "AlgorithmWorkspaceSignalTooltip.alligatorT": {"uk": "Alligator t"},
    "AlgorithmWorkspaceSignalTooltip.alligatorDecision": {"uk": "Рішення Alligator"},
    "AlgorithmWorkspaceSignalTooltip.finalDecision": {"uk": "Підсумкове рішення"},
    "AlgorithmWorkspaceSignalTooltip.candidateFLifecycle": {
        "uk": "Життєвий цикл Candidate F"
    },
    "AlgorithmWorkspaceSignalTooltip.lifecycleReason": {
        "uk": "Причина завершення lifecycle"
    },
    "AlgorithmWorkspaceSignalTooltip.lifecycleTime": {"uk": "Час завершення lifecycle"},
    "AlgorithmWorkspaceSignalTooltip.lifecycleDelayBars": {"uk": "Очікування, барів"},
    "AlgorithmWorkspaceSignalTooltip.lifecycleSnapshot": {
        "uk": "Стан при завершенні lifecycle"
    },
    "AlgorithmWorkspaceSignalTooltip.technicalCodes": {"uk": "Технічні коди причини"},
    "AlgorithmWorkspaceSignalTooltip.diagnosticReason": {"uk": "Діагностична причина"},
    "AlgorithmWorkspaceSignalTooltip.profileRevision": {"uk": "ревізія"},
    "AlgorithmWorkspaceSignalSummary.header": {
        "uk": (
            "************************************ ПІДСУМОК РІШЕННЯ "
            "************************************"
        )
    },
    "AlgorithmWorkspaceSignalSummary.footer": {
        "uk": (
            "************************************ КІНЕЦЬ ПІДСУМКУ "
            "************************************"
        )
    },
    "AlgorithmWorkspaceSignalSummary.signal": {"uk": "Сигнал"},
    "AlgorithmWorkspaceSignalSummary.macdQuality": {"uk": "MACD Quality"},
    "AlgorithmWorkspaceSignalSummary.alligator": {"uk": "Alligator"},
    "AlgorithmWorkspaceSignalSummary.alligatorStrength": {"uk": "Сила Alligator"},
    "AlgorithmWorkspaceSignalSummary.lifecycle": {"uk": "Candidate F"},
    "AlgorithmWorkspaceSignalSummary.lifecycleSnapshot": {"uk": "Стан lifecycle"},
    "AlgorithmWorkspaceSignalSummary.lifecycleReason": {"uk": "Причина lifecycle"},
    "AlgorithmWorkspaceSignalSummary.alligatorConfirmation": {
        "uk": "Підтвердження Alligator"
    },
    "AlgorithmWorkspaceSignalSummary.confirmationPassedRelease": {
        "uk": "ПРОЙДЕНО → RELEASE"
    },
    "AlgorithmWorkspaceSignalSummary.structuralGuard": {"uk": "Structural guard"},
    "AlgorithmWorkspaceSignalSummary.filter": {"uk": "Фільтр / guard"},
    "AlgorithmWorkspaceSignalSummary.finalDecision": {"uk": "Фінальне рішення"},
    "AlgorithmWorkspaceSignalSummary.decision": {"uk": "Рішення"},
    "AlgorithmWorkspaceSignalSummary.technicalHeader": {
        "uk": "*** ТЕХНІЧНА ДІАГНОСТИКА ***"
    },
    "AlgorithmWorkspaceCandidateFLifecycle.armed": {"uk": "ARMED"},
    "AlgorithmWorkspaceCandidateFLifecycle.release": {"uk": "RELEASE"},
    "AlgorithmWorkspaceCandidateFLifecycle.cancel": {"uk": "CANCEL"},
    "AlgorithmWorkspaceCandidateFLifecycle.expire": {"uk": "EXPIRE"},
    "AlgorithmWorkspaceCandidateFLifecycle.oppositeMacd": {
        "uk": ("З’явився протилежний сигнал MACD; " "ARMED скасовано.")
    },
    "AlgorithmWorkspaceCandidateFLifecycle.macdInvalid": {
        "uk": ("Співвідношення MACD стало невалідним " "до підтвердження.")
    },
    "AlgorithmWorkspaceCandidateFLifecycle.oppositeActiveAlligator": {
        "uk": "Протилежний ACTIVE Alligator скасував ARMED."
    },
    "AlgorithmWorkspaceCandidateFLifecycle.ttlExpired": {
        "uk": "TTL ARMED завершився без підтвердження."
    },
    "AlgorithmWorkspaceCandidateFLifecycle.releasedByAlligator": {
        "uk": ("Підтвердження Alligator дозволило " "відкладений сигнал.")
    },
    "AlgorithmWorkspaceSignalReason.macdClassicCross": {
        "uk": "Класичний перетин MACD."
    },
    "AlgorithmWorkspaceSignalReason.macdExtendedCross": {
        "uk": "Перетин MACD у розширеному режимі baseline."
    },
    "AlgorithmWorkspaceSignalReason.macdDeferredRelease": {
        "uk": "Відкладений сигнал MACD дозволено після підтвердження Alligator."
    },
    "AlgorithmWorkspaceSignalReason.alligatorDisabled": {
        "uk": "Фільтр Alligator вимкнено."
    },
    "AlgorithmWorkspaceSignalReason.alligatorSameBuyAllow": {
        "uk": "Alligator на таймфреймі сигналу підтверджує BUY."
    },
    "AlgorithmWorkspaceSignalReason.alligatorSameSellAllow": {
        "uk": "Alligator на таймфреймі сигналу підтверджує SELL."
    },
    "AlgorithmWorkspaceSignalReason.alligatorSameBuyReject": {
        "uk": "Alligator на таймфреймі сигналу не підтверджує BUY."
    },
    "AlgorithmWorkspaceSignalReason.alligatorSameSellReject": {
        "uk": "Alligator на таймфреймі сигналу не підтверджує SELL."
    },
    "AlgorithmWorkspaceSignalReason.alligatorSameNotReady": {
        "uk": "Прогрів Alligator ще не завершено."
    },
    "AlgorithmWorkspaceSignalReason.alligatorSameBuyStartingReject": {
        "uk": "Тренд Alligator ще формується; BUY відхилено."
    },
    "AlgorithmWorkspaceSignalReason.alligatorSameSellStartingReject": {
        "uk": "Тренд Alligator ще формується; SELL відхилено."
    },
    "AlgorithmWorkspaceSignalReason.alligatorSameBuyEndingReject": {
        "uk": "Тренд Alligator завершується; BUY відхилено."
    },
    "AlgorithmWorkspaceSignalReason.alligatorSameSellEndingReject": {
        "uk": "Тренд Alligator завершується; SELL відхилено."
    },
    "AlgorithmWorkspaceSignalReason.alligatorHigher1BuyAllow": {
        "uk": "Alligator HIGHER_1 підтверджує BUY."
    },
    "AlgorithmWorkspaceSignalReason.alligatorHigher1SellAllow": {
        "uk": "Alligator HIGHER_1 підтверджує SELL."
    },
    "AlgorithmWorkspaceSignalReason.alligatorHigher1BuyReject": {
        "uk": "Alligator HIGHER_1 не підтверджує BUY."
    },
    "AlgorithmWorkspaceSignalReason.alligatorHigher1SellReject": {
        "uk": "Alligator HIGHER_1 не підтверджує SELL."
    },
    "AlgorithmWorkspaceSignalReason.alligatorHigher1NotReady": {
        "uk": "Прогрів Alligator HIGHER_1 ще не завершено."
    },
    "AlgorithmWorkspaceSignalReason.alligatorHigher2BuyAllow": {
        "uk": "Alligator HIGHER_2 підтверджує BUY."
    },
    "AlgorithmWorkspaceSignalReason.alligatorHigher2SellAllow": {
        "uk": "Alligator HIGHER_2 підтверджує SELL."
    },
    "AlgorithmWorkspaceSignalReason.alligatorHigher2BuyReject": {
        "uk": "Alligator HIGHER_2 не підтверджує BUY."
    },
    "AlgorithmWorkspaceSignalReason.alligatorHigher2SellReject": {
        "uk": "Alligator HIGHER_2 не підтверджує SELL."
    },
    "AlgorithmWorkspaceSignalReason.alligatorHigher2NotReady": {
        "uk": "Прогрів Alligator HIGHER_2 ще не завершено."
    },
    "AlgorithmWorkspaceSignalReason.alligatorDeferredArmed": {
        "uk": "Сигнал MACD відкладено: відповідний тренд Alligator ще формується."
    },
    "AlgorithmWorkspaceSignalReason.alligatorDeferredRelease": {
        "uk": "Alligator перейшов у ACTIVE і дозволив відкладений сигнал MACD."
    },
    "AlgorithmWorkspaceSignalReason.alligatorOpeningCollapseReject": {
        "uk": "Розкриття Alligator надто швидко звужується; сигнал відхилено."
    },
    "AlgorithmWorkspaceSignalReason.alligatorWeakOpeningReject": {
        "uk": (
            "Alligator перейшов у ACTIVE надто рано і ще недостатньо "
            "розкритий; сигнал відхилено."
        )
    },
    "AlgorithmWorkspaceSignalReason.alligatorVolatilitySpikeReject": {
        "uk": "Стрибок волатильності збігся з погіршенням Alligator; сигнал відхилено."
    },
    "AlgorithmWorkspaceSignalReason.alligatorOverextendedReject": {
        "uk": "Тренд Alligator надмірно розігнаний; сигнал відхилено."
    },
    "AlgorithmWorkspaceSignalReason.runtimeStopped": {
        "uk": "Середовище виконання зупинено."
    },
    "AlgorithmWorkspaceSignalReason.marketDataNotLoaded": {
        "uk": "Ринкові дані ще не завантажено."
    },
    "AlgorithmWorkspaceSignalReason.waitingAcceptableSpread": {
        "uk": "Очікується допустимий спред."
    },
    "AlgorithmWorkspaceSignalReason.warmupIncomplete": {
        "uk": "Прогрів ще не завершено."
    },
    "AlgorithmWorkspaceSignalReason.waitingLiveSpread": {
        "uk": "Очікується перший live-спред."
    },
    "AlgorithmWorkspaceSignalReason.waitingFreshSpread": {
        "uk": "Очікується свіжий live-спред."
    },
    "AlgorithmWorkspaceSignalReason.waitingBrokerReconnect": {
        "uk": "Очікується повторне підключення брокера."
    },
    "AlgorithmWorkspaceSignalReason.runtimeError": {
        "uk": "Помилка середовища виконання."
    },
    "AlgorithmWorkspaceSignalReason.startupGuardNotReady": {
        "uk": "Стартовий захист ще не готовий."
    },
    "AlgorithmWorkspaceSignalReason.externalExposureSafetyHold": {
        "uk": (
            "Сигнали призупинено через захисну паузу зовнішньої " "IB FX-експозиції."
        )
    },
    "AlgorithmWorkspaceSignalReason.spreadTooWide": {"uk": "Спред завеликий."},
    "AlgorithmWorkspaceSignalReason.manualDisplayOnly": {
        "uk": "Сигнал прийнято лише для відображення в режимі MANUAL."
    },
    "AlgorithmWorkspaceSignalReason.semiConfirmationRequired": {
        "uk": ("Сигнал прийнято; у режимі SEMI потрібне підтвердження " "користувача.")
    },
    "AlgorithmWorkspaceSignalReason.autoAccepted": {
        "uk": "Сигнал прийнято в режимі AUTO."
    },
    "AlgorithmWorkspaceSignalReason.rejectedBeforeRisk": {
        "uk": "Сигнал відхилено до перевірки ризику."
    },
    "AlgorithmWorkspaceSignalReason.riskRejected": {
        "uk": "Сигнал відхилено обмеженнями ризику."
    },
    "AlgorithmWorkspaceWindow.colAlligatorRegime": {"uk": "Режим"},
    "AlgorithmWorkspaceWindow.colSignalTimeframeMode": {"uk": "ТФ / режим"},
    "AlgorithmWorkspaceWindow.colSignalProfileRevision": {"uk": "Ревізія профілю"},
    "AlgorithmWorkspaceWindow.colFilterResult": {"uk": "Фільтр / результат"},
    "AlgorithmWorkspaceWindow.colSpreadStatus": {"uk": "Спред"},
    "AlgorithmWorkspaceWindow.colCloseReason": {"uk": "Причина закриття"},
    "AlgorithmWorkspaceWindow.colPositionSignalTime": {"uk": "Сигнал"},
    "AlgorithmWorkspaceWindow.colClosedAt": {"uk": "Закрито"},
    "AlgorithmWorkspaceWindow.lblPositionDateJump": {"uk": "Перейти до дати"},
    "AlgorithmWorkspaceWindow.btnPositionDateJump": {"uk": "Перейти на вказану дату"},
    "AlgorithmWorkspaceWindow.positionDateJumpHint": {
        "uk": (
            "Вибрати календарну дату відкриття й перейти до першої "
            "видимої позиції цього дня або найближчої наступної "
            "доступної дати."
        )
    },
    "AlgorithmWorkspaceWindow.btnPositionGoSignal": {"uk": "До сигналу"},
    "AlgorithmWorkspaceWindow.btnPositionGoEntry": {"uk": "На діаграму"},
    "AlgorithmWorkspaceWindow.lblSignalDateJump": {"uk": "Перейти до дати"},
    "AlgorithmWorkspaceWindow.btnSignalDateJump": {"uk": "Перейти на вказану дату"},
    "AlgorithmWorkspaceWindow.signalDateJumpHint": {
        "uk": (
            "Вибрати календарну дату сигналу й перейти до першого "
            "видимого сигналу цього дня або найближчої наступної "
            "доступної дати."
        )
    },
    "AlgorithmWorkspaceWindow.btnSignalGoPosition": {"uk": "До позиції"},
    "AlgorithmWorkspaceWindow.btnSignalGoChart": {"uk": "До діаграми"},
    "AlgorithmWorkspaceWindow.btnSignalGoJournal": {"uk": "До журналу"},
    "AlgorithmWorkspaceWindow.signalGoPositionHint": {
        "uk": "Відкрити позицію, створену з вибраного прийнятого сигналу."
    },
    "AlgorithmWorkspaceWindow.signalGoChartHint": {
        "uk": "Показати й позначити на діаграмі бар вибраного сигналу."
    },
    "AlgorithmWorkspaceWindow.signalGoJournalHint": {
        "uk": "Відкрити записи журналу за часом вибраного сигналу."
    },
    "AlgorithmWorkspaceWindow.positionGoSignalHint": {
        "uk": "Перейти до сигналу, з якого створена вибрана позиція."
    },
    "AlgorithmWorkspaceWindow.positionGoEntryHint": {
        "uk": (
            "Показати й позначити на діаграмі бар фактичного входу "
            "за політикою NEXT_BAR_OPEN."
        )
    },
    "AlgorithmWorkspacePositionStatus.open": {"uk": "Відкрита"},
    "AlgorithmWorkspacePositionStatus.closed": {"uk": "Закрита"},
    "AlgorithmWorkspacePositionCloseReason.stopLoss": {"uk": "Stop Loss"},
    "AlgorithmWorkspacePositionCloseReason.takeProfit": {"uk": "Take Profit"},
    "AlgorithmWorkspacePositionCloseReason.profitDrawdown": {"uk": "Відкат прибутку"},
    "AlgorithmWorkspacePositionCloseReason.sessionEnd": {"uk": "Кінець Replay"},
    "AlgorithmWorkspacePositionTooltip.status": {"uk": "Стан"},
    "AlgorithmWorkspacePositionTooltip.closeReason": {"uk": "Причина закриття"},
    "AlgorithmWorkspacePositionTooltip.technicalStatus": {"uk": "Технічний статус"},
    "AlgorithmWorkspacePositionTooltip.technicalReason": {
        "uk": "Технічний код причини"
    },
    "OrdersPage.filterBroker": {
        "uk": "Зовнішні у брокері",
        "pl": "Zewnętrzne u brokera",
        "de": "Extern beim Broker",
        "fr": "Externes chez le courtier",
    },
    "OrdersPage.typeBrokerResidual": {
        "uk": "Зовнішня експозиція IB",
        "pl": "Zewnętrzna ekspozycja IB",
        "de": "Externe IB-Exposition",
        "fr": "Exposition IB externe",
    },
    "OrdersPage.tooltipExternalProtectionWithoutObservation": {
        "uk": (
            "У TWS активні зовнішні захисні ордери, але зовнішній "
            "обсяг позиції неможливо визначити, оскільки спостереження "
            "IB CASH Forex відсутнє."
        ),
        "pl": (
            "W TWS są aktywne zewnętrzne zlecenia ochronne, ale nie można "
            "określić zewnętrznej ekspozycji, ponieważ obserwacja pozycji "
            "IB CASH Forex jest niedostępna."
        ),
    },
    "OrdersPage.externalExposureNeedsConfirmation": {
        "uk": "Потрібне підтвердження",
        "pl": "Wymaga potwierdzenia",
        "de": "Bestätigung erforderlich",
        "fr": "Confirmation requise",
    },
    "OrdersPage.tooltipExternalExposureNeedsConfirmation": {
        "uk": (
            "Зовнішня IB FX-позиція збережена у постійному реєстрі, "
            "оскільки поточне спостереження Virtual FX відсутнє. Перед "
            "автоматичним виконанням Paper або Live для цього рахунку й "
            "символу потрібне підтвердження брокера."
        ),
        "pl": (
            "Zewnętrzna ekspozycja IB FX została zachowana w trwałym "
            "rejestrze, ponieważ bieżąca obserwacja Virtual FX jest "
            "niedostępna. Przed automatycznym wykonaniem Paper lub Live "
            "dla tego konta i symbolu wymagane jest potwierdzenie brokera."
        ),
    },
    "OrdersPage.tooltipExternalExposureRetained": {
        "uk": (
            "Збережену зовнішню IB FX-позицію не видалено, оскільки "
            "поточне спостереження IB CASH Forex відсутнє; потрібне "
            "підтвердження брокера."
        ),
        "pl": (
            "Zachowana zewnętrzna ekspozycja IB FX nie została usunięta, "
            "ponieważ bieżąca obserwacja IB CASH Forex jest niedostępna; "
            "wymagane jest potwierdzenie brokera."
        ),
    },
    "OrdersPage.tooltipExternalExposureProtectedWithoutObservation": {
        "uk": (
            "Захисні ордери іншого clientId підтверджують наявність "
            "збереженої зовнішньої IB FX-позиції, але поточне "
            "спостереження позиції відсутнє."
        ),
        "pl": (
            "Zlecenia ochronne innego clientId potwierdzają zachowaną "
            "zewnętrzną ekspozycję IB FX, ale bieżąca obserwacja pozycji "
            "jest niedostępna."
        ),
    },
    "OrdersPage.tooltipCurrentExternalExposure": {
        "uk": (
            "Поточна експозиція IB CASH Forex без точних віртуальних "
            "позицій LGE показана як зовнішня експозиція лише для читання."
        ),
        "pl": (
            "Bieżąca ekspozycja IB CASH Forex bez dokładnych wirtualnych "
            "pozycji LGE jest pokazana jako zewnętrzna ekspozycja tylko "
            "do odczytu."
        ),
    },
    "OrdersPage.tooltipExternalExecutionResidual": {
        "uk": (
            "Зовнішню експозицію IB CASH Forex визначено за точними "
            "виконаннями поза ордерами LGE, а не відніманням "
            "керованих позицій LGE від спостереження Virtual FX: "
            "зовнішня={external}, virtual_fx_мінус_керовані="
            "{virtual_fx_minus_managed}, керовані={managed}, "
            "virtual_fx={virtual_fx}, позиція={position}"
        ),
        "pl": (
            "Zewnętrzną ekspozycję IB CASH Forex wyznaczono z dokładnych "
            "wykonań spoza dokładnych zleceń LGE, a nie przez odejmowanie "
            "zarządzanych pozycji LGE od obserwacji Virtual FX: "
            "zewnętrzna={external}, virtual_fx_minus_managed="
            "{virtual_fx_minus_managed}, zarządzane={managed}, "
            "virtual_fx={virtual_fx}, pozycja={position}"
        ),
        "de": (
            "Die externe IB-CASH-Forex-Exposition wird aus exakten "
            "Ausführungen außerhalb exakter LGE-Aufträge bestimmt und nicht durch "
            "Abzug der verwalteten LGE-Positionen von der Virtual-FX-"
            "Beobachtung: extern={external}, virtual_fx_minus_managed="
            "{virtual_fx_minus_managed}, verwaltet={managed}, "
            "virtual_fx={virtual_fx}, Position={position}"
        ),
        "fr": (
            "L’exposition IB CASH Forex externe est déterminée à partir "
            "des exécutions hors des ordres LGE exacts, et non en "
            "soustrayant les positions LGE gérées de l’observation Virtual "
            "FX : externe={external}, virtual_fx_minus_managed="
            "{virtual_fx_minus_managed}, gérées={managed}, "
            "virtual_fx={virtual_fx}, position={position}"
        ),
    },
    "OrdersPage.tooltipPersistedExternalExecutionResidual": {
        "uk": (
            "Зовнішню експозицію IB CASH Forex збережено за раніше "
            "підтвердженими точними доказами, оскільки поточний знімок "
            "виконань уже не містить цього виконання поза ордерами LGE: "
            "зовнішня={external}, virtual_fx_мінус_керовані="
            "{virtual_fx_minus_managed}, керовані={managed}, "
            "virtual_fx={virtual_fx}, позиція={position}"
        ),
        "pl": (
            "Zewnętrzną ekspozycję IB CASH Forex zachowano na podstawie "
            "wcześniej potwierdzonych dokładnych dowodów, ponieważ bieżący "
            "zrzut wykonań nie zawiera już tego wykonania spoza zleceń LGE: "
            "zewnętrzna={external}, virtual_fx_minus_managed="
            "{virtual_fx_minus_managed}, zarządzane={managed}, "
            "virtual_fx={virtual_fx}, pozycja={position}"
        ),
        "de": (
            "Die externe IB-CASH-Forex-Exposition wird anhand zuvor "
            "bestätigter exakter Nachweise beibehalten, da der aktuelle "
            "Ausführungs-Snapshot enthält diese Ausführung außerhalb "
            "der LGE-Aufträge nicht mehr: extern={external}, "
            "virtual_fx_minus_managed="
            "{virtual_fx_minus_managed}, verwaltet={managed}, "
            "virtual_fx={virtual_fx}, Position={position}"
        ),
        "fr": (
            "L’exposition IB CASH Forex externe est conservée à partir de "
            "preuves exactes précédemment confirmées, car l’instantané "
            "actuel des exécutions ne contient plus cette exécution "
            "hors des ordres LGE : externe={external}, "
            "virtual_fx_minus_managed="
            "{virtual_fx_minus_managed}, gérées={managed}, "
            "virtual_fx={virtual_fx}, position={position}"
        ),
    },
    "OrdersPage.tooltipExternalExposureProtectiveEvidence": {
        "uk": (
            "Зовнішню IB FX-експозицію визначено за активними захисними "
            "ордерами іншого clientId, коли поточне спостереження позиції "
            "відсутнє. Ці ордери можуть бути залишковими, тому потрібне "
            "підтвердження брокера."
        ),
        "pl": (
            "Zewnętrzną ekspozycję IB FX wywnioskowano z aktywnych zleceń "
            "ochronnych innego clientId, gdy bieżąca obserwacja pozycji "
            "jest niedostępna. Zlecenia mogą być osierocone, dlatego "
            "wymagane jest potwierdzenie brokera."
        ),
    },
    "AlgorithmWorkspaceStartupPhase.safetyHoldExternalExposure": {
        "uk": "ЗАХИСНА ПАУЗА",
        "pl": "WSTRZYMANIE OCHRONNE",
        "de": "SICHERHEITSHALT",
        "fr": "MISE EN SÉCURITÉ",
    },
    "AlgorithmWorkspaceWindow.safetyHoldExternalExposureStatus": {
        "uk": (
            "ЗАХИСНА ПАУЗА • {symbol} • нові ордери LGE заблоковано • "
            "Ордери → Вирішення питань узгодження"
        ),
        "pl": (
            "WSTRZYMANIE OCHRONNE • {symbol} • nowe zlecenia LGE są "
            "zablokowane • Zlecenia → Rozwiąż uzgodnienie"
        ),
        "de": (
            "SICHERHEITSHALT • {symbol} • neue LGE-Orders sind gesperrt • "
            "Orders → Abstimmung klären"
        ),
        "fr": (
            "MISE EN SÉCURITÉ • {symbol} • nouveaux ordres LGE bloqués • "
            "Ordres → Résoudre le rapprochement"
        ),
    },
    "AlgorithmWorkspaceWindow.safetyHoldTooltip": {
        "uk": (
            "LGE EXCLUSIVE призупинила нові сигнали та ордери LGE; ринкові "
            "дані продовжують надходити. Рахунок: {account_id}; символ: "
            "{symbol}; зовнішня експозиція: {side} {volume}; стан доказів: "
            "{evidence}. Відкрий «Ордери», вибери рядок BROKER із типом "
            "«Зовнішня експозиція» та натисни «Вирішення питань "
            "узгодження», щоб побачити точні ідентифікатори TWS. Після "
            "врегулювання у TWS натисни «Оновити». Для повернення до WSP "
            "і журналу відкрий «Моніторинг»."
        ),
        "pl": (
            "LGE EXCLUSIVE wstrzymała nowe sygnały i zlecenia LGE; dane "
            "rynkowe nadal napływają. Konto: {account_id}; symbol: {symbol}; "
            "ekspozycja zewnętrzna: {side} {volume}; dowody: {evidence}. "
            "Otwórz Zlecenia, wybierz wiersz BROKER typu „Ekspozycja "
            "zewnętrzna” i kliknij Rozwiąż uzgodnienie, aby zobaczyć "
            "dokładne identyfikatory TWS. Po rozwiązaniu w TWS kliknij "
            "Odśwież. Do WSP i dziennika wróć przez Monitorowanie."
        ),
        "de": (
            "LGE EXCLUSIVE hat neue LGE-Signale und Orders angehalten; die "
            "Marktdaten laufen weiter. Konto: {account_id}; Symbol: {symbol}; "
            "externe Exposition: {side} {volume}; Nachweis: {evidence}. "
            "Öffne Orders, wähle die BROKER-Zeile vom Typ „Externe "
            "Exposition“ und klicke auf Abstimmung klären, um genaue "
            "TWS-Kennungen zu sehen. Nach der Klärung in TWS klicke auf "
            "Aktualisieren. WSP und Journal findest du unter Überwachung."
        ),
        "fr": (
            "LGE EXCLUSIVE a suspendu les nouveaux signaux et ordres LGE ; "
            "les données de marché continuent. Compte : {account_id} ; "
            "symbole : {symbol} ; exposition externe : {side} {volume} ; "
            "preuves : {evidence}. Ouvrez Ordres, sélectionnez la ligne "
            "BROKER de type « Exposition externe » et cliquez sur Résoudre "
            "le rapprochement pour voir les identifiants TWS exacts. Après "
            "régularisation dans TWS, cliquez sur Actualiser. Le WSP et le "
            "journal se trouvent dans Surveillance."
        ),
    },
    "AlgorithmWorkspaceJournal.categorySafety": {
        "uk": "Захист",
        "pl": "Bezpieczeństwo",
        "de": "Sicherheit",
        "fr": "Sécurité",
    },
    "AlgorithmWorkspaceJournal.safetyHoldEntered": {
        "uk": "ЗАХИСНУ ПАУЗУ УВІМКНЕНО",
        "pl": "WŁĄCZONO WSTRZYMANIE OCHRONNE",
        "de": "SICHERHEITSHALT AKTIVIERT",
        "fr": "MISE EN SÉCURITÉ ACTIVÉE",
    },
    "AlgorithmWorkspaceJournal.safetyHoldUpdated": {
        "uk": "ЗАХИСНУ ПАУЗУ ОНОВЛЕНО",
        "pl": "ZAKTUALIZOWANO WSTRZYMANIE OCHRONNE",
        "de": "SICHERHEITSHALT AKTUALISIERT",
        "fr": "MISE EN SÉCURITÉ ACTUALISÉE",
    },
    "AlgorithmWorkspaceJournal.safetyHoldCleared": {
        "uk": "ЗАХИСНУ ПАУЗУ ЗНЯТО",
        "pl": "WYŁĄCZONO WSTRZYMANIE OCHRONNE",
        "de": "SICHERHEITSHALT AUFGEHOBEN",
        "fr": "MISE EN SÉCURITÉ LEVÉE",
    },
    "AlgorithmWorkspaceJournal.safetyHoldActiveMessage": {
        "uk": (
            "Рахунок {account_id}, символ {symbol}: зовнішня експозиція "
            "{side} {volume}; стан доказів: {evidence}. Нові сигнали й ордери "
            "LGE заблоковано; ринкові дані продовжують надходити. Відкрий "
            "«Ордери», вибери рядок BROKER із типом «Зовнішня експозиція» "
            "і натисни «Вирішення питань узгодження»."
        ),
        "pl": (
            "Konto {account_id}, symbol {symbol}: ekspozycja zewnętrzna "
            "{side} {volume}; dowody: {evidence}. Nowe sygnały i zlecenia "
            "LGE są zablokowane; dane rynkowe nadal napływają. Otwórz "
            "Zlecenia, wybierz wiersz BROKER typu „Ekspozycja zewnętrzna” "
            "i kliknij Rozwiąż uzgodnienie."
        ),
        "de": (
            "Konto {account_id}, Symbol {symbol}: externe Exposition {side} "
            "{volume}; Nachweis: {evidence}. Neue LGE-Signale und Orders "
            "sind gesperrt; Marktdaten laufen weiter. Öffne Orders, wähle "
            "die BROKER-Zeile vom Typ „Externe Exposition“ und klicke auf "
            "Abstimmung klären."
        ),
        "fr": (
            "Compte {account_id}, symbole {symbol} : exposition externe "
            "{side} {volume} ; preuves : {evidence}. Les nouveaux signaux "
            "et ordres LGE sont bloqués ; les données continuent. Ouvrez "
            "Ordres, sélectionnez la ligne BROKER de type « Exposition "
            "externe » et cliquez sur Résoudre le rapprochement."
        ),
    },
    "AlgorithmWorkspaceJournal.safetyHoldClearedMessage": {
        "uk": (
            "Поточні дані брокера підтвердили відсутність зовнішньої "
            "експозиції. Перед відновленням виконання LGE очікує свіжий "
            "ринковий спред."
        ),
        "pl": (
            "Bieżące dane brokera potwierdziły usunięcie ekspozycji zewnętrznej. "
            "Przed wznowieniem wykonania LGE czeka na świeży spread rynkowy."
        ),
        "de": (
            "Aktuelle Brokerdaten bestätigen, dass die externe Exposition "
            "beseitigt ist. Vor der Wiederaufnahme wartet LGE auf einen neuen "
            "Live-Spread."
        ),
        "fr": (
            "Les données actuelles du courtier confirment la disparition de "
            "l’exposition externe. Avant de reprendre, LGE attend un nouveau "
            "spread en direct."
        ),
    },
    "AlgorithmWorkspaceJournal.safetyPhaseChanged": {
        "uk": "ЗМІНА ЗАХИСНОГО СТАНУ",
        "pl": "ZMIANA STANU OCHRONNEGO",
        "de": "ÄNDERUNG DES SICHERHEITSSTATUS",
        "fr": "CHANGEMENT D’ÉTAT DE SÉCURITÉ",
    },
    "AlgorithmWorkspaceJournal.safetyPhaseChangedMessage": {
        "uk": (
            "{previous_phase} → {target_phase}. Нове виконання LGE заблоковано, "
            "а ринкові дані продовжують надходити лише для читання."
        ),
        "pl": (
            "{previous_phase} → {target_phase}. Nowe wykonanie LGE jest "
            "zablokowane, a dane rynkowe nadal napływają tylko do odczytu."
        ),
        "de": (
            "{previous_phase} → {target_phase}. Neue LGE-Ausführung ist "
            "gesperrt; Marktdaten laufen schreibgeschützt weiter."
        ),
        "fr": (
            "{previous_phase} → {target_phase}. La nouvelle exécution LGE est "
            "bloquée tandis que les données continuent en lecture seule."
        ),
    },
    "AlgorithmWorkspaceSafety.sideBuy": {
        "uk": "КУПІВЛЯ",
        "pl": "KUPNO",
        "de": "KAUF",
        "fr": "ACHAT",
    },
    "AlgorithmWorkspaceSafety.sideSell": {
        "uk": "ПРОДАЖ",
        "pl": "SPRZEDAŻ",
        "de": "VERKAUF",
        "fr": "VENTE",
    },
    "AlgorithmWorkspaceSafety.sideUnknown": {
        "uk": "НЕВІДОМО",
        "pl": "NIEZNANE",
        "de": "UNBEKANNT",
        "fr": "INCONNU",
    },
    "AlgorithmWorkspaceSafety.evidenceConfirmed": {
        "uk": "підтверджено поточними даними IB",
        "pl": "potwierdzone bieżącymi danymi IB",
        "de": "durch aktuelle IB-Daten bestätigt",
        "fr": "confirmé par les données IB actuelles",
    },
    "AlgorithmWorkspaceSafety.evidenceStale": {
        "uk": "потрібне підтвердження брокера",
        "pl": "wymagane potwierdzenie brokera",
        "de": "Brokerbestätigung erforderlich",
        "fr": "confirmation du courtier requise",
    },
    "AlgorithmWorkspaceSafety.evidenceCleared": {
        "uk": "експозицію прибрано",
        "pl": "ekspozycja usunięta",
        "de": "Exposition beseitigt",
        "fr": "exposition supprimée",
    },
    "AlgorithmWorkspaceSafety.evidenceUnavailable": {
        "uk": "дані недоступні",
        "pl": "dane niedostępne",
        "de": "Nachweis nicht verfügbar",
        "fr": "preuves indisponibles",
    },
    "AlgorithmWorkspaceArea.externalExposureDetectedTitle": {
        "uk": "Зовнішня IB FX-експозиція",
        "pl": "Zewnętrzna ekspozycja IB FX",
        "de": "Externe IB-FX-Exposition",
        "fr": "Exposition FX IB externe",
    },
    "AlgorithmWorkspaceArea.externalExposureDetectedMessage": {
        "uk": (
            "Політика LGE EXCLUSIVE перевела робочий простір {workspace} "
            "у ЗАХИСНУ ПАУЗУ для {symbol}. Сторінку «Ордери» відкрито "
            "автоматично. Вибери рядок BROKER із типом «Зовнішня "
            "експозиція» та натисни «Вирішення питань узгодження», щоб "
            "побачити точні ідентифікатори ордерів TWS. Після врегулювання "
            "позиції або залишкових захисних ордерів у TWS натисни "
            "«Оновити». Для перегляду WSP і журналу перейди в «Моніторинг»."
        ),
        "pl": (
            "Polityka LGE EXCLUSIVE ustawiła obszar {workspace} w trybie "
            "WSTRZYMANIA OCHRONNEGO dla {symbol}. Strona Zlecenia została "
            "otwarta automatycznie. Wybierz wiersz BROKER typu „Ekspozycja "
            "zewnętrzna” i kliknij Rozwiąż uzgodnienie, aby zobaczyć "
            "dokładne identyfikatory zleceń TWS. Po rozwiązaniu pozycji lub "
            "osieroconych zleceń ochronnych w TWS kliknij Odśwież. Aby "
            "przejrzeć WSP i dziennik, przejdź do Monitorowania."
        ),
        "de": (
            "LGE EXCLUSIVE hat den Arbeitsbereich {workspace} für {symbol} "
            "in den SICHERHEITSHALT versetzt. Die Orders-Seite wurde "
            "automatisch geöffnet. Wähle die BROKER-Zeile vom Typ „Externe "
            "Exposition“ und klicke auf Abstimmung klären, um die genauen "
            "TWS-Orderkennungen zu sehen. Kläre danach die Position oder "
            "verwaisten Schutzorders in TWS und klicke auf Aktualisieren. "
            "Für WSP und Journal gehe zu Überwachung."
        ),
        "fr": (
            "LGE EXCLUSIVE a placé l’espace {workspace} en MISE EN SÉCURITÉ "
            "pour {symbol}. La page Ordres a été ouverte automatiquement. "
            "Sélectionnez la ligne BROKER de type « Exposition externe » "
            "et cliquez sur Résoudre le rapprochement pour voir les "
            "identifiants TWS exacts. Régularisez ensuite la position ou "
            "les ordres de protection orphelins dans TWS, puis cliquez sur "
            "Actualiser. Pour consulter le WSP et le journal, ouvrez "
            "Surveillance."
        ),
    },
    "OrdersPage.titleExternalExposureBlocked": {
        "uk": "Зовнішня IB FX-експозиція",
        "pl": "Zewnętrzna ekspozycja IB FX",
        "de": "Externe IB-FX-Exposition",
        "fr": "Exposition FX IB externe",
    },
    "OrdersPage.msgExternalExposureOrderBlocked": {
        "uk": (
            "LGE EXCLUSIVE заблокував новий ордер LGE до запису Trade у "
            "базу і до запиту брокеру. Рахунок: {account_id}; символ: "
            "{symbol}; зовнішня експозиція: {side} {volume}; стан доказів: "
            "{evidence}. Вибери рядок BROKER із типом «Зовнішня "
            "експозиція» та натисни «Вирішення питань узгодження», щоб "
            "побачити точні ідентифікатори ордерів TWS. Закрий або "
            "врегулюй зовнішню позицію та її захисні ордери, потім натисни "
            "«Оновити». Для перегляду WSP і журналу перейди в «Моніторинг»."
        ),
        "pl": (
            "LGE EXCLUSIVE zablokował nowe zlecenie LGE przed zapisem Trade "
            "w bazie i przed żądaniem do brokera. Konto: {account_id}; "
            "symbol: {symbol}; ekspozycja zewnętrzna: {side} {volume}; stan "
            "dowodów: {evidence}. Wybierz wiersz BROKER typu „Ekspozycja "
            "zewnętrzna” i kliknij Rozwiąż uzgodnienie, aby zobaczyć "
            "dokładne identyfikatory TWS. Rozwiąż pozycję i jej ochronę, "
            "kliknij Odśwież, a do WSP i dziennika wróć przez Monitorowanie."
        ),
        "de": (
            "LGE EXCLUSIVE hat die neue LGE-Order vor dem Trade-Eintrag und "
            "vor der Broker-Anfrage gesperrt. Konto: {account_id}; Symbol: "
            "{symbol}; externe Exposition: {side} {volume}; Nachweisstatus: "
            "{evidence}. Wähle die BROKER-Zeile vom Typ „Externe "
            "Exposition“ und klicke auf Abstimmung klären, um die genauen "
            "TWS-Kennungen zu sehen. Kläre Position und Schutzorders, klicke "
            "auf Aktualisieren und öffne Überwachung für WSP und Journal."
        ),
        "fr": (
            "LGE EXCLUSIVE a bloqué le nouvel ordre LGE avant l’écriture du "
            "Trade en base et avant la requête au courtier. Compte : "
            "{account_id} ; symbole : {symbol} ; exposition externe : "
            "{side} {volume} ; état des preuves : {evidence}. Sélectionnez "
            "la ligne BROKER de type « Exposition externe » et cliquez sur "
            "Résoudre le rapprochement pour voir les identifiants TWS "
            "exacts. Régularisez la position et sa protection, cliquez sur "
            "Actualiser, puis ouvrez Surveillance pour le WSP et le journal."
        ),
    },
    "OrdersPage.statusExternalExposureResolution": {
        "uk": (
            "LGE EXCLUSIVE: виріши питання зовнішньої IB FX-експозиції для "
            "рахунку {account_id}, символу {symbol}; потім натисни «Оновити»."
        ),
        "pl": (
            "LGE EXCLUSIVE: rozwiąż zewnętrzną ekspozycję IB FX dla konta "
            "{account_id}, symbolu {symbol}; następnie naciśnij Odśwież."
        ),
        "de": (
            "LGE EXCLUSIVE: externe IB-FX-Exposition für Konto {account_id}, "
            "Symbol {symbol} klären; danach Aktualisieren klicken."
        ),
        "fr": (
            "LGE EXCLUSIVE : régularisez l’exposition FX IB externe du "
            "compte {account_id}, symbole {symbol}, puis cliquez sur "
            "Actualiser."
        ),
    },
    "OrdersPage.titleExternalExposureDetails": {
        "uk": "Точні дані зовнішньої IB FX-експозиції",
        "pl": "Dokładne dane zewnętrznej ekspozycji IB FX",
        "de": "Genaue Daten der externen IB-FX-Exposition",
        "fr": "Détails exacts de l’exposition FX IB externe",
    },
    "OrdersPage.msgExternalExposureDetailsIntro": {
        "uk": (
            "Рахунок: {account_id}\nСимвол: {symbol}\nЗовнішня експозиція: "
            "{side} {volume}\nСтан доказів: {evidence}"
        ),
        "pl": (
            "Konto: {account_id}\nSymbol: {symbol}\nEkspozycja zewnętrzna: "
            "{side} {volume}\nStan dowodów: {evidence}"
        ),
        "de": (
            "Konto: {account_id}\nSymbol: {symbol}\nExterne Exposition: "
            "{side} {volume}\nNachweisstatus: {evidence}"
        ),
        "fr": (
            "Compte : {account_id}\nSymbole : {symbol}\nExposition externe : "
            "{side} {volume}\nÉtat des preuves : {evidence}"
        ),
    },
    "OrdersPage.msgExternalExposureOrdersHeader": {
        "uk": "Поточні захисні ордери іншого clientId, отримані від IB:",
        "pl": "Bieżące zlecenia ochronne innego clientId otrzymane z IB:",
        "de": "Aktuelle Schutzorders einer anderen clientId von IB:",
        "fr": "Ordres de protection actuels d’un autre clientId reçus d’IB :",
    },
    "OrdersPage.msgExternalExposureOrderLine": {
        "uk": (
            "{order_type} {action} {quantity} @ {price}; orderId={order_id}; "
            "permId={perm_id}; parentId={parent_id}; clientId={client_id}; "
            "OCA={oca_group}; статус={status}; TIF={tif}"
        ),
        "pl": (
            "{order_type} {action} {quantity} @ {price}; orderId={order_id}; "
            "permId={perm_id}; parentId={parent_id}; clientId={client_id}; "
            "OCA={oca_group}; status={status}; TIF={tif}"
        ),
        "de": (
            "{order_type} {action} {quantity} @ {price}; orderId={order_id}; "
            "permId={perm_id}; parentId={parent_id}; clientId={client_id}; "
            "OCA={oca_group}; Status={status}; TIF={tif}"
        ),
        "fr": (
            "{order_type} {action} {quantity} @ {price} ; orderId={order_id} ; "
            "permId={perm_id} ; parentId={parent_id} ; clientId={client_id} ; "
            "OCA={oca_group} ; statut={status} ; TIF={tif}"
        ),
    },
    "OrdersPage.msgExternalExposureNoCurrentOrders": {
        "uk": (
            "У поточному знімку IB немає точних рядків захисних ордерів. "
            "Не скасовуй ордер навмання: перевір позицію та ордери у TWS "
            "або у виписці IB."
        ),
        "pl": (
            "W bieżącym obrazie IB nie ma dokładnych wierszy zleceń "
            "ochronnych. Nie anuluj zlecenia na chybił trafił; sprawdź "
            "pozycję i zlecenia w TWS lub wyciągu IB."
        ),
        "de": (
            "Im aktuellen IB-Snapshot sind keine genauen Schutzorderzeilen "
            "verfügbar. Keine Order auf Verdacht stornieren; Position und "
            "Orders in TWS oder im IB-Auszug prüfen."
        ),
        "fr": (
            "L’instantané IB actuel ne contient pas les lignes exactes des "
            "ordres de protection. N’annulez rien au hasard ; vérifiez la "
            "position et les ordres dans TWS ou un relevé IB."
        ),
    },
    "OrdersPage.msgExternalExposureResolutionSteps": {
        "uk": (
            "Ці ордери брокера доступні в LGE лише для читання. Знайди їх у "
            "TWS → Orders за символом, типом, ціною, permId, parentId, "
            "clientId та OCA. Для ордерів іншого clientId IB може повернути "
            "orderId=0; тоді орієнтуйся на permId/clientId/parentId/OCA. LGE "
            "не вигадує номери рядків TWS на кшталт 6.1/6.2. Якщо зовнішня "
            "позиція ще існує — закрий або врегулюй її разом із захистом. "
            "Якщо позиції немає — скасуй лише точно відповідні залишкові "
            "захисні ордери. Потім натисни «Оновити». Для перегляду WSP і "
            "журналу перейди в «Моніторинг»."
        ),
        "pl": (
            "Te zlecenia brokera są w LGE tylko do odczytu. Znajdź je w TWS "
            "→ Orders według symbolu, typu, ceny, permId, parentId, clientId "
            "i OCA. Dla zleceń innego clientId IB może zwrócić orderId=0; "
            "wtedy użyj permId/clientId/parentId/OCA. LGE nie wymyśla numerów "
            "wierszy TWS takich jak 6.1/6.2. Rozwiąż pozycję wraz z ochroną "
            "albo anuluj wyłącznie dokładnie pasujące osierocone zlecenia. "
            "Następnie kliknij Odśwież. Do WSP i dziennika przejdź przez "
            "Monitorowanie."
        ),
        "de": (
            "Diese Brokerorders sind in LGE schreibgeschützt. Suche sie in "
            "TWS → Orders nach Symbol, Typ, Preis, permId, parentId, clientId "
            "und OCA. Für Orders einer anderen clientId kann IB orderId=0 "
            "melden; nutze dann permId/clientId/parentId/OCA. LGE erfindet "
            "keine TWS-Zeilennummern wie 6.1/6.2. Kläre Position samt Schutz "
            "oder storniere nur exakt passende verwaiste Schutzorders. Danach "
            "Aktualisieren klicken. WSP und Journal findest du unter "
            "Überwachung."
        ),
        "fr": (
            "Ces ordres sont en lecture seule dans LGE. Retrouvez-les dans "
            "TWS → Orders par symbole, type, prix, permId, parentId, clientId "
            "et OCA. Pour un autre clientId, IB peut renvoyer orderId=0 ; "
            "utilisez alors permId/clientId/parentId/OCA. LGE n’invente pas "
            "de numéros de ligne TWS comme 6.1/6.2. Régularisez la position "
            "avec sa protection ou annulez uniquement les ordres orphelins "
            "correspondants. Cliquez ensuite sur Actualiser. Le WSP et le "
            "journal sont dans Surveillance."
        ),
    },
    "OrdersPage.statusExternalExposureSelected": {
        "uk": (
            "Зовнішня IB-експозиція {symbol}: {side} {volume}; стан доказів: "
            "{evidence}. Натисни «Вирішення питань узгодження», щоб побачити "
            "точні ідентифікатори ордерів TWS."
        ),
        "pl": (
            "Zewnętrzna ekspozycja IB {symbol}: {side} {volume}; dowody: "
            "{evidence}. Kliknij Rozwiąż uzgodnienie, aby zobaczyć dokładne "
            "identyfikatory zleceń TWS."
        ),
        "de": (
            "Externe IB-Exposition {symbol}: {side} {volume}; Nachweis: "
            "{evidence}. Klicke auf Abstimmung klären, um genaue TWS-"
            "Orderkennungen zu sehen."
        ),
        "fr": (
            "Exposition IB externe {symbol} : {side} {volume} ; preuves : "
            "{evidence}. Cliquez sur Résoudre le rapprochement pour voir les "
            "identifiants exacts des ordres TWS."
        ),
    },
    "WorkspaceDataSource.broker": {
        "uk": "Дані брокера",
        "pl": "Dane brokera",
    },
    "AlgorithmWorkspaceWindow.chartLatest": {
        "uk": "До поточного",
        "pl": "Do bieżącego",
    },
    "AlgorithmWorkspaceWindow.chartZoomOutHint": {
        "uk": (
            "Горизонтальний масштаб: зменшити. Клавіша: -. " "Миша: коліщатко вниз."
        ),
        "pl": ("Skala pozioma: pomniejsz. Klawisz: -. " "Mysz: kółko w dół."),
    },
    "AlgorithmWorkspaceWindow.chartZoomInHint": {
        "uk": (
            "Горизонтальний масштаб: збільшити. Клавіша: +. " "Миша: коліщатко вгору."
        ),
        "pl": ("Skala pozioma: powiększ. Klawisz: +. " "Mysz: kółko w górę."),
    },
    "AlgorithmWorkspaceWindow.chartVerticalZoomOutHint": {
        "uk": (
            "Вертикальний масштаб: зменшити. Клавіші: Ctrl+-. "
            "Миша: Ctrl+коліщатко вниз."
        ),
        "pl": (
            "Skala pionowa: pomniejsz. Klawisze: Ctrl+-. " "Mysz: Ctrl+kółko w dół."
        ),
    },
    "AlgorithmWorkspaceWindow.chartVerticalZoomInHint": {
        "uk": (
            "Вертикальний масштаб: збільшити. Клавіші: Ctrl++. "
            "Миша: Ctrl+коліщатко вгору."
        ),
        "pl": (
            "Skala pionowa: powiększ. Klawisze: Ctrl++. " "Mysz: Ctrl+kółko w górę."
        ),
    },
    "AlgorithmWorkspaceWindow.chartVerticalPanHint": {
        "uk": "Рух по вертикалі. Клавіші: ↑/↓.",
        "pl": "Ruch pionowy. Klawisze: ↑/↓.",
    },
    "AlgorithmWorkspaceWindow.chartLatestHint": {
        "uk": "Перейти до останнього вже обробленого бара. Клавіша: End.",
        "pl": "Przejdź do ostatniej już przetworzonej świecy. Klawisz: End.",
    },
    "AlgorithmWorkspaceWindow.chartNavigationHint": {
        "uk": (
            "Перетягування: рух по горизонталі. ←/→: рух по горизонталі. "
            "↑/↓: рух по вертикалі. Коліщатко миші: горизонтальний "
            "масштаб. Ctrl+коліщатко: вертикальний масштаб. +/-: "
            "горизонтальний масштаб. Ctrl++/Ctrl+-: вертикальний масштаб. "
            "Home: на початок. End: до поточного. Replay SL/TP: наведи "
            "курсор на лінію SL або TP і перетягни її вгору/вниз; доступно "
            "лише на паузі. Entry не переміщується."
        ),
        "pl": (
            "Przeciąganie: ruch poziomy. ←/→: ruch poziomy. "
            "↑/↓: ruch pionowy. Kółko myszy: skala pozioma. "
            "Ctrl+kółko: skala pionowa. +/-: skala pozioma. "
            "Ctrl++/Ctrl+-: skala pionowa. Home: na początek. "
            "End: do bieżącego. Replay SL/TP: najedź na linię SL lub TP "
            "i przeciągnij ją pionowo; dostępne tylko podczas pauzy. "
            "Entry nie można przesuwać."
        ),
    },
    "AlgorithmWorkspaceWindow.chartStopLossDragHint": {
        "uk": (
            "Перетягни по вертикалі, щоб змінити Stop Loss. "
            "Replay має бути на паузі."
        ),
        "pl": (
            "Przeciągnij pionowo, aby zmienić Stop Loss. " "Replay musi być wstrzymany."
        ),
    },
    "AlgorithmWorkspaceWindow.chartTakeProfitDragHint": {
        "uk": (
            "Перетягни по вертикалі, щоб змінити Take Profit. "
            "Replay має бути на паузі."
        ),
        "pl": (
            "Przeciągnij pionowo, aby zmienić Take Profit. "
            "Replay musi być wstrzymany."
        ),
    },
    "AlgorithmWorkspaceWindow.chartDrawSegmentHint": {
        "uk": (
            "Похилий відрізок. Натисни кнопку, щоб увімкнути; натисни ще раз, "
            "щоб вимкнути. ПКМ — перша точка, далі рух миші. ПКМ — завершити "
            "лінію. ЛКМ під час побудови — завершити поточний відрізок і "
            "продовжити ламану з цієї ж точки."
        ),
    },
    "AlgorithmWorkspaceWindow.chartDrawHorizontalHint": {
        "uk": (
            "Горизонтальний відрізок. Натисни кнопку, щоб увімкнути; натисни "
            "ще раз, щоб вимкнути. ПКМ — перша точка, далі рух миші, ПКМ — "
            "друга точка."
        ),
    },
    "AlgorithmWorkspaceWindow.chartDrawVerticalHint": {
        "uk": (
            "Вертикальний відрізок. Натисни кнопку, щоб увімкнути; натисни ще "
            "раз, щоб вимкнути. ПКМ — перша точка, далі рух миші, ПКМ — друга "
            "точка."
        ),
    },
    "AlgorithmWorkspaceWindow.chartDrawClearHint": {
        "uk": "Очистити всі тимчасові ручні лінії на поточній діаграмі.",
    },
    "AlgorithmWorkspaceWindow.chartDrawingStartLabel": {
        "uk": "Початок",
    },
    "AlgorithmWorkspaceWindow.chartDrawingEndLabel": {
        "uk": "Кінець",
    },
    "AlgorithmWorkspaceWindow.chartDrawingLineLabel": {
        "uk": "Лінія",
    },
    "AlgorithmWorkspaceWindow.chartDrawingTimeLabel": {
        "uk": "Час UTC",
    },
    "AlgorithmWorkspaceWindow.chartDrawingValueLabel": {
        "uk": "Значення",
    },
    "AlgorithmWorkspaceWindow.btnHistoryDownload": {
        "uk": "Завантажити історію",
        "pl": "Pobierz historię",
    },
    "AlgorithmWorkspaceWindow.accountRuntimeIdTooltip": {
        "uk": "Внутрішній ID рахунку: {account_id}",
        "pl": "Wewnętrzny identyfikator konta: {account_id}",
    },
    "AlgorithmWorkspaceWindow.btnReplaySettings": {
        "uk": "Налаштування Replay",
        "pl": "Ustawienia Replay",
    },
    "AlgorithmWorkspaceWindow.replayConfiguredTooltip": {
        "uk": "Replay налаштовано: {source}",
        "pl": "Replay skonfigurowano: {source}",
    },
    "AlgorithmWorkspaceWindow.tabPosition": {
        "uk": "Позиція",
        "pl": "Pozycja",
    },
    "AlgorithmWorkspaceJournal.lblCategory": {
        "uk": "Категорія:",
        "pl": "Kategoria:",
    },
    "AlgorithmWorkspaceJournal.lblLevel": {
        "uk": "Рівень:",
        "pl": "Poziom:",
    },
    "AlgorithmWorkspaceJournal.lblSearch": {
        "uk": "Пошук:",
        "pl": "Szukaj:",
    },
    "AlgorithmWorkspaceJournal.searchPlaceholder": {
        "uk": "Подія, код або текст...",
        "pl": "Zdarzenie, kod lub tekst...",
    },
    "AlgorithmWorkspaceFilter.all": {
        "uk": "Усі",
        "pl": "Wszystkie",
    },
    "AlgorithmWorkspaceFilter.result": {
        "uk": "Результат:",
        "pl": "Wynik:",
    },
    "AlgorithmWorkspaceFilter.direction": {
        "uk": "Напрямок:",
        "pl": "Kierunek:",
    },
    "AlgorithmWorkspaceFilter.reason": {
        "uk": "Причина:",
        "pl": "Przyczyna:",
    },
    "AlgorithmWorkspaceFilter.regime": {
        "uk": "Режим:",
        "pl": "Tryb:",
    },
    "AlgorithmWorkspaceFilter.regimeUndefined": {
        "uk": "Не визначено",
        "pl": "Nie określono",
    },
    "AlgorithmWorkspaceFilter.closeReason": {
        "uk": "Причина закриття:",
        "pl": "Powód zamknięcia:",
    },
    "AlgorithmWorkspaceFilter.status": {
        "uk": "Статус:",
        "pl": "Status:",
    },
    "AlgorithmWorkspaceFilter.pnl": {
        "uk": "Прибуток:",
        "pl": "Wynik:",
    },
    "AlgorithmWorkspaceFilter.accepted": {
        "uk": "Прийнято",
        "pl": "Przyjęto",
    },
    "AlgorithmWorkspaceFilter.rejected": {
        "uk": "Відхилено",
        "pl": "Odrzucono",
    },
    "AlgorithmWorkspaceFilter.pnlProfit": {
        "uk": "Прибуток +",
        "pl": "Zysk +",
    },
    "AlgorithmWorkspaceFilter.pnlLoss": {
        "uk": "Збиток -",
        "pl": "Strata -",
    },
    "AlgorithmWorkspaceFilter.pnlZero": {
        "uk": "Нуль",
        "pl": "Zero",
    },
    "AlgorithmWorkspaceJournal.categoryAll": {
        "uk": "Усі",
        "pl": "Wszystkie",
    },
    "AlgorithmWorkspaceJournal.categoryRuntime": {
        "uk": "Виконання",
        "pl": "Wykonanie",
    },
    "AlgorithmWorkspaceJournal.categoryMarket": {
        "uk": "Ринок",
        "pl": "Rynek",
    },
    "AlgorithmWorkspaceJournal.categorySignal": {
        "uk": "Сигнали",
        "pl": "Sygnały",
    },
    "AlgorithmWorkspaceJournal.categoryGuard": {
        "uk": "Захист",
        "pl": "Zabezpieczenia",
    },
    "AlgorithmWorkspaceJournal.categoryBroker": {
        "uk": "Брокер",
        "pl": "Broker",
    },
    "AlgorithmWorkspaceJournal.categoryError": {
        "uk": "Помилки",
        "pl": "Błędy",
    },
    "AlgorithmWorkspaceJournal.levelAll": {
        "uk": "Усі",
        "pl": "Wszystkie",
    },
    "AlgorithmWorkspaceJournal.levelInfo": {
        "uk": "Інформація",
        "pl": "Informacja",
    },
    "AlgorithmWorkspaceJournal.levelWarning": {
        "uk": "Попередження",
        "pl": "Ostrzeżenie",
    },
    "AlgorithmWorkspaceJournal.levelError": {
        "uk": "Помилка",
        "pl": "Błąd",
    },
    "AlgorithmWorkspaceJournal.showMarketTicks": {
        "uk": "Показувати кожен ринковий тік",
        "pl": "Pokazuj każdy tick rynkowy",
    },
    "AlgorithmWorkspaceJournal.empty": {
        "uk": "Немає записів, що відповідають вибраним фільтрам.",
        "pl": "Brak wpisów zgodnych z wybranymi filtrami.",
    },
    "AlgorithmWorkspaceState.restored": {
        "uk": "ВІДНОВЛЕНО",
        "pl": "PRZYWRÓCONO",
    },
    "AlgorithmWorkspaceState.stopped": {
        "uk": "ЗУПИНЕНО",
        "pl": "ZATRZYMANO",
    },
    "AlgorithmWorkspaceState.starting": {
        "uk": "ЗАПУСК",
        "pl": "STARTUJE",
    },
    "AlgorithmWorkspaceState.running": {
        "uk": "ПРАЦЮЄ",
        "pl": "DZIAŁA",
    },
    "AlgorithmWorkspaceState.stopping": {
        "uk": "ЗУПИНЕННЯ",
        "pl": "ZATRZYMUJE",
    },
    "AlgorithmWorkspaceState.error": {
        "uk": "ПОМИЛКА",
        "pl": "BŁĄD",
    },
    "AlgorithmReplayState.ready": {
        "uk": "ГОТОВО",
        "pl": "GOTOWE",
    },
    "AlgorithmReplayState.running": {
        "uk": "ВІДТВОРЕННЯ",
        "pl": "ODTWARZANIE",
    },
    "AlgorithmReplayState.paused": {
        "uk": "ПАУЗА",
        "pl": "PAUZA",
    },
    "AlgorithmReplayState.completed": {
        "uk": "ЗАВЕРШЕНО",
        "pl": "ZAKOŃCZONO",
    },
    "AlgorithmReplayState.stopped": {
        "uk": "ЗУПИНЕНО",
        "pl": "ZATRZYMANO",
    },
    "AlgorithmWorkspaceStartupPhase.idle": {
        "uk": "ОЧІКУВАННЯ",
        "pl": "OCZEKIWANIE",
    },
    "AlgorithmWorkspaceStartupPhase.loadData": {
        "uk": "ЗАВАНТАЖЕННЯ",
        "pl": "WCZYTYWANIE",
    },
    "AlgorithmWorkspaceStartupPhase.warmup": {
        "uk": "ПРОГРІВ",
        "pl": "ROZGRZEWKA",
    },
    "AlgorithmWorkspaceStartupPhase.waitBroker": {
        "uk": "ОЧІКУВАННЯ БРОКЕРА",
        "pl": "OCZEKIWANIE NA BROKERA",
    },
    "CTraderConnectionDialog.btnClose": {
        "uk": "Закрити",
        "pl": "Zamknij",
    },
    "IBConnectionDialog.btnClose": {
        "uk": "Закрити",
        "pl": "Zamknij",
    },
    "SettingsPageTrading.btnClose": {
        "uk": "Закрити",
        "pl": "Zamknij",
    },
    "AlgorithmWorkspaceStartupPhase.waitSpread": {
        "uk": "ОЧІКУВАННЯ СПРЕДУ",
        "pl": "OCZEKIWANIE NA SPREAD",
    },
    "AlgorithmWorkspaceStartupPhase.ready": {
        "uk": "ГОТОВО",
        "pl": "GOTOWE",
    },
    "AlgorithmWorkspaceStartupPhase.running": {
        "uk": "ПРАЦЮЄ",
        "pl": "DZIAŁA",
    },
    "AlgorithmWorkspaceParametersDialog.workspace": {
        "uk": "Робочий простір: {name}",
        "pl": "Obszar roboczy: {name}",
    },
    "AlgorithmWorkspaceParametersDialog.windowTitle": {
        "uk": "Параметри WSP",
        "pl": "Parametry WSP",
    },
    "AlgorithmWorkspaceParametersDialog.context": {
        "uk": "Редакція: {edition} | Стан WSP: {runtime_state}",
        "pl": "Edycja: {edition} | Stan WSP: {runtime_state}",
    },
    "AlgorithmWorkspaceParametersDialog.columnParameter": {
        "uk": "Параметр",
        "pl": "Parametr",
    },
    "AlgorithmWorkspaceParametersDialog.columnValue": {
        "uk": "Значення",
        "pl": "Wartość",
    },
    "AlgorithmWorkspaceParametersDialog.grpValueEditor": {
        "uk": "Значення параметра",
        "pl": "Wartość parametru",
    },
    "AlgorithmWorkspaceParametersDialog.grpParameterDetails": {
        "uk": "Відомості про параметр",
        "pl": "Informacje o parametrze",
    },
    "AlgorithmWorkspaceParametersDialog.lblStatus": {
        "uk": "Статус:",
        "pl": "Status:",
    },
    "AlgorithmWorkspaceParametersDialog.lblFeature": {
        "uk": "Функція:",
        "pl": "Funkcja:",
    },
    "AlgorithmWorkspaceParametersDialog.lblConstraints": {
        "uk": "Обмеження:",
        "pl": "Ograniczenia:",
    },
    "AlgorithmWorkspaceParametersDialog.selectParameterTitle": {
        "uk": "Вибери параметр",
        "pl": "Wybierz parametr",
    },
    "AlgorithmWorkspaceParametersDialog.selectParameterDescription": {
        "uk": "Вибери групу та параметр у дереві ліворуч.",
        "pl": "Wybierz grupę i parametr w drzewie po lewej stronie.",
    },
    "AlgorithmWorkspaceParametersDialog.noSelection": {
        "uk": "Параметр не вибрано.",
        "pl": "Nie wybrano parametru.",
    },
    "AlgorithmWorkspaceParametersDialog.emptyGroup": {
        "uk": "Для цієї групи параметри ще не визначено.",
        "pl": "Dla tej grupy nie zdefiniowano jeszcze parametrów.",
    },
    "AlgorithmWorkspaceParametersDialog.selectParameter": {
        "uk": "Вибери параметр у цій групі.",
        "pl": "Wybierz parametr w tej grupie.",
    },
    "AlgorithmWorkspaceParametersDialog.valueType": {
        "uk": "Тип: {value_type}",
        "pl": "Typ: {value_type}",
    },
    "AlgorithmWorkspaceParametersDialog.minimum": {
        "uk": "Мінімум: {value}",
        "pl": "Minimum: {value}",
    },
    "AlgorithmWorkspaceParametersDialog.maximum": {
        "uk": "Максимум: {value}",
        "pl": "Maksimum: {value}",
    },
    "AlgorithmWorkspaceParametersDialog.step": {
        "uk": "Крок: {value}",
        "pl": "Krok: {value}",
    },
    "AlgorithmWorkspaceParametersDialog.allowedValues": {
        "uk": "Допустимі значення: {values}",
        "pl": "Dozwolone wartości: {values}",
    },
    "AlgorithmWorkspaceParametersDialog.booleanYes": {
        "uk": "Так",
        "pl": "Tak",
    },
    "AlgorithmWorkspaceParametersDialog.booleanNo": {
        "uk": "Ні",
        "pl": "Nie",
    },
    "AlgorithmWorkspaceParametersDialog.btnClose": {
        "uk": "Закрити",
        "pl": "Zamknij",
    },
    "AlgorithmWorkspaceParametersDialog.unsavedTitle": {
        "uk": "Незбережені зміни",
        "pl": "Niezapisane zmiany",
    },
    "AlgorithmWorkspaceParametersDialog.unsavedQuestion": {
        "uk": "Закрити без збереження змін параметрів?",
        "pl": "Zamknąć bez zapisywania zmian parametrów?",
    },
    "AlgorithmWorkspaceParametersDialog.grpRuntime": {
        "uk": "Захисні умови виконання",
        "pl": "Zabezpieczenia wykonania",
    },
    "AlgorithmWorkspaceParametersDialog.grpRisk": {
        "uk": "Ризик і захист прибутку",
        "pl": "Ryzyko i ochrona zysku",
    },
    "AlgorithmWorkspaceParametersDialog.lblAlligatorConfirmation": {
        "uk": "Підтвердження Alligator:",
        "pl": "Potwierdzenie Alligatora:",
    },
    "AlgorithmWorkspaceParametersDialog.lblWarmupBars": {
        "uk": "Бари прогріву:",
        "pl": "Liczba barów rozgrzewki:",
    },
    "AlgorithmWorkspaceParametersDialog.lblProfitDrawdown": {
        "uk": "Ліміт відкату прибутку для закриття:",
        "pl": "Próg zamknięcia przy obsunięciu zysku:",
    },
    "AlgorithmWorkspaceParametersDialog.alligatorSameTimeframe": {
        "uk": "Той самий таймфрейм",
        "pl": "Ten sam interwał",
    },
    "AlgorithmWorkspaceParametersDialog.alligatorHigher1": {
        "uk": "На один таймфрейм вище",
        "pl": "Jeden interwał wyżej",
    },
    "AlgorithmWorkspaceParametersDialog.alligatorHigher2": {
        "uk": "На два таймфрейми вище",
        "pl": "Dwa interwały wyżej",
    },
    "AlgorithmWorkspaceParametersDialog.alligatorDisabled": {
        "uk": "Вимкнено",
        "pl": "Wyłączone",
    },
    "AlgorithmWorkspaceWindow.lblOrders": {
        "pl": "Zlecenia:",
    },
    "AlgorithmWorkspaceWindow.lblPositions": {
        "pl": "Pozycje:",
    },
    "AlgorithmWorkspaceWindow.lblProfitDrawdown": {
        "pl": "Obsunięcie:",
    },
    "AlgorithmWorkspaceWindow.lblTimeframe": {
        "pl": "Interwał:",
    },
    "AlgorithmWorkspaceWindow.tabOrders": {
        "pl": "Zlecenia",
    },
    "AlgorithmWorkspaceWindow.colOrderId": {
        "pl": "ID zlecenia",
    },
    "AlgorithmWorkspaceWindow.colSide": {
        "pl": "Kierunek",
    },
    "AlgorithmWorkspaceWindow.colVolume": {
        "pl": "Wolumen",
    },
    "AlgorithmWorkspaceWindow.btnReplayResume": {
        "pl": "Wznów",
    },
    "AlgorithmWorkspaceWindow.btnReplayTick": {
        "uk": "Тік",
        "pl": "Tik",
    },
    "AlgorithmWorkspaceWindow.replayTickHint": {
        "uk": "Обробити одну найдрібнішу execution-подію Replay.",
        "pl": "Przetwórz jedno najmniejsze zdarzenie wykonania Replay.",
    },
    "AlgorithmWorkspaceWindow.replayTickLabel": {
        "uk": "Тік",
        "pl": "Tik",
    },
    "AlgorithmWorkspaceParametersDialog.grpSignal": {
        "pl": "Potwierdzenie sygnału",
    },
    "AlgorithmWorkspaceParametersDialog.lblMacdSignalMode": {
        "pl": "Tryb sygnału MACD:",
    },
    "AlgorithmWorkspaceParametersDialog.lblSpreadLimit": {
        "pl": "Maksymalny spread:",
    },
    "AlgorithmWorkspaceParametersDialog.lblRiskPercent": {
        "pl": "Procent ryzyka:",
    },
    "AlgorithmWorkspaceParametersDialog.lblMaximumPositionVolume": {
        "pl": "Maksymalny wolumen pozycji:",
    },
    "AlgorithmWorkspaceParametersDialog.note": {
        "uk": (
            "MACD і Alligator — перші незалежні тестові компоненти. Інші "
            "сигнали та фільтри додаватимуться по одному. Політику спреду "
            "та прогрів обчислює Runtime; legacy-значення зберігаються для "
            "сумісності."
        ),
        "pl": (
            "MACD i Alligator są pierwszymi niezależnymi komponentami "
            "testowymi. Kolejne sygnały i filtry będą dodawane pojedynczo. "
            "Politykę spreadu i rozgrzewkę oblicza Runtime; wartości legacy "
            "pozostają zapisane dla zgodności."
        ),
    },
    "AlgorithmWorkspaceParametersDialog.btnSave": {
        "pl": "Zapisz",
    },
    "AlgorithmWorkspaceParametersDialog.btnCancel": {
        "pl": "Anuluj",
    },
    "WorkspaceParameterGroup.filters.title": {
        "uk": "Фільтри та підтвердження",
        "pl": "Filtry i potwierdzenia",
    },
    "WorkspaceParameterGroup.filters.description": {
        "uk": (
            "Незалежні фільтри та підтвердження, які додаються по одному "
            "під час тестування."
        ),
        "pl": "Niezależne filtry i potwierdzenia dodawane pojedynczo podczas testów.",
    },
    "WorkspaceParameter.macdEnabled.title": {
        "uk": "Увімкнути джерело сигналу MACD",
        "pl": "Włącz źródło sygnału MACD",
    },
    "WorkspaceParameter.macdEnabled.description": {
        "uk": "Використовувати MACD як окреме джерело сигналів WSP.",
        "pl": "Używać MACD jako niezależnego źródła sygnałów WSP.",
    },
    "WorkspaceParameter.macdSignalMode.title": {
        "uk": "Режим сигналу MACD",
        "pl": "Tryb sygnału MACD",
    },
    "WorkspaceParameter.macdSignalMode.description": {
        "uk": "Визначає спосіб формування сигналу незалежним джерелом MACD.",
        "pl": "Określa sposób tworzenia sygnału przez niezależne źródło MACD.",
    },
    "WorkspaceParameter.macdExtremumMinProminence.title": {
        "uk": "MACD: мін. виразність екстремуму",
        "pl": "MACD: min. wyrazistość ekstremum",
        "de": "MACD: min. Extremum-Prominenz",
        "fr": "MACD : proéminence min. de l’extrémum",
    },
    "WorkspaceParameter.macdExtremumMinProminence.description": {
        "uk": (
            "Мінімальний відрив локального екстремуму гістограми H "
            "від сусідніх значень."
        ),
        "pl": (
            "Minimalna odległość lokalnego ekstremum histogramu H "
            "od wartości sąsiednich."
        ),
        "de": (
            "Mindestabstand des lokalen H-Histogramm-Extremums "
            "zu den benachbarten Werten."
        ),
        "fr": (
            "Écart minimal de l’extrémum local de l’histogramme H "
            "par rapport aux valeurs voisines."
        ),
    },
    "WorkspaceParameter.macdExtremumToCrossMinDistance.title": {
        "uk": "MACD: мін. відстань екстремум → перетин",
        "pl": "MACD: min. odległość ekstremum → przecięcie",
        "de": "MACD: min. Abstand Extremum → Kreuzung",
        "fr": "MACD : distance min. extrémum → croisement",
    },
    "WorkspaceParameter.macdExtremumToCrossMinDistance.description": {
        "uk": "Мінімальне |H[extremum]| перед перетином MACD і Signal.",
        "pl": "Minimalne |H[extremum]| przed przecięciem MACD i Signal.",
        "de": "Minimales |H[extremum]| vor der Kreuzung von MACD und Signal.",
        "fr": (
            "Valeur minimale de |H[extremum]| avant le croisement " "de MACD et Signal."
        ),
    },
    "WorkspaceParameter.macdCrossMinAngle.title": {
        "uk": "MACD: мін. кут перетину, °",
        "pl": "MACD: min. kąt przecięcia, °",
        "de": "MACD: min. Kreuzungswinkel, °",
        "fr": "MACD : angle min. de croisement, °",
    },
    "WorkspaceParameter.macdCrossMinAngle.description": {
        "uk": ("Мінімальний калібрований кут між MACD і Signal " "у режимі EXTENDED."),
        "pl": ("Minimalny skalibrowany kąt między MACD i Signal " "w trybie EXTENDED."),
        "de": (
            "Kalibrierter Mindestwinkel zwischen MACD und Signal " "im EXTENDED-Modus."
        ),
        "fr": ("Angle calibré minimal entre MACD et Signal " "en mode EXTENDED."),
    },
    "WorkspaceParameter.alligatorEnabled.title": {
        "uk": "Увімкнути фільтр Alligator",
        "pl": "Włącz filtr Alligator",
    },
    "WorkspaceParameter.alligatorEnabled.description": {
        "uk": "Використовувати Alligator як окремий фільтр сигналів.",
        "pl": "Używać Alligatora jako niezależnego filtra sygnałów.",
    },
    "WorkspaceParameter.alligatorConfirmation.title": {
        "uk": "Режим підтвердження Alligator",
        "pl": "Tryb potwierdzenia Alligatora",
    },
    "WorkspaceParameter.alligatorConfirmation.description": {
        "uk": "Визначає таймфрейм незалежного фільтра Alligator.",
        "pl": "Określa interwał niezależnego filtra Alligatora.",
    },
    "AlgorithmWorkspaceParametersDialog.macdLinear": {
        "pl": "Liniowy",
    },
    "AlgorithmWorkspaceParametersDialog.macdExtended": {
        "pl": "Rozszerzony",
    },
    "AlgorithmWorkspaceHistoryDownloadDialog.windowTitle": {
        "uk": "Завантаження історичних даних",
        "pl": "Pobieranie danych historycznych",
    },
    "AlgorithmWorkspaceHistoryDownloadDialog.workspace": {
        "uk": "Робочий простір: {name}",
        "pl": "Obszar roboczy: {name}",
    },
    "AlgorithmWorkspaceHistoryDownloadDialog.grpBinding": {
        "uk": "Джерело брокерських даних",
        "pl": "Źródło danych brokera",
    },
    "AlgorithmWorkspaceHistoryDownloadDialog.lblBroker": {
        "uk": "Брокер:",
    },
    "AlgorithmWorkspaceHistoryDownloadDialog.lblAccount": {
        "uk": "Обліковий запис:",
    },
    "AlgorithmWorkspaceHistoryDownloadDialog.lblSymbol": {
        "uk": "Символ:",
    },
    "AlgorithmWorkspaceHistoryDownloadDialog.lblTimeframe": {
        "uk": "Таймфрейм:",
        "pl": "Interwał:",
    },
    "AlgorithmWorkspaceHistoryDownloadDialog.grpRange": {
        "uk": "Період завантаження",
        "pl": "Okres pobierania",
    },
    "AlgorithmWorkspaceHistoryDownloadDialog.lblStartDate": {
        "uk": "Дата початку:",
        "pl": "Data początkowa:",
    },
    "AlgorithmWorkspaceHistoryDownloadDialog.lblEndDate": {
        "uk": "Дата завершення:",
        "pl": "Data końcowa:",
    },
    "AlgorithmWorkspaceHistoryDownloadDialog.lblTimezone": {
        "uk": "Часовий пояс періоду завантаження:",
        "pl": "Strefa czasowa okresu pobierania:",
    },
    "AlgorithmWorkspaceHistoryDownloadDialog.grpDestination": {
        "uk": "Збереження CSV",
        "pl": "Docelowy plik CSV",
    },
    "AlgorithmWorkspaceHistoryDownloadDialog.lblPlannedFile": {
        "uk": "Запланований CSV-файл:",
        "pl": "Planowany plik CSV:",
    },
    "AlgorithmWorkspaceHistoryDownloadDialog.lblDestinationFolder": {
        "uk": "Папка збереження:",
        "pl": "Folder docelowy:",
    },
    "AlgorithmWorkspaceHistoryDownloadDialog.grpProgress": {
        "uk": "Стан завантаження",
        "pl": "Stan pobierania",
    },
    "AlgorithmWorkspaceHistoryDownloadDialog.statusReady": {
        "uk": "Готово до завантаження.",
        "pl": "Gotowe do pobrania.",
    },
    "AlgorithmWorkspaceHistoryDownloadDialog.statusDownloading": {
        "uk": "Завантаження історичних даних з {broker}...",
        "pl": "Pobieranie danych historycznych z {broker}...",
    },
    "AlgorithmWorkspaceHistoryDownloadDialog.statusProgress": {
        "uk": (
            "Завантаження: {percent}% · запитів {requests} · "
            "барів {bars} · найраніший бар {covered_start} UTC"
        ),
        "pl": (
            "Pobieranie: {percent}% · zapytań {requests} · "
            "barów {bars} · najwcześniejszy bar {covered_start} UTC"
        ),
    },
    "AlgorithmWorkspaceHistoryDownloadDialog.statusCompleted": {
        "uk": "Завершено: {bars} барів у {requests} запитах, " "{first} — {last}.",
        "pl": "Zakończono: {bars} barów w {requests} zapytaniach, {first} — {last}.",
    },
    "AlgorithmWorkspaceHistoryDownloadDialog.note": {
        "uk": (
            "Вибрані дати визначають брокерський запит. Остаточна назва "
            "CSV використовує перший і останній фактично отримані бари."
        ),
        "pl": (
            "Wybrane daty określają zapytanie do brokera. Ostateczna "
            "nazwa pliku CSV wykorzystuje daty pierwszego i ostatniego "
            "faktycznie otrzymanego baru."
        ),
    },
    "AlgorithmWorkspaceHistoryDownloadDialog.btnDownload": {
        "uk": "Завантажити",
        "pl": "Pobierz",
    },
    "AlgorithmWorkspaceHistoryDownloadDialog.btnUseForReplay": {
        "uk": "Використати для Replay",
        "pl": "Użyj w Replay",
    },
    "AlgorithmWorkspaceHistoryDownloadDialog.btnClose": {
        "uk": "Закрити",
        "pl": "Zamknij",
    },
    "AlgorithmWorkspaceHistoryDownloadDialog.completedTitle": {
        "uk": "Завантаження завершено",
        "pl": "Pobieranie historii zakończone",
    },
    "AlgorithmWorkspaceHistoryDownloadDialog.completed": {
        "uk": (
            "Історичний CSV збережено: {file}\n\n"
            "Бари: {bars}\nЗапити: {requests}\n"
            "Початок завантаження: {download_started}\n"
            "Кінець завантаження: {download_finished}\n"
            "Тривалість завантаження: {download_duration}\n"
            "Запитаний період: {requested_first} — {requested_last}\n"
            "Фактичний період: {first} — {last}{coverage_note}"
        ),
        "pl": (
            "Historyczny plik CSV zapisano: {file}\n\n"
            "Bary: {bars}\nZapytania: {requests}\n"
            "Początek pobierania: {download_started}\n"
            "Koniec pobierania: {download_finished}\n"
            "Czas pobierania: {download_duration}\n"
            "Żądany okres: {requested_first} — {requested_last}\n"
            "Rzeczywisty okres: {first} — {last}{coverage_note}"
        ),
    },
    "AlgorithmWorkspaceHistoryDownloadDialog.coverageStartsLater": {
        "uk": (
            "Брокер не повернув барів між запитаним початком і "
            "першим фактичним баром. Це нормально для вихідних, "
            "свят, закритого ринку або недоступної історії брокера."
        ),
        "pl": (
            "Broker nie zwrócił barów między żądanym początkiem a "
            "pierwszym faktycznie otrzymanym barem. Jest to normalne "
            "w weekendy, święta, przy zamkniętym rynku lub braku danej "
            "historii po stronie brokera."
        ),
    },
    "AlgorithmWorkspaceHistoryDownloadDialog.failedTitle": {
        "uk": "Помилка завантаження",
        "pl": "Błąd pobierania",
    },
    "AlgorithmWorkspaceHistoryDownloadDialog.failed": {
        "uk": "Не вдалося завантажити історичні дані.\n\nТехнічні деталі: {details}",
        "pl": (
            "Nie udało się pobrać danych historycznych.\n\n"
            "Szczegóły techniczne: {details}"
        ),
    },
    "AlgorithmWorkspaceHistoryDownloadDialog.ibInvalidEndDateTime": {
        "uk": (
            "IB відхилив запит через некоректний формат кінцевої "
            "дати або часу.\n\nТехнічні деталі: {details}"
        ),
    },
    "AlgorithmWorkspaceHistoryDownloadDialog.messageOk": {
        "uk": "Зрозуміло",
        "pl": "Rozumiem",
    },
    "AlgorithmWorkspaceHistoryDownloadDialog.unavailable": {
        "uk": "Завантаження історії брокера недоступне.",
        "pl": "Pobieranie historii z brokera jest niedostępne.",
    },
    "AlgorithmWorkspaceReplayDialog.windowTitle": {
        "uk": "Налаштування тесту Replay",
        "pl": "Ustawienia testu Replay",
    },
    "AlgorithmWorkspaceReplayDialog.workspace": {
        "uk": "Робочий простір: {name}",
        "pl": "Obszar roboczy: {name}",
    },
    "AlgorithmWorkspaceReplayDialog.grpSource": {
        "uk": "Джерело Replay",
        "pl": "Źródło Replay",
    },
    "AlgorithmWorkspaceReplayDialog.lblSourceType": {
        "pl": "Typ źródła:",
    },
    "AlgorithmWorkspaceReplayDialog.lblFilePath": {
        "pl": "Historyczny plik CSV:",
    },
    "AlgorithmWorkspaceReplayDialog.lblSourceTimezone": {
        "pl": "Strefa czasowa źródła CSV:",
    },
    "AlgorithmWorkspaceReplayDialog.grpCsv": {
        "pl": "Format CSV i dane rynkowe",
    },
    "AlgorithmWorkspaceReplayDialog.lblSourceTimeframe": {
        "uk": "Таймфрейм джерела CSV (авто):",
        "pl": "Interwał źródłowego CSV (auto):",
    },
    "AlgorithmWorkspaceReplayDialog.sourceTimeframeDetected": {
        "uk": "Автоматично визначено за часовими мітками CSV: {timeframe}",
        "pl": "Wykryto automatycznie ze znaczników czasu CSV: {timeframe}",
    },
    "AlgorithmWorkspaceReplayDialog.sourceTimeframeManualFallback": {
        "uk": ("Таймфрейм CSV не вдалося визначити надійно. " "Виберіть його вручну."),
        "pl": (
            "Nie udało się wiarygodnie wykryć interwału CSV. " "Wybierz go ręcznie."
        ),
    },
    "AlgorithmWorkspaceReplayDialog.lblDelimiter": {
        "pl": "Separator kolumn:",
    },
    "AlgorithmWorkspaceReplayDialog.lblSpread": {
        "pl": "Domyślny spread:",
    },
    "AlgorithmWorkspaceReplayDialog.btnSave": {
        "pl": "Zapisz",
    },
    "AlgorithmWorkspaceReplayDialog.btnCancel": {
        "pl": "Anuluj",
    },
    "AlgorithmWorkspaceReplayDialog.sourceSynthetic": {
        "pl": "Syntetyczne dane testowe",
    },
    "AlgorithmWorkspaceReplayDialog.lblSourceName": {
        "uk": "Назва джерела:",
        "pl": "Nazwa źródła:",
    },
    "AlgorithmWorkspaceReplayDialog.btnBrowse": {
        "uk": "Огляд...",
        "pl": "Przeglądaj...",
    },
    "AlgorithmWorkspaceReplayDialog.btnDownloadCtrader": {
        "uk": "Завантажити з cTrader...",
    },
    "AlgorithmWorkspaceReplayDialog.btnDownloadIb": {
        "uk": "Завантажити з IB...",
    },
    "AlgorithmWorkspaceReplayDialog.downloadStartRequired": {
        "uk": "Увімкніть початок періоду завантаження.",
    },
    "AlgorithmWorkspaceReplayDialog.downloadEndRequired": {
        "uk": "Увімкніть кінець періоду завантаження.",
    },
    "AlgorithmWorkspaceReplayDialog.downloadCompleted": {
        "uk": "Історичний CSV збережено: {file} ({bars} барів).",
    },
    "AlgorithmWorkspaceReplayDialog.downloadProgressTitle": {
        "uk": "Завантаження історії",
    },
    "AlgorithmWorkspaceReplayDialog.downloadInProgress": {
        "uk": "Завантаження історичних даних з {broker}...",
    },
    "AlgorithmWorkspaceReplayDialog.downloadCompletedTitle": {
        "uk": "Завантаження завершено",
    },
    "AlgorithmWorkspaceReplayDialog.downloadFailedTitle": {
        "uk": "Помилка завантаження",
    },
    "AlgorithmWorkspaceReplayDialog.downloadFailed": {
        "uk": "Не вдалося завантажити історичні дані.\n\nТехнічні деталі: {details}",
    },
    "AlgorithmWorkspaceReplayDialog.ibInvalidEndDateTime": {
        "uk": (
            "IB відхилив запит через некоректний формат кінцевої "
            "дати або часу.\n\nТехнічні деталі: {details}"
        ),
    },
    "AlgorithmWorkspaceReplayDialog.messageOk": {
        "uk": "Зрозуміло",
        "pl": "Rozumiem",
    },
    "AlgorithmWorkspaceReplayDialog.grpDownloadRange": {
        "uk": "Період завантаження історії",
    },
    "AlgorithmWorkspaceReplayDialog.lblDownloadStartDate": {
        "uk": "Дата початку:",
    },
    "AlgorithmWorkspaceReplayDialog.lblDownloadEndDate": {
        "uk": "Дата завершення:",
    },
    "AlgorithmWorkspaceReplayDialog.lblDownloadTimezone": {
        "uk": "Часовий пояс періоду завантаження:",
    },
    "AlgorithmWorkspaceReplayDialog.downloadTimezoneInvalid": {
        "uk": "Невідомий часовий пояс завантаження історії: {timezone}.",
    },
    "AlgorithmWorkspaceReplayDialog.downloadRangeInvalid": {
        "uk": (
            "Дата початку завантаження історії не може бути пізнішою "
            "за дату завершення."
        ),
    },
    "AlgorithmWorkspaceReplayDialog.grpRange": {
        "uk": "Період тесту Replay і часовий пояс",
        "pl": "Okres testu Replay i strefa czasowa",
    },
    "AlgorithmWorkspaceReplayDialog.chkStartEnabled": {
        "uk": "Початок тесту UTC:",
        "pl": "Początek testu UTC:",
    },
    "AlgorithmWorkspaceReplayDialog.chkEndEnabled": {
        "uk": "Кінець тесту UTC:",
        "pl": "Koniec testu UTC:",
    },
    "AlgorithmWorkspaceReplayDialog.lblDecimalSeparator": {
        "uk": "Десятковий роздільник:",
        "pl": "Separator dziesiętny:",
    },
    "AlgorithmWorkspaceReplayDialog.note": {
        "uk": (
            "Період тесту Replay обмежує прийняті рядки CSV. Часові "
            "мітки CSV без зони трактуються у часовому поясі джерела."
        ),
        "pl": (
            "Okres testu Replay filtruje akceptowane wiersze pliku CSV. "
            "Znaczniki czasu bez informacji o strefie są interpretowane "
            "w wybranej strefie czasowej źródła."
        ),
    },
    "AlgorithmWorkspaceReplayDialog.sourceCsv": {
        "uk": "Історичний CSV",
        "pl": "Historyczny plik CSV",
    },
    "AlgorithmWorkspaceReplayDialog.delimiterAuto": {
        "uk": "Визначати автоматично",
        "pl": "Wykryj automatycznie",
    },
    "AlgorithmWorkspaceReplayDialog.delimiterTab": {
        "uk": "Табуляція",
        "pl": "Tabulator",
    },
    "AlgorithmWorkspaceWindow.historyQuality": {
        "uk": ("пропущено {filtered} • розривів {gaps} • " "котирувань {quotes}"),
    },
    "AlgorithmWorkspaceParametersDialog.btnIndicatorProfiles": {
        "uk": "Профілі індикаторів…",
        "pl": "Profile wskaźników…",
    },
    "AlgorithmWorkspaceParametersDialog.indicatorProfiles": {
        "uk": "Профілі WSP: MACD — {macd}; Alligator — {alligator}",
    },
    "AlgorithmWorkspaceParametersDialog.indicatorProfilesPending": {
        "uk": (
            "Профілі WSP (зміни очікують збереження): MACD — {macd}; "
            "Alligator — {alligator}"
        ),
    },
    "WorkspaceIndicatorProfilesDialog.windowTitle": {
        "uk": "Профілі індикаторів WSP",
        "pl": "Profile wskaźników WSP",
    },
    "WorkspaceIndicatorProfilesDialog.workspace": {
        "uk": "Робочий простір: {name}",
        "pl": "Obszar roboczy: {name}",
    },
    "WorkspaceIndicatorProfilesDialog.currentBindings": {
        "uk": "Поточні профілі WSP: MACD — {macd}; Alligator — {alligator}",
        "pl": "Bieżące profile WSP: MACD — {macd}; Alligator — {alligator}",
    },
    "WorkspaceIndicatorProfilesDialog.columnProfile": {
        "uk": "Профіль",
        "pl": "Profil",
    },
    "WorkspaceIndicatorProfilesDialog.columnRevision": {
        "uk": "Редакція",
        "pl": "Wersja",
    },
    "WorkspaceIndicatorProfilesDialog.columnStatus": {
        "uk": "Статус",
        "pl": "Status",
    },
    "WorkspaceIndicatorProfilesDialog.btnNew": {
        "uk": "Новий",
        "pl": "Nowy",
    },
    "WorkspaceIndicatorProfilesDialog.btnDuplicate": {
        "uk": "Дублювати",
        "pl": "Duplikuj",
    },
    "WorkspaceIndicatorProfilesDialog.btnArchive": {
        "uk": "Архівувати",
        "pl": "Archiwizuj",
    },
    "WorkspaceIndicatorProfilesDialog.btnDelete": {
        "uk": "Видалити",
        "pl": "Usuń",
    },
    "WorkspaceIndicatorProfilesDialog.grpProfile": {
        "uk": "Профіль",
        "pl": "Profil",
    },
    "WorkspaceIndicatorProfilesDialog.lblName": {
        "uk": "Назва:",
        "pl": "Nazwa:",
    },
    "WorkspaceIndicatorProfilesDialog.lblIndicator": {
        "uk": "Індикатор:",
        "pl": "Wskaźnik:",
    },
    "WorkspaceIndicatorProfilesDialog.lblSourceReference": {
        "uk": "Джерело шаблону:",
        "pl": "Źródło szablonu:",
    },
    "WorkspaceIndicatorProfilesDialog.lblRevision": {
        "uk": "Редакція:",
        "pl": "Wersja:",
    },
    "WorkspaceIndicatorProfilesDialog.lblStatus": {
        "uk": "Статус:",
        "pl": "Status:",
    },
    "WorkspaceIndicatorProfilesDialog.noSelection": {
        "uk": "Вибери профіль індикатора ліворуч.",
        "pl": "Wybierz profil wskaźnika po lewej stronie.",
    },
    "WorkspaceIndicatorProfilesDialog.lblSource": {
        "uk": "Джерело ціни:",
        "pl": "Źródło ceny:",
    },
    "WorkspaceIndicatorProfilesDialog.lblFastPeriod": {
        "uk": "Швидкий період:",
        "pl": "Szybki okres:",
    },
    "WorkspaceIndicatorProfilesDialog.lblSlowPeriod": {
        "uk": "Повільний період:",
        "pl": "Wolny okres:",
    },
    "WorkspaceIndicatorProfilesDialog.lblSignalPeriod": {
        "uk": "Сигнальний період:",
        "pl": "Okres sygnału:",
    },
    "WorkspaceIndicatorProfilesDialog.lblOscillatorMa": {
        "uk": "Тип MA осцилятора:",
        "pl": "Typ MA oscylatora:",
    },
    "WorkspaceIndicatorProfilesDialog.lblSignalMa": {
        "uk": "Тип MA сигнальної лінії:",
        "pl": "Typ MA linii sygnału:",
    },
    "WorkspaceIndicatorProfilesDialog.lblShift": {
        "uk": "Зсув:",
        "pl": "Przesunięcie:",
    },
    "WorkspaceIndicatorProfilesDialog.lblJawPeriod": {
        "uk": "Період Jaw:",
        "pl": "Okres Jaw:",
    },
    "WorkspaceIndicatorProfilesDialog.lblJawShift": {
        "uk": "Зсув Jaw:",
        "pl": "Przesunięcie Jaw:",
    },
    "WorkspaceIndicatorProfilesDialog.lblTeethPeriod": {
        "uk": "Період Teeth:",
        "pl": "Okres Teeth:",
    },
    "WorkspaceIndicatorProfilesDialog.lblTeethShift": {
        "uk": "Зсув Teeth:",
        "pl": "Przesunięcie Teeth:",
    },
    "WorkspaceIndicatorProfilesDialog.lblLipsPeriod": {
        "uk": "Період Lips:",
        "pl": "Okres Lips:",
    },
    "WorkspaceIndicatorProfilesDialog.lblLipsShift": {
        "uk": "Зсув Lips:",
        "pl": "Przesunięcie Lips:",
    },
    "WorkspaceIndicatorProfilesDialog.lblMaType": {
        "uk": "Тип MA:",
        "pl": "Typ MA:",
    },
    "WorkspaceIndicatorProfilesDialog.note": {
        "uk": "Вбудовані профілі є незмінними шаблонами. Для редагування створи копію. "
        "WSP зберігає вибрану редакцію та snapshot для відтворюваного Replay.",
        "pl": "Profile wbudowane są niezmiennymi szablonami. "
        "Aby je edytować, utwórz kopię. "
        "WSP zapisuje wybraną wersję i snapshot dla powtarzalnego Replay.",
    },
    "WorkspaceIndicatorProfilesDialog.btnUseForWorkspace": {
        "uk": "Використати для цього WSP",
        "pl": "Użyj dla tego WSP",
    },
    "WorkspaceIndicatorProfilesDialog.btnSelectedForWorkspace": {
        "uk": "Вибрано для цього WSP",
    },
    "WorkspaceIndicatorProfilesDialog.btnUseForWorkspaceTooltip": {
        "uk": "Вибрати цю точну редакцію профілю для поточного WSP.",
    },
    "WorkspaceIndicatorProfilesDialog.selectedForWorkspaceTooltip": {
        "uk": (
            "Закрий це вікно та натисни «Зберегти» у Параметрах WSP, "
            "щоб записати binding."
        ),
    },
    "WorkspaceIndicatorProfilesDialog.saveBeforeUseTitle": {
        "uk": "Спочатку збережи профіль",
    },
    "WorkspaceIndicatorProfilesDialog.saveBeforeUseMessage": {
        "uk": (
            "Спочатку збережи відредагований профіль, а вже потім "
            "вибери його для цього WSP."
        ),
    },
    "WorkspaceIndicatorProfilesDialog.btnSave": {
        "uk": "Зберегти як нову редакцію",
        "en": "Save as new revision",
        "de": "Als neue Revision speichern",
        "fr": "Enregistrer comme nouvelle révision",
        "pl": "Zapisz jako nową wersję",
    },
    "WorkspaceIndicatorProfilesDialog.btnClose": {
        "uk": "Закрити",
        "pl": "Zamknij",
    },
    "WorkspaceIndicatorProfilesDialog.sourceClose": {
        "uk": "Закриття",
        "pl": "Zamknięcie",
    },
    "WorkspaceIndicatorProfilesDialog.sourceOpen": {
        "uk": "Відкриття",
        "pl": "Otwarcie",
    },
    "WorkspaceIndicatorProfilesDialog.sourceHigh": {
        "uk": "Максимум",
        "pl": "Maksimum",
    },
    "WorkspaceIndicatorProfilesDialog.sourceLow": {
        "uk": "Мінімум",
        "pl": "Minimum",
    },
    "WorkspaceIndicatorProfilesDialog.sourceMedian": {
        "uk": "Медіанна ціна",
        "pl": "Cena medianowa",
    },
    "WorkspaceIndicatorProfilesDialog.sourceTypical": {
        "uk": "Типова ціна",
        "pl": "Cena typowa",
    },
    "WorkspaceIndicatorProfilesDialog.sourceWeighted": {
        "uk": "Зважене закриття",
        "pl": "Ważone zamknięcie",
    },
    "WorkspaceIndicatorProfilesDialog.maSimple": {
        "uk": "Проста",
        "pl": "Prosta",
    },
    "WorkspaceIndicatorProfilesDialog.maExponential": {
        "uk": "Експоненційна",
        "pl": "Wykładnicza",
    },
    "WorkspaceIndicatorProfilesDialog.maSmoothed": {
        "uk": "Згладжена",
        "pl": "Wygładzona",
    },
    "WorkspaceIndicatorProfilesDialog.copyName": {
        "uk": "{name} — копія",
        "pl": "{name} — kopia",
    },
    "WorkspaceIndicatorProfilesDialog.archiveTitle": {
        "uk": "Архівування профілю",
        "pl": "Archiwizacja profilu",
    },
    "WorkspaceIndicatorProfilesDialog.archiveQuestion": {
        "uk": "Архівувати профіль «{name}»? Наявні snapshot WSP залишаться чинними.",
        "pl": "Zarchiwizować profil „{name}”? "
        "Istniejące snapshoty WSP pozostaną ważne.",
    },
    "WorkspaceIndicatorProfilesDialog.deleteTitle": {
        "uk": "Видалення профілю",
        "pl": "Usuwanie profilu",
    },
    "WorkspaceIndicatorProfilesDialog.deleteQuestion": {
        "uk": "Назавжди видалити невикористаний профіль «{name}»?",
        "pl": "Trwale usunąć nieużywany profil „{name}”?",
    },
    "WorkspaceIndicatorProfilesDialog.deleteBlockedTitle": {
        "uk": "Профіль неможливо видалити",
        "pl": "Nie można usunąć profilu",
    },
    "WorkspaceIndicatorProfilesDialog.deleteBuiltInTooltip": {
        "uk": "Вбудовані шаблони не можна видаляти.",
        "pl": "Nie można usuwać wbudowanych szablonów.",
    },
    "WorkspaceIndicatorProfilesDialog.deleteInUseTooltip": {
        "uk": "Використовується у {count} прив’язках WSP; доступне лише архівування.",
        "pl": "Używany w {count} powiązaniach WSP; dostępna jest tylko archiwizacja.",
    },
    "WorkspaceIndicatorProfilesDialog.deleteUnusedTooltip": {
        "uk": "Назавжди видалити цей невикористаний користувацький профіль.",
        "pl": "Trwale usuń ten nieużywany profil użytkownika.",
    },
    "WorkspaceIndicatorProfilesDialog.deleteBuiltInMessage": {
        "uk": "Вбудовані шаблони не можна видаляти.",
        "pl": "Nie można usuwać wbudowanych szablonów.",
    },
    "WorkspaceIndicatorProfilesDialog.deleteInUseMessage": {
        "uk": "Профіль використовується у {count} прив’язках WSP: {names}. "
        "Його можна лише архівувати.",
        "pl": "Profil jest używany w {count} powiązaniach WSP: {names}. "
        "Można go tylko zarchiwizować.",
    },
    "WorkspaceIndicatorProfilesDialog.unsavedTitle": {
        "uk": "Незбережені зміни профілю",
        "pl": "Niezapisane zmiany profilu",
    },
    "WorkspaceIndicatorProfilesDialog.unsavedQuestion": {
        "uk": "Відкинути незбережені зміни профілю?",
        "pl": "Odrzucić niezapisane zmiany profilu?",
    },
    "WorkspaceIndicatorProfilesDialog.statusArchived": {
        "uk": "Архівний",
        "pl": "Zarchiwizowany",
    },
    "WorkspaceIndicatorProfilesDialog.statusReferenceOnly": {
        "uk": "Лише довідка — неповний",
        "pl": "Tylko informacyjny — niepełny",
    },
    "WorkspaceIndicatorProfilesDialog.statusBuiltIn": {
        "uk": "Вбудований шаблон",
        "pl": "Szablon wbudowany",
    },
    "WorkspaceIndicatorProfilesDialog.statusUser": {
        "uk": "Користувацький профіль",
        "pl": "Profil użytkownika",
    },
    "WorkspaceIndicatorProfile.macdLgeClassic": {
        "uk": "LGE Classic EMA 12/26/9 Close",
        "pl": "LGE Classic EMA 12/26/9 Close",
    },
    "WorkspaceIndicatorProfile.macdTwsDefault": {
        "uk": "TWS Default MACD",
        "pl": "TWS Default MACD",
    },
    "WorkspaceIndicatorProfile.macdCtraderReference": {
        "uk": "cTrader Default MACD — довідковий",
        "pl": "cTrader Default MACD — informacyjny",
    },
    "WorkspaceIndicatorProfile.alligatorLgeClassic": {
        "uk": "LGE Classic Smoothed",
        "pl": "LGE Classic Smoothed",
    },
    "WorkspaceIndicatorProfile.alligatorLgeCandidateF": {
        "uk": "LGE Candidate F Smoothed",
        "pl": "LGE Candidate F Smoothed",
    },
    "WorkspaceIndicatorProfile.alligatorCtraderDefault": {
        "uk": "cTrader Default Simple Close",
        "pl": "cTrader Default Simple Close",
    },
    "WorkspaceIndicatorProfile.alligatorTwsReference": {
        "uk": "TWS Default Alligator — довідковий",
        "pl": "TWS Default Alligator — informacyjny",
    },
}


def translation_context_for_key(key: str, target_lang: str) -> str:
    """Return domain context plus preferred terminology for one key."""
    normalized_key = str(key or "").strip()
    normalized_lang = str(target_lang or "").strip().lower()

    domain_context = DEFAULT_TRANSLATION_CONTEXT
    matching_prefixes = sorted(
        TRANSLATION_CONTEXTS_BY_PREFIX,
        key=lambda item: len(item[0]),
        reverse=True,
    )
    for prefix, context in matching_prefixes:
        if normalized_key.startswith(prefix):
            domain_context = context
            break

    glossary = LGE_TRANSLATION_GLOSSARY.get(normalized_lang)
    if not glossary:
        return domain_context

    glossary_text = "; ".join(
        f"{source} = {target}" for source, target in glossary.items()
    )
    return (
        f"{domain_context} Preferred {normalized_lang} terminology: "
        f"{glossary_text}."
    )


def translation_overrides_for_key(key: str) -> dict[str, str]:
    """Return a copy of exact centralized translations for one key."""
    entry = CENTRAL_TRANSLATION_OVERRIDES.get(str(key or "").strip())
    if not isinstance(entry, Mapping):
        return {}
    return {
        str(language).strip().lower(): str(text).strip()
        for language, text in entry.items()
        if str(language).strip() and str(text).strip()
    }


def translation_override_for_key(key: str, language: str) -> str | None:
    """Return one exact centralized translation when it is defined."""
    normalized_language = str(language or "").strip().lower()
    value = translation_overrides_for_key(key).get(normalized_language)
    return value if value else None


def apply_central_translation_overrides(
    catalog: MutableMapping[str, object],
) -> int:
    """Update existing catalog entries with exact centralized translations."""
    updated = 0

    for key, translations in CENTRAL_TRANSLATION_OVERRIDES.items():
        entry = catalog.get(key)
        if not isinstance(entry, dict):
            continue

        source_text = entry.get("en")
        if not isinstance(source_text, str):
            source_text = ""

        for language, text in translations.items():
            normalized_text = restore_format_placeholders(source_text, text)
            if entry.get(language) == normalized_text:
                continue
            entry[language] = normalized_text
            updated += 1

    return updated
