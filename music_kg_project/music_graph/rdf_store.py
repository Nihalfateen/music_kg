"""
music_graph/rdf_store.py

Singleton RDFStore — loads music_kg.nt once on app startup,
exposes the graph and SPARQL execution to all views.
"""
import json
import logging
import time
from pathlib import Path
from typing import Optional, Dict, Any, List

from rdflib import ConjunctiveGraph, Namespace, URIRef
from rdflib.namespace import RDF, RDFS, OWL, XSD

log = logging.getLogger(__name__)

# ── Namespaces (mirrors convert_to_rdf.py) ────────────────────────────────────
BASE = Namespace("http://musickg.org/")
MUSIC = Namespace("http://musickg.org/ontology#")
SCHEMA = Namespace("http://schema.org/")


class _RDFStore:
    """
    Internal singleton — do not instantiate directly.
    Access via: from music_graph.rdf_store import store
    """

    def __init__(self):
        self._graph: Optional[ConjunctiveGraph] = None
        self._stats: dict = {}
        self._loaded = False

    # ── Public properties ─────────────────────────────────────────────────────

    @property
    def graph(self) -> ConjunctiveGraph:
        if not self._loaded:
            raise RuntimeError(
                "RDFStore not initialised. Call store.load() first.")
        return self._graph

    @property
    def stats(self) -> dict:
        return self._stats

    @property
    def namespaces(self) -> dict:
        return {"MUSIC": MUSIC, "SCHEMA": SCHEMA, "OWL": OWL, "BASE": BASE}

    @property
    def loaded(self) -> bool:
        return self._loaded

    # ── Loader ────────────────────────────────────────────────────────────────

    def load(self, nt_path: Path, stats_path: Path) -> None:
        """
        Parse the N-Triples file into a ConjunctiveGraph.
        Called once from AppConfig.ready().
        """
        if self._loaded:
            log.warning("RDFStore.load() called twice — skipping.")
            return

        t0 = time.time()
        log.info(f"RDFStore: loading {nt_path} …")

        if not nt_path.exists():
            log.error(
                f"RDF file not found: {nt_path}. "
                "Run convert_to_rdf.py first, then copy output to data/."
            )
            # Initialise empty graph so the app still starts
            self._graph = ConjunctiveGraph()
            self._stats = {}
            self._loaded = True
            return

        g = ConjunctiveGraph()
        g.parse(str(nt_path), format="nt")

        # Bind namespaces for readable SPARQL prefixes
        g.bind("music",  MUSIC)
        g.bind("schema", SCHEMA)
        g.bind("owl",    OWL)
        g.bind("base",   BASE)

        self._graph = g
        elapsed = time.time() - t0
        log.info(f"RDFStore: loaded {len(g):,} triples in {elapsed:.2f}s")

        # Load stats.json
        if stats_path.exists():
            with open(stats_path, encoding="utf-8") as f:
                self._stats = json.load(f)
            log.info("RDFStore: stats.json loaded.")
        else:
            log.warning(f"stats.json not found at {stats_path}")
            self._stats = {"note": "stats.json not found"}

        self._loaded = True

    # ── SPARQL execution ──────────────────────────────────────────────────────

    def execute_sparql(self, query_string: str) -> List[Dict[str, Any]]:
        """
        Execute a SPARQL SELECT query and return results as a list of dicts.
        Keys are the variable names; values are Python strings/ints/floats.
        Returns empty list on error instead of crashing.
        """
        t0 = time.time()
        try:
            results = self._graph.query(query_string)
        except Exception as e:
            log.warning(f"SPARQL query failed: {e}")
            return []
        rows = []
        for row in results:
            record = {}
            for var in results.vars:
                val = row[var]
                if val is None:
                    record[str(var)] = None
                elif hasattr(val, "toPython"):
                    record[str(var)] = val.toPython()
                else:
                    record[str(var)] = str(val)
            rows.append(record)
        elapsed_ms = (time.time() - t0) * 1000
        log.debug(f"SPARQL returned {len(rows)} rows in {elapsed_ms:.1f}ms")
        return rows

    def get_stats(self) -> dict:
        stats = dict(self._stats)
        if self._loaded and self._graph:
            stats["graph_triples_live"] = len(self._graph)
        return stats


# ── Module-level singleton ────────────────────────────────────────────────────
store = _RDFStore()
