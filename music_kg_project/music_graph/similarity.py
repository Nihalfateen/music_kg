"""
music_graph/similarity.py

Recommendations engine — 3 algorithms:
  1. Audio Feature Cosine Similarity   (numpy + scipy)
  2. Genre Jaccard Similarity          (set intersection)
  3. Combined score + "You may also like" tracks
"""

import logging
import time
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

import numpy as np

from music_graph.rdf_store import store
from music_graph.sparql_queries import _PREFIXES, _round, _slug

log = logging.getLogger(__name__)

AUDIO_WEIGHT      = 0.6
GENRE_WEIGHT      = 0.4
TOP_N_SIMILAR     = 10
TOP_N_TRACKS      = 10
TRACKS_PER_ARTIST = 3


def _fetch_all_artist_features() -> List[Dict]:
    q = _PREFIXES + """
    SELECT ?uri ?name
           (AVG(?energy)   AS ?avgEnergy)
           (AVG(?dance)    AS ?avgDance)
           (AVG(?valence)  AS ?avgValence)
           (AVG(?tempo)    AS ?avgTempo)
           (AVG(?loudness) AS ?avgLoudness)
    WHERE {
        ?uri a music:Artist ; music:artistName ?name .
        ?track music:performedBy ?uri ;
               music:hasAudioFeatures ?af .
        ?af music:energy ?energy ; music:danceability ?dance ;
            music:valence ?valence ; music:tempo ?tempo ;
            music:loudness ?loudness .
    }
    GROUP BY ?uri ?name
    """
    return store.execute_sparql(q)


def _fetch_artist_genres() -> Dict[str, List[str]]:
    q = _PREFIXES + """
    SELECT ?uri ?genreLabel WHERE {
        ?uri a music:Artist .
        ?track music:performedBy ?uri ; music:inGenre ?g .
        ?g rdfs:label ?genreLabel .
    }
    """
    rows = store.execute_sparql(q)
    genre_map: Dict[str, List[str]] = {}
    for r in rows:
        uri = str(r.get("uri", "") or "")
        g   = str(r.get("genreLabel", "") or "")
        if uri and g:
            genre_map.setdefault(uri, [])
            if g not in genre_map[uri]:
                genre_map[uri].append(g)
    return genre_map


def _fetch_top_tracks_for_artists(artist_uris: List[str], exclude_uri: str) -> List[Dict]:
    if not artist_uris:
        return []
    values_block = " ".join(f"<{u}>" for u in artist_uris)
    q = _PREFIXES + f"""
    SELECT ?trackUri ?trackName ?artistUri ?artistName ?popularity ?energy ?dance ?valence
    WHERE {{
        VALUES ?artistUri {{ {values_block} }}
        ?trackUri a music:Track ; music:trackName ?trackName ;
                  music:performedBy ?artistUri .
        ?artistUri music:artistName ?artistName .
        OPTIONAL {{ ?trackUri music:popularity ?popularity }}
        OPTIONAL {{
            ?trackUri music:hasAudioFeatures ?af .
            ?af music:energy ?energy ; music:danceability ?dance ;
                music:valence ?valence .
        }}
        FILTER NOT EXISTS {{ ?trackUri music:performedBy <{exclude_uri}> }}
    }}
    ORDER BY ?artistUri DESC(?popularity)
    """
    return store.execute_sparql(q)


def _fetch_genre_companions(genres: List[str], exclude_uri: str, limit: int = 5) -> List[Dict]:
    if not genres:
        return []
    results = []
    for genre in genres:
        safe = genre.replace('"', '\\"')
        q = _PREFIXES + f"""
        SELECT ?uri ?name (COUNT(?t) AS ?cnt) WHERE {{
            ?g a music:Genre ; rdfs:label "{safe}" .
            ?t music:performedBy ?uri ; music:inGenre ?g .
            ?uri music:artistName ?name .
            FILTER (?uri != <{exclude_uri}>)
        }}
        GROUP BY ?uri ?name
        ORDER BY DESC(?cnt)
        LIMIT {limit}
        """
        rows = store.execute_sparql(q)
        names = [str(r["name"]) for r in rows if r.get("name")]
        if names:
            results.append({"genre": genre, "artists": names})
    return results


def _jaccard(set_a: set, set_b: set) -> float:
    union = set_a | set_b
    return len(set_a & set_b) / len(union) if union else 0.0


def _empty_result() -> Dict:
    return {"similar_artists": [], "recommended_tracks": [], "genre_companions": []}


