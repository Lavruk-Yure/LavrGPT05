# ai_translator.py
# -*- coding: utf-8 -*-
"""
AITranslator — переклад для автозаповнення strings (DeepL / LibreTranslate / mock).

Важливе:
- Налаштування беруться з conf["translator"].
- DeepL: 2 ключі (deepl_key_1, deepl_key_2).
- LibreTranslate: URL з conf["translator"]["libretranslate_url"].
- На будь-якій помилці повертаємо оригінальний текст (не ламаємо рантайм).
- Простий лог у lang/ai_translate.log.
"""

from __future__ import annotations

import datetime as dt
import logging
from pathlib import Path
from typing import Any, Dict, Optional

import requests

logger = logging.getLogger(__name__)

DEBUG_AI_TRANSLATOR = False  # тимчасово для тесту pl


class AITranslator:
    def __init__(self, conf: Dict[str, Any], lang_dir: Path) -> None:
        self.lang_dir = Path(lang_dir)
        self.log_path = self.lang_dir / "ai_translate.log"

        tr_conf = conf.get("translator", {}) if isinstance(conf, dict) else {}
        if not isinstance(tr_conf, dict):
            tr_conf = {}

        self.provider: str = str(tr_conf.get("provider") or "mock").strip().lower()

        # DeepL keys (canonical)
        self.deepl_key_1: str = str(tr_conf.get("deepl_key_1") or "").strip()
        self.deepl_key_2: str = str(tr_conf.get("deepl_key_2") or "").strip()

        # LibreTranslate URL (may be empty; caller or UI may set default)
        self.libre_url: str = str(tr_conf.get("libretranslate_url") or "").strip()

        self._dbg(
            "init",
            provider=self.provider,
            has_deepl1=bool(self.deepl_key_1),
            has_deepl2=bool(self.deepl_key_2),
            libre_url=self.libre_url,
            log_path=str(self.log_path),
        )

    # ---------------------------------------------------------
    def translate(self, text: str, target_lang: str, source_lang: str = "en") -> str:
        """
        Повертає переклад тексту.
        На помилці — повертає text.
        """
        text = text or ""
        target_lang = (target_lang or "").strip().lower()
        source_lang = (source_lang or "en").strip().lower()

        provider = self.provider
        if provider not in ("mock", "deepl", "libretranslate"):
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
                    "ENTER", f"{target_lang} provider={provider} src={source_lang}"
                )
            )

        if not target_lang or target_lang == source_lang:
            self._append_log(self._ts_line("SKIP", "empty target or same as source"))
            return text

        try:
            provider_used = provider

            if provider == "mock":
                result = text

            elif provider == "deepl":
                try:
                    result = self._translate_deepl(text, target_lang)
                except Exception as e:  # noqa: BLE001
                    if DEBUG_AI_TRANSLATOR:
                        self._log_fail(target_lang, "deepl", str(e))
                    # fallback to LibreTranslate if possible
                    result = self._translate_libre(text, source_lang, target_lang)
                    provider_used = "libretranslate"

            elif provider == "libretranslate":
                result = self._translate_libre(text, source_lang, target_lang)

            else:
                result = text

            if DEBUG_AI_TRANSLATOR:
                self._log_ok(target_lang, provider_used, preview=text[:60])
            return result

        except Exception as e:  # noqa: BLE001
            if DEBUG_AI_TRANSLATOR:
                self._log_fail(target_lang, provider, str(e))
            return text

    # ---------------------------------------------------------
    @staticmethod
    def _deepl_lang(target_lang: str) -> str:
        s = (target_lang or "").strip()
        if not s:
            return "EN"
        base = s.replace("_", "-").split("-", 1)[0]
        return base.upper()

    def _translate_deepl(self, text: str, target_lang: str) -> str:
        candidates = [
            ("key1", self.deepl_key_1),
            ("key2", self.deepl_key_2),
        ]
        candidates = [(slot, k) for slot, k in candidates if k]

        if not candidates:
            raise ValueError("DeepL keys are missing (deepl_key_1/deepl_key_2)")

        url = "https://api-free.deepl.com/v2/translate"
        payload = {"text": text, "target_lang": self._deepl_lang(target_lang)}

        last_err: Optional[str] = None

        for slot, auth_key in candidates:
            headers = {"Authorization": f"DeepL-Auth-Key {auth_key}"}
            try:
                if DEBUG_AI_TRANSLATOR:
                    logger.warning("DEEPL USING %s", slot)
                    self._append_log(
                        self._ts_line(
                            "DEEPL", f"try {slot} target={payload['target_lang']}"
                        )
                    )

                r = requests.post(url, data=payload, headers=headers, timeout=15)
                if r.status_code != 200:
                    raise ConnectionError(f"HTTP {r.status_code}: {r.text[:200]}")
                data = r.json()
                return data["translations"][0]["text"]

            except Exception as e:  # noqa: BLE001
                last_err = f"{slot}: {e}"
                continue

        raise ConnectionError(last_err or "DeepL failed")

    @staticmethod
    def _normalize_libre_url(url: str) -> str:
        url = (url or "").strip()
        if not url:
            return ""
        if not url.rstrip("/").endswith("/translate"):
            url = url.rstrip("/") + "/translate"
        return url

    def _translate_libre(self, text: str, source_lang: str, target_lang: str) -> str:
        libre_url = self._normalize_libre_url(self.libre_url)
        if not libre_url:
            raise ValueError("LibreTranslate URL is missing (libretranslate_url)")

        payload = {
            "q": text,
            "source": source_lang,
            "target": target_lang,
            "format": "text",
        }

        self._append_log(
            self._ts_line(
                "LIBRE", f"POST {libre_url} src={source_lang} tgt={target_lang}"
            )
        )
        r = requests.post(libre_url, json=payload, timeout=20)
        if r.status_code != 200:
            raise ConnectionError(f"HTTP {r.status_code}: {r.text[:200]}")
        data = r.json()
        out = data.get("translatedText")
        if not isinstance(out, str):
            raise ValueError("LibreTranslate bad response")
        return out

    # ---------------------------------------------------------
    def _log_ok(self, lang: str, provider: str, preview: str) -> None:
        self._append_log(self._ts_line("OK", f"{lang} {provider} | {preview}"))

    def _log_fail(self, lang: str, provider: str, error: str) -> None:
        self._append_log(self._ts_line("FAIL", f"{lang} {provider} | {error}"))

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
