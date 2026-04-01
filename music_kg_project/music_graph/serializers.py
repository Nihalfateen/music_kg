"""
music_graph/serializers.py
DRF serializers for Django DB models only.
RDF data is returned as plain dicts directly from views.
"""
from rest_framework import serializers
from music_graph.models import SPARQLQueryTemplate, SearchLog


class SPARQLQueryTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SPARQLQueryTemplate
        fields = ['id', 'name', 'description', 'query_text',
                  'category', 'is_featured', 'created_at']


class SearchLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = SearchLog
        fields = ['id', 'query', 'results_count',
                  'entity_types_found', 'searched_at']
