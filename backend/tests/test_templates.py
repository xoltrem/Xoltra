"""
test_templates.py, the template marketplace, tested through real HTTP
requests against real JWTs (self-signed, no external credentials needed)
rather than calling route functions directly. This exercises the actual
@require_auth decorator chain, not a bypassed version of it.
"""

import json
import pytest

from templates import templates_bp


@pytest.fixture
def client(flask_app):
    flask_app.register_blueprint(templates_bp)
    return flask_app.test_client()


def _post(client, headers, path, body):
    return client.post(path, headers=headers, data=json.dumps(body), content_type="application/json")


def test_save_and_list_own_template(db, client, auth_headers):
    _, headers = auth_headers("alice@example.com")

    resp = _post(client, headers, "/api/templates", {
        "name": "Lead Router", "graph": {"nodes": [], "edges": []}, "category": "sales"
    })
    assert resp.status_code == 201

    resp = client.get("/api/templates", headers=headers)
    data = resp.get_json()
    assert data["success"] is True
    assert len(data["templates"]) == 1
    assert data["templates"][0]["is_public"] is False


def test_private_template_not_visible_to_others(db, client, auth_headers):
    _, alice_headers = auth_headers("alice@example.com")
    _, bob_headers = auth_headers("bob@example.com")

    _post(client, alice_headers, "/api/templates", {
        "name": "Private Flow", "graph": {"nodes": [], "edges": []}, "category": "sales"
    })

    resp = client.get("/api/templates/public?category=sales", headers=bob_headers)
    assert resp.get_json()["templates"] == []


def test_publish_makes_it_visible_and_hides_owner(db, client, auth_headers):
    _, alice_headers = auth_headers("alice@example.com")
    _, bob_headers = auth_headers("bob@example.com")

    create = _post(client, alice_headers, "/api/templates", {
        "name": "Lead Router", "graph": {"nodes": [], "edges": []}, "category": "sales"
    })
    template_id = create.get_json()["template_id"]

    client.patch(f"/api/templates/{template_id}/publish", headers=alice_headers,
                 data=json.dumps({"is_public": True}), content_type="application/json")

    resp = client.get("/api/templates/public?category=sales", headers=bob_headers)
    public = resp.get_json()["templates"]
    assert len(public) == 1
    assert public[0]["name"] == "Lead Router"
    assert "user_id" not in public[0]  # privacy: never leak who owns a public template


def test_use_public_template_creates_workflow_and_increments_count(db, client, auth_headers):
    _, alice_headers = auth_headers("alice@example.com")
    bob_id, bob_headers = auth_headers("bob@example.com")

    create = _post(client, alice_headers, "/api/templates", {
        "name": "Lead Router", "graph": {"nodes": [], "edges": []}, "category": "sales"
    })
    template_id = create.get_json()["template_id"]
    client.patch(f"/api/templates/{template_id}/publish", headers=alice_headers,
                 data=json.dumps({"is_public": True}), content_type="application/json")

    resp = _post(client, bob_headers, f"/api/templates/{template_id}/use", {})
    assert resp.status_code == 201
    assert resp.get_json()["workflow"]["name"] == "Lead Router"

    public = client.get("/api/templates/public?category=sales", headers=bob_headers).get_json()["templates"]
    assert public[0]["use_count"] == 1


def test_cannot_use_a_private_template_you_dont_own(db, client, auth_headers):
    _, alice_headers = auth_headers("alice@example.com")
    _, bob_headers = auth_headers("bob@example.com")

    create = _post(client, alice_headers, "/api/templates", {
        "name": "Private Flow", "graph": {"nodes": [], "edges": []}
    })
    template_id = create.get_json()["template_id"]

    resp = _post(client, bob_headers, f"/api/templates/{template_id}/use", {})
    assert resp.status_code == 404


def test_missing_auth_header_is_rejected(db, client):
    resp = client.get("/api/templates")
    assert resp.status_code == 401
