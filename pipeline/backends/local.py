"""LocalBackend — persist the Dataset as files on disk."""

from __future__ import annotations

from pathlib import Path

from rdflib import Dataset

from pipeline.dataset import export_trig, export_union_turtle, triples_by_graph


class LocalBackend:
    name = "local"

    def persist(self, ds: Dataset, output_dir: Path) -> dict:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        export_union_turtle(ds, output_dir / "rtm.ttl")
        export_trig(ds, output_dir / "rtm.trig")
        return triples_by_graph(ds)

    def describe(self) -> str:
        return "Local filesystem (rdflib Dataset, persisted as output/rtm.ttl + output/rtm.trig)"
