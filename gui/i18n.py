"""Small own EN/RU view catalog; internal option IDs are never translated."""
import json
from pathlib import Path
from PySide6.QtCore import QLocale


def language(choice):
    if choice in ('en', 'ru'):
        return choice
    return 'ru' if QLocale.system().name().lower().startswith('ru') else 'en'


def catalog(choice):
    if language(choice) != 'ru':
        return {}
    try:
        data = json.loads((Path(__file__).parent/'lang'/'ru.json').read_text(encoding='utf8'))
        return {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, str)}
    except (OSError, ValueError):
        return {}


def translate(text, choice):
    return catalog(choice).get(text, text)
