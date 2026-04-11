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

# def get_artists(search=None, genre=None, limit=20, offset=0) -> List[Dict]:
#     """
#     Fast artist list using the in-memory search index.
#     No SPARQL — reads from pre-built CSV index.
#     """
#     index = _get_search_index()
#
#     # Filter to artists only
#     results = []
#     for item in index:
#         if item["type"] != "artist":
#             continue
#
#         # Genre filter
#         if genre:
#             item_genres = item.get("extra_info", {}).get("genres", [])
#             genre_lower = genre.strip().lower()
#             if genre_lower not in [g.lower() for g in item_genres]:
#                 continue
#
#         # Search filter
#         if search:
#             if search.strip().lower() not in item["name_lower"]:
#                 continue
#
#         results.append({
#             "uri":         item["uri"],
#             "name":        item["name"],
#             "slug":        item["slug"],
#             "genres":      item.get("extra_info", {}).get("genres", []),
#             "dbpedia_uri": None,
#         })
#
#     # Sort and paginate
#     results.sort(key=lambda x: x["name"])
#     return results[offset: offset + limit]

def get_artists(search=None, genre=None, limit=20, offset=0) -> List[Dict]:
    """
    Queries GraphDB for artists, supporting genre and name filters.
    """
    filters = []
    if search:
        filters.append(f'FILTER(CONTAINS(LCASE(?name), "{search.lower()}"))')

    genre_pattern = ""
    if genre:
        # Match artists who have tracks in this genre
        genre_uri = f"<http://musickg.org/genre/{genre.lower().strip()}>"
        genre_pattern = f"?uri music:inGenre {genre_uri} ."

    query = _PREFIXES + f"""
    SELECT DISTINCT ?uri ?name ?slug WHERE {{
        ?uri a music:Artist ;
             music:artistName ?name ;
             music:slug ?slug .
        {genre_pattern}
        {chr(10).join(filters)}
    }}
    ORDER BY ?name
    LIMIT {limit}
    OFFSET {offset}
    """

    rows = store.execute_sparql(query)
    return [
        {
            "uri": str(r["uri"]),
            "name": str(r["name"]),
            "slug": str(r["slug"]),
            "type": "artist"
        }
        for r in rows
    ]

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

    # Albums — avoid COUNT/GROUP BY due to rdflib/pyparsing bug
    album_q = _PREFIXES + f"""
    SELECT ?albumUri ?albumName ?year WHERE {{
        {artist_ref} music:hasAlbum ?albumUri .
        ?albumUri music:albumName ?albumName .
        OPTIONAL {{ ?albumUri music:releaseYear ?year }}
    }}
    ORDER BY DESC(?year)
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


# def update_track_metadata(track_uri: str, new_album_name: str):
#     """Moves a track to a different album node."""
#     # 1. Prepare Identifiers
#     # We derive the artist slug from the track URI to keep it in the same family
#     # track_uri example: http://musickg.org/track/harry_styles_as_it_was
#     parts = track_uri.split('/')[-1].split('_')
#     artist_slug = "_".join(parts[:2])  # e.g., harry_styles
#
#     album_slug = quote(new_album_name.lower().replace(' ', '_'))
#     new_album_uri = f"http://musickg.org/album/{artist_slug}_{album_slug}"
#
#     # 2. The Move Query
#     update_q = f"""
#     PREFIX music: <http://musickg.org/ontology#>
#
#     # 1. Break the old connection
#     DELETE {{ ?oldAlbum music:hasTrack <{track_uri}> }}
#     WHERE  {{ ?oldAlbum music:hasTrack <{track_uri}> }};
#
#     # 2. Create the new connection
#     INSERT DATA {{
#         <{new_album_uri}> rdf:type music:Album ;
#                          music:albumName \"\"\"{new_album_name}\"\"\" ;
#                          music:slug "{artist_slug}_{album_slug}" .
#         <{new_album_uri}> music:hasTrack <{track_uri}> .
#         <http://musickg.org/artist/{artist_slug}> music:hasAlbum <{new_album_uri}> .
#     }}
#     """
#     return store.execute_sparql_update(update_q)

