import csv
import json

import pytest

from src import recommend
from src import recommender


@pytest.fixture
def request_data():
    return dict(city="Алматы", category="Ведущий", date="2026-10-01",
                event_type="Свадьба", budget=100000, language="ru", duration=4,
                description="камерная свадьба")


@pytest.fixture
def catalog(tmp_path, monkeypatch):
    path = tmp_path / "contractors.csv"
    monkeypatch.setattr(recommender, "DATA_PATH", path)

    def write(*overrides):
        with path.open("w", encoding="utf-8-sig", newline="") as output:
            writer = csv.DictWriter(output, fieldnames=sorted(recommender.REQUIRED_COLUMNS))
            writer.writeheader()
            for index, override in enumerate(overrides):
                row = dict(id=str(index + 1), anon_name="Ведущий", city="Алматы", categories="Ведущий",
                           busy_dates="", event_formats="Свадьба|Корпоратив", price_from_kzt=50000,
                           languages="ru|kk", max_hours=6, description="Камерная свадьба. Живая музыка.")
                row.update(override)
                writer.writerow(row)
    return write


def ids(response):
    return [row["id"] for row in response["recommendations"]]


def test_busy_excluded(catalog, request_data):
    catalog(dict(id="busy", busy_dates='["2026-10-01"]'), dict(id="free"))
    result = recommend(request_data)
    assert ids(result) == ["free"]
    assert result["diagnostics"]["busy"] == 1


def test_over_budget_excluded(catalog, request_data):
    catalog(dict(price_from_kzt=100001), dict(id="boundary", price_from_kzt=100000))
    result = recommend(request_data)
    assert ids(result) == ["boundary"]
    assert result["diagnostics"]["budget"] == 1


def test_max_three_and_repeatable(catalog, request_data):
    catalog(*(dict(id=str(i)) for i in [5, 3, 1, 4, 2]))
    result = recommend(request_data)
    assert ids(result) == ["1", "2", "3"]
    assert result["diagnostics"]["remaining"] == 5
    assert all(recommend(request_data) == result for _ in range(5))
    catalog(*(dict(id=str(i)) for i in [2, 4, 1, 3, 5]))
    assert recommend(request_data) == result


def test_category_absent(catalog, request_data):
    catalog(dict(categories="Фотограф"), dict(city="Астана"))
    result = recommend(request_data)
    assert result["status"] == "category_absent"
    assert result["recommendations"] == []
    assert result["diagnostics"]["candidates"] == 0


def test_no_eligible(catalog, request_data):
    catalog(dict(price_from_kzt=200000))
    result = recommend(request_data)
    assert result["status"] == "no_eligible"
    assert result["recommendations"] == []
    assert result["diagnostics"]["remaining"] == 0


def test_date_changes_results(catalog, request_data):
    catalog(dict(id="first", busy_dates="2026-10-01|2026-10-03"),
            dict(id="second", busy_dates="2026-10-02"))
    assert ids(recommend(request_data)) == ["second"]
    assert ids(recommend({**request_data, "date": "2026-10-02"})) == ["first"]


def test_all_diagnostics_and_explanation(catalog, request_data):
    catalog(dict(busy_dates="2026-10-01", price_from_kzt=900000),
            dict(event_formats="Юбилей"), dict(price_from_kzt=100001),
            dict(languages="en"), dict(max_hours=3), dict(id="eligible"))
    result = recommend(request_data)
    assert result["status"] == "matched"
    assert result["diagnostics"] == dict(candidates=6, busy=1, format=1, budget=1,
                                          language=1, duration=1, remaining=1)
    explanation = result["recommendations"][0]["explanation"]
    for fact in ("2026-10-01", "50000", "100000", "Свадьба", "ru", "4 ч", "6 ч", "Камерная свадьба."):
        assert fact in explanation
    json.dumps(result, ensure_ascii=False, allow_nan=False)


@pytest.mark.parametrize("maximum", ["", "null", "None", "NaN", "4"])
def test_nullable_and_boundary_duration(catalog, request_data, maximum):
    catalog(dict(max_hours=maximum))
    result = recommend(request_data)
    assert result["status"] == "matched"
    if maximum != "4":
        assert "не применимо" in result["recommendations"][0]["explanation"]


def test_optional_filters_and_normalization(catalog, request_data):
    catalog(dict(languages='["kk"]', max_hours=1))
    result = recommend({**request_data, "city": " АЛМАТЫ ", "category": "ведущий",
                        "event_type": "свадьба", "duration": None, "language": None})
    assert result["status"] == "matched"


def test_tfidf_ranks_matching_description(catalog, request_data):
    catalog(dict(id="a", description="Спортивные соревнования"),
            dict(id="z", description="Камерная свадьба"))
    result = recommend(request_data)
    assert ids(result) == ["z", "a"]
    assert result["recommendations"][0]["score_components"]["semantic_similarity"] > 0


