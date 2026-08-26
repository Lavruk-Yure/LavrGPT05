# core/common_dialogs.py
# -*- coding: utf-8 -*-
"""
Common dialogs (Error / Info / Confirm).

Final patch:
- Резолв ключів через LangManager.resolve()
- Підтримка форматів: key, [key]
- Резолв текстів з UI (header/details/buttons)
- Коректні connect'и кнопок:
    Error / Info  -> btnOk.accept
    Confirm      -> btnYes.accept / btnNo.reject
"""

from __future__ import annotations

from typing import Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog

from core.lang_manager import LangManager
from ui.ui_Common_Confirm_Dialog import Ui_CommonConfirmDialog
from ui.ui_Common_Error_Dialog import Ui_CommonErrorDialog
from ui.ui_Common_Info_Dialog import Ui_CommonInfoDialog

# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------


def _strip_brackets(s: str) -> str:
    s2 = (s or "").strip()
    if s2.startswith("[") and s2.endswith("]"):
        return s2[1:-1].strip()
    return s2


def _looks_like_key(s: str) -> bool:
    return "." in s and " " not in s


def _resolve_text(lang_mgr: LangManager, value: Optional[str]) -> str:
    if not value:
        return ""

    raw = value.strip()
    key = _strip_brackets(raw)

    if _looks_like_key(key):
        try:
            resolved = lang_mgr.resolve(key)
            return resolved if resolved else key
        except Exception:  # noqa
            return key

    return value


def _resolve_all(
    lang_mgr: LangManager,
    title: str,
    header: str,
    details: str,
) -> Tuple[str, str, str]:
    return (
        _resolve_text(lang_mgr, title),
        _resolve_text(lang_mgr, header),
        _resolve_text(lang_mgr, details),
    )


# ----------------------------------------------------------------------
# dialogs
# ----------------------------------------------------------------------


class CommonErrorDialog(QDialog):
    @staticmethod
    def show_dialog(
        parent,
        lang_mgr: LangManager,
        *,
        title: str,
        header: str,
        details: str,
    ) -> None:
        dlg = CommonErrorDialog(parent)
        ui = Ui_CommonErrorDialog()
        ui.setupUi(dlg)

        t, h, d = _resolve_all(lang_mgr, title, header, details)

        dlg.setWindowTitle(t)
        ui.lblHeader.setText(h)
        ui.lblDetails.setText(d)

        details_norm = (d or "").strip()
        if not details_norm or details_norm in {"—", "-"}:
            ui.lblDetails.setVisible(False)

        # buttons
        if hasattr(ui, "btnOk"):
            ui.btnOk.setText(_resolve_text(lang_mgr, ui.btnOk.text()))
            ui.btnOk.clicked.connect(dlg.accept)
            ui.btnOk.setDefault(True)
            ui.btnOk.setAutoDefault(True)

        dlg.setModal(True)
        dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
        dlg.exec()


class CommonInfoDialog(QDialog):
    @staticmethod
    def show_dialog(
        parent,
        lang_mgr: LangManager,
        *,
        title: str,
        header: str,
        details: str,
    ) -> None:
        dlg = CommonInfoDialog(parent)
        ui = Ui_CommonInfoDialog()
        ui.setupUi(dlg)

        t, h, d = _resolve_all(lang_mgr, title, header, details)

        dlg.setWindowTitle(t)
        ui.lblHeader.setText(h)
        ui.lblDetails.setText(d)

        details_norm = (d or "").strip()
        if not details_norm or details_norm in {"—", "-"}:
            ui.lblDetails.setVisible(False)

        if hasattr(ui, "btnOk"):
            ui.btnOk.setText(_resolve_text(lang_mgr, ui.btnOk.text()))
            ui.btnOk.clicked.connect(dlg.accept)
            ui.btnOk.setDefault(True)
            ui.btnOk.setAutoDefault(True)

        dlg.setModal(True)
        dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
        dlg.exec()


class CommonConfirmDialog(QDialog):
    @staticmethod
    def show_dialog(
        parent,
        lang_mgr: LangManager,
        *,
        title: str,
        header: str,
        details: str,
    ) -> bool:
        dlg = CommonConfirmDialog(parent)
        ui = Ui_CommonConfirmDialog()
        ui.setupUi(dlg)

        t, h, d = _resolve_all(lang_mgr, title, header, details)

        dlg.setWindowTitle(t)
        ui.lblHeader.setText(h)
        ui.lblDetails.setText(d)

        details_norm = (d or "").strip()
        if not details_norm or details_norm in {"—", "-"}:
            ui.lblDetails.setVisible(False)

        if hasattr(ui, "btnYes"):
            ui.btnYes.setText(_resolve_text(lang_mgr, ui.btnYes.text()))
            ui.btnYes.clicked.connect(dlg.accept)
            ui.btnYes.setDefault(True)
            ui.btnYes.setAutoDefault(True)

        if hasattr(ui, "btnNo"):
            ui.btnNo.setText(_resolve_text(lang_mgr, ui.btnNo.text()))
            ui.btnNo.clicked.connect(dlg.reject)

        dlg.setModal(True)
        dlg.setWindowModality(Qt.WindowModality.ApplicationModal)

        result = dlg.exec()
        return result == QDialog.DialogCode.Accepted
