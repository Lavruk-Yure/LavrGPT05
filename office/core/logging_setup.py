# logging_setup.py
# -*- coding: utf-8 -*-
"""
logging_setup — базове логування для LGEOffice.
"""

from __future__ import annotations

import logging


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
