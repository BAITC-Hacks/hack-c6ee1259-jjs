"""Deterministic demo fixtures, independent of data/ and src/."""
from datetime import date

PRESETS = [
    dict(city="Алматы", date=date(2026, 9, 30), event_type="корпоратив", category="Ведущий", budget=1200000, duration=6, language="русский"),
    dict(city="Астана", date=date(2026, 9, 23), event_type="свадьба", category="Флорист", budget=350000, duration=None, language="русский"),
    dict(city="Алматы", date=date(2026, 9, 23), event_type="свадьба", category="Декоратор", budget=1000000, duration=None, language="русский"),
    dict(city="Астана", date=date(2026, 9, 23), event_type="корпоратив", category="Декоратор", budget=3000000, duration=None, language=None),
]


def profile(id, name, category, city, price, formats, languages, hours, busy=(), **flags):
    return dict(id=id, name=name, categories=[category], city=city, price=price,
                formats=formats, languages=languages, max_hours=hours, busy_dates=busy,
                synthetic=True, city_imputed=flags.get("city_imputed", False),
                price_imputed=flags.get("price_imputed", False))


PROFILES = [
    profile("h1", "Арман · demo", "Ведущий", "Алматы", 650000, ["корпоратив", "свадьба"], ["русский", "казахский"], 8, ["2026-10-29"]),
    profile("h2", "Дана · demo", "Ведущий", "Алматы", 800000, ["корпоратив"], ["русский", "английский"], 6, price_imputed=True),
    profile("h3", "Тимур · demo", "Ведущий", "Алматы", 1000000, ["корпоратив", "юбилей"], ["русский"], 7, ["2026-10-29"], city_imputed=True),
    profile("h4", "Алия · demo", "Ведущий", "Алматы", 900000, ["корпоратив"], ["русский", "казахский"], 9, ["2026-09-30"]),
    profile("h5", "Максат · demo", "Ведущий", "Алматы", 1500000, ["корпоратив"], ["русский"], 8),
    profile("f1", "Гүл Studio · demo", "Флорист", "Астана", 280000, ["свадьба"], ["русский", "казахский"], None),
    profile("d1", "Ақ Decor · demo", "Декоратор", "Астана", 1200000, ["корпоратив", "свадьба"], ["русский"], None, ["2026-09-23"]),
    profile("d2", "Aura Decor · demo", "Декоратор", "Астана", 1800000, ["свадьба"], ["русский"], None),
    profile("d3", "Nova Decor · demo", "Декоратор", "Астана", 3500000, ["корпоратив"], ["русский"], None, price_imputed=True),
]


def recommend(q):
    candidates = [p for p in PROFILES if p["city"] == q["city"] and q["category"] in p["categories"]]
    funnel = [{"label": "Кандидаты", "count": len(candidates)}]
    diagnostics, suggestions = [], []
    stages = [
        ("Свободны на дату", lambda p: q["date"] not in p["busy_dates"], "Заняты на выбранную дату", "Попробуйте другую дату."),
        ("Подходят по формату", lambda p: q["event_type"] in p["formats"], "Не работают с этим форматом", "Выберите другой формат, если он подходит мероприятию."),
        ("Проходят бюджет", lambda p: p["price"] <= q["budget"], "Цена выше бюджета", "Увеличьте бюджет или выберите другую категорию."),
        ("Проходят язык/длительность", lambda p: (not q["language"] or q["language"] in p["languages"]) and (q["duration"] is None or p["max_hours"] is None or p["max_hours"] >= q["duration"]), "Не подходят язык или длительность", "Проверьте язык и длительность; изменяйте их только при допустимости."),
    ]
    eligible = candidates
    for label, predicate, reason, suggestion in stages:
        rejected = [p for p in eligible if not predicate(p)]
        eligible = [p for p in eligible if predicate(p)]
        funnel.append({"label": label, "count": len(eligible)})
        if rejected:
            diagnostics.append({"reason": reason, "count": len(rejected), "names": [p["name"] for p in rejected]})
            suggestions.append(suggestion)
    cards = []
    for p in eligible:
        score = round(100 * (1 - p["price"] / q["budget"]), 2)
        duration = "Длительность не ограничена присутствием" if p["max_hours"] is None else f"До {p['max_hours']} ч на площадке"
        explanation = (f"Свободен {q['date']}, работает с форматом «{q['event_type']}»; цена от {p['price']:,} ₸ "
                       f"оставляет {q['budget'] - p['price']:,} ₸ бюджета. {duration}; языки: {', '.join(p['languages'])}.")
        cards.append({**p, "score": score, "explanation": explanation,
                      "evidence": {"source": "ui/mock_data.py — временный синтетический профиль", "id": p["id"],
                                   "requested_date": q["date"], "busy_dates": list(p["busy_dates"]),
                                   "event_formats": p["formats"], "languages": p["languages"],
                                   "max_hours": p["max_hours"], "price_from_kzt": p["price"],
                                   "score_formula": "100 × (1 − price / budget)"}})
    cards.sort(key=lambda p: (-p["score"], p["id"]))
    cards = cards[:3]
    funnel.append({"label": "Рекомендованы", "count": len(cards)})
    status = "category_absent" if not candidates else "matched" if cards else "no_eligible"
    return dict(status=status, cards=cards, funnel=funnel, diagnostics=diagnostics,
                suggestions=suggestions, source="mock", request=dict(q))
