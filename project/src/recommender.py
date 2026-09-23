"""Deterministic recommendations using hard filters followed by TF-IDF ranking.

Request: city, category, date (ISO YYYY-MM-DD), event_type, budget;
optional language, duration (hours), description (free text).
CSV: id, name, city, category, busy_dates, event_type, price_from_kzt,
languages, max_hours, description. Lists use JSON arrays or semicolons.
The real dataset is currently absent; this schema follows the task fields.
Diagnostics count the FIRST failed filter, in the order listed below.
category_absent means absent in the requested city; remaining is before top 3.
"""

import csv
import json
import math
import re
from collections import Counter
from datetime import date
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "contractors.csv"
REQUIRED_COLUMNS = {
    "id", "name", "city", "category", "busy_dates", "event_type",
    "price_from_kzt", "languages", "max_hours", "description",
}


def _norm(value):
    return str(value).strip().casefold()


def _number(value, field, positive=False):
    try:
        result = float(value)
    except (ValueError, TypeError):
        raise ValueError(f"{field} must be a finite number") from None
    if isinstance(value, bool) or not math.isfinite(result) or result < 0 or (positive and result == 0):
        raise ValueError(f"Invalid {field}: {value!r}")
    return result


def _iso_date(value):
    text = str(value)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        raise ValueError("date must use YYYY-MM-DD")
    return date.fromisoformat(text).isoformat()


def _items(value):
    value = value.strip()
    if not value:
        return []
    items = json.loads(value) if value.startswith("[") else value.split(";")
    if not isinstance(items, list) or any(not isinstance(item, str) for item in items):
        raise ValueError("List columns must contain strings")
    return [item.strip() for item in items if item.strip()]


def _load_contractors():
    with DATA_PATH.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Missing CSV columns: {', '.join(sorted(missing))}")
        rows = []
        ids = set()
        for raw in reader:
            if None in raw or any(value is None for value in raw.values()):
                raise ValueError("Malformed CSV row")
            row = {key: value.strip() for key, value in raw.items()}
            if not row["id"] or row["id"] in ids:
                raise ValueError("Contractor IDs must be nonempty and unique")
            ids.add(row["id"])
            row["price_from_kzt"] = _number(row["price_from_kzt"], "price_from_kzt")
            row["max_hours"] = (
                None if _norm(row["max_hours"]) in {"", "null", "none", "nan"}
                else _number(row["max_hours"], "max_hours")
            )
            row["busy_dates"] = [_iso_date(item) for item in _items(row["busy_dates"])]
            row["event_type"] = _items(row["event_type"])
            row["languages"] = _items(row["languages"])
            rows.append(row)
    return sorted(rows, key=lambda row: row["id"])


def _tokens(text):
    return re.findall(r"\w+", text.casefold(), flags=re.UNICODE)


def _similarities(query, documents):
    """Cosine TF-IDF, smoothed IDF fitted only on eligible descriptions."""
    counts = [Counter(_tokens(document)) for document in documents]
    frequencies = Counter(token for count in counts for token in sorted(count))
    idf = {token: math.log((1 + len(documents)) / (1 + count)) + 1
           for token, count in sorted(frequencies.items())}

    def vector(count):
        weights = {token: count[token] * idf[token] for token in sorted(count) if token in idf}
        norm = math.sqrt(sum(weight * weight for weight in weights.values()))
        return {token: weight / norm for token, weight in weights.items()} if norm else {}

    query_vector = vector(Counter(_tokens(query)))
    return [sum(weight * query_vector.get(token, 0) for token, weight in vector(count).items())
            for count in counts]


