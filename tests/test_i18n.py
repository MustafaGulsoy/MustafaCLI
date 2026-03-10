import pytest
from src.i18n.translator import Translator


def test_translate_en():
    t = Translator("en")
    assert t.t("welcome") == "Welcome to MustafaCLI"


def test_translate_tr():
    t = Translator("tr")
    assert t.t("welcome") == "MustafaCLI'ye hoş geldiniz"


def test_fallback_to_en():
    t = Translator("fr")
    assert t.t("welcome") == "Welcome to MustafaCLI"


def test_missing_key():
    t = Translator("en")
    assert t.t("nonexistent_key") == "nonexistent_key"


def test_format_params():
    t = Translator("en")
    result = t.t("tool_executing", tool_name="BashTool")
    assert result == "Executing tool: BashTool"


def test_set_locale():
    t = Translator("en")
    assert t.t("welcome") == "Welcome to MustafaCLI"
    t.set_locale("tr")
    assert t.t("welcome") == "MustafaCLI'ye hoş geldiniz"
