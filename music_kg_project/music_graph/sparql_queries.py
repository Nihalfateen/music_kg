"""
music_graph/sparql_queries.py

All SPARQL-backed query functions.
Each function builds a query string, runs it through the RDFStore singleton,
and returns clean Python dicts ready for serialisation.
"""
import re
import time
import logging
from typing import Optional, List, Dict, Any
from urllib.parse import quote, unquote

from rdflib import URIRef
from rdflib.namespace import RDF

from music_graph.rdf_store import store, BASE, MUSIC

log = logging.getLogger(__name__)

# ── Shared SPARQL prefix block ────────────────────────────────────────────────
_PREFIXES = """
PREFIX rdf:   <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs:  <http://www.w3.org/2000/01/rdf-schema#>
PREFIX owl:   <http://www.w3.org/2002/07/owl#>
PREFIX xsd:   <http://www.w3.org/2001/XMLSchema#>
PREFIX music: <http://musickg.org/ontology#>
PREFIX base:  <http://musickg.org/>
PREFIX schema:<http://schema.org/>
"""


def _slug(uri: str) -> str:
    """Extract last path segment of a URI as a URL-safe slug."""
    return uri.rstrip("/").split("/")[-1]


def _artist_uri_from_slug(slug: str) -> str:
    return f"<http://musickg.org/artist/{slug}>"


def _album_uri_from_slug(slug: str) -> str:
    return f"<http://musickg.org/album/{slug}>"


# ─────────────────────────────────────────────────────────────────────────────
# 1. get_artists
# ─────────────────────────────────────────────────────────────────────────────

def get_artists(search=None, genre=None, limit=20, offset=0) -> List[Dict]:
    """
    Fast artist list using the in-memory search index.
    No SPARQL — reads from pre-built CSV index.
    """
    index = _get_search_index()

    # Filter to artists only
    results = []
    for item in index:
        if item["type"] != "artist":
            continue

        # Genre filter
        if genre:
            item_genres = item.get("extra_info", {}).get("genres", [])
            genre_lower = genre.strip().lower()
            if genre_lower not in [g.lower() for g in item_genres]:
                continue

        # Search filter
        if search:
            if search.strip().lower() not in item["name_lower"]:
                continue

        results.append({
            "uri":         item["uri"],
            "name":        item["name"],
            "slug":        item["slug"],
            "genres":      item.get("extra_info", {}).get("genres", []),
            "dbpedia_uri": None,
        })

    # Sort and paginate
    results.sort(key=lambda x: x["name"])
    return results[offset: offset + limit]


def _get_dbpedia_for(uri: str) -> Optional[str]:
    """Return first owl:sameAs DBpedia URI for a given resource."""
    q = _PREFIXES + f"""
    SELECT ?same WHERE {{
        <{uri}> owl:sameAs ?same .
        FILTER (strstarts(str(?same), "http://dbpedia.org"))
    }} LIMIT 1
    """
    rows = store.execute_sparql(q)
    return str(rows[0]["same"]) if rows else None


# ─────────────────────────────────────────────────────────────────────────────
# 2. get_artist_detail
# ─────────────────────────────────────────────────────────────────────────────