# ─────────────────────────────────────────────────────────────────────────────
# 3. get_album_detail
# ─────────────────────────────────────────────────────────────────────────────

# def get_album_detail(album_slug: str) -> Optional[Dict]:
#     album_ref = f"<http://musickg.org/album/{album_slug}>"
#
#     info_q = _PREFIXES + f"""
#     SELECT ?albumName ?year ?artistUri ?artistName WHERE {{
#         {album_ref} music:albumName ?albumName .
#         OPTIONAL {{ {album_ref} music:releaseYear ?year }}
#         ?artistUri music:hasAlbum {album_ref} ;
#                    music:artistName ?artistName .
#     }} LIMIT 1
#     """
#     info = store.execute_sparql(info_q)
#     if not info:
#         return None
#
#     r0 = info[0]
#     artist_uri = str(r0["artistUri"])
#
#     tracks_q = _PREFIXES + f"""
#     SELECT DISTINCT ?trackUri ?trackName ?popularity ?duration
#            ?energy ?danceability ?valence ?tempo ?loudness
#     WHERE {{
#         ?trackUri a music:Track ;
#                   music:trackName ?trackName ;
#                   music:performedBy <{artist_uri}> .
#
#         # JOIN the album name so the table can see it
#         OPTIONAL {{
#             ?albumUri music:hasTrack ?trackUri ;
#                       music:albumName ?albumName .
#         }}
#         OPTIONAL {{ ?trackUri music:popularity ?popularity }}
#         OPTIONAL {{ ?trackUri music:durationMs ?duration }}
#         OPTIONAL {{
#             ?trackUri music:hasAudioFeatures ?af .
#             ?af music:energy ?energy ;
#                 music:danceability ?danceability ;
#                 music:valence ?valence ;
#                 music:tempo ?tempo ;
#                 music:loudness ?loudness .
#         }}
#     }}
#     ORDER BY ?trackName
#     """
#     tracks = [
#         {
#             "uri":        str(r["trackUri"]),
#             "slug":       _slug(str(r["trackUri"])),
#             "name":       str(r["trackName"]),
#             "album_name": str(r["trackName"]),
#             "popularity": r.get("popularity", 0),
#             "duration_ms": r.get("duration", 0),
#             "audio_features": {
#                 "energy":       r.get("energy"),
#                 "danceability": r.get("danceability"),
#                 "valence":      r.get("valence"),
#                 "tempo":        r.get("tempo"),
#                 "loudness":     r.get("loudness"),
#             },
#         }
#         for r in store.execute_sparql(tracks_q)
#     ]
#
#     return {
#         "uri":         f"http://musickg.org/album/{album_slug}",
#         "slug":        album_slug,
#         "name":        str(r0["albumName"]),
#         "year":        r0.get("year"),
#         "artist_uri":  str(r0["artistUri"]),
#         "artist_slug": _slug(str(r0["artistUri"])),
#         "artist_name": str(r0["artistName"]),
#         "tracks":      tracks,
#         "track_count": len(tracks),
#     }


def get_album_detail(album_slug: str) -> Optional[Dict]:
    album_ref = f"<http://musickg.org/album/{album_slug}>"

    # Prefix block is mandatory for GraphDB
    prefixes = """
    PREFIX music: <http://musickg.org/ontology#>
    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    """

    # 1. Get Album and Artist Info (Artist is OPTIONAL to prevent 404s)
    info_q = prefixes + f"""
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

    # 2. Get ONLY the tracks linked to this album node
    tracks_q = prefixes + f"""
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

