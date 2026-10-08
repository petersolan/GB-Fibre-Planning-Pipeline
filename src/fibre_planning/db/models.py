"""SQLAlchemy models for the ``fibre`` schema.

The schema itself is created and changed only by Alembic migrations
(``migrations/``); the pipeline loads data into these tables and the API
reads them. All geometries are British National Grid (EPSG:27700).
"""

from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import BigInteger, Boolean, DateTime, Float, Integer, MetaData, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

SCHEMA = "fibre"
SRID = 27700


class Base(DeclarativeBase):
    metadata = MetaData(schema=SCHEMA)


class AreaBoundary(Base):
    """The local authority the pipeline was run for."""

    __tablename__ = "area_boundary"

    lad_code: Mapped[str] = mapped_column(String(9), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    geom = mapped_column(Geometry("MULTIPOLYGON", srid=SRID, spatial_index=False), nullable=False)


class Premises(Base):
    """One address (UPRN) with modelled population and broadband coverage."""

    __tablename__ = "premises"

    uprn: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    postcode: Mapped[str | None] = mapped_column(String(8), index=True)
    population: Mapped[int] = mapped_column(Integer)
    gigabit_pct: Mapped[float | None] = mapped_column(Float)
    # Chance this address has no gigabit service: 1 - postcode gigabit share
    p_no_gigabit: Mapped[float | None] = mapped_column(Float)
    people_no_gigabit: Mapped[float | None] = mapped_column(Float)
    road_link_id: Mapped[str | None] = mapped_column(String(38), index=True)
    drop_m: Mapped[float | None] = mapped_column(Float)
    geom = mapped_column(Geometry("POINT", srid=SRID, spatial_index=False), nullable=False)


class PostcodeCoverage(Base):
    """Ofcom coverage per postcode, with premises and people from the census."""

    __tablename__ = "postcode_coverage"

    postcode: Mapped[str] = mapped_column(String(8), primary_key=True)
    premises: Mapped[int] = mapped_column(Integer)
    population: Mapped[int] = mapped_column(Integer)
    gigabit_pct: Mapped[float | None] = mapped_column(Float)
    people_no_gigabit: Mapped[float | None] = mapped_column(Float)
    geom = mapped_column(Geometry("POINT", srid=SRID, spatial_index=False), nullable=False)


class RoadLinkPriority(Base):
    """OS Open Roads link with the premises it serves and a build priority."""

    __tablename__ = "road_link_priority"

    road_link_id: Mapped[str] = mapped_column(String(38), primary_key=True)
    road_function: Mapped[str | None] = mapped_column(String(40))
    road_name: Mapped[str | None] = mapped_column(String(100))
    length_m: Mapped[float] = mapped_column(Float)
    premises: Mapped[int] = mapped_column(Integer)
    premises_no_gigabit: Mapped[float] = mapped_column(Float)
    people_no_gigabit: Mapped[float] = mapped_column(Float)
    people_per_km: Mapped[float] = mapped_column(Float)
    priority_rank: Mapped[int | None] = mapped_column(Integer, index=True)
    geom = mapped_column(Geometry("LINESTRING", srid=SRID, spatial_index=False), nullable=False)


class PipelineRun(Base):
    """Audit record written at the end of every pipeline run."""

    __tablename__ = "pipeline_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    lad_code: Mapped[str] = mapped_column(String(9))
    summary = mapped_column(JSONB)


class RoadNetwork(Base):
    """Routable graph for pgRouting: one edge per road link, junctions as integer vertices."""

    __tablename__ = "road_network"

    edge_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    road_link_id: Mapped[str] = mapped_column(String(38), unique=True)
    road_function: Mapped[str | None] = mapped_column(String(40))
    source: Mapped[int] = mapped_column(Integer, index=True)
    target: Mapped[int] = mapped_column(Integer, index=True)
    length_m: Mapped[float] = mapped_column(Float)
    cost: Mapped[float] = mapped_column(Float)  # length weighted by road type
    has_gigabit: Mapped[bool] = mapped_column(Boolean)  # existing network: start of new cable
    is_gap: Mapped[bool] = mapped_column(Boolean)  # serves people without gigabit
    people_no_gigabit: Mapped[float] = mapped_column(Float)
    geom = mapped_column(Geometry("LINESTRING", srid=SRID, spatial_index=False), nullable=False)


class GapConnection(Base):
    """A gap street with its connecting route from the existing gigabit network."""

    __tablename__ = "gap_connection"

    road_link_id: Mapped[str] = mapped_column(String(38), primary_key=True)
    road_name: Mapped[str | None] = mapped_column(String(100))
    people_no_gigabit: Mapped[float] = mapped_column(Float)
    street_m: Mapped[float] = mapped_column(Float)
    connect_m: Mapped[float] = mapped_column(Float)
    total_m: Mapped[float] = mapped_column(Float)
    people_per_km_total: Mapped[float] = mapped_column(Float)
    build_rank: Mapped[int] = mapped_column(Integer, unique=True)
    geom = mapped_column(Geometry("MULTILINESTRING", srid=SRID, spatial_index=False), nullable=False)


class BuildRoute(Base):
    """A road link in the proposed cable network ('connection' route or 'gap' street)."""

    __tablename__ = "build_route"

    road_link_id: Mapped[str] = mapped_column(String(38), primary_key=True)
    role: Mapped[str] = mapped_column(String(10))
    length_m: Mapped[float] = mapped_column(Float)
    gap_links_served: Mapped[int] = mapped_column(Integer)
    people_served: Mapped[float] = mapped_column(Float)
    geom = mapped_column(Geometry("LINESTRING", srid=SRID, spatial_index=False), nullable=False)
