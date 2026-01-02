# ai_translator.py
# -*- coding: utf-8 -*-
"""
AITranslator — переклад для автозаповнення strings (DeepL / mock / off).

Важливе:
- Налаштування беруться з conf["translator"].
- DeepL: 2 ключі (deepl_key_1, deepl_key_2).
- LibreTranslate прибрано.
- На будь-якій помилці повертаємо оригінальний текст (не ламаємо рантайм).
- Простий лог у lang/ai_translate.log (тільки якщо DEBUG увімкнено).
"""

from __future__ import annotations

import datetime as dt
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

import requests

logger = logging.getLogger(__name__)

# Увімкнути:
# 1) або тут True
# 2) або змінна середовища LGE05_AI_TRANSLATOR_DEBUG=1
DEBUG_AI_TRANSLATOR = False

DEEPL_BETA_LANGS = {"hi", "hr", "mk", "sq"}

MAX_RETRIES_429 = 5


class AITranslator:
    def __init__(self, conf: Dict[str, Any], lang_dir: Path) -> None:

        self.lang_dir = Path(lang_dir)
        self.log_path = self.lang_dir / "ai_translate.log"

        global DEBUG_AI_TRANSLATOR
        env_dbg = (os.getenv("LGE05_AI_TRANSLATOR_DEBUG") or "").strip()
        if env_dbg in ("1", "true", "True", "yes", "YES"):
            DEBUG_AI_TRANSLATOR = True

        tr_conf = conf.get("translator", {}) if isinstance(conf, dict) else {}
        if not isinstance(tr_conf, dict):
            tr_conf = {}

        # provider: off/mock/deepl
        self.provider: str = str(tr_conf.get("provider") or "mock").strip().lower()

        # DeepL keys (canonical)
        self.deepl_key_1: str = str(tr_conf.get("deepl_key_1") or "").strip()
        self.deepl_key_2: str = str(tr_conf.get("deepl_key_2") or "").strip()

        self._dbg(
            "init",
            provider=self.provider,
            has_deepl1=bool(self.deepl_key_1),
            has_deepl2=bool(self.deepl_key_2),
            log_path=str(self.log_path),
        )
        self._cache: dict[tuple[str, str, str], str] = {}

    # ---------------------------------------------------------
    def translate(self, text: str, target_lang: str, source_lang: str = "en") -> str:
        """
        Повертає переклад тексту.
        На помилці — повертає text.
        """
        text = text or ""
        target_lang = (target_lang or "").strip()
        source_lang = (source_lang or "en").strip()

        provider = self.provider
        if provider not in ("off", "mock", "deepl"):
            provider = "mock"

        self._dbg(
            "translate.enter",
            provider=provider,
            source=source_lang,
            target=target_lang,
            text_preview=text[:60],
        )

        if DEBUG_AI_TRANSLATOR:
            self._append_log(
                self._ts_line(
                    "ENTER",
                    f"provider={provider} src={source_lang} tgt={target_lang} "
                    f"text={repr(text[:60])}",
                )
            )

        if provider in ("off", "mock"):
            return text

        if not target_lang or target_lang.lower() == source_lang.lower():
            if DEBUG_AI_TRANSLATOR:
                self._append_log(
                    self._ts_line("SKIP", "empty target or same as source")
                )
            return text

        # --- CACHE (до запиту в DeepL) ---
        k = (text, source_lang.lower(), target_lang.lower())
        cached = self._cache.get(k)
        if isinstance(cached, str) and cached.strip():
            if DEBUG_AI_TRANSLATOR:
                self._append_log(
                    self._ts_line("CACHE", f"hit src={source_lang} tgt={target_lang}")
                )
            return cached

        try:
            result = self._translate_deepl(text, target_lang, source_lang)

            # --- CACHE STORE ---
            if isinstance(result, str) and result.strip():
                self._cache[k] = result

            if DEBUG_AI_TRANSLATOR:
                self._append_log(
                    self._ts_line(
                        "OK",
                        f"deepl src={source_lang} tgt={target_lang} "
                        f"out={repr(result[:60])}",
                    )
                )
            return result
        except Exception as e:  # noqa: BLE001
            if DEBUG_AI_TRANSLATOR:
                self._append_log(
                    self._ts_line(
                        "FAIL",
                        f"deepl src={source_lang} tgt={target_lang} | {e}",
                    )
                )
            return text

    # ---------------------------------------------------------
    @staticmethod
    def _deepl_lang(code: str) -> str:
        """
        DeepL API: target_lang = "EN", "DE", "HR", "AR", "PT-BR", "EN-GB"...
        Беремо base і підрегіон (якщо є), переводимо у верхній регістр.
        """
        s = (code or "").strip()
        if not s:
            return "EN"
        s = s.replace("_", "-").strip()
        parts = s.split("-", 1)
        base = parts[0].upper()
        if len(parts) == 1:
            return base
        sub = parts[1].upper()
        return f"{base}-{sub}"

    # ---------------------------------------------------------
    def _translate_deepl(self, text: str, target_lang: str, source_lang: str) -> str:
        candidates = [
            ("key1", self.deepl_key_1),
            ("key2", self.deepl_key_2),
        ]
        candidates = [(slot, k) for slot, k in candidates if k]
        if not candidates:
            raise ValueError("DeepL keys are missing (deepl_key_1/deepl_key_2)")

        url = "https://api-free.deepl.com/v2/translate"
        tgt = self._deepl_lang(target_lang)
        src = self._deepl_lang(source_lang)

        payload = {
            "text": text,
            "target_lang": tgt,
            "source_lang": src,
        }

        is_beta = target_lang.lower() in DEEPL_BETA_LANGS
        if is_beta:
            payload["enable_beta_languages"] = "1"
            if DEBUG_AI_TRANSLATOR:
                self._append_log(
                    self._ts_line("DEEPL", f"beta enabled src={src} tgt={tgt}")
                )

        last_err: Optional[str] = None

        for slot, auth_key in candidates:
            headers = {"Authorization": f"DeepL-Auth-Key {auth_key}"}

            try:
                if DEBUG_AI_TRANSLATOR:
                    self._append_log(
                        self._ts_line(
                            "DEEPL",
                            f"try={slot} src={src} tgt={tgt} text={repr(text[:60])}",
                        )
                    )

                retries_429 = 0

                while True:
                    r = requests.post(url, data=payload, headers=headers, timeout=20)

                    if DEBUG_AI_TRANSLATOR:
                        preview = (r.text or "")[:300].replace("\n", "\\n")
                        self._append_log(
                            self._ts_line(
                                "DEEPL_HTTP",
                                f"try={slot} status={r.status_code} resp={preview}",
                            )
                        )

                    if r.status_code == 200:
                        data = r.json()
                        translations = data.get("translations")
                        if not isinstance(translations, list) or not translations:
                            raise ValueError("DeepL: empty translations")
                        out = translations[0].get("text")
                        if not isinstance(out, str) or not out.strip():
                            raise ValueError("DeepL: empty text")
                        return out

                    if r.status_code == 429:
                        retries_429 += 1
                        if retries_429 >= MAX_RETRIES_429:
                            raise ConnectionError("DeepL 429 retry limit exceeded")

                        wait = 2**retries_429  # 2,4,8,16...
                        if DEBUG_AI_TRANSLATOR:
                            self._append_log(
                                self._ts_line("DEEPL_WAIT", f"{wait}s (#{retries_429})")
                            )
                        time.sleep(wait)
                        continue

                    raise ConnectionError(
                        f"HTTP {r.status_code}: {(r.text or '')[:200]}"
                    )

            except Exception as e:  # noqa: BLE001
                last_err = f"{slot}: {e}"
                continue

        raise ConnectionError(last_err or "DeepL failed")

    # _______________________________________________________
    @staticmethod
    def _ts_line(tag: str, msg: str) -> str:
        ts = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return f"[{ts}] {tag} | {msg}"

    def _append_log(self, line: str) -> None:
        if not DEBUG_AI_TRANSLATOR:
            return
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception as e:  # noqa: BLE001
            logger.exception("AITranslator log write failed: %s", e)

    @staticmethod
    def _dbg(name: str, **kw: Any) -> None:
        if not DEBUG_AI_TRANSLATOR:
            return
        logger.debug("AITranslator.%s | %s", name, kw)
