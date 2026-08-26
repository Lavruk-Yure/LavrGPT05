# init_db.py
# -*- coding: utf-8 -*-
"""
init_db — одноразова ініціалізація office.db (dev_tools).
Запуск:
  D:\\LavrGPT\\venv313\\Scripts\\python.exe
  D:\\LavrGPT\\LavrGPT05\\office\\dev_tools\\init_db.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def _bootstrap_import_path() -> Path:
    """
    Додає корінь репозиторію в sys.path, щоб працювали імпорти office.* при запуску
    як standalone-скрипта.
    """
    office_root = Path(__file__).resolve().parent.parent  # .../office
    repo_root = office_root.parent  # .../LavrGPT05
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    return office_root


def main() -> int:
    office_root = _bootstrap_import_path()

    # Локальні імпорти після bootstrap — щоб flake8 не лаявся на E402.
    from office.core.db import init_db
    from office.core.logging_setup import setup_logging

    setup_logging()

    logger.debug("Office root: %s", office_root)

    db_path = init_db(office_root)
    logger.info("OK: %s", db_path)
    print(f"✅ office.db готово: {db_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
