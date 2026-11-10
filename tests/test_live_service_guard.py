"""The hermetic-run guard in ``tests/conftest.py`` (#334) still trips."""

import socket
import threading
from typing import Callable, List
from urllib.parse import urlsplit

import psycopg
import psycopg_pool
import pytest

from bmlibrarian.llm.constants import DEFAULT_OLLAMA_HOST
from tests.conftest import live_tests_enabled


@pytest.fixture(autouse=True)
def _hermetic_only(request: pytest.FixtureRequest) -> None:
    """The guard is off in a live run, so there is nothing to check."""
    if live_tests_enabled(request.config):
        pytest.skip("guard is disabled when live tests run")


@pytest.mark.parametrize("connect", [
    lambda: psycopg.connect("dbname=bmlibrarian_dev"),
    lambda: psycopg.Connection.connect("dbname=bmlibrarian_dev"),
    lambda: psycopg_pool.ConnectionPool("dbname=bmlibrarian_dev", open=False),
], ids=["psycopg.connect", "Connection.connect", "ConnectionPool"])
def test_database_connection_fails_the_test(connect: Callable[[], object], live_guard_trips: List[str]) -> None:
    """Every psycopg entry point fails, naming the marker, even under ``except Exception``."""
    with pytest.raises(pytest.fail.Exception, match="requires_database"):
        try:
            connect()
        except Exception:  # what code under test typically does
            pass
    live_guard_trips.clear()


def test_ollama_connection_fails_the_test(live_guard_trips: List[str]) -> None:
    """Connecting to the local Ollama port fails, naming the marker."""
    port = urlsplit(DEFAULT_OLLAMA_HOST).port
    assert port is not None
    with pytest.raises(pytest.fail.Exception, match="requires_ollama"):
        socket.create_connection(("127.0.0.1", port), timeout=1)
    live_guard_trips.clear()


@pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
def test_trip_swallowed_elsewhere_is_recorded(live_guard_trips: List[str]) -> None:
    """A trip caught outside the test (here: a thread) is still recorded for the test."""
    thread = threading.Thread(target=lambda: psycopg.connect("dbname=bmlibrarian_dev"))
    thread.start()
    thread.join()
    assert live_guard_trips and "requires_database" in live_guard_trips[0]
    live_guard_trips.clear()
