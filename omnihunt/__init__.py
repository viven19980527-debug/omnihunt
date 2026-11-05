"""OmniHunt - multi-source search aggregator.

clearnet engines + .onion indexes + adult site catalogs + magnet indexes,
merged, de-duplicated and ranked locally.
"""
from .engine import SearchEngine, quick_search
from .models import Result, SearchResponse

__version__ = "1.0.0"
__all__ = ["SearchEngine", "quick_search", "Result", "SearchResponse", "__version__"]
