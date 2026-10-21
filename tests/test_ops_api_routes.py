from fastapi.testclient import TestClient
from app.main import app


def test_ops_edi_exceptions_endpoint_exists_and_returns_seeded_transactions():
    with TestClient(app) as client:
        response = client.get("/ops/edi/exceptions")
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 30
    assert payload["transactions"]


def test_ops_supply_reconcile_endpoint_exists_and_returns_seeded_plans():
    with TestClient(app) as client:
        response = client.get("/ops/supply/reconcile")
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] > 0
    assert payload["items"]
