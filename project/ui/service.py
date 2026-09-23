"""Single integration point for the future core service."""
from ui.mock_data import recommend as mock_recommend


def get_recommendations(request):
    """Replace this call with src.recommender.recommend; normalize to README contract.

    Do not silently fall back to mock when the real backend fails.
    """
    return mock_recommend(request)
