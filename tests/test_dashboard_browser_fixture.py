import asyncio

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from tools.dashboard_browser_fixture import CASE_NAMES, BrowserResult, create_fixture


def test_fixture_records_only_valid_results_from_its_own_origin() -> None:
    done = asyncio.Event()
    app = create_fixture(done)
    client = TestClient(app, base_url="http://localhost:8080")
    payload = {"user_agent": "test-browser", **dict.fromkeys(CASE_NAMES, "pass")}
    assert client.post("/result", json=payload).status_code == 403
    assert not done.is_set()
    response = client.post("/result", headers={"Origin": "http://localhost:8080"}, json=payload)
    assert response.status_code == 200
    assert done.is_set()
    assert app.state.result.model_dump() == payload


def test_fixture_requires_origin_and_never_accepts_extra_evidence_fields() -> None:
    client = TestClient(create_fixture(asyncio.Event()))
    assert client.post("/fixture-token").status_code == 403
    assert client.get("/").headers["cache-control"] == "no-store"
    with pytest.raises(ValidationError):
        BrowserResult.model_validate(
            {
                "user_agent": "test",
                "access_token": "must-not-be-retained",
                **dict.fromkeys(CASE_NAMES, "pass"),
            }
        )
