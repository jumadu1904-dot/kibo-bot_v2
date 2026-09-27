from kibo.i18n import t


def test_translates_in_each_language():
    assert "Kibo" in t("start.welcome_new", "ca", name="Joan")
    assert "Joan" in t("start.welcome_back", "es", name="Joan")


def test_unknown_language_falls_back_to_english():
    assert t("start.welcome_back", "fr", name="Joan") == t("start.welcome_back", "en", name="Joan")


def test_unknown_key_returns_key():
    assert t("does.not.exist") == "does.not.exist"