# def full_text_search(query: str, limit: int = 20) -> List[Dict]:
#     """
#     Fast in-memory search. Index built once on startup via RDF triple iteration.
#     Each search is O(n) Python string scan — typically <200ms for 80k entries.
#     """
#     if not query or not query.strip():
#         return []
#
#     q_lower = query.strip().lower()
#     index = _get_search_index()
#
#     results = []
#     for item in index:
#         if q_lower not in item["name_lower"]:
#             continue
#         n = item["name_lower"]
#         if n == q_lower:
#             score = 1.0
#         elif n.startswith(q_lower):
#             score = 0.7
#         else:
#             score = 0.4
#
#         results.append({
#             "type":       item["type"],
#             "uri":        item["uri"],
#             "slug":       item["slug"],
#             "name":       item["name"],
#             "score":      score,
#             "extra_info": item["extra_info"],
#         })
#
#     results.sort(key=lambda x: (
#         -x["score"],
#         -(x["extra_info"].get("popularity") or 0),
#         x["name"],
#     ))
#     return results[:limit]

def full_text_search(query: str, limit: int = 20) -> List[Dict]:
    if not query or not query.strip():
        return []

    q_lower = query.strip().lower()

    # 1. GET RESULTS FROM THE LIVE GRAPH (SPARQL)
    # This finds the artists/songs you just added
    graph_q = _PREFIXES + f"""
    SELECT ?uri ?name ?type ?slug WHERE {{
        {{
            ?uri a music:Artist ; music:artistName ?name .
            BIND("artist" AS ?type)
        }} UNION {{
            ?uri a music:Track ; music:trackName ?name .
            BIND("track" AS ?type)
        }} UNION {{
            ?uri a music:Album ; music:albumName ?name .
            BIND("album" AS ?type)
        }}
        ?uri music:slug ?slug .
        FILTER(CONTAINS(LCASE(STR(?name)), "{q_lower}"))
    }} LIMIT {limit}
    """
    graph_rows = store.execute_sparql(graph_q)

    # Format graph results
    results = []
    seen_uris = set()
    for r in graph_rows:
        uri = str(r["uri"])
        seen_uris.add(uri)
        results.append({
            "type": str(r["type"]),
            "uri": uri,
            "slug": str(r["slug"]),
            "name": str(r["name"]),
            "score": 1.0,  # Live matches get top priority
            "extra_info": {"from_graph": True},
        })

    # 2. GET RESULTS FROM CSV INDEX (FAST FALLBACK)
    index = _get_search_index()
    for item in index:
        if item["uri"] in seen_uris: continue  # Don't duplicate
        if q_lower not in item["name_lower"]: continue

        results.append({
            "type": item["type"],
            "uri": item["uri"],
            "slug": item["slug"],
            "name": item["name"],
            "score": _score(item["name"], query),
            "extra_info": item["extra_info"],
        })

    # 3. SORT & LIMIT
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
# 8. Add and Update Information
# ─────────────────────────────────────────────────────────────────────────────

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


# def create_songs_bulk(artist, songs_list):
#     artist_slug = unquote(artist).strip()
#     artist_uri = f"<http://musickg.org/artist/{artist_slug}>"
#     created_count = 0
#
#     for song in songs_list:
#         song_name = song['name'].strip()
#         album_name = song.get('album', '').strip()
#
#         # Create a unique slug for the song
#         track_safe_name = quote(song_name.lower().replace(' ', '_'))
#         song_slug = f"{artist_slug}_{track_safe_name}"
#         track_uri = f"<http://musickg.org/track/{song_slug}>"
#
#         # Check existence using SELECT (to avoid the 'results' error)
#         check_q = _PREFIXES + f"SELECT ?t WHERE {{ {track_uri} music:performedBy {artist_uri} . }} LIMIT 1"
#         if store.execute_sparql(check_q):
#             print(f"Skipping duplicate: {song_name}")
#             continue
#
#             # 3. Handle Album
#         album_triples = ""
#         if album_name:
#             album_safe_name = quote(album_name.lower().replace(' ', '_'))
#             album_slug = f"{artist_slug}_{album_safe_name}"
#             album_uri = f"<http://musickg.org/album/{album_slug}>"
#             album_triples = f"""
#                 {album_uri} a music:Album ;
#                             music:albumName \"\"\"{album_name}\"\"\" .
#                 {album_uri} music:hasTrack {track_uri} .
#                 {artist_uri} music:hasAlbum {album_uri} .
#             """
#
#         # 4. FIXED CONSTRUCT: Added 'rdf:' prefix and triple quotes
#         update_q = f"""
#             PREFIX music: <http://musickg.org/ontology#>
#             PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
#             INSERT DATA {{
#                 {track_uri} rdf:type music:Track .
#                 {track_uri} music:trackName \"\"\"{song_name}\"\"\" .
#                 {track_uri} music:slug "{song_slug}" .
#                 {track_uri} music:performedBy {artist_uri} .
#                 {album_triples}
#             }}
#         """
#
#         if store.execute_sparql_update(update_q):
#             created_count += 1
#
#         if hasattr(get_artist_detail, "cache_clear"):
#             get_artist_detail.cache_clear()
#
#     return created_count > 0, created_count


