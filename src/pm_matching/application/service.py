# src/pm_matching/application/service.py
from src.pm_matching.engine.engine import MatchingEngine

_engine: MatchingEngine | None = None


def get_matching_engine() -> MatchingEngine:
    global _engine  # noqa: PLW0603
    if _engine is None:
        _engine = MatchingEngine()
    return _engine
