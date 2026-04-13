"""
convert_to_rdf.py
Spotify Tracks Dataset → Music Knowledge Graph (OWL + Named Graphs + Inference)
"""

import os
import json
import time
import hashlib
import logging
from datetime import datetime, timezone
from urllib.parse import quote

import pandas as pd
import numpy as np
from tqdm import tqdm
from scipy.spatial.distance import cosine

from rdflib import (
    ConjunctiveGraph, Graph, URIRef, Literal, Namespace, BNode
)
from rdflib.namespace import RDF, RDFS, OWL, XSD

# ─────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Namespaces
# ─────────────────────────────────────────────
BASE   = Namespace("http://musickg.org/")
MUSIC  = Namespace("http://musickg.org/ontology#")
SCHEMA = Namespace("http://schema.org/")

# Named graph URIs
G_ONTOLOGY = URIRef("http://musickg.org/graph/ontology")
G_ARTISTS  = URIRef("http://musickg.org/graph/artists")
G_ALBUMS   = URIRef("http://musickg.org/graph/albums")
G_TRACKS   = URIRef("http://musickg.org/graph/tracks")

# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def safe_uri_part(text: str) -> str:
    """Slug-ify text for use in URI local names."""
    return quote(str(text).strip().replace(" ", "_"), safe="")


def make_id(text: str) -> str:
    """Short stable hash for deduplication-safe IDs."""
    return hashlib.md5(str(text).encode()).hexdigest()[:12]


def artist_uri(name: str) -> URIRef:
    return BASE[f"artist/{safe_uri_part(name)}"]


def album_uri(artist: str, album: str) -> URIRef:
    return BASE[f"album/{make_id(artist + '|' + album)}"]


def track_uri(track_id: str) -> URIRef:
    return BASE[f"track/{safe_uri_part(track_id)}"]


def genre_uri(genre: str) -> URIRef:
    return BASE[f"genre/{safe_uri_part(genre)}"]


def audio_uri(track_id: str) -> URIRef:
    return BASE[f"audio/{safe_uri_part(track_id)}"]


# ─────────────────────────────────────────────
# STEP 1 — Data Cleaning
# ─────────────────────────────────────────────

