from core.lang_manager import LangManager


def test_translation_basic():
    lm = LangManager()
    assert lm.t("welcome_message") in (
        "Ласкаво просимо до LavrGPT05",
        "Willkommen bei LavrGPT05",
        "Welcome to LavrGPT05",
    )


def test_multi_language_output():
    lm = LangManager()
    lm.multi_language = True
    result = lm.t_multi("order_executed")
    assert "[UK]" in result and "[DE]" in result and "[EN]" in result
