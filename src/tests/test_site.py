from fastapi.testclient import TestClient

from src.app.main import create_app
from src.tests.test_api import FakeMessenger, FakeQA


def _client(tmp_path):
    app = create_app(
        qa=FakeQA(),
        telegram_messenger=FakeMessenger(),
        whatsapp_messenger=FakeMessenger(),
        db_path=str(tmp_path / "site.db"),
    )
    return TestClient(app)


def test_site_pages_render(tmp_path):
    with _client(tmp_path) as client:
        for path, marker in [
            ("/", "Ask your sermons anything"),
            ("/", "Drop in PDFs or Word documents"),
            ("/get-started", "From clone to first answer"),
            ("/get-started", "No special format needed"),
            ("/get-started", "Keep the watcher running"),
            ("/self-host", "One container on any VPS"),
            ("/self-host", "watcher embeds them"),
            ("/changelog", "Rendered live from"),
        ]:
            resp = client.get(path)
            assert resp.status_code == 200, path
            assert marker in resp.text, path
            assert "Skip to content" in resp.text


def test_site_has_no_pricing_or_providers(tmp_path):
    with _client(tmp_path) as client:
        body = "".join(client.get(p).text for p in ["/", "/get-started", "/self-host", "/changelog"])
    for banned in ["$15", "$30", "Hetzner", "DigitalOcean", "Railway", "Fly.io", "Space Computer"]:
        assert banned not in body


def test_static_assets_served(tmp_path):
    with _client(tmp_path) as client:
        css = client.get("/static/site.css")
        js = client.get("/static/site.js")
    assert css.status_code == 200
    assert ":root" in css.text
    assert js.status_code == 200
    assert "clipboard" in js.text
