"""Нормализация и форматирование госномеров Кыргызстана.

Актуальный формат: «01 KG 123 ABC» (код региона, KG, три цифры, три буквы).
Старые форматы (кириллица и пр.) тоже допускаются: номер хранится в
нормализованном виде (латиница, без пробелов, без «KG» после кода региона).
"""
import re

# Кириллические буквы, похожие на латинские (на номерах используется латиница).
_CYR_TO_LAT = str.maketrans(
    {
        "А": "A", "В": "B", "Е": "E", "К": "K", "М": "M", "Н": "H",
        "О": "O", "Р": "P", "С": "C", "Т": "T", "У": "Y", "Х": "X",
        "а": "A", "в": "B", "е": "E", "к": "K", "м": "M", "н": "H",
        "о": "O", "р": "P", "с": "C", "т": "T", "у": "Y", "х": "X",
    }
)

_STRIP = re.compile(r"[^0-9A-ZА-ЯЁ]")
_KG_PREFIX = re.compile(r"^(\d{2})KG(.*)$")
_NEW_FORMAT = re.compile(r"^(\d{2})(\d{3})([A-Z]{3})$")


def normalize_plate(raw: str) -> str:
    """'01 KG 123 abc' / '01 123 АВС' -> '01123ABC'."""
    value = (raw or "").upper().translate(_CYR_TO_LAT)
    value = _STRIP.sub("", value)
    match = _KG_PREFIX.match(value)
    if match:
        value = match.group(1) + match.group(2)
    return value


def format_plate(normalized: str) -> str:
    """'01123ABC' -> '01 KG 123 ABC'. Нестандартные номера возвращаются как есть."""
    match = _NEW_FORMAT.match(normalized or "")
    if match:
        return f"{match.group(1)} KG {match.group(2)} {match.group(3)}"
    return normalized or ""


def is_valid_plate(normalized: str) -> bool:
    return 4 <= len(normalized) <= 12 and any(ch.isdigit() for ch in normalized)


def region_code(normalized: str):
    """Код региона по новому формату номера или None."""
    match = _NEW_FORMAT.match(normalized or "")
    return match.group(1) if match else None
