"""Format of `callback_data` for inline keyboards: "<namespace>:<action>:<arg>",
e.g. "menu:agenda", "onboard:lang:ca", "settings:topics:business". The
namespace tells a handler shared between onboarding and Configuració
(e.g. the language picker) whether finishing a step should advance the
onboarding wizard or return to the Settings screen."""

NAMESPACE_ONBOARD = "onboard"
# Used when a step shared with onboarding (language/briefing/topics picker) is
# opened from the Settings screen, so it knows to return there instead of
# advancing onboarding_step.
NAMESPACE_SETTINGS = "settings"
# The Settings root screen's own buttons ("Language", "Briefing", ...) — kept
# disjoint from NAMESPACE_SETTINGS so python-telegram-bot's prefix-based
# routing (only the first matching handler runs) can't confuse the two.
NAMESPACE_SETTINGS_MENU = "settingsmenu"
NAMESPACE_MENU = "menu"
# Google connect/disconnect screen, reused by onboarding (namespace=onboard,
# "later" to skip) and Settings (namespace=settings, "disconnect").
NAMESPACE_GOOGLE = "google"
NAMESPACE_AGENDA = "agenda"
NAMESPACE_TASKS = "tasks"
NAMESPACE_CONFIRM = "confirm"
NAMESPACE_REMINDERS = "reminders"
NAMESPACE_TASKLIST = "tasklist"


def build(namespace: str, action: str, arg: str = "") -> str:
    return f"{namespace}:{action}:{arg}" if arg else f"{namespace}:{action}"


def parse(data: str) -> tuple[str, str, str]:
    parts = data.split(":", 2)
    namespace = parts[0]
    action = parts[1] if len(parts) > 1 else ""
    arg = parts[2] if len(parts) > 2 else ""
    return namespace, action, arg
