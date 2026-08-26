from pathlib import Path  # noqa

from core.ai_translator import AITranslator


def test_translate_deepl_mock(monkeypatch, tmp_path):
    conf = {"translator": {"provider": "deepl", "deepl_api_key": "FAKE"}}
    ai = AITranslator(conf, lang_dir=tmp_path)

    # підміняємо запит requests.post
    def fake_post(url, data, headers, timeout):
        class Dummy:
            status_code = 200

            def json(self):
                return {"translations": [{"text": f"{data['text']} [DE_MOCK]"}]}

        return Dummy()

    import requests

    monkeypatch.setattr(requests, "post", fake_post)

    result = ai._translate_deepl("Тест перекладу", "de")
    assert "[DE_MOCK]" in result
