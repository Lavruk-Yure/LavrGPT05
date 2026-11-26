"""T116-45 TEST_ONLY — статичний аудит EURUSD symbolId у production LGE.

Не створює SDK Client, не відкриває мережу та не змінює production.
Результат T116-44 (symbolId=1) стосується лише DEMO API Account ID 46368962.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

DEMO_API_ACCOUNT_ID = 46368962
OBSERVED_DEMO_EURUSD_ID = 1


@dataclass(frozen=True)
class MappingAudit:
    """Фактичний контракт статичної таблиці та production-викликів."""

    table_id: int
    table_enabled: bool
    unique_symbols: bool
    unique_ids: bool
    history_lookup: bool
    history_request: bool
    order_lookup: bool
    order_request: bool
    quote_lookup: bool
    quote_subscription: bool
    spot_reverse_lookup: bool
    position_reverse_lookup: bool
    hardcoded_symbol_id_requests: int

    @property
    def accepted(self) -> bool:
        return (
            self.table_id == OBSERVED_DEMO_EURUSD_ID
            and self.table_enabled
            and self.unique_symbols
            and self.unique_ids
            and self.history_lookup
            and self.history_request
            and self.order_lookup
            and self.order_request
            and self.quote_lookup
            and self.quote_subscription
            and self.spot_reverse_lookup
            and self.position_reverse_lookup
            and self.hardcoded_symbol_id_requests == 0
        )


def _symbol_rows(source: str) -> list[tuple[int, str, bool]]:
    """Читати лише літеральні записи CTraderSymbol з AST, без виконання коду."""
    tree = ast.parse(source)
    rows: list[tuple[int, str, bool]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name) or node.func.id != "CTraderSymbol":
            continue
        if len(node.args) != 3 or node.keywords:
            raise ValueError("Неканонічний запис CTraderSymbol")
        values = [ast.literal_eval(argument) for argument in node.args]
        identifier, name, enabled = values
        if type(identifier) is not int or type(name) is not str:
            raise ValueError("Некоректний symbolId або symbolName")
        if type(enabled) is not bool:
            raise ValueError("Некоректне значення enabled")
        rows.append((identifier, name, enabled))
    return rows


def _method(tree: ast.AST, method_name: str) -> ast.FunctionDef:
    """Вимагати один production-метод із заданою назвою."""
    methods = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == method_name
    ]
    if len(methods) != 1:
        raise ValueError(f"Очікується рівно один метод {method_name}")
    return methods[0]


def _calls_mapping(method: ast.FunctionDef, method_name: str) -> bool:
    return any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == method_name
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "ctr_symbols"
        for node in ast.walk(method)
    )


def _assigns_symbol_id(method: ast.FunctionDef) -> bool:
    return any(
        isinstance(node, (ast.Assign, ast.AnnAssign))
        and any(
            isinstance(target, ast.Attribute)
            and target.attr == "symbolId"
            for target in (
                node.targets if isinstance(node, ast.Assign) else [node.target]
            )
        )
        for node in ast.walk(method)
    )


def _appends_symbol_id(method: ast.FunctionDef) -> bool:
    return any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "append"
        and isinstance(node.func.value, ast.Attribute)
        and node.func.value.attr == "symbolId"
        for node in ast.walk(method)
    )


def audit_sources(table_source: str, adapter_source: str) -> MappingAudit:
    """Порівняти таблицю з результатом DEMO та використанням у runtime."""
    rows = _symbol_rows(table_source)
    eurusd = [row for row in rows if row[1].upper() == "EURUSD"]
    if len(eurusd) != 1:
        raise ValueError("EURUSD має бути присутній рівно один раз")

    tree = ast.parse(adapter_source)
    imports_table = any(
        isinstance(node, ast.ImportFrom)
        and node.module == "core"
        and any(
            alias.name == "ctrader_symbols" and alias.asname == "ctr_symbols"
            for alias in node.names
        )
        for node in ast.walk(tree)
    )
    if not imports_table:
        raise ValueError("Production adapter не імпортує ctrader_symbols")

    def method(name: str) -> ast.FunctionDef:
        return _method(tree, name)

    hardcoded = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if any(
            isinstance(target, ast.Attribute) and target.attr == "symbolId"
            for target in node.targets
        ) and isinstance(node.value, ast.Constant):
            if type(node.value.value) is int:
                hardcoded += 1

    return MappingAudit(
        table_id=eurusd[0][0],
        table_enabled=eurusd[0][2],
        unique_symbols=len({name.upper() for _, name, _ in rows}) == len(rows),
        unique_ids=len({identifier for identifier, _, _ in rows}) == len(rows),
        history_lookup=_calls_mapping(
            method("get_historical_trendbars"), "get_enabled_symbol_id"
        ),
        history_request=_assigns_symbol_id(method("_request_trendbar_chunk")),
        order_lookup=_calls_mapping(
            method("place_market_order"), "get_enabled_symbol_id"
        ),
        order_request=_assigns_symbol_id(method("place_market_order")),
        quote_lookup=_calls_mapping(
            method("get_forex_quote_snapshot"), "get_enabled_symbol_id"
        ),
        quote_subscription=_appends_symbol_id(method("_subscribe_position_spots")),
        spot_reverse_lookup=_calls_mapping(
            method("_on_spot_event"), "get_symbol_name"
        ),
        position_reverse_lookup=_calls_mapping(
            method("_build_positions"), "get_symbol_name"
        ),
        hardcoded_symbol_id_requests=hardcoded,
    )


def audit_current_tree(project_root: Path) -> MappingAudit:
    """Прочитати лише два production-файли, без SDK чи мережі."""
    symbols = project_root / "core" / "ctrader_symbols.py"
    adapter = project_root / "engine" / "ctrader_adapter.py"
    return audit_sources(
        symbols.read_text(encoding="utf-8-sig"),
        adapter.read_text(encoding="utf-8-sig"),
    )
