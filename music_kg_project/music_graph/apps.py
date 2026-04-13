"""
music_graph/apps.py
"""
from django.apps import AppConfig


class MusicGraphConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'music_graph'
    verbose_name = 'Music Knowledge Graph'

    def ready(self):
        """
        Called once when Django finishes loading.
        Initializes the RDF singleton so all views share one in-memory graph.
        """
        # Avoid running during management commands like migrate / shell
        import sys
        if 'migrate' in sys.argv or 'makemigrations' in sys.argv:
            return

        from django.conf import settings
        from music_graph.rdf_store import store
        from music_graph.similarity import build_engine

        store.load(
            nt_path=settings.RDF_NT_PATH,
            stats_path=settings.RDF_STATS_PATH,
        )

        # Pre-compute artist similarity matrix
        build_engine()

        # Build search index in background thread (non-blocking)
        try:
            from music_graph.sparql_queries import build_search_index_async
            build_search_index_async()
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                f"Search index async start failed: {e}")
