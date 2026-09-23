"""Call the core without filtering, sorting or changing its recommendations."""
from src import recommender


def get_recommendations(request):
    """Keep submitted form values alongside the unmodified core response."""
    return {**recommender.recommend(dict(request)), "request": dict(request)}
