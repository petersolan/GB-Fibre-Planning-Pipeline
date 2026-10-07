"""Publish the PostGIS tables as GeoServer layers through its REST API.

Idempotent: safe to run after every pipeline run. Creates (or updates) a
workspace, a PostGIS store that connects with the read-only role, one layer
per table and the SLD styles in ``geoserver/styles``.

Usage:  python -m fibre_planning.geoserver
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import httpx
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from fibre_planning.db.config import get_settings

log = logging.getLogger(__name__)

WORKSPACE = "fibre"
STORE = "fibre_postgis"
STYLES_DIR = Path(__file__).resolve().parents[2] / "geoserver" / "styles"
# table -> (title, style name or None for GeoServer's default)
LAYERS = {
    "road_link_priority": ("Fibre build priority by road link", "road_link_priority"),
    "premises": ("Premises with gigabit coverage", "premises_coverage"),
    "postcode_coverage": ("Postcode coverage", None),
    "area_boundary": ("Planning area boundary", "area_boundary"),
}


class GeoServerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    geoserver_url: str = "http://127.0.0.1:8080/geoserver"
    geoserver_admin_user: str = "admin"
    geoserver_admin_password: SecretStr
    # How GeoServer reaches PostGIS: the Compose service name, not localhost
    geoserver_db_host: str = "postgis"
    geoserver_db_port: int = 5432


class GeoServer:
    def __init__(self, settings: GeoServerSettings) -> None:
        self.client = httpx.Client(
            base_url=f"{settings.geoserver_url}/rest",
            auth=(settings.geoserver_admin_user, settings.geoserver_admin_password.get_secret_value()),
            timeout=60,
            transport=httpx.HTTPTransport(retries=3),
        )

    def _exists(self, path: str) -> bool:
        return self.client.get(path, headers={"Accept": "application/json"}).is_success

    def _check(self, response: httpx.Response, action: str) -> None:
        if response.is_error:
            raise RuntimeError(f"GeoServer {action} failed: {response.status_code} {response.text[:300]}")

    def ensure_workspace(self) -> None:
        if not self._exists(f"/workspaces/{WORKSPACE}"):
            self._check(self.client.post("/workspaces", json={"workspace": {"name": WORKSPACE}}), "workspace")
            log.info("Created workspace %s", WORKSPACE)

    def ensure_store(self, gs: GeoServerSettings) -> None:
        db = get_settings()
        params = {
            "dbtype": "postgis",
            "host": gs.geoserver_db_host,
            "port": str(gs.geoserver_db_port),
            "database": db.postgres_db,
            "schema": "fibre",
            "user": db.api_db_user,  # read-only role
            "passwd": db.api_db_password.get_secret_value(),
            "Expose primary keys": "true",
            "Estimated extends": "true",
        }
        body = {
            "dataStore": {
                "name": STORE,
                "connectionParameters": {"entry": [{"@key": k, "$": v} for k, v in params.items()]},
            }
        }
        path = f"/workspaces/{WORKSPACE}/datastores"
        if self._exists(f"{path}/{STORE}"):
            self._check(self.client.put(f"{path}/{STORE}", json=body), "store update")
        else:
            self._check(self.client.post(path, json=body), "store create")
            log.info("Created PostGIS store %s", STORE)

    def ensure_style(self, name: str) -> None:
        sld = (STYLES_DIR / f"{name}.sld").read_bytes()
        headers = {"Content-Type": "application/vnd.ogc.sld+xml"}
        path = f"/workspaces/{WORKSPACE}/styles"
        if self._exists(f"{path}/{name}"):
            self._check(self.client.put(f"{path}/{name}", content=sld, headers=headers), f"style {name}")
        else:
            self._check(
                self.client.post(path, content=sld, headers=headers, params={"name": name}), f"style {name}"
            )

    def ensure_layer(self, table: str, title: str, style: str | None) -> None:
        path = f"/workspaces/{WORKSPACE}/datastores/{STORE}/featuretypes"
        if not self._exists(f"{path}/{table}"):
            body = {"featureType": {"name": table, "nativeName": table, "title": title, "srs": "EPSG:27700"}}
            self._check(self.client.post(path, json=body), f"layer {table}")
            log.info("Published layer %s:%s", WORKSPACE, table)
        else:
            # Recompute bounding boxes after a new pipeline run
            self._check(
                self.client.put(
                    f"{path}/{table}",
                    params={"recalculate": "nativebbox,latlonbbox"},
                    json={"featureType": {"name": table, "title": title}},
                ),
                f"layer {table} update",
            )
        if style:
            body = {"layer": {"defaultStyle": {"name": f"{WORKSPACE}:{style}"}}}
            self._check(self.client.put(f"/layers/{WORKSPACE}:{table}", json=body), f"style for {table}")


def publish() -> list[str]:
    settings = GeoServerSettings()  # type: ignore[call-arg]
    gs = GeoServer(settings)
    gs.ensure_workspace()
    gs.ensure_store(settings)
    for table, (title, style) in LAYERS.items():
        if style:
            gs.ensure_style(style)
        gs.ensure_layer(table, title, style)
    return [f"{WORKSPACE}:{t}" for t in LAYERS]


if __name__ == "__main__":
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"), format="%(levelname)s %(message)s")
    for layer in publish():
        log.info("Layer ready: %s", layer)