def test_budget_and_format_scores(catalog, request_data):
    catalog(dict(id="expensive", price_from_kzt=90000),
            dict(id="cheap", price_from_kzt=50000),
            dict(id="specialist", price_from_kzt=50000, event_formats="Свадьба"))
    assert ids(recommend(request_data)) == ["specialist", "cheap", "expensive"]


def test_price_breaks_score_tie(catalog, request_data):
    # 0.25 * 0.5 + 0.15 / 3 == 0.25 * 0.4 + 0.15 / 2.
    catalog(dict(id="a", price_from_kzt=60000, description=""),
            dict(id="z", price_from_kzt=50000, description="", event_formats="Свадьба|Юбилей|Корпоратив"))
    assert ids(recommend(request_data)) == ["z", "a"]


def test_empty_descriptions_and_zero_budget(catalog, request_data):
    catalog(dict(description="", price_from_kzt=0))
    result = recommend({**request_data, "budget": 0, "description": "!!!"})
    assert result["status"] == "matched"
    assert result["recommendations"][0]["score_components"]["semantic_similarity"] == 0
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("change", [dict(budget=-1), dict(budget="nan"), dict(duration=0),
                                      dict(duration="inf"), dict(date="2026-02-30"), dict(city="")])
def test_invalid_requests(catalog, request_data, change):
    catalog({})
    with pytest.raises(ValueError):
        recommend({**request_data, **change})


def test_missing_dataset_is_not_category_absent(catalog, request_data):
    with pytest.raises(FileNotFoundError):
        recommend(request_data)


def test_invalid_csv_schema(catalog, request_data):
    recommender.DATA_PATH.write_text("id,name\n1,Name\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Missing CSV columns"):
        recommend(request_data)


REAL_COLUMNS = [
    "id", "anon_name", "categories", "city", "city_imputed", "synthetic",
    "price_from_kzt", "price_imputed", "event_formats", "languages",
    "max_hours", "busy_dates", "description",
]


def test_real_csv_schema_and_metadata(tmp_path, monkeypatch, request_data):
    path = tmp_path / "contractors.csv"
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=REAL_COLUMNS)
        writer.writeheader()
        writer.writerow(dict(
            id="HK-test", anon_name="Анонимный подрядчик",
            categories="Музыкант | Ведущий", city="Алматы", city_imputed="False",
            synthetic="True", price_from_kzt="50000", price_imputed="True",
            event_formats="Корпоратив | Свадьба", languages="kk | ru",
            max_hours="null", busy_dates="2026-10-02|2026-10-03",
            description="Камерная свадьба.",
        ))
    monkeypatch.setattr(recommender, "DATA_PATH", path)
    result = recommend(request_data)
    assert result["status"] == "matched"
    row = result["recommendations"][0]
    assert row["anon_name"] == "Анонимный подрядчик"
    assert row["categories"] == ["Музыкант", "Ведущий"]
    assert row["event_formats"] == ["Корпоратив", "Свадьба"]
    assert row["languages"] == ["kk", "ru"]
    assert row["busy_dates"] == ["2026-10-02", "2026-10-03"]
    assert row["max_hours"] is None
    assert {key: row[key] for key in ("synthetic", "city_imputed", "price_imputed")} == {
        "synthetic": "True", "city_imputed": "False", "price_imputed": "True",
    }
    assert recommend({**request_data, "date": "2026-10-03"})["status"] == "no_eligible"
    assert recommend({**request_data, "category": "Музыкант"})["status"] == "matched"
    assert recommend({**request_data, "category": "Вед"})["status"] == "category_absent"


@pytest.mark.parametrize("missing", ["anon_name", "categories", "event_formats"])
def test_real_required_columns_are_validated(tmp_path, monkeypatch, request_data, missing):
    path = tmp_path / "contractors.csv"
    path.write_text(",".join(key for key in REAL_COLUMNS if key != missing) + "\n", encoding="utf-8")
    monkeypatch.setattr(recommender, "DATA_PATH", path)
    with pytest.raises(ValueError, match=f"Missing CSV columns: {missing}$"):
        recommend(request_data)


def test_repository_csv_loads_and_preserves_metadata():
    # Integration regression: exercise the actual dataset, not just a mock schema.
    with recommender.DATA_PATH.open(encoding="utf-8-sig", newline="") as source:
        raw = {row["id"]: row for row in csv.DictReader(source)}
    rows = recommender._load_contractors()
    assert len(rows) == len(raw) > 0
    for row in rows:
        for key in ("anon_name", "synthetic", "city_imputed", "price_imputed"):
            assert row[key] == raw[row["id"]][key].strip()
        for key in ("categories", "event_formats", "languages", "busy_dates"):
            assert row[key] == [value.strip() for value in raw[row["id"]][key].split("|") if value.strip()]
