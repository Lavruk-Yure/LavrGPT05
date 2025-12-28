# ui_translator.py
"""
UITranslator — перекладач UI-елементів LGE05.

Patch Translation 4b:
- Зчитує ключі з:
    • widget.text()                 → зберігає у widget.whatsThis()
    • widget.placeholderText()      → зберігає у property "lge_tr_placeholder_key"
    • widget.windowTitle()          → зберігає у property "lge_tr_title_key"
    • QAction.text()                → зберігає у action.whatsThis()
    • QTreeWidgetItem.text(col)     → зберігає у ItemDataRole.UserRole
    (по всіх колонках)
- Дерево перекладається по ВСІХ колонках, щоб не залежати від Designer/стилів.
- Для усунення інспекцій PyCharm, виклики text()/setText()/placeholder*
    виконуються через getattr().
"""

from __future__ import annotations

import re
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem, QWidget

DEBUG_TRANS = False


def log_cp(name: str, **kw: Any) -> None:
    """Локальний debug-логер UITranslator."""
    if not DEBUG_TRANS:
        return
    msg = f"[UI_TRANS:{name}] " + ", ".join(f"{k}={v!r}" for k, v in kw.items())
    print(msg)


class UITranslator:
    """Перекладач UI елементів через LangManager."""

    _PATTERN = re.compile(
        r"^\[(?P<obj>[A-Za-z0-9_]+)\.(?P<field>[A-Za-z0-9_\.]+)\]$"  # noqa
    )  # noqa

    def __init__(self, lang_mgr):
        self.lang = lang_mgr

    def _extract_key(self, text: str) -> str | None:
        text = text.strip()
        m = self._PATTERN.match(text)
        if not m:
            return None
        return f"{m.group('obj')}.{m.group('field')}"

    @staticmethod
    def _call0_str(obj: Any, method_name: str) -> str | None:
        fn = getattr(obj, method_name, None)
        if callable(fn):
            try:
                val = fn()
                return val if isinstance(val, str) else None
            except Exception:  # noqa
                return None
        return None

    @staticmethod
    def _call1_str(obj: Any, method_name: str, arg: str) -> bool:
        fn = getattr(obj, method_name, None)
        if callable(fn):
            try:
                fn(arg)
                return True
            except Exception:  # noqa
                return False
        return False

    # ---------------------------------------------------------
    # QWidget: title / text / placeholder
    # ---------------------------------------------------------
    def _apply_widget_title(self, widget: QWidget) -> None:
        raw = self._call0_str(widget, "windowTitle")
        if raw is None:
            return

        key = self._extract_key(raw)

        if key:
            widget.setProperty("lge_tr_title_key", key)
            log_cp("title.key.detected", key=key, widget=widget.objectName())

        if not key:
            saved = widget.property("lge_tr_title_key")
            key = saved.strip() if isinstance(saved, str) and saved.strip() else None
            if key:
                log_cp("title.key.saved", key=key, widget=widget.objectName())

        if not key:
            return

        value = self.lang.resolve(key)
        if not value:
            return

        fn = getattr(widget, "setWindowTitle", None)
        if callable(fn):
            try:
                fn(value)
                log_cp("title.translated", key=key, text=value)
            except Exception:  # noqa
                pass

    def _apply_widget_text(self, widget: QWidget) -> None:
        raw = self._call0_str(widget, "text")
        if not raw:
            return

        key = self._extract_key(raw)

        if key and hasattr(widget, "setWhatsThis"):
            widget.setWhatsThis(key)
            log_cp("text.key.detected", key=key, widget=widget.objectName())

        if not key and hasattr(widget, "whatsThis"):
            saved = widget.whatsThis()
            key = saved.strip() if isinstance(saved, str) and saved.strip() else None
            if key:
                log_cp("text.key.saved", key=key, widget=widget.objectName())

        if not key:
            return

        value = self.lang.resolve(key)
        if value:
            if self._call1_str(widget, "setText", value):
                log_cp("text.translated", key=key, text=value)

    def _apply_widget_placeholder(self, widget: QWidget) -> None:
        raw = self._call0_str(widget, "placeholderText")
        if raw is None:
            return

        key = self._extract_key(raw)

        if key:
            widget.setProperty("lge_tr_placeholder_key", key)
            log_cp("ph.key.detected", key=key, widget=widget.objectName())

        if not key:
            saved = widget.property("lge_tr_placeholder_key")
            key = saved.strip() if isinstance(saved, str) and saved.strip() else None
            if key:
                log_cp("ph.key.saved", key=key, widget=widget.objectName())

        if not key:
            return

        value = self.lang.resolve(key)
        if value:
            if self._call1_str(widget, "setPlaceholderText", value):
                log_cp("ph.translated", key=key, text=value)

    def _apply_widget(self, widget: QWidget) -> None:
        self._apply_widget_title(widget)
        self._apply_widget_text(widget)
        self._apply_widget_placeholder(widget)

    # ---------------------------------------------------------
    # QAction
    # ---------------------------------------------------------
    def _apply_action(self, action: QAction) -> None:
        raw = action.text().strip()
        key = self._extract_key(raw)

        if key:
            action.setWhatsThis(key)
            log_cp("act.key.detected", key=key)

        if not key:
            saved = action.whatsThis()
            key = saved.strip() if isinstance(saved, str) and saved.strip() else None
            if key:
                log_cp("act.key.saved", key=key)

        if not key:
            return

        value = self.lang.resolve(key)
        if value:
            action.setText(value)
            log_cp("act.translated", key=key, text=value)

    # ---------------------------------------------------------
    # Tree: translate ALL columns
    # ---------------------------------------------------------
    def _apply_tree_item(self, item: QTreeWidgetItem, cols: int) -> None:
        for col in range(max(1, cols)):
            raw = item.text(col).strip()
            key = self._extract_key(raw)

            if key:
                item.setData(col, Qt.ItemDataRole.UserRole, key)
            else:
                data = item.data(col, Qt.ItemDataRole.UserRole)
                key = data if isinstance(data, str) and data.strip() else None

            if not key:
                continue

            value = self.lang.resolve(key)
            if value:
                item.setText(col, value)

    def _walk_tree_children(self, item: QTreeWidgetItem, cols: int) -> None:
        for i in range(item.childCount()):
            child = item.child(i)
            self._apply_tree_item(child, cols=cols)
            self._walk_tree_children(child, cols=cols)

    # ---------------------------------------------------------
    # Walk
    # ---------------------------------------------------------
    def _walk(self, root: Any) -> None:
        if isinstance(root, QTreeWidget):
            cols = max(1, root.columnCount())
            for i in range(root.topLevelItemCount()):
                item = root.topLevelItem(i)
                self._apply_tree_item(item, cols=cols)
                self._walk_tree_children(item, cols=cols)

        if isinstance(root, QTreeWidgetItem):
            return

        if isinstance(root, QWidget):
            self._apply_widget(root)

            for child in root.findChildren(QWidget):
                self._apply_widget(child)

            # QAction з actions() (QToolBar/Menu)
            if hasattr(root, "actions"):
                try:
                    for act in root.actions():
                        if isinstance(act, QAction):
                            self._apply_action(act)
                except Exception:  # noqa
                    pass

            for act in root.findChildren(QAction):
                self._apply_action(act)

            for tree in root.findChildren(QTreeWidget):
                cols = max(1, tree.columnCount())
                for i in range(tree.topLevelItemCount()):
                    item = tree.topLevelItem(i)
                    self._apply_tree_item(item, cols=cols)
                    self._walk_tree_children(item, cols=cols)

    # ---------------------------------------------------------
    # Public
    # ---------------------------------------------------------
    def apply(self, root: Any) -> None:
        log_cp("apply.start", lang=self.lang.current_language)
        self._walk(root)
        log_cp("apply.done", lang=self.lang.current_language)
