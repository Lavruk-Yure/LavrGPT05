# -*- coding: utf-8 -*-
"""
JSON-сховище робочого середовища LGE.

Session зберігає лише конфігурацію UI/workspace, включно з ручною шириною
колонок основних таблиць. Воно не є джерелом істини для ордерів, позицій,
broker IDs, PnL або підключення.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.algorithm_workspace import (
    AlgorithmWorkspace,
    normalize_workspace_uid,
    utc_now_iso,
)
from core.app_paths import SESSION_DIR

SESSION_SCHEMA_VERSION = 2
SUPPORTED_SESSION_SCHEMA_VERSIONS = {1, SESSION_SCHEMA_VERSION}
SESSION_FILE_NAME = "session.json"
WORKSPACES_DIR_NAME = "workspaces"
MAIN_WINDOW_STATES = {"NORMAL", "MAXIMIZED"}


class SessionRepositoryError(RuntimeError):
    """Помилка читання або запису Session."""


class SessionRepository:
    """Repository для session.json і workspace_<uid>.json."""

    def __init__(self, session_dir: Path | None = None) -> None:
        self.session_dir = Path(session_dir or SESSION_DIR)
        self.workspaces_dir = self.session_dir / WORKSPACES_DIR_NAME
        self.session_path = self.session_dir / SESSION_FILE_NAME

    def ensure_storage(self) -> None:
        """Створити структуру каталогів Session."""
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.workspaces_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def default_main_window_state() -> dict[str, Any]:
        """Повернути безпечний початковий стан головного вікна."""
        return {
            "geometry": None,
            "window_state": "NORMAL",
        }

    @classmethod
    def default_manifest(cls) -> dict[str, Any]:
        """Повернути порожній session manifest."""
        return {
            "schema_version": SESSION_SCHEMA_VERSION,
            "layout_locked": False,
            "active_workspace_uid": None,
            "workspace_order": [],
            "main_window": cls.default_main_window_state(),
            "table_column_widths": {},
            "updated_utc": utc_now_iso(),
        }

    def load_manifest(self) -> dict[str, Any]:
        """Прочитати session.json або повернути manifest за замовчуванням."""
        self.ensure_storage()
        if not self.session_path.exists():
            return self.default_manifest()

        data = self._read_json(self.session_path)
        schema_version = int(data.get("schema_version", 0))
        if schema_version not in SUPPORTED_SESSION_SCHEMA_VERSIONS:
            raise SessionRepositoryError(
                f"Unsupported session schema_version: {schema_version}"
            )

        workspace_order = data.get("workspace_order", [])
        if not isinstance(workspace_order, list):
            raise SessionRepositoryError("workspace_order must be a list")

        normalized_order = [
            normalize_workspace_uid(workspace_uid)
            for workspace_uid in workspace_order
        ]

        active_workspace_uid = data.get("active_workspace_uid")
        if active_workspace_uid is not None:
            active_workspace_uid = normalize_workspace_uid(active_workspace_uid)

        return {
            "schema_version": SESSION_SCHEMA_VERSION,
            "layout_locked": bool(data.get("layout_locked", False)),
            "active_workspace_uid": active_workspace_uid,
            "workspace_order": normalized_order,
            "main_window": self._normalize_main_window_state(
                data.get("main_window")
            ),
            "table_column_widths": self._normalize_table_column_widths(
                data.get("table_column_widths")
            ),
            "updated_utc": str(data.get("updated_utc") or utc_now_iso()),
        }

    def save_manifest(self, manifest: dict[str, Any]) -> None:
        """Атомарно зберегти session.json."""
        workspace_order = manifest.get("workspace_order", [])
        if not isinstance(workspace_order, list):
            raise SessionRepositoryError("workspace_order must be a list")

        normalized_order = [
            normalize_workspace_uid(workspace_uid)
            for workspace_uid in workspace_order
        ]

        active_workspace_uid = manifest.get("active_workspace_uid")
        if active_workspace_uid is not None:
            active_workspace_uid = normalize_workspace_uid(active_workspace_uid)

        payload = {
            "schema_version": SESSION_SCHEMA_VERSION,
            "layout_locked": bool(manifest.get("layout_locked", False)),
            "active_workspace_uid": active_workspace_uid,
            "workspace_order": normalized_order,
            "main_window": self._normalize_main_window_state(
                manifest.get("main_window")
            ),
            "table_column_widths": self._normalize_table_column_widths(
                manifest.get("table_column_widths")
            ),
            "updated_utc": utc_now_iso(),
        }
        self._write_json_atomic(self.session_path, payload)

    def save_main_window_state(self, main_window: dict[str, Any]) -> None:
        """Зберегти geometry/state головного вікна, не чіпаючи WSP manifest."""
        manifest = self.load_manifest()
        manifest["main_window"] = self._normalize_main_window_state(main_window)
        self.save_manifest(manifest)

    def load_table_column_widths(
        self,
        table_key: str,
    ) -> tuple[int, ...] | None:
        """Прочитати збережені ширини колонок одного UI table."""
        key = str(table_key or "").strip()
        if not key:
            return None
        manifest = self.load_manifest()
        widths_by_table = manifest.get("table_column_widths", {})
        widths = widths_by_table.get(key)
        if not isinstance(widths, list):
            return None
        return tuple(int(width) for width in widths)

    def save_table_column_widths(
        self,
        table_key: str,
        widths: tuple[int, ...] | list[int],
    ) -> None:
        """Атомарно зберегти ручні ширини колонок одного UI table."""
        key = str(table_key or "").strip()
        if not key:
            raise SessionRepositoryError("table_key is required")
        normalized_widths = [int(width) for width in widths]
        if not normalized_widths or any(width <= 0 for width in normalized_widths):
            raise SessionRepositoryError("table column widths must be positive")

        manifest = self.load_manifest()
        widths_by_table = dict(manifest.get("table_column_widths") or {})
        widths_by_table[key] = normalized_widths
        manifest["table_column_widths"] = widths_by_table
        self.save_manifest(manifest)

    def save_workspace(self, workspace: AlgorithmWorkspace) -> Path:
        """Атомарно зберегти один workspace-файл."""
        self.ensure_storage()
        workspace.updated_utc = utc_now_iso()
        path = self.workspace_path(workspace.workspace_uid)
        self._write_json_atomic(path, workspace.to_storage_dict())
        return path

    def load_workspace(self, workspace_uid: str) -> AlgorithmWorkspace:
        """Прочитати workspace та відновити його як RESTORED."""
        path = self.workspace_path(workspace_uid)
        if not path.exists():
            raise SessionRepositoryError(
                f"Workspace file does not exist: {path.name}"
            )
        data = self._read_json(path)
        return AlgorithmWorkspace.from_storage_dict(data)

    def load_ordered_workspaces(self) -> list[AlgorithmWorkspace]:
        """Прочитати workspaces у порядку з session.json."""
        manifest = self.load_manifest()
        workspaces: list[AlgorithmWorkspace] = []

        for workspace_uid in manifest["workspace_order"]:
            path = self.workspace_path(workspace_uid)
            if not path.exists():
                continue
            workspaces.append(self.load_workspace(workspace_uid))

        return workspaces

    def delete_workspace(self, workspace_uid: str) -> None:
        """Видалити workspace-файл, якщо він існує."""
        path = self.workspace_path(workspace_uid)
        if path.exists():
            path.unlink()

    def workspace_path(self, workspace_uid: str) -> Path:
        """Побудувати canonical шлях workspace_<uuid>.json."""
        normalized_uid = normalize_workspace_uid(workspace_uid)
        return self.workspaces_dir / f"workspace_{normalized_uid}.json"

    @staticmethod
    def _normalize_table_column_widths(value: object) -> dict[str, list[int]]:
        """Нормалізувати persisted UI widths без падіння на legacy Session."""
        if not isinstance(value, dict):
            return {}
        normalized: dict[str, list[int]] = {}
        for raw_key, raw_widths in value.items():
            key = str(raw_key or "").strip()
            if not key or not isinstance(raw_widths, (list, tuple)):
                continue
            try:
                widths = [int(width) for width in raw_widths]
            except (TypeError, ValueError):
                continue
            if not widths or any(width <= 0 for width in widths):
                continue
            normalized[key] = widths
        return normalized

    @classmethod
    def _normalize_main_window_state(cls, value: object) -> dict[str, Any]:
        state = cls.default_main_window_state()
        if not isinstance(value, dict):
            return state

        window_state = str(value.get("window_state") or "NORMAL").upper()
        if window_state not in MAIN_WINDOW_STATES:
            window_state = "NORMAL"
        state["window_state"] = window_state

        geometry = value.get("geometry")
        if not isinstance(geometry, dict):
            return state

        try:
            x = int(geometry.get("x", 0))
            y = int(geometry.get("y", 0))
            width = int(geometry.get("width", 0))
            height = int(geometry.get("height", 0))
        except (TypeError, ValueError):
            return state

        if width <= 0 or height <= 0:
            return state

        state["geometry"] = {
            "x": x,
            "y": y,
            "width": width,
            "height": height,
        }
        return state

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SessionRepositoryError(f"Cannot read JSON: {path}") from exc

        if not isinstance(data, dict):
            raise SessionRepositoryError(f"JSON root must be an object: {path}")
        return data

    def _write_json_atomic(self, path: Path, payload: dict[str, Any]) -> None:
        self.ensure_storage()
        temp_path = path.with_suffix(path.suffix + ".tmp")
        try:
            temp_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            temp_path.replace(path)
        except OSError as exc:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise SessionRepositoryError(f"Cannot write JSON: {path}") from exc