def load_and_clean(csv_path: str) -> pd.DataFrame:
    log.info("Loading CSV …")

    try:
        df = pd.read_csv(csv_path, low_memory=False, encoding="utf-8")
    except UnicodeDecodeError:
        log.warning("  UTF-8 failed — retrying with latin-1 encoding")
        df = pd.read_csv(csv_path, low_memory=False, encoding="latin-1")

    log.info(f"  Rows loaded  : {len(df):,}")
    log.info(f"  Columns      : {df.columns.tolist()}")

    # Column normalization for spotify_songs.csv
    # Map actual column names → standard names used throughout the script
    rename_map = {
        "track_artist":              "artist_name",
        "track_album_name":          "album_name",
        "track_popularity":          "popularity",
        "playlist_genre":            "genre",
        # release date → year extracted below
        "track_album_release_date":  "_release_date",
    }
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})

    # Extract year from release date string (e.g. "2019-06-14" or "2019")
    if "_release_date" in df.columns and "year" not in df.columns:
        df["year"] = pd.to_datetime(
            df["_release_date"], errors="coerce"
        ).dt.year
        df = df.drop(columns=["_release_date"])

    # Deduplicate
    df = df.drop_duplicates(subset="track_id")
    log.info(f"  After dedup  : {len(df):,}")

    # Drop critical nulls
    df = df.dropna(subset=["artist_name", "track_name"])
    log.info(f"  After null drop : {len(df):,}")

    # Normalize text columns
    for col in ["track_name", "artist_name", "album_name", "genre"]:
        if col in df.columns:
            df[col] = (
                df[col]
                .astype(str)
                .str.strip()
                .str.encode("utf-8", errors="ignore")
                .str.decode("utf-8")
            )

    # Fill missing album / genre with sensible defaults
    if "album_name" in df.columns:
        df["album_name"] = df["album_name"].replace("nan", "Unknown Album").fillna("Unknown Album")
    if "genre" in df.columns:
        df["genre"] = df["genre"].replace("nan", "Unknown").fillna("Unknown")

    # Year filter
    df["year"] = pd.to_numeric(df["year"], errors="coerce")
    df = df[(df["year"] >= 1900) & (df["year"] <= 2024)]
    log.info(f"  After year filter : {len(df):,}")

    # Normalise audio features to [0, 1]
    # tempo: 0–250 BPM
    if "tempo" in df.columns:
        df["tempo"] = pd.to_numeric(df["tempo"], errors="coerce").fillna(0)
        df["tempo_norm"] = df["tempo"].clip(0, 250) / 250.0

    # loudness: −60 to 0 dB
    if "loudness" in df.columns:
        df["loudness"] = pd.to_numeric(df["loudness"], errors="coerce").fillna(-60)
        df["loudness_norm"] = (df["loudness"].clip(-60, 0) + 60) / 60.0

    # These are already in [0, 1] in spotify_songs.csv
    for col in ["energy", "danceability", "valence",
                "acousticness", "instrumentalness", "liveness", "speechiness"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).clip(0, 1)

    # popularity, duration_ms
    for col in ["popularity", "duration_ms"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    log.info("Data cleaning complete.")
    return df.reset_index(drop=True)


# ─────────────────────────────────────────────
# STEP 2 — OWL Ontology
# ─────────────────────────────────────────────

def build_ontology(g_ont: Graph) -> None:
    """Populate the ontology named graph with classes and properties."""

    def add_class(cls, label, comment, subclass_of=None, disjoint_with=None):
        g_ont.add((cls, RDF.type, OWL.Class))
        g_ont.add((cls, RDFS.label, Literal(label)))
        g_ont.add((cls, RDFS.comment, Literal(comment)))
        if subclass_of:
            g_ont.add((cls, RDFS.subClassOf, subclass_of))
        if disjoint_with:
            g_ont.add((cls, OWL.disjointWith, disjoint_with))

    def add_obj_prop(prop, label, domain, range_, inverse_of=None, symmetric=False):
        g_ont.add((prop, RDF.type, OWL.ObjectProperty))
        g_ont.add((prop, RDFS.label, Literal(label)))
        g_ont.add((prop, RDFS.domain, domain))
        g_ont.add((prop, RDFS.range, range_))
        if inverse_of:
            g_ont.add((prop, OWL.inverseOf, inverse_of))
        if symmetric:
            g_ont.add((prop, RDF.type, OWL.SymmetricProperty))

    def add_data_prop(prop, label, domain, range_):
        g_ont.add((prop, RDF.type, OWL.DatatypeProperty))
        g_ont.add((prop, RDFS.label, Literal(label)))
        g_ont.add((prop, RDFS.domain, domain))
        g_ont.add((prop, RDFS.range, range_))

    # Ontology declaration
    ont_uri = URIRef("http://musickg.org/ontology")
    g_ont.add((ont_uri, RDF.type, OWL.Ontology))
    g_ont.add((ont_uri, RDFS.label, Literal("Music Knowledge Graph Ontology")))

    # Classes
    add_class(MUSIC.Artist,
              "Artist",
              "A music artist or group",
              subclass_of=SCHEMA.MusicGroup,
              disjoint_with=MUSIC.Track)

    add_class(MUSIC.Album,
              "Album",
              "A music album released by an artist",
              subclass_of=SCHEMA.MusicAlbum)

    add_class(MUSIC.Track,
              "Track",
              "A single music recording",
              subclass_of=SCHEMA.MusicRecording)

    add_class(MUSIC.Genre,
              "Genre",
              "A musical genre category",
              subclass_of=SCHEMA.MusicGenre)

    add_class(MUSIC.AudioFeatures,
              "AudioFeatures",
              "Audio analysis features extracted from a track")

    # Object Properties
    add_obj_prop(MUSIC.hasAlbum,    "hasAlbum",    MUSIC.Artist, MUSIC.Album)
    add_obj_prop(MUSIC.hasTrack,    "hasTrack",    MUSIC.Album,  MUSIC.Track)
    add_obj_prop(MUSIC.inGenre,     "inGenre",     MUSIC.Track,  MUSIC.Genre)
    add_obj_prop(MUSIC.performedBy, "performedBy", MUSIC.Track,  MUSIC.Artist,
                 inverse_of=MUSIC.performs)
    add_obj_prop(MUSIC.performs,    "performs",    MUSIC.Artist, MUSIC.Track)
    add_obj_prop(MUSIC.hasAudioFeatures, "hasAudioFeatures",
                 MUSIC.Track, MUSIC.AudioFeatures)
    add_obj_prop(MUSIC.similarTo,   "similarTo",   MUSIC.Artist, MUSIC.Artist,
                 symmetric=True)

    # sharedGenreWith (used in inference)
    g_ont.add((MUSIC.sharedGenreWith, RDF.type, OWL.ObjectProperty))
    g_ont.add((MUSIC.sharedGenreWith, RDFS.label, Literal("sharedGenreWith")))
    g_ont.add((MUSIC.sharedGenreWith, RDFS.domain, MUSIC.Track))
    g_ont.add((MUSIC.sharedGenreWith, RDFS.range,  MUSIC.Track))
    g_ont.add((MUSIC.sharedGenreWith, RDF.type, OWL.SymmetricProperty))

    # Datatype Properties
    add_data_prop(MUSIC.trackName,   "trackName",   MUSIC.Track,          XSD.string)
    add_data_prop(MUSIC.artistName,  "artistName",  MUSIC.Artist,         XSD.string)
    add_data_prop(MUSIC.albumName,   "albumName",   MUSIC.Album,          XSD.string)
    add_data_prop(MUSIC.releaseYear, "releaseYear", MUSIC.Album,          XSD.integer)
    add_data_prop(MUSIC.tempo,       "tempo",       MUSIC.AudioFeatures,  XSD.float)
    add_data_prop(MUSIC.energy,      "energy",      MUSIC.AudioFeatures,  XSD.float)
    add_data_prop(MUSIC.danceability,"danceability",MUSIC.AudioFeatures,  XSD.float)
    add_data_prop(MUSIC.valence,     "valence",     MUSIC.AudioFeatures,  XSD.float)
    add_data_prop(MUSIC.loudness,    "loudness",    MUSIC.AudioFeatures,  XSD.float)
    add_data_prop(MUSIC.popularity,  "popularity",  MUSIC.Track,          XSD.integer)
    add_data_prop(MUSIC.durationMs,  "durationMs",  MUSIC.Track,          XSD.integer)

    log.info(f"  Ontology triples: {len(g_ont):,}")


# ─────────────────────────────────────────────
# STEP 3, 4 — Build Named Graphs + Linked Data
# ─────────────────────────────────────────────

def populate_graphs(
    df: pd.DataFrame,
    g_artists: Graph,
    g_albums: Graph,
    g_tracks: Graph,
) -> tuple[int, int]:
    """
    Returns (dbpedia_links, rows_processed)
    """
    dbpedia_links = 0

    seen_artists: set[str] = set()
    seen_albums:  set[str] = set()
    seen_genres:  set[str] = set()

    total = len(df)
    log.info(f"Populating graphs for {total:,} rows …")

    for i, row in enumerate(df.itertuples(index=False), 1):
        if i % 1000 == 0:
            log.info(f"  … {i:,}/{total:,} rows processed")

        artist_name = str(row.artist_name).strip()
        track_name  = str(row.track_name).strip()
        album_name  = str(getattr(row, "album_name", "Unknown Album")).strip()
        genre_name  = str(getattr(row, "genre",      "Unknown")).strip()
        track_id    = str(row.track_id).strip()
        year        = int(row.year)

        a_uri  = artist_uri(artist_name)
        al_uri = album_uri(artist_name, album_name)
        t_uri  = track_uri(track_id)
        g_uri  = genre_uri(genre_name)
        af_uri = audio_uri(track_id)

        # Artist graph
        if artist_name not in seen_artists:
            seen_artists.add(artist_name)
            g_artists.add((a_uri, RDF.type,         MUSIC.Artist))
            g_artists.add((a_uri, MUSIC.artistName, Literal(artist_name, datatype=XSD.string)))
            # DBpedia sameAs
            dbp = URIRef(f"http://dbpedia.org/resource/{quote(artist_name.replace(' ', '_'), safe='')}")
            g_artists.add((a_uri, OWL.sameAs, dbp))
            dbpedia_links += 1

        # Genre
        if genre_name not in seen_genres:
            seen_genres.add(genre_name)
            g_artists.add((g_uri, RDF.type, MUSIC.Genre))
            g_artists.add((g_uri, RDFS.label, Literal(genre_name, datatype=XSD.string)))
            dbp_genre = URIRef(f"http://dbpedia.org/resource/{quote(genre_name.replace(' ', '_'), safe='')}")
            g_artists.add((g_uri, OWL.sameAs, dbp_genre))
            dbpedia_links += 1

        # Album graph
        album_key = (artist_name, album_name)
        if album_key not in seen_albums:
            seen_albums.add(album_key)
            g_albums.add((al_uri, RDF.type,          MUSIC.Album))
            g_albums.add((al_uri, MUSIC.albumName,   Literal(album_name, datatype=XSD.string)))
            g_albums.add((al_uri, MUSIC.releaseYear, Literal(year, datatype=XSD.integer)))
            g_albums.add((a_uri,  MUSIC.hasAlbum,    al_uri))

        # Track graph
        g_tracks.add((t_uri, RDF.type,         MUSIC.Track))
        g_tracks.add((t_uri, MUSIC.trackName,  Literal(track_name, datatype=XSD.string)))
        g_tracks.add((t_uri, MUSIC.performedBy, a_uri))
        g_tracks.add((t_uri, MUSIC.inGenre,    g_uri))
        g_tracks.add((al_uri, MUSIC.hasTrack,  t_uri))

        pop = getattr(row, "popularity", 0) or 0
        dur = getattr(row, "duration_ms", 0) or 0
        g_tracks.add((t_uri, MUSIC.popularity, Literal(int(pop), datatype=XSD.integer)))
        g_tracks.add((t_uri, MUSIC.durationMs, Literal(int(dur), datatype=XSD.integer)))

        # AudioFeatures
        g_tracks.add((t_uri,  MUSIC.hasAudioFeatures, af_uri))
        g_tracks.add((af_uri, RDF.type, MUSIC.AudioFeatures))

        tempo_norm = float(getattr(row, "tempo_norm", 0) or 0)
        energy     = float(getattr(row, "energy", 0) or 0)
        dance      = float(getattr(row, "danceability", 0) or 0)
        valence    = float(getattr(row, "valence", 0) or 0)
        loudness_n = float(getattr(row, "loudness_norm", 0) or 0)
        loudness   = float(getattr(row, "loudness", -60) or -60)

        g_tracks.add((af_uri, MUSIC.tempo,        Literal(tempo_norm, datatype=XSD.float)))
        g_tracks.add((af_uri, MUSIC.energy,       Literal(energy,     datatype=XSD.float)))
        g_tracks.add((af_uri, MUSIC.danceability, Literal(dance,      datatype=XSD.float)))
        g_tracks.add((af_uri, MUSIC.valence,      Literal(valence,    datatype=XSD.float)))
        g_tracks.add((af_uri, MUSIC.loudness,     Literal(loudness_n, datatype=XSD.float)))

    log.info(f"Graph population complete. Artists={len(seen_artists):,}, "
             f"Albums={len(seen_albums):,}, Genres={len(seen_genres):,}")
    return dbpedia_links, len(seen_artists), len(seen_albums), len(seen_genres)


# ─────────────────────────────────────────────
# STEP 5 — RDFS Inference
# ─────────────────────────────────────────────

def apply_inference(
    g_artists: Graph,
    g_albums: Graph,
    g_tracks: Graph,
) -> int:
    """Apply inference rules; returns number of new triples added."""
    added = 0

    # Rule 1: Artist hasAlbum Album ^ Album hasTrack Track → Artist performs Track
    log.info("Inference Rule 1: hasAlbum + hasTrack → performs …")
    album_track_map: dict[URIRef, list[URIRef]] = {}
    for album, _, track in g_tracks.triples((None, MUSIC.hasTrack, None)):
        album_track_map.setdefault(album, []).append(track)

    for artist, _, album in g_albums.triples((None, MUSIC.hasAlbum, None)):
        for track in album_track_map.get(album, []):
            triple = (artist, MUSIC.performs, track)
            if triple not in g_tracks:
                g_tracks.add(triple)
                added += 1

    # Rule 2: similarTo symmetric closure
    log.info("Inference Rule 2: similarTo symmetric closure …")
    sym_pairs = list(g_artists.triples((None, MUSIC.similarTo, None)))
    for x, _, y in sym_pairs:
        triple = (y, MUSIC.similarTo, x)
        if triple not in g_artists:
            g_artists.add(triple)
            added += 1

    # Rule 3: shared genre → sharedGenreWith (top 50 per genre)
    log.info("Inference Rule 3: sharedGenreWith …")
    genre_tracks: dict[URIRef, list[URIRef]] = {}
    for track, _, genre in g_tracks.triples((None, MUSIC.inGenre, None)):
        genre_tracks.setdefault(genre, []).append(track)

    for genre, tracks in genre_tracks.items():
        limited = tracks[:50]
        for i in range(len(limited)):
            for j in range(i + 1, len(limited)):
                t1, t2 = limited[i], limited[j]
                if t1 != t2:
                    g_tracks.add((t1, MUSIC.sharedGenreWith, t2))
                    g_tracks.add((t2, MUSIC.sharedGenreWith, t1))
                    added += 2

    log.info(f"  Inference triples added: {added:,}")
    return added


# ─────────────────────────────────────────────
# STEP 6 — Similarity Computation
# ─────────────────────────────────────────────

def compute_similarity(df: pd.DataFrame, g_artists: Graph) -> int:
    """Compute cosine similarity between artists; add top-3 similarTo triples."""
    log.info("Computing artist similarity …")

    feature_cols = ["tempo_norm", "energy", "danceability", "valence", "loudness_norm"]
    available = [c for c in feature_cols if c in df.columns]

    if not available:
        log.warning("No feature columns found — skipping similarity.")
        return 0

    artist_vecs = (
        df.groupby("artist_name")[available]
        .mean()
        .dropna()
    )
    if len(artist_vecs) < 2:
        return 0

    names  = artist_vecs.index.tolist()
    matrix = artist_vecs.values.astype(float)

    # Normalize rows to unit vectors (safe for cosine)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1
    matrix_norm = matrix / norms

    similarity_links = 0
    n = len(names)

    log.info(f"  Computing similarity for {n:,} artists …")
    for i in tqdm(range(n), desc="Similarity", unit="artist"):
        sims = matrix_norm @ matrix_norm[i]   # dot product = cosine for unit vecs
        sims[i] = -1                           # exclude self
        top3_idx = np.argsort(sims)[-3:][::-1]

        a_src = artist_uri(names[i])
        for j in top3_idx:
            if sims[j] > 0:
                a_tgt = artist_uri(names[j])
                g_artists.add((a_src, MUSIC.similarTo, a_tgt))
                similarity_links += 1

    log.info(f"  Similarity triples added: {similarity_links:,}")
    return similarity_links


# ─────────────────────────────────────────────
# STEP 7 — Serialization
# ─────────────────────────────────────────────

def serialize_graphs(
    cg: ConjunctiveGraph,
    g_ont: Graph,
    stats: dict,
    data_dir: str,
) -> None:
    os.makedirs(data_dir, exist_ok=True)

    log.info("Serialising N-Triples …")
    cg.serialize(destination=os.path.join(data_dir, "music_kg.nt"), format="nt")

    log.info("Serialising RDF/XML …")
    cg.serialize(destination=os.path.join(data_dir, "music_kg.rdf"), format="xml")

    log.info("Serialising Turtle ontology …")
    g_ont.serialize(destination=os.path.join(data_dir, "ontology.ttl"), format="turtle")

    log.info("Writing stats.json …")
    with open(os.path.join(data_dir, "stats.json"), "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2)

    log.info("Serialisation complete.")


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main(csv_path: str = "spotify_songs.csv", data_dir: str = "data") -> None:
    t0 = time.time()

    # ── Step 1 ──────────────────────────────
    df = load_and_clean(csv_path)

    # Build ConjunctiveGraph
    cg = ConjunctiveGraph()
    cg.bind("music",  MUSIC)
    cg.bind("schema", SCHEMA)
    cg.bind("owl",    OWL)
    cg.bind("rdfs",   RDFS)
    cg.bind("xsd",    XSD)
    cg.bind("base",   BASE)

    g_ont     = cg.get_context(G_ONTOLOGY)
    g_artists = cg.get_context(G_ARTISTS)
    g_albums  = cg.get_context(G_ALBUMS)
    g_tracks  = cg.get_context(G_TRACKS)

    # Step 2 — Ontology
    log.info("Building OWL ontology …")
    build_ontology(g_ont)

    # ── Steps 3 & 4 — Populate + Linked Data ─
    dbpedia_links, n_artists, n_albums, n_genres = populate_graphs(df, g_artists, g_albums, g_tracks)

    # ── Step 6 — Similarity ──────────────────
    sim_links = compute_similarity(df, g_artists)

    # ── Step 5 — Inference ───────────────────
    # (after similarity so Rule 2 also closes those links)
    inf_added = apply_inference(g_artists, g_albums, g_tracks)

    # Collect stats
    stats = {
        "total_triples": len(cg),
        "unique_artists": n_artists,
        "unique_albums":  n_albums,
        "unique_tracks":  df["track_id"].nunique(),
        "unique_genres":  n_genres,
        "named_graphs": {
            "ontology": len(g_ont),
            "artists":  len(g_artists),
            "albums":   len(g_albums),
            "tracks":   len(g_tracks),
        },
        "similarity_links":       sim_links,
        "dbpedia_links":          dbpedia_links,
        "inference_triples_added": inf_added,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    log.info("\n=== Stats ===")
    for k, v in stats.items():
        log.info(f"  {k}: {v}")

    # ── Step 7 — Serialise ───────────────────
    serialize_graphs(cg, g_ont, stats, data_dir)

    elapsed = time.time() - t0
    log.info(f"\nDone in {elapsed:.1f}s  ({elapsed/60:.2f} min)")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Spotify CSV → Music Knowledge Graph")
    parser.add_argument("--csv",      default="spotify_songs.csv", help="Input CSV path")
    parser.add_argument("--data-dir", default="data",               help="Output directory")
    args = parser.parse_args()
    main(csv_path=args.csv, data_dir=args.data_dir)
