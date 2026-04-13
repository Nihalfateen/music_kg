"""
music_graph/sparql_queries.py

All SPARQL-backed query functions.
Each function builds a query string, runs it through the RDFStore singleton,
and returns clean Python dicts ready for serialization.
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

# Shared SPARQL prefix block
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

def _round(val, digits=4):
    try:
        return round(float(val), digits)
    except (TypeError, ValueError):
        return None

def _int(val):
    try:
        return int(float(val)) if val is not None else 0
    except (TypeError, ValueError):
        return 0

def _artist_uri_from_slug(slug: str) -> str:
    return f"<http://musickg.org/artist/{slug}>"

def _album_uri_from_slug(slug: str) -> str:
    return f"<http://musickg.org/album/{slug}>"


# ─────────────────────────────────────────────────────────────────────────────
# 1. get_artists
# ─────────────────────────────────────────────────────────────────────────────


def get_artists(search=None, genre=None, limit=500, offset=0) -> List[Dict]:
    """
     Queries GraphDB for artists, supporting genre and name filters.
     """
    limit_val = int(limit) if limit else 500

    query = _PREFIXES + f"""
    SELECT ?uri 
           (SAMPLE(?nameVal) AS ?name) 
           (SAMPLE(?slugVal) AS ?slug) 
           (GROUP_CONCAT(DISTINCT ?gLabel; SEPARATOR=",") AS ?genreList)
    WHERE {{
        ?uri a music:Artist .

        OPTIONAL {{ ?uri music:artistName ?n1 }}
        OPTIONAL {{ ?uri rdfs:label ?n2 }}
        BIND(COALESCE(?n1, ?n2, REPLACE(STR(?uri), "^.*[/#]", "")) AS ?nameVal)

        OPTIONAL {{ ?uri music:slug ?s1 }}
        BIND(COALESCE(?s1, REPLACE(STR(?uri), "^.*[/#]", "")) AS ?slugVal)

        OPTIONAL {{
            ?uri music:performs ?track .
            ?track (music:inGenre|schema:genre) ?gen .
            OPTIONAL {{ ?gen (rdfs:label|schema:name) ?lab }}
            BIND(COALESCE(?lab, REPLACE(STR(?gen), "^.*[/#]", "")) AS ?gLabel)
        }}
    }}
    GROUP BY ?uri
    LIMIT {limit_val}
    """

    rows = store.execute_sparql(query)
    results = []
    for r in rows:
        uri_str = str(r["uri"])
        name = str(r.get("name") or uri_str.split("/")[-1])
        slug = str(r.get("slug") or uri_str.split("/")[-1])

        genre_list = [g.strip().lower() for g in str(r.get("genreList", "")).split(",") if g.strip()]

        results.append({
            "uri": uri_str,
            "name": name,
            "slug": slug,
            "type": "artist",
            "genres": genre_list
        })
    return results


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

def get_artist_detail(artist: str) -> Optional[Dict]:
    artist_slug = artist.strip()
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

    # Albums
    album_q = _PREFIXES + f"""
    SELECT ?albumUri ?albumName ?year WHERE {{
        {artist_ref} music:hasAlbum ?albumUri .
        ?albumUri music:albumName ?albumName .
        OPTIONAL {{ ?albumUri music:releaseYear ?year }}
    }}
    ORDER BY DESC(?year)
    """
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
            "year":        r.get("year", "Unknown"),
            "track_count": track_counts.get(str(r["albumUri"]), 0),
        }
        for r in store.execute_sparql(album_q)
    ]

    # Tracks by popularity
    tracks_q = _PREFIXES + f"""
    SELECT ?trackUri ?trackName ?albumUri ?albumName ?popularity
           ?energy ?danceability ?valence ?tempo ?loudness
    WHERE {{
        ?trackUri music:performedBy {artist_ref} ;
                  music:trackName ?trackName .

        OPTIONAL {{ ?albumUri music:hasTrack ?trackUri ; music:albumName ?albumName . }}
        OPTIONAL {{ ?trackUri music:popularity ?popularity }}

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
            "album_uri":  str(r.get("albumUri", "")),
            "album_name": r.get("albumName", 'Single'),
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
    if feat_count > 0:
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
        {"uri": str(r["simUri"]), "slug": _slug(str(r["simUri"])), "name": str(r["simName"])}
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
    SELECT ?albumName ?year ?artistName ?artistUri WHERE {{
        {album_ref} music:albumName ?albumName .
        OPTIONAL {{ {album_ref} music:releaseYear ?year . }}
        OPTIONAL {{
            ?artistUri music:hasAlbum {album_ref} ;
                       music:artistName ?artistName .
        }}
    }} LIMIT 1
    """
    info = store.execute_sparql(info_q)
    if not info:
        return None

    r0 = info[0]
    artist_uri = r0.get("artistUri")

    tracks_q = _PREFIXES + f"""
    SELECT DISTINCT ?trackUri ?trackName ?pop ?dur ?e ?d ?v WHERE {{
        {album_ref} music:hasTrack ?trackUri . 
        ?trackUri music:trackName ?trackName .
        OPTIONAL {{ ?trackUri music:popularity ?pop }}
        OPTIONAL {{ ?trackUri music:durationMs ?dur }}
        OPTIONAL {{
            ?trackUri music:hasAudioFeatures ?af .
            ?af music:energy ?e ; music:danceability ?d ; music:valence ?v .
        }}
    }}
    ORDER BY ?trackName
    """

    results = store.execute_sparql(tracks_q)
    tracks = [{
        "uri": str(r["trackUri"]),
        "name": str(r["trackName"]),
        "popularity": _int(r.get("pop")),
        "duration_ms": _int(r.get("dur")),
        "audio_features": {
            "energy": _round(r.get("e")),
            "danceability": _round(r.get("d")),
            "valence": _round(r.get("v"))
        }
    } for r in results]

    return {
        "uri": album_ref.strip("<>"),
        "name": str(r0["albumName"]),
        "year": str(r0.get("year", "Unknown")),
        "artist_name": str(r0.get("artistName", "Unknown Artist")),
        "artist_slug": _slug(artist_uri) if artist_uri else "unknown",
        "tracks": tracks,
        "track_count": len(tracks)
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
# 5. build_search_index
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
    album_pos: Dict[str, int] = {}

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
                        "extra_info": {"genres": [genre] if genre else [], "popularity": pop},
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
                        "extra_info": {"year": yr, "genres": [genre] if genre else [], "popularity": pop},
                    })
                elif genre and al_key in album_pos:
                    pos = album_pos.get(al_key)
                    gs = index[pos]["extra_info"].setdefault("genres", [])
                    if genre not in gs: gs.append(genre)

                if tid:
                    ts = _q(tid, safe="")
                    index.append({
                        "type": "track",
                        "uri":  f"http://musickg.org/track/{ts}",
                        "slug": ts, "name": tname, "name_lower": tname.lower(),
                        "extra_info": {"artist": aname, "popularity": pop, "genres": [genre] if genre else []},
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

def full_text_search(query: str, genre: str = None, e_type: str = None, limit: int = 20, offset: int = 0) -> dict:
    q_lower = query.strip().lower() if query else ""

    if not q_lower and not genre:
        return {"results": [], "total_count": 0}

    type_filter = ""
    if e_type == 'artist':
        type_filter = 'FILTER(?type = "artist")'
    elif e_type == 'album':
        type_filter = 'FILTER(?type = "album")'
    elif e_type == 'track':
        type_filter = 'FILTER(?type = "track")'
    elif e_type == 'artist_album':
        type_filter = 'FILTER(?type = "artist" || ?type = "album")'

    genre_sparql = f"?uri music:inGenre <http://musickg.org/genre/{genre.lower()}> ." if genre else ""
    name_filter = f'FILTER(CONTAINS(LCASE(STR(?name)), "{q_lower}"))' if q_lower else ""

    graph_q = _PREFIXES + f"""
    SELECT DISTINCT ?uri ?name ?type ?slug ?pop WHERE {{
        {{
            {{ ?uri a music:Artist ; music:artistName ?name . BIND("artist" AS ?type) OPTIONAL {{ ?uri music:popularity ?pop }} }}
            UNION 
            {{ ?uri a music:Track ; music:trackName ?name . BIND("track" AS ?type) OPTIONAL {{ ?uri music:popularity ?pop }} }}
            UNION 
            {{ ?uri a music:Album ; music:albumName ?name . BIND("album" AS ?type) OPTIONAL {{ ?uri music:releaseYear ?pop }} }}
        }}
        
        ?uri music:slug ?slug .
        {genre_sparql}
        {name_filter}
        {type_filter}
    }} LIMIT 500
    """
    graph_rows = store.execute_sparql(graph_q)
    results = []
    seen_uris = set()

    for r in graph_rows:
        uri = str(r["uri"])
        seen_uris.add(uri)
        results.append({
            "type": str(r["type"]), "uri": uri, "slug": str(r["slug"]), "name": str(r["name"]),
            "score": 1.0,
            "popularity": _int(r.get("pop")),
            "extra_info": {"from_graph": True},
        })

    index = _get_search_index()
    for item in index:
        if item["uri"] in seen_uris: continue

        if e_type == 'artist_album':
            if item["type"] not in ['artist', 'album']:
                continue
        elif e_type and item["type"] != e_type:
            continue

        if q_lower and q_lower not in item["name_lower"]:
            continue

        if genre:
            item_genres = item.get("extra_info", {}).get("genres", [])
            if genre.lower() not in [g.lower() for g in item_genres]:
                continue

        results.append({
            "type": item["type"],
            "uri": item["uri"],
            "slug": item["slug"],
            "name": item["name"],
            "score": _score(item["name"], query) if q_lower else 0.5,
            "popularity": item.get("extra_info", {}).get("popularity") or 0,
            "extra_info": item["extra_info"],
        })

    results.sort(key=lambda x: (
        -x["score"],
        -(x["extra_info"].get("popularity") or 0),
        x["uri"]
    ))
    total_count = len(results)

    return {"results": results[offset : offset + limit], "total_count": total_count}

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
        "tempo":        ("?af music:tempo ?val",        0.0,   1.0),
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
# 8. Similarity edges (graph page)
# ─────────────────────────────────────────────────────────────────────────────

def get_similarity_edges(limit=2000) -> List[Dict]:
    """
    Finds artists who share a genre.
    Generates slugs from URIs to ensure connections work even if music:slug is missing.
    """
    query = _PREFIXES + f"""
    SELECT DISTINCT ?sSlug ?tSlug WHERE {{
        ?s1 a music:Artist ; (music:inGenre|schema:genre) ?g .
        ?s2 a music:Artist ; (music:inGenre|schema:genre) ?g .

        BIND(REPLACE(STR(?s1), "^.*[/#]", "") AS ?sSlug)
        BIND(REPLACE(STR(?s2), "^.*[/#]", "") AS ?tSlug)

        FILTER(?sSlug < ?tSlug)
    }} LIMIT {int(limit)}
    """
    rows = store.execute_sparql(query)

    return [{"source": str(r["sSlug"]), "target": str(r["tSlug"])} for r in rows]

# ─────────────────────────────────────────────────────────────────────────────
# 9. Add and Update Information
# ─────────────────────────────────────────────────────────────────────────────

CLEANUP_EMPTY_ALBUMS_QUERY = _PREFIXES + """
    DELETE {
        ?alb ?p ?o .
        ?s ?rel ?alb .
    }
    WHERE {
        ?alb a music:Album .
        FILTER NOT EXISTS { 
            ?alb music:hasTrack ?track . 
            ?track a music:Track . 
        }
        ?alb ?p ?o .
        OPTIONAL { ?s ?rel ?alb . }
    }
"""

def create_artist_node(name: str, genre: str):
    slug = quote(name.lower().strip().replace(" ", "_"))
    artist_uri = f"<http://musickg.org/artist/{slug}>"
    genre_uri = f"<http://musickg.org/genre/{genre.lower().strip()}>"

    check_q = _PREFIXES + f"SELECT ?name WHERE {{ {artist_uri} music:artistName ?name . }} LIMIT 1"
    exists = store.execute_sparql(check_q)

    if exists:
        print("Duplicate detected.")
        return False, slug

    update_q = f"""
    PREFIX music: <http://musickg.org/ontology#>
    INSERT DATA {{
        {artist_uri} a music:Artist ;
                    music:artistName \"\"\"{name}\"\"\" ;
                    music:slug "{slug}" .
        {artist_uri} music:inGenre {genre_uri} .
    }}
    """
    success = store.execute_sparql_update(update_q)
    return success, slug


def create_songs_bulk(artist_slug, songs_list):
    artist_slug = unquote(artist_slug).strip()
    artist_uri = f"http://musickg.org/artist/{artist_slug}"
    created_count = 0

    for song in songs_list:
        song_name = song['name'].strip()
        album_name = song.get('album', '').strip()

        track_safe_name = quote(song_name.lower().replace(' ', '_'))
        song_slug = f"{artist_slug}_{track_safe_name}"
        track_uri = f"http://musickg.org/track/{song_slug}"

        if album_name:
            album_safe_name = quote(album_name.lower().replace(' ', '_'))
            album_slug = f"{artist_slug}_{album_safe_name}"

            album_check_q = _PREFIXES + f"""
                        SELECT ?alb WHERE {{ 
                            <{artist_uri}> music:hasAlbum ?alb . 
                            ?alb music:albumName ?name .
                            FILTER(LCASE(STR(?name)) = "{album_name.lower()}")
                        }} LIMIT 1
                    """
            existing_alb = store.execute_sparql(album_check_q)

            if existing_alb:
                album_uri = str(existing_alb[0]['alb'])
                final_album_slug = album_slug
            else:
                album_uri = f"http://musickg.org/album/{album_slug}"
                final_album_slug = album_slug
        else:
            final_album_slug = f"{artist_slug}_singles"
            album_uri = f"http://musickg.org/album/{final_album_slug}"
            album_name = "Singles"

        update_q = _PREFIXES + f"""
            INSERT DATA {{
                <{track_uri}> rdf:type music:Track ;
                             music:trackName \"\"\"{song_name}\"\"\" ;
                             music:slug "{song_slug}" ;
                             music:performedBy <{artist_uri}> ;
                             music:popularity 0 . 

                <{album_uri}> rdf:type music:Album ; 
                             music:albumName \"\"\"{album_name}\"\"\" ;
                             music:slug "{final_album_slug}" .
                <{album_uri}> music:hasTrack <{track_uri}> .
                <{artist_uri}> music:hasAlbum <{album_uri}> .
            }}
        """
        if store.execute_sparql_update(update_q):
            created_count += 1

    if hasattr(get_artist_detail, "cache_clear"):
        get_artist_detail.cache_clear()

    return created_count > 0, created_count


def update_track_album(track_uri: str, artist_uri: str, new_album_name: str) -> bool:
    t_uri = f"<{track_uri}>" if not track_uri.startswith("<") else track_uri
    a_uri = f"<{artist_uri}>" if not artist_uri.startswith("<") else artist_uri

    check_q = _PREFIXES + f"""
    SELECT ?albumUri WHERE {{
        {a_uri} music:hasAlbum ?albumUri .
        ?albumUri music:albumName "{new_album_name}" .
    }} LIMIT 1
    """
    res = store.execute_sparql(check_q)

    if res:
        target_album_uri = f"<{res[0]['albumUri']}>"
    else:
        safe_name = quote(new_album_name.lower().replace(" ", "_"))
        artist_part = _slug(artist_uri.strip("<>"))
        generated_slug = f"{artist_part}_{safe_name}"
        target_album_uri = f"<http://musickg.org/album/{generated_slug}>"

        insert_alb_q = _PREFIXES + f"""
        INSERT DATA {{
            {target_album_uri} a music:Album ;
                               music:albumName "{new_album_name}" ;
                               music:slug "{generated_slug}" .
            {a_uri} music:hasAlbum {target_album_uri} .
        }}
        """
        store.execute_sparql_update(insert_alb_q)

    update_q = _PREFIXES + f"""
    DELETE {{ 
        ?oldAlbum music:hasTrack {t_uri} . 
        {t_uri} music:albumName ?oldName .
    }}
    INSERT {{ 
        {target_album_uri} music:hasTrack {t_uri} . 
        {t_uri} music:albumName "{new_album_name}" .
    }}
    WHERE {{
        OPTIONAL {{ ?oldAlbum music:hasTrack {t_uri} . }}
        OPTIONAL {{ {t_uri} music:albumName ?oldName . }}
    }}
    """

    success = store.execute_sparql_update(update_q)

    if success:
        store.execute_sparql_update(CLEANUP_EMPTY_ALBUMS_QUERY)

        if hasattr(get_artist_detail, "cache_clear"):
            get_artist_detail.cache_clear()

    return success

def update_album_year(album_uri: str, new_year: int) -> bool:
    """
    Updates the music:releaseYear for a specific album node in GraphDB.
    Uses DELETE/INSERT to ensure the old year is replaced rather than duplicated.
    """
    if not album_uri.startswith("<"):
        album_uri = f"<{album_uri}>"

    prefixes = """
    PREFIX music: <http://musickg.org/ontology#>
    PREFIX xsd:   <http://www.w3.org/2001/XMLSchema#>
    """

    update_q = prefixes + f"""
    DELETE {{ {album_uri} music:releaseYear ?oldYear . }}
    INSERT {{ {album_uri} music:releaseYear "{new_year}"^^xsd:integer . }}
    WHERE  {{ 
        OPTIONAL {{ {album_uri} music:releaseYear ?oldYear . }}
    }}
    """

    try:
        return store.execute_sparql_update(update_q)
    except Exception as e:
        log.error(f"SPARQL Update Error for album {album_uri}: {str(e)}")
        return False


def delete_track_from_graph(track_uri: str) -> bool:
    """
    Deletes the track and all its properties.
    Then cleans up any albums that are now empty.
    """
    t_uri = f"<{track_uri}>" if not track_uri.startswith("<") else track_uri

    delete_q = _PREFIXES + f"""
    DELETE {{
        {t_uri} ?p ?o .
        ?subject ?p2 {t_uri} .
    }}
    WHERE {{
        {t_uri} ?p ?o .
        OPTIONAL {{ ?subject ?p2 {t_uri} . }}
    }}
    """
    success = store.execute_sparql_update(delete_q)

    if success:
        store.execute_sparql_update(CLEANUP_EMPTY_ALBUMS_QUERY)
        if hasattr(get_artist_detail, "cache_clear"):
            get_artist_detail.cache_clear()

    return success

# ─────────────────────────────────────────────────────────────────────────────
# 10. execute_raw_sparql
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
