import asyncio
import os
import sys

_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_SRC_DIR = os.path.join(_BACKEND_DIR, "src")
for _p in (_BACKEND_DIR, _SRC_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from services.user_feedback_service import UserFeedbackService


def test_user_feedback_service_degrades_when_vector_store_unavailable(monkeypatch) -> None:
    class FailingStore:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("pg unavailable")

    monkeypatch.setattr("services.user_feedback_service.PgVectorStore", FailingStore)

    service = UserFeedbackService()

    feedback = asyncio.run(service.retrieve_feedback("tree case"))
    high_freq = service.get_high_frequency_corrections()

    assert feedback == []
    assert high_freq == []