def get_artist_detail(artist_slug: str) -> Optional[Dict]:
    artist_ref = f"<http://musickg.org/artist/{artist_slug}>"

    # Basic info
    basic_q = _PREFIXES + f"""
    SELECT ?name WHERE {{
        {artist_ref} a music:Artist ;
                     music:artistName ?name .
    }} LIMIT 1
    """
    basic = store.execute_sparql(basic_q)
    if not basic:
        return None

    name = str(basic[0]["name"])

    # Genres
    genre_q = _PREFIXES + f"""
    SELECT DISTINCT ?genreLabel WHERE {{
        ?track music:performedBy {artist_ref} ;
               music:inGenre ?g .
        ?g rdfs:label ?genreLabel .
    }}
    """
    genres = [str(r["genreLabel"]) for r in store.execute_sparql(genre_q)]

    # Albums — avoid COUNT/GROUP BY due to rdflib/pyparsing bug
    album_q = _PREFIXES + f"""
    SELECT ?albumUri ?albumName ?year WHERE {{
        {artist_ref} music:hasAlbum ?albumUri .
        ?albumUri music:albumName ?albumName ;
                  music:releaseYear ?year .
    }}
    ORDER BY ?year
    """
    # Count tracks per album using a separate simple query
    album_tracks_q = _PREFIXES + f"""
    SELECT ?albumUri ?trackUri WHERE {{
        {artist_ref} music:hasAlbum ?albumUri .
        ?albumUri music:hasTrack ?trackUri .
    }}
    """
    track_counts: Dict[str, int] = {}
    for r in store.execute_sparql(album_tracks_q):
        au = str(r.get("albumUri", ""))
        if au:
            track_counts[au] = track_counts.get(au, 0) + 1

    albums = [
        {
            "uri":         str(r["albumUri"]),
            "slug":        _slug(str(r["albumUri"])),
            "name":        str(r["albumName"]),
            "year":        r.get("year"),
            "track_count": track_counts.get(str(r["albumUri"]), 0),
        }
        for r in store.execute_sparql(album_q)
    ]

    # Top 10 tracks by popularity
    tracks_q = _PREFIXES + f"""
    SELECT ?trackUri ?trackName ?popularity
           ?energy ?danceability ?valence ?tempo ?loudness
    WHERE {{
        ?trackUri a music:Track ;
                  music:trackName ?trackName ;
                  music:performedBy {artist_ref} ;
                  music:popularity ?popularity .
        OPTIONAL {{
            ?trackUri music:hasAudioFeatures ?af .
            ?af music:energy ?energy ;
                music:danceability ?danceability ;
                music:valence ?valence ;
                music:tempo ?tempo ;
                music:loudness ?loudness .
        }}
    }}
    ORDER BY DESC(?popularity)
    LIMIT 10
    """
    top_tracks = []
    energy_sum = dance_sum = val_sum = tempo_sum = loud_sum = 0.0
    feat_count = 0
    for r in store.execute_sparql(tracks_q):
        t = {
            "uri":         str(r["trackUri"]),
            "slug":        _slug(str(r["trackUri"])),
            "name":        str(r["trackName"]),
            "popularity":  r.get("popularity", 0),
            "audio_features": {
                "energy":       r.get("energy"),
                "danceability": r.get("danceability"),
                "valence":      r.get("valence"),
                "tempo":        r.get("tempo"),
                "loudness":     r.get("loudness"),
            },
        }
        top_tracks.append(t)
        if r.get("energy") is not None:
            energy_sum += float(r["energy"])
            dance_sum += float(r["danceability"])
            val_sum += float(r["valence"])
            tempo_sum += float(r["tempo"])
            loud_sum += float(r["loudness"])
            feat_count += 1

    avg_features = None
    if feat_count:
        avg_features = {
            "energy":       round(energy_sum / feat_count, 4),
            "danceability": round(dance_sum / feat_count, 4),
            "valence":      round(val_sum / feat_count, 4),
            "tempo":        round(tempo_sum / feat_count, 4),
            "loudness":     round(loud_sum / feat_count, 4),
        }

    # Similar artists
    similar_q = _PREFIXES + f"""
    SELECT ?simUri ?simName WHERE {{
        {artist_ref} music:similarTo ?simUri .
        ?simUri music:artistName ?simName .
    }} LIMIT 10
    """
    similar = [
        {"uri": str(r["simUri"]), "slug": _slug(
            str(r["simUri"])), "name": str(r["simName"])}
        for r in store.execute_sparql(similar_q)
    ]

    dbpedia = _get_dbpedia_for(f"http://musickg.org/artist/{artist_slug}")

    return {
        "uri":             f"http://musickg.org/artist/{artist_slug}",
        "slug":            artist_slug,
        "name":            name,
        "genres":          genres,
        "dbpedia_uri":     dbpedia,
        "albums":          albums,
        "top_tracks":      top_tracks,
        "avg_audio_features": avg_features,
        "similar_artists": similar,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 3. get_album_detail
# ─────────────────────────────────────────────────────────────────────────────

def get_album_detail(album_slug: str) -> Optional[Dict]:
    album_ref = f"<http://musickg.org/album/{album_slug}>"

    info_q = _PREFIXES + f"""
    SELECT ?albumName ?year ?artistUri ?artistName WHERE {{
        {album_ref} music:albumName ?albumName ;
                    music:releaseYear ?year .
        ?artistUri music:hasAlbum {album_ref} ;
                   music:artistName ?artistName .
    }} LIMIT 1
    """
    info = store.execute_sparql(info_q)
    if not info:
        return None

    r0 = info[0]
    tracks_q = _PREFIXES + f"""
    SELECT DISTINCT ?trackUri ?trackName ?popularity ?duration
           ?energy ?danceability ?valence ?tempo ?loudness
    WHERE {{
        {{
            {album_ref} music:hasTrack ?trackUri .
        }} UNION {{
            ?trackUri music:performedBy ?artistUri .
            ?artistUri music:hasAlbum {album_ref} .
        }}
        ?trackUri music:trackName ?trackName .
        OPTIONAL {{ ?trackUri music:popularity ?popularity }}
        OPTIONAL {{ ?trackUri music:durationMs ?duration }}
        OPTIONAL {{
            ?trackUri music:hasAudioFeatures ?af .
            ?af music:energy ?energy ;
                music:danceability ?danceability ;
                music:valence ?valence ;
                music:tempo ?tempo ;
                music:loudness ?loudness .
        }}
    }}
    ORDER BY ?trackName
    """
    tracks = [
        {
            "uri":        str(r["trackUri"]),
            "slug":       _slug(str(r["trackUri"])),
            "name":       str(r["trackName"]),
            "popularity": r.get("popularity", 0),
            "duration_ms": r.get("duration", 0),
            "audio_features": {
                "energy":       r.get("energy"),
                "danceability": r.get("danceability"),
                "valence":      r.get("valence"),
                "tempo":        r.get("tempo"),
                "loudness":     r.get("loudness"),
            },
        }
        for r in store.execute_sparql(tracks_q)
    ]

    return {
        "uri":         f"http://musickg.org/album/{album_slug}",
        "slug":        album_slug,
        "name":        str(r0["albumName"]),
        "year":        r0.get("year"),
        "artist_uri":  str(r0["artistUri"]),
        "artist_slug": _slug(str(r0["artistUri"])),
        "artist_name": str(r0["artistName"]),
        "tracks":      tracks,
        "track_count": len(tracks),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 4. get_tracks
# ─────────────────────────────────────────────────────────────────────────────

def get_tracks(
    search=None, genre=None,
    year_min=None, year_max=None,
    energy_min=None, energy_max=None,
    limit=20, offset=0,
) -> List[Dict]:

    filters = []
    if search:
        safe = search.replace('"', '\\"')
        filters.append(
            f'FILTER (contains(lcase(str(?trackName)), lcase("{safe}")))')
    if energy_min is not None:
        filters.append(f"FILTER (?energy >= {float(energy_min)})")
    if energy_max is not None:
        filters.append(f"FILTER (?energy <= {float(energy_max)})")

    genre_block = ""
    if genre:
        from urllib.parse import quote as _quote
        genre_uri_str = f"http://musickg.org/genre/{_quote(genre.strip().lower(), safe='')}"
        genre_block = f"""
        ?trackUri music:inGenre <{genre_uri_str}> .
        """

    year_block = ""
    if year_min or year_max:
        year_block = "?albumUri music:hasTrack ?trackUri ; music:releaseYear ?year ."
        if year_min:
            filters.append(f"FILTER (?year >= {int(year_min)})")
        if year_max:
            filters.append(f"FILTER (?year <= {int(year_max)})")

    filter_str = "\n".join(filters)

    query = _PREFIXES + f"""
    SELECT ?trackUri ?trackName ?artistName ?popularity ?duration
           ?energy ?danceability ?valence ?tempo
    WHERE {{
        ?trackUri a music:Track ;
                  music:trackName ?trackName ;
                  music:performedBy ?artist .
        ?artist music:artistName ?artistName .
        OPTIONAL {{ ?trackUri music:popularity ?popularity }}
        OPTIONAL {{ ?trackUri music:durationMs ?duration }}
        OPTIONAL {{
            ?trackUri music:hasAudioFeatures ?af .
            ?af music:energy ?energy ;
                music:danceability ?danceability ;
                music:valence ?valence ;
                music:tempo ?tempo .
        }}
        {genre_block}
        {year_block}
        {filter_str}
    }}
    ORDER BY DESC(?popularity)
    LIMIT {limit}
    OFFSET {offset}
    """

    rows = store.execute_sparql(query)
    return [
        {
            "uri":         str(r["trackUri"]),
            "slug":        _slug(str(r["trackUri"])),
            "name":        str(r["trackName"]),
            "artist":      str(r.get("artistName", "")),
            "popularity":  r.get("popularity", 0),
            "duration_ms": r.get("duration", 0),
            "audio_features": {
                "energy":       r.get("energy"),
                "danceability": r.get("danceability"),
                "valence":      r.get("valence"),
                "tempo":        r.get("tempo"),
            },
        }
        for r in rows
    ]


# ─────────────────────────────────────────────────────────────────────────────
# 5. full_text_search
# ─────────────────────────────────────────────────────────────────────────────
# In-memory search index — parsed directly from NT file (fastest possible)
# ─────────────────────────────────────────────────────────────────────────────

_search_index: Optional[List[Dict]] = None
_index_ready = False
_index_building = False


def _build_search_index() -> List[Dict]:
    """Build search index from CSV — fast (~1s), includes genres per artist."""
    import time as _time
    import logging as _lm
    import csv as _csv
    import hashlib as _hs
    import os as _os
    from urllib.parse import quote as _q
    _log = _lm.getLogger(__name__)
    t0 = _time.time()

    try:
        from django.conf import settings
        base_dir = str(settings.BASE_DIR)
    except Exception:
        base_dir = "."

    csv_candidates = [
        _os.path.join(base_dir, "..", "spotify_songs.csv"),
        _os.path.join(base_dir, "spotify_songs.csv"),
        "spotify_songs.csv",
    ]
    csv_path = next((p for p in csv_candidates if _os.path.exists(p)), None)

    if not csv_path:
        _log.warning(f"spotify_songs.csv not found. Tried: {csv_candidates}")
        return []

    _log.info(f"Building search index from {csv_path}")

    def _make_id(t): return _hs.md5(t.encode()).hexdigest()[:12]
    def _aslug(n): return _q(n.strip().replace(" ", "_"), safe="")

    index: List[Dict] = []
    seen_artists: set = set()
    seen_albums:  set = set()
    artist_pos: Dict[str, int] = {}

    try:
        with open(csv_path, encoding="latin-1", newline="") as f:
            for row in _csv.DictReader(f):
                tid = (row.get("track_id") or "").strip()
                tname = (row.get("track_name") or "").strip()
                aname = (row.get("track_artist") or "").strip()
                alname = (row.get("track_album_name") or "").strip()
                genre = (row.get("playlist_genre") or "").strip().lower()
                try:
                    pop = int(float(row.get("track_popularity") or 0))
                except:
                    pop = 0

                if not tname or not aname:
                    continue

                if aname not in seen_artists:
                    seen_artists.add(aname)
                    slug = _aslug(aname)
                    pos = len(index)
                    artist_pos[aname] = pos
                    index.append({
                        "type": "artist",
                        "uri":  f"http://musickg.org/artist/{slug}",
                        "slug": slug, "name": aname, "name_lower": aname.lower(),
                        "extra_info": {"genres": [genre] if genre else []},
                    })
                elif genre:
                    pos = artist_pos.get(aname)
                    if pos is not None:
                        gs = index[pos]["extra_info"].setdefault("genres", [])
                        if genre not in gs:
                            gs.append(genre)

                al_key = f"{aname}|{alname}"
                if alname and al_key not in seen_albums:
                    seen_albums.add(al_key)
                    aid = _make_id(al_key)
                    rd = (row.get("track_album_release_date") or "")
                    yr = None
                    try:
                        yr = int(rd[:4])
                    except:
                        pass
                    index.append({
                        "type": "album",
                        "uri":  f"http://musickg.org/album/{aid}",
                        "slug": aid, "name": alname, "name_lower": alname.lower(),
                        "extra_info": {"year": yr},
                    })

                if tid:
                    ts = _q(tid, safe="")
                    index.append({
                        "type": "track",
                        "uri":  f"http://musickg.org/track/{ts}",
                        "slug": ts, "name": tname, "name_lower": tname.lower(),
                        "extra_info": {"artist": aname, "popularity": pop},
                    })
    except Exception as e:
        _log.error(f"Search index build error: {e}")
        return []

    _log.info(
        f"Search index built: {len(index):,} entries in {_time.time()-t0:.2f}s")
    return index


def build_search_index_async() -> None:
    """Build index synchronously at startup — fast enough (< 1s from CSV)."""
    global _search_index, _index_ready, _index_building
    if _index_ready:
        return
    _index_building = True
    _search_index = _build_search_index()
    _index_ready = True
    _index_building = False


def _get_search_index() -> List[Dict]:
    global _search_index, _index_ready
    if not _index_ready:
        build_search_index_async()
    return _search_index or []


# ─────────────────────────────────────────────────────────────────────────────
# 5. full_text_search  (fast in-memory)
# ─────────────────────────────────────────────────────────────────────────────

def full_text_search(query: str, limit: int = 20) -> List[Dict]:
    """
    Fast in-memory search. Index built once on startup via RDF triple iteration.
    Each search is O(n) Python string scan — typically <200ms for 80k entries.
    """
    if not query or not query.strip():
        return []

    q_lower = query.strip().lower()
    index = _get_search_index()

    results = []
    for item in index:
        if q_lower not in item["name_lower"]:
            continue
        n = item["name_lower"]
        if n == q_lower:
            score = 1.0
        elif n.startswith(q_lower):
            score = 0.7
        else:
            score = 0.4

        results.append({
            "type":       item["type"],
            "uri":        item["uri"],
            "slug":       item["slug"],
            "name":       item["name"],
            "score":      score,
            "extra_info": item["extra_info"],
        })

    results.sort(key=lambda x: (
        -x["score"],
        -(x["extra_info"].get("popularity") or 0),
        x["name"],
    ))
    return results[:limit]


def _score(name: str, query: str) -> float:
    n, q = name.lower(), query.lower()
    if n == q:
        return 1.0
    if n.startswith(q):
        return 0.7
    return 0.4


# ─────────────────────────────────────────────────────────────────────────────
# 6. get_genre_landscape
# ─────────────────────────────────────────────────────────────────────────────

def get_genre_landscape() -> List[Dict]:
    """Aggregate stats per genre for scatter plot."""
    query = _PREFIXES + """
    SELECT ?genreLabel
           (COUNT(DISTINCT ?artist) AS ?artistCount)
           (COUNT(DISTINCT ?track)  AS ?trackCount)
           (AVG(?energy)            AS ?avgEnergy)
           (AVG(?dance)             AS ?avgDance)
           (AVG(?tempo)             AS ?avgTempo)
           (AVG(?valence)           AS ?avgValence)
           (AVG(?pop)               AS ?avgPop)
    WHERE {
        ?genre a music:Genre ;
               rdfs:label ?genreLabel .
        ?track music:inGenre ?genre ;
               music:performedBy ?artist .
        OPTIONAL { ?track music:popularity ?pop }
        OPTIONAL {
            ?track music:hasAudioFeatures ?af .
            ?af music:energy ?energy ;
                music:danceability ?dance ;
                music:tempo ?tempo ;
                music:valence ?valence .
        }
    }
    GROUP BY ?genreLabel
    ORDER BY DESC(?trackCount)
    """
    rows = store.execute_sparql(query)
    return [
        {
            "genre":           str(r["genreLabel"]),
            "artist_count":    r.get("artistCount", 0),
            "track_count":     r.get("trackCount", 0),
            "avg_energy":      _round(r.get("avgEnergy")),
            "avg_danceability": _round(r.get("avgDance")),
            "avg_tempo":       _round(r.get("avgTempo")),
            "avg_valence":     _round(r.get("avgValence")),
            "avg_popularity":  _round(r.get("avgPop")),
        }
        for r in rows
    ]


def _round(val, digits=4):
    try:
        return round(float(val), digits)
    except (TypeError, ValueError):
        return None


# ─────────────────────────────────────────────────────────────────────────────
# 7. get_audio_distribution
# ─────────────────────────────────────────────────────────────────────────────

def get_audio_distribution() -> dict:
    """
    Histogram data (20 buckets) for energy, danceability,
    valence, tempo, loudness, popularity.
    """
    import math

    feature_queries = {
        "energy":       ("?af music:energy ?val",       0.0,   1.0),
        "danceability": ("?af music:danceability ?val", 0.0,   1.0),
        "valence":      ("?af music:valence ?val",      0.0,   1.0),
        # normalised
        "tempo":        ("?af music:tempo ?val",        0.0,   1.0),
        # normalised
        "loudness":     ("?af music:loudness ?val",     0.0,   1.0),
    }

    result = {}
    BUCKETS = 20

    for feature, (triple_pattern, min_val, max_val) in feature_queries.items():
        q = _PREFIXES + f"""
        SELECT ?val WHERE {{
            ?t music:hasAudioFeatures ?af .
            {triple_pattern}
        }}
        """
        rows = store.execute_sparql(q)
        values = []
        for r in rows:
            try:
                values.append(float(r["val"]))
            except (TypeError, ValueError):
                pass

        buckets, counts = _make_histogram(values, min_val, max_val, BUCKETS)
        result[feature] = {"buckets": buckets, "counts": counts}

    # Popularity (integer 0–100)
    pop_q = _PREFIXES + """
    SELECT ?pop WHERE { ?t music:popularity ?pop }
    """
    pop_vals = []
    for r in store.execute_sparql(pop_q):
        try:
            pop_vals.append(float(r["pop"]))
        except (TypeError, ValueError):
            pass
    buckets, counts = _make_histogram(pop_vals, 0, 100, BUCKETS)
    result["popularity"] = {"buckets": buckets, "counts": counts}

    return result


def _make_histogram(values, min_val, max_val, n_buckets):
    step = (max_val - min_val) / n_buckets
    counts = [0] * n_buckets
    labels = []
    for i in range(n_buckets):
        lo = round(min_val + i * step, 4)
        hi = round(min_val + (i + 1) * step, 4)
        labels.append(f"{lo}–{hi}")
    for v in values:
        idx = int((v - min_val) / step)
        idx = max(0, min(idx, n_buckets - 1))
        counts[idx] += 1
    return labels, counts


# ─────────────────────────────────────────────────────────────────────────────
# 8. execute_raw_sparql
# ─────────────────────────────────────────────────────────────────────────────

_FORBIDDEN = re.compile(
    r'\b(INSERT|DELETE|UPDATE|DROP|CREATE|CLEAR|LOAD|COPY|MOVE|ADD)\b',
    re.IGNORECASE
)


def execute_raw_sparql(query_string: str) -> dict:
    """
    Execute a raw SELECT SPARQL query from the user.
    Blocks modification queries. Returns columns, rows, timing.
    """
    if _FORBIDDEN.search(query_string):
        return {
            "error": "Only SELECT queries are allowed.",
            "columns": [],
            "rows": [],
            "execution_time_ms": 0,
            "triple_count_scanned": 0,
        }

    if not re.search(r'\bSELECT\b', query_string, re.IGNORECASE):
        return {
            "error": "Query must be a SELECT statement.",
            "columns": [],
            "rows": [],
            "execution_time_ms": 0,
            "triple_count_scanned": 0,
        }

    t0 = time.time()
    try:
        rows = store.execute_sparql(query_string)
        elapsed_ms = round((time.time() - t0) * 1000, 2)
        columns = list(rows[0].keys()) if rows else []
        return {
            "columns":              columns,
            "rows":                 rows,
            "execution_time_ms":    elapsed_ms,
            "triple_count_scanned": len(store.graph),
        }
    except Exception as exc:
        return {
            "error":                str(exc),
            "columns":              [],
            "rows":                 [],
            "execution_time_ms":    round((time.time() - t0) * 1000, 2),
            "triple_count_scanned": 0,
        }
