"""
music_kg_project/urls.py
"""
from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse

from music_graph import views

def health_check(request):
    return JsonResponse({"status": "ok", "service": "Music Knowledge Graph API"})


urlpatterns = [
    path('admin/', admin.site.urls),
    path('health/', health_check),
    path('api/', include('music_graph.urls')),
    path('', views.api_home, name='api-home')
]
