# conftest.py
"""Тепер Python знатиме, що треба шукати модулі в корені проєкту
(LavrGPT05/core, LavrGPT05/monitoring тощо"""
import os
import sys

sys.path.append(os.path.dirname(__file__))
