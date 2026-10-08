"""API tests against the seeded ``fibre_test`` database (see tests/conftest.py)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from tests.conftest import TEST_LAD

pytestmark = pytest.mark.integration

# The seeded area (BNG 291000-292000, 92000-93000) is -3.5457,50.7174 to -3.5312,50.7266 in WGS84
TESTVILLE_BBOX = "-3.547,50.717,-3.530,50.727"


@pytest.fixture(scope="module")
def client(seeded_database):
    from fibre_planning.api.app import app

    with TestClient(app) as c:
        yield c


def test_health_and_ready(client):
    assert client.get("/health").json() == {"status": "ok"}
    ready = client.get("/ready")
    assert ready.status_code == 200
    assert ready.json()["last_run_at"] is not None


def test_area_summary(client):
    body = client.get(f"/v1/areas/{TEST_LAD}/summary").json()
    assert body["name"] == "Testville"
    assert body["gigabit_coverage_pct"] == 50
    assert body["people_no_gigabit"] == 5


def test_area_summary_validates_code(client):
    assert client.get("/v1/areas/not-a-code/summary").status_code == 422
    assert client.get("/v1/areas/E99999999/summary").status_code == 404


def test_road_links_ranked_only(client):
    body = client.get("/v1/road-links").json()
    assert body["type"] == "FeatureCollection"
    assert [f["id"] for f in body["features"]] == ["LINK-B"]  # LINK-A has nobody without gigabit
    assert body["features"][0]["properties"]["people_per_km"] == 10
    lon, lat = body["features"][0]["geometry"]["coordinates"][0]
    assert -3.6 < lon < -3.4 and 50.6 < lat < 50.8  # returned in WGS84


def test_build_plan(client):
    body = client.get("/v1/build-plan").json()
    (feature,) = body["features"]
    assert feature["id"] == "LINK-B"
    assert feature["properties"]["build_rank"] == 1
    assert feature["properties"]["connect_m"] == 100
    assert feature["geometry"]["type"] == "MultiLineString"


def test_premises_bbox(client):
    body = client.get("/v1/premises", params={"bbox": TESTVILLE_BBOX}).json()
    assert body["count"] == 4
    assert {f["id"] for f in body["features"]} == {1, 2, 3, 4}
    limited = client.get("/v1/premises", params={"bbox": TESTVILLE_BBOX, "limit": 2}).json()
    assert limited["count"] == 2


@pytest.mark.parametrize("bbox", ["1,2,3", "a,b,c,d", "-3.5,50.7,-3.6,50.8", "-3.6,50.6,-3.4,50.8"])
def test_premises_bbox_rejects_bad_input(client, bbox):
    assert client.get("/v1/premises", params={"bbox": bbox}).status_code == 422


def test_postcode_normalised(client):
    body = client.get("/v1/postcodes/ex22bb").json()
    assert body["postcode"] == "EX2 2BB"
    assert body["gigabit_pct"] == 0
    assert client.get("/v1/postcodes/NOTAPOSTCODE").status_code == 422
    assert client.get("/v1/postcodes/ZZ9 9ZZ").status_code == 404


def test_reader_role_cannot_write(seeded_database):
    from fibre_planning.api.db import get_engine

    with get_engine().connect() as conn, pytest.raises(SQLAlchemyError):
        conn.execute(text("DELETE FROM fibre.premises"))


def test_metrics_and_headers(client):
    response = client.get("/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert "X-Request-ID" in response.headers
    assert 'route="/health"' in client.get("/metrics").text
