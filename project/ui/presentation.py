"""Presentation only: retain the core's facts and selected description excerpt."""
from datetime import date


MONTHS = ("января", "февраля", "марта", "апреля", "мая", "июня",
          "июля", "августа", "сентября", "октября", "ноября", "декабря")


def money(value):
    # Preserve fractional prices rather than rounding a suggested minimum down.
    return f"{value:,.2f}".rstrip("0").rstrip(".").replace(",", " ").replace(".", ",") + " ₸"


def human_date(value):
    day = date.fromisoformat(str(value))
    return f"{day.day} {MONTHS[day.month - 1]} {day.year}"


def explanation(card, request):
    """Rephrase technical sentences; leave the core's grounded excerpt intact."""
    price, budget = card["price_from_kzt"], request["budget"]
    text = card["explanation"]
    text = text.replace(
        f"Свободен на {request['date']}: дата отсутствует в списке занятости.",
        f"Свободен {human_date(request['date'])}.",
    )
    text = text.replace(
        f"Цена от {price:g} KZT при бюджете {budget:g} KZT; запас {budget - price:g} KZT.",
        f"Стартовая цена {money(price)} укладывается в бюджет {money(budget)}.",
    )
    text = text.replace(
        "max_hours не применимо; ограничение длительности не проверяется.",
        "Для этой категории ограничение по длительности не применяется.",
    )
    return text


def rejection_summary(diagnostics):
    reasons = [
        ("busy", "занят на дату", "заняты на дату"),
        ("format", "не работает с этим форматом", "не работают с этим форматом"),
        ("budget", "превышает бюджет", "превышают бюджет"),
        ("language", "не подходит по языку", "не подходят по языку"),
        ("duration", "не подходит по длительности", "не подходят по длительности"),
    ]
    parts = []
    for key, singular, plural in reasons:
        count = diagnostics[key]
        if count:
            label = singular if count % 10 == 1 and count % 100 != 11 else plural
            parts.append(f"{count} {label}")
    return ", ".join(parts) + "." if parts else ""


def short_result_message(count, diagnostics):
    text = ("Найден 1 подрядчик, который проходит все условия." if count == 1 else
            "Найдены 2 подрядчика, которые проходят все условия.")
    text += (" Остальные кандидаты не добавляются, чтобы не нарушать требования "
             "по бюджету, дате, формату, языку или длительности.")
    summary = rejection_summary(diagnostics)
    return text + (f" Причины отсева: {summary}" if summary else "")
