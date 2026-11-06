"""Tests for virtual clock and fault injection capabilities."""

import pytest
from fastapi.testclient import TestClient
from mocks.main import app
from mocks.services.scenarios import reset_database

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    reset_database()


def test_clock_advance_and_set():
    """Test getting, advancing, and explicitly setting virtual clock."""
    # 1. Get clock
    res = client.get("/admin/clock")
    assert res.status_code == 200
    initial_time = res.json()["current_time"]

    # 2. Advance by 5 days and 2 hours
    adv_res = client.post("/admin/clock/advance", json={"days": 5, "hours": 2, "minutes": 0})
    assert adv_res.status_code == 200
    new_time = adv_res.json()["current_time"]
    assert new_time > initial_time

    # 3. Explicitly set clock
    set_res = client.post("/admin/clock/set", json={"at": "2026-11-15T14:30:00+05:30"})
    assert set_res.status_code == 200
    assert set_res.json()["current_time"] == "2026-11-15T14:30:00+05:30"


def test_faults_configuration():
    """Test updating and reading fault injection flags."""
    res = client.post("/admin/faults", json={
        "drop_response_after_commit": True,
        "delay_ms": 100,
        "error_rate": 0.0,
        "duplicate_webhooks": True,
        "webhook_down": False
    })
    assert res.status_code == 200
    data = res.json()
    assert data["drop_response_after_commit"] is True
    assert data["delay_ms"] == 100
    assert data["duplicate_webhooks"] is True

    get_res = client.get("/admin/faults")
    assert get_res.status_code == 200
    assert get_res.json()["drop_response_after_commit"] is True
