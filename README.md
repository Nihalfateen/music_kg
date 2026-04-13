# 🎵 Music Knowledge Graph

> A full-stack semantic web application featuring a persistent RDF store, SPARQL 1.1 CRUD operations, and real-time audio analytics.

![Python](https://img.shields.io/badge/Python-3.9-blue) ![Django](https://img.shields.io/badge/Django-4.2-green) ![React](https://img.shields.io/badge/React-18-61dafb) ![rdflib](https://img.shields.io/badge/rdflib-SPARQL-orange)

---

## Overview

Music Knowledge Graph transforms a Spotify playlist dataset into a queryable RDF knowledge graph. Artists, albums, tracks, genres, and audio features are modelled as semantic triples and exposed through a Django REST API. A React SPA provides search, discovery, artist profiles, timeline analytics, and a live SPARQL editor.

**Dataset:** 32,833 tracks · 10,693 artists · 6 genres · **569,708 RDF triples**

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Knowledge Graph | rdflib · RDF/NT serialisation · SPARQL 1.1 · custom ontology (`music:`) |
| Backend | Python 3.9 · Django 4.2 · Django REST Framework · django-cors-headers |
| Frontend | React 18 · Vite · Tailwind CSS · Recharts · Framer Motion · Axios |
| Similarity Engine | NumPy · cosine similarity on 5-D audio vectors · Jaccard genre overlap |
| Data Source | Spotify playlist CSV — 32,833 rows, 23 columns |

---

## Repository Layout

```
music_kg/
├── convert_to_rdf.py          # ETL: CSV → RDF triples (NT + RDF/XML)
├── requirements.txt
├── spotify_songs.csv
│
├── music_kg_project/          # Django backend
│   ├── manage.py
│   ├── data/
│   │   ├── music_kg.nt        # 569k RDF triples (loaded at startup)
│   │   └── stats.json
│   └── music_graph/
│       ├── apps.py            # Loads graph + builds similarity engine
│       ├── rdf_store.py       # Singleton ConjunctiveGraph wrapper
│       ├── sparql_queries.py  # All SPARQL query functions + in-memory search index
│       ├── similarity.py      # Cosine + Jaccard recommendation engine
│       ├── timeline.py        # Timeline & genre evolution queries
│       ├── views.py           # 11 DRF APIViews
│       └── urls.py            # 13 API endpoints
│
└── music-kg-frontend/         # React 18 + Vite SPA
    └── src/
        ├── api/index.js       # Axios instance + all endpoint calls
        ├── pages/             # Home, Search, Artist, Album, Timeline, Analytics, SPARQL
        └── components/        # Shared UI components
```

---

## Getting Started

### Prerequisites

- Python 3.9+
- Node.js 18+ and npm
- GraphDB installed and running on port 7200
- A virtual environment (recommended)

### 1 — Generate the RDF graph

Run the ETL script once. It reads the CSV, builds the ontology, and writes `music_kg.nt` (~75 MB) into the data directory.

```bash
cd music_kg
pip install -r requirements.txt
python convert_to_rdf.py \
  --csv spotify_songs.csv \
  --data-dir music_kg_project/data/
```

### 2 — Start the Django backend

```bash
cd music_kg_project
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

> The server starts at **http://127.0.0.1:8000**.
> On first run it loads all 569k triples (~13 s), builds the similarity matrix (~9 s), and indexes 65k entities for fast search (~1 s).

### 3 — Start the React frontend

```bash
cd music-kg-frontend
npm install
npm run dev
```

> The SPA runs at **http://localhost:3000** and proxies `/api/*` requests to the Django backend via Vite.

---

## API Reference

Base URL: `http://localhost:8000/api` — all responses are JSON.

| Method  | Endpoint                   | Description |
|---------|----------------------------|-------------|
| `GET`   | `/artists/`                | Paginated artist list — `?search=` `?genre=` `?page=` `?page_size=` |
| `GET`   | `/artists/<slug>/`         | Full artist profile with albums, top tracks, audio features |
| `GET`   | `/albums/<slug>/`          | Album detail with full track listing |
| `GET`   | `/tracks/`                 | Track list — `?search=` `?genre=` `?year_min=` `?year_max=` `?energy_min=` |
| `GET`   | `/search/?q=`              | Full-text search across artists, albums and tracks (in-memory, < 50 ms) |
| `POST`  | `/sparql/`                 | Execute raw SPARQL SELECT — body: `{ "query": "SELECT ..." }` |
| `GET`   | `/stats/`                  | Graph statistics (triple count, entity counts) |
| `GET`   | `/timeline/`               | Per-year aggregate: track count, avg energy, top genre |
| `GET`   | `/timeline/<genre>/`       | Decade-level genre evolution — energy, danceability, valence |
| `GET`   | `/genre-landscape/`        | Genre scatter data for analytics view |
| `GET`   | `/audio-distribution/`     | Histogram data for danceability, energy, valence, tempo |
| `GET`   | `/sparql-templates/`       | Saved SPARQL query templates |
| `GET`   | `/recommendations/<slug>/` | Similar artists + recommended tracks for a given artist |
| `POST`	 | `/artists/create/`	        | Create a new Artist node|
| `POST`	 | `/songs/bulk-create/`	     | Bulk Insert tracks & albums for an artist|
| `POST`	 | `/tracks/update-album/`	   | Move a track & trigger garbage collection|
| `POST`	 | `/albums/update-year/`	    | Update release year via DELETE/INSERT|
| `POST`	 | `/tracks/delete/`	         | Surgical Delete of a track node|
---

## Features

### ➝ Search
Full-text search is backed by a 65,383-entry in-memory index built from the CSV at startup (< 1 s). Each keystroke scans the index in Python — results return in under 50 ms with no SPARQL overhead.

### ➝ Artist Profiles
Each artist page shows genre badges, an audio radar chart (energy · danceability · valence · tempo · loudness), a sortable top-tracks table, and a discography split into real albums (2+ tracks) and singles.

### ➝ Recommendation Engine
Implemented in `similarity.py` using two algorithms combined at a **60/40 ratio**:

- **Cosine similarity** on a 5-dimensional audio feature vector (energy, danceability, valence, normalised tempo, normalised loudness)
- **Jaccard similarity** on genre sets

The full artist-×-artist matrix is pre-computed on startup and cached with `lru_cache` for O(1) lookups at request time.


### ➝ Timeline & Analytics
The Timeline page charts tracks released per year with avg energy and danceability overlays. The Analytics page shows genre scatter plots, audio-feature histograms, and genre evolution across decades.

---

## Ontology

Namespace: `http://musickg.org/ontology#` (prefix `music:`)

### Classes

| Class | Description |
|-------|-------------|
| `music:Artist` | A recording artist |
| `music:Album` | An album or single release |
| `music:Track` | An individual track |
| `music:Genre` | A playlist genre (pop, rap, rock, latin, r&b, edm) |
| `music:AudioFeatures` | Numerical audio descriptors for a track |

### Object Properties

| Property | Domain → Range |
|----------|---------------|
| `music:hasAlbum` | Artist → Album |
| `music:hasTrack` | Album → Track |
| `music:performedBy` | Track → Artist |
| `music:inGenre` | Track → Genre |
| `music:hasAudioFeatures` | Track → AudioFeatures |

### Data Properties

| Property | Type |
|----------|------|
| `music:artistName`, `music:albumName`, `music:trackName` | `xsd:string` |
| `music:releaseYear` | `xsd:integer` |
| `music:popularity` | `xsd:integer` (0–100) |
| `music:durationMs` | `xsd:integer` |
| `music:energy`, `music:danceability`, `music:valence`, `music:loudness`, `music:tempo` | `xsd:decimal` |

---

## Example SPARQL Queries

**Find all pop artists:**
```sparql
PREFIX music: <http://musickg.org/ontology#>

SELECT DISTINCT ?name WHERE {
  ?track music:inGenre <http://musickg.org/genre/pop> ;
         music:performedBy ?artist .
  ?artist music:artistName ?name .
}
ORDER BY ?name
LIMIT 20
```

**Top tracks by popularity:**
```sparql
PREFIX music: <http://musickg.org/ontology#>

SELECT ?name ?artistName ?popularity WHERE {
  ?track a music:Track ;
         music:trackName ?name ;
         music:performedBy ?artist ;
         music:popularity ?popularity .
  ?artist music:artistName ?artistName .
}
ORDER BY DESC(?popularity)
LIMIT 10
```

---

## Known Limitations

- **rdflib aggregation bug** — `COUNT`, `GROUP BY`, and `AVG` in SPARQL trigger a pyparsing compatibility issue on Python 3.9. Affected queries are rewritten to avoid aggregation or fall back to empty results gracefully.
- **Dataset structure** — the source is playlist-derived, so most "albums" contain only one track. The UI separates real albums (2+ tracks) from singles.
- **Cold start** — the similarity engine pre-computes a ~10k × 10k matrix in memory (~9 s). The server is unresponsive to recommendation requests until this completes.
- **No persistent RDF store** — the graph is reloaded from the NT file on every server restart.
- **Analytics Cold Start** — User-created artists/tracks do not currently have pre-computed audio analytics or popularity scores.
---

## Licence

Released for educational and research purposes.

The Spotify dataset is sourced from Kaggle (public domain) : https://www.kaggle.com/datasets/joebeachcapital/30000-spotify-songs

---

*Built with ♥ using RDF, Django, and React*
