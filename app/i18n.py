from contextvars import ContextVar
from functools import lru_cache
from pathlib import Path
import gettext as _gettext_mod

LOCALES_DIR = Path(__file__).parent.parent / "translations"
SUPPORTED: dict[str, str] = {"en": "English", "vi": "Tiếng Việt"}

_current_gettext: ContextVar = ContextVar("gettext", default=lambda s: s)
_current_ngettext: ContextVar = ContextVar(
    "ngettext", default=lambda s, p, n: s if n == 1 else p
)
_current_lang: ContextVar = ContextVar("lang", default="en")


@lru_cache(maxsize=None)
def _load(lang: str):
    return _gettext_mod.translation(
        "messages", localedir=str(LOCALES_DIR), languages=[lang], fallback=True
    )


def set_language(lang: str) -> tuple:
    if lang not in SUPPORTED:
        lang = "en"
    t = _load(lang)
    return (
        _current_gettext.set(t.gettext),
        _current_ngettext.set(t.ngettext),
        _current_lang.set(lang),
    )


def reset_language(tokens: tuple) -> None:
    for tok in tokens:
        tok.var.reset(tok)


def get_lang() -> str:
    return _current_lang.get()


def _(s: str) -> str:
    return _current_gettext.get()(s)


def ngettext(singular: str, plural: str, n: int) -> str:
    return _current_ngettext.get()(singular, plural, n)


_VI_MONTHS = [
    "", "Tháng 1", "Tháng 2", "Tháng 3", "Tháng 4",
    "Tháng 5", "Tháng 6", "Tháng 7", "Tháng 8",
    "Tháng 9", "Tháng 10", "Tháng 11", "Tháng 12",
]


def fmt_month_year(y: int, m: int) -> str:
    if get_lang() == "vi":
        return f"{_VI_MONTHS[m]} {y}"
    import calendar
    return f"{calendar.month_name[m]} {y}"
