"""Form parameters only: every submitted preset calls the real core."""
from datetime import date

PRESETS = [
    dict(city="Алматы", date=date(2026, 9, 30), event_type="корпоратив", category="Ведущий", budget=1200000, duration=6, language="русский"),
    dict(city="Астана", date=date(2026, 9, 23), event_type="свадьба", category="Флорист", budget=350000, duration=None, language="русский"),
    dict(city="Алматы", date=date(2026, 9, 23), event_type="свадьба", category="Декоратор", budget=1000000, duration=None, language="русский"),
    dict(city="Астана", date=date(2026, 9, 23), event_type="корпоратив", category="Декоратор", budget=3000000, duration=None, language=None),
]