def _explanation(row, request, query):
    price, budget = row["price_from_kzt"], request["budget"]
    facts = [
        f"Свободен на {request['date']}: дата отсутствует в списке занятости.",
        f"Цена от {price:g} KZT при бюджете {budget:g} KZT; запас {budget - price:g} KZT.",
        f"Поддерживает формат «{request['event_type']}» (в данных: {', '.join(row['event_type'])}).",
    ]
    language = request.get("language")
    facts.append(f"Язык «{language}» поддерживается." if language else
                 f"Язык не задан; в данных: {', '.join(row['languages']) or 'не указан'}.")
    duration, maximum = request.get("duration"), row["max_hours"]
    if maximum is None:
        facts.append("max_hours не применимо; ограничение длительности не проверяется.")
    elif duration is not None:
        facts.append(f"Длительность {duration:g} ч не превышает максимум {maximum:g} ч.")
    else:
        facts.append(f"Длительность не задана; максимум {maximum:g} ч.")
    fragments = [part.strip() for part in re.split(r"(?<=[.!?])\s+", row["description"]) if part.strip()]
    if fragments:
        scores = _similarities(query, fragments)
        fragment = fragments[max(range(len(fragments)), key=lambda index: scores[index])]
        facts.append(f"Из описания: «{fragment}».")
    else:
        facts.append("Описание в данных отсутствует.")
    return " ".join(facts)


def recommend(request):
    """Return {status, recommendations, diagnostics}; never relax hard filters.

    Score = 0.6 * description cosine + 0.25 * (1 - price / budget)
    + 0.15 * format specificity (1 / number of supported event types).
    For zero budget, eligible free contractors have budget fit 1.
    Ties: price ascending, then textual ID ascending. Missing/invalid CSV
    raises an error rather than falsely reporting category_absent.
    """
    request = dict(request)
    for key in ("city", "category", "event_type"):
        if not isinstance(request.get(key), str) or not request[key].strip():
            raise ValueError(f"{key} is required")
        request[key] = request[key].strip()
    request["date"] = _iso_date(request.get("date"))
    request["budget"] = _number(request.get("budget"), "budget")
    if request.get("duration") is not None:
        request["duration"] = _number(request["duration"], "duration", positive=True)
    if request.get("language") is not None:
        if not isinstance(request["language"], str):
            raise ValueError("language must be a string")
        request["language"] = request["language"].strip()
    if request.get("description") is not None and not isinstance(request["description"], str):
        raise ValueError("description must be a string")
    candidates = [row for row in _load_contractors()
                  if _norm(row["city"]) == _norm(request["city"])
                  and _norm(row["category"]) == _norm(request["category"])]
    diagnostics = dict.fromkeys(("candidates", "busy", "format", "budget", "language", "duration", "remaining"), 0)
    diagnostics["candidates"] = len(candidates)
    eligible = []
    for row in candidates:
        checks = (
            ("busy", request["date"] in row["busy_dates"]),
            ("format", _norm(request["event_type"]) not in {_norm(item) for item in row["event_type"]}),
            ("budget", row["price_from_kzt"] > request["budget"]),
            ("language", bool(request.get("language")) and _norm(request["language"]) not in {_norm(item) for item in row["languages"]}),
            ("duration", request.get("duration") is not None and row["max_hours"] is not None
             and request["duration"] > row["max_hours"]),
        )
        for reason, failed in checks:
            if failed:
                diagnostics[reason] += 1
                break
        else:
            eligible.append(row)
    diagnostics["remaining"] = len(eligible)
    query = request.get("description") or request["event_type"]
    similarities = _similarities(query, [row["description"] for row in eligible])
    recommendations = []
    for row, similarity in zip(eligible, similarities):
        budget_fit = 1 - row["price_from_kzt"] / request["budget"] if request["budget"] else 1.0
        format_relevance = 1 / len({_norm(item) for item in row["event_type"]})
        score = 0.6 * similarity + 0.25 * budget_fit + 0.15 * format_relevance
        recommendations.append({**row, "score": score,
                                "score_components": {"semantic_similarity": similarity,
                                                     "budget_fit": budget_fit,
                                                     "format_relevance": format_relevance},
                                "explanation": _explanation(row, request, query)})
    recommendations.sort(key=lambda row: (-row["score"], row["price_from_kzt"], row["id"]))
    return {"status": "matched" if eligible else "no_eligible" if candidates else "category_absent",
            "recommendations": recommendations[:3], "diagnostics": diagnostics}