# def update_track_album(track_uri: str, artist_uri: str, new_album_name: str):
#     """
#     Moves a track to a new album and deletes the old album if it becomes empty.
#     """
#     # 1. Prepare URIs
#     new_slug = new_album_name.lower().replace(" ", "_").strip()
#     new_album_uri = f"http://musickg.org/album/{new_slug}"
#
#     # 2. Perform the Move
#     # We use execute_sparql_update (the method that already exists in your store)
#     update_q = _PREFIXES + f"""
#     DELETE {{ ?oldAlbum music:hasTrack <{track_uri}> }}
#     INSERT {{
#         <{new_album_uri}> a music:Album ;
#                          music:albumName "{new_album_name}" .
#         <{artist_uri}> music:hasAlbum <{new_album_uri}> .
#         <{new_album_uri}> music:hasTrack <{track_uri}> .
#     }} WHERE {{
#         # This finds the old album dynamically inside the graph
#         OPTIONAL {{ ?oldAlbum music:hasTrack <{track_uri}> }}
#     }}
#     """
#     # CHANGE THIS LINE: use execute_sparql_update
#     store.execute_sparql_update(update_q)
#
#     # 3. GARBAGE COLLECTION: Delete any album that is now empty
#     cleanup_q = _PREFIXES + f"""
#     DELETE {{ ?oa ?p ?o . ?s ?p2 ?oa }}
#     WHERE {{
#         ?oa a music:Album .
#         FILTER NOT EXISTS {{ ?oa music:hasTrack ?anyTrack }}
#         ?oa ?p ?o .
#         OPTIONAL {{ ?s ?p2 ?oa }}
#     }}
#     """
#     # CHANGE THIS LINE: use execute_sparql_update
#     store.execute_sparql_update(cleanup_q)
#
#     if hasattr(get_artist_detail, "cache_clear"):
#         get_artist_detail.cache_clear()
#
#     return True

