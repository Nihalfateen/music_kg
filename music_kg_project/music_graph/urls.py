"""
music_graph/urls.py
"""
from django.urls import path, re_path
from music_graph import views

urlpatterns = [
    path('artists/create/', views.ArtistCreateView.as_view(), name='api_create_artist'),
    path('songs/bulk-create/', views.SongBulkCreateView.as_view(), name='api_create_songs_bulk'),
    path('tracks/update-album/', views.TrackAlbumUpdateView.as_view(), name='update_album_view'),
    path('albums/update-year/', views.AlbumYearUpdateView.as_view(), name='update_album_year'),
    path('tracks/delete/', views.TrackDeleteView.as_view(), name='delete-track'),

    # Artists
    path('artists/', views.ArtistListView.as_view(), name='artist-list'),
    re_path(r'^artists/(?P<slug>.+)/$', views.ArtistDetailView.as_view(), name='artist-detail'),

    # Albums
    re_path(r'^albums/(?P<slug>.+)/$', views.AlbumDetailView.as_view(), name='album-detail'),

    # Tracks
    path('tracks/', views.TrackListView.as_view(), name='track-list'),

    # Search
    path('search/', views.SearchView.as_view(), name='search'),

    # SPARQL
    path('sparql/', views.SPARQLView.as_view(), name='sparql'),
    path('sparql/update/', views.SPARQLUpdateView.as_view(), name='sparql-update'),
    path('sparql-templates/', views.SPARQLTemplatesView.as_view(), name='sparql-templates'),

    # Stats
    path('stats/', views.StatsView.as_view(), name='stats'),

    # Timeline
    path('timeline/', views.TimelineView.as_view(), name='timeline'),
    re_path(r'^timeline/(?P<genre>.+)/$', views.TimelineView.as_view(), name='timeline-genre'),

    # Analytics
    path('genre-landscape/', views.GenreLandscapeView.as_view(), name='genre-landscape'),
    path('audio-distribution/', views.AudioDistributionView.as_view(), name='audio-distribution'),

    path('similar-edges/', views.SimilarityEdgesView.as_view(), name='similar-edges'),
    # Recommendations
    re_path(r'^recommendations/(?P<slug>.+)/$', views.RecommendationsView.as_view(), name='recommendations'),

]
