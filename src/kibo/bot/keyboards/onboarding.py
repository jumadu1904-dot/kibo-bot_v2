"""Keyboards for the steps shared between the onboarding wizard and
Configuració/Settings (language, briefing time, news topics). The
`namespace` (see kibo.bot.callbacks) tells the handler whether picking an
option should advance onboarding or return to the Settings screen."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from kibo.bot import callbacks
from kibo.i18n import t
from kibo.services.onboarding import BRIEFING_PRESETS, NEWS_TOPICS

_LANGUAGES = [("en", "English"), ("es", "Español"), ("ca", "Català")]


def language_keyboard(namespace: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(label, callback_data=callbacks.build(namespace, "lang", code))]
            for code, label in _LANGUAGES
        ]
    )


def briefing_keyboard(namespace: str, lang: str) -> InlineKeyboardMarkup:
    preset_row = [
        InlineKeyboardButton(preset, callback_data=callbacks.build(namespace, "briefing", preset))
        for preset in BRIEFING_PRESETS
    ]
    return InlineKeyboardMarkup(
        [
            preset_row,
            [
                InlineKeyboardButton(
                    t("briefing.button_custom", lang),
                    callback_data=callbacks.build(namespace, "briefing", "custom"),
                )
            ],
            [
                InlineKeyboardButton(
                    t("briefing.button_off", lang),
                    callback_data=callbacks.build(namespace, "briefing", "off"),
                )
            ],
        ]
    )


def topics_keyboard(selected: list[str], namespace: str, lang: str) -> InlineKeyboardMarkup:
    rows = []
    for topic in NEWS_TOPICS:
        label = t(f"topics.{topic}", lang)
        if topic in selected:
            label = f"✔️ {label}"
        rows.append(
            [InlineKeyboardButton(label, callback_data=callbacks.build(namespace, "topic", topic))]
        )
    rows.append(
        [
            InlineKeyboardButton(
                t("topics.done_button", lang),
                callback_data=callbacks.build(namespace, "topics_done"),
            )
        ]
    )
    return InlineKeyboardMarkup(rows)