def create_songs_bulk(artist_slug, songs_list):
    artist_slug = unquote(artist_slug).strip()
    artist_uri = f"http://musickg.org/artist/{artist_slug}"
    created_count = 0

    for song in songs_list:
        song_name = song['name'].strip()
        album_name = song.get('album', '').strip()

        # Track URI
        track_safe_name = quote(song_name.lower().replace(' ', '_'))
        song_slug = f"{artist_slug}_{track_safe_name}"
        track_uri = f"http://musickg.org/track/{song_slug}"

        # 1. Smart Album Check (The "Twin" Fix)
        # We look for ANY album linked to this artist that matches the name
        album_check_q = _PREFIXES + f"""
            SELECT ?alb WHERE {{ 
                <{artist_uri}> music:hasAlbum ?alb . 
                ?alb music:albumName ?name .
                FILTER(LCASE(STR(?name)) = "{album_name.lower()}")
            }} LIMIT 1
        """
        existing_alb = store.execute_sparql(album_check_q)

        # if existing_alb:
        #     # Use the existing URI found in the graph
        #     album_uri = str(existing_alb[0]['alb'])
        # else:
        #     # Only create a new one if it truly doesn't exist
        #     album_safe_name = quote(album_name.lower().replace(' ', '_'))
        #     album_uri = f"http://musickg.org/album/{album_safe_name}"

        if album_name:
            # 1. Create the scoped slug (Artist + Album)
            album_safe_name = quote(album_name.lower().replace(' ', '_'))
            album_slug = f"{artist_slug}_{album_safe_name}"

            # 2. Check if this artist already has this album (The "Twin" Fix)
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
                # Ensure we use the slug already in the graph
                final_album_slug = album_slug  # Or fetch from graph if different
            else:
                album_uri = f"http://musickg.org/album/{album_slug}"
                final_album_slug = album_slug
        else:
            # Fallback for singles
            final_album_slug = f"{artist_slug}_singles"
            album_uri = f"http://musickg.org/album/{final_album_slug}"
            album_name = "Singles"

        # 2. Combined INSERT
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

# def update_track_album(track_uri: str, artist_uri: str, new_album_name: str):
#     # 1. CHECK FOR EXISTING ALBUM
#     # Ask the graph: "Does this artist already have an album with this exact name?"
#     check_q = _PREFIXES + f"""
#     SELECT ?existingAlbum WHERE {{
#         <{artist_uri}> music:hasAlbum ?existingAlbum .
#         ?existingAlbum music:albumName "{new_album_name}" .
#     }} LIMIT 1
#     """
#     res = store.execute_sparql(check_q)
#
#     if res:
#         # If it exists, use that URI!
#         new_album_uri = str(res[0]['existingAlbum'])
#     else:
#         # If it doesn't exist, only THEN create a new slug-based URI
#         new_slug = new_album_name.lower().replace(" ", "_").strip()
#         new_album_uri = f"http://musickg.org/album/{new_slug}"
#
#     # 2. Perform the Move (Same as before, but using the smarter new_album_uri)
#     update_q = _PREFIXES + f"""
#     DELETE {{ ?oldAlbum music:hasTrack <{track_uri}> }}
#     INSERT {{
#         <{new_album_uri}> a music:Album ;
#                          music:albumName "{new_album_name}" ;
#                          music:slug "{new_slug}" .
#         <{artist_uri}> music:hasAlbum <{new_album_uri}> .
#         <{new_album_uri}> music:hasTrack <{track_uri}> .
#     }} WHERE {{
#         OPTIONAL {{ ?oldAlbum music:hasTrack <{track_uri}> }}
#     }}
#     """
#     store.execute_sparql_update(update_q)
#
#     # 3. GARBAGE COLLECTION (Crucial: This will kill the duplicate once it's empty)
#     cleanup_q = _PREFIXES + f"""
#     DELETE {{ ?oa ?p ?o . ?s ?p2 ?oa }}
#     WHERE {{
#         ?oa a music:Album .
#         FILTER NOT EXISTS {{ ?oa music:hasTrack ?anyTrack }}
#         ?oa ?p ?o .
#         OPTIONAL {{ ?s ?p2 ?oa }}
#     }}
#     """
#     store.execute_sparql_update(cleanup_q)
#
#     if hasattr(get_artist_detail, "cache_clear"):
#         get_artist_detail.cache_clear()
#
#     return True

