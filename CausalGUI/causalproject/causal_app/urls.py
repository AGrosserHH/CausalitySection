from django.urls import path
from .views import get_variables, save_graph, causal_inference, upload_csv

urlpatterns = [
    path('variables/', get_variables, name='variables'),
    path('save_graph/', save_graph, name='save_graph'),
    path('causal_inference/', causal_inference, name='causal_inference'),
    path('upload_csv/', upload_csv, name='upload_csv'),
]
