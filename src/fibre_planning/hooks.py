"""Kedro hooks: per-node timings and row counts, logged as JSON and kept per run.

Every node logs one structured line (duration, rows per output, process
memory). When the run included ``record_run``, the timings are also merged
into that run's ``fibre.pipeline_run.summary``, so slow-downs show up in the
run history, not just in a terminal.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

import psutil
from kedro.framework.hooks import hook_impl
from kedro.pipeline.node import Node
from sqlalchemy import create_engine, text

from fibre_planning.db.config import get_settings

log = logging.getLogger("fibre_planning.monitoring")


def _rows(value: Any) -> int | None:
    try:
        return len(value)
    except TypeError:
        return None


class PipelineMonitoringHooks:
    def __init__(self) -> None:
        self._started: dict[str, float] = {}
        self._timings: dict[str, float] = {}
        self._run_started = 0.0
        self._process = psutil.Process(os.getpid())

    @hook_impl
    def before_pipeline_run(self, run_params: dict[str, Any]) -> None:
        self._run_started = time.perf_counter()
        self._timings.clear()

    @hook_impl
    def before_node_run(self, node: Node) -> None:
        self._started[node.name] = time.perf_counter()

    @hook_impl
    def after_node_run(self, node: Node, outputs: dict[str, Any]) -> None:
        seconds = time.perf_counter() - self._started.pop(node.name, time.perf_counter())
        self._timings[node.name] = round(seconds, 3)
        event = {
            "event": "node_completed",
            "node": node.name,
            "seconds": round(seconds, 3),
            "rows": {name: _rows(value) for name, value in outputs.items()},
            "rss_mb": round(self._process.memory_info().rss / 2**20),
        }
        log.info(json.dumps(event))

    @hook_impl
    def on_node_error(self, error: Exception, node: Node) -> None:
        log.error(json.dumps({"event": "node_failed", "node": node.name, "error": type(error).__name__}))

    @hook_impl
    def after_pipeline_run(self, run_params: dict[str, Any]) -> None:
        total = round(time.perf_counter() - self._run_started, 3)
        log.info(json.dumps({"event": "pipeline_completed", "seconds": total, "nodes": len(self._timings)}))
        if "record_run" not in self._timings:
            return
        extra = json.dumps({"node_seconds": self._timings, "total_seconds": total})
        engine = create_engine(get_settings().owner_url)
        with engine.begin() as conn:
            conn.execute(
                text("""
                    UPDATE fibre.pipeline_run SET summary = summary || CAST(:extra AS jsonb)
                    WHERE id = (SELECT max(id) FROM fibre.pipeline_run)
                """),
                {"extra": extra},
            )
        engine.dispose()
