from django.urls import path

from .views import causal_inference, get_variables, openai_suggest_edges, save_graph, upload_csv

urlpatterns = [
    path('variables/', get_variables, name='variables'),
    path('save_graph/', save_graph, name='save_graph'),
    path('causal_inference/', causal_inference, name='causal_inference'),
    path('upload_csv/', upload_csv, name='upload_csv'),
    path('openai/suggest_edges/', openai_suggest_edges, name='openai_suggest_edges'),
]
