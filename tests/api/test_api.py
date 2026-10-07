"""API tests against the real PostGIS database (after `kedro run` for Exeter).

Skipped when the database isn't reachable, so unit tests still run anywhere.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from fibre_planning.api.app import app
from fibre_planning.api.db import get_engine

EXETER = "E07000041"
CENTRAL_EXETER = "-3.535,50.720,-3.525,50.727"


def _database_ready() -> bool:
    try:
        with get_engine().connect() as conn:
            return bool(conn.execute(text("SELECT count(*) FROM fibre.pipeline_run")).scalar())
    except (SQLAlchemyError, ValueError):
        return False


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _database_ready(), reason="PostGIS not available"),
]


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_health_and_ready(client):
    assert client.get("/health").json() == {"status": "ok"}
    ready = client.get("/ready")
    assert ready.status_code == 200
    assert ready.json()["last_run_at"] is not None


def test_area_summary(client):
    body = client.get(f"/v1/areas/{EXETER}/summary").json()
    assert body["name"] == "Exeter"
    assert 0 < body["gigabit_coverage_pct"] <= 100
    assert body["people_no_gigabit"] < body["population"]


def test_area_summary_validates_code(client):
    assert client.get("/v1/areas/not-a-code/summary").status_code == 422
    assert client.get("/v1/areas/E99999999/summary").status_code == 404


def test_road_links_are_ranked_geojson(client):
    body = client.get("/v1/road-links", params={"limit": 5}).json()
    assert body["type"] == "FeatureCollection" and body["count"] == 5
    ranks = [f["properties"]["priority_rank"] for f in body["features"]]
    assert ranks == sorted(ranks)
    lon, lat = body["features"][0]["geometry"]["coordinates"][0]
    assert -4 < lon < -3 and 50 < lat < 51  # WGS84 around Exeter


def test_premises_bbox(client):
    body = client.get("/v1/premises", params={"bbox": CENTRAL_EXETER, "limit": 50}).json()
    assert 0 < body["count"] <= 50
    assert {"population", "gigabit_pct", "road_link_id"} <= set(body["features"][0]["properties"])


@pytest.mark.parametrize("bbox", ["1,2,3", "a,b,c,d", "-3.5,50.7,-3.6,50.8", "-3.6,50.6,-3.4,50.8"])
def test_premises_bbox_rejects_bad_input(client, bbox):
    assert client.get("/v1/premises", params={"bbox": bbox}).status_code == 422


def test_postcode_normalised(client):
    any_postcode = client.get("/v1/premises", params={"bbox": CENTRAL_EXETER, "limit": 1}).json()
    postcode = any_postcode["features"][0]["properties"]["postcode"]
    squashed = postcode.replace(" ", "").lower()
    body = client.get(f"/v1/postcodes/{squashed}").json()
    assert body["postcode"] == postcode
    assert client.get("/v1/postcodes/NOTAPOSTCODE").status_code == 422


def test_reader_role_cannot_write():
    with get_engine().connect() as conn, pytest.raises(SQLAlchemyError):
        conn.execute(text("DELETE FROM fibre.premises"))


def test_metrics_and_headers(client):
    response = client.get("/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert "X-Request-ID" in response.headers
    assert "api_requests_total" in client.get("/metrics").text
