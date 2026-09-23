"""Regression checks for verified alternatives, date boundaries and the live UI."""
import csv
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src import recommender
from ui.presets import PRESETS
from ui.presentation import explanation, money, short_result_message
from ui.service import get_recommendations

PROJECT = Path(__file__).resolve().parents[1]


@pytest.fixture
def query():
    return dict(city="Алматы", category="Ведущий", date="2026-09-30",
                event_type="корпоратив", budget=100, language="русский", duration=6)


@pytest.fixture
def write_catalog(tmp_path, monkeypatch):
    path = tmp_path / "contractors.csv"
    monkeypatch.setattr(recommender, "DATA_PATH", path)

    def write(*changes):
        with path.open("w", encoding="utf-8", newline="") as output:
            writer = csv.DictWriter(output, fieldnames=sorted(recommender.REQUIRED_COLUMNS))
            writer.writeheader()
            for index, change in enumerate(changes):
                row = dict(id=str(index), anon_name="Имя", categories="Ведущий", city="Алматы",
                           price_from_kzt=100, event_formats="корпоратив", languages="русский",
                           max_hours=6, busy_dates="", description="Работа с аудиторией.")
                writer.writerow({**row, **change})
    return write


def test_budget_suggestion_is_minimum_that_passes_every_other_filter(write_catalog, query):
    write_catalog(dict(price_from_kzt=110, languages="английский"),
                  dict(price_from_kzt=120, max_hours=2),
                  dict(price_from_kzt=130, busy_dates=query["date"]),
                  dict(price_from_kzt=140, event_formats="свадьба"),
                  dict(price_from_kzt=250), dict(price_from_kzt=200))
    result = get_recommendations(query)
    assert result["status"] == "no_eligible"
    assert result["suggestions"] == {"minimum_budget_kzt": 200, "budget_increase_kzt": 100}
    assert get_recommendations(query) == result
    assert recommender.recommend({**query, "budget": 200})["status"] == "matched"
    assert recommender.recommend({**query, "budget": 199})["status"] == "no_eligible"
    assert result["request"] == query


@pytest.mark.parametrize("failure", [dict(languages="английский"), dict(max_hours=2),
                                      dict(event_formats="свадьба"), dict(busy_dates="2026-09-30")])
def test_no_budget_advice_for_other_failed_constraints(write_catalog, query, failure):
    write_catalog(dict(price_from_kzt=200, **failure))
    result = get_recommendations(query)
    assert result["status"] == "no_eligible"
    assert result["suggestions"] == {}


def test_nearest_date_preserves_budget_and_other_requirements(write_catalog, query):
    write_catalog(dict(busy_dates="2026-09-30|2026-10-01"),
                  dict(busy_dates="2026-09-30", languages="английский"))
    result = get_recommendations(query)
    assert result["suggestions"] == {"next_available_date": "2026-10-02"}
    assert recommender.recommend({**query, "date": "2026-10-02"})["status"] == "matched"
    assert recommender.recommend({**query, "date": "2026-10-01"})["status"] == "no_eligible"


def test_no_date_suggestion_outside_calendar(write_catalog, query):
    write_catalog(dict(busy_dates="2026-12-31"))
    result = get_recommendations({**query, "date": "2026-12-31"})
    assert result["status"] == "no_eligible"
    assert result["suggestions"] == {}


@pytest.mark.parametrize("day", ["2026-09-22", "2027-01-01"])
def test_outside_calendar_is_unknown_not_free(write_catalog, query, day):
    write_catalog({})
    with pytest.raises(ValueError, match="доступность неизвестна"):
        recommender.recommend({**query, "date": day})


@pytest.mark.parametrize("day", ["2026-09-23", "2026-12-31"])
def test_calendar_endpoints_are_allowed(write_catalog, query, day):
    write_catalog({})
    assert recommender.recommend({**query, "date": day})["status"] == "matched"


def test_human_explanation_keeps_profile_facts(write_catalog, query):
    write_catalog(dict(price_from_kzt=50, max_hours=""))
    card = recommender.recommend(query)["recommendations"][0]
    text = explanation(card, query)
    assert "30 сентября 2026" in text
    assert "50 ₸" in text and "100 ₸" in text
    assert "корпоратив" in text and "русский" in text
    assert "Для этой категории ограничение по длительности не применяется." in text
    assert "Работа с аудиторией." in text
    assert "max_hours" not in text and "дата отсутствует" not in text
    assert money(1200000) == "1 200 000 ₸"
    assert money(1200000.50) == "1 200 000,5 ₸"


def test_short_results_include_real_rejection_reasons():
    diagnostics = dict(busy=2, format=0, budget=1, language=0, duration=0)
    text = short_result_message(1, diagnostics)
    assert "Найден 1 подрядчик" in text
    assert "2 заняты на дату, 1 превышает бюджет." in text
    assert "Найдены 2 подрядчика" in short_result_message(2, diagnostics)


def _submit(app):
    app.button(key="FormSubmitter:request_form-Подобрать").click().run(timeout=30)
    assert not app.exception
    assert not app.error


@pytest.mark.parametrize("index,status,count", [
    (0, "matched", 3), (1, "matched", 1), (2, "no_eligible", 0), (3, "category_absent", 0),
])
def test_demo_scenarios_in_streamlit(index, status, count):
    app = AppTest.from_file(str(PROJECT / "app.py")).run()
    app.button[index].click().run()
    _submit(app)
    result = app.session_state["results"][0]
    assert result["status"] == status
    assert len(result["recommendations"]) == count
    core = recommender.recommend(result["request"])
    assert result["recommendations"] == core["recommendations"]
    assert result["diagnostics"] == core["diagnostics"]
    assert result["request"] == {**PRESETS[index], "date": PRESETS[index]["date"].isoformat()}
    rendered = "\n".join(element.value for kind in ("markdown", "caption", "info", "warning", "success")
                         for element in app.get(kind))
    for internal in ("matched", "no_eligible", "category_absent", "Diagnostics", "Evidence", "max_hours", "Score:"):
        assert internal not in rendered
    assert app.get("progress")[0].proto.text == f"Кандидаты в городе и категории: {core['diagnostics']['candidates']}"
    assert app.get("progress")[-1].proto.text == f"↓ Рекомендованы: {count}"
    if index == 2:
        suggestions = result["suggestions"]
        assert suggestions["minimum_budget_kzt"] > result["request"]["budget"]
        changed = {**result["request"], "budget": suggestions["minimum_budget_kzt"]}
        assert recommender.recommend(changed)["status"] == "matched"
        assert "увеличьте бюджет минимум до" in rendered
    if index == 1:
        assert "Найден 1 подрядчик, который проходит все условия." in rendered
        assert "Синтетический профиль" in rendered


def test_compare_two_dates_in_streamlit():
    app = AppTest.from_file(str(PROJECT / "app.py")).run()
    app.checkbox(key="compare").check()
    _submit(app)
    results = app.session_state["results"]
    assert [item["request"]["date"] for item in results] == ["2026-09-30", "2026-10-29"]
    for result in results:
        core = recommender.recommend(result["request"])
        assert result["recommendations"] == core["recommendations"]
        assert result["diagnostics"] == core["diagnostics"]
    assert [card["id"] for card in results[0]["recommendations"]] != [card["id"] for card in results[1]["recommendations"]]