class _SimilarityEngine:
    def __init__(self):
        self._built = False
        self._uris: List[str] = []
        self._names: Dict[str, str] = {}
        self._matrix: Optional[np.ndarray] = None
        self._matrix_norm: Optional[np.ndarray] = None
        self._genres: Dict[str, List[str]] = {}
        self._uri_idx: Dict[str, int] = {}

    def build(self) -> None:
        if self._built:
            return
        if not store.loaded:
            log.warning("SimilarityEngine: RDFStore not loaded — skipping.")
            return

        t0 = time.time()
        log.info("SimilarityEngine: fetching artist features …")

        rows = _fetch_all_artist_features()
        if not rows:
            log.warning("SimilarityEngine: no features found.")
            self._built = True
            return

        uris, names, vectors = [], {}, []
        for r in rows:
            uri = str(r.get("uri", "") or "")
            if not uri:
                continue
            try:
                energy = float(r.get("avgEnergy",   0) or 0)
                dance  = float(r.get("avgDance",    0) or 0)
                val    = float(r.get("avgValence",  0) or 0)
                tempo  = float(np.clip(float(r.get("avgTempo",    0) or 0), 0, 1))
                loud   = float(np.clip(float(r.get("avgLoudness", 0) or 0), 0, 1))
            except (TypeError, ValueError):
                continue
            uris.append(uri)
            names[uri] = str(r.get("name", "") or "")
            vectors.append([energy, dance, val, tempo, loud])

        if not uris:
            self._built = True
            return

        self._uris    = uris
        self._names   = names
        self._uri_idx = {u: i for i, u in enumerate(uris)}
        mat = np.array(vectors, dtype=np.float32)
        self._matrix  = mat
        norms = np.linalg.norm(mat, axis=1, keepdims=True)
        norms[norms == 0] = 1e-9
        self._matrix_norm = mat / norms

        log.info("SimilarityEngine: fetching genres …")
        self._genres = _fetch_artist_genres()

        elapsed = time.time() - t0
        log.info(f"SimilarityEngine: ready — {len(uris):,} artists, {elapsed:.2f}s")
        self._built = True

    @property
    def is_ready(self) -> bool:
        return self._built and self._matrix_norm is not None and len(self._uris) > 0

    def recommend(self, artist_uri: str, top_n: int = TOP_N_SIMILAR) -> Dict:
        if not self.is_ready:
            return _empty_result()
        idx = self._uri_idx.get(artist_uri)
        if idx is None:
            return _empty_result()

        # Algorithm 1 — cosine similarity (vectorised dot product)
        cosine_sims = (self._matrix_norm @ self._matrix_norm[idx]).copy()
        cosine_sims[idx] = -1.0

        src_genres = set(self._genres.get(artist_uri, []))

        # Algorithm 2 — jaccard on top-50 cosine candidates
        candidate_scores: List[Tuple[int, float, float, float]] = []
        for c_idx in np.argsort(cosine_sims)[-50:][::-1]:
            c_uri = self._uris[int(c_idx)]
            c_cos = float(cosine_sims[c_idx])
            c_jac = _jaccard(src_genres, set(self._genres.get(c_uri, [])))
            final = AUDIO_WEIGHT * max(c_cos, 0.0) + GENRE_WEIGHT * c_jac
            candidate_scores.append((int(c_idx), final, c_cos, c_jac))

        candidate_scores.sort(key=lambda x: -x[1])

        similar_artists: List[Dict] = []
        top_uris: List[str] = []
        for c_idx, final, c_cos, c_jac in candidate_scores[:top_n]:
            c_uri  = self._uris[c_idx]
            shared = sorted(src_genres & set(self._genres.get(c_uri, [])))
            similar_artists.append({
                "uri":              c_uri,
                "slug":             _slug(c_uri),
                "name":             self._names.get(c_uri, ""),
                "similarity_score": round(final,     4),
                "audio_distance":   round(1 - c_cos, 4),
                "genre_jaccard":    round(c_jac,     4),
                "shared_genres":    shared,
            })
            top_uris.append(c_uri)

        # Algorithm 3 — "You may also like" tracks
        track_rows = _fetch_top_tracks_for_artists(top_uris[:5], exclude_uri=artist_uri)
        seen: Dict[str, int] = {}
        candidates: List[Dict] = []
        for r in track_rows:
            a_uri = str(r.get("artistUri", "") or "")
            if seen.get(a_uri, 0) >= TRACKS_PER_ARTIST:
                continue
            seen[a_uri] = seen.get(a_uri, 0) + 1
            pop  = float(r.get("popularity", 0) or 0)
            rank = (top_uris.index(a_uri) + 1) if a_uri in top_uris else 999
            candidates.append({
                "_rs":                pop / rank,
                "track_uri":          str(r.get("trackUri",   "") or ""),
                "track_name":         str(r.get("trackName",  "") or ""),
                "artist_name":        str(r.get("artistName", "") or ""),
                "because_similar_to": self._names.get(a_uri, ""),
                "popularity":         int(pop),
                "energy":             _round(r.get("energy")),
                "danceability":       _round(r.get("dance")),
            })

        candidates.sort(key=lambda x: -x["_rs"])
        recommended_tracks = []
        for t in candidates[:TOP_N_TRACKS]:
            t.pop("_rs", None)
            recommended_tracks.append(t)

        genre_companions = _fetch_genre_companions(list(src_genres)[:3], artist_uri)

        return {
            "similar_artists":    similar_artists,
            "recommended_tracks": recommended_tracks,
            "genre_companions":   genre_companions,
        }


_engine = _SimilarityEngine()


def build_engine() -> None:
    """Called from AppConfig.ready() after store.load()."""
    _engine.build()


@lru_cache(maxsize=1000)
def get_recommendations(artist_slug: str) -> Dict:
    """
    Main public API — called by views.py.
    Cached per slug with lru_cache(maxsize=1000).

    Output:
    {
      "similar_artists":    [{uri, slug, name, similarity_score,
                               audio_distance, genre_jaccard, shared_genres}],
      "recommended_tracks": [{track_uri, track_name, artist_name,
                               because_similar_to, popularity, energy, danceability}],
      "genre_companions":   [{genre, artists:[name,...]}]
    }
    """
    return _engine.recommend(f"http://musickg.org/artist/{artist_slug}")


def clear_recommendation_cache() -> None:
    get_recommendations.cache_clear()
    log.info("Recommendation cache cleared.")


def engine_stats() -> Dict:
    return {
        "built":        _engine._built,
        "artist_count": len(_engine._uris),
        "matrix_shape": list(_engine._matrix.shape) if _engine._matrix is not None else None,
        "cache_info":   get_recommendations.cache_info()._asdict(),
    }
