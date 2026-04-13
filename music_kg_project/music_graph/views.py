"""
music_graph/views.py
All DRF API views for the Music Knowledge Graph.
"""
import time
import logging
from typing import Union

import json

from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from music_graph import sparql_queries as sq
from music_graph import timeline as tl
from music_graph import similarity as sim
from music_graph.models import SearchLog, SPARQLQueryTemplate
from music_graph.rdf_store import store
from music_graph.similarity import get_recommendations, engine_stats
from music_graph.serializers import SPARQLQueryTemplateSerializer

from music_graph.sparql_queries import create_artist_node
from music_graph.sparql_queries import create_songs_bulk
from music_graph.sparql_queries import update_track_album
from music_graph.sparql_queries import update_album_year

log = logging.getLogger(__name__)

CACHE_TTL = 3600  # 1 hour

def api_home(request):
    return JsonResponse({
        "project": "Music Knowledge Graph API",
        "status": "Online",
        "endpoints": {
            "api_root": "/api/",
            "admin": "/admin/",
            "health_check": "/health/"
        }
    })

def _timed_response(data: Union[dict, list], t0: float, status_code=200) -> Response:
    """Wrap data with execution_time_ms field."""
    elapsed = round((time.time() - t0) * 1000, 2)
    if isinstance(data, dict):
        data["execution_time_ms"] = elapsed
    else:
        data = {"results": data, "execution_time_ms": elapsed}
    return Response(data, status=status_code)


class StandardPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/artists/
# ─────────────────────────────────────────────────────────────────────────────

class ArtistListView(APIView):
    def get(self, request):
        t0 = time.time()

        limit_param = request.query_params.get("limit") or request.query_params.get("page_size")
        limit = int(limit_param) if limit_param else 500

        page = int(request.query_params.get("page", 1))
        offset = (page - 1) * limit

        search = request.query_params.get("search", "").strip()
        genre = request.query_params.get("genre", "").strip()

        artists = sq.get_artists(
            search=search or None,
            genre=genre or None,
            limit=limit,
            offset=offset,
        )

        return _timed_response({
            "page": page,
            "results": artists,
            "count": len(artists),
        }, t0)

# ─────────────────────────────────────────────────────────────────────────────
# GET /api/artists/<slug>/
# ─────────────────────────────────────────────────────────────────────────────

