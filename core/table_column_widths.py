# -*- coding: utf-8 -*-
"""Збереження ручної ширини колонок основних таблиць LGE.

Модуль відновлює ширини з Session, застосовує безпечні початкові значення
для нового профілю UI та зберігає лише фактичні ручні зміни користувача.
Стан таблиць є суто UI-даними: він не впливає на runtime, сигнали, risk,
Replay або broker execution.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

from PySide6.QtCore import QCoreApplication, QObject, QTimer

from core.session_repository import SessionRepository, SessionRepositoryError

TABLE_COLUMN_WIDTH_SAVE_DELAY_MS = 250
TABLE_COLUMN_WIDTH_MINIMUM = 36

logger = logging.getLogger(__name__)


class TableColumnWidthPersistence(QObject):
    """Відновити та debounce-зберігати ширини колонок одного view."""

    def __init__(
        self,
        view: Any,
        table_key: str,
        default_widths: Sequence[int],
        *,
        repository: SessionRepository | None = None,
        save_delay_ms: int = TABLE_COLUMN_WIDTH_SAVE_DELAY_MS,
    ) -> None:
        super().__init__(view)
        self._view = view
        self._table_key = str(table_key).strip()
        self._repository = repository or SessionRepository()
        self._default_widths = tuple(
            max(TABLE_COLUMN_WIDTH_MINIMUM, int(width))
            for width in default_widths
        )
        self._restoring = False
        self._dirty = False
        self._effective_widths = list(self._default_widths)

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(max(0, int(save_delay_ms)))
        self._save_timer.timeout.connect(self.flush)

        self._restore_widths()
        self._header().sectionResized.connect(self._on_section_resized)
        application = QCoreApplication.instance()
        if application is not None:
            application.aboutToQuit.connect(self.flush)

    def current_widths(self) -> tuple[int, ...]:
        """Повернути ширини, не втрачаючи значення прихованих колонок."""
        widths: list[int] = []
        for column in range(self._view.columnCount()):
            current_width = int(self._view.columnWidth(column))
            if current_width > 0:
                widths.append(current_width)
                continue
            if column < len(self._effective_widths):
                widths.append(int(self._effective_widths[column]))
                continue
            widths.append(TABLE_COLUMN_WIDTH_MINIMUM)
        return tuple(widths)

    def flush(self) -> None:
        """Негайно зберегти pending ручну зміну, якщо вона була."""
        if not self._dirty:
            return
        self._save_timer.stop()
        try:
            self._repository.save_table_column_widths(
                self._table_key,
                self.current_widths(),
            )
        except SessionRepositoryError:
            logger.exception(
                "Cannot save table column widths: %s",
                self._table_key,
            )
        self._dirty = False

    def _header(self) -> Any:
        horizontal_header = getattr(self._view, "horizontalHeader", None)
        if callable(horizontal_header):
            return horizontal_header()
        return self._view.header()

    def _restore_widths(self) -> None:
        column_count = int(self._view.columnCount())
        try:
            saved = self._repository.load_table_column_widths(self._table_key)
        except SessionRepositoryError:
            logger.exception(
                "Cannot restore table column widths: %s",
                self._table_key,
            )
            saved = None
        widths = saved
        if widths is None or len(widths) != column_count:
            widths = self._default_widths
        if len(widths) != column_count:
            return

        restored_widths = [
            max(TABLE_COLUMN_WIDTH_MINIMUM, int(width))
            for width in widths
        ]
        self._restoring = True
        try:
            for column, width in enumerate(restored_widths):
                self._view.setColumnWidth(column, width)
        finally:
            self._restoring = False
        self._effective_widths = restored_widths

    def _on_section_resized(
        self,
        _logical_index: int,
        old_size: int,
        new_size: int,
    ) -> None:
        old_size = int(old_size)
        new_size = int(new_size)
        if self._restoring or old_size == new_size:
            return

        if new_size <= 0:
            return

        if 0 <= int(_logical_index) < len(self._effective_widths):
            self._effective_widths[int(_logical_index)] = new_size

        if old_size <= 0:
            return

        self._dirty = True
        self._save_timer.start()
