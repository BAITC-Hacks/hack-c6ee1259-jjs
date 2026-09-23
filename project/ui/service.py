"""Call the core and verify alternatives without changing its recommendations."""
from datetime import date, timedelta
from src import recommender

DATASET_START = recommender.DATASET_START
DATASET_END = recommender.DATASET_END


def _suggestions(request, result):
    """Change one constraint at a time; every alternative must pass the core.

    Checking distinct catalog prices in ascending order finds the actual minimum,
    even if that contractor would not enter the top three at a larger budget.
    Diagnostics alone cannot establish that the later filters would pass.
    """
    suggestions = {}
    if result["status"] != "no_eligible":
        return suggestions
    if result["diagnostics"]["budget"]:
        prices = sorted({row["price_from_kzt"] for row in recommender._load_contractors()
                         if row["price_from_kzt"] > request["budget"]})
        for price in prices:
            alternative = recommender.recommend({**request, "budget": price})
            if alternative["status"] == "matched":
                suggestions["minimum_budget_kzt"] = price
                suggestions["budget_increase_kzt"] = price - request["budget"]
                break
    if result["diagnostics"]["busy"]:
        next_date = date.fromisoformat(str(request["date"])) + timedelta(days=1)
        while next_date <= DATASET_END:
            alternative = recommender.recommend({**request, "date": next_date.isoformat()})
            if alternative["status"] == "matched":
                suggestions["next_available_date"] = next_date.isoformat()
                break
            next_date += timedelta(days=1)
    return suggestions


def get_recommendations(request):
    """Keep form values and verified alternatives alongside the core response."""
    request = dict(request)
    result = recommender.recommend(request)
    return {**result, "request": request, "suggestions": _suggestions(request, result)}