def update_track_album(track_uri: str, artist_uri: str, new_album_name: str) -> bool:
    # 1. Clean  for SPARQL
    t_uri = f"<{track_uri}>" if not track_uri.startswith("<") else track_uri
    a_uri = f"<{artist_uri}>" if not artist_uri.startswith("<") else artist_uri

    # 2. Check if the artist already has an album with this name
    check_q = _PREFIXES + f"""
    SELECT ?albumUri WHERE {{
        {a_uri} music:hasAlbum ?albumUri .
        ?albumUri music:albumName "{new_album_name}" .
    }} LIMIT 1
    """
    res = store.execute_sparql(check_q)

    if res:
        # Album exists: use its existing URI
        target_album_uri = f"<{res[0]['albumUri']}>"
    else:
        # Album is new: define slug and URI inside this block
        safe_name = quote(new_album_name.lower().replace(" ", "_"))
        artist_part = _slug(artist_uri.strip("<>"))
        generated_slug = f"{artist_part}_{safe_name}"
        target_album_uri = f"<http://musickg.org/album/{generated_slug}>"

        # Create the new album node first
        insert_alb_q = _PREFIXES + f"""
        INSERT DATA {{
            {target_album_uri} a music:Album ;
                               music:albumName "{new_album_name}" ;
                               music:slug "{generated_slug}" .
            {a_uri} music:hasAlbum {target_album_uri} .
        }}
        """
        store.execute_sparql_update(insert_alb_q)

    # 3. Execute the move:
    # - Remove old hasTrack link
    # - Add new hasTrack link
    # - Update the string property on the track itself
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
        cleanup_q = _PREFIXES + """
            DELETE {
                ?alb ?p ?o .
                ?artist music:hasAlbum ?alb .
            }
            WHERE {
                ?alb a music:Album .
                ?alb ?p ?o .
                OPTIONAL { ?artist music:hasAlbum ?alb . }

                # The condition for total disappearance:
                FILTER NOT EXISTS { ?alb music:hasTrack ?anyTrack . }
            }
            """
        store.execute_sparql_update(cleanup_q)

    if success and hasattr(get_artist_detail, "cache_clear"):
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


# def create_track_for_artist(artist_uri: str, track_name: str, album_name: str = None) -> bool:
#     # 1. Generate URIs
#     artist_slug = _slug(artist_uri)
#     track_slug = f"{artist_slug}_{quote(track_name.lower().replace(' ', '_'))}"
#     track_uri = f"http://musickg.org/track/{track_slug}"
#
#     _PREFIXES = """
#     PREFIX rdf:   <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
#     PREFIX rdfs:  <http://www.w3.org/2000/01/rdf-schema#>
#     PREFIX xsd:   <http://www.w3.org/2001/XMLSchema#>
#     PREFIX music: <http://musickg.org/ontology#>
#     """
#
#     # 2. Start the triple block
#     triples = [
#         f"<{track_uri}> a music:Track .",
#         f"<{track_uri}> music:trackName \"{track_name}\" .",
#         f"<{track_uri}> music:performedBy <{artist_uri}> ."
#     ]
#
#     # 3. Handle Album (Optional)
#     if album_name:
#         album_slug = f"{artist_slug}_{quote(album_name.lower().replace(' ', '_'))}"
#         album_uri = f"http://musickg.org/album/{album_slug}"
#
#         # Add album metadata and the bidirectional link
#         triples.extend([
#             f"<{album_uri}> a music:Album .",
#             f"<{album_uri}> music:albumName \"{album_name}\" .",
#             f"<{track_uri}> music:albumName \"{album_name}\" .",
#             f"<{artist_uri}> music:hasAlbum <{album_uri}> .",
#             f"<{album_uri}> music:hasTrack <{track_uri}> ."
#         ])
#
#     update_q = _PREFIXES + f"INSERT DATA {{ {' '.join(triples)} }}"
#     return store.execute_sparql_update(update_q)

def delete_track_from_graph(track_uri: str) -> bool:
    """
    Deletes the track and all its properties.
    Then cleans up any albums that are now empty.
    """
    t_uri = f"<{track_uri}>" if not track_uri.startswith("<") else track_uri

    # 1. Delete the track node and all incoming/outgoing links
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
        if hasattr(get_artist_detail, "cache_clear"):
            get_artist_detail.cache_clear()

    return success

# ─────────────────────────────────────────────────────────────────────────────
# 9. execute_raw_sparql
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
