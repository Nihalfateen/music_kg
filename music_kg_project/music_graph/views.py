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
from music_graph.sparql_queries import update_track_metadata

log = logging.getLogger(__name__)

CACHE_TTL = 3600  # 1 hour


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

@method_decorator(cache_page(CACHE_TTL), name='dispatch')
class ArtistListView(APIView):
    """Paginated artist list with optional ?search= and ?genre= filters."""

    def get(self, request):
        t0 = time.time()
        search = request.query_params.get("search", "").strip()
        genre = request.query_params.get("genre",  "").strip()
        page = int(request.query_params.get("page", 1))
        page_size = int(request.query_params.get("page_size", 20))
        offset = (page - 1) * page_size

        artists = sq.get_artists(
            search=search or None,
            genre=genre or None,
            limit=page_size,
            offset=offset,
        )
        return _timed_response({
            "page":    page,
            "results": artists,
            "count":   len(artists),
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
        if not q:
            return Response(
                {"error": "Provide ?q= query parameter."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        limit = int(request.query_params.get("limit", 20))
        results = sq.full_text_search(q, limit=limit)

        # Log the search
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
            pass  # Don't fail API because of logging

        return _timed_response({
            "query":   q,
            "results": results,
            "count":   len(results),
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


import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .sparql_queries import create_artist_node


@csrf_exempt
def api_create_artist(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        name = data.get('name')
        genre = data.get('genre')

        # success is False if the artist already exists OR if GraphDB fails
        success, slug = create_artist_node(name, genre)

        if success:
            return JsonResponse({"status": "ok", "slug": slug}, status=201)
        else:
            return JsonResponse({
                "error": "Artist already exists in the Knowledge Graph",
                "slug": slug
            }, status=409)

    return JsonResponse({"error": "Method Not Allowed"}, status=405)

@csrf_exempt
def api_create_songs_bulk(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        artist_slug = data.get('artist_slug')
        songs = data.get('songs', []) # Expected: [{'name': 's1', 'album': 'a1'}, ...]

        success, count = create_songs_bulk(artist_slug, songs)
        return JsonResponse({"status": "ok", "created": count}, status=201)
    return JsonResponse({"error": "Method not allowed"}, status=405)

@csrf_exempt
def api_update_track(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        success = update_track_metadata(
            track_uri=data.get('track_uri'),
            new_album_name=data.get('new_album_name')
        )
        return JsonResponse({'success': success})