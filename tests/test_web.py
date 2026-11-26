"""Website: configurator API builds REAL geometry, order flow, admin workflow, notifications, security."""

from __future__ import annotations

import base64
import re
import zipfile
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from printyz_web import notify  # noqa: E402
from printyz_web.app import create_app  # noqa: E402
from printyz_web.settings import Settings  # noqa: E402

pytestmark = pytest.mark.slow

DESIGN = {"text": "אבג", "mode": "flush", "layout": {"style": "row"}, "keycap": "standard", "texture": "smooth",
          "keychain": {"enabled": False}, "colors": {}, "extras": []}
CUSTOMER = {"name": "בדיקה", "email": "test@example.com", "phone": "050-1234567", "notes": "",
            "marketing": True, "terms": True}


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    d = tmp_path_factory.mktemp("site")
    s = Settings(data_dir=d, admin_password="secret-test-pw", secret_key="k" * 32, email_backend="memory",
                 owner_email="owner@example.com", base_url="http://testserver")
    s.__post_init__()
    app = create_app(s, workers=ThreadPoolExecutor(1))
    with TestClient(app) as c:
        c.settings = s
        yield c


def login(c):
    r = c.post("/admin/login", data={"password": "secret-test-pw"}, follow_redirects=False)
    assert r.status_code == 303
    page = c.get("/admin").text
    return re.search(r'name="csrf" value="([^"]+)"', c.get("/admin/settings").text).group(1), page


def test_public_pages(client):
    for path in ("/", "/gallery", "/clicker", "/privacy", "/terms", "/accessibility", "/static/js/clicker.js",
                 "/static/favicon.png"):
        assert client.get(path).status_code == 200, path
    assert client.get("/nope").status_code == 404


def test_config_lists_only_stock_and_prices(client):
    cfg = client.get("/api/config").json()
    assert cfg["colors"] and all(c["hex"].startswith("#") for c in cfg["colors"])
    assert cfg["pricing"]["per_key"] == 6.0
    assert cfg["fonts"] and cfg["max_keys"] <= 10


def test_preview_builds_real_meshes_and_prices(client):
    r = client.post("/api/preview", json=DESIGN).json()
    assert r["errors"] == []
    assert r["price"] == 18.0                      # 3 keys x 6
    assert len(r["keys"]) == 3
    body = [p for p in r["parts"] if p["role"] == "body"][0]
    pos = np.frombuffer(base64.b64decode(body["positions"]), np.float32).reshape(-1, 3)
    idx = np.frombuffer(base64.b64decode(body["indices"]), np.uint32)
    assert len(pos) > 100 and idx.max() < len(pos)


def test_preview_rejects_too_many_keys_and_unlisted_colour(client):
    r = client.post("/api/preview", json=DESIGN | {"text": "אבגדהוזחטיכל"}).json()
    assert r["errors"] and r["parts"] == []        # never silently truncated
    r = client.post("/api/preview", json=DESIGN | {"colors": {"body": "#123456"}}).json()
    body = [p for p in r["parts"] if p["role"] == "body"][0]
    assert body["color"].upper() != "#123456"      # forced back to a stock colour


def test_order_requires_contact_and_terms(client):
    r = client.post("/api/orders", json={"design": DESIGN, "customer": CUSTOMER | {"terms": False}})
    assert r.status_code == 400
    r = client.post("/api/orders", json={"design": DESIGN, "customer": CUSTOMER | {"email": "bad"}})
    assert r.status_code == 400


def test_full_order_flow(client):
    notify.OUTBOX.clear()
    r = client.post("/api/orders", json={"design": DESIGN, "customer": CUSTOMER})
    assert r.status_code == 200, r.text
    track = r.json()["track_url"]
    oid = r.json()["id"]
    f = client.settings.data_dir / "orders" / f"order-{oid}.printyz-order"
    with zipfile.ZipFile(f) as z:
        assert "project.printyz.json" in z.namelist()
    to = [m["to"] for m in notify.OUTBOX]
    assert "owner@example.com" in to and "test@example.com" in to
    assert any(m["attachments"] for m in notify.OUTBOX if m["to"] == "owner@example.com")
    assert "ממתינה לאישור" in client.get(track).text

    # admin is protected
    assert client.get(f"/admin/orders/{oid}", follow_redirects=False).status_code == 303
    csrf, listing = login(client)
    assert f"#{oid}" in listing
    # CSRF required
    assert client.post(f"/admin/orders/{oid}", data={"action": "approve"}).status_code == 400

    notify.OUTBOX.clear()
    client.post(f"/admin/orders/{oid}", data={"action": "approve", "csrf": csrf, "final_price": "20",
                                              "payment_link": "https://pay.example/abc"})
    page = client.get(track).text
    assert "https://pay.example/abc" in page and "₪20" in page
    assert notify.OUTBOX and "https://pay.example/abc" in notify.OUTBOX[-1]["body"]
    assert "wa.me/972501234567" in client.get(f"/admin/orders/{oid}").text

    client.post(f"/admin/orders/{oid}", data={"action": "paid", "csrf": csrf})
    client.post(f"/admin/orders/{oid}", data={"action": "production", "csrf": csrf, "ready_days": "4"})
    assert "4 ימים" in client.get(track).text
    assert client.get(f"/admin/orders/{oid}/file").status_code == 200
    assert client.get(f"/admin/orders/{oid}/preview.png").headers["content-type"] == "image/png"

    subs = client.get("/admin/subscribers.csv").text
    assert "test@example.com" in subs


def test_admin_settings_change_prices_immediately(client):
    csrf, _ = login(client)
    page = client.get("/admin/settings").text
    form = {"csrf": csrf, "price_per_key": "7", "max_keys": "10", "keychain": "on", "symbols_allowed": "on"}
    names = re.findall(r'name="color_name" value="([^"]*)"', page)
    hexes = re.findall(r'name="color_hex" value="([^"]*)"', page)
    data = form | {"color_name": names, "color_hex": hexes, "color_stock": [str(i) for i in range(len(names))]}
    assert client.post("/admin/settings", data=data, follow_redirects=False).status_code == 303
    assert client.get("/api/config").json()["pricing"]["per_key"] == 7.0
    assert client.post("/api/preview", json=DESIGN).json()["price"] == 21.0


def test_wrong_password_rejected(client):
    c2 = TestClient(client.app)
    r = c2.post("/admin/login", data={"password": "nope"})
    assert "סיסמה שגויה" in r.text
    assert c2.get("/admin", follow_redirects=False).status_code == 303
