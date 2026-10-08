"""Calls to the fibre planning API, kept free of any user interface.

Requests go through QgsBlockingNetworkRequest, so they use QGIS's proxy, SSL
and authentication settings like every other QGIS network call. Parsing is in
plain functions so it can be tested without a running QGIS desktop.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from urllib.parse import quote, urlencode

from qgis.core import QgsBlockingNetworkRequest
from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtNetwork import QNetworkRequest

DEFAULT_API_URL = "http://127.0.0.1:8000"
POSTCODE = re.compile(r"^[A-Z]{1,2}\d[A-Z\d]? ?\d[A-Z]{2}$")
INWARD_CODE_LENGTH = 3  # the "4QJ" in "EX4 4QJ"
HTTP_ERROR = 400


class ApiError(Exception):
    """The API could not be reached or returned an error."""


@dataclass(frozen=True)
class RoadLink:
    road_link_id: str
    rank: int
    name: str
    people_no_gigabit: float
    people_per_km: float
    length_m: float
    coordinates: list[list[float]]  # WGS84 lon/lat

    @property
    def label(self) -> str:
        return (
            f"#{self.rank}  {self.name}: {self.people_no_gigabit:.0f} people without gigabit, "
            f"{self.length_m:.0f} m ({self.people_per_km:.0f}/km)"
        )

    @property
    def lines(self) -> list[list[list[float]]]:
        return [self.coordinates]


@dataclass(frozen=True)
class BuildStep:
    """A gap street with its route from the existing gigabit network (pgRouting)."""

    road_link_id: str
    rank: int
    name: str
    people_no_gigabit: float
    connect_m: float
    total_m: float
    est_cost_gbp: float
    cost_per_premises_gbp: float
    lines: list[list[list[float]]]  # WGS84 lon/lat: the street plus its connecting route

    @property
    def label(self) -> str:
        reach = "on the network" if self.connect_m == 0 else f"+{self.connect_m:.0f} m to reach"
        return (
            f"#{self.rank}  {self.name}: {self.people_no_gigabit:.0f} people, {reach}, "
            f"~£{self.est_cost_gbp:,.0f} (£{self.cost_per_premises_gbp:,.0f}/premises)"
        )


@dataclass(frozen=True)
class Postcode:
    postcode: str
    premises: int
    population: int
    gigabit_pct: float | None
    people_no_gigabit: float | None
    lon: float
    lat: float

    @property
    def summary(self) -> str:
        coverage = "no Ofcom data" if self.gigabit_pct is None else f"{self.gigabit_pct:.0f}% gigabit"
        missing = self.people_no_gigabit or 0
        return (
            f"{self.postcode}: {self.premises} premises, {self.population} residents, "
            f"{coverage}, about {missing:.0f} people without gigabit"
        )


def parse_road_links(collection: dict) -> list[RoadLink]:
    links = []
    for feature in collection.get("features", []):
        props = feature["properties"]
        links.append(
            RoadLink(
                road_link_id=str(feature["id"]),
                rank=int(props["priority_rank"]),
                name=props.get("road_name") or props.get("road_function") or "Unnamed road",
                people_no_gigabit=float(props["people_no_gigabit"]),
                people_per_km=float(props["people_per_km"]),
                length_m=float(props["length_m"]),
                coordinates=feature["geometry"]["coordinates"],
            )
        )
    return links


def parse_build_plan(collection: dict) -> list[BuildStep]:
    steps = []
    for feature in collection.get("features", []):
        props = feature["properties"]
        geometry = feature["geometry"]
        lines = (
            geometry["coordinates"] if geometry["type"] == "MultiLineString" else [geometry["coordinates"]]
        )
        steps.append(
            BuildStep(
                road_link_id=str(feature["id"]),
                rank=int(props["build_rank"]),
                name=props.get("road_name") or "Unnamed road",
                people_no_gigabit=float(props["people_no_gigabit"]),
                connect_m=float(props["connect_m"]),
                total_m=float(props["total_m"]),
                est_cost_gbp=float(props["est_cost_gbp"]),
                cost_per_premises_gbp=float(props["cost_per_premises_gbp"]),
                lines=lines,
            )
        )
    return steps


def normalise_postcode(text: str) -> str:
    """'ex44qj' -> 'EX4 4QJ'; raises ValueError if it can't be a UK postcode."""
    compact = re.sub(r"\s+", "", text.upper())
    n = INWARD_CODE_LENGTH
    candidate = f"{compact[:-n]} {compact[-n:]}" if len(compact) > n else compact
    if not POSTCODE.match(candidate):
        raise ValueError(f"Not a UK postcode: {text!r}")
    return candidate


class FibreApi:
    def __init__(self, base_url: str = DEFAULT_API_URL) -> None:
        self.base_url = base_url.rstrip("/")

    def url(self, path: str, **params: object) -> str:
        query = f"?{urlencode(params)}" if params else ""
        return f"{self.base_url}{path}{query}"

    def _get(self, path: str, **params: object) -> dict:
        request = QgsBlockingNetworkRequest()
        error = request.get(QNetworkRequest(QUrl(self.url(path, **params))), forceRefresh=True)
        reply = request.reply()
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        body = bytes(reply.content()).decode("utf-8") if reply.content() else ""
        if error != QgsBlockingNetworkRequest.ErrorCode.NoError and not status:
            raise ApiError(f"Could not reach the API at {self.base_url}: {request.errorMessage()}")
        if status and int(status) >= HTTP_ERROR:
            detail = json.loads(body).get("detail", body) if body.startswith("{") else body
            raise ApiError(f"API error {status}: {detail}")
        return json.loads(body)

    def health(self) -> bool:
        return self._get("/health").get("status") == "ok"

    def top_road_links(self, limit: int = 20) -> list[RoadLink]:
        return parse_road_links(self._get("/v1/road-links", limit=limit))

    def build_plan(self, limit: int = 20) -> list[BuildStep]:
        return parse_build_plan(self._get("/v1/build-plan", limit=limit))

    def postcode(self, text: str) -> Postcode:
        normalised = normalise_postcode(text)
        return Postcode(**self._get(f"/v1/postcodes/{quote(normalised)}"))