@method_decorator(cache_page(CACHE_TTL), name='dispatch')
class ArtistDetailView(APIView):
    def get(self, request, slug):
        t0 = time.time()
        detail = sq.get_artist_detail(slug)
        if not detail:
            return Response(
                {"error": f"Artist '{slug}' not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return _timed_response(detail, t0)


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/albums/<slug>/
# ─────────────────────────────────────────────────────────────────────────────

@method_decorator(cache_page(CACHE_TTL), name='dispatch')
class AlbumDetailView(APIView):
    def get(self, request, slug):
        t0 = time.time()
        detail = sq.get_album_detail(slug)
        if not detail:
            return Response(
                {"error": f"Album '{slug}' not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return _timed_response(detail, t0)


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/tracks/
# ─────────────────────────────────────────────────────────────────────────────

@method_decorator(cache_page(CACHE_TTL), name='dispatch')
class TrackListView(APIView):
    """
    Filters: ?search= ?genre= ?year_min= ?year_max=
             ?energy_min= ?energy_max= ?page= ?page_size=
    """

    def get(self, request):
        t0 = time.time()
        qp = request.query_params
        page = int(qp.get("page", 1))
        page_size = int(qp.get("page_size", 20))
        offset = (page - 1) * page_size

        tracks = sq.get_tracks(
            search=qp.get("search") or None,
            genre=qp.get("genre") or None,
            year_min=qp.get("year_min") or None,
            year_max=qp.get("year_max") or None,
            energy_min=qp.get("energy_min") or None,
            energy_max=qp.get("energy_max") or None,
            limit=page_size,
            offset=offset,
        )
        return _timed_response({
            "page":    page,
            "results": tracks,
            "count":   len(tracks),
        }, t0)


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/search/?q=
# ─────────────────────────────────────────────────────────────────────────────

class SearchView(APIView):
    """Full-text search across artists, albums, tracks."""

    def get(self, request):
        t0 = time.time()
        q = request.query_params.get("q", "").strip()
        genre = request.query_params.get("genre", "").strip()
        e_type = request.query_params.get("type", "").strip()

        page = int(request.query_params.get("page", 1))
        limit = int(request.query_params.get("limit", 20))
        offset = (page - 1) * limit

        if not q and not genre:
            return Response(
                {"error": "Provide ?q= query parameter."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        limit = int(request.query_params.get("limit", 20))

        search_data = sq.full_text_search(q, genre=genre or None, e_type=e_type or None, limit=limit, offset=offset)
        results = search_data["results"]
        total_count = search_data["total_count"]

        entity_types = {}
        for r in results:
            entity_types[r["type"]] = entity_types.get(r["type"], 0) + 1

        try:
            SearchLog.objects.create(
                query=q,
                results_count=len(results),
                entity_types_found=entity_types,
            )
        except Exception:
            pass

        return _timed_response({
            "query":   q,
            "results": results,
            "total_count": total_count,
            "count":   len(results),
            "page": page
        }, t0)


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/sparql/
# ─────────────────────────────────────────────────────────────────────────────

class SPARQLView(APIView):
    """Execute raw SPARQL SELECT queries. POST body: {"query": "SELECT ..."}"""

    def post(self, request):
        t0 = time.time()
        query_string = request.data.get("query", "").strip()
        if not query_string:
            return Response(
                {"error": "POST body must include 'query' field."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        result = sq.execute_raw_sparql(query_string)
        if "error" in result:
            return Response(result, status=status.HTTP_400_BAD_REQUEST)

        result["execution_time_ms"] = round((time.time() - t0) * 1000, 2)
        return Response(result)


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/sparql/update/
# ─────────────────────────────────────────────────────────────────────────────

class SPARQLUpdateView(APIView):
    """
    Execute SPARQL UPDATE operations (INSERT DATA, DELETE DATA, DELETE/INSERT WHERE).
    POST body: {"update": "INSERT DATA { ... }"}

    Examples:
      INSERT DATA  — add new triples
      DELETE DATA  — remove specific triples
      DELETE WHERE — remove triples matching a pattern
      DELETE { ?s ?p ?o } INSERT { ?s ?p ?new } WHERE { ... }  — modify triples
    """

    def post(self, request):
        t0 = time.time()
        update_string = request.data.get("update", "").strip()
        if not update_string:
            return Response(
                {"error": "POST body must include 'update' field."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Detect operation type for logging
        upper = update_string.upper().lstrip()
        if upper.startswith("INSERT"):
            op = "INSERT"
        elif upper.startswith("DELETE"):
            op = "DELETE"
        elif upper.startswith("CLEAR"):
            op = "CLEAR"
        elif upper.startswith("DROP"):
            op = "DROP"
        else:
            op = "UPDATE"

        ok = store.execute_sparql_update(update_string)
        elapsed = round((time.time() - t0) * 1000, 2)

        if ok:
            return Response({
                "status":           "success",
                "operation":        op,
                "backend":          "GraphDB" if store.using_graphdb else "rdflib",
                "execution_time_ms": elapsed,
            })
        else:
            return Response(
                {
                    "error":     "SPARQL UPDATE failed",
                    "operation": op,
                    "execution_time_ms": elapsed,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/stats/
# ─────────────────────────────────────────────────────────────────────────────

@method_decorator(cache_page(CACHE_TTL), name='dispatch')
class StatsView(APIView):
    def get(self, request):
        t0 = time.time()
        stats = store.get_stats()
        return _timed_response(stats, t0)


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/timeline/
# GET /api/timeline/<genre>/
# ─────────────────────────────────────────────────────────────────────────────

@method_decorator(cache_page(CACHE_TTL), name='dispatch')
class TimelineView(APIView):
    def get(self, request, genre=None):
        t0 = time.time()
        start = int(request.query_params.get("start_year", 1950))
        end = int(request.query_params.get("end_year",   2024))

        if genre:
            data = tl.get_genre_evolution(genre)
            return _timed_response({"genre": genre, "evolution": data}, t0)
        else:
            data = tl.get_timeline_data(start, end)
            return _timed_response({"timeline": data}, t0)


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/genre-landscape/
# ─────────────────────────────────────────────────────────────────────────────

@method_decorator(cache_page(CACHE_TTL), name='dispatch')
class GenreLandscapeView(APIView):
    def get(self, request):
        t0 = time.time()
        data = sq.get_genre_landscape()
        return _timed_response({"genres": data}, t0)


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/audio-distribution/
# ─────────────────────────────────────────────────────────────────────────────

@method_decorator(cache_page(CACHE_TTL), name='dispatch')
class AudioDistributionView(APIView):
    def get(self, request):
        t0 = time.time()
        data = sq.get_audio_distribution()
        return _timed_response({"distributions": data}, t0)


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/sparql-templates/
# ─────────────────────────────────────────────────────────────────────────────

@method_decorator(cache_page(CACHE_TTL), name='dispatch')
class SPARQLTemplatesView(APIView):
    def get(self, request):
        t0 = time.time()
        category = request.query_params.get("category")
        qs = SPARQLQueryTemplate.objects.all()
        if category:
            qs = qs.filter(category=category)
        serializer = SPARQLQueryTemplateSerializer(qs, many=True)
        return _timed_response({
            "templates": serializer.data,
            "count": len(serializer.data),
        }, t0)


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/recommendations/<slug>/
# ─────────────────────────────────────────────────────────────────────────────

@method_decorator(cache_page(CACHE_TTL), name='dispatch')
class RecommendationsView(APIView):
    def get(self, request, slug):
        t0 = time.time()
        data = get_recommendations(slug)
        if not data["similar_artists"] and not data["recommended_tracks"]:
            return Response(
                {"error": f"No recommendations found for artist '{slug}'."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return _timed_response(data, t0)


@method_decorator(cache_page(CACHE_TTL), name='dispatch')
class StatsView(APIView):
    def get(self, request):
        t0 = time.time()
        stats = store.get_stats()
        stats["similarity_engine"] = engine_stats()
        return _timed_response(stats, t0)


class SimilarityEdgesView(APIView):
    def get(self, request):
        t0 = time.time()
        edges = sq.get_similarity_edges(limit=2000)
        return _timed_response(edges, t0)

# ─────────────────────────────────────────────────────────────────────────────
# POST /api/artists/create/
# POST /api/songs/bulk-create/
# POST /api/tracks/udate-album/
# POST /api/albums/update-year/
# POST /api/tracks/delete/
# ─────────────────────────────────────────────────────────────────────────────

class ArtistCreateView(APIView):
    def post(self, request):
        t0 = time.time()
        name = request.data.get('name')
        genre = request.data.get('genre')

        if not name or not genre:
            return Response({"error": "Name and genre are required."}, status=status.HTTP_400_BAD_REQUEST)

        success, slug = sq.create_artist_node(name, genre)

        if success:
            return _timed_response({"status": "ok", "slug": slug}, t0, status_code=status.HTTP_201_CREATED)
        else:
            return Response({
                "error": "Artist already exists in the Knowledge Graph",
                "slug": slug
            }, status=status.HTTP_409_CONFLICT)


class SongBulkCreateView(APIView):
    def post(self, request):
        t0 = time.time()
        artist_slug = request.data.get('artist_slug')
        songs = request.data.get('songs', [])

        if not artist_slug:
            return Response({"error": "artist_slug is required."}, status=status.HTTP_400_BAD_REQUEST)

        success, count = sq.create_songs_bulk(artist_slug, songs)
        return _timed_response({"status": "ok", "created": count}, t0, status_code=status.HTTP_201_CREATED)


class TrackAlbumUpdateView(APIView):
    def post(self, request):
        t0 = time.time()
        try:
            track_uri = request.data.get('trackUri')
            artist_uri = request.data.get('artistUri')
            new_album_name = request.data.get('newAlbumName')

            if not all([track_uri, artist_uri, new_album_name]):
                return Response({"error": "Missing required fields (trackUri, artistUri, newAlbumName)."},
                                status=status.HTTP_400_BAD_REQUEST)

            sq.update_track_album(track_uri, artist_uri, new_album_name)
            return _timed_response({'status': 'success'}, t0)
        except Exception as e:
            return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AlbumYearUpdateView(APIView):
    def post(self, request):
        t0 = time.time()
        album_uri = request.data.get('albumUri')
        new_year_raw = request.data.get('newYear')

        if not album_uri or new_year_raw is None:
            return Response({'status': 'error', 'message': 'Missing albumUri or newYear'},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            new_year = int(float(new_year_raw))
        except (ValueError, TypeError):
            return Response({'status': 'error', 'message': 'Year must be a valid number'},
                            status=status.HTTP_400_BAD_REQUEST)

        success = sq.update_album_year(album_uri, new_year)

        if success:
            return _timed_response({'status': 'success'}, t0)
        else:
            return Response({'status': 'error', 'message': 'SPARQL update failed'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class TrackDeleteView(APIView):
    def post(self, request):
        t0 = time.time()
        track_uri = request.data.get('trackUri')

        if not track_uri:
            return Response({'error': 'No track URI provided'}, status=status.HTTP_400_BAD_REQUEST)

        success = sq.delete_track_from_graph(track_uri)

        if success:
            return _timed_response({'message': 'Track deleted successfully'}, t0)
        else:
            return Response({'error': 'Failed to delete track from graph'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
