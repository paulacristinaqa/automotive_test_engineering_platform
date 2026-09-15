from fastapi import FastAPI
from fastapi.testclient import TestClient

from atep.core.config import Settings, get_settings
from atep.dashboard.ui import FILES, router


def client(enabled: bool) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_settings] = lambda: Settings(dashboard_ui_enabled=enabled)
    return TestClient(app)


def test_dashboard_shell_is_disabled_by_default() -> None:
    assert not Settings().dashboard_ui_enabled
    for name in ["", *FILES]:
        assert client(False).get(f"/dashboard/{name}").status_code == 404


def test_dashboard_assets_are_allowlisted_and_hardened() -> None:
    browser = client(True)
    for name in ["", *FILES]:
        response = browser.get(f"/dashboard/{name}")
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["referrer-policy"] == "no-referrer"
        assert "form-action 'none'" in response.headers["content-security-policy"]
        assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    for path in [".env", "package.json", "../config.py", "%2e%2e%2fconfig.py"]:
        assert browser.get(f"/dashboard/{path}").status_code == 404


def test_dashboard_markup_has_accessible_labels_and_no_inline_code() -> None:
    page = client(True).get("/dashboard/").text
    for identifier in ["email", "password", "view"]:
        assert f'for="{identifier}"' in page
    assert 'type="password"' in page
    assert 'role="status"' in page
    assert '<script type="module" src=' in page
    assert "onclick=" not in page
    assert 'method="post"' in page
    assert 'href="#main-content"' in page
    assert 'id="main-content" tabindex="-1"' in page
    assert page.count('aria-atomic="true"') == 2
    assert 'aria-describedby="credential-note"' in page
    assert 'id="credential-note"' in page
