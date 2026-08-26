# office_config.py
# -*- coding: utf-8 -*-
"""
office_config — читання/запис office_config.json
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class OfficeConfig:
    initialized: bool
    password_salt: str
    password_hash: str

    def to_dict(self) -> dict:
        return {
            "initialized": self.initialized,
            "auth": {
                "password_salt": self.password_salt,
                "password_hash": self.password_hash,
            },
        }


def write_config(path: Path, cfg: OfficeConfig) -> None:
    path.write_text(
        json.dumps(cfg.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_smtp_config(cfg: dict) -> dict:
    return cfg.get("smtp", {})


def read_config(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
