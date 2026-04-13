"""
music_graph/rdf_store.py

Dual-mode RDF store:
  - GraphDB mode  (default): queries go to GraphDB via HTTP SPARQL endpoint
  - rdflib  mode  (fallback): in-memory ConjunctiveGraph when GraphDB is down
"""
import json
import logging
import time
import requests
from pathlib import Path
from typing import Optional, Dict, Any, List

from rdflib import Namespace
from rdflib.namespace import RDF, RDFS, OWL, XSD

# Namespaces (kept at module level for backward compatibility)
BASE = Namespace("http://musickg.org/")
MUSIC = Namespace("http://musickg.org/ontology#")
SCHEMA = Namespace("http://schema.org/")

log = logging.getLogger(__name__)

# GraphDB defaults
GRAPHDB_URL = "http://localhost:7200"
GRAPHDB_REPOSITORY = "music-kg"

GRAPHDB_USER = "admin"
GRAPHDB_PASS = "root"

class _RDFStore:
    """
    Singleton RDF store.
    Automatically detects whether GraphDB is running.
    Falls back to rdflib in-memory if GraphDB is unavailable.
    """

    def __init__(self):
        self._stats:        dict = {}
        self._loaded:       bool = False
        self._use_graphdb:  bool = False
        self._sparql_url:   str = ""
        self._update_url:   str = ""
        # rdflib fallback
        self._graph = None

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def loaded(self) -> bool:
        return self._loaded

    @property
    def using_graphdb(self) -> bool:
        return self._use_graphdb

    def load(self, nt_path: Path, stats_path: Path) -> None:
        """
        Called once from AppConfig.ready().
        Tries GraphDB first; falls back to rdflib.
        """
        if self._loaded:
            log.warning("RDFStore.load() called twice — skipping.")
            return

        if stats_path.exists():
            with open(stats_path, encoding="utf-8") as f:
                self._stats = json.load(f)
            log.info("RDFStore: stats.json loaded.")
        else:
            self._stats = {}

        # Try GraphDB
        if self._try_graphdb(nt_path):
            self._loaded = True
            return

        # Fallback: rdflib in-memory
        log.warning("GraphDB unavailable — falling back to rdflib in-memory.")
        self._load_rdflib(nt_path)
        self._loaded = True

    # ── GraphDB ───────────────────────────────────────────────────────────────

    def _try_graphdb(self, nt_path: Path) -> bool:
        """
        Check if GraphDB is running and the repository exists.
        If the repo is empty, upload the NT file automatically.
        Returns True if GraphDB is ready to use.
        """
        repo_url = f"{GRAPHDB_URL}/repositories/{GRAPHDB_REPOSITORY}"
        self._sparql_url = repo_url
        self._update_url = f"{repo_url}/statements"

        try:
            # Ping GraphDB
            r = requests.get(
                f"{GRAPHDB_URL}/rest/repositories",
                timeout=3,
                headers={"Accept": "application/json"},
            )
            if r.status_code != 200:
                return False

            repos = [rep.get("id") for rep in r.json()]
            if GRAPHDB_REPOSITORY not in repos:
                log.info(
                    f"GraphDB repository '{GRAPHDB_REPOSITORY}' not found — creating it.")
                if not self._create_repository():
                    return False

            # Check triple count
            count = self._graphdb_triple_count()

            if count < 500 and nt_path.exists():
                log.info(f"GraphDB only has {count} triples (Ontology only). Starting full data upload...")

                if self._upload_nt(nt_path):
                    count = self._graphdb_triple_count()
                    log.info(f"Auto-upload successful. Now have {count:,} triples.")
                else:
                    log.error("Auto-upload failed.")
                    return False

            self._use_graphdb = True
            return True

        except requests.exceptions.ConnectionError:
            log.info("GraphDB not reachable at %s", GRAPHDB_URL)
            return False
        except Exception as e:
            log.warning(f"GraphDB check failed: {e}")
            return False

    def _create_repository(self) -> bool:
        """Create the music-kg repository in GraphDB."""
        try:
            config = (
                "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#>.\n"
                "@prefix rep: <http://www.openrdf.org/config/repository#>.\n"
                "@prefix sr: <http://www.openrdf.org/config/repository/sail#>.\n"
                "@prefix sail: <http://www.openrdf.org/config/sail#>.\n"
                "@prefix owlim: <http://www.ontotext.com/trree/owlim#>.\n"
                "[] a rep:Repository ;\n"
                f"   rep:repositoryID \"{GRAPHDB_REPOSITORY}\" ;\n"
                f"   rdfs:label \"Music Knowledge Graph\" ;\n"
                "   rep:repositoryImpl [\n"
                "     rep:repositoryType \"graphdb:SailRepository\" ;\n"
                "     sr:sailImpl [\n"
                "       sail:sailType \"graphdb:Sail\" ;\n"
                "       owlim:base-URL \"http://musickg.org/\" ;\n"
                "       owlim:defaultNS \"\" ;\n"
                "       owlim:entity-index-size \"10000000\" ;\n"
                "       owlim:ruleset \"empty\" ;\n"
                "       owlim:storage-folder \"storage\" ;\n"
                "       owlim:enable-context-index \"true\" ;\n"
                "       owlim:enablePredicateList \"true\" ;\n"
                "       owlim:cache-memory \"512m\" ;\n"
                "       owlim:tuple-index-memory \"512m\" ;\n"
                "     ]\n"
                "   ].\n"
            )
            r = requests.post(
                f"{GRAPHDB_URL}/rest/repositories",
                data=config,
                headers={"Content-Type": "text/turtle"},
                auth=(GRAPHDB_USER, GRAPHDB_PASS),
                timeout=15,
            )
            return r.status_code in (200, 201)
        except Exception as e:
            log.warning(f"Failed to create repository: {e}")
            return False

    def _upload_nt(self, nt_path: Path) -> bool:
        """Upload the NT file to GraphDB via SPARQL Update / RDF4J REST."""
        try:
            t0 = time.time()
            with open(nt_path, "rb") as f:
                r = requests.post(
                    self._update_url,
                    data=f,
                    headers={"Content-Type": "text/plain"},  # N-Triples
                    auth=(GRAPHDB_USER, GRAPHDB_PASS),
                    timeout=300,
                )
            if r.status_code in (200, 204):
                log.info(f"Uploaded {nt_path.name} in {time.time()-t0:.1f}s")
                return True
            log.warning(f"NT upload returned {r.status_code}: {r.text[:200]}")
            return False
        except Exception as e:
            log.warning(f"NT upload failed: {e}")
            return False

    def _graphdb_triple_count(self) -> int:
        try:
            q = "SELECT (COUNT(*) AS ?c) WHERE { ?s ?p ?o }"
            rows = self._sparql_via_http(q)
            if rows:
                val = rows[0].get("c", 0)
                return int(val) if val else 0
        except Exception:
            pass
        return 0

    def _sparql_via_http(self, query_string: str) -> List[Dict[str, Any]]:
        """Send a SPARQL SELECT to GraphDB and parse the JSON response."""
        try:
            r = requests.post(
                self._sparql_url,
                data={"query": query_string},
                headers={"Accept": "application/sparql-results+json"},
                timeout=30,
            )
            if r.status_code != 200:
                log.warning(
                    f"GraphDB SPARQL returned {r.status_code}: {r.text[:200]}")
                return []

            data = r.json()
            vars_ = data["results"]["bindings"] and data["head"]["vars"]
            rows = []
            for binding in data["results"]["bindings"]:
                record = {}
                for var in data["head"]["vars"]:
                    node = binding.get(var)
                    if node is None:
                        record[var] = None
                    else:
                        raw = node["value"]
                        typ = node.get("datatype", "")

                        if "integer" in typ or "int" in typ:
                            try:
                                raw = int(raw)
                            except:
                                pass
                        elif "decimal" in typ or "float" in typ or "double" in typ:
                            try:
                                raw = float(raw)
                            except:
                                pass
                        record[var] = raw
                rows.append(record)
            return rows
        except Exception as e:
            log.warning(f"GraphDB HTTP SPARQL error: {e}")
            return []

    # ── rdflib fallback ───────────────────────────────────────────────────────

    def _load_rdflib(self, nt_path: Path) -> None:
        from rdflib import ConjunctiveGraph, Namespace
        from rdflib.namespace import OWL

        BASE = Namespace("http://musickg.org/")
        MUSIC = Namespace("http://musickg.org/ontology#")
        SCHEMA = Namespace("http://schema.org/")

        if not nt_path.exists():
            log.error(f"NT file not found: {nt_path}")
            self._graph = ConjunctiveGraph()
            return

        t0 = time.time()
        log.info(f"rdflib: loading {nt_path} …")
        g = ConjunctiveGraph()
        g.parse(str(nt_path), format="nt")
        g.bind("music",  MUSIC)
        g.bind("schema", SCHEMA)
        g.bind("base",   BASE)
        self._graph = g
        log.info(f"rdflib: loaded {len(g):,} triples in {time.time()-t0:.2f}s")

    # ── execute_sparql (SELECT) ───────────────────────────────────────────────

    def execute_sparql(self, query_string: str) -> List[Dict[str, Any]]:
        """
        Execute a SPARQL SELECT query.
        Routes to GraphDB (HTTP) or rdflib depending on what's available.
        Always returns a list of dicts — never raises.
        """
        t0 = time.time()
        try:
            if self._use_graphdb:
                rows = self._sparql_via_http(query_string)
            else:
                rows = self._sparql_via_rdflib(query_string)
        except Exception as e:
            log.warning(f"SPARQL execute error: {e}")
            rows = []
        elapsed_ms = (time.time() - t0) * 1000
        log.debug(f"SPARQL ({('GraphDB' if self._use_graphdb else 'rdflib')}) "
                  f"→ {len(rows)} rows in {elapsed_ms:.1f}ms")
        return rows

    # ── execute_sparql_update (INSERT / DELETE / UPDATE) ─────────────────────

    def execute_sparql_update(self, update_string: str) -> bool:
        """
        Execute a SPARQL UPDATE operation (INSERT DATA, DELETE DATA,
        DELETE/INSERT WHERE, CLEAR, DROP, …).

        Returns True on success, False on failure.

        GraphDB mode  → POST to /repositories/{repo}/statements
        rdflib mode   → graph.update()

        Example:
            store.execute_sparql_update('''
                PREFIX music: <http://musickg.org/ontology#>
                INSERT DATA {
                    <http://musickg.org/artist/New_Artist>
                        a music:Artist ;
                        music:artistName "New Artist" .
                }
            ''')
        """
        t0 = time.time()
        try:
            if self._use_graphdb:
                ok = self._update_via_http(update_string)
            else:
                ok = self._update_via_rdflib(update_string)
        except Exception as e:
            log.warning(f"SPARQL UPDATE error: {e}")
            return False
        elapsed_ms = (time.time() - t0) * 1000
        log.info(f"SPARQL UPDATE ({('GraphDB' if self._use_graphdb else 'rdflib')}) "
                 f"→ {'OK' if ok else 'FAILED'} in {elapsed_ms:.1f}ms")
        return ok

    def _update_via_http(self, update_string: str) -> bool:
        """Send SPARQL UPDATE to GraphDB /statements endpoint."""
        try:
            r = requests.post(
                self._update_url,
                data={"update": update_string},
                auth=(GRAPHDB_USER, GRAPHDB_PASS),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=30,
            )
            if r.status_code in (200, 204):
                return True
            log.warning(f"GraphDB UPDATE returned {r.status_code}: {r.text[:200]}")
            return False
        except Exception as e:
            log.warning(f"GraphDB UPDATE HTTP error: {e}")
            return False

    def _update_via_rdflib(self, update_string: str) -> bool:
        """Execute SPARQL UPDATE against in-memory rdflib graph."""
        if not self._graph:
            return False
        try:
            self._graph.update(update_string)
            return True
        except Exception as e:
            log.warning(f"rdflib UPDATE failed: {e}")
            return False

    def _sparql_via_rdflib(self, query_string: str) -> List[Dict[str, Any]]:
        if not self._graph:
            return []
        try:
            results = self._graph.query(query_string)
        except Exception as e:
            log.warning(f"rdflib SPARQL failed: {e}")
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
                    record[str(var)] = str(val)
            rows.append(record)
        return rows

    # ── stats ─────────────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        stats = dict(self._stats)
        stats["backend"] = "GraphDB" if self._use_graphdb else "rdflib"
        if self._use_graphdb:
            stats["graphdb_url"] = GRAPHDB_URL
            stats["repository"] = GRAPHDB_REPOSITORY
        elif self._graph:
            stats["graph_triples_live"] = len(self._graph)
        return stats

# ── Module-level singleton ────────────────────────────────────────────────────
store = _RDFStore()
